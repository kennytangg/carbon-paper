# Research notes: cloud cover and uncertainty (verified 2026-10-30)

Status labels: [V] verified from the primary source; [V2] verified from a secondary source only; [U] unverified, do not cite.

## Cloud frequency
- Wilson & Jetz 2016, PLoS Biol 14(3):e1002415, doi:10.1371/journal.pbio.1002415 [V]
  - Global median cloud frequency 51%.
  - Southeast Asia, Congo and equatorial South America: >=80%.
  - Tropical/subtropical moist forest biome mean 80.1 +/- 9.5%.
  - Intra-annual SD low (~5.6-5.9%), so there is no reliable clear season.
- Sudmanns et al. 2020, IJDE 13(7):768-784, doi:10.1080/17538947.2019.1572799 [V]
  - Tropical Indonesia: only 0-1 cloud-free S2 scenes in 2017 (scene metadata).
  - More acquisitions does not mean more clear scenes.
- Asner 2001, IJRS 22(18):3855-3862, doi:10.1080/01431160010006926 [V citation; numbers U]
- Ju & Roy 2008, RSE 112(3):1196-1211, doi:10.1016/j.rse.2007.08.011 [V]
- Li & Roy 2017, Remote Sens 9(9):902, doi:10.3390/rs9090902 [V]: S2A+S2B+L8 global median revisit 2.9 days.
- No published Kalimantan S2 clear fraction found, so our measurement is novel.

## Cloud masks
- Zhu & Woodcock 2012, RSE 118:83-94, doi:10.1016/j.rse.2011.10.028 [V]: Fmask, 96.4% overall accuracy.
- Qiu, Zhu, He 2019, RSE 231, doi:10.1016/j.rse.2019.05.024 [V2]: Fmask 4.0 S2 94.3% vs Sen2Cor 87.1%.
- Skakun et al. 2022, RSE 274:112990, doi:10.1016/j.rse.2022.112990 [V; numbers V2]: CMIX, S2 mean overall accuracy 80.0-89.4% depending on reference set; thin cloud is the main issue.
- Pasquarella et al. 2023, CVPRW pp. 2125-2135, doi:10.1109/CVPRW59228.2023.00206 [V]: Cloud Score+, cs/cs_cdf, threshold 0.5-0.65.
- Sen2Cor SCL overall accuracy ~80-90% [V2].

## Ways around clouds
- Reiche et al. 2016, Nat Clim Change 6:120-122, doi:10.1038/nclimate2919 [V]: SAR/optical fusion.
- White et al. 2014, CJRS 40(3):192-212, doi:10.1080/07038992.2014.945827 [V]: best-available-pixel compositing.
- Griffiths et al. 2013, IEEE JSTARS 6(5):2088-2101, doi:10.1109/JSTARS.2012.2228167 [V]
- Claverie et al. 2018, RSE 219:145-161, doi:10.1016/j.rse.2018.09.002 [V]: HLS.
- Meraner et al. 2020, ISPRS JPRS 166:333-346, doi:10.1016/j.isprsjprs.2020.05.013 [V]: DSen2-CR, SAR-to-optical cloud removal.
- Neverova et al. 2016, IEEE TPAMI, doi:10.1109/TPAMI.2015.2461544 [V]: ModDrop (modality dropout).
- Mermoz et al. 2015, RSE 159:307-317, doi:10.1016/j.rse.2014.12.019 [V]
- NISAR launched 30 Jul 2025 [V]; L-band biomass requirement 20 Mg/ha where AGB <100 [V2].
- ESA BIOMASS launched 29 Apr 2025 [V]; P-band, 200 m, 20% accuracy target [V2].

## Benchmarks: satellite AGB vs field
- Berninger et al. 2018, Remote Sens 10(6):831, doi:10.3390/rs10060831 [V]
  - Kalimantan, S1 + PALSAR, rRMSE 31-38%, RMSE 53-57 t/ha.
  - Validated against a LiDAR-upscaled layer, so not blind.
  - Underestimates above 200 t/ha by 34-42 t/ha.
- Jucker et al. 2018, Biogeosciences 15:3811-3830, doi:10.5194/bg-15-3811-2018 [V]
  - Sabah, airborne lidar (ALS), RMSE 39.3 Mg C/ha.
  - Plot-level error 25.0% at 0.1 ha, 19.5% at 0.25 ha, 16.2% at 0.5 ha, 13.4% at 1 ha.
- Araza et al. 2022, RSE 272:112917, doi:10.1016/j.rse.2022.112917 [V]
  - CCI RMSD by AGB bin: 0-50: 29; 100-150: 50; 200-250: 61; 300-400: 107; >400: 503 Mg/ha.
  - The CCI SD layer is pessimistic.
  - Plot error budget: measurement SD 93.9, sampling 51.6, temporal 24.6 Mg/ha (73/22/5% of variance).
  - Map-error spatial correlation range 50-104 km.
- Santoro et al. 2021, ESSD 13:3927-3950, doi:10.5194/essd-13-3927-2021 [V]: saturation ~250 Mg/ha; mean relative SD ~50%.
- Duncanson et al. 2022, RSE 270:112845, doi:10.1016/j.rse.2021.112845 [V]
  - GEDI L4A; island Southeast Asia under-represented.
  - Asia evergreen broadleaf %RMSE 78.9 [V2].
- Dubayah et al. 2022, ERL 17(9):095001 [V]: GEDI L4B.
- Réjou-Méchain et al. 2014, Biogeosciences 11:6827-6840 [V]: local CV 46.3% at 0.1 ha, 16.6% at 1 ha.
- Duncanson et al. 2019, Surv Geophys 40(4):979-999, doi:10.1007/s10712-019-09538-8 [V]
  - Use plots of 1 ha or more; plots under 0.25 ha carry ~30% error.
  - ~10 m geolocation error under canopy.
  - A +/-5 yr date gap is acceptable where change is slow.
- Réjou-Méchain et al. 2019, Surv Geophys 40(4):881-911, doi:10.1007/s10712-019-09532-0 [V; specific recommendations U]
- Duncanson et al. (eds) 2021, CEOS AGB Validation Protocol v1.0, doi:10.5067/doc/ceoswgcv/lpv/agb.001 [V]

## Conformal prediction
- Lei et al. 2018, JASA 113(523):1094-1111, doi:10.1080/01621459.2017.1307116 [V]
  - q = ceil((n+1)(1-a))-th smallest score.
  - Coverage in [1-a, 1-a+1/(n+1)].
- Romano, Patterson, Candès 2019, NeurIPS 32:3543-3553, arXiv:1905.03222 [V]
  - Score E = max(qlo - y, y - qhi) (Eq. 14).
  - Interval [qlo - Q, qhi + Q] (Eq. 15).
- Papadopoulos, Gammerman, Vovk 2008, Proc. IASTED AIA, pp. 64-69 [V]: normalized nonconformity.
- Boström & Johansson 2020, PMLR 128:114-133 [V]: Mondrian conformal regressors.
- Tibshirani et al. 2019, NeurIPS 32:2530-2540, arXiv:1904.06019 [V]: weighted conformal under covariate shift.
- Mao, Martin, Reich 2024, JASA 119(546):904-914, doi:10.1080/01621459.2022.2147531 [V]: spatial conformal.

## Standards
- IPCC reports uncertainty as the 95% CI half-width [V2].
- Verra uses the 90% CI [V2]. VM0048 deducts uncertainty above 10%, e.g. 19.9% gives a 9.9% deduction [V2].
- ART-TREES: 90% CI with Monte Carlo [V2].
- FCPF: no deduction at <=15% uncertainty [V2].
