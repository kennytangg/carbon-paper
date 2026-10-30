# estimation: blind satellite-vs-field carbon benchmark

This package produces every number in `docs/carbon_paper.tex`. The **right grid** is the field ground truth, computed by the standard formula and sealed. The **left grid** is the satellite-only estimate; it sees only the public manifest. A hash-chained ledger (`data/estimation/blind_ledger.jsonl`) records the order of seal, commit, release, and reveal.

## Setup

```
python -m venv .venv && .venv/Scripts/pip install pandas pyarrow lightgbm rasterio pystac-client planetary-computer pyproj pyreadr openpyxl scipy matplotlib
```

Satellite reads use the Microsoft Planetary Computer (anonymous). `extract_gee.py` needs the Earth Engine service account (roles: Service Usage Consumer, Earth Engine Resource Viewer) and its key file `service-account-key.json` in the folder above the repo; the key is never committed.

## Raw data (`data/gt_raw/`)

| Dataset | Source | Licence |
| --- | --- | --- |
| HCSA Indonesia field plots | HCSA Steering Group, 2023 release | CC BY-SA 4.0 |
| GEO-TREES plots | geo-trees.org | see source |
| Labrière et al. 2018 in situ (TropiSAR/AfriSAR) | Labrière et al. 2018 | CC0 |
| SAFE tree census 2011–2020 | Zenodo 10.5281/zenodo.14882506 (download, not committed: 41 MB) | see record |
| SAFE gazetteer, location aliases | Zenodo record 3906082 | see record |
| Global Wood Density Database | BIOMASS v2.1.11 `wdData.rda` | see package |

## Run order

| Step | Command | Writes |
| --- | --- | --- |
| 1. Right grid, stock (seals) | `python -m estimation.right_grid` | `right_grid_sealed.parquet`, `plot_manifest.parquet` |
| 2. Right grid, change (seals) | `python -m estimation.right_grid_seq` | `seq_right_grid_sealed.parquet`, `seq_plot_manifest.parquet` |
| 3. Left grid extraction | `python -m estimation.extract_left --workers 24 --window 90` (+ `--seq`) | `left_features_win90*.parquet` |
| 4. Window sensitivity extraction | `python -m estimation.extract_left --window W --datasets HCSA_Indonesia --sensors s2,landsat,s1` | `left_features_winW_HCSA_Indonesia.parquet` |
| 4b. Earth Engine features | `python -m estimation.extract_gee` (+ `--seq`) | `left_features_gee*.parquet` (service-account key at repo parent) |
| 5. Blind stock evaluation | `python -m estimation.evaluate --window 90` | `results/stock_metrics.csv`, k-shot and aggregation curves |
| 6. Blind change evaluation | `python -m estimation.evaluate_seq --window 90` | `results/seq_metrics.csv` |
| 7. Right-grid uncertainty | `python -m estimation.right_grid_uncertainty` | `results/gt_*` |
| 8. Improvement ladders | `python -m estimation.improve`, `python -m estimation.improve_seq` | `results/improvement_ladder.csv`, `results/seq_improvement.csv` |
| 9. Window sensitivity | `python -m estimation.window_sensitivity` | `results/window_sensitivity.csv` |
| 10. Cloud climatology | `python -m estimation.cloud_climatology`, then `python -m estimation.cloud_analysis` | `results/cloud_*` |
| 11. Cloud robustness and intervals | `python -m estimation.robust`, then `python -m estimation.robust --only-u4` | `results/cloud_robustness.csv`, `results/interval_methods.csv`, `results/cloud_aware_cqr.csv` |
| 12. Project-level uncertainty | `python -m estimation.project_uncertainty` | `results/project_*` |
| 13. Reliability | `python -m estimation.reliability` | `results/bootstrap_ci.csv`, `results/seed_stability.csv` |
| 13b. Conformal crediting | `python -m estimation.conformal_crediting`, `python -m estimation.crediting_frontier`, `python -m estimation.crediting_robustness` | `results/conformal_crediting.csv`, `results/crediting_frontier.csv`, `results/crediting_robustness.csv` |
| 13c. Gain-loss test (SAFE) | `python -m estimation.gain_loss` | `results/gain_loss.csv` |
| 13d. Sharper inputs (GEE) | `python -m estimation.accuracy_gee` | `results/accuracy_gee*.csv` |
| 14. Systems experiments | `python -m estimation.systems_experiments --n-tasks 48` | `results/systems_experiments.json` |
| 15. Figures | `python -m estimation.figures` | `docs/figures/*.pdf` |

Steps 1–2 append seals to the ledger, and steps 5–6 open a new epoch and reveal. Run them once per evaluation, in order. Steps 7–15 come after the reveal and are exploratory, and the paper labels them so.
