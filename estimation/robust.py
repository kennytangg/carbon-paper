"""
Cloud robustness and honest confidence for the blind stock estimate (experiments C2, U1, U3).

C2  Clouds remove the optical block (Sentinel-2, Landsat) for some plots. We remove it at random
    for a fraction q of the target-region plots and compare four ways to cope:
      naive      the full model; LightGBM routes the missing values down its default branches
      dropout    one model trained on the real rows plus copies with the optical block removed
                 (modality dropout), so it has learned what to do without optical data
      switch     a cloud-aware ensemble: the full model when optical data exist, else a model
                 trained without optical inputs (radar + terrain + annual product)
      impute     optical features regressed from the radar + terrain block, then the full model
U1  Interval methods, all calibrated on inner leave-one-region-out residuals of the training
    regions only, target 90%:
      split      |ln y - ln yhat|, one quantile (the method used in evaluate.py)
      mondrian   split, but a separate quantile per optical-availability group
      normalized |ln y - ln yhat| / sigma(x), sigma(x) a second LightGBM fitted to inner residuals
      cqr        conformalized quantile regression on ln y (LightGBM quantile 5% / 95%)
U3  Does a metadata "confidence score" of the kind used by monitoring platforms (cloud,
    completeness, temporal offset) predict the actual error? Spearman rho vs |ln error|,
    compared with the normalized-conformal sigma(x).

Everything is leave-one-region-out. Run after the reveal: exploratory, every variant reported.

Usage: python -m estimation.robust --window 90
"""

from __future__ import annotations

import argparse
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from estimation.models import _lgbm, feature_columns

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
OUTD = EST / "results"
ALPHA = 0.1
OPT, RAD, TER, PROD = ("s2_", "ls_"), ("s1_", "palsar_"), ("dem_",), ("chloris_agb",)


def blocks(df):
    f = feature_columns(df, OPT + RAD + TER + PROD)
    opt = [c for c in f if c.startswith(OPT)]
    return f, opt, [c for c in f if c not in opt]


def fit(X, y, seed=0, **kw):
    m = _lgbm(seed).set_params(**kw).fit(X, y)
    return m


def conformal_q(scores, alpha=ALPHA):
    s = np.sort(np.asarray(scores))
    k = int(np.ceil((len(s) + 1) * (1 - alpha))) - 1
    return float(s[min(k, len(s) - 1)])


def hide(X, cols, mask):
    X = X.copy()
    X.loc[mask, cols] = np.nan
    return X


def strategies(tr, te_X, feats, opt, rest, rng):
    """Return predictions in ln space of every cloud strategy for the rows of te_X."""
    y = np.log(tr["agb_Mg_ha"].to_numpy())
    full = fit(tr[feats], y)
    aug = pd.concat([tr[feats], hide(tr[feats], opt, np.ones(len(tr), bool))])
    drop = fit(aug, np.r_[y, y], seed=1)
    noopt = fit(tr[rest], y, seed=2)
    miss = te_X[opt].isna().all(axis=1).to_numpy()
    imp_X = te_X.copy()
    if miss.any():
        for c in opt:
            ok = tr[c].notna()
            if ok.sum() > 30:
                r = fit(tr.loc[ok, rest], tr.loc[ok, c], n_estimators=200)
                imp_X.loc[miss, c] = r.predict(te_X.loc[miss, rest])
    return {"naive": full.predict(te_X[feats]), "dropout": drop.predict(te_X[feats]),
            "switch": np.where(miss, noopt.predict(te_X[rest]), full.predict(te_X[feats])),
            "impute": full.predict(imp_X[feats])}


