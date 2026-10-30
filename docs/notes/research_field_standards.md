# Research notes: field (right-grid) standards (verified 2026-10-30)

V = verified from the primary source, U = unverified.

## IPCC 2006 Vol. 4 + 2019 Refinement
- Five pools (Vol. 4 Ch. 1, Table 1.1) [V]: AGB, BGB, dead wood (>=10 cm), litter, SOM (30 cm).
- CF (Ch. 4, Table 4.3) [V]: tropical 0.47 (0.44-0.49). The 2019 Refinement makes no change.
- R, 2006 Table 4.4 [V]: tropical rainforest 0.37 (Fittkau & Klinge 1973).
  - Tropical moist deciduous: 0.20 if AGB<125, 0.24 if >125 (Mokany 2006).
  - Mountain: 0.27.
- R, 2019 Table 4.4 (Updated), Asia [V]
  - Tropical rainforest natural: 0.207 (SD 0.072) if AGB<=125; 0.212 (0.077) if >125.
  - Planted: 0.325 (0.025) if <=125.
  - Tropical moist natural: 0.323 (0.073) if <=125; 0.246 (0.036) if >125.
- Stock change (Vol. 4 Ch. 2) [V]
  - Eq. 2.4: gain-loss, dC = dC_G - dC_L.
  - Eq. 2.5: stock-difference, dC = (C_t2 - C_t1)/(t2 - t1).
  - Eq. 2.8: biomass-specific form. The same area is required at both dates.
- Uncertainty (Vol. 1 Ch. 3) [V]
  - Eq. 3.1, products: U = sqrt(sum U_i^2); valid for CV < ~0.3.
  - Eq. 3.2, sums: U = sqrt(sum (U_i x_i)^2) / |sum x_i|.
  - U = half the 95% CI / total, in %.
  - Approach 2 Monte Carlo: e.g. 10,000 iterations, or until the 95% CI is stable to +/-1%.

## SNI 7724:2011 [V]
- Scope: five pools, Tier 3.
- Sampling: stratified systematic or random, maximum sampling error 20%.
- Strata: land cover from imagery of 30 m or finer.
- Growth classes: semai (seedling) <2 cm & H<=1.5 m; pancang (sapling) 2-<10 cm; tiang (pole) 10-<20 cm; pohon (tree) >=20 cm.
- Nested plot: A 2x2 m (seedlings, litter, understorey); B 5x5 m (saplings); C 10x10 m (poles); D 20x20 m (trees).
  - Circular equivalents: r = 1.13, 2.82, 5.64, 11.29 m.
- DBH measured at 1.3 m, or 20 cm above the buttress.
- Dead wood
  - Standing: V = 1/4 pi (dbh/100)^2 t f, with f = 0.6.
  - Or allometric x integrity factor 0.9/0.8/0.7.
  - Down: Brereton formula.
- Litter/understorey: fresh weight -> ~300 g subsample -> oven at 70-85 C; B_o = (B_ks/B_bs) B_bt.
- Soil: C = Kd x rho x %C; composite of 5 points at depths 0-5, 5-10, 10-20, 20-30 cm.
- Formulas
  - B_bp = NAP x B_ap (NAP = root-to-shoot ratio; Lampiran A uses IPCC 2006, tropical rainforest 0.37).
  - C = B x 0.47.
  - C_n = C_x/1000 x 10000/l_plot.
  - C_plot = sum of pools.
  - C_stratum = mean(C_plot) x area.

## Indonesia national forest inventory (NFI), from the 2nd FRL (KLHK 2022, Annex 4) [V]
- 20 km grid; clusters of 3x3 plots of 100x100 m.
- Centre plot is a permanent sample plot (PSP) of 16 x 25x25 m recording units.
- Subplot radii: 1 m (seedlings), 2 m (saplings), 5 m (poles 5-19.9 cm); trees >=20 cm over the whole plot.
- Allometry: Manuri et al. 2017. Wood density: FORDA 2012. CF: 0.47.

## Verra VM0047 [V]
- v1.0 (2023): plot sampling, remeasurement every <=5 yr. Allometry preference: ecoregion-specific > global.
  - U_p = SE x t(90%).
  - Eq. 27: UNC = min(100%, max(0, U - 10%)).
