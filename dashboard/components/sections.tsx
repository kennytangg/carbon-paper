"use client";

import { useState } from "react";
import { ColumnChart, HBarChart, LineChart, RangeChart, ScatterChart, Segmented } from "./charts";
import { Card, TableView, Tile } from "./ui";
import { D, H, DATASET_SHORT, accuracy, pct, share } from "@/lib/data";

type Metric = "acc" | "err";
const metricOpts: { value: Metric; label: string }[] = [
  { value: "acc", label: "Accuracy" },
  { value: "err", label: "Error" },
];
const asMetric = (m: Metric, err: number) => (m === "acc" ? accuracy(err) : err);
const range = (a: number, b: number, nd = 0) => {
  const [lo, hi] = [Math.min(a, b), Math.max(a, b)];
  return lo.toFixed(nd) === hi.toFixed(nd) ? `${lo.toFixed(nd)}%` : `${lo.toFixed(nd)}–${hi.toFixed(nd)}%`;
};

function Section({ id, title, sub, children }: { id: string; title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section className="block" id={id}>
      <div className="wrap">
        <h2>{title}</h2>
        {sub && <p className="section-sub">{sub}</p>}
        {children}
      </div>
    </section>
  );
}

/* ================================================================== overview */

export function Overview() {
  const acc1ha = accuracy(H.plot_1ha_best);
  const proj = [accuracy(H.project_k0_labriere), accuracy(H.project_k0_geotrees)];
  const avg20 = [accuracy(H.avg20_labriere), accuracy(H.avg20_geotrees)];
  return (
    <Section
      id="overview"
      title="The answer in one screen"
      sub="Accuracy here means 100 minus the relative error (relative RMSE) of the satellite estimate against the field ground truth, which is computed with the standard formula (Chave 2014 allometry, then carbon fraction 0.47, then 44/12 for CO₂). The satellite model never saw the field values of the region it was scored on."
    >
      <div className="hero">
        <div className="card">
          <div className="eyebrow">Per 1-hectare plot, satellite only</div>
          <div className="hero-figure">{acc1ha.toFixed(0)}%</div>
          <p style={{ margin: 0, color: "var(--text-secondary)" }}>
            accuracy against the field formula on the 1&nbsp;ha Labrière plots (error {pct(H.plot_1ha_best)}). With Sentinel, Landsat and PALSAR
            alone it was {accuracy(H.plot_1ha_base).toFixed(0)}%; adding a 1&nbsp;m canopy height map and GEDI lidar from Google Earth Engine
            raised it.
          </p>
          <div className="meter" aria-hidden>
            <div style={{ width: `${acc1ha}%` }} />
          </div>
        </div>
        <div className="card">
          <h3>How to read the numbers</h3>
          <ul style={{ margin: "10px 0 0", paddingLeft: 18, color: "var(--text-secondary)", fontSize: 14 }}>
            <li>
              <b style={{ color: "var(--text-primary)" }}>Bigger areas are more accurate.</b> Errors of single plots partly cancel when a whole project is
              added up.
            </li>
            <li>
              <b style={{ color: "var(--text-primary)" }}>Plot size matters more than the algorithm.</b> Small 0.05&nbsp;ha plots in Indonesia cannot be
              predicted plot by plot.
            </li>
            <li>
              <b style={{ color: "var(--text-primary)" }}>Growth is not visible from space at this scale.</b> A regional default rate beat every
              satellite change model.
            </li>
          </ul>
        </div>
      </div>
      <div className="grid tiles">
        <Tile
          label="Project total, no field plots (outside Indonesia)"
          value={range(proj[0], proj[1])}
          detail={`Error ${pct(H.project_k0_labriere)} (Labrière) and ${pct(H.project_k0_geotrees)} (GEO-TREES)`}
          status="good"
          statusText="Usable for screening"
          meter={Math.min(...proj)}
        />
        <Tile
          label="Average of 20 plots"
          value={range(avg20[0], avg20[1])}
          detail={`Error ${pct(H.avg20_labriere)} (Labrière) and ${pct(H.avg20_geotrees)} (GEO-TREES)`}
          status="good"
          statusText="Errors cancel out"
          meter={Math.min(...avg20)}
        />
        <Tile
          label="All 475 plots, one by one"
          value={`${accuracy(H.all_best).toFixed(0)}%`}
          detail={`Error ${pct(H.all_best)}, down from ${pct(H.all_base)} (gain ${Math.abs(H.gain_all).toFixed(1)} points, 95% CI ${Math.abs(H.gain_all_hi).toFixed(1)}–${Math.abs(H.gain_all_lo).toFixed(1)})`}
          status="warning"
          statusText="Mixed plot sizes"
          meter={accuracy(H.all_best)}
        />
        <Tile
          label="Small Indonesian plots (0.05 ha), one by one"
          value={`${accuracy(H.hcsa_best).toFixed(0)}%`}
          detail={`Error ${pct(H.hcsa_best)}. As a province total: ${accuracy(H.project_k0_hcsa).toFixed(0)}% (error ${pct(H.project_k0_hcsa)})`}
          status="critical"
          statusText="Not usable per plot"
          meter={accuracy(H.hcsa_best)}
        />
        <Tile
          label="Clear satellite views over Indonesian plots"
          value={share(H.idn_clear_share)}
          detail={`of Sentinel-2 passes see the plot cloud-free. A 30% scene cloud filter throws away ${share(H.idn_scene30_clear_rejected)} of those clear views.`}
          status="warning"
          statusText="Mask per plot, not per scene"
        />
        <Tile
          label="Over-crediting risk with conformal crediting"
          value={share(H.sat_conformal_over)}
          detail={`of ${H.n_projects} test projects over-credited (target 10%), satellite only, keeping ${share(H.sat_conformal_yield)} of the true stock (${share(H.gee_conformal_yield)} with the canopy height + GEDI map). The VM0047 deduction with 5–10 field plots over-credited ${range(H.vm0047_field_over_min * 100, H.vm0047_field_over_max * 100)}.`}
          status="good"
          statusText="Meets its target"
        />
      </div>
    </Section>
  );
}

/* ================================================================== accuracy */

