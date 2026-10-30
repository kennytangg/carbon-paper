"""
Left-grid estimators (satellite only) and the experiments that score them.

Estimator ladder, from least to most information about the target region:
  E0  off-the-shelf satellite biomass products read at the plot (never fit to our plots)
  E1  ML trained only on spaceborne-lidar (GEDI) labels: no field data anywhere
  E2  ML trained on field plots from OTHER regions (leave-one-region-out): target region blind
  E3  E1/E2 plus k field plots from the target region for bias calibration (k-shot curve)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import lightgbm as lgb
import numpy as np
import pandas as pd

from src.evaluator import compute_mrv_metrics

FEATURE_PREFIXES = ("s2_", "ls_", "s1_", "palsar_", "dem_", "gedi_")
EXCLUDE = ("_n", "_n_clear", "_min_offset_days", "_year", "_year_gap")


def feature_columns(df: pd.DataFrame, prefixes: Sequence[str] = FEATURE_PREFIXES) -> List[str]:
    return [c for c in df.columns if c.startswith(tuple(prefixes)) and not c.endswith(EXCLUDE)
            and pd.api.types.is_numeric_dtype(df[c])]


def _lgbm(seed: int = 0) -> lgb.LGBMRegressor:
    return lgb.LGBMRegressor(n_estimators=400, learning_rate=0.03, num_leaves=15, min_child_samples=10,
                             subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
                             random_state=seed, verbose=-1)


def fit_log_model(X: pd.DataFrame, y: np.ndarray, seed: int = 0):
    """Fit on log(AGB) and return (model, Duan smearing factor) for unbiased back-transformation."""
    m = _lgbm(seed).fit(X, np.log(y))
    resid = np.log(y) - m.predict(X)
    return m, float(np.mean(np.exp(resid)))


def predict_log_model(model, smear: float, X: pd.DataFrame) -> np.ndarray:
    return np.exp(model.predict(X)) * smear


def leave_one_region_out(df: pd.DataFrame, target: str, region_col: str, feats: List[str], seed: int = 0,
                         alpha: float = 0.1) -> pd.DataFrame:
    """E2: for each region, train on all other regions and predict it blind.

    Also returns a split-conformal (1-alpha) interval per plot, calibrated on out-of-fold
    residuals from the training regions only.
    """
    out = []
    for reg in sorted(df[region_col].unique()):
        tr, te = df[df[region_col] != reg], df[df[region_col] == reg]
        if len(tr) < 30 or len(te) == 0:
            continue
        # Conformal calibration: inner leave-one-region-out within the training regions
        cal_res = []
        for inner in tr[region_col].unique():
            a, b = tr[tr[region_col] != inner], tr[tr[region_col] == inner]
            if len(a) < 30:
                continue
            m_i, s_i = fit_log_model(a[feats], a[target].to_numpy(), seed)
            cal_res.extend(np.abs(np.log(b[target].to_numpy()) - np.log(predict_log_model(m_i, s_i, b[feats]))))
        q = float(np.quantile(cal_res, min(1.0, (1 - alpha) * (1 + 1 / max(len(cal_res), 1))))) if cal_res else np.nan
        m, s = fit_log_model(tr[feats], tr[target].to_numpy(), seed)
        pred = predict_log_model(m, s, te[feats])
        out.append(te.assign(pred=pred, pi_lo=pred * np.exp(-q), pi_hi=pred * np.exp(q), fold_region=reg))
    return pd.concat(out) if out else pd.DataFrame()


def k_shot_curve(df: pd.DataFrame, target: str, pred_col: str, region_col: str,
                 ks: Sequence[int] = (0, 1, 2, 3, 5, 10, 20), n_draws: int = 200, seed: int = 0) -> pd.DataFrame:
    """E3: within each region, draw k plots, apply a ratio bias correction mean(y_k)/mean(pred_k),
    and score on the region's remaining plots. k=0 is the blind satellite-only estimate."""
    rng = np.random.default_rng(seed)
    rows = []
    for reg, g in df.groupby(region_col):
        y, p = g[target].to_numpy(), g[pred_col].to_numpy()
        for k in ks:
            if k >= len(g) - 2:
                continue
            for d in range(n_draws if k > 0 else 1):
                idx = rng.permutation(len(g))
                cal, ev = idx[:k], idx[k:]
                ratio = (y[cal].mean() / p[cal].mean()) if k > 0 else 1.0
                pe, ye = p[ev] * ratio, y[ev]
                rows.append({"region": reg, "k": k, "draw": d,
                             "rmse": float(np.sqrt(np.mean((pe - ye) ** 2))),
                             "rrmse_pct": float(100 * np.sqrt(np.mean((pe - ye) ** 2)) / ye.mean()),
                             "region_total_err_pct": float(100 * (pe.sum() - ye.sum()) / ye.sum())})
    return pd.DataFrame(rows)


def aggregation_curve(df: pd.DataFrame, target: str, pred_col: str, region_col: str,
                      sizes: Sequence[int] = (1, 2, 5, 10, 20, 50), n_draws: int = 300, seed: int = 0) -> pd.DataFrame:
    """Error of the mean of n plots (a proxy for estimating a larger area) as n grows.
    Random error shrinks roughly as 1/sqrt(n); what remains at large n is systematic bias."""
    rng = np.random.default_rng(seed)
    rows = []
    for reg, g in df.groupby(region_col):
        y, p = g[target].to_numpy(), g[pred_col].to_numpy()
        for n in sizes:
            if n > len(g):
                continue
            errs = []
            for _ in range(n_draws):
                i = rng.choice(len(g), n, replace=False)
                errs.append(100 * (p[i].mean() - y[i].mean()) / y[i].mean())
            errs = np.array(errs)
            rows.append({"region": reg, "n_plots": n, "mean_abs_err_pct": float(np.mean(np.abs(errs))),
                         "bias_pct": float(np.mean(errs)), "p90_abs_err_pct": float(np.quantile(np.abs(errs), 0.9))})
    return pd.DataFrame(rows)


def score(df: pd.DataFrame, target: str, pred_col: str, name: str, unit: str, subset: str,
          lo: Optional[str] = None, hi: Optional[str] = None) -> Dict:
    m = compute_mrv_metrics(df[target], df[pred_col], model_name=name, target_unit=unit, subset_name=subset)
    if lo and hi and lo in df and hi in df:
        ok = df[[target, lo, hi]].dropna()
        m["pi90_coverage"] = round(float(((ok[target] >= ok[lo]) & (ok[target] <= ok[hi])).mean()), 3)
    return m