- v1.1 (May 2025), section 8.5, Eq. 28
  - UNC_t = MIN(100%, MAX(0, (T x sqrt(SE0^2 + SEt^2 - 2 rho SE0 SEt)/dC - 0.10) x 100)).
  - T = two-tailed t at alpha 0.1; rho = permanent-plot correlation.
  - Eq. 32: CR = min(dC, dC(1-PB)) x (1-UNC) - PE - LK.
  - Zero credits if the 90% half-width exceeds 100%. Ex-ante minimum deduction 10%.
- VMD0017 v2.2 (REDD+) [V]: +/-15% at 95%; excess deducted (Eq. 22).

## CDM tools [V]
- AR-TOOL03 v2.1.0: n = N t^2 (sum w_i s_i)^2 / (N E^2 + t^2 sum w_i s_i^2).
  - Simplified: n = (t/E)^2 (sum w s)^2 if the sampled area is <5% of the project.
  - Neyman allocation: n_i = n w_i s_i / sum w s.
  - Iterate with df = n-1 if n < 30.
- AR-TOOL14 v04.2
  - Uncertainty = SE x t(90%) / mean; only sampling error counts.
  - Eq. 12: C = 44/12 x CF x B.
  - Eq. 14: b = sum w_i b_i.
  - Eq. 15: u = t sqrt(sum w_i^2 s_i^2/n_i) / b, with df = n - M.
  - Eq. 17: s_i^2 formula.
  - Discount table (Appendix 2), as a share of U: <=10% -> 0; 10-15 -> 25% of U; 15-20 -> 50%; 20-30 -> 75%; >30 -> 100%.
  - Worked example: n=34, mean 45.328, SD 12.776 -> 8.18%.

## Gold Standard A/R v2.1 (2024) [V]
- CF 0.475.
- Precision target +/-20% at 90%; the excess over 20% is deducted.

## Allometry and error models
- Chave et al. 2014 [V]
  - Eq. 4: 0.0673 (rho D^2 H)^0.976, RSE 0.357; bias +5.31%; underestimates trees >30 Mg by ~20%.
  - Eq. 7: exp[-1.803 - 0.976E + 0.976 ln rho + 2.673 ln D - 0.0299 (ln D)^2], RSE 0.413.
  - Eq. 6a: ln H = 0.893 - E + 0.760 ln D - 0.0340 (ln D)^2, RSE 0.243.
- Chave et al. 2004, Phil Trans B 359:409-420, doi:10.1098/rstb.2003.1425 [V]
  - DBH error: SD = 0.0062 D + 0.0904 for 95% of trees; SD = 4.64 cm for 5%.
  - Height error ~10%.
  - Within-plot s.e.m.: 16% at 0.1 ha, 10% at 0.25 ha, 5% at 1 ha.
  - Recommendations: plots >=0.25 ha; ~5 ha total for +/-10% at 95%.
- BIOMASS 2.1.4 source [V]: WD sd by level: species 0.0708, genus 0.0941, family 0.1234; truncation 0.08-1.39.
  - Allometric error: posterior of the Eq. 4 coefficients plus N(0, sd) on the log scale.
  - CF option: N(47.13, 2.06)% (Thomas & Martin 2012).
  - Output: 95% credibility interval.
- Basuki et al. 2009, FEM 257:1684-1694 [V]: East Kalimantan, n=122.
  - ln AGB = -0.744 + 2.188 ln D + 0.832 ln WD; SE 0.303, correction factor 1.047.
- Manuri et al. 2014 [citation V, coefficients U].
- HCSA Toolkit v2.0 Module 4 [V]
  - Plot: r 5.64 m (100 m^2) for DBH 5-14.9 cm; r 12.61 m (500 m^2) for DBH >=15 cm.
  - Classes HDF, MDF, LDF, YRF, S, OL. Target +/-10% at 90%.

## Palms
- Goodman et al. 2013, FEM 310:994-1004 [V], Amazonian palms: AGB^0.25 = 0.55512 (dmf D^2 H_stem)^0.25.
- Lewis et al. 2020, Sci Rep 10:2230 [V], oil palm: DW = 12.87 + 560.8 TVol; stand AGB 6.389 YAP - 17.59 Mg/ha.