const GEE_LABELS: Record<string, string> = {
  "baseline E2": "Sentinel-1/2 + Landsat + PALSAR (baseline)",
  "+ canopy height": "+ 1 m canopy height map",
  "+ GEDI": "+ GEDI lidar",
  "+ CCI": "+ ESA CCI biomass map",
  "+ canopy height + GEDI": "+ canopy height + GEDI (best)",
  "+ all new inputs": "+ all new inputs",
  "canopy height + GEDI only (no optical/radar)": "Canopy height + GEDI only",
  "height only, power law (1 m CHM)": "Canopy height only, power law",
  "product: GEDI L4A 1 km": "GEDI L4A biomass, as published",
  "product: GEDI L4B": "GEDI L4B biomass, as published",
  "product: ESA CCI": "ESA CCI biomass, as published",
  "product: Chloris (earlier E0)": "Chloris biomass, as published",
};
const LADDER_LABELS: Record<string, string> = {
  "optical only (S2 + Landsat)": "Optical only (Sentinel-2 + Landsat)",
  "radar only (S1 + PALSAR)": "Radar only (Sentinel-1 + PALSAR)",
  "optical + radar": "Optical + radar",
  "optical + radar + terrain (E2)": "Optical + radar + terrain",
  "E2 + Chloris product as feature": "+ Chloris map as an input",
  "E2 + Chloris + plot footprint": "+ Chloris + plot size",
  "Ensemble: mean(E2, Chloris)": "Average of model and Chloris",
  "E0 Chloris (reference)": "Chloris map alone",
};
type Subset = "All" | "Labriere2018" | "GEO-TREES" | "HCSA_Indonesia";
const subsetOpts: { value: Subset; label: string }[] = [
  { value: "All", label: "All plots" },
  { value: "Labriere2018", label: "Labrière 1 ha" },
  { value: "GEO-TREES", label: "GEO-TREES" },
  { value: "HCSA_Indonesia", label: "HCSA 0.05 ha" },
];
const DS3 = ["Labriere2018", "GEO-TREES", "HCSA_Indonesia"] as const;

function logDomain(vals: number[]): [number, number] {
  const steps = (e: number) => [1, 2, 5].map((m) => m * Math.pow(10, e));
  const mn = Math.min(...vals);
  const mx = Math.max(...vals);
  let lo = 1;
  for (let e = -1; e < 5; e++) for (const s of steps(e)) if (s <= mn) lo = s;
  let up = 10000;
  for (let e = 4; e >= -1; e--) for (const s of [...steps(e)].reverse()) if (s >= mx) up = s;
  return [lo, up];
}

