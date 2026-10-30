"""
How stable are the headline numbers? (reliability checks for the paper)

  bootstrap  95% intervals for rRMSE, bias and interval coverage by resampling REGION BLOCKS with
             replacement (2,000 draws), because errors are correlated within a region; plus the
             paired difference E2 - Chloris, to say whether one estimator is really better
  seeds      E2 leave-one-region-out refitted with five LightGBM seeds: the spread of rRMSE says how
             much of a difference between variants could be seed noise

Usage: python -m estimation.reliability
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from estimation.models import feature_columns, leave_one_region_out

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
RES = EST / "results"
B = 2000


def rrmse(y, p):
    return 100 * np.sqrt(np.mean((p - y) ** 2)) / np.mean(y)


def block_bootstrap(df, stat, seed=0):
    rng = np.random.default_rng(seed)
    regions = df["region"].unique()
    groups = {r: g for r, g in df.groupby("region")}
    out = []
    for _ in range(B):
        pick = rng.choice(regions, len(regions), replace=True)
        out.append(stat(pd.concat([groups[r] for r in pick])))
    return np.percentile(out, [2.5, 97.5])


def main() -> None:
    ev = pd.read_parquet(RES / "evaluation_table.parquet").dropna(subset=["E2_loro_lgbm", "E0_chloris"])
    rows = []
    for subset, g in [("All", ev)] + list(ev.groupby("dataset")):
        y = g["agb_Mg_ha"]
        for name, col in [("E2 LORO", "E2_loro_lgbm"), ("E0 Chloris", "E0_chloris")]:
            lo, hi = block_bootstrap(g, lambda d, c=col: rrmse(d["agb_Mg_ha"], d[c]))
            rows.append({"subset": subset, "metric": f"rRMSE {name}", "value": rrmse(y, g[col]), "ci_lo": lo, "ci_hi": hi})
        lo, hi = block_bootstrap(g, lambda d: rrmse(d["agb_Mg_ha"], d["E2_loro_lgbm"]) - rrmse(d["agb_Mg_ha"], d["E0_chloris"]))
        rows.append({"subset": subset, "metric": "rRMSE E2 - Chloris", "value": rrmse(y, g["E2_loro_lgbm"]) - rrmse(y, g["E0_chloris"]), "ci_lo": lo, "ci_hi": hi})
        ins = (g["agb_Mg_ha"] >= g["pi_lo"]) & (g["agb_Mg_ha"] <= g["pi_hi"])
        lo, hi = block_bootstrap(g.assign(ins=ins), lambda d: 100 * d["ins"].mean())
        rows.append({"subset": subset, "metric": "split-conformal coverage %", "value": 100 * ins.mean(), "ci_lo": lo, "ci_hi": hi})

    # cloud-aware CQR coverage, re-derived per plot is not stored, so use the interval table of robust.py
    I = pd.read_parquet(RES / "intervals.parquet")
    I = I.merge(ev[["plot_id"]], on="plot_id")
    I["ins"] = (I["agb_Mg_ha"] >= I["cqr_lo"]) & (I["agb_Mg_ha"] <= I["cqr_hi"])
    lo, hi = block_bootstrap(I, lambda d: 100 * d["ins"].mean())
    rows.append({"subset": "All", "metric": "CQR coverage %", "value": 100 * I["ins"].mean(), "ci_lo": lo, "ci_hi": hi})
    # paired differences behind the improvement-ladder claims (exploratory variants, same plots)
    L = pd.read_parquet(RES / "improvement_preds.parquet")
    for label, a, b in [("ensemble - E2", "Ensemble: mean(E2, Chloris)", "optical + radar + terrain (E2)"),
                        ("radar only - optical only", "radar only (S1 + PALSAR)", "optical only (S2 + Landsat)")]:
        for subset, g in [("All", L)] + list(L.groupby("dataset")):
            g = g.dropna(subset=[a, b])
            f = lambda d, a=a, b=b: rrmse(d["agb_Mg_ha"], d[a]) - rrmse(d["agb_Mg_ha"], d[b])
            lo, hi = block_bootstrap(g, f)
            rows.append({"subset": subset, "metric": f"rRMSE {label}", "value": f(g), "ci_lo": lo, "ci_hi": hi})
    # cloud-aware vs plain CQR when every target plot is clouded (per-plot file from robust.py --only-u4)
    O = pd.read_parquet(RES / "cloud_aware_cqr_plots.parquet").merge(ev[["plot_id", "region"]], on="plot_id")
    c = O[O["condition"] == "fully clouded"].assign(
        ia=lambda d: (d["agb_Mg_ha"] >= d["aware_lo"]) & (d["agb_Mg_ha"] <= d["aware_hi"]),
        ip=lambda d: (d["agb_Mg_ha"] >= d["plain_lo"]) & (d["agb_Mg_ha"] <= d["plain_hi"]))
    f = lambda d: 100 * (d["ia"].mean() - d["ip"].mean())
    lo, hi = block_bootstrap(c, f)
    rows.append({"subset": "All", "metric": "coverage cloud-aware - plain, fully clouded (points)", "value": f(c), "ci_lo": lo, "ci_hi": hi})
    lo, hi = block_bootstrap(c, lambda d: 100 * d["ia"].mean())
    rows.append({"subset": "All", "metric": "cloud-aware CQR coverage %, fully clouded", "value": 100 * c["ia"].mean(), "ci_lo": lo, "ci_hi": hi})
    R = pd.DataFrame(rows).round(2)
    R.to_csv(RES / "bootstrap_ci.csv", index=False)
    print(R.to_string(index=False))

    feat = pd.read_parquet(EST / "plot_manifest.parquet").merge(pd.read_parquet(EST / "left_features_win90.parquet"), on=["plot_id", "date"])
    df = feat.merge(pd.read_parquet(EST / "right_grid_sealed.parquet")[["plot_id", "agb_Mg_ha"]], on="plot_id")
    df = df[df["agb_Mg_ha"] > 1]
    feats = feature_columns(df)
    srows = []
    for seed in range(5):
        e = leave_one_region_out(df, "agb_Mg_ha", "region", feats, seed=seed)
        r = {"seed": seed, "All": rrmse(e["agb_Mg_ha"], e["pred"])}
        for ds, g in e.groupby("dataset"):
            r[ds] = rrmse(g["agb_Mg_ha"], g["pred"])
        srows.append(r)
        print(r, flush=True)
    S = pd.DataFrame(srows)
    S.to_csv(RES / "seed_stability.csv", index=False)
    print(S.describe().loc[["mean", "std", "min", "max"]].round(2).to_string())


if __name__ == "__main__":
    main()
