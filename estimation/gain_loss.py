"""
Gain-loss hybrid for removals (SAFE, excluding oil palm), in the spirit of IPCC Eq. 2.4.

Satellites failed to measure growth by stock difference. Can they at least find LOSS? The hybrid:
  gain  the mean measured change of plots in OTHER blocks that the satellite does not flag
  loss  plots the satellite flags (Landsat dNBR or dNDVI between the census dates below a threshold
        chosen on other blocks) get the mean change of flagged plots in other blocks
Everything is leave-one-block-out. Compared with no change and the regional default rate.

Usage: python -m estimation.gain_loss
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
RES = EST / "results"


def auc(score, label):
    pos, neg = score[label], score[~label]
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    return float((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean())


def main() -> None:
    ev = pd.read_parquet(RES / "seq_evaluation_table.parquet")
    ev = ev[ev["land_use"] != "oil_palm"].reset_index(drop=True)
    lf = pd.read_parquet(EST / "left_features_win90_seq.parquet")
    t0 = ev[["plot_id", "date_t0"]].merge(lf, left_on=["plot_id", "date_t0"], right_on=["plot_id", "date"], how="left")
    t1 = ev[["plot_id", "date_t1"]].merge(lf, left_on=["plot_id", "date_t1"], right_on=["plot_id", "date"], how="left")
    ev["d_nbr"] = (t1["ls_nbr"] - t0["ls_nbr"]).to_numpy()
    ev["d_ndvi"] = (t1["ls_ndvi"] - t0["ls_ndvi"]).to_numpy()
    y = ev["dagb_Mg_ha_yr"].to_numpy()
    loss = y < -2.0  # a plot losing more than 2 Mg/ha/yr, about the mean growth in reverse
    print(f"plots {len(ev)}, loss plots {loss.sum()}, Landsat change available {ev['d_nbr'].notna().sum()}")
    for c in ("d_nbr", "d_ndvi"):
        ok = ev[c].notna().to_numpy()
        print(f"{c}: Spearman with dAGB {spearmanr(ev.loc[ok, c], y[ok]).statistic:+.3f}; "
              f"AUC for loss (lower = loss) {auc(-ev.loc[ok, c].to_numpy(), loss[ok]):.3f}")

    preds = {"no change": np.zeros(len(ev)), "regional default rate": np.full(len(ev), np.nan)}
    for c in ("d_nbr", "d_ndvi"):
        preds[f"gain-loss ({c})"] = np.full(len(ev), np.nan)
    for b in ev["block"].unique():
        te, tr = (ev["block"] == b).to_numpy(), (ev["block"] != b).to_numpy()
        preds["regional default rate"][te] = y[tr].mean()
        for c in ("d_nbr", "d_ndvi"):
            v = ev[c].to_numpy()
            ok_tr = tr & ~np.isnan(v)
            # threshold: the value that best separates loss plots in the other blocks (Youden J)
            cand = np.quantile(v[ok_tr], np.linspace(0.02, 0.5, 25))
            J = [((v[ok_tr] < th) & loss[ok_tr]).sum() / max(loss[ok_tr].sum(), 1)
                 - ((v[ok_tr] < th) & ~loss[ok_tr]).sum() / max((~loss[ok_tr]).sum(), 1) for th in cand]
            th = cand[int(np.argmax(J))]
            flag_tr = ok_tr & (v < th)
            gain = y[tr & ~(np.nan_to_num(v, nan=np.inf) < th)].mean()
            lossrate = y[flag_tr].mean() if flag_tr.any() else gain
            vt = v[te]
            preds[f"gain-loss ({c})"][te] = np.where(np.nan_to_num(vt, nan=np.inf) < th, lossrate, gain)

    rows = []
    for level in ("plot", "block mean"):
        for name, p in preds.items():
            if level == "plot":
                yy, pp = y, p
            else:
                df = pd.DataFrame({"b": ev["block"], "y": y, "p": p}).groupby("b").mean()
                yy, pp = df["y"].to_numpy(), df["p"].to_numpy()
            e = pp - yy
            rows.append({"level": level, "estimator": name, "rmse": np.sqrt(np.mean(e ** 2)), "mae": np.mean(np.abs(e)), "bias": e.mean()})
    R = pd.DataFrame(rows).round(3)
    R.to_csv(RES / "gain_loss.csv", index=False)
    print(R.to_string(index=False))


if __name__ == "__main__":
    main()