export function Accuracy() {
  const [subset, setSubset] = useState<Subset>("Labriere2018");
  const [metric, setMetric] = useState<Metric>("acc");
  const [model, setModel] = useState<"g" | "b">("g");
  const [psModel, setPsModel] = useState<"best" | "base">("best");

  const gee = Object.keys(GEE_LABELS).map((k) => D.accuracy_gee.find((r) => r.model_name === k && r.subset === subset));
  const ladder = Object.keys(LADDER_LABELS).map((k) => D.ladder.find((r) => r.model_name === k && r.subset === subset));
  const fmt = (v: number) => `${v.toFixed(metric === "acc" ? 0 : 1)}%`;
  const accMax = metric === "acc" ? 100 : undefined;

  const scatter = D.scatter
    .filter((p) => p.y > 0 && p[model] > 0)
    .map((p) => ({ x: p.y, y: p[model], s: DS3.indexOf(p.d as (typeof DS3)[number]) }))
    .filter((p) => p.s >= 0);
  const domain = logDomain(D.scatter.flatMap((p) => [p.y, p.b, p.g]).filter((v) => v > 0));

  const psName = psModel === "best" ? "+ canopy height + GEDI" : "baseline E2";
  const ps = DS3.map((d) => D.project_scale.find((r) => r.model === psName && r.dataset === d)!);
  const boot = D.accuracy_gee_bootstrap;
  const seeds = D.seed_stability;
  const seedRange = (k: string) => {
    const v = seeds.map((s) => s[k]);
    return `${Math.min(...v).toFixed(1)}–${Math.max(...v).toFixed(1)}%`;
  };

  return (
    <Section
      id="accuracy"
      title="How close is the satellite to the field?"
      sub="Each plot is predicted by a LightGBM model trained only on the other regions (leave-one-region-out), so the score is what a new project would see. Pick a dataset; the 1 ha plots are the fair test of a satellite pixel stack."
    >
      <div className="controls">
        <Segmented label="Dataset" options={subsetOpts} value={subset} onChange={setSubset} />
        <Segmented label="Show as" options={metricOpts} value={metric} onChange={setMetric} />
      </div>
      <div className="grid two">
        <Card
          title="Which satellite inputs help"
          sub={`${DATASET_SHORT[subset]}, ${gee[0]?.n_samples ?? ""} plots. ${metric === "acc" ? "Accuracy = 100 − relative RMSE; higher is better." : "Relative RMSE; lower is better."}`}
          takeaway="Fine canopy structure gave the largest gain: a 1 m canopy height map plus GEDI lidar. On every dataset, published biomass maps used as they are do worse than the model with canopy height and GEDI."
          note={`Region-bootstrap 95% CI of the gain from canopy height + GEDI: ${boot
            .map((b) => `${DATASET_SHORT[b.subset] ?? b.subset} ${b.diff_points.toFixed(1)} (${b.ci_lo.toFixed(1)} to ${b.ci_hi.toFixed(1)})`)
            .join("; ")} points.`}
        >
          <HBarChart
            ariaLabel="Accuracy by satellite input set"
            categories={Object.values(GEE_LABELS)}
            series={[{ label: metric === "acc" ? "Accuracy" : "Error", values: gee.map((r) => (r ? asMetric(metric, r.rrmse_pct) : null)) }]}
            format={fmt}
            max={accMax}
            emphasize={[4]}
            tipExtra={(ci) => {
              const r = gee[ci];
              return r
                ? [
                    { label: "Relative RMSE", value: pct(r.rrmse_pct) },
                    { label: "Bias", value: pct(r.relative_bias_pct) },
                    { label: "R²", value: r.r2_score.toFixed(2) },
                    { label: "Plots", value: String(r.n_samples) },
                  ]
                : [];
            }}
          />
          <TableView
            rows={gee.filter((r): r is NonNullable<typeof r> => !!r)}
            cols={[
              { key: "m", label: "Inputs", get: (r) => GEE_LABELS[r.model_name] },
              { key: "n", label: "Plots", num: true, get: (r) => r.n_samples },
              { key: "e", label: "rRMSE", num: true, get: (r) => pct(r.rrmse_pct) },
              { key: "a", label: "Accuracy", num: true, get: (r) => pct(accuracy(r.rrmse_pct)) },
              { key: "b", label: "Bias", num: true, get: (r) => pct(r.relative_bias_pct) },
              { key: "r2", label: "R²", num: true, get: (r) => r.r2_score.toFixed(2) },
            ]}
          />
        </Card>
        <Card
          title="Satellite estimate against the field value"
          sub="Each dot is one plot, in Mg of above-ground biomass per hectare (log scale). On the dashed line the estimate equals the field value."
          takeaway="The 1 ha plots hug the line. The small Indonesian plots scatter widely: a 0.05 ha circle is smaller than the area a satellite pixel stack can resolve."
        >
          <div className="controls">
            <Segmented
              label="Model"
              options={[
                { value: "g", label: "+ canopy height + GEDI" },
                { value: "b", label: "Baseline sensors" },
              ]}
              value={model}
              onChange={setModel}
            />
          </div>
          <ScatterChart
            ariaLabel="Observed versus predicted biomass per plot"
            points={scatter}
            labels={DS3.map((d) => DATASET_SHORT[d])}
            domain={domain}
            xLabel="Field ground truth (Mg/ha)"
            yLabel="Satellite estimate (Mg/ha)"
            unit=" Mg/ha"
            height={440}
          />
        </Card>
        <Card
          title="Bigger areas are more accurate"
          sub={`Error of the average of n plots, and of a whole region's total estimated with no local field plots. ${metric === "acc" ? "Shown as accuracy." : "Shown as error."}`}
          takeaway="Plot errors partly cancel. With canopy height and GEDI, a project total outside Indonesia lands within about 7–9% of the field total without any local plot."
        >
          <div className="controls">
            <Segmented
              label="Model"
              options={[
                { value: "best", label: "+ canopy height + GEDI" },
                { value: "base", label: "Baseline sensors" },
              ]}
              value={psModel}
              onChange={setPsModel}
            />
          </div>
          <ColumnChart
            ariaLabel="Accuracy by aggregation scale"
            categories={DS3.map((d) => DATASET_SHORT[d].replace(", ", "\n"))}
            series={[
              { label: "One plot", values: ps.map((r) => asMetric(metric, r.agg_n1)) },
              { label: "Average of 10", values: ps.map((r) => asMetric(metric, r.agg_n10)) },
              { label: "Average of 20", values: ps.map((r) => asMetric(metric, r.agg_n20)) },
              { label: "Region total, no plots", values: ps.map((r) => asMetric(metric, r.kshot_k0)) },
            ]}
            format={fmt}
            yMax={metric === "acc" ? 100 : undefined}
          />
          <TableView
            rows={D.project_scale}
            cols={[
              { key: "m", label: "Model", get: (r) => (r.model === "baseline E2" ? "Baseline" : "+ CHM + GEDI") },
              { key: "d", label: "Dataset", get: (r) => DATASET_SHORT[r.dataset] },
              { key: "1", label: "1 plot", num: true, get: (r) => pct(r.agg_n1) },
              { key: "10", label: "Avg 10", num: true, get: (r) => pct(r.agg_n10) },
              { key: "20", label: "Avg 20", num: true, get: (r) => pct(r.agg_n20) },
              { key: "k0", label: "Total, 0 plots", num: true, get: (r) => pct(r.kshot_k0) },
              { key: "k10", label: "Total, 10 plots", num: true, get: (r) => pct(r.kshot_k10) },
              { key: "k20", label: "Total, 20 plots", num: true, get: (r) => pct(r.kshot_k20) },
            ]}
            summary="Show the numbers (errors, %)"
          />
        </Card>
        <Card
          title="Sensor ladder (earlier inputs)"
          sub={`${DATASET_SHORT[subset]}. The inputs available before the Earth Engine layers were added.`}
          takeaway="Combining optical and radar and adding terrain helps; adding the Chloris map helps a little more. None of these closes the gap that canopy height closes."
          note={`Stability: across 5 random seeds the error stayed within ${seedRange("All")} (all plots) and ${seedRange("Labriere2018")} (Labrière).`}
        >
          <HBarChart
            ariaLabel="Accuracy by sensor combination"
            categories={Object.values(LADDER_LABELS)}
            series={[{ label: metric === "acc" ? "Accuracy" : "Error", values: ladder.map((r) => (r ? asMetric(metric, r.rrmse_pct) : null)) }]}
            format={fmt}
            max={accMax}
            tipExtra={(ci) => {
              const r = ladder[ci];
              return r ? [{ label: "Relative RMSE", value: pct(r.rrmse_pct) }, { label: "R²", value: r.r2_score.toFixed(2) }] : [];
            }}
          />
        </Card>
      </div>
    </Section>
  );
}

/* ================================================================== ground truth */

