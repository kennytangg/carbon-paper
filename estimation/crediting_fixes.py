"""
Two fixes for the limits the simulations exposed, on the same 1,000 simulated projects.

1. Over-crediting above target. The project credit map * exp(-q) went above the field amount in
   12% of projects at delta = 0.1. Errors are shared within a region, so the exchangeable unit is
   the region, not the project. Region-level conformal takes one score per calibration region
   (the log ratio of map to field over all its plots) and the finite-sample (1 - delta) quantile of
   those scores. It is compared with the project-level q of simulations.py.
2. Regional bias (Indonesia). A few local field plots outside the project, drawn from the same
   region, give a ratio correction sum(field) / sum(map) (the E3 ratio estimator). k = 0, 3, 5, 10.
   Small plots are noisy, so the plain ratio can do more harm than the bias it removes. The shrunk
   version weighs the local log ratio z_k against the map's regional bias seen on other regions,
   z ~ N(mu, tau^2): z* = (mu / tau^2 + z_k / v) / (1 / tau^2 + 1 / v), with v = s^2 / k and s^2
   the per-plot variance of the log ratio within a region, pooled over other regions measured
   with the same plot protocol (a project knows its own plot size). k = 0 gives the map times
   exp(-mu), a bias correction learnt on other regions only. The _realm variants take mu and
   tau^2 from the other regions of the same biogeographic realm.

Every map is a leave-one-region-out prediction, so the project's region never trains the map.
Exploratory: run after the reveal.

Usage: python -m estimation.crediting_fixes [--map "column in accuracy_embeddings_preds"]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from estimation.conformal_crediting import conformal_q
from estimation.simulations import DELTA, N_PLOTS, conformal_q_by_region, draw_projects
from estimation.tree_count import realm

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "data" / "estimation" / "results"
KS = (0, 3, 5, 10)


def region_z(d: pd.DataFrame, col: str) -> pd.Series:
    """Log ratio map / field of each region's plot total; a region is a calibration unit only with
    at least N_PLOTS plots (smaller ones are single-plot noise, not a regional bias)."""
    n = d.groupby("region").size()
    g = d[d["region"].isin(n[n >= N_PLOTS].index)].groupby("region")
    return np.log(g[col].sum() / g["agb_Mg_ha"].sum())


def region_q(d: pd.DataFrame, col: str) -> dict:
    z = region_z(d, col)
    return {reg: conformal_q(z.drop(reg), DELTA) for reg in z.index}


def region_q_corrected(d: pd.DataFrame, col: str) -> dict:
    """Region-level q for the realm-corrected map. Each calibration region j is corrected by the mean
    log ratio of its realm without j and without the target region, as the target itself is."""
    z = region_z(d, col)
    rl = d.groupby("region")["realm"].first().reindex(z.index)

    def mu(j, excl):
        pool = (z.index != j) & ~z.index.isin(excl)
        near = pool & (rl == rl[j]).to_numpy()
        return z[near if near.sum() >= 3 else pool].mean()
    return {reg: conformal_q(pd.Series([z[j] - mu(j, [reg]) for j in z.index if j != reg]), DELTA) for reg in z.index}


def shrink_priors(d: pd.DataFrame, col: str, by_realm: bool) -> dict:
    """Per held-out region: (mu, tau^2) of the regional log ratio and the pooled per-plot variance s^2.

    by_realm: mu and tau^2 come from the other regions of the same biogeographic realm (a project in
    Riau borrows the bias seen in other Indonesian provinces), if there are at least three."""
    z = region_z(d, col)
    lr = np.log(d[col] / d["agb_Mg_ha"])
    s2 = lr.groupby(d["region"]).var()
    ds = d.groupby("region")["dataset"].first().reindex(z.index)
    rl = d.groupby("region")["realm"].first().reindex(z.index)
    out = {}
    for reg in z.index:
        other = z.index != reg
        near = other & (rl == rl[reg]).to_numpy()
        pool = near if (by_realm and near.sum() >= 3) else other
        same = other & (ds == ds[reg]).to_numpy()
        out[reg] = (z[pool].mean(), z[pool].var(), s2[z.index[same if same.any() else other]].mean())
    return out


def run(d: pd.DataFrame, col: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    q_proj = conformal_q_by_region(d.drop(columns=["lat", "lon"]).assign(map_agb_Mg_ha=d[col]))
    q_reg = region_q(d, col)
    q_cor = region_q_corrected(d, col)
    priors = {"": shrink_priors(d, col, by_realm=False), "_realm": shrink_priors(d, col, by_realm=True)}
    rows = []
    for s, reg, g in draw_projects(d):
        field, sat = g["agb_Mg_ha"].mean(), g[col].mean()
        row = {"sim": s, "dataset": g["dataset"].iloc[0], "region": reg, "map_pct": 100 * sat / field}
        for tag, q in [("credit_project_q", q_proj[reg]), ("credit_region_q", q_reg[reg])]:
            row[tag] = 100 * sat * np.exp(-q) / field if np.isfinite(q) else 0.0
        for t, pr in priors.items():
            row[f"map_mu{t}_pct"] = 100 * sat * np.exp(-pr[reg][0]) / field
        row["credit_mu_realm_region_q"] = row["map_mu_realm_pct"] * np.exp(-q_cor[reg])
        rest = d[(d["region"] == reg) & ~d["plot_id"].isin(g["plot_id"])]
        rng = np.random.default_rng(10_000 + s)
        for k in KS[1:]:
            if len(rest) >= k:
                c = rest.iloc[rng.choice(len(rest), k, replace=False)]
                zk = np.log(c[col].sum() / c["agb_Mg_ha"].sum())
                row[f"local{k}_pct"] = 100 * sat * np.exp(-zk) / field
                for t, pr in priors.items():
                    mu, tau2, s2 = pr[reg]
                    zs = (mu / tau2 + zk * k / s2) / (1 / tau2 + k / s2)
                    row[f"local{k}_shrunk{t}_pct"] = 100 * sat * np.exp(-zs) / field
        rows.append(row)
    S = pd.DataFrame(rows)
    out = []
    cols = (["map_pct", "map_mu_pct", "map_mu_realm_pct", "credit_project_q", "credit_region_q", "credit_mu_realm_region_q"]
            + [f"local{k}{t}_pct" for k in KS[1:] for t in ("", "_shrunk", "_shrunk_realm")])
    for subset, x in [("All", S)] + list(S.groupby("dataset")):
        for c in cols:
            v = x[c].dropna()
            out.append({"subset": subset, "estimate": c, "projects": len(v), "median_pct": v.median(),
                        "p5_pct": v.quantile(.05), "p95_pct": v.quantile(.95), "within_25pct": 100 * ((v - 100).abs() <= 25).mean(),
                        "above_field_pct": 100 * (v > 100).mean()})
    return S, pd.DataFrame(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", nargs="+", default=["best map", "embeddings + CH + GEDI"])
    a = ap.parse_args()
    d = pd.read_parquet(RES / "accuracy_embeddings_preds.parquet")
    m = pd.read_parquet(ROOT / "data" / "estimation" / "plot_manifest.parquet")[["plot_id", "lat", "lon"]]
    d = d.merge(m, on="plot_id", how="left")
    d["realm"] = [realm(lon, lat) for lon, lat in zip(d["lon"], d["lat"])]
    U, R = [], []
    for col in a.map:
        S, u = run(d, col)
        U.append(u.assign(map=col))
        R.append(S.groupby("region").agg(projects=("sim", "size"), over_project_q=("credit_project_q", lambda x: 100 * (x > 100).mean()),
                                         over_region_q=("credit_region_q", lambda x: 100 * (x > 100).mean())).assign(map=col))
    U, R = pd.concat(U, ignore_index=True), pd.concat(R)
    U.to_csv(RES / "crediting_fixes.csv", index=False)
    R.to_csv(RES / "crediting_fixes_by_region.csv")
    pd.set_option("display.width", 220)
    print(U.round(1).to_string(index=False))
    print(R.round(1).to_string())


if __name__ == "__main__":
    main()
