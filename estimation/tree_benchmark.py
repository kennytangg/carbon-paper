"""
Benchmark of E4 (count the trees from space, then the field formula) against the right grid, and
what the field tree lists say about trees, wood and carbon. Run after tree_count; opens the sealed
right grid, so it is part of the reveal.

  A  ground truth anatomy   HCSA stem lists: stems per hectare, carbon by diameter class, and the
                            wood of every stem grouped by density (light < 0.5, medium 0.5-0.7,
                            heavy >= 0.7 g/cm3), with the error of a default density instead of the
                            species value (the only density a satellite can use)
  B  trees seen from space  satellite tops per hectare against field stems per hectare (HCSA)
  C  carbon benchmark       satellite carbon as a share of field carbon, per dataset, for E4 as is,
                            E4 scaled by a factor learned on other regions (leave-one-region-out),
                            and the paper's best map (E2 + canopy height + GEDI)
  D  greenness              Sentinel-2 NDVI by biomass class: why an index alone cannot give carbon
  E  examples               the canopy height patch and detected trees of the median-biomass plot of
                            each dataset, for the dashboard

No RMSE here: every row is an amount of carbon and a percentage of the field amount.

Usage: python -m estimation.tree_benchmark
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from estimation.right_grid import hcsa_trees
from estimation.tree_count import CHM, FOOTPRINT_HA, default_wood_density

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
RES = EST / "results"
CF, CO2 = 0.47, 44 / 12
WD_CLASSES = [(0, 0.5, "light (< 0.5)"), (0.5, 0.7, "medium (0.5-0.7)"), (0.7, 9, "heavy (>= 0.7)")]
D_CLASSES = [(5, 15, "5-15 cm"), (15, 30, "15-30 cm"), (30, 50, "30-50 cm"), (50, 999, ">= 50 cm")]


def eval_table() -> pd.DataFrame:
    """Plots with field truth, E4, its leave-one-region-out scaled version and the best map."""
    gt = pd.read_parquet(EST / "right_grid_sealed.parquet")[["plot_id", "agb_Mg_ha", "n_trees"]]
    e4 = pd.read_parquet(EST / "left_tree_count.parquet")
    best = pd.read_parquet(RES / "accuracy_gee_preds.parquet")[["plot_id", "+ canopy height + GEDI"]]
    d = e4.merge(gt, on="plot_id").merge(best.rename(columns={"+ canopy height + GEDI": "map_agb_Mg_ha"}), on="plot_id")
    d = d[d["agb_Mg_ha"] > 1].reset_index(drop=True)
    # one factor per held-out region: ratio of totals on every other region with a nonzero count
    k = np.full(len(d), np.nan)
    for reg in d["region"].unique():
        tr = (d["region"] != reg) & (d["sat_agb_Mg_ha"] > 0)
        k[(d["region"] == reg).to_numpy()] = d.loc[tr, "agb_Mg_ha"].sum() / d.loc[tr, "sat_agb_Mg_ha"].sum()
    d["e4_factor"] = k
    d["e4cal_agb_Mg_ha"] = d["sat_agb_Mg_ha"] * d["e4_factor"]
    return d


def anatomy() -> dict:
    t = hcsa_trees()
    t["agb_Mg_ha"] = t["agb_Mg_ha_contrib"]
    t["stems_ha"] = 1 / t["area_protocol_ha"]
    n_plots = t["plot_key"].nunique()
    rho0 = default_wood_density()["Indo-Malaya"]
    t["agb_default_rho"] = 0.0673 * (rho0 * t["DBH (cm)"] ** 2 * t["Height (m)"]) ** 0.976 / 1000 / t["area_protocol_ha"]
    per_plot = t.groupby("plot_key").agg(stems_ha=("stems_ha", "sum"), agb=("agb_Mg_ha", "sum"), agb_rho0=("agb_default_rho", "sum"),
                                         species=("Scientific Name", "nunique"), h_max=("Height (m)", "max"))
    per_plot = per_plot[per_plot["agb"] > 1]
    rows = []
    for lo, hi, name in WD_CLASSES:
        s = t[(t["Wood density (g/cm3)"] >= lo) & (t["Wood density (g/cm3)"] < hi)]
        fam = s.groupby("Famili")["agb_Mg_ha"].sum().sort_values(ascending=False).head(3).index.str.strip().tolist()
        sp = s.groupby("Scientific Name")["agb_Mg_ha"].sum().sort_values(ascending=False).head(3).index.str.strip().tolist()
        rows.append({"class": name, "records": len(s), "species": s["Scientific Name"].nunique(),
                     "stem_share_pct": 100 * s["stems_ha"].sum() / t["stems_ha"].sum(),
                     "carbon_share_pct": 100 * s["agb_Mg_ha"].sum() / t["agb_Mg_ha"].sum(),
                     "mean_wd": s["Wood density (g/cm3)"].mean(), "top_families": "; ".join(fam), "top_species": "; ".join(sp)})
    wd = pd.DataFrame(rows)
    drows = []
    for lo, hi, name in D_CLASSES:
        s = t[(t["DBH (cm)"] >= lo) & (t["DBH (cm)"] < hi)]
        drows.append({"diameter": name, "stems_ha": s["stems_ha"].sum() / n_plots,
                      "stem_share_pct": 100 * s["stems_ha"].sum() / t["stems_ha"].sum(),
                      "carbon_share_pct": 100 * s["agb_Mg_ha"].sum() / t["agb_Mg_ha"].sum()})
    dc = pd.DataFrame(drows)
    ratio = per_plot["agb_rho0"] / per_plot["agb"]
    summary = {
        "hcsa_plots": int(len(per_plot)), "hcsa_records": int(len(t)), "hcsa_species": int(t["Scientific Name"].nunique()),
        "hcsa_families": int(t["Famili"].str.strip().nunique()),
        "stems_ha_median": float(per_plot["stems_ha"].median()), "species_per_plot_median": float(per_plot["species"].median()),
        "wd_stem_mean": float(np.average(t["Wood density (g/cm3)"], weights=t["stems_ha"])), "wd_default": rho0,
        "wd_default_total_pct": float(100 * per_plot["agb_rho0"].sum() / per_plot["agb"].sum()),
        "wd_default_plot_p10_pct": float(100 * ratio.quantile(0.1)), "wd_default_plot_p90_pct": float(100 * ratio.quantile(0.9)),
    }
    return {"wd": wd, "dc": dc, "summary": summary, "per_plot": per_plot}


def main() -> None:
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    A = anatomy()
    A["wd"].to_csv(RES / "gt_wood_density_classes.csv", index=False)
    A["dc"].to_csv(RES / "gt_diameter_classes.csv", index=False)
    print(A["wd"].round(2).to_string(index=False))
    print(A["dc"].round(1).to_string(index=False))
    print({k: round(v, 3) if isinstance(v, float) else v for k, v in A["summary"].items()})

    d = eval_table()
    # B: trees seen from space against stems counted in the field (HCSA has the stem lists)
    t = hcsa_trees()
    t["plot_id"] = "HCSA_" + t["plot_key"].str.replace(r"[^A-Za-z0-9]+", "_", regex=True)
    field = t.assign(s=1 / t["area_protocol_ha"], s15=(t["DBH (cm)"] >= 15) / t["area_protocol_ha"]).groupby("plot_id")[["s", "s15"]].sum()
    h = d.merge(field.rename(columns={"s": "field_stems_ha", "s15": "field_stems_d15_ha"}), left_on="plot_id", right_index=True)
    count = {
        "plots": len(h),
        "field_stems_ha_median": float(h["field_stems_ha"].median()), "field_stems_d15_ha_median": float(h["field_stems_d15_ha"].median()),
        "sat_trees_ha_median": float(h["sat_trees_ha"].median()), "sat_trees_ha_unsmoothed_median": float(h["sat_trees_ha_unsmoothed"].median()),
        "sat_share_of_stems_pct": float(100 * h["sat_trees_ha"].sum() / h["field_stems_ha"].sum()),
        "sat_share_of_d15_stems_pct": float(100 * h["sat_trees_ha"].sum() / h["field_stems_d15_ha"].sum()),
        "count_corr_spearman": float(h[["sat_trees_ha", "field_stems_ha"]].corr("spearman").iloc[0, 1]),
    }
    print("trees seen from space (HCSA):", {k: round(v, 2) for k, v in count.items()})

    # C: carbon benchmark, amounts and percentages only
    est = {"E4 count + formula (as is)": "sat_agb_Mg_ha", "E4 unsmoothed (sensitivity)": "sat_agb_Mg_ha_unsmoothed",
           "E4 scaled on other regions": "e4cal_agb_Mg_ha", "map: E2 + canopy height + GEDI": "map_agb_Mg_ha"}
    rows = []
    for subset, g in [("All", d)] + list(d.groupby("dataset")):
        field_t = (g["agb_Mg_ha"] * CF * CO2 * g["footprint_ha"]).sum()
        for name, col in est.items():
            sat_t = (g[col] * CF * CO2 * g["footprint_ha"]).sum()
            pct = 100 * g[col] / g["agb_Mg_ha"]
            rows.append({"subset": subset, "estimator": name, "plots": len(g),
                         "field_tCO2e_ha_mean": float((g["agb_Mg_ha"] * CF * CO2).mean()),
                         "sat_tCO2e_ha_mean": float((g[col] * CF * CO2).mean()),
                         "sat_pct_of_field_total": float(100 * sat_t / field_t),
                         "plot_pct_median": float(pct.median()), "plot_pct_p10": float(pct.quantile(0.1)), "plot_pct_p90": float(pct.quantile(0.9)),
                         "plots_within_25pct": float(100 * ((pct >= 75) & (pct <= 125)).mean())})
    B = pd.DataFrame(rows)
    B.to_csv(RES / "tree_benchmark.csv", index=False)
    print(B.round(1).to_string(index=False))
    pd.DataFrame([{**A["summary"], **{f"count_{k}": v for k, v in count.items()},
                   "e4_factor_median": float(d["e4_factor"].median())}]).to_csv(RES / "tree_benchmark_summary.csv", index=False)
    d = d.merge(field.rename(columns={"s": "field_stems_ha", "s15": "field_stems_d15_ha"}), left_on="plot_id", right_index=True, how="left")
    cols = ["plot_id", "dataset", "region", "footprint_ha", "agb_Mg_ha", "n_trees", "field_stems_ha", "sat_trees_ha", "sat_trees_d15_ha",
            "sat_top_h_mean_m", "chm_mean_m", "rho_default", "sat_agb_Mg_ha", "e4_factor", "e4cal_agb_Mg_ha", "map_agb_Mg_ha"]
    d[cols].to_csv(RES / "tree_benchmark_plots.csv", index=False)
    print(f"factor learned on other regions: median {d['e4_factor'].median():.2f}")

    # D: greenness against biomass, on the plots with a clear Sentinel-2 view in the matching window
    f = pd.read_parquet(EST / "left_features_win90.parquet")[["plot_id", "s2_ndvi"]].dropna()
    g = d[["plot_id", "agb_Mg_ha"]].merge(f, on="plot_id")
    g["agb_class"] = pd.cut(g["agb_Mg_ha"], [0, 100, 200, 300, np.inf], right=False, labels=["< 100", "100-200", "200-300", ">= 300"])
    nd = g.groupby("agb_class", observed=True)["s2_ndvi"].agg(n="size", median="median", p10=lambda x: x.quantile(0.1), p90=lambda x: x.quantile(0.9)).reset_index()
    nd["spearman_all"] = g[["s2_ndvi", "agb_Mg_ha"]].corr("spearman").iloc[0, 1]
    hi = g[g["agb_Mg_ha"] >= 150]
    nd["spearman_agb150"] = hi[["s2_ndvi", "agb_Mg_ha"]].corr("spearman").iloc[0, 1]
    nd.to_csv(RES / "ndvi_saturation.csv", index=False)
    print(nd.round(3).to_string(index=False))

    # E: one example per dataset, the plot with the median field biomass (no hand-picking)
    trees = pd.read_parquet(EST / "left_tree_list.parquet")
    ex = []
    for ds, gg in d.groupby("dataset"):
        p = gg.iloc[(gg["agb_Mg_ha"] - gg["agb_Mg_ha"].median()).abs().argsort().iloc[0]]
        h = np.clip(np.nan_to_num(np.load(CHM / f"{p.plot_id}.npy"), nan=0.0), 0, 56).round().astype(int)
        tt = trees[trees["plot_id"] == p.plot_id]
        ex.append({"plot_id": p.plot_id, "dataset": ds, "size": int(h.shape[0]), "footprint_r_m": float(np.sqrt(FOOTPRINT_HA[ds] * 1e4 / np.pi)),
                   "heights": "".join(chr(35 + v) for v in h.ravel()),
                   "trees": [[int(t.row), int(t.col), round(float(t.H_m), 1), round(float(t.CD_m), 1), round(float(t.D_cm), 1)] for t in tt.itertuples()],
                   "field_tco2e_ha": float(p.agb_Mg_ha * CF * CO2), "e4_tco2e_ha": float(p.sat_agb_Mg_ha * CF * CO2),
                   "map_tco2e_ha": float(p.map_agb_Mg_ha * CF * CO2), "field_stems_ha": None if pd.isna(p.field_stems_ha) else float(p.field_stems_ha),
                   "sat_trees_ha": float(p.sat_trees_ha), "rho_default": float(p.rho_default)})
    (RES / "chm_examples.json").write_text(json.dumps(ex), encoding="utf-8")
    print("examples:", [(e["dataset"], e["plot_id"], len(e["trees"])) for e in ex])
    # the field stem list of the HCSA example: what a ground-truth plot actually contains
    hx = next(e["plot_id"] for e in ex if e["dataset"] == "HCSA_Indonesia")
    sl = t[t["plot_id"] == hx].sort_values("DBH (cm)", ascending=False)
    sl = pd.DataFrame({"plot_id": hx, "dbh_cm": sl["DBH (cm)"], "height_m": sl["Height (m)"], "local_name": sl["Local Name"].str.strip(),
                       "scientific_name": sl["Scientific Name"].str.strip(), "family": sl["Famili"].str.strip(),
                       "wood_density": sl["Wood density (g/cm3)"], "plot_area_ha": sl["area_protocol_ha"], "agb_kg": sl["agb_kg"],
                       "agb_Mg_ha": sl["agb_Mg_ha_contrib"]})
    sl.to_csv(RES / "stem_list_example.csv", index=False)
    print(f"stem list of {hx}: {len(sl)} stems, {sl['agb_Mg_ha'].sum():.1f} Mg/ha")


if __name__ == "__main__":
    main()
