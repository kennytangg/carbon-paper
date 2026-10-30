"""
Integrity-yield frontier: for each crediting rule, the realised over-crediting rate against the mean
share of the true stock credited, as the target delta varies. A rule on the frontier gives the most
credit for a given risk; a rule off it gives up credit, or takes risk, for nothing.

Rules: satellite only (conformal plain, conformal Mondrian + studentized, parametric two-component
bound) and satellite + 10 random field plots (ratio estimator: design lower bound, conformal
studentized). The VM0047 deduction has no delta, so it is one point per setting.

Usage: python -m estimation.crediting_frontier
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from estimation.conformal_crediting import RES, conformal_q, draw, estimates, make_projects

DELTAS = (0.05, 0.075, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50)
K, REPS = 10, 150


def main() -> None:
    ev = pd.read_parquet(RES / "evaluation_table.parquet").dropna(subset=["E2_loro_lgbm"])
    ev = ev[ev["agb_Mg_ha"] > 1]
    P = make_projects(ev).merge(pd.read_parquet(RES / "intervals.parquet")[["plot_id", "cqr_lo", "cqr_hi"]], on="plot_id", how="left")
    P["w"] = (np.log(P["cqr_hi"]) - np.log(P["cqr_lo"])) / 2
    P["lr"] = np.log(P["agb_Mg_ha"] / P["E2_loro_lgbm"])
    g = P.groupby("project")
    meta = pd.DataFrame({"region": g["region"].first(), "n": g.size(), "Y": g["agb_Mg_ha"].mean(), "S": g["E2_loro_lgbm"].mean(),
                         "w": g["w"].mean(), "small": g["radius_m"].median() <= 15})
    meta["z"] = np.log(meta["S"] / meta["Y"])
    meta["zs"] = meta["z"] / meta["w"]
    rows = []
    for delta in DELTAS:
        out = {"satellite: conformal plain": [], "satellite: conformal Mondrian + studentized": [], "satellite: parametric two-component bound": []}
        for p, r in meta.iterrows():
            cal = meta[meta["region"] != r["region"]]
            calg = cal[cal["small"] == r["small"]]
            q1, q2 = conformal_q(cal["z"], delta), conformal_q(calg["zs"], delta)
            other = P[P["region"] != r["region"]]
            rm = other.groupby("region")["lr"].mean()
            se = np.sqrt((other["lr"] - other["region"].map(rm)).var() / r["n"] + rm[other.groupby("region").size() >= 3].var())
            out["satellite: conformal plain"].append(r["S"] * np.exp(-q1) if np.isfinite(q1) else 0.0)
            out["satellite: conformal Mondrian + studentized"].append(r["S"] * np.exp(-q2 * r["w"]) if np.isfinite(q2) else 0.0)
            out["satellite: parametric two-component bound"].append(r["S"] * np.exp(-stats.norm.ppf(1 - delta) * se))
        for rule, c in out.items():
            c = np.array(c)
            rows.append({"rule": rule, "delta": delta, "over": float(np.mean(c > meta["Y"].to_numpy())), "yield": float(np.mean(c / meta["Y"].to_numpy()))})
    # VM0047 on the satellite-only two-component U (one point)
    c = []
    for p, r in meta.iterrows():
        other = P[P["region"] != r["region"]]
        rm = other.groupby("region")["lr"].mean()
        se = np.sqrt((other["lr"] - other["region"].map(rm)).var() / r["n"] + rm[other.groupby("region").size() >= 3].var())
        c.append(r["S"] * (1 - min(1.0, max(0.0, 1.645 * se - 0.10))))
    c = np.array(c)
    rows.append({"rule": "satellite: VM0047 deduction", "delta": np.nan, "over": float(np.mean(c > meta["Y"].to_numpy())), "yield": float(np.mean(c / meta["Y"].to_numpy()))})

    # satellite + K field plots
    rng = np.random.default_rng(1)
    data = {p: (gg["agb_Mg_ha"].to_numpy(), gg["E2_loro_lgbm"].to_numpy()) for p, gg in g if len(gg) >= K + 3}
    D = {p: np.array([[e[0][0], e[0][1]] for e in (estimates(y, x, draw(y, x, K, "srs", rng), K) for _ in range(REPS))]) for p, (y, x) in data.items()}
    ps = list(D)
    t95 = stats.t.ppf(0.95, K - 1)
    vm_over, vm_yield = [], []
    for p in ps:
        T, r = D[p][:, 0], D[p][:, 1]
        cvm = T * (1 - np.clip(t95 * r - 0.10, 0, 1))
        vm_over.append(np.mean(cvm > meta.loc[p, "Y"])); vm_yield.append(np.mean(cvm / meta.loc[p, "Y"]))
    rows.append({"rule": f"satellite + {K} plots: VM0047 deduction", "delta": np.nan, "over": float(np.mean(vm_over)), "yield": float(np.mean(vm_yield))})
    for delta in DELTAS:
        lb_o, lb_y, cs_o, cs_y = [], [], [], []
        tq = stats.t.ppf(1 - delta, K - 1)
        for p in ps:
            Y = meta.loc[p, "Y"]
            cal = [c for c in ps if meta.loc[c, "region"] != meta.loc[p, "region"]]
            T, r = D[p][:, 0], D[p][:, 1]
            clb = T * (1 - tq * r)
            lb_o.append(np.mean(clb > Y)); lb_y.append(np.mean(np.clip(clb, 0, None) / Y))
            cs = np.zeros(REPS)
            for rep in range(REPS):
                j = rng.integers(0, REPS, len(cal))
                zs = [np.log(D[c][jj, 0] / meta.loc[c, "Y"]) / max(D[c][jj, 1], 1e-6) for c, jj in zip(cal, j)]
                q = conformal_q(zs, delta)
                cs[rep] = T[rep] * np.exp(-q * r[rep]) if np.isfinite(q) else 0.0
            cs_o.append(np.mean(cs > Y)); cs_y.append(np.mean(cs / Y))
        rows.append({"rule": f"satellite + {K} plots: design lower bound", "delta": delta, "over": float(np.mean(lb_o)), "yield": float(np.mean(lb_y))})
        rows.append({"rule": f"satellite + {K} plots: conformal studentized", "delta": delta, "over": float(np.mean(cs_o)), "yield": float(np.mean(cs_y))})
        print(f"delta {delta} done", flush=True)
    F = pd.DataFrame(rows)
    F.to_csv(RES / "crediting_frontier.csv", index=False)
    print(F.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
