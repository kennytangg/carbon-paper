"""
Right grid: field ground truth computed with the standard deterministic chain
(Chave et al. 2014 -> IPCC carbon fraction 0.47 -> 44/12), then sealed.

Writes two files and seals them in the ledger:
  data/estimation/right_grid_sealed.parquet  outcomes; only the evaluator may open it
  data/estimation/plot_manifest.parquet      id, region, coordinates, date, radius; the ONLY
                                             thing the satellite-only left grid ever sees
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

from estimation.ledger import BlindLedger
from src.formulas import IPCC_DEFAULT_CARBON_FRACTION_TROPICAL as CF, MOLECULAR_WEIGHT_RATIO_CO2_C as CO2_C

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "gt_raw"
OUT = ROOT / "data" / "estimation"


def chave2014_eq4_kg(d_cm, h_m, wd):
    return 0.0673 * (wd * d_cm ** 2 * h_m) ** 0.976


def hcsa_trees() -> pd.DataFrame:
    """Screened tree records of HCSA Indonesia with per-tree Chave Eq. 4 AGB and the protocol area."""
    t = pd.read_csv(RAW / "hcsa" / "hcsa_indonesia_field_plots.csv")
    t["plot_key"] = t["Region"].str.strip() + "|" + t["PLOT"].astype(str).str.strip()
    req = ["DBH (cm)", "Height (m)", "Wood density (g/cm3)", "Plot Area (Ha)", "Lat_Y", "Long_X"]
    for c in req[:4] + ["Biomass (kg)/pohon"]:
        t[c] = pd.to_numeric(t[c], errors="coerce")  # the archive marks a tree-less plot with "-"
    t = t[~t[req[:4]].isna().all(axis=1)]
    bad = set(t.loc[t[req].isna().any(axis=1), "plot_key"])
    bad |= set(t.loc[t["Height (m)"] < 1.3, "plot_key"])
    bad |= set(t.loc[~t["Plot Area (Ha)"].isin([0.01, 0.05]), "plot_key"])
    # DBH > 200 cm is implausible here (e.g. RU09: Gluta renghas recorded at 480 cm, which matches a
    # circumference typed into the DBH column, 480/pi = 153 cm). Excluded, never imputed.
    bad |= set(t.loc[t["DBH (cm)"] > 200, "plot_key"])
    coords = t.groupby("plot_key")[["Lat_Y", "Long_X"]].nunique()
    bad |= set(coords[(coords > 1).any(axis=1)].index)
    t = t[~t["plot_key"].isin(bad)].copy()
    # HCSA protocol (Toolkit v2.0 Module 4): stems 5-15 cm are counted in the 0.01 ha subplot, stems
    # >=15 cm in the 0.05 ha plot. Records that contradict the rule are expanded by the protocol area,
    # otherwise one misfiled large stem is multiplied by 100 instead of 20.
    t = t[t["DBH (cm)"] >= 5].copy()
    t["area_protocol_ha"] = np.where(t["DBH (cm)"] >= 15, 0.05, 0.01)
    t["area_reassigned"] = ~np.isclose(t["area_protocol_ha"], t["Plot Area (Ha)"])
    print(f"HCSA: {int(t['area_reassigned'].sum())} records contradict the diameter-to-area rule and were reassigned")
    t["agb_kg"] = chave2014_eq4_kg(t["DBH (cm)"], t["Height (m)"], t["Wood density (g/cm3)"])
    t["agb_Mg_ha_contrib"] = t["agb_kg"] / 1000.0 / t["area_protocol_ha"]
    t["reproduces_archive"] = np.isclose(t["agb_kg"], t["Biomass (kg)/pohon"], rtol=1e-3)
    print(f"HCSA: {t['plot_key'].nunique()} plots kept, {len(bad)} plots screened out")
    return t


def hcsa() -> pd.DataFrame:
    """HCSA Indonesia (2023 release). Nested circular plots: 5-15 cm stems in 0.01 ha, >=15 cm in 0.05 ha."""
    t = hcsa_trees()
    g = t.groupby("plot_key").agg(
        region=("Region", "first"), lat=("Lat_Y", "first"), lon=("Long_X", "first"),
        agb_Mg_ha=("agb_Mg_ha_contrib", "sum"), n_trees=("agb_kg", "size"),
        land_cover=("Land Cover Update", "first"), archive_reproduced_frac=("reproduces_archive", "mean"),
        n_area_reassigned=("area_reassigned", "sum"),
    ).reset_index()
    g["plot_id"] = "HCSA_" + g["plot_key"].str.replace(r"[^A-Za-z0-9]+", "_", regex=True)
    g["dataset"] = "HCSA_Indonesia"
    g["region"] = "IDN_" + g["region"].str.replace(" ", "")
    g["date"] = "2023-01-01"
    g["date_precision"] = "year"
    g["timestamp_basis"] = "dataset_release_year"
    g["radius_m"] = 10.0
    g["formula_id"] = "CHAVE_2014_EQ4 (recomputed per tree) + nested-area expansion"
    return g.drop(columns=["plot_key"])


def geotrees() -> pd.DataFrame:
    gj = json.loads((RAW / "geotrees" / "geotrees_plots.geojson").read_text(encoding="utf-8"))
    rows = []
    for f in gj["features"]:
        geom, p = f["geometry"], f["properties"]
        if geom["type"] == "Point":
            lon, lat = geom["coordinates"][:2]
        else:
            ring = np.array(geom["coordinates"][0][:-1])
            lon, lat = ring[:, 0].mean(), ring[:, 1].mean()
        rows.append({**p, "lon": lon, "lat": lat})
    df = pd.DataFrame(rows)
    g = df.groupby("Plot_ID").agg(lat=("lat", "mean"), lon=("lon", "mean"), agb_Mg_ha=("AGB", "mean"),
                                  census_year=("CensusYear", "first"), network=("Network", "first"),
                                  n_subplots=("AGB", "size")).reset_index()
    g["plot_id"] = "GEOTREES_" + g["Plot_ID"]
    g["dataset"] = "GEO-TREES"
    # Spatial blocks for leave-one-region-out: continent + 10-degree cell
    cont = np.where(g["lon"] < -30, "AM", np.where(g["lon"] < 60, "AF", "AS"))
    g["region"] = "GT_" + cont + "_" + (g["lat"] // 10).astype(int).astype(str) + "_" + (g["lon"] // 10).astype(int).astype(str)
    g["date"] = g["census_year"].astype(int).astype(str) + "-07-01"
    g["date_precision"] = "year"
    g["timestamp_basis"] = "census_year"
    g["radius_m"] = 40.0
    g["formula_id"] = "Network AGB (Chave 2014 family), as published"
    print(f"GEO-TREES: {len(g)} plots")
    return g.drop(columns=["Plot_ID"])


def labriere() -> pd.DataFrame:
    z = zipfile.ZipFile(RAW / "labriere" / "tropisar_afrisar_insitu_lidar.zip")
    parts = []
    for name, campaign_date in [("CSV_TropiSAR_AfriSAR/TropiSAR_plotbased_AGB.csv", "2009-08-15"),
                                ("CSV_TropiSAR_AfriSAR/AfriSAR_plotbased_AGB.csv", "2016-02-15")]:
        d = pd.read_csv(io.BytesIO(z.read(name)), sep=None, engine="python")  # delimiter differs from comma
        d["date"] = campaign_date
        parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    d = d[d["Scale"].astype(str).str.startswith("1")].copy()  # 1 ha units only: least geolocation noise
    for c in ["agb_loc", "cred_loc_2.5", "cred_loc_97.5", "sw_x", "nw_x", "se_x", "ne_x", "sw_y", "nw_y", "se_y", "ne_y"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    zones = {"Nouragues": 32622, "Paracou": 32622, "Mondah": 32632, "Lope": 32732, "Mabounie": 32732, "Rabi": 32732}
    cx = d[["sw_x", "nw_x", "se_x", "ne_x"]].mean(axis=1)
    cy = d[["sw_y", "nw_y", "se_y", "ne_y"]].mean(axis=1)
    lat, lon = np.full(len(d), np.nan), np.full(len(d), np.nan)
    for site, epsg in zones.items():
        m = (d["Site"].str.upper() == site.upper()).to_numpy()
        if m.any():
            tr = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
            lon[m], lat[m] = tr.transform(cx[m].to_numpy(), cy[m].to_numpy())
    g = pd.DataFrame({
        "plot_id": "LAB_" + d["Area_code"].astype(str), "dataset": "Labriere2018",
        "region": "LAB_" + d["Site"].astype(str), "lat": lat, "lon": lon,
        "agb_Mg_ha": d["agb_loc"].to_numpy(), "agb_ci_lo": d["cred_loc_2.5"].to_numpy(),
        "agb_ci_hi": d["cred_loc_97.5"].to_numpy(), "date": d["date"].to_numpy(),
    })
    g["date_precision"] = "campaign_year"
    g["timestamp_basis"] = "campaign_year"
    g["radius_m"] = 40.0
    g["formula_id"] = "CHAVE_2014_EQ4 with local H-D model (agb_loc)"
    g = g.dropna(subset=["lat", "lon", "agb_Mg_ha"])
    print(f"Labriere: {len(g)} one-hectare units")
    return g


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    gt = pd.concat([hcsa(), geotrees(), labriere()], ignore_index=True)
    gt = gt[gt["agb_Mg_ha"] > 0].copy()
    gt["carbon_tC_ha"] = gt["agb_Mg_ha"] * CF
    gt["co2e_tCO2e_ha"] = gt["carbon_tC_ha"] * CO2_C
    manifest_cols = ["plot_id", "dataset", "region", "lat", "lon", "date", "date_precision", "timestamp_basis", "radius_m"]
    sealed, manifest = OUT / "right_grid_sealed.parquet", OUT / "plot_manifest.parquet"
    gt.to_parquet(sealed, index=False)
    gt[manifest_cols].to_parquet(manifest, index=False)
    e = BlindLedger(OUT / "blind_ledger.jsonl").seal_ground_truth(sealed, manifest)
    print(gt.groupby("dataset").agg(n=("plot_id", "size"), agb_mean=("agb_Mg_ha", "mean"), regions=("region", "nunique")).round(1))
    print("sealed:", e["sealed_sha256"][:16], "manifest:", e["public_manifest_sha256"][:16])


if __name__ == "__main__":
    build()
