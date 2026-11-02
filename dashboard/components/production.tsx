"use client";

import { HBarChart } from "./charts";
import { Section } from "./sections";
import { Card, Tile } from "./ui";
import { D } from "@/lib/data";

const P = D.production;
const p0 = (v: number) => `${v.toFixed(0)}%`;
const p1 = (v: number) => `${v.toFixed(1)}%`;
const FIX = Object.fromEntries(P.fixes.map((f) => [f.key, f]));
const DZ = Object.fromEntries(P.danum.map((d) => [d.estimate, d]));

const FIX_ROWS: [string, string][] = [
  ["paper", "Map of the paper (E2 + canopy height + GEDI)"],
  ["map_pct", "Embeddings + canopy height + GEDI"],
  ["map_mu_realm_pct", "… × realm bias correction (the estimate)"],
  ["local3_pct", "… + 3 local plots, plain ratio"],
  ["local3_shrunk_realm_pct", "… + 3 local plots, shrunk"],
  ["local10_shrunk_realm_pct", "… + 10 local plots, shrunk"],
];
const HEIGHT_NAMES: Record<string, string> = {
  "Jucker 2018 Eq 10": "Jucker 2018 (Sabah lidar)",
  "Coomes 2017": "Coomes 2017 (Sepilok lidar)",
  "app as coded": "NusaCarbon formula, as coded",
  "app read as carbon": "NusaCarbon formula, read as carbon",
};

