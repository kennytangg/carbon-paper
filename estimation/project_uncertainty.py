"""
Project-level confidence (experiment U2): the scale at which credits are issued.

Each region block with at least N_MIN plots plays the role of a project; its true stock is the mean
field AGB of its plots. Satellite predictions are the committed E2 leave-one-region-out predictions.

P0  satellite only, naive CI: plot errors treated as independent, half-width z * s_w / sqrt(n)
P1  satellite only, two-component CI: Var = s_w^2 / n + s_b^2, where s_b^2 is the between-region
    variance of the region-mean ln residual. s_w and s_b come from the OTHER regions only.
F   field only (traditional MRV with k plots): mean of k plots, CI from t_{k-1} s_y / sqrt(k)
R   satellite + k plots, ratio estimator (Cochran 1977, Ch. 6): R = sum y_k / sum yhat_k,
    T = R * mean(yhat over all n plots), Var = (1 - k/n) s_e^2 / k with e = y - R yhat

For F and R we report coverage over random draws, the mean CI half-width (% of truth), the
relative efficiency Var_F / Var_R (how many field plots one satellite-assisted plot is worth), and
the plots needed for +/-10% at 90% confidence, n = (t CV / 0.10)^2 (AR-TOOL03 style).

Uncertainty deduction: the conservative estimate is T * (1 - D(U)), U = 90% CI half-width / T,
with D from the standard (see DEDUCTION). Over-crediting = conservative estimate > truth.

Usage: python -m estimation.project_uncertainty
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
OUTD = EST / "results"
N_MIN = 8
Z90 = stats.norm.ppf(0.95)


def deduction(u: np.ndarray) -> np.ndarray:
    """Uncertainty deduction as a fraction of the estimate. Placeholder rule, replaced once the
    exact standard text is verified: none up to 10% half-width, otherwise the excess over 10%."""
    return np.clip(u - 0.10, 0, None)


def satellite_only(ev: pd.DataFrame) -> pd.DataFrame:
    ev = ev.assign(lr=np.log(ev["agb_Mg_ha"]) - np.log(ev["E2_loro_lgbm"]))
    rows = []
    for reg, g in ev.groupby("region"):
        if len(g) < N_MIN:
            continue
        other = ev[ev["region"] != reg]
        reg_mean = other.groupby("region")["lr"].mean()
        s_w = float(np.sqrt((other["lr"] - other["region"].map(reg_mean)).var()))
        s_b = float(reg_mean[other.groupby("region").size() >= 3].std())
        n = len(g)
        est = float(g["E2_loro_lgbm"].mean())
        truth = float(g["agb_Mg_ha"].mean())
        for name, se in [("P0 naive independent", s_w / np.sqrt(n)), ("P1 two-component", np.sqrt(s_w ** 2 / n + s_b ** 2))]:
            lo, hi = est * np.exp(-Z90 * se), est * np.exp(Z90 * se)
            u = (hi - lo) / 2 / est
            cons = est * (1 - deduction(np.array([u]))[0])
            rows.append({"method": name, "region": reg, "dataset": g["dataset"].iloc[0], "n": n, "truth": truth, "est": est,
                         "covered": lo <= truth <= hi, "half_width_pct": 100 * u, "err_pct": 100 * (est - truth) / truth,
                         "conservative": cons, "overcredit": cons > truth})
    return pd.DataFrame(rows)


def with_field_plots(ev: pd.DataFrame, ks=(3, 5, 10, 20), draws=500, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for reg, g in ev.groupby("region"):
        y, x = g["agb_Mg_ha"].to_numpy(), g["E2_loro_lgbm"].to_numpy()
        n, truth = len(y), y.mean()
        for k in ks:
            if k > n - 2:
                continue
            t = stats.t.ppf(0.95, k - 1)
            fpc = 1 - k / n
            for d in range(draws):
                i = rng.choice(n, k, replace=False)
                ys, xs = y[i], x[i]
                f_est, f_se = ys.mean(), np.sqrt(fpc * ys.var(ddof=1) / k)
                R = ys.sum() / xs.sum()
                r_est = R * x.mean()
                e = ys - R * xs
                r_se = np.sqrt(fpc * e.var(ddof=1) / k)
                # regression (GREG) estimator: y_bar + b (X_bar - x_bar); residual variance on k - 2 df
                b = np.polyfit(xs, ys, 1)[0] if xs.std() > 0 else 0.0
                g_est = ys.mean() + b * (x.mean() - xs.mean())
                eg = ys - ys.mean() - b * (xs - xs.mean())
                g_se = np.sqrt(fpc * (eg ** 2).sum() / max(k - 2, 1) / k)
                for name, est, se in [("F field only", f_est, f_se), ("R satellite + k plots (ratio)", r_est, r_se),
                                      ("G satellite + k plots (regression)", g_est, g_se)]:
                    u = t * se / est if est > 0 else np.nan
                    cons = est * (1 - deduction(np.array([u]))[0])
                    rows.append({"method": name, "region": reg, "dataset": g["dataset"].iloc[0], "n": n, "k": k, "draw": d,
                                 "covered": abs(est - truth) <= t * se, "half_width_pct": 100 * u,
                                 "abs_err_pct": 100 * abs(est - truth) / truth, "var": se ** 2,
                                 "sq_err_pct": (100 * (est - truth) / truth) ** 2,
                                 "overcredit": cons > truth})
    return pd.DataFrame(rows)


def plots_needed(ev: pd.DataFrame) -> pd.DataFrame:
    """Plots needed for +/-10% at 90% with field only (CV of y) vs ratio estimation (CV of e),
    using every plot of the region as the pilot sample."""
    rows = []
    for reg, g in ev.groupby("region"):
        if len(g) < N_MIN:
            continue
        y, x = g["agb_Mg_ha"].to_numpy(), g["E2_loro_lgbm"].to_numpy()
        R = y.sum() / x.sum()
        cv_y, cv_e = y.std(ddof=1) / y.mean(), (y - R * x).std(ddof=1) / y.mean()
        need = lambda cv: int(np.ceil((Z90 * cv / 0.10) ** 2))  # iterate t later; z is the large-n limit
        rows.append({"region": reg, "dataset": g["dataset"].iloc[0], "n_plots": len(g), "cv_field_pct": 100 * cv_y,
                     "cv_ratio_resid_pct": 100 * cv_e, "n_needed_field": need(cv_y), "n_needed_ratio": need(cv_e),
                     "corr_y_yhat": float(np.corrcoef(y, x)[0, 1])})
    return pd.DataFrame(rows)


def main() -> None:
    ev = pd.read_parquet(OUTD / "evaluation_table.parquet").dropna(subset=["E2_loro_lgbm"])
    ev = ev[ev["agb_Mg_ha"] > 1]
    A = satellite_only(ev)
    A.to_csv(OUTD / "project_satellite_only.csv", index=False)
    print(A.groupby("method").agg(projects=("region", "size"), coverage=("covered", "mean"),
                                  median_half_width_pct=("half_width_pct", "median"), median_abs_err_pct=("err_pct", lambda s: s.abs().median()),
                                  overcredit_rate=("overcredit", "mean")).round(3).to_string())
    print(A.groupby(["method", "dataset"]).agg(coverage=("covered", "mean"), overcredit=("overcredit", "mean"), n=("region", "size")).round(2).to_string())

    B = with_field_plots(ev)
    B.to_parquet(OUTD / "project_with_field_plots.parquet", index=False)
    summ = B.groupby(["dataset", "k", "method"]).agg(coverage=("covered", "mean"), half_width_pct=("half_width_pct", "median"),
                                                    abs_err_pct=("abs_err_pct", "median"), overcredit=("overcredit", "mean"),
                                                    var=("var", "mean"), mse_pct=("sq_err_pct", "mean")).reset_index()
    # relative efficiency vs field only from the EMPIRICAL error over draws (>1: the satellite saves
    # field plots); the estimated variance is not used because GREG underestimates it at small k
    summ["rmse_pct"] = np.sqrt(summ["mse_pct"])
    eff = summ.pivot_table(index=["dataset", "k"], columns="method", values="mse_pct")
    summ["rel_efficiency"] = [eff.loc[(d, k), "F field only"] / v for d, k, v in zip(summ["dataset"], summ["k"], summ["mse_pct"])]
    summ.to_csv(OUTD / "project_with_field_plots.csv", index=False)
    print(summ.round(3).to_string(index=False))

    N = plots_needed(ev)
    N.to_csv(OUTD / "plots_needed.csv", index=False)
    print(N.round(2).to_string(index=False))
    print(N.groupby("dataset")[["cv_field_pct", "cv_ratio_resid_pct", "n_needed_field", "n_needed_ratio", "corr_y_yhat"]].median().round(1))


if __name__ == "__main__":
    main()
