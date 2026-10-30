"""
Exploratory sequestration variants (RQ3), run AFTER the SAFE reveal and reported as such.

Oil-palm blocks are excluded: Chave 2014 is a dicot-tree allometry and SAFE records palm "DBH"
including frond bases, so the right grid is not valid there (the subset was fixed before the reveal).

  S2c  E2 stock difference using only sensors present at BOTH dates (Landsat + terrain), so the
       difference is not an artefact of Sentinel-1 or PALSAR appearing between t0 and t1
  S3   LightGBM on change features (Landsat t1 - t0, Chloris t1 - t0, plus t0 state), trained on the
       OTHER SAFE blocks' measured change and predicting the held-out block (leave-one-block-out)

Also reports the noise floor: the spread of E2 stock errors divided by the census gap, i.e. the
smallest annual change a stock-difference estimator could resolve.

Usage: python -m estimation.improve_seq --window 90
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from estimation.models import _lgbm, feature_columns, fit_log_model, predict_log_model

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
OUTD = EST / "results"


def metrics(y, p, name, unit="Mg AGB/ha/yr"):
    ok = ~(np.isnan(y) | np.isnan(p))
    e = p[ok] - y[ok]
    return {"model_name": name, "n": int(ok.sum()), "mean_true": y[ok].mean(), "mean_pred": p[ok].mean(),
            "rmse": float(np.sqrt(np.mean(e ** 2))), "mae": float(np.mean(np.abs(e))), "bias": float(e.mean()),
            "pearson_r": float(np.corrcoef(y[ok], p[ok])[0, 1]) if np.std(p[ok]) > 0 else np.nan}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=90)
    args = ap.parse_args()
    ev = pd.read_parquet(OUTD / "seq_evaluation_table.parquet")
    ev = ev[ev["land_use"] != "oil_palm"].reset_index(drop=True)
    sm = ev[["plot_id", "block", "date_t0", "date_t1", "years", "dagb_Mg_ha_yr", "agb_t0_Mg_ha"]]
    lf = pd.read_parquet(EST / f"left_features_win{args.window}_seq.parquet")
    t0 = sm.merge(lf, left_on=["plot_id", "date_t0"], right_on=["plot_id", "date"], how="left")
    t1 = sm.merge(lf, left_on=["plot_id", "date_t1"], right_on=["plot_id", "date"], how="left")

    # S2c: stock model on consistent sensors only
    stock = pd.read_parquet(EST / "plot_manifest.parquet").merge(
        pd.read_parquet(EST / f"left_features_win{args.window}.parquet"), on=["plot_id", "date"])
    stock = stock.merge(pd.read_parquet(EST / "right_grid_sealed.parquet")[["plot_id", "agb_Mg_ha"]], on="plot_id")
    stock = stock[stock["agb_Mg_ha"] > 1]
    feats = feature_columns(stock, ("ls_", "dem_"))
    m, s = fit_log_model(stock[feats], stock["agb_Mg_ha"].to_numpy())
    p0, p1 = predict_log_model(m, s, t0[feats]), predict_log_model(m, s, t1[feats])
    ev["S2c_consistent"] = (p1 - p0) / ev["years"]

    # S3: change model, leave-one-SAFE-block-out
    lsf = [c for c in feats if c.startswith("ls_")]
    X = pd.DataFrame({f"d_{c}": t1[c] - t0[c] for c in lsf})
    X = X.join(t0[lsf].add_prefix("t0_"))
    X["d_chloris"] = (t1["chloris_agb_Mg_ha"] - t0["chloris_agb_Mg_ha"]) / (t1["chloris_year"] - t0["chloris_year"]).replace(0, np.nan)
    X["years"] = ev["years"]
    y = ev["dagb_Mg_ha_yr"].to_numpy()
    s3 = np.full(len(ev), np.nan)
    for b in ev["block"].unique():
        te = (ev["block"] == b).to_numpy()
        mdl = _lgbm().set_params(n_estimators=200, num_leaves=7, min_child_samples=15).fit(X[~te], y[~te])
        s3[te] = mdl.predict(X[te])
    ev["S3_change_lobo"] = s3
    # No satellite at all: the mean measured rate of the other blocks (a regional default rate)
    ev["S_regional_default"] = [ev.loc[ev["block"] != b, "dagb_Mg_ha_yr"].mean() for b in ev["block"]]

    cols = ["S_zero", "S_regional_default", "S0_chloris", "S2_lgbm", "S2c_consistent", "S3_change_lobo"]
    rows = []
    for level, g in [("plot", ev), ("block mean", ev.groupby("block")[["dagb_Mg_ha_yr"] + cols].mean())]:
        for col in cols:
            r = metrics(g["dagb_Mg_ha_yr"].to_numpy(), g[col].to_numpy(dtype=float), col)
            r["level"] = level
            rows.append(r)
    out = pd.DataFrame(rows).round(3)
    out.to_csv(OUTD / "seq_improvement.csv", index=False)
    print(out.to_string(index=False))

    # Noise floor of stock differencing
    err0 = np.log(p0) - np.log(ev["agb_t0_Mg_ha"].clip(lower=1))
    sd_stock = float(np.std(p0 - ev["agb_t0_Mg_ha"]))
    print(f"E2 stock error SD at t0 (consistent sensors): {sd_stock:.1f} Mg/ha; median census gap {ev['years'].median():.2f} yr")
    print(f"field dAGB: mean {y.mean():.2f}, SD {y.std():.2f} Mg/ha/yr; log-error SD {np.std(err0):.2f}")
    print(f"if t0 and t1 errors were independent, differencing noise would be {sd_stock * np.sqrt(2) / ev['years'].median():.1f} Mg/ha/yr")


if __name__ == "__main__":
    main()
