"""Export the paper's result tables into one compact JSON file for the dashboard.

Run from the repo root with the project venv:

    .venv/Scripts/python.exe dashboard/scripts/export_data.py

Reads only data/estimation/results/ (published result tables and plot-level
predictions). Writes dashboard/data/results.json. Every number the dashboard
shows comes from this file.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EST = ROOT / "data" / "estimation"
RES = EST / "results"
OUT = ROOT / "dashboard" / "data" / "results.json"

DATASETS = {
    "Labriere2018": "Labrière (1 ha, Gabon & Fr. Guiana)",
    "GEO-TREES": "GEO-TREES (pantropical network)",
    "HCSA_Indonesia": "HCSA Indonesia (0.05 ha)",
    "All": "All 475 plots",
}


def r(x, nd=2):
    if x is None:
        return None
    try:
        if isinstance(x, float) and math.isnan(x):
            return None
    except TypeError:
        pass
    if isinstance(x, (bool,)):
        return x
    if isinstance(x, (int,)):
        return x
    try:
        return round(float(x), nd)
    except (TypeError, ValueError):
        return x


def rows(df: pd.DataFrame, cols: list[str], nd=3) -> list[dict]:
    out = []
    for rec in df[cols].to_dict("records"):
        out.append({k: (r(v, nd) if not isinstance(v, str) else v) for k, v in rec.items()})
    return out


def csv(name: str) -> pd.DataFrame:
    return pd.read_csv(RES / name)


def pick(df, **kw):
    m = pd.Series(True, index=df.index)
    for k, v in kw.items():
        m &= df[k] == v
    sub = df[m]
    assert len(sub) == 1, (kw, len(sub))
    return sub.iloc[0]


def main() -> None:
    data: dict = {"datasets": DATASETS}

    # ---------------------------------------------------------------- accuracy
    acc = csv("accuracy_gee.csv")
    best, base = "+ canopy height + GEDI", "baseline E2"
    data["accuracy_gee"] = rows(
        acc, ["model_name", "subset", "n_samples", "rrmse_pct", "relative_bias_pct", "r2_score", "lins_ccc"]
    )
    ladder = csv("improvement_ladder.csv")
    data["ladder"] = rows(ladder, ["model_name", "subset", "n_samples", "rrmse_pct", "relative_bias_pct", "r2_score"])
    boot = csv("accuracy_gee_bootstrap.csv")
    data["accuracy_gee_bootstrap"] = rows(boot, list(boot.columns))
    ps = csv("accuracy_gee_project_scale.csv")
    data["project_scale"] = rows(ps, list(ps.columns), 2)

    preds = pd.read_parquet(RES / "accuracy_gee_preds.parquet")
    data["scatter"] = [
        {"d": d, "y": r(y, 1), "b": r(b, 1), "g": r(g, 1)}
        for d, y, b, g in zip(preds["dataset"], preds["agb_Mg_ha"], preds[base], preds[best])
    ]

    # ---------------------------------------------------------------- headline
    def rr(subset, model):
        return float(pick(acc, subset=subset, model_name=model)["rrmse_pct"])

    def pscale(dataset, model, col):
        return float(pick(ps, dataset=dataset, model=model)[col])

    b_all = pick(boot, subset="All")
    cc = csv("conformal_crediting.csv")
    # same design as the paper's Table IV: satellite + 5 or 10 random plots, ratio estimator
    vm_field = cc[(cc["setting"] == "ratio (satellite + k)") & (cc["design"] == "srs") & (cc["rule"] == "VM0047 (U-10%)")]
    rob = csv("crediting_robustness.csv")
    gee_conf = pick(rob, estimator="E2 + canopy height + GEDI", bound="conformal", delta=0.1)
    conf_field = cc[(cc["setting"] == "field only") & (cc["rule"] == "conformal plain") & (cc["delta"] == 0.1)]
    fr = csv("crediting_frontier.csv")
    sat_conf = pick(fr, rule="satellite: conformal plain", delta=0.1)
    grp = csv("cloud_by_group.csv")
    scene = csv("cloud_scene_filter.csv")
    idn_scene = pick(scene, group="Indonesia (HCSA)", scene_threshold_pct=30)
    data["headline"] = {
        "plot_1ha_best": rr("Labriere2018", best),
        "plot_1ha_base": rr("Labriere2018", base),
        "all_best": rr("All", best),
        "all_base": rr("All", base),
        "geotrees_best": rr("GEO-TREES", best),
        "hcsa_best": rr("HCSA_Indonesia", best),
        "gain_all": float(b_all["diff_points"]),
        "gain_all_lo": float(b_all["ci_lo"]),
        "gain_all_hi": float(b_all["ci_hi"]),
        "project_k0_labriere": pscale("Labriere2018", best, "kshot_k0"),
        "project_k0_geotrees": pscale("GEO-TREES", best, "kshot_k0"),
        "project_k0_hcsa": pscale("HCSA_Indonesia", best, "kshot_k0"),
        "avg20_labriere": pscale("Labriere2018", best, "agg_n20"),
        "avg20_geotrees": pscale("GEO-TREES", best, "agg_n20"),
        "idn_clear_share": float(pick(grp, group="Indonesia (HCSA)")["p_clear"]),
        "idn_scene30_clear_rejected": float(idn_scene["clear_plots_rejected"]),
        "vm0047_field_over_min": float(vm_field["over_rate"].min()),
        "vm0047_field_over_max": float(vm_field["over_rate"].max()),
        "conformal_field_over_max": float(conf_field["over_rate"].max()),
        "sat_conformal_over": float(sat_conf["over"]),
        "sat_conformal_yield": float(sat_conf["yield"]),
        "gee_conformal_over": float(gee_conf["realised_over"]),
        "gee_conformal_yield": float(gee_conf["yield"]),
        "n_projects": int(cc[cc["setting"] == "satellite only"]["projects"].iloc[0]),
    }
    data["headline"] = {k: r(v, 4) for k, v in data["headline"].items()}

    # ---------------------------------------------------------------- ground truth
    gtp = csv("gt_hcsa_project_uncertainty.csv")
    data["gt_project"] = rows(
        gtp,
        [
            "region", "n_plots", "agb_mean", "u90_total_pct", "share_sampling_pct",
            "deduct_VM0047_pct", "deduct_ARTOOL14_pct", "deduct_GS_pct", "deduct_VMD0017_pct",
            "SNI7724_meets_20pct", "n_needed_10pct_90",
        ],
        1,
    )
    gpl = csv("gt_hcsa_plot_uncertainty.csv").sort_values("agb_mc_median")
    data["gt_plots"] = rows(gpl, ["region", "n_trees", "agb_mc_median", "agb_lo95", "agb_hi95", "rel_hw95_pct"], 1)
    blk = csv("gt_safe_block_seq_uncertainty.csv")
    data["gt_safe_blocks"] = rows(
        blk, ["block", "n_plots", "dagb_Mg_ha_yr", "rho_t0_t1", "U90_rho0_pct", "U90_rho_pct", "deduct_rho0_pct", "deduct_rho_pct"], 2
    )

    # ---------------------------------------------------------------- clouds
    mon = csv("cloud_by_month.csv")
    data["cloud_month"] = rows(mon, list(mon.columns), 3)
    data["cloud_group"] = rows(
        grp, ["group", "n_locations", "p_clear", "median_gap_days", "p90_gap_days", "max_gap_days", "P_win30_emp", "P_win90_emp"], 3
    )
    data["cloud_scene"] = rows(scene, list(scene.columns), 3)
    rob = csv("cloud_robustness.csv")
    data["cloud_robustness"] = rows(rob, ["q", "strategy", "subset", "n", "rrmse_pct", "bias_pct"], 2)

    # ---------------------------------------------------------------- confidence
    im = csv("interval_methods.csv")
    data["interval_methods"] = rows(im, ["method", "subset", "n", "coverage", "median_ratio_hi_lo"], 3)
    ca = csv("cloud_aware_cqr.csv")
    data["cloud_aware"] = rows(ca, list(ca.columns), 3)

    # ---------------------------------------------------------------- crediting
    data["frontier"] = rows(fr, list(fr.columns), 3)
    rob_c = csv("crediting_robustness.csv")
    data["crediting_robustness"] = rows(rob_c, ["estimator", "delta", "bound", "realised_over", "ci_lo", "ci_hi", "yield"], 3)
    data["conformal_crediting"] = rows(
        cc, ["setting", "k", "design", "rule", "delta", "projects", "over_rate", "mean_yield"], 3
    )
    bank = csv("conformal_bank_stress.csv")
    data["bank_stress"] = rows(bank, list(bank.columns), 3)

    # ---------------------------------------------------------------- sequestration
    data["seq_gain_loss"] = rows(csv("gain_loss.csv"), ["level", "estimator", "rmse", "mae", "bias"], 3)
    data["seq_gee"] = rows(csv("seq_gee.csv"), ["level", "estimator", "rmse", "mae", "r"], 3)
    data["seq_improvement"] = rows(csv("seq_improvement.csv"), ["model_name", "level", "n", "rmse", "mae", "bias"], 3)

    # ---------------------------------------------------------------- reliability
    data["seed_stability"] = rows(csv("seed_stability.csv"), list(csv("seed_stability.csv").columns), 2)
    data["bootstrap_ci"] = rows(csv("bootstrap_ci.csv"), ["subset", "metric", "value", "ci_lo", "ci_hi"], 2)

    # ---------------------------------------------------------------- trees from space (tree_benchmark)
    tco2 = 0.47 * 44 / 12  # Mg AGB/ha -> t CO2e/ha, the right grid's own factors
    data["trees_summary"] = {k: r(v, 4) for k, v in csv("tree_benchmark_summary.csv").iloc[0].items()}
    data["wood_classes"] = rows(csv("gt_wood_density_classes.csv"), ["class", "species", "stem_share_pct", "carbon_share_pct", "mean_wd", "top_families"], 3)
    data["diameter_classes"] = rows(csv("gt_diameter_classes.csv"), ["diameter", "stems_ha", "stem_share_pct", "carbon_share_pct"], 2)
    data["tree_benchmark"] = rows(csv("tree_benchmark.csv"), ["subset", "estimator", "plots", "field_tCO2e_ha_mean", "sat_tCO2e_ha_mean",
                                                             "sat_pct_of_field_total", "plot_pct_median", "plots_within_25pct"], 2)
    data["ndvi"] = rows(csv("ndvi_saturation.csv"), ["agb_class", "n", "median", "p10", "p90", "spearman_all", "spearman_agb150"], 3)
    tp = csv("tree_benchmark_plots.csv")
    data["plots"] = [
        {"id": p.plot_id, "d": p.dataset, "reg": p.region, "f": r(p.agb_Mg_ha * tco2, 1), "m": r(p.map_agb_Mg_ha * tco2, 1),
         "e4": r(p.sat_agb_Mg_ha * tco2, 1), "e4s": r(p.e4cal_agb_Mg_ha * tco2, 1), "st": r(p.field_stems_ha, 0), "tr": r(p.sat_trees_ha, 0),
         "h": r(p.chm_mean_m, 1)}
        for p in tp.itertuples()
    ]
    data["no_canopy_plots"] = int(((tp["chm_mean_m"] < 2) & (tp["agb_Mg_ha"] > 150)).sum())
    data["chm_examples"] = json.loads((RES / "chm_examples.json").read_text(encoding="utf-8"))
    data["stem_example"] = rows(csv("stem_list_example.csv"), ["plot_id", "dbh_cm", "height_m", "local_name", "scientific_name", "family",
                                                               "wood_density", "plot_area_ha", "agb_kg", "agb_Mg_ha"], 3)

    # ---------------------------------------------------------------- project simulations
    sims = csv("simulations.csv")
    data["simulations"] = rows(sims.head(10), ["sim", "dataset", "site", "plots", "area_ha", "field_stems_ha", "sat_trees_ha", "field_tCO2e",
                                               "map_tCO2e", "map_pct", "e4_tCO2e", "e4_pct", "e4cal_tCO2e", "e4cal_pct", "credited_tCO2e",
                                               "credited_pct", "over_credited"], 3)
    data["simulation_plots"] = rows(csv("simulation_plots.csv"), ["sim", "plot_id", "site", "field_stems_ha", "sat_trees_ha", "field_tCO2e_ha",
                                                                   "map_tCO2e_ha", "e4_tCO2e_ha", "e4cal_tCO2e_ha"], 3)
    data["simulations_summary"] = rows(csv("simulations_summary.csv"), ["estimate", "median_pct", "p5_pct", "p95_pct", "within_10pct",
                                                                         "within_25pct", "above_field_pct"], 3)
    edges = list(range(0, 210, 10))
    hist = {}
    for col in ["map_pct", "e4_pct", "e4cal_pct", "credited_pct"]:
        counts = pd.cut(sims[col].clip(upper=209.9), edges + [210], right=False).value_counts(sort=False).tolist()
        hist[col.replace("_pct", "")] = counts
    data["simulation_hist"] = {"edges": edges, "n": len(sims), **hist}

    # ---------------------------------------------------------------- toward production (exploratory) and the unseen Danum test
    fx = csv("crediting_fixes.csv")
    fx = fx[(fx["map"] == "embeddings + CH + GEDI") & fx["subset"].isin(["All", "HCSA_Indonesia"])]
    fx = fx.pivot(index="estimate", columns="subset", values=["median_pct", "p5_pct", "p95_pct", "within_25pct", "above_field_pct"])
    fx.columns = [f"{a}_{'all' if b == 'All' else 'hcsa'}" for a, b in fx.columns]
    ref = pick(csv("simulations_summary.csv"), estimate="map")
    ref_hcsa = pick(csv("accuracy_embeddings_projects.csv"), variant="best map", subset="HCSA_Indonesia")
    fixes = [{"key": "paper", "median_pct_all": ref["median_pct"], "p5_pct_all": ref["p5_pct"], "p95_pct_all": ref["p95_pct"],
              "within_25pct_all": ref["within_25pct"], "within_25pct_hcsa": ref_hcsa["within_25pct"]}]
    for k in ["map_pct", "map_mu_realm_pct", "local3_pct", "local3_shrunk_realm_pct", "local10_shrunk_realm_pct", "credit_project_q", "credit_region_q"]:
        fixes.append({"key": k, **fx.loc[k].to_dict()})
    dz = csv("external_danum.csv")
    eq = csv("height_equations.csv").query("subset == 'All'")
    eq_d = csv("external_danum_equations.csv").set_index("estimate")["total_pct_of_field"]
    heights = []
    for name in ["Jucker 2018 Eq 10", "Coomes 2017", "app as coded", "app read as carbon"]:
        heights.append({"name": name, "v1": eq.loc[eq["estimate"] == f"{name} [CHMv1]", "pct_of_field"].iloc[0],
                        "v2": eq.loc[eq["estimate"] == f"{name} [CHMv2]", "pct_of_field"].iloc[0], "danum": eq_d[f"{name} [CHMv2]"]})
    gt = pd.read_parquet(EST / "right_grid_sealed.parquet")[["plot_id", "agb_Mg_ha"]]
    e4 = {}
    for tag, f in [("v1", "left_tree_count.parquet"), ("v2", "left_tree_count_v2.parquet")]:
        t = pd.read_parquet(EST / f).merge(gt, on="plot_id")
        t = t[t["agb_Mg_ha"] > 1]
        e4[tag] = {"trees_ha": float(t["sat_trees_ha"].median()), "pct": 100 * t["sat_agb_Mg_ha"].sum() / t["agb_Mg_ha"].sum()}
    boot = pick(csv("accuracy_embeddings_bootstrap.csv"), comparison="embeddings + CH + GEDI - best map")
    acc = csv("accuracy_embeddings.csv").query("subset == 'All'").set_index("variant")["rrmse_pct"]
    data["production"] = {
        "fixes": [{k: r(v, 3) if not isinstance(v, str) else v for k, v in f.items()} for f in fixes],
        "danum": rows(dz, ["estimate", "plots", "rrmse_pct", "total_pct_of_field", "draws10_median_pct", "draws10_p5_pct", "draws10_p95_pct",
                           "draws10_within_25pct", "draws10_above_field_pct"], 3),
        "heights": [{k: r(v, 3) if not isinstance(v, str) else v for k, v in h.items()} for h in heights],
        "e4": {k: {kk: r(vv, 3) for kk, vv in v.items()} for k, v in e4.items()},
        "rrmse_paper": r(acc["best map"], 3), "rrmse_prod": r(acc["embeddings + CH + GEDI"], 3),
        "rrmse_gain": r(boot["diff_points"], 3), "rrmse_gain_lo": r(boot["ci_lo"], 3), "rrmse_gain_hi": r(boot["ci_hi"], 3),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")
    for k, v in data["headline"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
