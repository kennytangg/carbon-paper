"""
Run the blind protocol end to end for carbon STOCK:

  1. left grid predicts from satellite features only (E0 products, E2 leave-one-region-out ML)
  2. each estimator's predictions are hashed and committed to the ledger
  3. the right grid is revealed (digest checked against its seal) and every estimator is scored

E2 needs labels from the training regions. Those are released per fold by the evaluator, and the
hash of every released label set is logged, so the ledger shows the target region was never released.

Usage: python -m estimation.evaluate --window 90
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from estimation.ledger import BlindLedger
from estimation.models import (aggregation_curve, feature_columns, k_shot_curve, leave_one_region_out, score)
from src.formulas import IPCC_DEFAULT_CARBON_FRACTION_TROPICAL as CF

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
OUTD = EST / "results"


def e0_products(feat: pd.DataFrame) -> pd.DataFrame:
    out = feat[["plot_id"]].copy()
    out["E0_chloris"] = feat.get("chloris_agb_Mg_ha")
    # Spawn et al. (2020) harmonized map stores AGB carbon density in MgC/ha with scale factor 0.1
    out["E0_hgb2010"] = feat.get("hgb2010_raw") * 0.1 / CF if "hgb2010_raw" in feat else np.nan
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=90)
    args = ap.parse_args()
    OUTD.mkdir(parents=True, exist_ok=True)
    ledger = BlindLedger(EST / "blind_ledger.jsonl")
    manifest = pd.read_parquet(EST / "plot_manifest.parquet")
    feat = manifest.merge(pd.read_parquet(EST / f"left_features_win{args.window}.parquet"), on=["plot_id", "date"], how="left")

    sealed = EST / "right_grid_sealed.parquet"
    ledger.seal_ground_truth(sealed, EST / "plot_manifest.parquet")  # opens a new evaluation epoch

    # ---- 1-2. Blind estimators: predict and commit before anything is revealed ----
    e0 = e0_products(feat)
    p_e0 = OUTD / "pred_E0.parquet"
    e0.to_parquet(p_e0, index=False)
    ledger.commit_predictions("E0_offtheshelf_products", p_e0)

    # ---- E2: leave-one-region-out with per-fold label release (logged) ----
    gt_all = pd.read_parquet(sealed)[["plot_id", "agb_Mg_ha"]]
    feats = feature_columns(feat)
    df = feat.merge(gt_all, on="plot_id")  # evaluator-side join; folds below only ever train on other regions
    for reg in sorted(df["region"].unique()):
        released = df.loc[df["region"] != reg, ["plot_id", "agb_Mg_ha"]].sort_values("plot_id")
        ledger.append("release_training_labels", fold_target_region=reg, n_labels=len(released),
                      labels_sha256=hashlib.sha256(released.to_csv(index=False).encode()).hexdigest(),
                      target_region_released=bool((released["plot_id"].isin(df.loc[df.region == reg, "plot_id"])).any()))
    e2 = leave_one_region_out(df, "agb_Mg_ha", "region", feats)
    e2_out = e2[["plot_id", "pred", "pi_lo", "pi_hi", "fold_region"]].rename(columns={"pred": "E2_loro_lgbm"})
    p_e2 = OUTD / "pred_E2.parquet"
    e2_out.to_parquet(p_e2, index=False)
    ledger.commit_predictions("E2_loro_lightgbm", p_e2)

    # ---- 3. Reveal and score ----
    ledger.reveal_ground_truth(sealed)
    assert ledger.verify(), "ledger chain broken"
    gt = pd.read_parquet(sealed)
    ev = gt.merge(e0, on="plot_id").merge(e2_out, on="plot_id", how="left").merge(
        feat[["plot_id"] + [c for c in feat.columns if c.endswith(("_min_offset_days", "_year_gap", "_n_clear"))]], on="plot_id", how="left")
    ev.to_parquet(OUTD / "evaluation_table.parquet", index=False)

    rows = []
    for subset, g in [("All", ev)] + list(ev.groupby("dataset")):
        for col, name in [("E0_chloris", "E0 Chloris (off-the-shelf)"), ("E0_hgb2010", "E0 HGB 2010 (off-the-shelf)"),
                          ("E2_loro_lgbm", "E2 LightGBM leave-one-region-out")]:
            rows.append(score(g, "agb_Mg_ha", col, name, "Mg AGB/ha", subset,
                              *(("pi_lo", "pi_hi") if col == "E2_loro_lgbm" else (None, None))))
    metrics = pd.DataFrame(rows)
    metrics.to_csv(OUTD / "stock_metrics.csv", index=False)
    print(metrics[["model_name", "subset", "n_samples", "rmse", "rrmse_pct", "bias", "relative_bias_pct", "r2_score",
                   "lins_ccc"] + (["pi90_coverage"] if "pi90_coverage" in metrics else [])].to_string(index=False))

    e2v = ev.dropna(subset=["E2_loro_lgbm"])
    k_shot_curve(e2v, "agb_Mg_ha", "E2_loro_lgbm", "region").to_csv(OUTD / "kshot_curve.csv", index=False)
    aggregation_curve(e2v, "agb_Mg_ha", "E2_loro_lgbm", "region").to_csv(OUTD / "aggregation_curve.csv", index=False)
    print("ledger entries:", len(ledger.entries()), "| chain valid:", ledger.verify())


if __name__ == "__main__":
    main()
