"""
Project simulations: how much carbon does each grid find in the same project?

One simulation is a hypothetical 1,000 ha forest carbon project. It picks one region at random
(regions with at least 10 plots, each region equally likely) and 10 of its plots at random; the 10
plots stand for the project. For those plots it reports, in tonnes of CO2e for the whole project:

  field        right grid: the stem lists or published plot biomass, Chave 2014, x 0.47 x 44/12
  map          the paper's best satellite map (E2 + canopy height + GEDI, leave-one-region-out)
  E4           count the trees on the 1 m canopy height map, then the field formula (tree_count)
  E4 scaled    E4 times a factor learned on other regions
  credited     what conformal crediting would issue on the map: map x exp(-q), with q calibrated
               on projects of other regions at a 10% over-crediting risk (as in crediting_robustness)

and each as a percentage of the field amount. 1,000 simulations are run; the first 10 are printed
plot by plot (simulation_plots.csv) and project by project (simulations.csv holds all 1,000).

Usage: python -m estimation.simulations
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from estimation.conformal_crediting import conformal_q, make_projects
from estimation.right_grid import hcsa_trees
from estimation.tree_benchmark import eval_table

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
RES = EST / "results"
CF, CO2 = 0.47, 44 / 12
N_SIM, N_PLOTS, AREA_HA, DELTA = 1000, 10, 1000.0, 0.10
SITE = {"LAB_": "Labriere ", "IDN_": "HCSA ", "GT_": "GEO-TREES "}


def site_name(region: str) -> str:
    for k, v in SITE.items():
        if region.startswith(k):
            rest = region[len(k):]
            if k == "IDN_":  # "CentralKalimantan" -> "Central Kalimantan"
                rest = "".join(" " + ch if ch.isupper() and i else ch for i, ch in enumerate(rest))
            if k == "LAB_":  # "NOURAGUES" -> "Nouragues"
                rest = rest.title()
            if k == "GT_":  # "AM_-1_-6" -> "Americas cell -10/-60" (south-west corner of the 10 degree cell)
                cont, la, lo = rest.split("_")
                rest = {"AM": "Americas", "AF": "Africa", "AS": "Asia"}[cont] + f" cell {int(la) * 10}/{int(lo) * 10}"
            return v + rest
    return region


def conformal_q_by_region(d: pd.DataFrame) -> dict:
    """q for a target region, from the map's log ratio on projects of every other region."""
    m = pd.read_parquet(EST / "plot_manifest.parquet")[["plot_id", "lat", "lon"]]
    P = make_projects(d.merge(m, on="plot_id"))
    g = P.groupby("project")
    pr = pd.DataFrame({"region": g["region"].first(), "z": np.log(g["map_agb_Mg_ha"].mean() / g["agb_Mg_ha"].mean())})
    return {reg: conformal_q(pr.loc[pr["region"] != reg, "z"], DELTA) for reg in d["region"].unique()}


def draw_projects(d: pd.DataFrame):
    """The simulated projects: (sim number, region, its 10 plots), seeded so every caller gets the same draws."""
    regions = sorted(r for r, n in d["region"].value_counts().items() if n >= N_PLOTS)
    for s in range(1, N_SIM + 1):
        rng = np.random.default_rng(s)
        reg = regions[rng.integers(len(regions))]
        g = d[d["region"] == reg]
        yield s, reg, g.iloc[rng.choice(len(g), N_PLOTS, replace=False)]


def main() -> None:
    d = eval_table()
    t = hcsa_trees()
    t["plot_id"] = "HCSA_" + t["plot_key"].str.replace(r"[^A-Za-z0-9]+", "_", regex=True)
    stems = (1 / t["area_protocol_ha"]).groupby(t["plot_id"]).sum().rename("field_stems_ha")
    d = d.merge(stems, left_on="plot_id", right_index=True, how="left")
    q = conformal_q_by_region(d)
    regions = sorted(r for r, n in d["region"].value_counts().items() if n >= N_PLOTS)
    t_ha = lambda x: x * CF * CO2  # Mg AGB/ha -> t CO2e/ha
    sims, plot_rows = [], []
    for s, reg, g in draw_projects(d):
        field = t_ha(g["agb_Mg_ha"].mean()) * AREA_HA
        row = {"sim": s, "dataset": g["dataset"].iloc[0], "region": reg, "site": site_name(reg), "plots": N_PLOTS, "area_ha": AREA_HA,
               "field_stems_ha": g["field_stems_ha"].mean(), "sat_trees_ha": g["sat_trees_ha"].mean(), "field_tCO2e": field}
        for name, col in [("map", "map_agb_Mg_ha"), ("e4", "sat_agb_Mg_ha"), ("e4cal", "e4cal_agb_Mg_ha")]:
            v = t_ha(g[col].mean()) * AREA_HA
            row[f"{name}_tCO2e"], row[f"{name}_pct"] = v, 100 * v / field
        credit = row["map_tCO2e"] * np.exp(-q[reg]) if np.isfinite(q[reg]) else 0.0
        row.update({"credited_tCO2e": credit, "credited_pct": 100 * credit / field, "over_credited": credit > field})
        sims.append(row)
        if s <= 10:
            for p in g.itertuples(index=False):
                plot_rows.append({"sim": s, "plot_id": p.plot_id, "site": site_name(reg), "field_stems_ha": p.field_stems_ha,
                                  "sat_trees_ha": p.sat_trees_ha, "field_tCO2e_ha": t_ha(p.agb_Mg_ha),
                                  "map_tCO2e_ha": t_ha(p.map_agb_Mg_ha), "e4_tCO2e_ha": t_ha(p.sat_agb_Mg_ha),
                                  "e4cal_tCO2e_ha": t_ha(p.e4cal_agb_Mg_ha)})
    S = pd.DataFrame(sims)
    S.to_csv(RES / "simulations.csv", index=False)
    pd.DataFrame(plot_rows).to_csv(RES / "simulation_plots.csv", index=False)

    summ = []
    for col in ["map_pct", "e4_pct", "e4cal_pct", "credited_pct"]:
        x = S[col]
        summ.append({"estimate": col.replace("_pct", ""), "median_pct": x.median(), "p5_pct": x.quantile(0.05), "p95_pct": x.quantile(0.95),
                     "within_10pct": 100 * ((x - 100).abs() <= 10).mean(), "within_25pct": 100 * ((x - 100).abs() <= 25).mean(),
                     "above_field_pct": 100 * (x > 100).mean()})
    U = pd.DataFrame(summ)
    U.to_csv(RES / "simulations_summary.csv", index=False)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    show = ["sim", "site", "field_stems_ha", "sat_trees_ha", "field_tCO2e", "map_tCO2e", "map_pct", "e4_tCO2e", "e4_pct", "e4cal_pct", "credited_tCO2e", "credited_pct"]
    print(S.head(10)[show].round(1).to_string(index=False))
    print(U.round(1).to_string(index=False))
    print(f"regions drawn from: {len(regions)}; over-credited simulations: {100 * S['over_credited'].mean():.1f}%")


if __name__ == "__main__":
    main()