def cloud_experiment(df, feats, opt, rest, qs=(0.0, 0.25, 0.5, 0.75, 1.0), seed=0):
    rows = []
    for q in qs:
        rng = np.random.default_rng(seed)
        preds = []
        for reg in sorted(df["region"].unique()):
            tr, te = df[df["region"] != reg], df[df["region"] == reg]
            mask = rng.random(len(te)) < q
            te_X = hide(te[feats], opt, mask)
            # plots that really had no clear optical scene stay cloud-hit at every q
            p = strategies(tr, te_X, feats, opt, rest, rng)
            preds.append(te[["plot_id", "dataset", "agb_Mg_ha"]].assign(cloud_hit=te_X[opt].isna().all(axis=1).to_numpy(),
                                                                        **{k: np.exp(v) for k, v in p.items()}))
        P = pd.concat(preds)
        for s in ("naive", "dropout", "switch", "impute"):
            for sub, g in [("all", P), ("cloud-hit plots", P[P["cloud_hit"]]), ("clear plots", P[~P["cloud_hit"]])]:
                if len(g) == 0:
                    continue
                e = g[s] - g["agb_Mg_ha"]
                rows.append({"q": q, "strategy": s, "subset": sub, "n": len(g),
                             "rrmse_pct": 100 * np.sqrt(np.mean(e ** 2)) / g["agb_Mg_ha"].mean(),
                             "bias_pct": 100 * e.mean() / g["agb_Mg_ha"].mean()})
        print(f"q={q} done", flush=True)
    return pd.DataFrame(rows)


def interval_experiment(df, feats, opt, rest):
    """Outer LORO; inner LORO out-of-fold residuals on the training regions calibrate every method."""
    out = []
    for reg in sorted(df["region"].unique()):
        tr, te = df[df["region"] != reg].reset_index(drop=True), df[df["region"] == reg]
        y = np.log(tr["agb_Mg_ha"].to_numpy())
        oof, oof_lo, oof_hi = np.full(len(tr), np.nan), np.full(len(tr), np.nan), np.full(len(tr), np.nan)
        for inner in tr["region"].unique():
            a, b = (tr["region"] != inner).to_numpy(), (tr["region"] == inner).to_numpy()
            oof[b] = fit(tr.loc[a, feats], y[a]).predict(tr.loc[b, feats])
            oof_lo[b] = fit(tr.loc[a, feats], y[a], objective="quantile", alpha=ALPHA / 2).predict(tr.loc[b, feats])
            oof_hi[b] = fit(tr.loc[a, feats], y[a], objective="quantile", alpha=1 - ALPHA / 2).predict(tr.loc[b, feats])
        r = np.abs(y - oof)
        tr_opt = tr[opt].notna().any(axis=1).to_numpy()
        te_opt = te[opt].notna().any(axis=1).to_numpy()
        # difficulty model: predicts |residual| from the inputs plus the plot footprint (public manifest)
        sig_X = tr[feats].assign(radius_m=tr["radius_m"], has_opt=tr_opt.astype(float))
        sig = fit(sig_X, np.log(r + 1e-3), n_estimators=200, num_leaves=7, min_child_samples=20)
        sig_tr = np.exp(sig.predict(sig_X))
        sig_te = np.exp(sig.predict(te[feats].assign(radius_m=te["radius_m"], has_opt=te_opt.astype(float))))

        m = fit(tr[feats], y)
        p = m.predict(te[feats])
        qlo = fit(tr[feats], y, objective="quantile", alpha=ALPHA / 2).predict(te[feats])
        qhi = fit(tr[feats], y, objective="quantile", alpha=1 - ALPHA / 2).predict(te[feats])

        q_split = conformal_q(r)
        q_mon = {g: conformal_q(r[tr_opt == g]) if (tr_opt == g).sum() > 10 else q_split for g in (True, False)}
        q_norm = conformal_q(r / sig_tr)
        q_cqr = conformal_q(np.maximum(oof_lo - y, y - oof_hi))
        qm = np.array([q_mon[g] for g in te_opt])
        out.append(te[["plot_id", "dataset", "region", "agb_Mg_ha"]].assign(
            has_opt=te_opt, pred=np.exp(p), sigma=sig_te,
            split_lo=np.exp(p - q_split), split_hi=np.exp(p + q_split),
            mondrian_lo=np.exp(p - qm), mondrian_hi=np.exp(p + qm),
            normalized_lo=np.exp(p - q_norm * sig_te), normalized_hi=np.exp(p + q_norm * sig_te),
            cqr_lo=np.exp(qlo - q_cqr), cqr_hi=np.exp(qhi + q_cqr)))
        print(f"intervals: {reg}", flush=True)
    return pd.concat(out)


