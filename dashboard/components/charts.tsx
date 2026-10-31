"use client";

import { useEffect, useRef, useState, type PointerEvent as RPointerEvent } from "react";

/* Categorical slots in fixed order. Never cycled: callers pass at most five series. */
export const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)", "var(--series-5)"];

type TipRow = { color?: string; label: string; value: string };

/** Surface-coloured outline so labels stay legible where a reference line crosses them. */
const HALO = { stroke: "var(--surface)", strokeWidth: 3, strokeLinejoin: "round" as const, style: { paintOrder: "stroke" as const } };
type TipState = { x: number; y: number; title: string; rows: TipRow[] } | null;

function useWidth(initial = 640) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(initial);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const cw = entries[0]?.contentRect.width ?? initial;
      setW(Math.max(260, Math.floor(cw)));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [initial]);
  return [ref, w] as const;
}

function Tip({ tip, width }: { tip: TipState; width: number }) {
  if (!tip) return null;
  const tw = 220;
  const left = tip.x + 16 + tw > width ? Math.max(0, tip.x - tw - 12) : tip.x + 16;
  return (
    <div className="tip" style={{ left, top: Math.max(0, tip.y - 12) }} role="status">
      <div className="t">{tip.title}</div>
      {tip.rows.map((r, i) => (
        <div className="r" key={i}>
          <span>
            {r.color && <i style={{ background: r.color }} />}
            {r.label}
          </span>
          <b>{r.value}</b>
        </div>
      ))}
    </div>
  );
}

export type LegendItem = { label: string; color?: string; kind?: "box" | "line" | "ref" };

