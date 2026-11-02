import raw from "@/data/results.json";

type Num = number | null;

export interface AccRow {
  model_name: string;
  subset: string;
  n_samples: number;
  rrmse_pct: number;
  relative_bias_pct: number;
  r2_score: number;
  lins_ccc?: number;
}

export interface Results {
  datasets: Record<string, string>;
  headline: Record<string, number>;
  accuracy_gee: AccRow[];
  ladder: AccRow[];
  accuracy_gee_bootstrap: { subset: string; comparison: string; diff_points: number; ci_lo: number; ci_hi: number }[];
  project_scale: {
    model: string;
    dataset: string;
    agg_n1: number;
    agg_n10: number;
    agg_n20: number;
    kshot_k0: number;
    kshot_k10: number;
    kshot_k20: number;
  }[];
  scatter: { d: string; y: number; b: number; g: number }[];
  gt_project: {
    region: string;
    n_plots: number;
    agb_mean: number;
    u90_total_pct: number;
    share_sampling_pct: number;
    deduct_VM0047_pct: number;
    deduct_ARTOOL14_pct: number;
    deduct_GS_pct: number;
    deduct_VMD0017_pct: number;
    SNI7724_meets_20pct: boolean;
    n_needed_10pct_90: number;
  }[];
  gt_plots: { region: string; n_trees: number; agb_mc_median: number; agb_lo95: number; agb_hi95: number; rel_hw95_pct: number }[];
  gt_safe_blocks: {
    block: string;
    n_plots: number;
    dagb_Mg_ha_yr: number;
    rho_t0_t1: number;
    U90_rho0_pct: number;
    U90_rho_pct: number;
    deduct_rho0_pct: number;
    deduct_rho_pct: number;
  }[];
  cloud_month: Record<string, number>[];
  cloud_group: {
    group: string;
    n_locations: number;
    p_clear: number;
    median_gap_days: number;
    p90_gap_days: number;
    max_gap_days: number;
    P_win30_emp: number;
    P_win90_emp: number;
  }[];
  cloud_scene: {
    group: string;
    scene_threshold_pct: number;
    share_passing: number;
    plot_clear_given_pass: number;
    clear_plots_rejected: number;
    plot_cloudy_given_pass: number;
  }[];
  cloud_robustness: { q: number; strategy: string; subset: string; n: number; rrmse_pct: number; bias_pct: number }[];
  interval_methods: { method: string; subset: string; n: number; coverage: number; median_ratio_hi_lo: number }[];
  cloud_aware: { condition: string; subset: string; method: string; n: number; coverage: number; median_ratio_hi_lo: number }[];
  frontier: { rule: string; delta: Num; over: number; yield: number }[];
  crediting_robustness: {
    estimator: string;
    delta: number;
    bound: string;
    realised_over: number;
    ci_lo: number;
    ci_hi: number;
    yield: number;
  }[];
  conformal_crediting: {
    setting: string;
    k: number;
    design: string;
    rule: string;
    delta: number;
    projects: number;
    over_rate: number;
    mean_yield: number;
  }[];
  bank_stress: { scheme: string; delta: number; over: number; yld: number; n_cal_min: number }[];
  seq_gain_loss: { level: string; estimator: string; rmse: number; mae: number; bias: number }[];
  seq_gee: { level: string; estimator: string; rmse: number; mae: number; r: Num }[];
  seq_improvement: { model_name: string; level: string; n: number; rmse: number; mae: number; bias: number }[];
  seed_stability: Record<string, number>[];
  bootstrap_ci: { subset: string; metric: string; value: number; ci_lo: number; ci_hi: number }[];
  trees_summary: Record<string, number>;
  wood_classes: { class: string; species: number; stem_share_pct: number; carbon_share_pct: number; mean_wd: number; top_families: string }[];
  diameter_classes: { diameter: string; stems_ha: number; stem_share_pct: number; carbon_share_pct: number }[];
  tree_benchmark: {
    subset: string;
    estimator: string;
    plots: number;
    field_tCO2e_ha_mean: number;
    sat_tCO2e_ha_mean: number;
    sat_pct_of_field_total: number;
    plot_pct_median: number;
    plots_within_25pct: number;
  }[];
  ndvi: { agb_class: string; n: number; median: number; p10: number; p90: number; spearman_all: number; spearman_agb150: number }[];
  /** One row per plot, carbon in t CO2e/ha: f field, m map, e4 tree count, e4s tree count scaled; st field stems/ha, tr satellite trees/ha, h mean canopy height. */
  plots: { id: string; d: string; reg: string; f: number; m: number; e4: number; e4s: number; st: Num; tr: number; h: Num }[];
  no_canopy_plots: number;
  chm_examples: ChmExample[];
  stem_example: {
    plot_id: string;
    dbh_cm: number;
    height_m: number;
    local_name: string;
    scientific_name: string;
    family: string;
    wood_density: number;
    plot_area_ha: number;
    agb_kg: number;
    agb_Mg_ha: number;
  }[];
  simulations: {
    sim: number;
    dataset: string;
    site: string;
    plots: number;
    area_ha: number;
    field_stems_ha: Num;
    sat_trees_ha: number;
    field_tCO2e: number;
    map_tCO2e: number;
    map_pct: number;
    e4_tCO2e: number;
    e4_pct: number;
    e4cal_tCO2e: number;
    e4cal_pct: number;
    credited_tCO2e: number;
    credited_pct: number;
    over_credited: boolean;
  }[];
  simulation_plots: {
    sim: number;
    plot_id: string;
    site: string;
    field_stems_ha: Num;
    sat_trees_ha: number;
    field_tCO2e_ha: number;
    map_tCO2e_ha: number;
    e4_tCO2e_ha: number;
    e4cal_tCO2e_ha: number;
  }[];
  simulations_summary: {
    estimate: string;
    median_pct: number;
    p5_pct: number;
    p95_pct: number;
    within_10pct: number;
    within_25pct: number;
    above_field_pct: number;
  }[];
  simulation_hist: { edges: number[]; n: number; map: number[]; e4: number[]; e4cal: number[]; credited: number[] };
  /** Fixes after the reveal (exploratory) on the same 1,000 projects, and the blind test on 35 unseen Danum plots. */
  production: {
    fixes: {
      key: string;
      median_pct_all: number;
      p5_pct_all: number;
      p95_pct_all: number;
      within_25pct_all: number;
      within_25pct_hcsa: number;
      median_pct_hcsa?: number;
      above_field_pct_all?: number;
      above_field_pct_hcsa?: number;
    }[];
    danum: {
      estimate: "map" | "estimate" | "credit";
      plots: number;
      rrmse_pct: number;
      total_pct_of_field: number;
      draws10_median_pct: number;
      draws10_p5_pct: number;
      draws10_p95_pct: number;
      draws10_within_25pct: number;
      draws10_above_field_pct: number;
    }[];
    heights: { name: string; v1: number; v2: number; danum: number }[];
    e4: { v1: { trees_ha: number; pct: number }; v2: { trees_ha: number; pct: number } };
    rrmse_paper: number;
    rrmse_prod: number;
    rrmse_gain: number;
    rrmse_gain_lo: number;
    rrmse_gain_hi: number;
  };
}

