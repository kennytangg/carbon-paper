"""
Improvement ladder for the left grid (RQ2): which changes move the blind stock estimate closer to the
right grid? Every variant is scored leave-one-region-out, so the target region is never seen.

These runs come AFTER the stock reveal, so they are exploratory: the variant list is fixed here in
code and every variant is reported, including the ones that do not help.

Usage: python -m estimation.improve --window 90
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from estimation.models import feature_columns, leave_one_region_out, score

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
OUTD = EST / "results"

VARIANTS = {
    "optical only (S2 + Landsat)": ("s2_", "ls_"),
    "radar only (S1 + PALSAR)": ("s1_", "palsar_"),
    "optical + radar": ("s2_", "ls_", "s1_", "palsar_"),
    "optical + radar + terrain (E2)": ("s2_", "ls_", "s1_", "palsar_", "dem_"),
    "E2 + Chloris product as feature": ("s2_", "ls_", "s1_", "palsar_", "dem_", "chloris_agb"),
    "E2 + Chloris + plot footprint": ("s2_", "ls_", "s1_", "palsar_", "dem_", "chloris_agb", "radius_m"),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=90)
    args = ap.parse_args()
    feat = pd.read_parquet(EST / "plot_manifest.parquet").merge(
        pd.read_parquet(EST / f"left_features_win{args.window}.parquet"), on=["plot_id", "date"], how="left")
    gt = pd.read_parquet(EST / "right_grid_sealed.parquet")[["plot_id", "agb_Mg_ha"]]
    df = feat.merge(gt, on="plot_id")
    df = df[df["agb_Mg_ha"] > 1].reset_index(drop=True)  # log target; drops 2 near-zero plots

    preds = df[["plot_id", "dataset", "region", "agb_Mg_ha"]].copy()
    for name, prefixes in VARIANTS.items():
        feats = feature_columns(df, prefixes)
        e = leave_one_region_out(df, "agb_Mg_ha", "region", feats)
        preds = preds.merge(e[["plot_id", "pred"]].rename(columns={"pred": name}), on="plot_id", how="left")
        print(f"{name}: {len(feats)} features")
    preds["Ensemble: mean(E2, Chloris)"] = (preds["optical + radar + terrain (E2)"] + df["chloris_agb_Mg_ha"]) / 2
    preds["E0 Chloris (reference)"] = df["chloris_agb_Mg_ha"]

    rows = []
    cols = [c for c in preds.columns if c not in ("plot_id", "dataset", "region", "agb_Mg_ha")]
    for subset, g in [("All", preds)] + [(d, x) for d, x in preds.groupby("dataset")]:
        for c in cols:
            ok = g.dropna(subset=[c])
            rows.append(score(ok, "agb_Mg_ha", c, c, "Mg AGB/ha", subset))
    out = pd.DataFrame(rows)
    out.to_csv(OUTD / "improvement_ladder.csv", index=False)
    preds.to_parquet(OUTD / "improvement_preds.parquet", index=False)
    print(out[["model_name", "subset", "n_samples", "rrmse_pct", "relative_bias_pct", "r2_score", "lins_ccc"]].to_string(index=False))


if __name__ == "__main__":
    main()