export function GroundTruth() {
  const plots = D.gt_plots;
  const hw = [...plots.map((p) => p.rel_hw95_pct)].sort((a, b) => a - b);
  const medHw = hw[Math.floor(hw.length / 2)];
  const gp = D.gt_project;
  const blocks = D.gt_safe_blocks;
  const region = (r: string) => r.replace("IDN_", "").replace(/([a-z])([A-Z])/g, "$1 $2");
  return (
    <Section
      id="ground-truth"
      title="How certain is the ground truth itself?"
      sub="The field answer is also a model: tree diameter, height and wood density go through the Chave 2014 equation. We propagated their errors with a Monte Carlo (IPCC Approach 2) and scored each Indonesian province against SNI 7724, VM0047, AR-TOOL14, Gold Standard and VMD0017."
    >
      <div className="grid two">
        <Card
          title="Field value of each Indonesian plot, with its 95% range"
          sub={`${plots.length} HCSA plots. The line is the Monte Carlo 95% range from measurement and allometry error.`}
          takeaway={`A single small plot's own field value is uncertain by about ±${medHw.toFixed(0)}% (median). Plots with few trees are the least certain.`}
        >
          <RangeChart
            ariaLabel="Ground truth biomass per plot with 95% interval"
            items={plots.map((p) => ({
              v: p.agb_mc_median,
              lo: p.agb_lo95,
              hi: p.agb_hi95,
              title: region(p.region),
              extra: String(p.n_trees),
            }))}
            domain={logDomain(plots.flatMap((p) => [p.agb_lo95, p.agb_hi95]).filter((v) => v > 0))}
            yLabel="Above-ground biomass (Mg/ha, log scale)"
            unit=" Mg/ha"
          />
        </Card>
        <Card
          title="Province-level uncertainty against the standards"
          sub="90% uncertainty of the province mean (sampling + measurement). SNI 7724 asks for at most 20%; VM0047 deducts nothing below 10%."
          takeaway="Five of six provinces meet SNI 7724 with the plots they have. Jambi does not: it needs about 71 plots for ±10%."
        >
          <HBarChart
            ariaLabel="Province uncertainty"
            categories={gp.map((r) => region(r.region))}
            series={[{ label: "90% uncertainty", values: gp.map((r) => r.u90_total_pct) }]}
            format={(v) => `${v.toFixed(0)}%`}
            refs={[
              { value: 10, label: "10%" },
              { value: 20, label: "SNI 20%" },
            ]}
            tipExtra={(ci) => [
              { label: "Plots", value: String(gp[ci].n_plots) },
              { label: "Plots for ±10%", value: String(gp[ci].n_needed_10pct_90) },
              { label: "VM0047 deduction", value: pct(gp[ci].deduct_VM0047_pct) },
            ]}
          />
          <TableView
            rows={gp}
            cols={[
              { key: "r", label: "Province", get: (r) => region(r.region) },
              { key: "n", label: "Plots", num: true, get: (r) => r.n_plots },
              { key: "u", label: "U90", num: true, get: (r) => pct(r.u90_total_pct) },
              { key: "v", label: "VM0047", num: true, get: (r) => pct(r.deduct_VM0047_pct) },
              { key: "a", label: "AR-TOOL14", num: true, get: (r) => pct(r.deduct_ARTOOL14_pct) },
              { key: "g", label: "Gold Std.", num: true, get: (r) => pct(r.deduct_GS_pct) },
              { key: "d", label: "VMD0017", num: true, get: (r) => pct(r.deduct_VMD0017_pct) },
              { key: "s", label: "SNI ≤20%", get: (r) => (r.SNI7724_meets_20pct ? "meets" : "fails") },
              { key: "k", label: "Plots for ±10%", num: true, get: (r) => r.n_needed_10pct_90 },
            ]}
            summary="Show deductions under each standard"
          />
        </Card>
        <Card
          wide
          title="Growth from remeasured field plots (SAFE, Sabah)"
          sub="90% uncertainty of each block's yearly biomass change. Remeasuring the same trees correlates the two censuses (ρ); ignoring that inflates the uncertainty."
          takeaway={`Even the field answer for growth needs the census correlation ρ (VM0047 Eq. 28). Ignoring it, ${blocks.filter((b) => b.deduct_rho0_pct >= 100).length} of ${blocks.length} blocks lose their whole credit to the uncertainty deduction; with the measured ρ, ${blocks.filter((b) => b.deduct_rho_pct >= 100).length} still do.`}
        >
          <ColumnChart
            ariaLabel="Growth uncertainty by block"
            categories={blocks.map((b) => b.block)}
            series={[
              { label: "Ignoring ρ", values: blocks.map((b) => b.U90_rho0_pct) },
              { label: "With measured ρ", values: blocks.map((b) => b.U90_rho_pct) },
            ]}
            format={(v) => `${v.toFixed(0)}%`}
            refs={[{ value: 100, label: "100%: whole credit deducted" }]}
            height={240}
          />
          <TableView
            rows={blocks}
            cols={[
              { key: "b", label: "Block", get: (r) => r.block },
              { key: "n", label: "Plots", num: true, get: (r) => r.n_plots },
              { key: "g", label: "ΔAGB (Mg/ha/yr)", num: true, get: (r) => r.dagb_Mg_ha_yr.toFixed(2) },
              { key: "rho", label: "ρ", num: true, get: (r) => r.rho_t0_t1.toFixed(2) },
              { key: "u0", label: "U90, ρ=0", num: true, get: (r) => pct(r.U90_rho0_pct, 0) },
              { key: "u1", label: "U90, ρ", num: true, get: (r) => pct(r.U90_rho_pct, 0) },
              { key: "d0", label: "Deduct, ρ=0", num: true, get: (r) => pct(r.deduct_rho0_pct, 0) },
              { key: "d1", label: "Deduct, ρ", num: true, get: (r) => pct(r.deduct_rho_pct, 0) },
            ]}
          />
        </Card>
      </div>
    </Section>
  );
}

/* ================================================================== clouds */

