"""
Is a crediting bound calibrated whatever the map it is applied to?

A crediting rule must protect integrity for any satellite product a developer brings, including
biased ones. For several satellite-only estimators, the realised over-crediting rate of three
bounds that all target delta (one-sided, multiplicative on the project mean):

  parametric, independent   S exp(-z s_w / sqrt(n))         plot errors assumed independent, mean zero
  parametric, two-component S exp(-z sqrt(s_w^2/n + s_b^2))  adds the between-region spread, mean zero
  conformal                 S exp(-q), q from ln(S/Y) of projects in other regions

s_w and s_b come from the estimator's own residuals in other regions. Estimators: E2, the Chloris
product, the E2-Chloris average, and E2 scaled by 1.1 and 1.2 (a product that over-predicts,
as a vendor map might in a new biome).

Usage: python -m estimation.crediting_robustness
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from estimation.conformal_crediting import RES, conformal_q, make_projects

DELTAS = (0.10, 0.20)


def main() -> None:
    ev = pd.read_parquet(RES / "evaluation_table.parquet").dropna(subset=["E2_loro_lgbm", "E0_chloris"])
    ev = ev[ev["agb_Mg_ha"] > 1]
    ev = ev.assign(ensemble=(ev["E2_loro_lgbm"] + ev["E0_chloris"]) / 2, e2_x110=ev["E2_loro_lgbm"] * 1.1, e2_x120=ev["E2_loro_lgbm"] * 1.2)
    P = make_projects(ev)
    estimators = {"E2 (blind LightGBM)": "E2_loro_lgbm", "Chloris product": "E0_chloris", "E2-Chloris average": "ensemble",
                  "E2 x 1.1 (over-predicting)": "e2_x110", "E2 x 1.2 (over-predicting)": "e2_x120"}
    rows = []
    for name, col in estimators.items():
        Q = P.assign(lr=np.log(P["agb_Mg_ha"] / P[col]))
        g = Q.groupby("project")
        m = pd.DataFrame({"region": g["region"].first(), "n": g.size(), "Y": g["agb_Mg_ha"].mean(), "S": g[col].mean()})
        m["z"] = np.log(m["S"] / m["Y"])
        for delta in DELTAS:
            zq = stats.norm.ppf(1 - delta)
            c = {"parametric, independent": [], "parametric, two-component": [], "conformal": []}
            for p, r in m.iterrows():
                o = Q[Q["region"] != r["region"]]
                rm = o.groupby("region")["lr"].mean()
                sw = np.sqrt((o["lr"] - o["region"].map(rm)).var())
                sb = rm[o.groupby("region").size() >= 3].std()
                c["parametric, independent"].append(r["S"] * np.exp(-zq * sw / np.sqrt(r["n"])))
                c["parametric, two-component"].append(r["S"] * np.exp(-zq * np.sqrt(sw ** 2 / r["n"] + sb ** 2)))
                q = conformal_q(m.loc[m["region"] != r["region"], "z"], delta)
                c["conformal"].append(r["S"] * np.exp(-q) if np.isfinite(q) else 0.0)
            for bound, v in c.items():
                v = np.array(v)
                x, n = int((v > m["Y"].to_numpy()).sum()), len(v)
                rows.append({"estimator": name, "delta": delta, "bound": bound, "realised_over": x / n,
                             "ci_lo": stats.beta.ppf(0.025, x, n - x + 1) if x > 0 else 0.0,
                             "ci_hi": stats.beta.ppf(0.975, x + 1, n - x) if x < n else 1.0,
                             "yield": float(np.mean(v / m["Y"].to_numpy())),
                             "mean_log_bias": float(m["z"].mean())})
    R = pd.DataFrame(rows)
    R.to_csv(RES / "crediting_robustness.csv", index=False)
    pd.set_option("display.width", 200)
    print(R.round(3).to_string(index=False))
    # worst-case calibration error over estimators, per bound
    print(R.assign(err=R["realised_over"] - R["delta"]).groupby(["delta", "bound"])["err"].agg(["max", "mean"]).round(3))


if __name__ == "__main__":
    main()
