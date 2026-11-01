"use client";

import { Fragment, useEffect, useMemo, useRef, useState, type PointerEvent as RPointerEvent } from "react";
import { ColumnChart, HBarChart, Legend, Segmented } from "./charts";
import { Section } from "./sections";
import { Card, TableView, Tile } from "./ui";
import { D, DATASET_SHORT, type ChmExample } from "@/lib/data";

/* Colour follows the estimate everywhere on the page. */
const C = {
  map: "var(--series-1)",
  e4: "var(--series-2)",
  e4s: "var(--series-5)",
  credit: "var(--series-4)",
  stems: "var(--axis-text)",
  carbon: "var(--series-3)",
};
const T = D.trees_summary;
const t0 = (v: number) => Math.round(v).toLocaleString("en-US");
const p0 = (v: number) => `${v.toFixed(0)}%`;
const SIM = Object.fromEntries(D.simulations_summary.map((r) => [r.estimate, r]));
const site = (s: string) => s.replace("Labriere", "Labrière");

/* ================================================================== how it works */

function StemList() {
  const rows = D.stem_example;
  const total = rows.reduce((a, r) => a + r.agb_Mg_ha, 0);
  return (
    <>
      <TableView
        open
        summary={`The stem list of plot ${rows[0].plot_id.replace("HCSA_", "").replace(/_/g, " ")}: ${rows.length} measured stems`}
        rows={rows}
        cols={[
          { key: "d", label: "Diameter (cm)", num: true, get: (r) => r.dbh_cm.toFixed(1) },
          { key: "h", label: "Height (m)", num: true, get: (r) => r.height_m.toFixed(1) },
          { key: "l", label: "Local name", get: (r) => r.local_name },
          { key: "s", label: "Species", get: (r) => <i>{r.scientific_name}</i> },
          { key: "f", label: "Family", get: (r) => r.family },
          { key: "w", label: "Wood density", num: true, get: (r) => r.wood_density.toFixed(2) },
          { key: "a", label: "Counted in", num: true, get: (r) => `${r.plot_area_ha} ha` },
          { key: "k", label: "Biomass (kg)", num: true, get: (r) => t0(r.agb_kg) },
          { key: "m", label: "Mg/ha", num: true, get: (r) => r.agb_Mg_ha.toFixed(1) },
        ]}
      />
      <p className="note">
        Sum: {total.toFixed(1)} Mg of above-ground biomass per hectare, × 0.47 × 44/12 = {t0(total * 0.47 * (44 / 12))} t CO₂e per hectare. Stems under
        15 cm are counted in the inner 0.01 ha circle, so each stands for 100 per hectare; larger stems stand for 20.
      </p>
    </>
  );
}

function NdviCalc() {
  const [nir, setNir] = useState(0.3);
  const [red, setRed] = useState(0.04);
  const ndvi = (nir - red) / (nir + red || 1);
  const read = ndvi >= 0.6 ? "dense green canopy" : ndvi >= 0.2 ? "sparse or mixed vegetation" : "bare soil, rock, water or cloud";
  return (
    <div className="calc" aria-label="NDVI calculator">
      <label>
        Near-infrared (B8)
        <input type="range" min={0} max={0.6} step={0.01} value={nir} onChange={(e) => setNir(+e.target.value)} />
        <output>{nir.toFixed(2)}</output>
      </label>
      <label>
        Red (B4)
        <input type="range" min={0} max={0.3} step={0.01} value={red} onChange={(e) => setRed(+e.target.value)} />
        <output>{red.toFixed(2)}</output>
      </label>
      <div>
        NDVI = ({nir.toFixed(2)} − {red.toFixed(2)}) / ({nir.toFixed(2)} + {red.toFixed(2)}) = <b>{ndvi.toFixed(2)}</b>, a rough guide says {read}.
      </div>
    </div>
  );
}

