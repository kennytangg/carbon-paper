"""
External blind test: 35 'Danum Revised' plots, Sabah, Malaysian Borneo, measured Jan-Jun 2020.

Source: Zenodo 10.5281/zenodo.8042468 (CC BY 4.0), 0.28 ha circular plots (30 m radius), every
stem >= 10 cm with DBH, height and species; plot centres by GPS (UTM 50N). None of these plots
trains anything, and the three GEO-TREES Danum plots (DAN-01..03, region GT_AS_0_11) are left out
of training too, so the valley is unseen.

The production method is fixed before the seal is opened (PRODUCTION below):
  map      LightGBM on log AGB, AlphaEarth embeddings + canopy height + GEDI (accuracy_embeddings),
           trained on every other plot
  estimate map x exp(-mu), mu the mean log ratio map/field of the realm's regions (>= 10 plots),
           from the leave-one-region-out predictions
  credit   map x exp(-q), q the region-level conformal quantile (delta 0.1) over all regions with
           >= 10 plots (crediting_fixes.region_q)

Steps, in order (each writes to data/estimation/external/ and the Danum ledger):
  seal      right grid: Chave 2014 Eq. 4 on live stems, measured height (a local ln-ln H-D model
            for the 167 stems without one), GWDD wood density as in right_grid_seq; sealed
  features  embeddings (2020), Earth Engine canopy height and GEDI, CHMv2, from the manifest only
  predict   train, predict, commit the prediction file's hash
  reveal    open the seal and score: per plot, the 35-plot total, and 1,000 draws of 10 plots

Usage: python -m estimation.external_danum {seal,features,predict,reveal}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

from estimation.ledger import BlindLedger
from estimation.right_grid import chave2014_eq4_kg
from estimation.right_grid_seq import wood_density_lookup

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
OUT = EST / "external"
RAW = ROOT / "data" / "gt_raw" / "danum"
TREES = RAW / "DanumRevised_35Plots_FullPlotData_Trees_2020_edit_4.11.2022.xlsx"
LOCS = RAW / "DanumRevisedLocations.geojson"
RADIUS_M = 30.0
AREA_HA = np.pi * RADIUS_M ** 2 / 10_000
DEAD_NOTES = {"D1", "D2", "D3", "D4"}
EXCLUDE_REGIONS = {"GT_AS_0_11"}
MIN_REGION_PLOTS = 10
DELTA = 0.10
PRODUCTION = "embeddings + CH + GEDI"
SEALED, MANIFEST = OUT / "danum_right_grid_sealed.parquet", OUT / "danum_manifest.parquet"
FEATURES, PREDS = OUT / "danum_features.parquet", OUT / "danum_predictions.parquet"
LEDGER = OUT / "danum_ledger.jsonl"


def live_stems() -> pd.DataFrame:
    t = pd.read_excel(TREES, sheet_name=0)
    dead = t["Notes"].isin(DEAD_NOTES) | t["Comments"].astype(str).str.lower().str.contains(r"(?<!ali)\bdead")
    t = t[~dead & (t["Distance.m"] <= RADIUS_M) & t["DBH.mm"].notna()].copy()
    t["D_cm"] = t["DBH.mm"] / 10
    t["plot"] = t["PlotNo"].astype(str).str.rstrip("D").astype(int)
    return t


def seal() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    t = live_stems()
    # heights: measured, else a ln-ln H-D model on this dataset's measured stems (Duan smearing)
    ok = t["Height_m"] > 1.3
    b, a = np.polyfit(np.log(t.loc[ok, "D_cm"]), np.log(t.loc[ok, "Height_m"]), 1)
    smear = np.mean(np.exp(np.log(t.loc[ok, "Height_m"]) - (a + b * np.log(t.loc[ok, "D_cm"]))))
    t["H_m"] = t["Height_m"].where(ok, np.exp(a + b * np.log(t["D_cm"])) * smear)
    sp, ge, fa, wd_default = wood_density_lookup()
    t["wd"] = [sp.get((g, s)) or ge.get(g) or fa.get(str(f).strip().title()) or np.nan
               for g, s, f in zip(t["Genus"], t["Species"], t["Family"])]
    t["wd"] = t["wd"].fillna(t.groupby("plot")["wd"].transform("mean")).fillna(wd_default)
    t["agb_kg"] = chave2014_eq4_kg(t["D_cm"], t["H_m"], t["wd"])
    gt = t.groupby("plot").agg(n_trees=("agb_kg", "size"), agb_kg=("agb_kg", "sum"), date=("Date", "median")).reset_index()
    gt["agb_Mg_ha"] = gt["agb_kg"] / 1000 / AREA_HA
    loc = json.loads(LOCS.read_text(encoding="utf-8"))
    to_ll = Transformer.from_crs("EPSG:32650", "EPSG:4326", always_xy=True)
    xy = {int(f["properties"]["PLOTNUMBER"]): to_ll.transform(*f["geometry"]["coordinates"][:2]) for f in loc["features"]}
    gt["lon"], gt["lat"] = [xy[p][0] for p in gt["plot"]], [xy[p][1] for p in gt["plot"]]
    gt["plot_id"] = "DANUM_" + gt["plot"].astype(str).str.zfill(2)
    gt["date"] = pd.to_datetime(gt["date"]).dt.strftime("%Y-%m-%d")
    gt = gt.assign(dataset="Danum2020", region="DANUM", date_precision="day", timestamp_basis="median stem date",
                   radius_m=RADIUS_M, formula_id="CHAVE_2014_EQ4 + measured H (local H-D where missing) + GWDD wood density")
    cols = ["plot_id", "dataset", "region", "lat", "lon", "date", "date_precision", "timestamp_basis", "radius_m"]
    gt.drop(columns=["agb_kg"]).to_parquet(SEALED, index=False)
    gt[cols].to_parquet(MANIFEST, index=False)
    e = BlindLedger(LEDGER).seal_ground_truth(SEALED, MANIFEST)
    print(f"sealed {len(gt)} plots, {int(gt['n_trees'].sum())} live stems; heights modelled for {int((~ok).sum())}")
    print("sealed:", e["sealed_sha256"][:16], "manifest:", e["public_manifest_sha256"][:16])


def features() -> None:
    from estimation import extract_chm_v2, extract_embeddings, extract_gee
    m = pd.read_parquet(MANIFEST)
    g = extract_gee.run(m.assign(key=m["plot_id"] + "|" + m["date"], year=pd.to_datetime(m["date"]).dt.year)[
        ["key", "lat", "lon", "radius_m", "year"]], "danum")
    g[["plot_id", "date"]] = g["key"].str.split("|", expand=True)
    g = g.drop(columns=[c for c in g.columns if c.endswith(("_count", "_year")) and c not in ("cci_year", "pal_year")] + ["key"])
    e = pd.DataFrame(extract_embeddings.chunk_rows(m, 2020)).drop(columns=["emb_year"])
    extract_chm_v2.CACHE.mkdir(parents=True, exist_ok=True)
    for r in m.itertuples(index=False):
        extract_chm_v2.fetch(r.plot_id, r.lon, r.lat)
    v2 = pd.DataFrame([{"plot_id": r.plot_id, **extract_chm_v2.patch_features(np.load(extract_chm_v2.CACHE / f"{r.plot_id}.npy"), r.radius_m, "chm2_")}
                       for r in m.itertuples(index=False)])
    F = m[["plot_id", "date"]].merge(g, on=["plot_id", "date"], how="left").merge(e, on="plot_id", how="left").merge(v2, on="plot_id", how="left")
    F.to_parquet(FEATURES, index=False)
    print(f"features: {F.shape}, missing embeddings {F['emb_A00'].isna().sum()}, missing GEDI 1 km {F['gedi1k_agbd_mean'].isna().sum()}")


def calibration(preds: pd.DataFrame) -> tuple[float, float]:
    """mu of the Indo-Malayan realm and the region-level q, from leave-one-region-out predictions."""
    from estimation.conformal_crediting import conformal_q
    from estimation.tree_count import realm
    m = pd.read_parquet(EST / "plot_manifest.parquet")[["plot_id", "lat", "lon"]]
    d = preds.merge(m, on="plot_id")
    d = d[~d["region"].isin(EXCLUDE_REGIONS)]
    n = d.groupby("region").size()
    d = d[d["region"].isin(n[n >= MIN_REGION_PLOTS].index)]
    z = np.log(d.groupby("region")[PRODUCTION].sum() / d.groupby("region")["agb_Mg_ha"].sum())
    rl = d.groupby("region").apply(lambda g: realm(g["lon"].iloc[0], g["lat"].iloc[0])).reindex(z.index)
    return float(z[rl == "Indo-Malaya"].mean()), conformal_q(z, DELTA)


def predict() -> None:
    from estimation.accuracy_embeddings import CHM, EMB, GEDI, features as train_features
    from estimation.models import feature_columns, fit_log_model, predict_log_model
    tr = train_features()
    tr = tr[~tr["region"].isin(EXCLUDE_REGIONS)].reset_index(drop=True)
    feats = feature_columns(tr, EMB + CHM + GEDI)
    F = pd.read_parquet(FEATURES)
    missing = [c for c in feats if c not in F]
    assert not missing, f"features missing for Danum: {missing[:5]}"
    model, smear = fit_log_model(tr[feats], tr["agb_Mg_ha"].to_numpy())
    mu, q = calibration(pd.read_parquet(EST / "results" / "accuracy_embeddings_preds.parquet"))
    P = F[["plot_id"]].copy()
    P["map_agb_Mg_ha"] = predict_log_model(model, smear, F[feats])
    P["estimate_agb_Mg_ha"] = P["map_agb_Mg_ha"] * np.exp(-mu)
    P["credit_agb_Mg_ha"] = P["map_agb_Mg_ha"] * np.exp(-q)
    P.to_parquet(PREDS, index=False)
    e = BlindLedger(LEDGER).commit_predictions(f"production: {PRODUCTION}; mu={mu:.4f}; q={q:.4f}", PREDS)
    print(f"{len(feats)} features, trained on {len(tr)} plots; mu = {mu:.3f} (x{np.exp(-mu):.3f}), q = {q:.3f} (x{np.exp(-q):.3f})")
    print("committed:", e["predictions_sha256"][:16])


def reveal() -> None:
    from estimation.reliability import rrmse
    BlindLedger(LEDGER).reveal_ground_truth(SEALED)
    d = pd.read_parquet(SEALED).merge(pd.read_parquet(PREDS), on="plot_id")
    rows = []
    for c in ["map_agb_Mg_ha", "estimate_agb_Mg_ha", "credit_agb_Mg_ha"]:
        rng = np.random.default_rng(0)
        draws = [100 * d[c].iloc[i].mean() / d["agb_Mg_ha"].iloc[i].mean()
                 for i in (rng.choice(len(d), 10, replace=False) for _ in range(1000))]
        rows.append({"estimate": c.replace("_agb_Mg_ha", ""), "plots": len(d), "rrmse_pct": rrmse(d["agb_Mg_ha"], d[c]),
                     "total_pct_of_field": 100 * d[c].sum() / d["agb_Mg_ha"].sum(),
                     "draws10_median_pct": np.median(draws), "draws10_p5_pct": np.percentile(draws, 5),
                     "draws10_p95_pct": np.percentile(draws, 95), "draws10_within_25pct": 100 * np.mean(np.abs(np.array(draws) - 100) <= 25),
                     "draws10_above_field_pct": 100 * np.mean(np.array(draws) > 100)})
    R = pd.DataFrame(rows)
    R.to_csv(EST / "results" / "external_danum.csv", index=False)
    d.to_csv(EST / "results" / "external_danum_plots.csv", index=False)
    print(f"field AGB: mean {d['agb_Mg_ha'].mean():.0f} Mg/ha, median {d['agb_Mg_ha'].median():.0f}")
    print(R.round(1).to_string(index=False))


def exploratory() -> None:
    """After the reveal, not committed: the published canopy-height equations on Danum's CHMv2 patches."""
    from estimation.extract_chm import HALF
    from estimation.extract_chm_v2 import CACHE
    from estimation.height_equations import equations
    yy, xx = np.mgrid[0:2 * HALF, 0:2 * HALF]
    inside = np.hypot(yy + 0.5 - HALF, xx + 0.5 - HALF) <= RADIUS_M
    d = pd.read_parquet(SEALED)[["plot_id", "agb_Mg_ha"]]
    v = [np.load(CACHE / f"{p}.npy")[inside] for p in d["plot_id"]]
    tch = pd.Series([x.mean() for x in v])
    e = pd.DataFrame(equations(tch, pd.Series([(x > 20).mean() for x in v]), pd.Series([(x < 19).mean() for x in v])))
    R = pd.DataFrame({"estimate": [f"{c} [CHMv2]" for c in e.columns], "total_pct_of_field": [100 * e[c].sum() / d["agb_Mg_ha"].sum() for c in e.columns]})
    R.to_csv(EST / "results" / "external_danum_equations.csv", index=False)
    print(f"Danum CHMv2 mean height {tch.mean():.1f} m")
    print(R.round(1).to_string(index=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["seal", "features", "predict", "reveal", "exploratory"])
    {"seal": seal, "features": features, "predict": predict, "reveal": reveal, "exploratory": exploratory}[ap.parse_args().step]()