const GROUPS = ["Indonesia (HCSA)", "Borneo, Sabah (SAFE)", "Asia, other", "Africa", "Americas"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const STRATEGY: Record<string, string> = {
  naive: "Leave gaps to the model",
  dropout: "Train with optical dropped",
  switch: "Switch to a radar-only model",
  impute: "Fill gaps with averages",
};

export function Clouds() {
  const [grp, setGrp] = useState<"Indonesia (HCSA)" | "all">("Indonesia (HCSA)");
  const scene = D.cloud_scene.filter((r) => r.group === grp);
  const rob = D.cloud_robustness.filter((r) => r.subset === "all");
  return (
    <Section
      id="clouds"
      title="Clouds"
      sub="Sentinel-2 scene classification read at each plot, every pass from 2021 to 2023 (97 locations). What matters is whether the plot itself is clear, not the whole 100 km scene."
    >
      <div className="grid two">
        <Card title="Share of passes that see the plot clear, by month" sub="Indonesian plots are clear least often from October to February.">
          <LineChart
            ariaLabel="Monthly clear-sky share by region"
            series={GROUPS.map((g) => ({ label: g, points: D.cloud_month.map((r) => ({ x: r.month, y: r[g] })) }))}
            xFormat={(v) => MONTHS[v - 1]}
            yFormat={(v) => `${(v * 100).toFixed(0)}%`}
            yMax={0.7}
          />
        </Card>
        <Card title="Clear views per region" sub="Share of all Sentinel-2 passes in 2021–2023 that saw the plot cloud-free.">
          <HBarChart
            ariaLabel="Clear-sky share by region"
            categories={GROUPS}
            series={[{ label: "Clear share", values: GROUPS.map((g) => D.cloud_group.find((r) => r.group === g)?.p_clear ?? null) }]}
            format={(v) => `${(v * 100).toFixed(0)}%`}
            max={0.5}
            tipExtra={(ci) => {
              const r = D.cloud_group.find((x) => x.group === GROUPS[ci]);
              return r
                ? [
                    { label: "Median gap between clear views", value: `${r.median_gap_days.toFixed(0)} days` },
                    { label: "Longest gap", value: `${r.max_gap_days.toFixed(0)} days` },
                    { label: "Clear view within 30 days", value: share(r.P_win30_emp) },
                    { label: "Locations", value: String(r.n_locations) },
                  ]
                : [];
            }}
          />
          <p className="takeaway">
            A clear view almost always arrives within 90 days, so a 90-day window per plot is enough; the problem is the scene filter, not the sky.
          </p>
        </Card>
        <Card
          title="What a scene-level cloud filter does"
          sub="Many pipelines keep a Sentinel-2 scene only if its whole-scene cloud cover is below a threshold. Checked against the plot's own pixels:"
          takeaway="At the common 30% threshold the filter throws away about two thirds of the clear views over Indonesian plots, and a third of the scenes it keeps are cloudy over the plot. Mask clouds per plot instead."
        >
          <div className="controls">
            <Segmented
              label="Region"
              options={[
                { value: "Indonesia (HCSA)", label: "Indonesia" },
                { value: "all", label: "All regions" },
              ]}
              value={grp}
              onChange={setGrp}
            />
          </div>
          <LineChart
            ariaLabel="Scene filter trade-off"
            series={[
              { label: "Clear plot views thrown away", points: scene.map((r) => ({ x: r.scene_threshold_pct, y: r.clear_plots_rejected })) },
              { label: "Kept scenes cloudy over the plot", points: scene.map((r) => ({ x: r.scene_threshold_pct, y: r.plot_cloudy_given_pass })) },
            ]}
            xFormat={(v) => `${v}%`}
            yFormat={(v) => `${(v * 100).toFixed(0)}%`}
            yMax={1}
            xLabel="Scene cloud-cover threshold"
          />
        </Card>
        <Card
          title="When optical data is missing"
          sub="We clouded out a growing share of plots on purpose and re-scored the satellite model (all plots)."
          takeaway="Filling missing optical values with averages is the one strategy that breaks. Leaving the gaps to the model, training with optical dropped, or switching to radar all stay near 48–50% error."
        >
          <LineChart
            ariaLabel="Error as more plots lose optical data"
            series={Object.keys(STRATEGY).map((s) => ({
              label: STRATEGY[s],
              points: rob.filter((r) => r.strategy === s).map((r) => ({ x: r.q, y: r.rrmse_pct })),
            }))}
            xFormat={(v) => `${(v * 100).toFixed(0)}%`}
            yFormat={(v) => `${v.toFixed(0)}%`}
            xLabel="Share of plots with optical data removed"
            yLabel="Relative RMSE"
            yMax={100}
          />
        </Card>
      </div>
    </Section>
  );
}

/* ================================================================== confidence */

const METHODS: Record<string, string> = {
  split: "Split conformal",
  mondrian: "Mondrian (per dataset)",
  normalized: "Normalized conformal",
  cqr: "Conformal quantile regression",
};
type CSub = "all" | "Labriere2018" | "GEO-TREES" | "HCSA_Indonesia" | "optical missing";

export function Confidence() {
  const [sub, setSub] = useState<CSub>("all");
  const [caSub, setCaSub] = useState<"all" | "HCSA_Indonesia" | "GEO-TREES" | "Labriere2018">("all");
  const rows = Object.keys(METHODS).map((m) => D.interval_methods.find((r) => r.method === m && r.subset === sub));
  const ca = (cond: string, method: string) => D.cloud_aware.find((r) => r.condition === cond && r.subset === caSub && r.method === method)?.coverage ?? null;
  const caAll = (cond: string, method: string) => D.cloud_aware.find((r) => r.condition === cond && r.subset === "all" && r.method === method)?.coverage ?? 0;
  const caBoot = D.bootstrap_ci.find((r) => r.metric.startsWith("coverage cloud-aware - plain"));
  return (
    <Section
      id="confidence"
      title="Confidence that means something"
      sub="A 90% interval should contain the field value 9 times out of 10. We checked that on plots the model never saw, instead of trusting a letter grade."
    >
      <div className="grid two">
        <Card title="Do 90% intervals hold 90% of the time?" sub="Share of plots whose field value fell inside the interval.">
          <div className="controls">
            <Segmented
              label="Plots"
              options={[
                { value: "all", label: "All" },
                { value: "Labriere2018", label: "Labrière" },
                { value: "GEO-TREES", label: "GEO-TREES" },
                { value: "HCSA_Indonesia", label: "HCSA" },
                { value: "optical missing", label: "Cloud-hit" },
              ]}
              value={sub}
              onChange={setSub}
            />
          </div>
          <HBarChart
            ariaLabel="Interval coverage by method"
            categories={Object.values(METHODS)}
            series={[{ label: "Coverage", values: rows.map((r) => r?.coverage ?? null) }]}
            format={(v) => `${(v * 100).toFixed(0)}%`}
            max={1}
            refs={[{ value: 0.9, label: "90% target" }]}
            tipExtra={(ci) => {
              const r = rows[ci];
              return r
                ? [
                    { label: "Plots", value: String(r.n) },
                    { label: "Median width (upper ÷ lower)", value: `${r.median_ratio_hi_lo.toFixed(1)}×` },
                  ]
                : [];
            }}
          />
          <p className="takeaway">
            Conformal quantile regression keeps close to 90% with the narrowest honest intervals overall. On the small Indonesian plots every method falls
            short, which is itself a warning sign for that data.
          </p>
        </Card>
        <Card title="Cloud-aware intervals" sub="Intervals calibrated with optical data randomly removed, compared with plain intervals, when every plot is clouded.">
          <div className="controls">
            <Segmented
              label="Plots"
              options={[
                { value: "all", label: "All" },
                { value: "Labriere2018", label: "Labrière" },
                { value: "GEO-TREES", label: "GEO-TREES" },
                { value: "HCSA_Indonesia", label: "HCSA" },
              ]}
              value={caSub}
              onChange={setCaSub}
            />
          </div>
          <ColumnChart
            ariaLabel="Coverage of plain and cloud-aware intervals"
            categories={["As observed", "Fully clouded"]}
            series={[
              { label: "Plain CQR", values: [ca("as observed", "plain"), ca("fully clouded", "plain")] },
              { label: "Cloud-aware CQR", values: [ca("as observed", "aware"), ca("fully clouded", "aware")] },
            ]}
            format={(v) => `${(v * 100).toFixed(0)}%`}
            yMax={1}
            refs={[{ value: 0.9, label: "90% target" }]}
            height={240}
          />
          <p className="takeaway">
            Across all plots under full cloud, plain CQR drops to {share(caAll("fully clouded", "plain"))} while the cloud-aware version holds{" "}
            {share(caAll("fully clouded", "aware"))}
            {caBoot ? ` (gain ${caBoot.value.toFixed(1)} points, 95% CI ${caBoot.ci_lo.toFixed(1)}–${caBoot.ci_hi.toFixed(1)})` : ""}. It does this by
            widening the interval, not by guessing. On the small HCSA plots neither reaches 90%.
          </p>
        </Card>
      </div>
    </Section>
  );
}

/* ================================================================== crediting */

const FRONTIER_RULES: Record<string, string> = {
  "satellite: conformal plain": "Conformal crediting",
  "satellite: conformal Mondrian + studentized": "Conformal, per plot size",
  "satellite: parametric two-component bound": "Parametric lower bound",
};
const BOUNDS: Record<string, string> = {
  "parametric, independent": "Parametric, independent errors",
  "parametric, two-component": "Parametric, two-component",
  conformal: "Conformal crediting",
};
const RULES_K: Record<string, string> = {
  "VM0047 (U-10%)": "VM0047 deduction",
  "conformal plain": "Conformal crediting",
  "design lower bound T - t SE": "Design lower bound",
};

export function Crediting() {
  const [fm, setFm] = useState<"over" | "yield">("over");
  const [setting, setSetting] = useState<"field only" | "ratio (satellite + k)">("ratio (satellite + k)");
  const [delta, setDelta] = useState<"0.1" | "0.2">("0.1");
  const fr = D.frontier;
  const cats: { k: number; design: string; label: string }[] = [
    { k: 5, design: "srs", label: "5 plots\nrandom" },
    { k: 10, design: "srs", label: "10 plots\nrandom" },
    { k: 5, design: "ranked", label: "5 plots\nranked" },
    { k: 10, design: "ranked", label: "10 plots\nranked" },
  ];
  const cc = (rule: string, k: number, design: string) =>
    D.conformal_crediting.find((r) => r.setting === setting && r.rule === rule && r.k === k && r.design === design && r.delta === 0.1)?.over_rate ?? null;
  const estimators = Array.from(new Set(D.crediting_robustness.map((r) => r.estimator)));
  const rob = (est: string, bound: string) => D.crediting_robustness.find((r) => r.estimator === est && r.bound === bound && r.delta === Number(delta));
  const vmSat = fr.find((r) => r.rule === "satellite: VM0047 deduction");
  const bankOther = D.bank_stress.find((r) => r.scheme === "other datasets only" && r.delta === 0.1);
  const bankSmall = D.bank_stress.find((r) => r.scheme === "same dataset, other regions" && r.delta === 0.1);
  return (
    <Section
      id="crediting"
      title="From intervals to credits"
      sub="Conformal crediting issues credit = estimate × exp(−q·r), where q is learned from how badly the satellite over-estimated other regions' projects. It guarantees that at most a share δ of projects is over-credited, and inflating the map does not change the credit. Tested on 31 projects."
    >
      <div className="grid two">
        <Card
          title="Does the over-crediting target hold?"
          sub="Satellite only, no field plot in the project. The target δ is the over-crediting share the issuer accepts."
          note={vmSat ? `For reference, the VM0047 deduction applied to the satellite-only uncertainty over-credits ${share(vmSat.over)} but keeps only ${share(vmSat.yield)} of the true stock.` : undefined}
        >
          <div className="controls">
            <Segmented
              label="Measure"
              options={[
                { value: "over", label: "Over-credited share" },
                { value: "yield", label: "Credit kept" },
              ]}
              value={fm}
              onChange={setFm}
            />
          </div>
          <LineChart
            ariaLabel="Crediting frontier"
            series={Object.keys(FRONTIER_RULES).map((k) => ({
              label: FRONTIER_RULES[k],
              points: fr.filter((r) => r.rule === k && r.delta != null).map((r) => ({ x: r.delta as number, y: fm === "over" ? r.over : r.yield })),
            }))}
            xFormat={(v) => `${+(v * 100).toFixed(1)}%`}
            xTicks={[0.05, 0.1, 0.2, 0.3, 0.4, 0.5]}
            yFormat={(v) => `${(v * 100).toFixed(0)}%`}
            yMax={fm === "over" ? 0.6 : 1.1}
            diagonal={fm === "over" ? "Realised = target" : undefined}
            xLabel="Target over-crediting share δ"
          />
          <p className="takeaway">
            Conformal crediting tracks its target (at δ = 10%: {share(H.sat_conformal_over, 1)} over-credited) while keeping{" "}
            {share(H.sat_conformal_yield)} of the true stock.
          </p>
        </Card>
        <Card
          title="With field plots: VM0047 against conformal crediting"
          sub="Share of projects over-credited at a 10% target. Random or ranked sampling of 5 or 10 plots."
          takeaway={`The VM0047 uncertainty deduction over-credits ${range(H.vm0047_field_over_min * 100, H.vm0047_field_over_max * 100)} of projects with 5–10 random plots and the satellite (ratio estimator). Conformal crediting stays at or below the 10% target in every design.`}
        >
          <div className="controls">
            <Segmented
              label="Estimator"
              options={[
                { value: "field only", label: "Field plots only" },
                { value: "ratio (satellite + k)", label: "Satellite + plots" },
              ]}
              value={setting}
              onChange={setSetting}
            />
          </div>
          <ColumnChart
            ariaLabel="Over-crediting with field plots"
            categories={cats.map((c) => c.label)}
            series={Object.keys(RULES_K).map((rule) => ({ label: RULES_K[rule], values: cats.map((c) => cc(rule, c.k, c.design)) }))}
            format={(v) => `${(v * 100).toFixed(0)}%`}
            yMax={0.4}
            refs={[{ value: 0.1, label: "10% target" }]}
            height={250}
          />
        </Card>
        <Card
          title="Does a worse or inflated map break it?"
          sub="Over-credited share across six maps, including the model's map inflated by 10% and 20% and the sharper canopy height + GEDI map."
          takeaway="Inflating the map by 10% or 20% does not change conformal over-crediting at all, so inflation does not buy credits. The parametric bounds drift upward as the map is inflated. The weakest map (Chloris) overshoots the 10% target by about 3 points."
        >
          <div className="controls">
            <Segmented
              label="Target"
              options={[
                { value: "0.1", label: "δ = 10%" },
                { value: "0.2", label: "δ = 20%" },
              ]}
              value={delta}
              onChange={setDelta}
            />
          </div>
          <HBarChart
            ariaLabel="Over-crediting by map and rule"
            categories={estimators}
            series={Object.keys(BOUNDS).map((b) => ({ label: BOUNDS[b], values: estimators.map((e) => rob(e, b)?.realised_over ?? null) }))}
            format={(v) => `${(v * 100).toFixed(0)}%`}
            max={0.5}
            refs={[{ value: Number(delta), label: `${Number(delta) * 100}% target` }]}
            tipExtra={(ci, si) => {
              const r = rob(estimators[ci], Object.keys(BOUNDS)[si]);
              return r
                ? [
                    { label: "95% CI", value: `${share(r.ci_lo)}–${share(r.ci_hi)}` },
                    { label: "Credit kept", value: share(r.yield) },
                  ]
                : [];
            }}
          />
        </Card>
        <Card title="How many calibration projects are needed?" sub="Over-crediting at a 10% and 20% target when calibrating on different pools of other projects.">
          <TableView
            rows={D.bank_stress}
            open
            summary="Calibration-bank stress test"
            cols={[
              { key: "s", label: "Calibration pool", get: (r) => r.scheme },
              { key: "d", label: "Target δ", num: true, get: (r) => share(r.delta) },
              { key: "o", label: "Over-credited", num: true, get: (r) => share(r.over, 1) },
              { key: "y", label: "Credit kept", num: true, get: (r) => share(r.yld) },
              { key: "n", label: "Min. projects", num: true, get: (r) => r.n_cal_min },
            ]}
          />
          <p className="takeaway">
            Calibrating on other regions of any dataset meets the target. Calibrating only on other datasets misses it at δ = 10% (
            {share(bankOther?.over ?? 0, 1)}). With as few as {bankSmall?.n_cal_min} calibration projects the credit kept collapses to{" "}
            {share(bankSmall?.yld ?? 0)}: at δ = 10% a bank needs at least 9 projects for the conformal quantile to exist.
          </p>
        </Card>
      </div>
    </Section>
  );
}

/* ================================================================== sequestration */

export function Sequestration() {
  const [level, setLevel] = useState<"block mean" | "plot">("block mean");
  const items: { label: string; mae: number | undefined; rmse: number | undefined }[] = [
    { label: "No change (zero growth)", ...pickSeq("gain", "no change") },
    { label: "Regional default growth rate", ...pickSeq("gain", "regional default rate") },
    { label: "Landsat gain–loss (dNBR)", ...pickSeq("gain", "gain-loss (d_nbr)") },
    { label: "Landsat gain–loss (dNDVI)", ...pickSeq("gain", "gain-loss (d_ndvi)") },
    { label: "Change model, Earth Engine inputs", ...pickSeq("gee", "change model with GEE inputs (LOBO)") },
    { label: "Change model, earlier inputs", ...pickSeq("imp", "S3_change_lobo") },
    { label: "Chloris map difference", ...pickSeq("imp", "S0_chloris") },
    { label: "Stock difference, consistent sensors", ...pickSeq("imp", "S2c_consistent") },
    { label: "Stock difference, LightGBM", ...pickSeq("imp", "S2_lgbm") },
  ];
  function pickSeq(src: "gain" | "gee" | "imp", key: string) {
    if (src === "gain") {
      const r = D.seq_gain_loss.find((x) => x.level === level && x.estimator === key);
      return { mae: r?.mae, rmse: r?.rmse };
    }
    if (src === "gee") {
      const r = D.seq_gee.find((x) => x.level === level && x.estimator === key);
      return { mae: r?.mae, rmse: r?.rmse };
    }
    const r = D.seq_improvement.find((x) => x.level === level && x.model_name === key);
    return { mae: r?.mae, rmse: r?.rmse };
  }
  return (
    <Section
      id="sequestration"
      title="Growth: the honest negative result"
      sub="Credits for regrowth need the change in carbon, not the stock. On 196 remeasured SAFE plots in Sabah (oil palm excluded), we asked whether any satellite method beats a simple regional default rate."
    >
      <div className="grid two">
        <Card
          title="Error of each growth estimate"
          sub="Mean absolute error of yearly above-ground biomass change, Mg/ha/yr; lower is better."
          takeaway="The regional default rate wins. At this plot size and with these sensors, information about growth comes from nearby field remeasurements, not from the pixels."
        >
          <div className="controls">
            <Segmented
              label="Level"
              options={[
                { value: "block mean", label: "Block average" },
                { value: "plot", label: "Single plot" },
              ]}
              value={level}
              onChange={setLevel}
            />
          </div>
          <HBarChart
            ariaLabel="Growth estimate error"
            categories={items.map((i) => i.label)}
            series={[{ label: "Mean absolute error", values: items.map((i) => i.mae ?? null) }]}
            format={(v) => v.toFixed(2)}
            emphasize={[1]}
            tipExtra={(ci) => (items[ci].rmse != null ? [{ label: "RMSE", value: (items[ci].rmse as number).toFixed(2) }] : [])}
          />
        </Card>
        <Card title="What this means for NusaCarbon" sub="Where satellites are useful today, and where they are not.">
          <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 14, color: "var(--text-secondary)", display: "grid", gap: 8 }}>
            <li>
              <b style={{ color: "var(--text-primary)" }}>Stock, project scale:</b> usable for screening and baselines outside small-plot settings, with
              conformal crediting to cap the over-crediting risk.
            </li>
            <li>
              <b style={{ color: "var(--text-primary)" }}>Stock, single small plot:</b> not usable; measure it.
            </li>
            <li>
              <b style={{ color: "var(--text-primary)" }}>Growth:</b> use a regional default rate or field remeasurement; satellites flag disturbance,
              not growth.
            </li>
            <li>
              <b style={{ color: "var(--text-primary)" }}>Next:</b> drone lidar above the canopy and a drone swarm under it, tested with the same blind
              protocol (see Method).
            </li>
          </ul>
        </Card>
      </div>
    </Section>
  );
}