export function Legend({ items }: { items: LegendItem[] }) {
  return (
    <div className="legend">
      {items.map((it) => (
        <span key={it.label}>
          <i className={it.kind === "line" ? "line" : it.kind === "ref" ? "ref" : undefined} style={it.kind === "ref" ? undefined : { background: it.color }} />
          {it.label}
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ scales */

function niceStep(range: number, count: number) {
  const raw = range / Math.max(1, count);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / mag;
  const step = n >= 5 ? 10 : n >= 2 ? 5 : n >= 1 ? 2 : 1;
  return step * mag;
}

function linearTicks(min: number, max: number, count = 5) {
  const step = niceStep(max - min, count);
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

function niceMax(max: number, count = 5) {
  const step = niceStep(max, count);
  return Math.ceil(max / step) * step;
}

function logTicks(min: number, max: number) {
  const out: number[] = [];
  for (let e = Math.floor(Math.log10(min)); e <= Math.ceil(Math.log10(max)); e++) {
    for (const m of [1, 2, 5]) {
      const v = m * Math.pow(10, e);
      if (v >= min * 0.999 && v <= max * 1.001) out.push(v);
    }
  }
  return out;
}

/** Horizontal bar with a 4px rounded data-end and a square baseline end. */
function hbarPath(x0: number, x1: number, y: number, h: number) {
  const w = x1 - x0;
  if (w <= 0.5) return "";
  const r = Math.min(4, h / 2, w);
  return `M${x0},${y}H${x1 - r}Q${x1},${y} ${x1},${y + r}V${y + h - r}Q${x1},${y + h} ${x1 - r},${y + h}H${x0}Z`;
}

/** Vertical column with a 4px rounded top. */
function vbarPath(x: number, w: number, y0: number, y1: number) {
  const h = y0 - y1;
  if (h <= 0.5) return "";
  const r = Math.min(4, w / 2, h);
  return `M${x},${y0}V${y1 + r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 + r}V${y0}Z`;
}

/* ------------------------------------------------------------------ horizontal bars */

export type BarSeries = { label: string; values: (number | null)[] };
export type RefLine = { value: number; label: string };

export function HBarChart({
  categories,
  series,
  format = (v) => v.toFixed(1),
  max,
  refs = [],
  emphasize = [],
  tipExtra,
  barH,
  ariaLabel,
}: {
  categories: string[];
  series: BarSeries[];
  format?: (v: number) => string;
  max?: number;
  refs?: RefLine[];
  emphasize?: number[];
  tipExtra?: (ci: number, si: number) => TipRow[];
  barH?: number;
  ariaLabel: string;
}) {
  const [ref, width] = useWidth();
  const [tip, setTip] = useState<TipState>(null);
  const [hover, setHover] = useState<string | null>(null);
  const ns = series.length;
  const bh = barH ?? (ns === 1 ? 16 : ns === 2 ? 13 : 11);
  const labelH = 18;
  const groupGap = 12;
  const groupH = labelH + ns * bh + (ns - 1) * 2;
  const top = refs.length ? 18 : 4;
  const axisH = 22;
  const height = top + categories.length * (groupH + groupGap) - groupGap + axisH;
  const valueRoom = 56;
  const plotW = Math.max(120, width - valueRoom);
  const allVals = series.flatMap((s) => s.values.filter((v): v is number => v != null));
  const vmax = max ?? niceMax(Math.max(...allVals, ...refs.map((r) => r.value)) * 1.02);
  const x = (v: number) => (Math.min(v, vmax) / vmax) * plotW;
  const ticks = linearTicks(0, vmax, width < 420 ? 3 : 5);
  const bottom = height - axisH;

  return (
    <div className="chart" ref={ref} onPointerLeave={() => (setTip(null), setHover(null))}>
      {ns > 1 && <Legend items={series.map((s, i) => ({ label: s.label, color: SERIES[i] }))} />}
      <svg width={width} height={height} role="img" aria-label={ariaLabel}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={top - 2} y2={bottom} stroke="var(--grid)" strokeWidth={1} />
            <text x={x(t)} y={bottom + 15} fontSize={11} fill="var(--axis-text)" textAnchor={t === 0 ? "start" : "middle"} style={{ fontVariantNumeric: "tabular-nums" }}>
              {format(t)}
            </text>
          </g>
        ))}
        <line x1={0} x2={0} y1={top - 2} y2={bottom} stroke="var(--baseline)" strokeWidth={1} />
        {refs.map((r) => (
          <g key={r.label}>
            <line x1={x(r.value)} x2={x(r.value)} y1={top - 4} y2={bottom} stroke="var(--ref)" strokeWidth={1.5} strokeDasharray="4 3" />
            <text x={x(r.value)} y={top - 7} fontSize={11} fill="var(--text-secondary)" textAnchor={x(r.value) > plotW - 60 ? "end" : "middle"} {...HALO}>
              {r.label}
            </text>
          </g>
        ))}
        {categories.map((c, ci) => {
          const gy = top + ci * (groupH + groupGap);
          return (
            <g key={c}>
              <text x={0} y={gy + 12} fontSize={12.5} fill="var(--text-primary)" fontWeight={emphasize.includes(ci) ? 650 : 400} {...HALO}>
                {c}
              </text>
              {series.map((s, si) => {
                const v = s.values[ci];
                const y = gy + labelH + si * (bh + 2);
                const id = `${ci}-${si}`;
                const dim = hover != null && hover !== id;
                return (
                  <g key={si}>
                    {v != null && (
                      <path d={hbarPath(0, x(v), y, bh)} fill={SERIES[si]} opacity={dim ? 0.55 : 1} />
                    )}
                    {v != null && (
                      <text x={x(v) + 6} y={y + bh / 2 + 4} fontSize={11.5} fill="var(--text-secondary)" {...HALO} style={{ paintOrder: "stroke", fontVariantNumeric: "tabular-nums" }}>
                        {format(v)}
                      </text>
                    )}
                    <rect
                      x={0}
                      y={y - 1}
                      width={width}
                      height={bh + 2}
                      fill="transparent"
                      onPointerMove={(e: RPointerEvent<SVGRectElement>) => {
                        const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                        setHover(id);
                        setTip({
                          x: e.clientX - box.left,
                          y: e.clientY - box.top + (ns > 1 ? 28 : 0),
                          title: c,
                          rows: [
                            { color: SERIES[si], label: s.label, value: v == null ? "n/a" : format(v) },
                            ...(tipExtra ? tipExtra(ci, si) : []),
                          ],
                        });
                      }}
                    />
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
      <Tip tip={tip} width={width} />
    </div>
  );
}

/* ------------------------------------------------------------------ grouped columns */

export function ColumnChart({
  categories,
  series,
  format = (v) => v.toFixed(1),
  yMax,
  refs = [],
  height = 260,
  ariaLabel,
  yLabel,
}: {
  categories: string[];
  series: BarSeries[];
  format?: (v: number) => string;
  yMax?: number;
  refs?: RefLine[];
  height?: number;
  ariaLabel: string;
  yLabel?: string;
}) {
  const [ref, width] = useWidth();
  const [tip, setTip] = useState<TipState>(null);
  const [hover, setHover] = useState<number | null>(null);
  const m = { l: 44, r: 8, t: yLabel ? 22 : 12, b: 40 };
  const pw = width - m.l - m.r;
  const ph = height - m.t - m.b;
  const ns = series.length;
  const all = series.flatMap((s) => s.values.filter((v): v is number => v != null));
  const vmax = yMax ?? niceMax(Math.max(...all, ...refs.map((r) => r.value)) * 1.05);
  const y = (v: number) => m.t + ph - (Math.min(v, vmax) / vmax) * ph;
  const band = pw / categories.length;
  const bw = Math.min(24, (band * 0.72 - (ns - 1) * 2) / ns);
  const groupW = ns * bw + (ns - 1) * 2;
  const ticks = linearTicks(0, vmax, 4);
  const narrow = band < 70;

  return (
    <div className="chart" ref={ref} onPointerLeave={() => (setTip(null), setHover(null))}>
      {(ns > 1 || refs.length > 0) && (
        <Legend
          items={[
            ...(ns > 1 ? series.map((s, i) => ({ label: s.label, color: SERIES[i] })) : []),
            ...refs.map((r) => ({ label: r.label, kind: "ref" as const })),
          ]}
        />
      )}
      <svg width={width} height={height} role="img" aria-label={ariaLabel}>
        {yLabel && (
          <text x={0} y={11} fontSize={11} fill="var(--text-muted)">
            {yLabel}
          </text>
        )}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={m.l} x2={width - m.r} y1={y(t)} y2={y(t)} stroke={t === 0 ? "var(--baseline)" : "var(--grid)"} strokeWidth={1} />
            <text x={m.l - 6} y={y(t) + 4} fontSize={11} fill="var(--axis-text)" textAnchor="end" style={{ fontVariantNumeric: "tabular-nums" }}>
              {format(t)}
            </text>
          </g>
        ))}
        {categories.map((c, ci) => {
          const gx = m.l + ci * band + (band - groupW) / 2;
          return (
            <g key={c}>
              {series.map((s, si) => {
                const v = s.values[ci];
                if (v == null) return null;
                return (
                  <path
                    key={si}
                    d={vbarPath(gx + si * (bw + 2), bw, y(0), y(v))}
                    fill={SERIES[si]}
                    opacity={hover != null && hover !== ci ? 0.55 : 1}
                  />
                );
              })}
              <text
                x={m.l + ci * band + band / 2}
                y={height - m.b + 16}
                fontSize={narrow ? 10.5 : 11.5}
                fill="var(--text-secondary)"
                textAnchor="middle"
              >
                {c.split("\n").map((line, li) => (
                  <tspan key={li} x={m.l + ci * band + band / 2} dy={li === 0 ? 0 : 13}>
                    {line}
                  </tspan>
                ))}
              </text>
              <rect
                x={m.l + ci * band}
                y={m.t}
                width={band}
                height={ph}
                fill="transparent"
                onPointerMove={(e: RPointerEvent<SVGRectElement>) => {
                  const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                  setHover(ci);
                  setTip({
                    x: e.clientX - box.left,
                    y: e.clientY - box.top + (ns > 1 ? 28 : 0),
                    title: c.replace("\n", " "),
                    rows: series.map((s, si) => ({
                      color: SERIES[si],
                      label: s.label,
                      value: s.values[ci] == null ? "n/a" : format(s.values[ci] as number),
                    })),
                  });
                }}
              />
            </g>
          );
        })}
        {refs.map((r) => (
          <g key={r.label}>
            <line x1={m.l} x2={width - m.r} y1={y(r.value)} y2={y(r.value)} stroke="var(--ref)" strokeWidth={1.5} strokeDasharray="4 3" />
          </g>
        ))}
      </svg>
      <Tip tip={tip} width={width} />
    </div>
  );
}

/* ------------------------------------------------------------------ lines */

export type LineSeries = { label: string; points: { x: number; y: number | null }[] };

export function LineChart({
  series,
  xFormat = (v) => String(v),
  yFormat = (v) => v.toFixed(0),
  xTicks,
  yMin = 0,
  yMax,
  refs = [],
  diagonal,
  height = 260,
  xLabel,
  yLabel,
  ariaLabel,
}: {
  series: LineSeries[];
  xFormat?: (v: number) => string;
  yFormat?: (v: number) => string;
  xTicks?: number[];
  yMin?: number;
  yMax?: number;
  refs?: RefLine[];
  diagonal?: string;
  height?: number;
  xLabel?: string;
  yLabel?: string;
  ariaLabel: string;
}) {
  const [ref, width] = useWidth();
  const [hx, setHx] = useState<number | null>(null);
  const [tipY, setTipY] = useState(0);
  const m = { l: 44, r: 12, t: yLabel ? 24 : 12, b: xLabel ? 42 : 26 };
  const pw = width - m.l - m.r;
  const ph = height - m.t - m.b;
  const xs = Array.from(new Set(series.flatMap((s) => s.points.map((p) => p.x)))).sort((a, b) => a - b);
  const xmin = xs[0];
  const xmax = xs[xs.length - 1];
  const allY = series.flatMap((s) => s.points.map((p) => p.y).filter((v): v is number => v != null));
  const ymax = yMax ?? niceMax(Math.max(...allY, ...refs.map((r) => r.value)) * 1.05);
  const X = (v: number) => m.l + ((v - xmin) / (xmax - xmin || 1)) * pw;
  const Y = (v: number) => m.t + ph - ((v - yMin) / (ymax - yMin)) * ph;
  const yt = linearTicks(yMin, ymax, 4);
  const xt = xTicks ?? xs;

  const onMove = (e: RPointerEvent<SVGRectElement>) => {
    const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
    const px = e.clientX - box.left;
    let best = xs[0];
    for (const v of xs) if (Math.abs(X(v) - px) < Math.abs(X(best) - px)) best = v;
    setHx(best);
    setTipY(e.clientY - box.top + (series.length > 1 ? 28 : 0));
  };

  const tip: TipState =
    hx == null
      ? null
      : {
          x: X(hx),
          y: tipY,
          title: xFormat(hx),
          rows: series.map((s, si) => {
            const p = s.points.find((q) => q.x === hx);
            return { color: SERIES[si], label: s.label, value: p?.y == null ? "n/a" : yFormat(p.y) };
          }),
        };

  return (
    <div className="chart" ref={ref} onPointerLeave={() => setHx(null)}>
      {(series.length > 1 || diagonal || refs.length > 0) && (
        <Legend
          items={[
            ...(series.length > 1 ? series.map((s, i) => ({ label: s.label, color: SERIES[i], kind: "line" as const })) : []),
            ...(diagonal ? [{ label: diagonal, kind: "ref" as const }] : []),
          ]}
        />
      )}
      <svg width={width} height={height} role="img" aria-label={ariaLabel}>
        {yLabel && (
          <text x={0} y={11} fontSize={11} fill="var(--text-muted)">
            {yLabel}
          </text>
        )}
        {yt.map((t) => (
          <g key={t}>
            <line x1={m.l} x2={width - m.r} y1={Y(t)} y2={Y(t)} stroke={t === yMin ? "var(--baseline)" : "var(--grid)"} strokeWidth={1} />
            <text x={m.l - 6} y={Y(t) + 4} fontSize={11} fill="var(--axis-text)" textAnchor="end" style={{ fontVariantNumeric: "tabular-nums" }}>
              {yFormat(t)}
            </text>
          </g>
        ))}
        {xt.map((t, i) => (
          <text
            key={t}
            x={X(t)}
            y={m.t + ph + 16}
            fontSize={11}
            fill="var(--axis-text)"
            textAnchor={i === 0 && X(t) - m.l < 12 ? "start" : "middle"}
            style={{ fontVariantNumeric: "tabular-nums" }}
          >
            {xFormat(t)}
          </text>
        ))}
        {xLabel && (
          <text x={m.l + pw / 2} y={height - 4} fontSize={11} fill="var(--text-muted)" textAnchor="middle">
            {xLabel}
          </text>
        )}
        {diagonal && (
          <line
            x1={X(Math.max(xmin, yMin))}
            y1={Y(Math.max(xmin, yMin))}
            x2={X(Math.min(xmax, ymax))}
            y2={Y(Math.min(xmax, ymax))}
            stroke="var(--ref)"
            strokeWidth={1.5}
            strokeDasharray="4 3"
          />
        )}
        {refs.map((r) => (
          <g key={r.label}>
            <line x1={m.l} x2={width - m.r} y1={Y(r.value)} y2={Y(r.value)} stroke="var(--ref)" strokeWidth={1.5} strokeDasharray="4 3" />
            <text x={width - m.r} y={Y(r.value) - 5} fontSize={11} fill="var(--text-secondary)" textAnchor="end" {...HALO}>
              {r.label}
            </text>
          </g>
        ))}
        {hx != null && <line x1={X(hx)} x2={X(hx)} y1={m.t} y2={m.t + ph} stroke="var(--baseline)" strokeWidth={1} />}
        {series.map((s, si) => {
          const pts = s.points.filter((p) => p.y != null) as { x: number; y: number }[];
          const d = pts.map((p, i) => `${i ? "L" : "M"}${X(p.x)},${Y(p.y)}`).join("");
          return (
            <g key={s.label}>
              <path d={d} fill="none" stroke={SERIES[si]} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {pts.map((p) => (
                <circle
                  key={p.x}
                  cx={X(p.x)}
                  cy={Y(p.y)}
                  r={p.x === hx ? 5 : 4}
                  fill={SERIES[si]}
                  stroke="var(--surface)"
                  strokeWidth={2}
                />
              ))}
            </g>
          );
        })}
        <rect x={m.l} y={m.t} width={pw} height={ph} fill="transparent" onPointerMove={onMove} />
      </svg>
      <Tip tip={tip} width={width} />
    </div>
  );
}

/* ------------------------------------------------------------------ log-log scatter */

export function ScatterChart({
  points,
  labels,
  domain,
  xLabel,
  yLabel,
  ariaLabel,
  height = 360,
  unit = "",
}: {
  points: { x: number; y: number; s: number }[];
  labels: string[];
  domain: [number, number];
  xLabel: string;
  yLabel: string;
  ariaLabel: string;
  height?: number;
  unit?: string;
}) {
  const [ref, width] = useWidth();
  const [hi, setHi] = useState<number | null>(null);
  const m = { l: 44, r: 12, t: 22, b: 42 };
  const size = Math.min(width - m.l - m.r, height - m.t - m.b);
  const h = size + m.t + m.b;
  const [lo, up] = domain;
  const L = (v: number) => (Math.log10(Math.max(lo, Math.min(up, v))) - Math.log10(lo)) / (Math.log10(up) - Math.log10(lo));
  const X = (v: number) => m.l + L(v) * size;
  const Y = (v: number) => m.t + size - L(v) * size;
  const ticks = logTicks(lo, up);

  const onMove = (e: RPointerEvent<SVGRectElement>) => {
    const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
    const px = e.clientX - box.left;
    const py = e.clientY - box.top;
    let best = -1;
    let bd = 24 * 24;
    points.forEach((p, i) => {
      const d = (X(p.x) - px) ** 2 + (Y(p.y) - py) ** 2;
      if (d < bd) {
        bd = d;
        best = i;
      }
    });
    setHi(best >= 0 ? best : null);
  };
  const p = hi != null ? points[hi] : null;
  const tip: TipState = p
    ? {
        x: X(p.x),
        y: Y(p.y) + 28,
        title: labels[p.s],
        rows: [
          { label: "Field (ground truth)", value: `${p.x.toFixed(0)}${unit}` },
          { label: "Satellite estimate", value: `${p.y.toFixed(0)}${unit}` },
          { label: "Off by", value: `${(((p.y - p.x) / p.x) * 100).toFixed(0)}%` },
        ],
      }
    : null;

  return (
    <div className="chart" ref={ref} onPointerLeave={() => setHi(null)}>
      <Legend items={[...labels.map((l, i) => ({ label: l, color: SERIES[i] })), { label: "Perfect estimate (1:1)", kind: "ref" as const }]} />
      <svg width={width} height={h} role="img" aria-label={ariaLabel}>
        <text x={0} y={11} fontSize={11} fill="var(--text-muted)">
          {yLabel}
        </text>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={X(t)} x2={X(t)} y1={m.t} y2={m.t + size} stroke="var(--grid)" strokeWidth={1} />
            <line x1={m.l} x2={m.l + size} y1={Y(t)} y2={Y(t)} stroke="var(--grid)" strokeWidth={1} />
            <text x={X(t)} y={m.t + size + 15} fontSize={11} fill="var(--axis-text)" textAnchor="middle">
              {t}
            </text>
            <text x={m.l - 6} y={Y(t) + 4} fontSize={11} fill="var(--axis-text)" textAnchor="end">
              {t}
            </text>
          </g>
        ))}
        <text x={m.l + size / 2} y={h - 4} fontSize={11} fill="var(--text-muted)" textAnchor="middle">
          {xLabel}
        </text>
        <line x1={X(lo)} y1={Y(lo)} x2={X(up)} y2={Y(up)} stroke="var(--ref)" strokeWidth={1.5} strokeDasharray="4 3" />
        {points.map((q, i) => (
          <circle
            key={i}
            cx={X(q.x)}
            cy={Y(q.y)}
            r={i === hi ? 6 : 4}
            fill={SERIES[q.s]}
            fillOpacity={hi == null || i === hi ? 0.85 : 0.35}
            stroke="var(--surface)"
            strokeWidth={i === hi ? 2 : 1}
          />
        ))}
        <rect x={m.l} y={m.t} width={size} height={size} fill="transparent" onPointerMove={onMove} />
      </svg>
      <Tip tip={tip} width={width} />
    </div>
  );
}

/* ------------------------------------------------------------------ dot + interval (ranked) */

export function RangeChart({
  items,
  domain,
  yLabel,
  ariaLabel,
  height = 260,
  unit = "",
}: {
  items: { v: number; lo: number; hi: number; title: string; extra?: string }[];
  domain: [number, number];
  yLabel: string;
  ariaLabel: string;
  height?: number;
  unit?: string;
}) {
  const [ref, width] = useWidth();
  const [hi, setHi] = useState<number | null>(null);
  const m = { l: 44, r: 8, t: 22, b: 24 };
  const pw = width - m.l - m.r;
  const ph = height - m.t - m.b;
  const [lo, up] = domain;
  const L = (v: number) => (Math.log10(Math.max(lo, Math.min(up, v))) - Math.log10(lo)) / (Math.log10(up) - Math.log10(lo));
  const Y = (v: number) => m.t + ph - L(v) * ph;
  const X = (i: number) => m.l + ((i + 0.5) / items.length) * pw;
  const ticks = logTicks(lo, up);

  const onMove = (e: RPointerEvent<SVGRectElement>) => {
    const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
    const i = Math.floor(((e.clientX - box.left - m.l) / pw) * items.length);
    setHi(i >= 0 && i < items.length ? i : null);
  };
  const it = hi != null ? items[hi] : null;
  const tip: TipState = it
    ? {
        x: X(hi as number),
        y: Y(it.hi),
        title: it.title,
        rows: [
          { label: "Median", value: `${it.v.toFixed(0)}${unit}` },
          { label: "95% range", value: `${it.lo.toFixed(0)}–${it.hi.toFixed(0)}${unit}` },
          ...(it.extra ? [{ label: "Trees", value: it.extra }] : []),
        ],
      }
    : null;

  return (
    <div className="chart" ref={ref} onPointerLeave={() => setHi(null)}>
      <svg width={width} height={height} role="img" aria-label={ariaLabel}>
        <text x={0} y={11} fontSize={11} fill="var(--text-muted)">
          {yLabel}
        </text>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={m.l} x2={width - m.r} y1={Y(t)} y2={Y(t)} stroke="var(--grid)" strokeWidth={1} />
            <text x={m.l - 6} y={Y(t) + 4} fontSize={11} fill="var(--axis-text)" textAnchor="end">
              {t}
            </text>
          </g>
        ))}
        {items.map((d, i) => (
          <line key={`l${i}`} x1={X(i)} x2={X(i)} y1={Y(d.lo)} y2={Y(d.hi)} stroke="var(--series-1)" strokeOpacity={hi == null || hi === i ? 0.45 : 0.2} strokeWidth={Math.max(1, Math.min(3, pw / items.length - 1))} strokeLinecap="round" />
        ))}
        {items.map((d, i) => (
          <circle key={`c${i}`} cx={X(i)} cy={Y(d.v)} r={hi === i ? 6 : 4} fill="var(--series-1)" stroke="var(--surface)" strokeWidth={hi === i ? 2 : 1} />
        ))}
        <text x={m.l} y={height - 6} fontSize={11} fill="var(--text-muted)">
          plots, sorted from lowest to highest carbon stock →
        </text>
        <rect x={m.l} y={m.t} width={pw} height={ph} fill="transparent" onPointerMove={onMove} />
      </svg>
      <Tip tip={tip} width={width} />
    </div>
  );
}

/* ------------------------------------------------------------------ small UI */

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
