# Metodologi, Variabel Input, Formula Standar, dan Outcome Ground Truth MRV Karbon Hutan

Dokumen ini merangkum alur matematis (**Input Variabel $\rightarrow$ Formula Standar $\rightarrow$ Outcome Karbon + Timestamp**) yang diekstraksi dan diverifikasi oleh sistem dari berbagai *registry* karbon internasional (**Verra VCS**, **Gold Standard**, **ACR**, **CAR**, **ART-TREES**, **Cercarbono**) serta repositori inventarisasi plot ilmiah terbuka (**Chave et al. 2014 Pantropical Database**, **rOpenSci/ForestGEO allodb**, **USFS FIA**, **ESA/NASA TropiSAR & AfriSAR**, **Sentinel-2/1 Multi-Sensor Field Plots**, dan **FAO FRA 2020 NFI**).

---

## 1. Level 1: Proyek MRV & Registry Kredit Karbon (Verra VCS, Gold Standard, CAR, ACR, ART-TREES)

### 1.1 Formula Akuntansi Pool Karbon IFM (*Improved Forest Management* — Verra VCSOPR / CAR / ACR / CARB)
Digunakan pada proyek kehutanan terverifikasi di *registry* (lihat tabel `level1_verra_ifm_biophysical_mrv.csv`):

- **Variabel Input ($X$)**:
  - $\text{Area}_{\text{ha}}$: Luas area proyek hutan (hektar, dikonversi dari $\text{acreage} \times 0.4046856$)
  - $C_{\text{BL, IFM1}}$: Stok karbon *baseline* pohon hidup tegakan (*standing live trees*, $\text{tCO}_2\text{e}$)
  - $C_{\text{BL, IFM3}}$: Stok karbon *baseline* pohon mati tegakan (*standing dead wood*, $\text{tCO}_2\text{e}$)
  - $C_{\text{BL, IFM7}}$: Stok karbon *baseline* produk kayu terpakai (*in-use harvested wood products*, $\text{tCO}_2\text{e}$)
  - $C_{\text{BL, IFM8}}$: Stok karbon *baseline* produk kayu di *landfill* ($\text{tCO}_2\text{e}$)
  - $C_{\text{RP1, IFM1}}, C_{\text{RP1, IFM3}}, C_{\text{RP1, IFM7}}, C_{\text{RP1, IFM8}}$: Stok karbon aktual pada *Reporting Period 1* ($\text{tCO}_2\text{e}$)
  - $\text{SE}$: *Secondary Effects* / *Leakage* (kebocoran emisi di luar batas proyek, $\text{tCO}_2\text{e}$)
  - $\text{CD}$: *Confidence Deduction* (potongan ketidakpastian statistik sampling plot lapangan, $\text{tCO}_2\text{e}$)
  - $\text{Buffer}$: Kontribusi ke *buffer pool* asuransi risiko pembalikan (*reversal risk*, $\text{tCO}_2\text{e}$)
- **Formula Standar**:
  $$\Delta C_{\text{onsite}} = (C_{\text{RP1, IFM1}} - C_{\text{BL, IFM1}}) + (C_{\text{RP1, IFM3}} - C_{\text{BL, IFM3}})$$
  $$\Delta C_{\text{HWP}} = (C_{\text{RP1, IFM7}} - C_{\text{BL, IFM7}}) + (C_{\text{RP1, IFM8}} - C_{\text{BL, IFM8}})$$
  $$\text{Net Credits}_{\text{tCO}_2\text{e}} = \Delta C_{\text{onsite}} + \Delta C_{\text{HWP}} + \text{SE} - \text{CD}$$
- **Outcome ($Y$)**:
  - `outcome_formula_recalculated_tCO2e`: Hasil kalkulasi ulang langsung dari formula standar di atas
  - `outcome_registry_reported_tCO2e` & `outcome_registry_issued_tCO2e`: Jumlah kredit karbon terverifikasi ($\text{tCO}_2\text{e}$) yang diterbitkan
- **Timestamp**:
  - `data_generated_timestamp`: Rentang waktu periode pemantauan (`rp1_start_date` s/d `rp1_end_date`)
  - `data_ingested_timestamp_utc`: Waktu penarikan data oleh sistem (UTC ISO-8601)

### 1.2 Metodologi Verra VCS (REDD+ & ARR) dan Gold Standard A/R
Digunakan pada tabel `level1_registry_projects_mrv.csv` dan `level1_registry_credit_issuances.csv`:

