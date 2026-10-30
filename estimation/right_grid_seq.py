"""
Right grid for SEQUESTRATION: SAFE Project repeat tree censuses (Sabah, Malaysian Borneo, 2011-2020).

Per plot and census: AGB = sum over living stems of Chave et al. (2014) Eq. 4, with height from a
local log-log height-diameter model fitted on the heights SAFE measured, and wood density from the
Global Wood Density Database (species -> genus -> family -> plot mean, SE-Asian records first).
Sequestration = (AGB_last - AGB_first) / years between the plot's median census dates, which SAFE
records per stem to the day.

Writes data/estimation/seq_right_grid_sealed.parquet and seq_plot_manifest.parquet, sealed in the ledger.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadr

from estimation.ledger import BlindLedger
from estimation.right_grid import chave2014_eq4_kg
from src.formulas import IPCC_DEFAULT_CARBON_FRACTION_TROPICAL as CF

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "gt_raw"
OUT = ROOT / "data" / "estimation"
CENSUSES = ["2011", "2012", "2012B", "2013", "2014", "2014B", "2015", "2016", "2017", "2018", "2019", "2020"]
PLOT_AREA_HA = 0.0625  # 25 m x 25 m SAFE sampling plots


def wood_density_lookup() -> tuple[dict, dict, dict, float]:
    wd = pyreadr.read_r(RAW / "wood_density" / "wdData_BIOMASS_v2.1.11.rda")["wdData"]
    sea = wd[wd["regionId"].isin(["SouthEastAsiaTrop", "SouthEastAsia"])]
    def means(df, keys):
        return df.groupby(keys)["wd"].mean().to_dict()
    sp = {**means(wd, ["genus", "species"]), **means(sea, ["genus", "species"])}
    ge = {**means(wd, "genus"), **means(sea, "genus")}
    fa = {**means(wd, "family"), **means(sea, "family")}
    return sp, ge, fa, float(sea["wd"].mean())


def load_census() -> pd.DataFrame:
    df = pd.read_excel(RAW / "safe" / "TreeCensus11_20.xlsx", sheet_name="Census11_20", header=9)
    df = df.rename(columns={df.columns[0]: "_row"})
    df["PlotID"] = df["Block"].astype(str).str.strip() + "_" + df["Plot"].astype(str).str.strip()
    return df.replace("NA", np.nan)


def build() -> None:
    df = load_census()
    sp, ge, fa, wd_default = wood_density_lookup()

    def wd_of(r):
        g, s, f = r.get("Genus"), r.get("Species"), r.get("Family")
        return sp.get((g, s)) or ge.get(g) or fa.get(f) or np.nan
    df["wd"] = df.apply(wd_of, axis=1)
    df["wd"] = df["wd"].fillna(df.groupby("PlotID")["wd"].transform("mean")).fillna(wd_default)

    # Local height-diameter model: ln H = a + b ln D on all measured (stem, census) pairs
    hd = []
    for c in CENSUSES:
        d = pd.to_numeric(df.get(f"DBH{c}_mm_clean"), errors="coerce") / 10.0
        h = pd.to_numeric(df.get(f"Length_{c}_m"), errors="coerce")
        ok = (d >= 10) & (h > 1.3) & (h < 80)
        hd.append(pd.DataFrame({"d": d[ok], "h": h[ok]}))
    hd = pd.concat(hd)
    b, a = np.polyfit(np.log(hd["d"]), np.log(hd["h"]), 1)
    resid = np.log(hd["h"]) - (a + b * np.log(hd["d"]))
    smear = float(np.mean(np.exp(resid)))
    print(f"H-D model: ln H = {a:.3f} + {b:.3f} ln D (n={len(hd)}, Duan smear {smear:.3f})")

    rows = []
    for c in CENSUSES:
        d = pd.to_numeric(df.get(f"DBH{c}_mm_clean"), errors="coerce") / 10.0
        dates = pd.to_datetime(df.get(f"Date_{c}"), errors="coerce", dayfirst=True)
        alive = d >= 10  # SAFE census threshold is 10 cm DBH
        h = np.exp(a + b * np.log(d.where(alive))) * smear
        agb = chave2014_eq4_kg(d.where(alive), h, df["wd"]) / 1000.0
        part = pd.DataFrame({"PlotID": df["PlotID"], "census": c, "agb_Mg": agb, "date": dates.where(alive), "alive": alive})
        g = part.groupby("PlotID").agg(agb_Mg=("agb_Mg", "sum"), n_stems=("alive", "sum"), date=("date", "median"))
        g = g[(g["n_stems"] > 0) & g["date"].notna()].reset_index()
        g["census"] = c
        rows.append(g)
    pc = pd.concat(rows, ignore_index=True)
    pc["agb_Mg_ha"] = pc["agb_Mg"] / PLOT_AREA_HA

    gaz = json.loads((RAW / "safe" / "gazetteer.geojson").read_text(encoding="utf-8"))
    loc = {f["properties"]["location"]: (f["properties"]["centroid_y"], f["properties"]["centroid_x"]) for f in gaz["features"]}
    seq = []
    for pid, g in pc.sort_values("date").groupby("PlotID"):
        if pid not in loc or len(g) < 2:
            continue
        first, last = g.iloc[0], g.iloc[-1]
        years = (last["date"] - first["date"]).days / 365.25
        if years < 3:
            continue
        seq.append({
            "plot_id": f"SAFE_{pid}", "dataset": "SAFE_Sabah", "block": re.sub(r"_.*", "", pid),
            "lat": loc[pid][0], "lon": loc[pid][1],
            "date_t0": first["date"].date().isoformat(), "date_t1": last["date"].date().isoformat(),
            "census_t0": first["census"], "census_t1": last["census"], "years": years, "n_censuses": len(g),
            "agb_t0_Mg_ha": first["agb_Mg_ha"], "agb_t1_Mg_ha": last["agb_Mg_ha"],
            "n_stems_t0": int(first["n_stems"]), "n_stems_t1": int(last["n_stems"]),
        })
    seq = pd.DataFrame(seq)
    seq["dagb_Mg_ha_yr"] = (seq["agb_t1_Mg_ha"] - seq["agb_t0_Mg_ha"]) / seq["years"]
    seq["dC_tC_ha_yr"] = seq["dagb_Mg_ha_yr"] * CF
    seq["region"] = "SAFE_" + seq["block"]
    seq["radius_m"] = 15.0
    seq["date_precision"] = "day"
    seq["formula_id"] = "CHAVE_2014_EQ4 + local H-D (ln-ln, Duan) + GWDD wood density; stock difference"

    OUT.mkdir(parents=True, exist_ok=True)
    sealed, manifest = OUT / "seq_right_grid_sealed.parquet", OUT / "seq_plot_manifest.parquet"
    seq.to_parquet(sealed, index=False)
    seq[["plot_id", "dataset", "region", "block", "lat", "lon", "date_t0", "date_t1", "date_precision", "radius_m"]].to_parquet(manifest, index=False)
    pc.to_parquet(OUT / "seq_plot_census_series_sealed.parquet", index=False)
    e = BlindLedger(OUT / "blind_ledger.jsonl").seal_ground_truth(sealed, manifest)
    print(f"SAFE: {len(seq)} plots with >=3 years between censuses, {seq['block'].nunique()} blocks")
    print(seq[["years", "n_censuses", "agb_t0_Mg_ha", "agb_t1_Mg_ha", "dagb_Mg_ha_yr"]].describe().round(2).to_string())
    print(seq.groupby("block")["dagb_Mg_ha_yr"].agg(["size", "mean", "median"]).round(2).to_string())
    print("sealed:", e["sealed_sha256"][:16])


if __name__ == "__main__":
    build()