export function Production() {
  const est = FIX.map_mu_realm_pct;
  const cr = FIX.credit_region_q;
  return (
    <Section
      id="production"
      title="Toward production: fixes, then an unseen test"
      sub="Each limit found above was attacked after the reveal (so these are exploratory) on the same 1,000 simulated projects. The resulting method was then frozen and tested blind on 35 plots from Danum, Sabah, that no model had seen."
    >
      <div className="grid tiles" style={{ marginBottom: 16 }}>
        <Tile
          label="Projects within ±25% of the field"
          value={p1(est.within_25pct_all)}
          detail={`was ${p0(FIX.paper.within_25pct_all)} for the paper's map; Indonesian projects ${p0(FIX.paper.within_25pct_hcsa)} → ${p0(est.within_25pct_hcsa!)}`}
          status="good"
          statusText="Embeddings + realm bias correction"
          meter={est.within_25pct_all}
        />
        <Tile
          label="Unseen test: 35 Danum plots"
          value={p0(DZ.estimate.total_pct_of_field)}
          detail={`of the field carbon, frozen method; the map alone found ${p0(DZ.map.total_pct_of_field)}. ${p0(DZ.estimate.draws10_within_25pct)} of 10-plot projects within ±25%`}
          status="good"
          statusText="Blind: sealed, committed, revealed"
          meter={DZ.estimate.total_pct_of_field}
        />
        <Tile
          label="Credit above the field amount"
          value={p1(cr.above_field_pct_all!)}
          detail={`of projects, target 10% (was ${p1(FIX.credit_project_q.above_field_pct_all!)}); median credit ${p0(cr.median_pct_all)} of the field carbon. On Danum: ${p0(DZ.credit.total_pct_of_field)}, never above`}
          status="good"
          statusText="One score per region"
          meter={cr.median_pct_all}
        />
        <Tile
          label="Tree count on the 2026 canopy map"
          value={p0(P.e4.v2.pct)}
          detail={`of the field carbon (was ${p0(P.e4.v1.pct)}); ${P.e4.v2.trees_ha.toFixed(0)} trees per hectare instead of ${P.e4.v1.trees_ha.toFixed(0)}, against about 700 stems in the field`}
          status="warning"
          statusText="Still blind to the understorey"
          meter={P.e4.v2.pct}
        />
      </div>
      <div className="grid two">
        <Card
          title="What each fix does to a project"
          sub="Share of the 1,000 simulated projects whose carbon comes within ±25% of the field amount, for all projects and for the Indonesian (HCSA) ones."
          takeaway={`Satellite embeddings and a bias learnt from the other regions of the same realm do most of the work. A few small local plots make it worse unless they are weighted by their noise.`}
        >
          <HBarChart
            ariaLabel="Share of projects within 25 percent of the field carbon for each fix"
            categories={FIX_ROWS.map(([, l]) => l)}
            series={[
              { label: "All projects", values: FIX_ROWS.map(([k]) => FIX[k].within_25pct_all) },
              { label: "Indonesian projects", values: FIX_ROWS.map(([k]) => FIX[k].within_25pct_hcsa) },
            ]}
            colors={["var(--series-1)", "var(--series-3)"]}
            format={p0}
            max={100}
          />
        </Card>
        <Card
          title="Unseen test: Danum, Sabah"
          sub="35 plots of 0.28 ha measured in 2020 (4,201 live stems, mean 366 Mg/ha), sealed before the frozen method read them. Total carbon found, % of the field amount."
          takeaway={`In this tall forest the map saturates. The bias learnt in Sumatra, Kalimantan and Papua carried to Sabah, and the credit stayed below the field.`}
        >
          <HBarChart
            ariaLabel="Carbon found on the unseen Danum plots"
            categories={["Map alone", "Estimate: map × realm bias", "Credit: map × safety factor"]}
            series={[{ label: "% of field", values: [DZ.map.total_pct_of_field, DZ.estimate.total_pct_of_field, DZ.credit.total_pct_of_field] }]}
            colors={["var(--series-1)"]}
            format={p0}
            refs={[{ value: 100, label: "Field = 100%" }]}
            max={110}
          />
        </Card>
        <Card
          title="Published height equations, no training"
          sub="Carbon from canopy height alone, applied unchanged, as % of the field total over 475 plots; Danum on the 2026 map, computed after the reveal."
          takeaway="On the 2026 map a published Sabah lidar equation lands near the field total with no training, but it scatters project to project. The NusaCarbon formula matches no published equation; its curve behaves like a carbon model that is then multiplied by 0.47 again."
        >
          <HBarChart
            ariaLabel="Carbon found by published canopy height equations"
            categories={P.heights.map((h) => HEIGHT_NAMES[h.name] ?? h.name)}
            series={[
              { label: "2024 map", values: P.heights.map((h) => h.v1) },
              { label: "2026 map", values: P.heights.map((h) => h.v2) },
              { label: "Danum, 2026 map", values: P.heights.map((h) => h.danum) },
            ]}
            colors={["var(--series-2)", "var(--series-1)", "var(--series-4)"]}
            format={p0}
            refs={[{ value: 100, label: "Field = 100%" }]}
          />
        </Card>
        <Card title="The frozen method" sub="What was committed before the Danum seal was opened, and what a platform would run for a drawn polygon.">
          <ol className="steps">
            <li>
              <b>Features</b> from Earth Engine only, per 1 ha cell: the AlphaEarth embedding of the year, canopy height (Meta, ETH), GEDI biomass within 500
              m and 1 km.
            </li>
            <li>
              <b>Map</b>: LightGBM on log biomass trained on all field plots ({P.rrmse_prod.toFixed(1)}% plot error, was {P.rrmse_paper.toFixed(1)}%; gain{" "}
              {P.rrmse_gain.toFixed(1)} points, 95% {P.rrmse_gain_lo.toFixed(1)} to {P.rrmse_gain_hi.toFixed(1)}).
            </li>
            <li>
              <b>Estimate</b>: map × e<sup>−μ</sup>, μ the mean bias of the other regions of the same realm.
            </li>
            <li>
              <b>Credit</b>: map × e<sup>−q</sup>, q the conformal quantile of one score per field-verified region (δ = 0.1).
            </li>
            <li>
              <b>Growth</b>: a regional default (IPCC 2019: 0.7 t/ha/yr primary, 2.7 older secondary, 3.4 young secondary, Asian rainforest), not a
              satellite difference.
            </li>
            <li>
              <b>Field plots</b>, if any, of 0.25–1 ha, shrunk toward the realm prior.
            </li>
          </ol>
        </Card>
      </div>
    </Section>
  );
}