def cloud_aware_cqr(df, feats, opt):
    """U4: are the intervals still honest when clouds remove the optical block?

    plain  CQR fitted and calibrated on the plots as observed; at test time optical is removed
    aware  quantile models trained with modality dropout, and two conformal groups: the inner
           out-of-fold plots as observed, and the SAME plots with the optical block hidden
           (synthetic cloud), so the cloud-hit group has as many calibration scores as the clear one
    Both are scored on every target-region plot twice: as observed, and fully clouded."""
    out = []
    for reg in sorted(df["region"].unique()):
        tr, te = df[df["region"] != reg].reset_index(drop=True), df[df["region"] == reg]
        y = np.log(tr["agb_Mg_ha"].to_numpy())
        all_hidden = np.ones(len(tr), bool)
        sc_plain, sc_clear, sc_cloud = [], [], []
        for inner in tr["region"].unique():
            a, b = (tr["region"] != inner).to_numpy(), (tr["region"] == inner).to_numpy()
            Xa, Xb, ya, yb = tr.loc[a, feats], tr.loc[b, feats], y[a], y[b]
            lo = fit(Xa, ya, objective="quantile", alpha=ALPHA / 2)
            hi = fit(Xa, ya, objective="quantile", alpha=1 - ALPHA / 2)
            sc_plain.extend(np.maximum(lo.predict(Xb) - yb, yb - hi.predict(Xb)))
            Xa2 = pd.concat([Xa, hide(Xa, opt, np.ones(len(Xa), bool))])
            lo2 = fit(Xa2, np.r_[ya, ya], objective="quantile", alpha=ALPHA / 2)
            hi2 = fit(Xa2, np.r_[ya, ya], objective="quantile", alpha=1 - ALPHA / 2)
            Xbh = hide(Xb, opt, np.ones(len(Xb), bool))
            sc_clear.extend(np.maximum(lo2.predict(Xb) - yb, yb - hi2.predict(Xb)))
            sc_cloud.extend(np.maximum(lo2.predict(Xbh) - yb, yb - hi2.predict(Xbh)))
        q_plain, q_clear, q_cloud = conformal_q(sc_plain), conformal_q(sc_clear), conformal_q(sc_cloud)
        lo = fit(tr[feats], y, objective="quantile", alpha=ALPHA / 2)
        hi = fit(tr[feats], y, objective="quantile", alpha=1 - ALPHA / 2)
        X2 = pd.concat([tr[feats], hide(tr[feats], opt, all_hidden)])
        lo2 = fit(X2, np.r_[y, y], objective="quantile", alpha=ALPHA / 2)
        hi2 = fit(X2, np.r_[y, y], objective="quantile", alpha=1 - ALPHA / 2)
        for cond, Xt in [("as observed", te[feats]), ("fully clouded", hide(te[feats], opt, np.ones(len(te), bool)))]:
            miss = Xt[opt].isna().all(axis=1).to_numpy()
            qa = np.where(miss, q_cloud, q_clear)
            out.append(te[["plot_id", "dataset", "agb_Mg_ha"]].assign(
                condition=cond,
                plain_lo=np.exp(lo.predict(Xt) - q_plain), plain_hi=np.exp(hi.predict(Xt) + q_plain),
                aware_lo=np.exp(lo2.predict(Xt) - qa), aware_hi=np.exp(hi2.predict(Xt) + qa)))
        print(f"cloud-aware CQR: {reg}", flush=True)
    O = pd.concat(out)
    O.to_parquet(OUTD / "cloud_aware_cqr_plots.parquet", index=False)
    rows = []
    for (cond, ds), g in list(O.groupby(["condition", "dataset"])) + [((c, "all"), g) for c, g in O.groupby("condition")]:
        for m in ("plain", "aware"):
            ins = (g["agb_Mg_ha"] >= g[f"{m}_lo"]) & (g["agb_Mg_ha"] <= g[f"{m}_hi"])
            rows.append({"condition": cond, "subset": ds, "method": m, "n": len(g), "coverage": float(ins.mean()),
                         "median_ratio_hi_lo": float(np.median(g[f"{m}_hi"] / g[f"{m}_lo"]))})
    return pd.DataFrame(rows)


