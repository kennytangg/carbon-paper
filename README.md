# Sistem Ingesti, Verifikasi Formula, dan Benchmarking Dataset Ground Truth MRV Karbon Hutan

Sistem otomatis berbasis Python untuk mengumpulkan (*scraping/ingestion*), memverifikasi formula matematis, dan menstandardisasi dataset **Ground Truth MRV (Measurement, Reporting, and Verification) Karbon Hutan** dari berbagai *registry* karbon internasional (**Verra VCS**, **Gold Standard**, **ACR**, **CAR**, **ART-TREES**, **Cercarbono**) serta inventarisasi plot ilmiah terbuka (**Chave et al. 2014 Pantropical Destructive Harvest Database**, **rOpenSci/ForestGEO allodb**, **USFS FIA**, **ESA/NASA TropiSAR & AfriSAR Airborne LiDAR**, **Sentinel-2/1 Multi-Sensor Field Plots**, dan **FAO FRA 2020 NFI**).

Setiap baris data dilengkapi dengan:
1. **Variabel Input ($X$)**: Parameter biofisik pohon/plot/proyek maupun sensor penginderaan jauh.
2. **Formula & Standar Metodologi ($f(X)$)**: Persamaan matematis standar yang digunakan (Verra VM0007/VM0015/VM0047/AR-ACM0003, Gold Standard A/R, CARB/CAR/ACR IFM, Chave et al. 2014 Eq. 4 & Eq. 7, Ketterings et al. 2001 SNI 7724, Brown 1997 UNFCCC, IPCC 2006/2019 Tier 1/2, serta model struktural LiDAR & indeks spektral Sentinel-2).
3. **Outcome Ground Truth ($Y$)**: Nilai biomassa ($\text{kg}$, $\text{Mg/ha}$), stok karbon ($\text{tC/ha}$), dan ekuivalen karbon dioksida ($\text{kg CO}_2\text{e}$, $\text{tCO}_2\text{e/ha}$, maupun total kredit $\text{tCO}_2\text{e}$).
4. **Dual Timestamps**:
   - `data_generated_timestamp`: Kapan pengukuran lapangan, periode pemantauan (*monitoring/reporting period*), atau penerbitan kredit karbon tersebut benar-benar terjadi/ter-generate.
   - `data_ingested_timestamp_utc`: Kapan data tersebut ditarik dan diverifikasi oleh sistem ini (ISO-8601 UTC).

---

## Struktur Direktori

```text
.
├── run_pipeline.py                        # CLI utama penarikan data, verifikasi formula, & pembuatan dataset
├── compare_custom_algorithm.py            # Script template untuk membandingkan algoritma kustom Anda vs Ground Truth
├── docs/
│   └── METHODOLOGY_AND_FORMULAS.md        # Dokumentasi ilmiah lengkap seluruh formula & variabel
├── src/
│   ├── formulas.py                        # Engine formula standar MRV, allometrik, & penginderaan jauh
│   ├── pipeline.py                        # Orchestrator harmonisasi skema & ekspor CSV/Parquet/SQLite/JSON
│   ├── evaluator.py                       # Framework evaluasi statistik (RMSE, rRMSE%, MAE, MAPE%, R2, Lin's CCC)
│   └── scrapers/
│       ├── base.py                        # HTTP client, raw cache, & pencatat provenance SHA-256
│       ├── registry_scraper.py            # Scraper Level 1: Verra VCS, Gold Standard, ACR, CAR, ART-TREES, IFM DB
│       ├── allometry_scraper.py           # Scraper Level 2: Chave 2014 (Global & Indonesia), allodb, FIA, Bennett, 2ndFOR
│       └── remote_sensing_scraper.py      # Scraper Level 3: TropiSAR/AfriSAR LiDAR, Sentinel-2/1 Optical+SAR, FAO NFI
└── data/
    ├── raw/                               # Cache file mentah asli yang diunduh dari internet
    ├── processed/                         # Dataset siap pakai dalam format .csv dan .parquet (11 tabel)
    ├── sqlite/
    │   └── forest_carbon_mrv_groundtruth.db # Database relasional SQLite berisi seluruh tabel
    └── metadata/
        ├── ingestion_manifest.json        # Manifest provenance lengkap (URL, DOI, SHA-256, timestamps)
        └── benchmark_summary_report.json  # Ringkasan metrik evaluasi formula standar terhadap ground truth
```

---

## Ringkasan Dataset yang Dihasilkan (`data/processed/`)