function useThemeKey() {
  const [k, setK] = useState(0);
  useEffect(() => {
    const bump = () => setK((v) => v + 1);
    const mo = new MutationObserver(bump);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", bump);
    return () => {
      mo.disconnect();
      mq.removeEventListener("change", bump);
    };
  }, []);
  return k;
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.trim().replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

const H_MAX = 45;

function CanopyMap({ ex }: { ex: ChmExample }) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [px, setPx] = useState(420);
  const [hover, setHover] = useState<{ i: number; x: number; y: number } | null>(null);
  const theme = useThemeKey();
  const n = ex.size;

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver((e) => setPx(Math.max(220, Math.min(460, Math.floor(e[0].contentRect.width)))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const cv = canvas.current;
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(px * dpr);
    cv.height = Math.round(px * dpr);
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const css = getComputedStyle(document.documentElement);
    const lo = hexToRgb(css.getPropertyValue("--seq-lo"));
    const hi = hexToRgb(css.getPropertyValue("--seq-hi"));
    const img = ctx.createImageData(n, n);
    for (let i = 0; i < n * n; i++) {
      const h = Math.min(H_MAX, ex.heights.charCodeAt(i) - 35);
      const t = h / H_MAX;
      img.data[4 * i] = lo[0] + (hi[0] - lo[0]) * t;
      img.data[4 * i + 1] = lo[1] + (hi[1] - lo[1]) * t;
      img.data[4 * i + 2] = lo[2] + (hi[2] - lo[2]) * t;
      img.data[4 * i + 3] = 255;
    }
    const off = document.createElement("canvas");
    off.width = n;
    off.height = n;
    off.getContext("2d")?.putImageData(img, 0, 0);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(off, 0, 0, cv.width, cv.height);
    const s = cv.width / n;
    // plot footprint
    ctx.setLineDash([6 * dpr, 4 * dpr]);
    ctx.lineWidth = 1.5 * dpr;
    ctx.strokeStyle = css.getPropertyValue("--ref").trim();
    ctx.beginPath();
    ctx.arc((n / 2) * s, (n / 2) * s, ex.footprint_r_m * s, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
    // crowns and tops, with a surface ring so they read on any height
    const surface = css.getPropertyValue("--surface").trim();
    const mark = css.getPropertyValue("--series-2").trim();
    ex.trees.forEach(([r, c, , cd], i) => {
      const x = (c + 0.5) * s;
      const y = (r + 0.5) * s;
      ctx.lineWidth = 1.5 * dpr;
      ctx.strokeStyle = mark;
      ctx.globalAlpha = hover?.i === i ? 1 : 0.7;
      ctx.beginPath();
      ctx.arc(x, y, (cd / 2) * s, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(x, y, (hover?.i === i ? 6 : 4.5) * dpr, 0, Math.PI * 2);
      ctx.fillStyle = mark;
      ctx.fill();
      ctx.lineWidth = 2 * dpr;
      ctx.strokeStyle = surface;
      ctx.stroke();
    });
  }, [ex, px, theme, hover, n]);

  const onMove = (e: RPointerEvent<HTMLCanvasElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const mx = e.clientX - box.left;
    const my = e.clientY - box.top;
    const s = px / n;
    let best = -1;
    let bd = 14 * 14;
    ex.trees.forEach(([r, c], i) => {
      const d = ((c + 0.5) * s - mx) ** 2 + ((r + 0.5) * s - my) ** 2;
      if (d < bd) {
        bd = d;
        best = i;
      }
    });
    setHover(best >= 0 ? { i: best, x: mx, y: my } : null);
  };
  const tr = hover ? ex.trees[hover.i] : null;
  const agb = tr ? 0.0673 * Math.pow(ex.rho_default * tr[4] * tr[4] * tr[2], 0.976) : 0;

  return (
    <div className="canopy-fig" ref={wrap}>
      <canvas
        ref={canvas}
        style={{ width: px, height: px }}
        role="img"
        aria-label={`1 m canopy height around plot ${ex.plot_id}, ${ex.trees.length} trees detected inside the plot`}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      />
      {tr && hover && (
        <div className="tip" style={{ left: Math.min(hover.x + 14, px - 210), top: Math.max(0, hover.y - 10) }} role="status">
          <div className="t">Tree {hover.i + 1} found from space</div>
          <div className="r">
            <span>Height (top)</span>
            <b>{tr[2].toFixed(0)} m</b>
          </div>
          <div className="r">
            <span>Crown diameter</span>
            <b>{tr[3].toFixed(1)} m</b>
          </div>
          <div className="r">
            <span>Stem diameter (Jucker)</span>
            <b>{tr[4].toFixed(0)} cm</b>
          </div>
          <div className="r">
            <span>Biomass, ρ {ex.rho_default.toFixed(2)}</span>
            <b>{t0(agb)} kg</b>
          </div>
        </div>
      )}
      <div className="colorbar">
        <span>0 m</span>
        <span className="bar" aria-hidden />
        <span>{H_MAX}+ m canopy height</span>
      </div>
      <Legend
        items={[
          { label: "Tree top and crown found by E4", color: C.e4 },
          { label: "Plot boundary", kind: "ref" },
        ]}
      />
    </div>
  );
}

function exampleText(ex: ChmExample) {
  const n = ex.size;
  const c = n / 2;
  let sum = 0;
  let cnt = 0;
  for (let r = 0; r < n; r++)
    for (let k = 0; k < n; k++)
      if ((r + 0.5 - c) ** 2 + (k + 0.5 - c) ** 2 <= ex.footprint_r_m ** 2) {
        sum += ex.heights.charCodeAt(r * n + k) - 35;
        cnt++;
      }
  const meanH = sum / Math.max(1, cnt);
  if (ex.trees.length === 0 && meanH < 2)
    return `The map reads under 2 m over the whole plot, although the field measured ${t0(ex.field_tco2e_ha)} t CO₂e per hectare of forest. Here the map, not the forest, is empty; this happened on ${D.no_canopy_plots} of the 475 plots.`;
  if (ex.trees.length === 0)
    return `The plot circle is ${Math.round(2 * ex.footprint_r_m)} m across. The map shows canopy ${meanH.toFixed(0)} m tall on average, but no tree top falls inside the circle, so E4 counts nothing.${ex.field_stems_ha != null ? ` The field crew counted ${t0(ex.field_stems_ha)} stems per hectare here.` : ""}`;
  return `The map finds ${ex.trees.length} crowns: the large trees whose tops reach the canopy. The trees under them never appear on a map of the canopy surface; in the HCSA stem lists the median plot has ${t0(T.stems_ha_median)} stems per hectare.`;
}

export function HowItWorks() {
  const [exId, setExId] = useState(D.chm_examples[0].plot_id);
  const ex = D.chm_examples.find((e) => e.plot_id === exId) ?? D.chm_examples[0];
  const nd = D.ndvi;
  return (
    <Section
      id="how"
      title="How each side gets its number"
      sub="Coordinates only say where a plot is. The field side measures the trees standing there; the satellite side only has pixels over the same spot. Both end with the same factors: × 0.47 for carbon and × 44/12 for CO₂."
    >
      <div className="grid two">
        <Card
          title="Field (right grid): the trees are the data"
          sub="What a ground-truth plot contains, step by step, as done for the HCSA plots."
          takeaway="The coordinates are only the address. The ground truth is the stem list: every tree's diameter, height and species, and the wood density that the species sets."
        >
          <ol className="steps">
            <li>
              <b>Find the plot.</b> The crew walks to the coordinates and lays out a 0.05 ha circle (12.6 m radius), with an inner 0.01 ha circle for small
              stems.
            </li>
            <li>
              <b>Measure every stem.</b> Each tree of 5 cm or more is tagged; its diameter is taped at 1.3 m and its height taken with a clinometer.
            </li>
            <li>
              <b>Name the species.</b> The local name is resolved by a botanist to species, genus and family.
            </li>
            <li>
              <b>Look up wood density.</b> The species sets ρ, the dry mass per volume of its wood. Two trees of the same size can differ by more than half
              in mass.
            </li>
            <li>
              <b>Apply the formula</b> to each tree, add them up per hectare, then × 0.47 × 44/12.
            </li>
          </ol>
          <div className="formula">AGB per tree (kg) = 0.0673 × (ρ × D² × H)^0.976</div>
          <StemList />
        </Card>
        <Card
          title="Satellite (left grid): only pixels at the coordinates"
          sub="The satellite never sees the stem list. It sees light and radar echoes over the plot."
          takeaway={`Greenness saturates: median NDVI is ${nd[0].median.toFixed(2)} below 100 Mg/ha and ${nd[nd.length - 1].median.toFixed(2)} above 300. Above 150 Mg/ha its rank correlation with biomass is ${nd[0].spearman_agb150.toFixed(2)}, so the model leans on radar, canopy height and GEDI.`}
        >
          <ol className="steps">
            <li>
              <b>Find images</b> from Sentinel-2, Landsat, Sentinel-1 and PALSAR within 90 days of the field date.
            </li>
            <li>
              <b>Drop cloudy ones:</b> keep a scene only if every pixel over the plot is clear.
            </li>
            <li>
              <b>Measure greenness and structure.</b> Optical bands give indices such as NDVI; radar gives backscatter; Earth Engine adds a 1 m canopy height
              map and GEDI lidar.
            </li>
            <li>
              <b>Learn biomass</b> with a model trained on the plots of other regions only.
            </li>
            <li>
              <b>Same factors:</b> × 0.47 × 44/12, exactly as the field side.
            </li>
          </ol>
          <div className="formula">NDVI = (NIR − Red) / (NIR + Red)</div>
          <p className="sub" style={{ margin: 0 }}>
            Chlorophyll absorbs red light and leaves reflect near-infrared, so green canopy scores high. Try it:
          </p>
          <NdviCalc />
          <ColumnChart
            ariaLabel="Median NDVI by field biomass class"
            categories={nd.map((r) => `${r.agb_class.replace("-", "–").replace(">=", "≥")}\nMg/ha`)}
            series={[{ label: "Median NDVI", values: nd.map((r) => r.median) }]}
            colors={[C.carbon]}
            format={(v) => v.toFixed(2)}
            yMax={1}
            height={200}
            yLabel={`Median NDVI by field biomass (${nd.reduce((a, r) => a + r.n, 0)} plots with a clear view)`}
          />
        </Card>
        <Card
          wide
          title="Counting trees from space (E4)"
          sub="Count the trees on the 1 m canopy height map, give each a size, then apply the same field formula. Each example is the plot with the median field biomass of its dataset, not a hand-picked one. Hover a tree."
        >
          <div className="controls">
            <Segmented
              label="Example plot"
              options={D.chm_examples.map((e) => ({ value: e.plot_id, label: DATASET_SHORT[e.dataset] }))}
              value={exId}
              onChange={setExId}
            />
          </div>
          <div className="canopy">
            <CanopyMap ex={ex} />
            <div>
              <dl className="kv">
                <dt>Field stems per hectare</dt>
                <dd>{ex.field_stems_ha == null ? "list not published" : t0(ex.field_stems_ha)}</dd>
                <dt>Trees found from space, per hectare</dt>
                <dd>{t0(ex.sat_trees_ha)}</dd>
                <dt>Field carbon (t CO₂e/ha)</dt>
                <dd>{t0(ex.field_tco2e_ha)}</dd>
                <dt>E4: count + formula</dt>
                <dd>
                  {t0(ex.e4_tco2e_ha)} ({p0((100 * ex.e4_tco2e_ha) / ex.field_tco2e_ha)})
                </dd>
                <dt>Map: E2 + canopy height + GEDI</dt>
                <dd>
                  {t0(ex.map_tco2e_ha)} ({p0((100 * ex.map_tco2e_ha) / ex.field_tco2e_ha)})
                </dd>
              </dl>
              <p className="takeaway">{exampleText(ex)}</p>
              <ol className="steps" style={{ fontSize: 13 }}>
                <li>Smooth the height map by 1 m (it stores whole metres).</li>
                <li>Tree tops: local highest points of 5 m or more, in a window of 0.06 × height + 0.5 m.</li>
                <li>Crowns: grow from each top while the canopy stays above half its height.</li>
                <li>
                  Stem diameter from height and crown: D = a × (H × crown)<sup>b</sup> (Jucker et al. 2017).
                </li>
                <li>Wood density: the regional default (no species from space), ρ = {ex.rho_default.toFixed(3)}.</li>
                <li>The field formula per tree, summed over the plot, × 0.47 × 44/12.</li>
              </ol>
            </div>
          </div>
        </Card>
      </div>
    </Section>
  );
}

/* ================================================================== trees and wood */

const TB_EST = [
  ["map: E2 + canopy height + GEDI", "Map: E2 + canopy height + GEDI", C.map],
  ["E4 count + formula (as is)", "E4: count + formula", C.e4],
  ["E4 scaled on other regions", "E4 scaled on other regions", C.e4s],
] as const;
type TbSubset = "All" | "Labriere2018" | "GEO-TREES" | "HCSA_Indonesia";

export function Trees() {
  const [metric, setMetric] = useState<"total" | "within">("total");
  const subsets: TbSubset[] = ["All", "Labriere2018", "GEO-TREES", "HCSA_Indonesia"];
  const tb = (s: string, e: string) => D.tree_benchmark.find((r) => r.subset === s && r.estimator === e)!;
  const wc = D.wood_classes;
  const dc = D.diameter_classes;
  const wcLabel = (c: string) => c.charAt(0).toUpperCase() + c.slice(1).replace("(< 0.5)", "(< 0.5 g/cm³)").replace("(>= 0.7)", "(≥ 0.7)").replace("-", "–");
  const unsm = tb("All", "E4 unsmoothed (sensitivity)");
  return (
    <Section
      id="trees"
      title="What the field counts, and what the satellite sees"
      sub={`From the ${t0(T.hcsa_plots)} HCSA stem lists (${t0(T.hcsa_records)} stems of ${t0(T.hcsa_species)} species in ${t0(T.hcsa_families)} families) and the 1 m canopy height map over all 475 plots.`}
    >
      <div className="grid two">
        <Card
          title="Most stems are small; most carbon is in big trees"
          sub="HCSA stems by diameter: share of all stems and share of all carbon."
          takeaway={`Stems of 5–15 cm are ${p0(dc[0].stem_share_pct)} of the count but ${p0(dc[0].carbon_share_pct)} of the carbon. The ${p0(dc[2].stem_share_pct + dc[3].stem_share_pct)} of stems of 30 cm or more hold ${p0(dc[2].carbon_share_pct + dc[3].carbon_share_pct)}. Finding the big trees matters more than counting every stem.`}
        >
          <HBarChart
            ariaLabel="Share of stems and of carbon by stem diameter"
            categories={dc.map((r) => r.diameter.replace("-", "–").replace(">=", "≥"))}
            series={[
              { label: "Share of stems", values: dc.map((r) => r.stem_share_pct) },
              { label: "Share of carbon", values: dc.map((r) => r.carbon_share_pct) },
            ]}
            colors={[C.stems, C.carbon]}
            format={p0}
            max={100}
          />
          <TableView
            rows={dc}
            cols={[
              { key: "d", label: "Diameter", get: (r) => r.diameter },
              { key: "n", label: "Stems per ha", num: true, get: (r) => t0(r.stems_ha) },
              { key: "s", label: "Stems", num: true, get: (r) => `${r.stem_share_pct.toFixed(1)}%` },
              { key: "c", label: "Carbon", num: true, get: (r) => `${r.carbon_share_pct.toFixed(1)}%` },
            ]}
          />
        </Card>
        <Card
          title="Light, medium and heavy wood"
          sub="HCSA stems grouped by the wood density of their species (g/cm³)."
          takeaway={`The stems average ρ = ${T.wd_stem_mean.toFixed(3)}; a satellite must assume the regional default ${T.wd_default.toFixed(3)}. With the default, a plot keeps ${p0(T.wd_default_total_pct)} of its carbon in total and ${p0(T.wd_default_plot_p10_pct)}–${p0(T.wd_default_plot_p90_pct)} plot by plot: species alone moves a plot by a fifth.`}
        >
          <HBarChart
            ariaLabel="Share of stems and of carbon by wood density class"
            categories={wc.map((r) => wcLabel(r.class))}
            series={[
              { label: "Share of stems", values: wc.map((r) => r.stem_share_pct) },
              { label: "Share of carbon", values: wc.map((r) => r.carbon_share_pct) },
            ]}
            colors={[C.stems, C.carbon]}
            format={p0}
            max={100}
          />
          <TableView
            rows={wc}
            cols={[
              { key: "c", label: "Class", get: (r) => wcLabel(r.class) },
              { key: "s", label: "Species", num: true, get: (r) => r.species },
              { key: "w", label: "Mean ρ", num: true, get: (r) => r.mean_wd.toFixed(2) },
              { key: "f", label: "Leading families (by carbon)", get: (r) => r.top_families.replace(/; /g, ", ") },
            ]}
          />
        </Card>
        <Card
          title="Trees counted per hectare (HCSA plots)"
          sub="Median over the 148 HCSA plots: stems on the field crew's list against tree tops found on the 1 m canopy height map."
          takeaway={`The satellite found ${p0(T.count_sat_share_of_stems_pct)} of the stems and ${p0(T.count_sat_share_of_d15_stems_pct)} of those of 15 cm or more, with a rank correlation of ${T.count_count_corr_spearman.toFixed(2)} against the field count. Without smoothing, the same map gives ${t0(T.count_sat_trees_ha_unsmoothed_median)}: the count is a processing choice, not a measurement.`}
        >
          <HBarChart
            ariaLabel="Trees per hectare counted in the field and from space"
            categories={["Field crew, stems ≥ 5 cm", "Field crew, stems ≥ 15 cm", "Satellite E4, as run", "Satellite E4, no smoothing"]}
            series={[{ label: "Per hectare", values: [T.count_field_stems_ha_median, T.count_field_stems_d15_ha_median, T.count_sat_trees_ha_median, T.count_sat_trees_ha_unsmoothed_median] }]}
            colors={[C.stems]}
            format={t0}
          />
        </Card>
        <Card
          title="Carbon found, as a share of the field"
          sub="The same formula applied to trees counted from space (E4), against the map that learns biomass from the pixels directly."
          takeaway={`E4 finds about a quarter of the field carbon on every dataset. Scaled by the factor learned on other regions (×${T.e4_factor_median.toFixed(1)}), its total is right, but plot by plot it is worse than the map. Without smoothing it finds ${p0(unsm.sat_pct_of_field_total)}.`}
        >
          <div className="controls">
            <Segmented
              label="Measure"
              options={[
                { value: "total", label: "Share of the field total" },
                { value: "within", label: "Plots within ±25%" },
              ]}
              value={metric}
              onChange={setMetric}
            />
          </div>
          <HBarChart
            ariaLabel="Carbon found by each estimate as a share of the field"
            categories={subsets.map((s) => `${DATASET_SHORT[s]} (${tb(s, TB_EST[0][0]).plots})`)}
            series={TB_EST.map(([k, label]) => ({
              label,
              values: subsets.map((s) => (metric === "total" ? tb(s, k).sat_pct_of_field_total : tb(s, k).plots_within_25pct)),
            }))}
            colors={TB_EST.map((e) => e[2])}
            format={p0}
            refs={metric === "total" ? [{ value: 100, label: "Field = 100%" }] : []}
            max={metric === "within" ? 100 : undefined}
          />
          <TableView
            rows={D.tree_benchmark}
            cols={[
              { key: "s", label: "Subset", get: (r) => DATASET_SHORT[r.subset] },
              { key: "e", label: "Estimate", get: (r) => r.estimator },
              { key: "f", label: "Field t CO₂e/ha", num: true, get: (r) => t0(r.field_tCO2e_ha_mean) },
              { key: "v", label: "Estimate t CO₂e/ha", num: true, get: (r) => t0(r.sat_tCO2e_ha_mean) },
              { key: "t", label: "% of field total", num: true, get: (r) => p0(r.sat_pct_of_field_total) },
              { key: "m", label: "Median plot %", num: true, get: (r) => p0(r.plot_pct_median) },
              { key: "w", label: "Within ±25%", num: true, get: (r) => p0(r.plots_within_25pct) },
            ]}
          />
        </Card>
      </div>
    </Section>
  );
}

/* ================================================================== simulations */

const SIM_SERIES = [
  ["map_pct", "Map: E2 + canopy height + GEDI", C.map],
  ["e4_pct", "E4: count + formula", C.e4],
  ["e4cal_pct", "E4 scaled", C.e4s],
  ["credited_pct", "Credited (conformal, 10% risk)", C.credit],
] as const;

function SimTable() {
  const [open, setOpen] = useState<number | null>(1);
  const sims = D.simulations;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th className="num">#</th>
            <th>Region (10 random plots)</th>
            <th className="num">Field, t CO₂e</th>
            <th className="num">Map</th>
            <th className="num">E4</th>
            <th className="num">E4 scaled</th>
            <th className="num">Credited</th>
            <th className="num">Stems / trees per ha</th>
          </tr>
        </thead>
        <tbody>
          {sims.map((s) => {
            const isOpen = open === s.sim;
            const plots = D.simulation_plots.filter((p) => p.sim === s.sim);
            return (
              <Fragment key={s.sim}>
                <tr
                  className={isOpen ? "clickable open" : "clickable"}
                  onClick={() => setOpen(isOpen ? null : s.sim)}
                  onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setOpen(isOpen ? null : s.sim))}
                  tabIndex={0}
                  aria-expanded={isOpen}
                >
                  <td className="num">{isOpen ? "▾" : "▸"} {s.sim}</td>
                  <td>{site(s.site)}</td>
                  <td className="num">{t0(s.field_tCO2e)}</td>
                  <td className="num">
                    {t0(s.map_tCO2e)} <small>({p0(s.map_pct)})</small>
                  </td>
                  <td className="num">
                    {t0(s.e4_tCO2e)} <small>({p0(s.e4_pct)})</small>
                  </td>
                  <td className="num">
                    {t0(s.e4cal_tCO2e)} <small>({p0(s.e4cal_pct)})</small>
                  </td>
                  <td className="num">
                    {t0(s.credited_tCO2e)} <small>({p0(s.credited_pct)})</small>
                  </td>
                  <td className="num">
                    {s.field_stems_ha == null ? "–" : t0(s.field_stems_ha)} / {t0(s.sat_trees_ha)}
                  </td>
                </tr>
                {isOpen && (
                  <tr>
                    <td colSpan={8} className="sub-rows">
                      <table>
                        <thead>
                          <tr>
                            <th>Plot</th>
                            <th className="num">Field stems/ha</th>
                            <th className="num">Satellite trees/ha</th>
                            <th className="num">Field t CO₂e/ha</th>
                            <th className="num">Map</th>
                            <th className="num">E4</th>
                            <th className="num">E4 scaled</th>
                          </tr>
                        </thead>
                        <tbody>
                          {plots.map((p) => (
                            <tr key={p.plot_id}>
                              <td>{p.plot_id}</td>
                              <td className="num">{p.field_stems_ha == null ? "–" : t0(p.field_stems_ha)}</td>
                              <td className="num">{t0(p.sat_trees_ha)}</td>
                              <td className="num">{t0(p.field_tCO2e_ha)}</td>
                              <td className="num">
                                {t0(p.map_tCO2e_ha)} <small>({p0((100 * p.map_tCO2e_ha) / p.field_tCO2e_ha)})</small>
                              </td>
                              <td className="num">{t0(p.e4_tCO2e_ha)}</td>
                              <td className="num">{t0(p.e4cal_tCO2e_ha)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function PlotTable() {
  const [ds, setDs] = useState<string>("All");
  const [q, setQ] = useState("");
  const [all, setAll] = useState(false);
  const rows = useMemo(
    () => D.plots.filter((p) => (ds === "All" || p.d === ds) && p.id.toLowerCase().includes(q.trim().toLowerCase())),
    [ds, q],
  );
  const shown = all ? rows : rows.slice(0, 40);
  const pc = (v: number, f: number) => p0((100 * v) / f);
  return (
    <>
      <div className="controls">
        <Segmented
          label="Dataset"
          options={[
            { value: "All", label: "All" },
            { value: "Labriere2018", label: "Labrière" },
            { value: "GEO-TREES", label: "GEO-TREES" },
            { value: "HCSA_Indonesia", label: "HCSA" },
          ]}
          value={ds}
          onChange={setDs}
        />
        <input className="search" type="search" placeholder="Search plot id, e.g. RU12" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search plots" />
      </div>
      <div className="table-scroll bigtable">
        <table>
          <thead>
            <tr>
              <th>Plot</th>
              <th className="num">Field stems/ha</th>
              <th className="num">Satellite trees/ha</th>
              <th className="num">Canopy height (m)</th>
              <th className="num">Field t CO₂e/ha</th>
              <th className="num">Map</th>
              <th className="num">E4</th>
              <th className="num">E4 scaled</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((p) => (
              <tr key={p.id}>
                <td>{p.id}</td>
                <td className="num">{p.st == null ? "–" : t0(p.st)}</td>
                <td className="num">{t0(p.tr)}</td>
                <td className="num">{p.h == null ? "–" : p.h.toFixed(1)}</td>
                <td className="num">{t0(p.f)}</td>
                <td className="num">
                  {t0(p.m)} <small>({pc(p.m, p.f)})</small>
                </td>
                <td className="num">
                  {t0(p.e4)} <small>({pc(p.e4, p.f)})</small>
                </td>
                <td className="num">
                  {t0(p.e4s)} <small>({pc(p.e4s, p.f)})</small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="note">
        {rows.length} plots match.{" "}
        {rows.length > 40 && (
          <button type="button" className="link-btn" onClick={() => setAll(!all)}>
            {all ? "Show the first 40" : `Show all ${rows.length}`}
          </button>
        )}{" "}
        Field stems are published only in the HCSA stem lists; GEO-TREES and Labrière publish plot biomass.
      </p>
    </>
  );
}

export function Simulations() {
  const sims = D.simulations;
  const h = D.simulation_hist;
  // 20-point bins from the exported 10-point bins; the last bin holds 200% and more
  const bins = Array.from({ length: 10 }, (_, i) => i);
  const sum2 = (a: number[]) => [...bins.map((i) => a[2 * i] + a[2 * i + 1]), a[20]];
  const binLabels = [...bins.map((i) => `${i * 20}`), "200+"];
  return (
    <Section
      id="simulations"
      title="Ten simulated projects: carbon found, not error"
      sub="Each simulation is a hypothetical 1,000 ha project: one region drawn at random, then 10 of its plots at random. Every method estimates the carbon of the whole project; the table shows tonnes of CO₂e and the percentage of the field amount. 1,000 simulations were run; the first ten are shown, each with its plots."
    >
      <div className="grid tiles" style={{ marginBottom: 16 }}>
        <Tile
          label="Map: E2 + canopy height + GEDI"
          value={p0(SIM.map.median_pct)}
          detail={`median share of the field carbon over 1,000 projects; within ±25% in ${p0(SIM.map.within_25pct)} of them (5th–95th: ${p0(SIM.map.p5_pct)}–${p0(SIM.map.p95_pct)})`}
          status="good"
          statusText="Close at project scale"
          meter={SIM.map.within_25pct}
        />
        <Tile
          label="E4: count the trees + formula"
          value={p0(SIM.e4.median_pct)}
          detail={`median share of the field carbon; never within ±25% (5th–95th: ${p0(SIM.e4.p5_pct)}–${p0(SIM.e4.p95_pct)})`}
          status="critical"
          statusText="Sees only the canopy"
          meter={SIM.e4.within_25pct}
        />
        <Tile
          label="E4 scaled on other regions"
          value={p0(SIM.e4cal.median_pct)}
          detail={`median; within ±25% in ${p0(SIM.e4cal.within_25pct)} of projects (5th–95th: ${p0(SIM.e4cal.p5_pct)}–${p0(SIM.e4cal.p95_pct)})`}
          status="warning"
          statusText="Right on average, noisy"
          meter={SIM.e4cal.within_25pct}
        />
        <Tile
          label="Credited by conformal crediting"
          value={p0(SIM.credited.median_pct)}
          detail={`median share of the field carbon credited; above the field amount in ${p0(SIM.credited.above_field_pct)} of projects (target 10%)`}
          status="good"
          statusText="Near its risk target"
          meter={SIM.credited.median_pct}
        />
      </div>
      <div className="grid two">
        <Card wide title="Carbon found in each of the ten projects" sub="Percentage of the field amount; the dashed line is the field (100%).">
          <HBarChart
            ariaLabel="Carbon found by each method in ten simulated projects"
            categories={sims.map((s) => `#${s.sim} ${site(s.site)}`)}
            series={SIM_SERIES.map(([k, label]) => ({ label, values: sims.map((s) => s[k]) }))}
            colors={SIM_SERIES.map((s) => s[2])}
            format={p0}
            refs={[{ value: 100, label: "Field = 100%" }]}
            barH={9}
          />
        </Card>
        <Card
          wide
          title="The ten projects, plot by plot"
          sub="Click a project to see its 10 plots. Carbon for the whole 1,000 ha project in t CO₂e (percentage of the field amount)."
          takeaway={`Inside a project the plots disagree far more than the totals: in project 1 the map gives one Riau plot six times its field value and another half of it, and the project still comes out at ${p0(sims[0].map_pct)}.`}
        >
          <SimTable />
        </Card>
        <Card
          wide
          title="All 1,000 projects"
          sub={`How many of the ${t0(h.n)} simulated projects fall in each band of carbon found, as % of the field amount. Bands are 20 points wide and labelled by their lower edge: 80 means 80–100%.`}
          takeaway="The map and the credit cluster around the field amount; the credit sits a little below it by design. E4 scaled spreads from a fifth to more than double."
        >
          <ColumnChart
            ariaLabel="Distribution of carbon found over 1,000 simulated projects"
            categories={binLabels}
            series={[
              { label: "Map", values: sum2(h.map) },
              { label: "E4 scaled", values: sum2(h.e4cal) },
              { label: "Credited", values: sum2(h.credited) },
            ]}
            colors={[C.map, C.e4s, C.credit]}
            format={(v) => t0(v)}
            height={260}
            yLabel="Projects"
          />
        </Card>
        <Card
          wide
          title="Every plot"
          sub="All 475 plots: field and satellite carbon per hectare, field stems and satellite trees per hectare, and the mean canopy height of the map."
        >
          <PlotTable />
        </Card>
      </div>
    </Section>
  );
}