/* ================================================================== method */

const TIERS = [
  {
    tier: "Under canopy",
    sensor: "Drone swarm with laser scanner (to be built)",
    role: "Measure tree diameter and position on 1 ha plots without a field crew; becomes the ground truth",
    evidence: "Piloted under-canopy UAV laser scanning: DBH error 0.6–0.9 cm (boreal); autonomous flight 3.8–22% by stand complexity",
    test: "H1: swarm DBH within 3% of tape on tropical stems, ≥90% of stems detected",
  },
  {
    tier: "Above canopy",
    sensor: "DJI Matrice 350 RTK + Zenmuse L2 lidar",
    role: "Canopy height over the whole project, converted to biomass with the under-canopy plots; repeat flights for growth",
    evidence: "L2: 4 cm vertical accuracy at 150 m, ~2.5 km² per flight (manufacturer); airborne lidar in Sabah: 13% at 1 ha",
    test: "H2: lidar biomass within 15% at 1 ha; H3: repeat-flight growth beats the default rate",
  },
  {
    tier: "Satellite",
    sensor: "Sentinel-1/2, Landsat, PALSAR, GEDI, 1 m canopy height",
    role: "Wall-to-wall stock, yearly disturbance monitoring, screening",
    evidence: `This study: ${pct(H.plot_1ha_best, 0)} error at 1 ha; ${range(H.project_k0_labriere, H.project_k0_geotrees)} on project totals outside Indonesia; no skill for growth`,
    test: "Gain when calibrated on drone lidar instead of sparse plots",
  },
];

