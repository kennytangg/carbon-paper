"""
Blind protocol for SEQUESTRATION (SAFE, Sabah) and an out-of-region stock check.

Left-grid estimators of dAGB/dt (Mg ha^-1 yr^-1):
  S_zero     no change (the baseline any estimator must beat)
  S0_chloris difference of Chloris annual AGB between the census years, divided by the year gap
  S2_lgbm    difference of E2 stock predictions at the two census dates, divided by the date gap.
             E2 is trained on the 476 stock plots (HCSA, GEO-TREES, Labriere); no SAFE label is released.

Usage: python -m estimation.evaluate_seq --window 90
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from estimation.ledger import BlindLedger
from estimation.models import feature_columns, fit_log_model, predict_log_model, score

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
OUTD = EST / "results"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=90)
    args = ap.parse_args()
    OUTD.mkdir(parents=True, exist_ok=True)
    ledger = BlindLedger(EST / "blind_ledger.jsonl")
    sealed = EST / "seq_right_grid_sealed.parquet"
    ledger.seal_ground_truth(sealed, EST / "seq_plot_manifest.parquet")

    sm = pd.read_parquet(EST / "seq_plot_manifest.parquet")
    lf = pd.read_parquet(EST / f"left_features_win{args.window}_seq.parquet")
    t0 = sm.merge(lf, left_on=["plot_id", "date_t0"], right_on=["plot_id", "date"], how="left")
    t1 = sm.merge(lf, left_on=["plot_id", "date_t1"], right_on=["plot_id", "date"], how="left")

    # Stock model trained on the stock right grid only (SAFE labels are never released)
    stock_feat = pd.read_parquet(EST / f"left_features_win{args.window}.parquet")
    stock = pd.read_parquet(EST / "plot_manifest.parquet").merge(stock_feat, on=["plot_id", "date"])
    labels = pd.read_parquet(EST / "right_grid_sealed.parquet")[["plot_id", "agb_Mg_ha"]]
    train = stock.merge(labels, on="plot_id")
    ledger.append("release_training_labels", fold_target_region="SAFE_all", n_labels=len(train),
                  labels_sha256=hashlib.sha256(train[["plot_id", "agb_Mg_ha"]].sort_values("plot_id").to_csv(index=False).encode()).hexdigest(),
                  target_region_released=bool(train["plot_id"].str.startswith("SAFE_").any()))
    feats = [f for f in feature_columns(train) if f in t0.columns and not f.startswith("s2_")]  # S2 absent before 2017
    model, smear = fit_log_model(train[feats], train["agb_Mg_ha"].to_numpy())
    p0 = predict_log_model(model, smear, t0[feats])
    p1 = predict_log_model(model, smear, t1[feats])
    years = (pd.to_datetime(sm["date_t1"]) - pd.to_datetime(sm["date_t0"])).dt.days / 365.25

    pred = pd.DataFrame({"plot_id": sm["plot_id"], "region": sm["region"], "block": sm["block"],
                         "E2_stock_t0": p0, "E2_stock_t1": p1,
                         "S2_lgbm": (p1 - p0) / years, "S_zero": 0.0})
    c0, c1 = t0.get("chloris_agb_Mg_ha"), t1.get("chloris_agb_Mg_ha")
    y0, y1 = t0.get("chloris_year"), t1.get("chloris_year")
    pred["S0_chloris"] = np.where((y1 - y0) > 0, (c1 - c0) / (y1 - y0), np.nan)
    pred["E0_chloris_stock_t0"] = c0
    p_file = OUTD / "pred_seq.parquet"
    pred.to_parquet(p_file, index=False)
    ledger.commit_predictions("SEQ_S0_S2_Szero", p_file)

    ledger.reveal_ground_truth(sealed)
    assert ledger.verify()
    gt = pd.read_parquet(sealed)
    ev = gt.merge(pred, on=["plot_id", "region", "block"])
    ev["land_use"] = np.where(ev["block"].str.startswith("OP"), "oil_palm",
                     np.where(ev["block"].isin(["OG1", "OG2", "OG3", "VJR"]), "old_growth", "logged_or_riparian"))
    ev.to_parquet(OUTD / "seq_evaluation_table.parquet", index=False)

    rows = []
    for subset, g in [("All SAFE", ev), ("SAFE excl. oil palm", ev[ev["land_use"] != "oil_palm"])]:
        rows.append(score(g, "agb_t0_Mg_ha", "E2_stock_t0", "E2 stock (out-of-region, Borneo)", "Mg AGB/ha", subset))
        rows.append(score(g, "agb_t0_Mg_ha", "E0_chloris_stock_t0", "E0 Chloris stock", "Mg AGB/ha", subset))
    stock_rows = pd.DataFrame(rows)

    # Sequestration can be negative, so score with explicit errors rather than the positive-only helper
    def seq_metrics(g, col, name, subset):
        ok = g[["dagb_Mg_ha_yr", col]].dropna()
        e = ok[col] - ok["dagb_Mg_ha_yr"]
        r = np.corrcoef(ok[col], ok["dagb_Mg_ha_yr"])[0, 1] if ok[col].std() > 0 else np.nan
        return {"model_name": name, "subset": subset, "n": len(ok), "mean_true": ok["dagb_Mg_ha_yr"].mean(),
                "mean_pred": ok[col].mean(), "rmse": float(np.sqrt(np.mean(e ** 2))), "mae": float(np.mean(np.abs(e))),
                "bias": float(e.mean()), "pearson_r": r}
    srows = []
    for subset, g in [("All SAFE", ev), ("SAFE excl. oil palm", ev[ev["land_use"] != "oil_palm"])]:
        for col, name in [("S_zero", "No change (baseline)"), ("S0_chloris", "S0 Chloris difference"), ("S2_lgbm", "S2 LightGBM stock difference")]:
            srows.append(seq_metrics(g, col, name, subset))
        # Block level (aggregation): mean over the plots of each block
        blk = g.groupby("block")[["dagb_Mg_ha_yr", "S_zero", "S0_chloris", "S2_lgbm"]].mean().reset_index()
        for col, name in [("S_zero", "No change (baseline)"), ("S0_chloris", "S0 Chloris difference"), ("S2_lgbm", "S2 LightGBM stock difference")]:
            srows.append(seq_metrics(blk, col, name + " [block mean]", subset))
    seq_rows = pd.DataFrame(srows).round(3)
    stock_rows.to_csv(OUTD / "seq_stock_check_metrics.csv", index=False)
    seq_rows.to_csv(OUTD / "seq_metrics.csv", index=False)
    print(stock_rows[["model_name", "subset", "n_samples", "rmse", "rrmse_pct", "relative_bias_pct", "r2_score", "lins_ccc"]].to_string(index=False))
    print(seq_rows.to_string(index=False))
    print("ledger chain valid:", ledger.verify())


if __name__ == "__main__":
    main()