def interval_scores(I):
    rows = []
    for meth in ("split", "mondrian", "normalized", "cqr"):
        lo, hi = I[f"{meth}_lo"], I[f"{meth}_hi"]
        y = I["agb_Mg_ha"]
        inside = (y >= lo) & (y <= hi)
        # Winkler interval score on ln scale: width + (2/alpha) * distance outside
        ly, llo, lhi = np.log(y), np.log(lo), np.log(hi)
        wink = (lhi - llo) + (2 / ALPHA) * (np.maximum(llo - ly, 0) + np.maximum(ly - lhi, 0))
        for sub, msk in [("all", np.ones(len(I), bool))] + [(d, (I["dataset"] == d).to_numpy()) for d in sorted(I["dataset"].unique())] + \
                        [("optical present", I["has_opt"].to_numpy()), ("optical missing", ~I["has_opt"].to_numpy())]:
            if msk.sum() == 0:
                continue
            rows.append({"method": meth, "subset": sub, "n": int(msk.sum()), "coverage": float(inside[msk].mean()),
                         "median_ratio_hi_lo": float(np.median((hi / lo)[msk])), "winkler_ln": float(wink[msk].mean())})
    return pd.DataFrame(rows)


def heuristic_confidence(df):
    """A metadata confidence score in the style of platform 'confidence scorers' (0-100):
    40 pts optical clear-scene availability, 30 pts data completeness, 30 pts temporal closeness."""
    s2 = df.get("s2_n_clear", pd.Series(0, index=df.index)).fillna(0)
    ls = df.get("ls_n_clear", pd.Series(0, index=df.index)).fillna(0)
    clear = np.clip((s2 + ls) / 6, 0, 1) * 40
    groups = [OPT, ("s1_",), ("palsar_",), TER]
    comp = sum(df[[c for c in df.columns if c.startswith(g)]].notna().any(axis=1).astype(float) for g in groups) / len(groups) * 30
    off = df[[c for c in ("s2_min_offset_days", "ls_min_offset_days", "s1_min_offset_days") if c in df]].min(axis=1).fillna(365)
    temporal = np.clip(1 - off / 365, 0, 1) * 30
    return clear + comp + temporal


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=90)
    ap.add_argument("--skip-cloud", action="store_true")
    ap.add_argument("--only-u4", action="store_true")
    args = ap.parse_args()
    feat = pd.read_parquet(EST / "plot_manifest.parquet").merge(
        pd.read_parquet(EST / f"left_features_win{args.window}.parquet"), on=["plot_id", "date"], how="left")
    gt = pd.read_parquet(EST / "right_grid_sealed.parquet")[["plot_id", "agb_Mg_ha"]]
    df = feat.merge(gt, on="plot_id")
    df = df[df["agb_Mg_ha"] > 1].reset_index(drop=True)
    feats, opt, rest = blocks(df)
    print(f"{len(feats)} features: {len(opt)} optical, {len(rest)} radar/terrain/product; "
          f"plots with no optical at all: {df[opt].isna().all(axis=1).sum()}")

    if args.only_u4:
        A = cloud_aware_cqr(df, feats, opt)
        A.to_csv(OUTD / "cloud_aware_cqr.csv", index=False)
        print(A.round(3).to_string(index=False))
        return

    if not args.skip_cloud:
        C = cloud_experiment(df, feats, opt, rest)
        C.to_csv(OUTD / "cloud_robustness.csv", index=False)
        print(C[C["subset"] != "clear plots"].round(1).to_string(index=False))

    I = interval_experiment(df, feats, opt, rest)
    I.to_parquet(OUTD / "intervals.parquet", index=False)
    S = interval_scores(I)
    S.to_csv(OUTD / "interval_methods.csv", index=False)
    print(S.round(3).to_string(index=False))

    err = np.abs(np.log(I["pred"]) - np.log(I["agb_Mg_ha"]))
    H = heuristic_confidence(df.set_index("plot_id").loc[I["plot_id"]].reset_index())
    rows = [{"score": "metadata confidence (higher = more confident)", "spearman_vs_abs_ln_error": spearmanr(H, err).statistic},
            {"score": "normalized-conformal sigma(x) (higher = less confident)", "spearman_vs_abs_ln_error": spearmanr(I["sigma"], err).statistic}]
    for d in sorted(I["dataset"].unique()):
        m = (I["dataset"] == d).to_numpy()
        rows.append({"score": f"metadata confidence [{d}]", "spearman_vs_abs_ln_error": spearmanr(H[m], err[m]).statistic})
        rows.append({"score": f"sigma(x) [{d}]", "spearman_vs_abs_ln_error": spearmanr(I["sigma"][m], err[m]).statistic})
    U = pd.DataFrame(rows)
    U.to_csv(OUTD / "confidence_score_check.csv", index=False)
    print(U.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