| Nama Tabel (`.csv` / `.parquet` / SQLite) | Level MRV | Jumlah Baris | Kolom | Deskripsi Singkat |
| :--- | :--- | ---: | ---: | :--- |
| `unified_ground_truth_benchmark` | **Master (Semua Level)** | **12.154** | 19 | Tabel gabungan terstandardisasi (`input_variables_json` $\rightarrow$ `formula_expression` $\rightarrow$ `ground_truth_outcome_value` + `timestamps`) |
| `level1_registry_projects_mrv` | Level 1 (Registry) | 1.042 | 22 | Proyek kredit karbon hutan dari **Verra VCS**, **Gold Standard**, **ACR**, **CAR**, **ART-TREES**, **Cercarbono** |
| `level1_registry_credit_issuances` | Level 1 (Registry) | 1.162 | 13 | Transaksi penerbitan kredit karbon terverifikasi beserta `vintage_year`, `transaction_date`, dan `quantity_issued_tCO2e` |
| `level1_verra_ifm_biophysical_mrv` | Level 1 (Biophysical MRV) | 74 | 43 | Proyek IFM (Verra VCSOPR, CAR, ACR) lengkap dengan pool karbon *baseline* vs *reporting period 1*, *leakage*, *buffer*, komposisi basal area spesies, & verifikasi formula |
| `level2_tree_allometry_groundtruth` | Level 2 (Pohon / Allometrik) | 5.228 | 38 | Data pohon tebang-timbang destruktif **Chave et al. (2014)** di 69 lokasi pantropis (**termasuk 537 pohon di 10 lokasi Indonesia: Kalimantan, Sumatra, Jawa Barat, Maluku**) |
| `level2_allodb_equations_catalog` | Level 2 (Katalog Formula) | 570 | 54 | Katalog 570 persamaan allometrik hutan *peer-reviewed* dari `ropensci/allodb` |
| `level2_plot_inventory_fia_neotropical` | Level 2 (Plot Lapangan) | 4.753 | 29 | Gabungan plot **USFS FIA / rFIA**, **Bennett et al. (2020)** (iklim & tanah), dan **Poorter et al. (2016) 2ndFOR** (suksesi hutan sekunder) |
| `level3_remote_sensing_lidar_sar_plots` | Level 3 (LiDAR + Plot) | 1.093 | 41 | Plot kalibrasi **ESA/NASA TropiSAR & AfriSAR** (`TCH`, `H50`, `GF20`, `STDV` LiDAR + `BA`, `WD`, `Ndens` $\rightarrow$ 3 formula AGB Chave & LiDAR) |
| `level3_remote_sensing_sentinel_optical_sar_plots` | Level 3 (Optik + SAR + Plot) | 305 | 80 | Plot lapangan dipasangkan dengan 12 band **Sentinel-2**, 35 indeks vegetasi (`NDVI`, `EVI`, `SAVI`, `NDRE`, `IRECI`), **Sentinel-1 SAR** (`VV`, `VH`), & topografi |
| `level3_national_nfi_satellite_intercomparison` | Level 3 (Nasional NFI vs Satelit) | 182 | 26 | Komparasi inventarisasi hutan nasional (**FAO FRA 2020 NFI**, termasuk Indonesia) vs peta biomassa satelit **ESA CCI** |
| `standard_formulas_benchmark_evaluation` | Evaluasi Benchmark | 13 | 15 | Hasil metrik akurasi (`RMSE`, `rRMSE%`, `MAE`, `MAPE%`, `Bias`, `R2`, `Lin's CCC`) dari seluruh formula standar terhadap ground truth |

---

## Cara Menjalankan Sistem

### 1. Menjalankan Pipeline Penarikan & Pembuatan Dataset
```bash
python3 run_pipeline.py
```
Untuk mengunduh ulang seluruh data mentah langsung dari server/API sumber (mengabaikan cache lokal):
```bash
python3 run_pipeline.py --force-refresh
```

### 2. Membandingkan Algoritma Kustom Anda dengan Ground Truth & Formula Standar
Buka dan jalankan [`compare_custom_algorithm.py`](file:///home/kenny/personal/github-clones/paper/compare_custom_algorithm.py):
```bash
python3 compare_custom_algorithm.py
```
Anda cukup memasukkan fungsi prediksi model/algoritma Anda ke dalam helper `evaluate_custom_algorithm()` dari [`src/evaluator.py`](file:///home/kenny/personal/github-clones/paper/src/evaluator.py) untuk mendapatkan tabel metrik komparasi siap publikasi (*paper-ready*).