| Kode Metodologi | Standar / Registry | Fokus Hutan | Formula Umum Pengurangan / Serapan Emisi Bersih ($\text{tCO}_2\text{e}$) |
| :--- | :--- | :--- | :--- |
| **VM0007** | Verra VCS | REDD+ Framework | $\text{NER}_t = (\Delta C_{\text{BSL}, t} - \Delta C_{\text{WPS}, t} - \Delta C_{\text{LK}, t}) \times (1 - f_{\text{buffer}})$ |
| **VM0015** | Verra VCS | Avoided Unplanned Deforestation | $\text{NER}_t = (A_{\text{BSL}, t} \cdot C_{\text{stock/ha}} - \Delta C_{\text{WPS}, t} - \Delta C_{\text{LK}, t}) \times (1 - f_{\text{buffer}})$ |
| **VM0047** | Verra VCS | Afforestation, Reforestation & Revegetation (ARR) | $\text{NER}_t = (\Delta C_{\text{ARR}} - \Delta C_{\text{BSL, matched}} - E_{\text{LK}}) \times (1 - f_{\text{buffer}})$ |
| **AR-ACM0003** | UNFCCC / Verra VCS | Afforestation & Reforestation | $\Delta C_{\text{AR}, t} = \frac{44}{12} \cdot \text{CF} \sum_i A_i \cdot \text{AGB}_i (1 + R_i) - \Delta C_{\text{BSL}, t} - \text{LK}_t$ |
| **Gold Standard A/R** | Gold Standard | Afforestation / Reforestation | $\text{VER}_t = \left(\sum_i A_i (\text{AGB}_i + \text{BGB}_i) \cdot \text{CF} \cdot \frac{44}{12} - C_{\text{BSL}, t} - \text{LK}_t\right)(1 - f_{\text{buffer}})$ |

---

## 2. Level 2: Allometrik Pohon & Inventarisasi Plot Lapangan (Pantropis & Indonesia)

Digunakan pada tabel `level2_tree_allometry_groundtruth.csv` (5.228 pohon yang ditebang & ditimbang kering secara destruktif, termasuk **10 lokasi hutan di Indonesia: Kalimantan, Sumatra, Jawa Barat, dan Maluku**).

### 2.1 Variabel Input ($X$)
- $D$ (`input_dbh_cm`): Diameter setinggi dada (*Diameter at Breast Height* pada $1,3\text{ m}$, dalam $\text{cm}$)
- $H$ (`input_height_m`): Tinggi total pohon (dalam $\text{m}$)
- $\rho$ (`input_wood_density_g_cm3`): Berat jenis / kerapatan kayu kering tanur (*Wood Specific Gravity*, dalam $\text{g/cm}^3$)
- $\text{TS}$ (`input_temp_seasonality_sd100`): *Temperature Seasonality* ($\text{SD} \times 100$)
- $\text{PS}$ (`input_precip_seasonality_cv`): *Precipitation Seasonality* ($\text{CV}\%$)
- $\text{CWD}$ (`input_cwd_mm`): *Climatic Water Deficit* ($\text{mm/tahun}$)
- $E$ (`input_chave_E_index`): Indeks cekaman bioklimatik Chave et al. (2014):
  $$E = (0,178 \times \text{TS} - 0,938 \times \text{CWD} - 6,61 \times \text{PS}) \times 10^{-3}$$

### 2.2 Empat Formula Allometrik Standar yang Dievaluasi
1. **Chave et al. (2014) Persamaan 4 (Pantropis dengan Tinggi Pohon $H$)**:
   $$\text{AGB}_{\text{kg}} = 0,0673 \times (\rho \cdot D^2 \cdot H)^{0,976}$$
2. **Chave et al. (2014) Persamaan 7 (Pantropis tanpa Tinggi Pohon, menggunakan Indeks Iklim $E$)**:
   $$\text{AGB}_{\text{kg}} = \exp\left(-1,803 - 0,976 E + 0,976 \ln(\rho) + 2,673 \ln(D) - 0,0299 (\ln D)^2\right)$$
3. **Ketterings et al. (2001) / Standar Nasional Indonesia (SNI 7724:2011) Hutan Sekunder Campuran (Sumatra/Kalimantan)**:
   $$\text{AGB}_{\text{kg}} = 0,11 \times \rho \times D^{2,62}$$
4. **Brown (1997) / UNFCCC CDM AR-ACM0003 Hutan Tropis Lembap**:
   $$\text{AGB}_{\text{kg}} = \exp\left(-2,134 + 2,530 \ln(D)\right)$$

### 2.3 Konversi Biomassa ke Stok Karbon ($C$) dan Ekuivalen $\text{CO}_2$ ($\text{CO}_2\text{e}$) — IPCC (2006 / 2019)
- **Fraksi Karbon Default IPCC (2006 Vol. 4 Ch. 4)**: $\text{CF} = 0,47\text{ tC / ton biomassa kering}$ (atau $\text{CF} = 0,50$ pada protokol USFS FIA / CARB)
- **Rasio Akar-Tajuk (*Root-to-Shoot Ratio*)**: $\text{BGB} = R \times \text{AGB}$ ($R = 0,24$ untuk hutan hujan tropis)
- **Konversi Stokiometri Karbon ke $\text{CO}_2\text{e}$**:
  $$C = \text{CF} \times \text{Biomassa}, \qquad \text{CO}_2\text{e} = C \times \frac{44}{12} = C \times 3,6667$$

