"""
Conformal crediting: a crediting rule with a distribution-free bound on over-crediting.

A project is credited a LOWER BOUND of its stock. Registries derive that bound from a variance
formula and a deduction (VM0047: deduct U - 10%), which we showed does not bound over-crediting.
Here the bound is calibrated on other projects whose field truth is known:

  score     z_j = ln(T_j / Y_j) / r_j      (T: estimate, Y: true project mean, r: relative SE;
                                            r = 1 for satellite-only, "plain" scores)
  credit    C_j = T_j * exp(-q * r_j),      q = the ceil((m+1)(1-delta))-th smallest of m scores
  guarantee P(C_j > Y_j) <= delta           when projects are exchangeable (split conformal)

Projects: region blocks, with regions of 16+ plots split into spatial sub-projects of about 10
plots (k-means on coordinates). A target project is calibrated only on projects from OTHER regions,
so the guarantee is tested under transfer, not within a region.

With k field plots the estimate T is the ratio estimator with the satellite map as auxiliary data
(or the field-only mean), r its design-based relative SE, and draws are handled by the subsampling
scheme for two-layer data: per repetition, one random draw per calibration project.

Plot selection (which k plots to measure): simple random sampling (SRS), or a systematic sample
along the satellite prediction ("ranked", an implicit stratification on the map).

Compared rules: no deduction; VM0047 (credit T(1 - max(0, U - 0.10)), U = t SE / T); the one-sided
95% lower bound T - t SE; conformal plain; conformal studentized.
Metrics: over-crediting rate, mean yield (credit / true), share of projects credited zero.

Usage: python -m estimation.conformal_crediting
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "data" / "estimation" / "results"
DELTAS = (0.10, 0.20)
KS = (5, 10)
REPS = 200


def make_projects(ev: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = []
    for reg, g in ev.groupby("region"):
        if len(g) < 8:
            continue
        n_sub = max(1, len(g) // 10) if len(g) >= 16 else 1
        if n_sub == 1:
            out.append(g.assign(project=reg))
            continue
        xy = g[["lat", "lon"]].to_numpy()
        cent = xy[rng.choice(len(g), n_sub, replace=False)]
        for _ in range(50):  # plain k-means
            lab = np.argmin(((xy[:, None, :] - cent[None]) ** 2).sum(-1), 1)
            cent = np.array([xy[lab == c].mean(0) if (lab == c).any() else cent[c] for c in range(n_sub)])
        for c in range(n_sub):
            sub = g[lab == c]
            if len(sub) >= 8:
                out.append(sub.assign(project=f"{reg}#{c}"))
    return pd.concat(out)


def conformal_q(scores, delta):
    s = np.sort(np.asarray(scores))
    k = int(np.ceil((len(s) + 1) * (1 - delta)))
    return np.inf if k > len(s) else float(s[k - 1])


def draw(y, x, k, design, rng):
    n = len(y)
    if design == "srs":
        return rng.choice(n, k, replace=False)
    order = np.argsort(x)  # systematic along the satellite prediction, random start
    step = n / k
    start = rng.uniform(0, step)
    return order[np.floor(start + step * np.arange(k)).astype(int)]


def estimates(y, x, i, k):
    """Ratio estimator (satellite + k plots) and field-only mean with relative SEs."""
    n = len(y)
    fpc = 1 - k / n
    ys, xs = y[i], x[i]
    f_est = ys.mean()
    f_se = np.sqrt(fpc * ys.var(ddof=1) / k)
    R = ys.sum() / xs.sum()
    r_est = R * x.mean()
    r_se = np.sqrt(fpc * (ys - R * xs).var(ddof=1) / k)
    return (r_est, r_se / r_est), (f_est, f_se / f_est)


def main() -> None:
    ev = pd.read_parquet(RES / "evaluation_table.parquet").dropna(subset=["E2_loro_lgbm"])
    ev = ev[ev["agb_Mg_ha"] > 1]
    P = make_projects(ev)
    projs = P.groupby("project")
    meta = pd.DataFrame({"region": projs["region"].first(), "dataset": projs["dataset"].first(), "n": projs.size(),
                         "Y": projs["agb_Mg_ha"].mean(), "S": projs["E2_loro_lgbm"].mean()})
    print(f"{len(meta)} projects from {meta['region'].nunique()} regions; plots per project {meta['n'].min()}-{meta['n'].max()}")
    rng = np.random.default_rng(0)
    rows = []

    # ---- satellite only (no field plot in the project)
    # public covariates of a project: plot footprint class (manifest radius) and the model's own
    # out-of-region CQR interval width, a difficulty score computed without the project's truth
    iv = pd.read_parquet(RES / "intervals.parquet")[["plot_id", "cqr_lo", "cqr_hi"]]
    P2 = P.merge(iv, on="plot_id", how="left")  # radius_m (public manifest field) is already in P
    P2["w"] = (np.log(P2["cqr_hi"]) - np.log(P2["cqr_lo"])) / 2
    g2 = P2.groupby("project")
    meta["size_class"] = (g2["radius_m"].median() <= 15).map({True: "small plots", False: "large plots"})
    meta["w"] = g2["w"].mean()
    meta["z_sat"] = np.log(meta["S"] / meta["Y"])
    meta["z_stud"] = meta["z_sat"] / meta["w"]
    # two-component parametric SE (Eq. twocomp), from plot log residuals of other regions
    P2["lr"] = np.log(P2["agb_Mg_ha"] / P2["E2_loro_lgbm"])
    for delta in DELTAS:
        zq = stats.norm.ppf(1 - delta)
        for p, r in meta.iterrows():
            other = P2[P2["region"] != r["region"]]
            rm = other.groupby("region")["lr"].mean()
            s_w = float(np.sqrt((other["lr"] - other["region"].map(rm)).var()))
            s_b = float(rm[other.groupby("region").size() >= 3].std())
            se = np.sqrt(s_w ** 2 / r["n"] + s_b ** 2)
            cal = meta[meta["region"] != r["region"]]
            calg = cal[cal["size_class"] == r["size_class"]]
            q_plain, q_stud = conformal_q(cal["z_sat"], delta), conformal_q(cal["z_stud"], delta)
            q_mond, q_mond_s = conformal_q(calg["z_sat"], delta), conformal_q(calg["z_stud"], delta)
            u = 1.645 * se
            credits = {"no deduction": r["S"],
                       "VM0047 on two-component U": r["S"] * (1 - min(1.0, max(0.0, u - 0.10))),
                       "parametric lower bound (two-component)": r["S"] * np.exp(-zq * se),
                       "conformal plain": r["S"] * np.exp(-q_plain) if np.isfinite(q_plain) else 0.0,
                       "conformal studentized (CQR width)": r["S"] * np.exp(-q_stud * r["w"]) if np.isfinite(q_stud) else 0.0,
                       "conformal Mondrian by plot size": r["S"] * np.exp(-q_mond) if np.isfinite(q_mond) else 0.0,
                       "conformal Mondrian + studentized": r["S"] * np.exp(-q_mond_s * r["w"]) if np.isfinite(q_mond_s) else 0.0}
            for rule, c in credits.items():
                rows.append({"setting": "satellite only", "k": 0, "design": "-", "rule": rule, "delta": delta,
                             "project": p, "dataset": r["dataset"], "size_class": r["size_class"],
                             "n_cal": len(calg) if "Mondrian" in rule else len(cal),
                             "over": float(c > r["Y"]), "yield": c / r["Y"], "zero": float(c <= 0)})

    # ---- with k field plots: draws per project, subsampling conformal across projects
    data = {p: (g["agb_Mg_ha"].to_numpy(), g["E2_loro_lgbm"].to_numpy()) for p, g in projs}
    for k in KS:
        for design in ("srs", "ranked"):
            D = {}  # per project: arrays over reps of (est, rel_se) for ratio and field
            for p, (y, x) in data.items():
                if len(y) < k + 3:
                    continue
                est = [estimates(y, x, draw(y, x, k, design, rng), k) for _ in range(REPS)]
                D[p] = np.array([[e[0][0], e[0][1], e[1][0], e[1][1]] for e in est])
            ps = list(D)
            t = stats.t.ppf(0.95, k - 1)
            for p in ps:
                Y = meta.loc[p, "Y"]
                region = meta.loc[p, "region"]
                cal = [c for c in ps if meta.loc[c, "region"] != region]
                arr = D[p]
                for est_name, ci, si in (("ratio (satellite + k)", 0, 1), ("field only", 2, 3)):
                    T, r = arr[:, ci], arr[:, si]
                    unc = np.clip(t * r - 0.10, 0, 1)
                    c_vm = T * (1 - unc)
                    for delta in DELTAS:
                        c_lb = T * (1 - stats.t.ppf(1 - delta, k - 1) * r)  # one-sided bound at the same delta
                        over_vals = {"no deduction": (T, T > Y), "VM0047 (U-10%)": (c_vm, c_vm > Y),
                                     "design lower bound T - t SE": (c_lb, c_lb > Y)}
                        cp, cs = np.zeros(REPS), np.zeros(REPS)
                        for rep in range(REPS):
                            j = rng.integers(0, REPS, len(cal))  # one draw per calibration project
                            zp = [np.log(D[c][jj, ci] / meta.loc[c, "Y"]) for c, jj in zip(cal, j)]
                            zs = [np.log(D[c][jj, ci] / meta.loc[c, "Y"]) / max(D[c][jj, si], 1e-6) for c, jj in zip(cal, j)]
                            qp, qs = conformal_q(zp, delta), conformal_q(zs, delta)
                            cp[rep] = T[rep] * np.exp(-qp) if np.isfinite(qp) else 0.0
                            cs[rep] = T[rep] * np.exp(-qs * r[rep]) if np.isfinite(qs) else 0.0
                        vals = dict(over_vals)
                        vals["conformal plain"] = (cp, cp > Y)
                        vals["conformal studentized"] = (cs, cs > Y)
                        for rule, (c, o) in vals.items():
                            rows.append({"setting": est_name, "k": k, "design": design, "rule": rule, "delta": delta,
                                         "project": p, "dataset": meta.loc[p, "dataset"], "size_class": meta.loc[p, "size_class"], "over": float(np.mean(o)),
                                         "yield": float(np.mean(np.clip(c, 0, None) / Y)), "zero": float(np.mean(c <= 0))})
            print(f"k={k} {design} done", flush=True)

    A = pd.DataFrame(rows)
    A.to_csv(RES / "conformal_crediting_projects.csv", index=False)
    S = A.groupby(["setting", "k", "design", "rule", "delta"]).agg(
        projects=("project", "nunique"), over_rate=("over", "mean"), mean_yield=("yield", "mean"),
        zero_share=("zero", "mean")).reset_index()
    by = A.groupby(["setting", "k", "design", "rule", "delta", "size_class"])["over"].mean().unstack("size_class")
    S = S.merge(by.add_prefix("over_").reset_index(), on=["setting", "k", "design", "rule", "delta"], how="left")
    # exact (Clopper-Pearson) 95% interval for the satellite-only over-crediting rate: one decision per project
    sat = S["setting"] == "satellite only"
    lo, hi = [], []
    for _, r in S.iterrows():
        if r["setting"] == "satellite only":
            x, n = int(round(r["over_rate"] * r["projects"])), int(r["projects"])
            lo.append(stats.beta.ppf(0.025, x, n - x + 1) if x > 0 else 0.0)
            hi.append(stats.beta.ppf(0.975, x + 1, n - x) if x < n else 1.0)
        else:
            lo.append(np.nan); hi.append(np.nan)
    S["over_ci_lo"], S["over_ci_hi"] = lo, hi
    S.to_csv(RES / "conformal_crediting.csv", index=False)
    pd.set_option("display.width", 250)
    print(S[sat].round(3).to_string(index=False))
    print(S[~sat & (S["design"] == "srs")].drop(columns=["over_ci_lo", "over_ci_hi"]).round(3).to_string(index=False))
    print(S[~sat & (S["design"] == "ranked")][["setting", "k", "rule", "delta", "over_rate", "mean_yield"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