/** A 1 m canopy height patch (heights as characters, code 35 = 0 m) with the trees E4 detected inside the plot. */
export interface ChmExample {
  plot_id: string;
  dataset: string;
  size: number;
  footprint_r_m: number;
  heights: string;
  /** row, col, height m, crown diameter m, stem diameter cm */
  trees: [number, number, number, number, number][];
  field_tco2e_ha: number;
  e4_tco2e_ha: number;
  map_tco2e_ha: number;
  field_stems_ha: Num;
  sat_trees_ha: number;
  rho_default: number;
}

export const D = raw as unknown as Results;
export const H = D.headline;

export const DATASET_KEYS = ["Labriere2018", "GEO-TREES", "HCSA_Indonesia"] as const;
export const DATASET_SHORT: Record<string, string> = {
  All: "All plots",
  Labriere2018: "Labrière, 1 ha",
  "GEO-TREES": "GEO-TREES",
  HCSA_Indonesia: "HCSA Indonesia, 0.05 ha",
};

/** Accuracy as the paper's readers use it: 100 minus the relative RMSE against the field value. */
export const accuracy = (errPct: number) => Math.max(0, 100 - errPct);

export const pct = (v: number, nd = 1) => `${v.toFixed(nd)}%`;
export const share = (v: number, nd = 0) => `${(v * 100).toFixed(nd)}%`;