---

## 3. Level 3: Penginderaan Jauh (LiDAR, SAR, & Spektral Optik Sentinel-2) + Plot Kalibrasi Lapangan

### 3.1 Model Allometrik-Struktural Airborne LiDAR (ESA/NASA TropiSAR & AfriSAR — Labrière, Chave, Saatchi et al. 2018)
Digunakan pada tabel `level3_remote_sensing_lidar_sar_plots.csv` (1.093 plot kalibrasi di French Guiana dan Gabon):
- **Variabel Input ($X$)**:
  - $\text{TCH}$ (`input_lidar_tch_mean_m`): Rata-rata tinggi pucuk kanopi (*Top-of-Canopy Height*) dari LiDAR CHM resolusi $1\text{ m}$ ($\text{m}$)
  - $H_{50}$ (`input_lidar_h50_median_m`): Median tinggi kanopi LiDAR ($\text{m}$)
  - $\text{GF}_{20}$ (`input_lidar_gap_fraction_20m`): Fraksi celah kanopi pada ketinggian $20\text{ m}$ ($\text{Canopy Cover}_{20\text{m}} = 1 - \text{GF}_{20}$)
  - $\text{STDV}$ (`input_lidar_height_stdv_m`): Simpangan baku tinggi kanopi LiDAR ($\text{m}$)
  - $\text{BA}$ (`input_basal_area_m2_ha`): Bidang dasar tegakan (*Basal Area*, $\text{m}^2/\text{ha}$)
  - $\rho$ (`input_wood_density_g_cm3`): Rata-rata tertimbang kerapatan kayu ($\text{g/cm}^3$)
  - $N_{\text{dens}}$ (`input_stem_density_ha`): Kerapatan batang pohon ($\text{pohon/ha}$)
- **Formula Standar**:
  $$\text{AGB}_{\text{LiDAR}} = 6,021 \times \text{TCH}^{0,3344} \times \text{BA}^{0,9605} \times \rho^{0,7604} \quad (\text{Mg/ha})$$
- **Outcome Ground Truth ($Y$)**:
  - `outcome_agb_loc_Mg_ha`: Biomassa plot ($\text{Mg/ha}$) dari persamaan Chave et al. (2014) Eq. 4 dengan kurva $H-D$ lokal
  - `outcome_agb_fph_Mg_ha`: Biomassa plot ($\text{Mg/ha}$) dengan kurva $H-D$ regional Feldpausch et al. (2012)
  - `outcome_agb_chv_Mg_ha`: Biomassa plot ($\text{Mg/ha}$) dengan persamaan Chave et al. (2014) Eq. 7 (indeks $E$)
  - `outcome_co2e_loc_tCO2e_ha`: Stok karbon ekuivalen ($\text{tCO}_2\text{e/ha}$)

### 3.2 Multi-Sensor Optik Sentinel-2 (B1–B12, NDVI, EVI, Red-Edge) & SAR Sentinel-1 (VV, VH)
Digunakan pada tabel `level3_remote_sensing_sentinel_optical_sar_plots.csv` (305 plot inventarisasi hutan):
- **Variabel Input ($X$)**:
  - Reflektansi permukaan Sentinel-2 MSI: Band `B1` s/d `B12`
  - Hamburan balik (*backscatter*) radar C-band Sentinel-1 SAR: `VV`, `VH`, `VV/VH`, `VH+VV`, `VH-VV`
  - Topografi & Iklim: Elevasi (`ele`, $\text{m}$), Kemiringan lereng (`slope`, derajat), Aspek (`aspect`), Suhu (`Temp`, $^\circ\text{C}$), Presipitasi musim tumbuh (`GSP`, $\text{mm}$)
- **Formula Indeks Vegetasi Spektral yang Diverifikasi**:
  $$\text{NDVI} = \frac{B_8 - B_4}{B_8 + B_4}, \qquad \text{SAVI} = \frac{1,5(B_8 - B_4)}{B_8 + B_4 + 0,5}, \qquad \text{NDRE} = \frac{B_8 - B_5}{B_8 + B_5}, \qquad \text{IRECI} = \frac{B_7 - B_4}{B_5 / B_6}$$
- **Outcome Ground Truth ($Y$)**:
  - `outcome_agb_Mg_ha` ($\text{Mg/ha}$), `outcome_carbon_tC_ha` ($\text{tC/ha}$), dan `outcome_co2e_tCO2e_ha` ($\text{tCO}_2\text{e/ha}$).