export function Method() {
  return (
    <Section
      id="method"
      title="Method: a blind test with two isolated grids"
      sub="The field answer (right grid) is computed and sealed before the satellite side (left grid) makes its estimate. A hash-chained ledger records the order, so any change after the reveal is detectable."
    >
      <div className="flow">
        <div className="lane" style={{ ["--lane-color" as string]: "var(--series-3)" }}>
          <h4>Right grid: field ground truth</h4>
          <div className="who">476 plots: HCSA Indonesia, GEO-TREES, Labrière</div>
          <ol>
            <li>
              Tree diameter, height, wood density<small>nested plots by SNI 7724 / HCSA</small>
            </li>
            <li>
              Chave 2014 allometry → biomass<small>Monte Carlo error, IPCC Approach 2</small>
            </li>
            <li>
              × 0.47 carbon fraction × 44/12<small>tonnes CO₂e per hectare</small>
            </li>
            <li>
              Sealed<small>hash written to the ledger</small>
            </li>
          </ol>
        </div>
        <div className="lane">
          <h4>Blindness ledger</h4>
          <div className="who">hash-chained, append-only</div>
          <div className="ledger-steps">
            <div>
              <b>1. Seal</b>
              <span>field values hashed and locked</span>
            </div>
            <div className="arrow">↓</div>
            <div>
              <b>2. Commit</b>
              <span>satellite predictions hashed</span>
            </div>
            <div className="arrow">↓</div>
            <div>
              <b>3. Release</b>
              <span>field values unlocked</span>
            </div>
            <div className="arrow">↓</div>
            <div>
              <b>4. Reveal and score</b>
              <span>accuracy, intervals, credits</span>
            </div>
          </div>
        </div>
        <div className="lane" style={{ ["--lane-color" as string]: "var(--series-1)" }}>
          <h4>Left grid: satellite only</h4>
          <div className="who">sees plot location, size and date, nothing else</div>
          <ol>
            <li>
              Sentinel-1/2, Landsat, PALSAR<small>per-plot cloud mask, 90-day window</small>
            </li>
            <li>
              Google Earth Engine layers<small>1 m and 10 m canopy height, GEDI L4A/L2A/L4B, ESA CCI, Hansen</small>
            </li>
            <li>
              LightGBM, leave-one-region-out<small>log biomass, Duan smearing</small>
            </li>
            <li>
              Estimate + 90% interval<small>conformal quantile regression</small>
            </li>
          </ol>
        </div>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <h3>Roadmap: three measurement tiers</h3>
        <p className="sub">NusaCarbon&apos;s planned drones, and what each tier still has to prove. No drone data enter the results above.</p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Tier</th>
                <th>Sensor</th>
                <th>Role</th>
                <th>Published evidence</th>
                <th>To be shown</th>
              </tr>
            </thead>
            <tbody>
              {TIERS.map((t) => (
                <tr key={t.tier}>
                  {[t.tier, t.sensor, t.role, t.evidence, t.test].map((c, i) => (
                    <td key={i} style={{ whiteSpace: "normal", minWidth: i === 0 ? 90 : 160, verticalAlign: "top", fontWeight: i === 0 ? 600 : 400 }}>
                      {c}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Section>
  );
}
