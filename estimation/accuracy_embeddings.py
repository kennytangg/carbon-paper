"""
Do the AlphaEarth satellite embeddings bring the blind estimate closer to the field answer?

Run after the stock reveal, so it is exploratory. Every variant is leave-one-region-out and is scored
twice: per plot, and on the same 1,000 simulated projects as simulations.py (median % of the field
carbon, share within +-25%, and the conformal credit with its over-crediting rate).

  best map                 E2 + canopy height + GEDI (the paper's best, recomputed as a check)
  + embeddings             the best map's inputs plus the 64 embedding bands, in the plot and 100 m around
  embeddings + CH + GEDI   Earth Engine assets only: no time-matched composites, so a polygon in any
                           year from 2017 can be read the same way
  embeddings only          the 128 embedding columns
  linear: emb + CH + GEDI  ridge regression on log AGB, the same inputs; a linear model is a band
                           expression in Earth Engine, so an app can map it without a Python service
  embeddings + CHMv2 ...   the Meta/WRI canopy height v2 (extract_chm_v2) in place of, or beside, v1

Usage: python -m estimation.accuracy_embeddings
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from estimation.accuracy_gee import BASE, CHM, GEDI
from estimation.models import feature_columns, fit_log_model, predict_log_model
from estimation.reliability import block_bootstrap, rrmse
from estimation.simulations import DELTA, conformal_q_by_region, draw_projects
from estimation.tree_benchmark import eval_table

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
RES = EST / "results"
EMB = ("emb_", "embb_")
CHM2 = ("chm2_",)
REF = "best map"


def features() -> pd.DataFrame:
    m = pd.read_parquet(EST / "plot_manifest.parquet")
    f = m.merge(pd.read_parquet(EST / "left_features_win90.parquet"), on=["plot_id", "date"], how="left")
    g = pd.read_parquet(EST / "left_features_gee.parquet")
    g = g.drop(columns=[c for c in g.columns if c.endswith(("_count", "_year")) and c not in ("cci_year", "pal_year")])
    e = pd.read_parquet(EST / "left_features_embeddings.parquet").drop(columns=["emb_year"])
    v2 = pd.read_parquet(EST / "left_features_chm_v2.parquet")
    f = f.merge(g, on=["plot_id", "date"], how="left").merge(e, on=["plot_id", "date"], how="left").merge(v2, on=["plot_id", "date"], how="left")
    gt = pd.read_parquet(EST / "right_grid_sealed.parquet")[["plot_id", "agb_Mg_ha"]]
    df = f.merge(gt, on="plot_id")
    return df[df["agb_Mg_ha"] > 1].reset_index(drop=True)


def loro_lgbm(df: pd.DataFrame, feats: list) -> np.ndarray:
    p = np.full(len(df), np.nan)
    for reg in df["region"].unique():
        te, tr = (df["region"] == reg).to_numpy(), (df["region"] != reg).to_numpy()
        m, s = fit_log_model(df.loc[tr, feats], df.loc[tr, "agb_Mg_ha"].to_numpy())
        p[te] = predict_log_model(m, s, df.loc[te, feats])
    return p


def loro_ridge(df: pd.DataFrame, feats: list) -> np.ndarray:
    """Ridge on log AGB; the penalty is chosen by grouped CV over the training regions only."""
    p = np.full(len(df), np.nan)
    for reg in df["region"].unique():
        te, tr = (df["region"] == reg).to_numpy(), (df["region"] != reg).to_numpy()
        X, y, grp = df.loc[tr, feats], np.log(df.loc[tr, "agb_Mg_ha"].to_numpy()), df.loc[tr, "region"]
        pipe = make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(), Ridge())
        cv = GridSearchCV(pipe, {"ridge__alpha": np.logspace(-1, 4, 11)}, cv=GroupKFold(5), scoring="neg_mean_squared_error")
        cv.fit(X, y, groups=grp)
        smear = float(np.mean(np.exp(y - cv.predict(X))))
        p[te] = np.exp(cv.predict(df.loc[te, feats])) * smear
    return p


def project_scores(d: pd.DataFrame, col: str) -> list:
    q = conformal_q_by_region(d.assign(map_agb_Mg_ha=d[col]))
    rows = []
    for s, reg, g in draw_projects(d):
        pct = 100 * g[col].mean() / g["agb_Mg_ha"].mean()
        credit = pct * np.exp(-q[reg]) if np.isfinite(q[reg]) else 0.0
        rows.append({"sim": s, "dataset": g["dataset"].iloc[0], "pct": pct, "credit_pct": credit})
    S = pd.DataFrame(rows)
    out = []
    for subset, x in [("All", S)] + list(S.groupby("dataset")):
        out.append({"subset": subset, "projects": len(x), "median_pct": x["pct"].median(), "p5_pct": x["pct"].quantile(.05),
                    "p95_pct": x["pct"].quantile(.95), "within_25pct": 100 * ((x["pct"] - 100).abs() <= 25).mean(),
                    "credit_median_pct": x["credit_pct"].median(), "over_credited_pct": 100 * (x["credit_pct"] > 100).mean()})
    return out


def main() -> None:
    df = features()
    ref_feats = feature_columns(df, BASE + CHM + GEDI)
    variants = {REF: ("lgbm", BASE + CHM + GEDI), "+ embeddings": ("lgbm", BASE + CHM + GEDI + EMB),
                "embeddings + CH + GEDI": ("lgbm", EMB + CHM + GEDI), "embeddings only": ("lgbm", EMB),
                "linear: emb + CH + GEDI": ("ridge", EMB + CHM + GEDI),
                "embeddings + CHMv2 + GEDI": ("lgbm", EMB + CHM2 + ("eth_",) + GEDI),
                "embeddings + CHMv1/v2 + GEDI": ("lgbm", EMB + CHM + CHM2 + GEDI)}
    preds = df[["plot_id", "dataset", "region", "agb_Mg_ha"]].copy()
    for name, (kind, pref) in variants.items():
        feats = feature_columns(df, pref)
        preds[name] = (loro_lgbm if kind == "lgbm" else loro_ridge)(df, feats)
        print(f"{name}: {len(feats)} features", flush=True)

    d = eval_table()[["plot_id", "dataset", "region", "agb_Mg_ha", "map_agb_Mg_ha"]]
    d = d.merge(preds.drop(columns=["dataset", "region", "agb_Mg_ha"]), on="plot_id", how="left")
    assert np.allclose(d[REF], d["map_agb_Mg_ha"]), "the recomputed best map differs from accuracy_gee"
    assert len(ref_feats) > 0

    plot_rows, proj_rows, boot = [], [], []
    for name in variants:
        for subset, g in [("All", d)] + list(d.groupby("dataset")):
            plot_rows.append({"variant": name, "subset": subset, "n": len(g), "rrmse_pct": rrmse(g["agb_Mg_ha"], g[name]),
                              "bias_pct": 100 * (g[name].mean() / g["agb_Mg_ha"].mean() - 1)})
        proj_rows += [{"variant": name, **r} for r in project_scores(d, name)]
        if name != REF:
            fn = lambda x, n=name: rrmse(x["agb_Mg_ha"], x[n]) - rrmse(x["agb_Mg_ha"], x[REF])
            lo, hi = block_bootstrap(d, fn)
            boot.append({"comparison": f"{name} - {REF}", "diff_points": fn(d), "ci_lo": lo, "ci_hi": hi})
    P, J, B = pd.DataFrame(plot_rows), pd.DataFrame(proj_rows), pd.DataFrame(boot)
    P.to_csv(RES / "accuracy_embeddings.csv", index=False)
    J.to_csv(RES / "accuracy_embeddings_projects.csv", index=False)
    B.to_csv(RES / "accuracy_embeddings_bootstrap.csv", index=False)
    d.to_parquet(RES / "accuracy_embeddings_preds.parquet", index=False)
    pd.set_option("display.width", 220)
    print(P.round(1).to_string(index=False))
    print(J.round(1).to_string(index=False))
    print(B.round(2).to_string(index=False))
    print(f"credit at delta = {DELTA}")


if __name__ == "__main__":
    main()
