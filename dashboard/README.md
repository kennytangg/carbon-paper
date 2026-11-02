# Results dashboard

A static Next.js site that shows the paper's results visually: how the field and the satellite each get their number (a real stem list, the NDVI formula, trees counted on the 1 m canopy height map), accuracy against the field ground truth, what the field counts against what the satellite sees, ten simulated projects plot by plot, ground-truth uncertainty, clouds, interval coverage, conformal crediting, growth, and the blind two-grid method with the drone roadmap.

Every number on the page is read from `data/estimation/results/` (the same tables the paper uses). Nothing is typed in by hand.

## Run

Requires Node 20.9 or newer.

```bash
cd dashboard
npm install
npm run dev      # http://localhost:3000
npm run build    # static site in dashboard/out/
npx serve out    # preview the static build
```

`out/` is plain HTML, CSS and JS. Deploy it to any static host (Vercel, Netlify, GitHub Pages). For a sub-path such as GitHub Pages, build with `BASE_PATH=/carbon-paper npm run build`.

## Refresh the data

After re-running the estimation pipeline (see `estimation/README.md`), regenerate the dashboard's data file from the repo root with the project venv:

```bash
.venv/Scripts/python.exe dashboard/scripts/export_data.py   # Windows
.venv/bin/python dashboard/scripts/export_data.py           # macOS/Linux
```

This rewrites `dashboard/data/results.json` (about 250 KB) and prints the headline numbers. Commit that file; the build only reads it, so `npm run build` needs no Python.

## Layout

| Path | What it holds |
|---|---|
| `scripts/export_data.py` | Reads the result CSVs and prediction parquet, writes `data/results.json` |
| `data/results.json` | All numbers the page shows |
| `lib/data.ts` | Types for the JSON, accuracy helper (accuracy = 100 − relative RMSE) |
| `components/charts.tsx` | Hand-written SVG charts (bars, columns, lines, log-log scatter, ranked intervals) with hover tooltips |
| `components/sections.tsx` | Overview and the original seven sections |
| `components/trees.tsx` | How it works (stem list, NDVI, canopy map with detected trees), trees and wood, the ten simulated projects and every plot |
| `components/production.tsx` | Toward production: each fix on the 1,000 projects, the unseen Danum test, published height equations, the frozen method |
| `components/ui.tsx` | Cards, stat tiles, status tags, table views |
| `app/` | Page, layout, global styles (light and dark tokens) |

## Reading the numbers

- **Accuracy** = 100 − relative RMSE of the satellite estimate against the field value, floored at 0.
- **Project total, no field plots** = error of a region's total when the model saw no plot from that region (`kshot_k0` in `accuracy_gee_project_scale.csv`).
- **Over-credited share** = fraction of test projects whose issued credit exceeded the true field stock.
- **Simulations** show carbon found, not error: each method's carbon for a 1,000 ha project of 10 random plots, in t CO₂e and as % of the field amount (`simulations.csv`).
