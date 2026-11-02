"""
Published canopy-height equations, applied unchanged to the 1 m canopy height maps (CHMv1 and CHMv2).

None is fitted to our plots, so each is what an app could use with no training data. TCH is the mean
canopy height in the plot footprint, Cover20 the share of pixels above 20 m, GF19 the share below
19 m. Equations output aboveground carbon (Mg C/ha) unless noted; AGB = ACD / 0.47.

  app as coded       AGB = 3.836 TCH^1.131 (NusaCarbon lib/data-sources/canopy-height.ts; no such equation
                     is published, and it is then multiplied by 0.47 like a biomass)
  app read as carbon the same curve read as carbon (AGB = curve / 0.47): it tracks 6.85 TCH^0.952 within ~10%
  Asner TCH-only     ACD = 6.85 TCH^0.952, pantropical (Asner & Mascaro 2014, as tabled in PMC12040082)
  Jucker 2018 Eq 9   ACD = 0.567 TCH^0.554 BA^1.081 WD^0.186, BA = 1.112 TCH, WD = 0.385 TCH^0.097
  Jucker 2018 Eq 10  the same with BA = 1.287 TCH^0.987 (1 + 1.983 Cover_resid),
                     Cover_resid = Cover20 - 1 / (1 + exp(12.431) TCH^-4.061)   (Sabah, 173 plots)
  Coomes 2017        ACD = 25.93 GF19^-0.209 TCH^0.437 (Sepilok, 36 x 1 ha); GF19 floored at 0.01

Scored per plot and on the same 1,000 simulated projects as simulations.py. Exploratory.

Usage: python -m estimation.height_equations
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from estimation.extract_chm import HALF
from estimation.reliability import rrmse
from estimation.simulations import draw_projects
from estimation.tree_benchmark import eval_table
from estimation.tree_count import FOOTPRINT_HA

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
RES = EST / "results"
CF = 0.47
CACHES = {"CHMv1": EST / "cache" / "chm", "CHMv2": EST / "cache" / "chm_v2"}


def canopy_metrics(plots: pd.DataFrame, cache: Path) -> pd.DataFrame:
    yy, xx = np.mgrid[0:2 * HALF, 0:2 * HALF]
    dist = np.hypot(yy + 0.5 - HALF, xx + 0.5 - HALF)
    rows = []
    for p in plots.itertuples(index=False):
        f = cache / f"{p.plot_id}.npy"
        if not f.exists():
            continue
        h = np.load(f).astype("float64")
        v = h[(dist <= np.sqrt(FOOTPRINT_HA[p.dataset] * 10_000 / np.pi)) & (h >= 0)]
        if len(v):
            rows.append({"plot_id": p.plot_id, "tch": v.mean(), "cover20": (v > 20).mean(), "gf19": (v < 19).mean()})
    return pd.DataFrame(rows)


def equations(tch: pd.Series, cover20: pd.Series, gf19: pd.Series) -> dict:
    """AGB (Mg/ha) by each published equation."""
    t = tch.clip(lower=0.1)
    wd = 0.385 * t ** 0.097
    jucker = lambda ba: 0.567 * t ** 0.554 * ba ** 1.081 * wd ** 0.186
    resid = cover20 - 1 / (1 + np.exp(12.431) * t ** -4.061)
    ba10 = (1.287 * t ** 0.987 * (1 + 1.983 * resid)).clip(lower=0.1)
    return {"app as coded": 3.836 * t ** 1.131,
            "app read as carbon": 3.836 * t ** 1.131 / CF,
            "Asner TCH-only": 6.85 * t ** 0.952 / CF,
            "Jucker 2018 Eq 9": jucker(1.112 * t) / CF,
            "Jucker 2018 Eq 10": jucker(ba10) / CF,
            "Coomes 2017": 25.93 * gf19.clip(lower=0.01) ** -0.209 * t ** 0.437 / CF}


def main() -> None:
    d = eval_table()[["plot_id", "dataset", "region", "agb_Mg_ha", "map_agb_Mg_ha"]]
    m = pd.read_parquet(EST / "plot_manifest.parquet")[["plot_id", "dataset"]]
    cols = []
    for tag, cache in CACHES.items():
        c = canopy_metrics(m, cache)
        e = pd.DataFrame(equations(c["tch"], c["cover20"], c["gf19"]))
        e.columns = [f"{k} [{tag}]" for k in e.columns]
        d = d.merge(pd.concat([c[["plot_id"]], c[["tch"]].rename(columns={"tch": f"tch [{tag}]"}), e], axis=1), on="plot_id", how="left")
        cols += list(e.columns)
    cols = ["map_agb_Mg_ha"] + cols
    plot_rows, proj = [], {c: [] for c in cols}
    for c in cols:
        for subset, g in [("All", d)] + list(d.groupby("dataset")):
            g = g.dropna(subset=[c])
            plot_rows.append({"estimate": c, "subset": subset, "n": len(g), "rrmse_pct": rrmse(g["agb_Mg_ha"], g[c]),
                              "pct_of_field": 100 * g[c].sum() / g["agb_Mg_ha"].sum()})
    for s, reg, g in draw_projects(d):
        for c in cols:
            proj[c].append({"dataset": g["dataset"].iloc[0], "pct": 100 * g[c].mean() / g["agb_Mg_ha"].mean()})
    proj_rows = []
    for c in cols:
        S = pd.DataFrame(proj[c])
        for subset, x in [("All", S)] + list(S.groupby("dataset")):
            proj_rows.append({"estimate": c, "subset": subset, "median_pct": x["pct"].median(), "p5_pct": x["pct"].quantile(.05),
                              "p95_pct": x["pct"].quantile(.95), "within_25pct": 100 * ((x["pct"] - 100).abs() <= 25).mean()})
    P, J = pd.DataFrame(plot_rows), pd.DataFrame(proj_rows)
    P.to_csv(RES / "height_equations.csv", index=False)
    J.to_csv(RES / "height_equations_projects.csv", index=False)
    pd.set_option("display.width", 220)
    print(d[[c for c in d.columns if c.startswith("tch")]].describe().round(1).to_string())
    print(P[P["subset"] == "All"].round(1).to_string(index=False))
    print(J.pivot(index="estimate", columns="subset", values=["median_pct", "within_25pct"]).round(0).to_string())


if __name__ == "__main__":
    main()
