"""
Does more (and sharper) data bring the blind estimate closer to the field answer?

Every variant is leave-one-region-out against the sealed right grid. Run after the stock reveal, so it
is exploratory; every variant is reported.

  baseline E2         Sentinel-1/2, Landsat, PALSAR (Planetary Computer), terrain
  + canopy height     Meta 1 m and ETH 10 m canopy height in and around the plot
  + GEDI              spaceborne lidar footprints (L4A biomass, L2A height) and L4B grid
  + CCI               ESA CCI Biomass, nearest year
  + all               everything above, plus GEE PALSAR at the field year and Hansen loss
  height only (power) AGB = a * H^b on the 1 m canopy height, fitted on other regions: what a
                      canopy-height model, as a drone lidar would give, achieves from height alone
  products as-is      GEDI L4A mean within 1 km, GEDI L4B, ESA CCI (no fitting)

Usage: python -m estimation.accuracy_gee
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from estimation.models import feature_columns, leave_one_region_out, score
from estimation.reliability import block_bootstrap, rrmse

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
RES = EST / "results"

BASE = ("s2_", "ls_", "s1_", "palsar_", "dem_")
CHM = ("meta_", "eth_")
GEDI = ("gedi500_", "gedi1k_", "l4b_")
CCI = ("cci_mean",)
EXTRA = ("pal_hh", "pal_hv", "hansen_")


def main() -> None:
    m = pd.read_parquet(EST / "plot_manifest.parquet")
    f = m.merge(pd.read_parquet(EST / "left_features_win90.parquet"), on=["plot_id", "date"], how="left")
    g = pd.read_parquet(EST / "left_features_gee.parquet")
    g = g.drop(columns=[c for c in g.columns if c.endswith(("_count", "_year")) and c not in ("cci_year", "pal_year")])
    f = f.merge(g, on=["plot_id", "date"], how="left")
    gt = pd.read_parquet(EST / "right_grid_sealed.parquet")[["plot_id", "agb_Mg_ha"]]
    df = f.merge(gt, on="plot_id")
    df = df[df["agb_Mg_ha"] > 1].reset_index(drop=True)
    print("coverage of new inputs:", {c: round(df[c].notna().mean(), 2) for c in ["meta_plot_mean", "eth_plot_mean", "gedi1k_agbd_mean", "l4b_mean", "cci_mean"]})

    variants = {"baseline E2": BASE, "+ canopy height": BASE + CHM, "+ GEDI": BASE + GEDI, "+ CCI": BASE + CCI,
                "+ canopy height + GEDI": BASE + CHM + GEDI, "+ all new inputs": BASE + CHM + GEDI + CCI + EXTRA,
                "canopy height + GEDI only (no optical/radar)": CHM + GEDI}
    preds = df[["plot_id", "dataset", "region", "agb_Mg_ha"]].copy()
    for name, pref in variants.items():
        feats = feature_columns(df, pref)
        e = leave_one_region_out(df, "agb_Mg_ha", "region", feats)
        preds = preds.merge(e[["plot_id", "pred"]].rename(columns={"pred": name}), on="plot_id", how="left")
        print(f"{name}: {len(feats)} features", flush=True)

    # height-only power model AGB = a H^b on the 1 m canopy height, fitted on other regions (log-log)
    h = df["meta_plot_mean"].clip(lower=0.5)
    p = np.full(len(df), np.nan)
    for reg in df["region"].unique():
        te, tr = (df["region"] == reg).to_numpy(), (df["region"] != reg).to_numpy()
        ok = tr & h.notna().to_numpy()
        b, a = np.polyfit(np.log(h[ok]), np.log(df.loc[ok, "agb_Mg_ha"]), 1)
        res = np.log(df.loc[ok, "agb_Mg_ha"]) - (a + b * np.log(h[ok]))
        p[te] = np.exp(a + b * np.log(h[te])) * np.mean(np.exp(res))
    preds["height only, power law (1 m CHM)"] = p
    preds["product: GEDI L4A 1 km"] = df["gedi1k_agbd_mean"]
    preds["product: GEDI L4B"] = df["l4b_mean"]
    preds["product: ESA CCI"] = df["cci_mean"]
    preds["product: Chloris (earlier E0)"] = df["chloris_agb_Mg_ha"]

    rows = []
    cols = [c for c in preds.columns if c not in ("plot_id", "dataset", "region", "agb_Mg_ha")]
    for subset, gg in [("All", preds)] + list(preds.groupby("dataset")):
        for c in cols:
            ok = gg.dropna(subset=[c])
            if len(ok) < 10:
                continue
            r = score(ok, "agb_Mg_ha", c, c, "Mg AGB/ha", subset)
            r["coverage_n"] = len(ok)
            rows.append(r)
    R = pd.DataFrame(rows)
    R.to_csv(RES / "accuracy_gee.csv", index=False)
    preds.to_parquet(RES / "accuracy_gee_preds.parquet", index=False)
    pd.set_option("display.width", 220)
    print(R[["model_name", "subset", "n_samples", "rrmse_pct", "relative_bias_pct", "r2_score", "lins_ccc"]].round(3).to_string(index=False))

    # is the best variant really better than baseline? region-block bootstrap of the paired difference
    best = R[(R["subset"] == "All") & R["model_name"].str.startswith("+")].sort_values("rrmse_pct").iloc[0]["model_name"]
    out = []
    for subset, gg in [("All", preds)] + list(preds.groupby("dataset")):
        gg = gg.dropna(subset=[best, "baseline E2"])
        fn = lambda d: rrmse(d["agb_Mg_ha"], d[best]) - rrmse(d["agb_Mg_ha"], d["baseline E2"])
        lo, hi = block_bootstrap(gg, fn)
        out.append({"subset": subset, "comparison": f"{best} - baseline", "diff_points": fn(gg), "ci_lo": lo, "ci_hi": hi})
    B = pd.DataFrame(out).round(2)
    B.to_csv(RES / "accuracy_gee_bootstrap.csv", index=False)
    print(B.to_string(index=False))


if __name__ == "__main__":
    main()
