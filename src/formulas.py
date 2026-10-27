"""
Standardized Mathematical Formulas for Forest Carbon MRV Ground Truth.

Covers three hierarchical levels of Forest Carbon MRV:
1. Level 1 - Registry Project MRV (Verra VCS VM0007/VM0015/VM0047/AR-ACM0003,
   Gold Standard A/R, CARB/CAR/ACR Improved Forest Management Protocol)
2. Level 2 - Tree & Plot Allometric Biomass & Carbon Equations (Chave et al. 2014
   Eq. 4 & Eq. 7, Ketterings et al. 2001 Indonesia, Brown 1997 UNFCCC, IPCC 2006/2019 Tier 1/2)
3. Level 3 - Remote Sensing (Airborne/Spaceborne LiDAR Canopy Height, Sentinel-2 Optical
   Spectral Indices, Sentinel-1 SAR Backscatter) to Forest Biomass/Carbon Equations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Any, Optional
import numpy as np


# Constants defined by IPCC (2006 / 2019 Refinement) & UNFCCC
MOLECULAR_WEIGHT_RATIO_CO2_C: float = 44.0 / 12.0  # 3.6666666667 tCO2e per tC
IPCC_DEFAULT_CARBON_FRACTION_TROPICAL: float = 0.47  # tC per Mg dry biomass (IPCC 2006 Vol.4 Ch.4 Table 4.3)
FIA_CARB_CARBON_FRACTION: float = 0.50  # tC per ton dry biomass (USFS FIA / CARB Forest Protocol)
IPCC_ROOT_TO_SHOOT_TROPICAL_RAINFOREST: float = 0.24  # BGB / AGB ratio (IPCC 2006 Table 4.4 / Mokany 2006)
IPCC_ROOT_TO_SHOOT_TEMPERATE: float = 0.26
ACRES_TO_HECTARES: float = 0.40468564224
SHORT_TON_TO_METRIC_TON: float = 0.90718474


@dataclass(frozen=True)
class FormulaMetadata:
    """Metadata describing a standard MRV or allometric mathematical formula."""

    formula_id: str
    name: str
    standard_or_citation: str
    level: str
    expression_latex: str
    expression_code: str
    input_variables: Dict[str, str]
    output_variable: str
    output_unit: str
    notes: str


FORMULA_REGISTRY: Dict[str, FormulaMetadata] = {
    "CHAVE_2014_EQ4": FormulaMetadata(
        formula_id="CHAVE_2014_EQ4",
        name="Chave et al. (2014) Pantropical Allometric Equation 4 (with Tree Height)",
        standard_or_citation="Chave et al. (2014) Global Change Biology 20(10):3177-3190; Verra VCS VM0007/VM0015/VM0047 & Gold Standard A/R",
        level="tree_allometry",
        expression_latex=r"\text{AGB}_{\text{kg}} = 0.0673 \times (\rho \cdot D^2 \cdot H)^{0.976}",
        expression_code="0.0673 * ((wood_density_g_cm3 * (dbh_cm ** 2) * height_m) ** 0.976)",
        input_variables={
            "dbh_cm": "Diameter at breast height (1.3m) in cm",
            "height_m": "Total tree height in m",
            "wood_density_g_cm3": "Oven-dry wood specific gravity (g/cm^3)",
        },
        output_variable="agb_kg",
        output_unit="kg dry matter / tree",
        notes="Gold-standard pantropical equation when total tree height H is directly measured or derived from local H-D curves.",
    ),
    "CHAVE_2014_EQ7": FormulaMetadata(
        formula_id="CHAVE_2014_EQ7",
        name="Chave et al. (2014) Pantropical Allometric Equation 7 (Bioclimatic Stress E, without Height)",
        standard_or_citation="Chave et al. (2014) Global Change Biology 20(10):3177-3190; Verra VCS REDD+ & IPCC Tier 2/3",
        level="tree_allometry",
        expression_latex=r"\text{AGB}_{\text{kg}} = \exp(-1.803 - 0.976 E + 0.976 \ln(\rho) + 2.673 \ln(D) - 0.0299 (\ln D)^2)",
        expression_code="exp(-1.803 - 0.976 * E + 0.976 * ln(wood_density_g_cm3) + 2.673 * ln(dbh_cm) - 0.0299 * (ln(dbh_cm) ** 2))",
        input_variables={
            "dbh_cm": "Diameter at breast height (1.3m) in cm",
            "wood_density_g_cm3": "Oven-dry wood specific gravity (g/cm^3)",
            "E": "Bioclimatic environmental stress index: E = (0.178*TS - 0.938*CWD - 6.61*PS) * 1e-3",
        },
        output_variable="agb_kg",
        output_unit="kg dry matter / tree",
        notes="Used when tree height H is unavailable; incorporates temperature seasonality (TS), climatic water deficit (CWD), and precipitation seasonality (PS).",
    ),
    "KETTERINGS_2001_INDONESIA": FormulaMetadata(
        formula_id="KETTERINGS_2001_INDONESIA",
        name="Ketterings et al. (2001) Indonesian Mixed Secondary Forest Equation (SNI 7724)",
        standard_or_citation="Ketterings et al. (2001) Forest Ecology and Management 146:199-209; Standar Nasional Indonesia (SNI 7724:2011)",
        level="tree_allometry",
        expression_latex=r"\text{AGB}_{\text{kg}} = 0.11 \times \rho \times D^{2.62}",
        expression_code="0.11 * wood_density_g_cm3 * (dbh_cm ** 2.62)",
        input_variables={
            "dbh_cm": "Diameter at breast height (1.3m) in cm",
            "wood_density_g_cm3": "Oven-dry wood specific gravity (g/cm^3)",
        },
        output_variable="agb_kg",
        output_unit="kg dry matter / tree",
        notes="Widely used across Indonesian (Sumatra/Kalimantan) MRV and National Forest Inventory (NFI) protocols.",
    ),
    "BROWN_1997_UNFCCC": FormulaMetadata(
        formula_id="BROWN_1997_UNFCCC",
        name="Brown (1997) / UNFCCC CDM Moist Tropical Forest Equation",
        standard_or_citation="Brown (1997) FAO Forestry Paper 134; UNFCCC CDM AR-ACM0003 / Verra VCS",
        level="tree_allometry",
        expression_latex=r"\text{AGB}_{\text{kg}} = \exp(-2.134 + 2.530 \ln(D))",
        expression_code="exp(-2.134 + 2.530 * ln(dbh_cm))",
        input_variables={
            "dbh_cm": "Diameter at breast height (1.3m) in cm",
        },
        output_variable="agb_kg",
        output_unit="kg dry matter / tree",
        notes="Classic single-variable DBH allometric equation for moist tropical forests.",
    ),
    "IPCC_2006_2019_CARBON_CONVERSION": FormulaMetadata(
        formula_id="IPCC_2006_2019_CARBON_CONVERSION",
        name="IPCC (2006/2019) Biomass to Total Carbon Stock & CO2e Conversion",
        standard_or_citation="IPCC (2006 / 2019 Refinement) Guidelines for National GHG Inventories Vol. 4 AFOLU Ch. 4",
        level="plot_inventory",
        expression_latex=r"\text{BGB} = R \cdot \text{AGB}; \quad C = \text{CF} \cdot (\text{AGB} + \text{BGB}); \quad \text{CO}_2\text{e} = C \cdot \frac{44}{12}",
        expression_code="total_co2e = agb * (1 + root_to_shoot_ratio) * carbon_fraction * (44.0 / 12.0)",
        input_variables={
            "agb": "Aboveground dry biomass (kg or Mg/ha)",
            "root_to_shoot_ratio": "Belowground-to-aboveground biomass ratio R (default 0.24 tropical, 0.26 temperate, or 0.0 for AGB-only)",
            "carbon_fraction": "Carbon fraction of dry matter CF (default 0.47 IPCC, 0.50 FIA/CARB)",
        },
        output_variable="co2e",
        output_unit="kg CO2e or tCO2e/ha",
        notes="Standard conversion from dry biomass to elemental carbon (tC) and carbon dioxide equivalent (tCO2e).",
    ),
    "CARB_VERRA_ACR_CAR_IFM_CREDITING": FormulaMetadata(
        formula_id="CARB_VERRA_ACR_CAR_IFM_CREDITING",
        name="Improved Forest Management (IFM) Net GHG Reductions Formula (Verra VCSOPR / CAR / ACR / CARB)",
        standard_or_citation="CARB Compliance Offset Protocol U.S. Forest Projects (2015) & Verra/CAR/ACR IFM Registry Reporting",
        level="registry_project_mrv",
        expression_latex=r"\text{ARBOCs} = (\Delta C_{\text{IFM1}} + \Delta C_{\text{IFM3}}) + (\Delta C_{\text{IFM7}} + \Delta C_{\text{IFM8}}) + \text{SE} - \text{CD}",
        expression_code="((rp_ifm1 - bl_ifm1) + (rp_ifm3 - bl_ifm3)) + ((rp_ifm7 - bl_ifm7) + (rp_ifm8 - bl_ifm8)) + secondary_effects - confidence_deduction",
        input_variables={
            "bl_ifm1": "Baseline standing live carbon trees (tCO2e)",
            "bl_ifm3": "Baseline standing dead carbon (tCO2e)",
            "bl_ifm7": "Baseline in-use harvested wood products carbon (tCO2e)",
            "bl_ifm8": "Baseline landfilled wood products carbon (tCO2e)",
            "rp_ifm1": "Reporting period standing live carbon (tCO2e)",
            "rp_ifm3": "Reporting period standing dead carbon (tCO2e)",
            "rp_ifm7": "Reporting period in-use harvested wood products carbon (tCO2e)",
            "rp_ifm8": "Reporting period landfilled wood products carbon (tCO2e)",
            "secondary_effects": "Leakage / secondary effects adjustment (tCO2e, typically negative)",
            "confidence_deduction": "Statistical sampling uncertainty deduction (tCO2e)",
        },
        output_variable="net_credits_tCO2e",
        output_unit="tCO2e",
        notes="Exact registry accounting equation linking pool-level forest carbon inventory inputs to verified carbon credits issued.",
    ),
    "LABRIERE_CHAVE_2018_LIDAR_AGB": FormulaMetadata(
        formula_id="LABRIERE_CHAVE_2018_LIDAR_AGB",
        name="Asner & Mascaro (2014) / Labrière, Chave & Saatchi (2018) Airborne LiDAR + Basal Area + Wood Density AGB Formula",
        standard_or_citation="Asner & Mascaro (2014) Remote Sensing of Environment 140:614-624; Labrière et al. (2018) IEEE JSTARS 11(10):3617-3627",
        level="remote_sensing_plot",
        expression_latex=r"\text{AGB}_{\text{Mg/ha}} = 6.021 \cdot \text{TCH}^{0.3344} \cdot \text{BA}^{0.9605} \cdot \text{WD}^{0.7604}",
        expression_code="6.021 * (tch_m ** 0.3344) * (basal_area_m2_ha ** 0.9605) * (wood_density_g_cm3 ** 0.7604)",
        input_variables={
            "tch_m": "Mean Top-of-Canopy Height from 1m LiDAR Canopy Height Model (m)",
            "basal_area_m2_ha": "Plot basal area (m^2/ha)",
            "wood_density_g_cm3": "Basal-area-weighted mean wood density (g/cm^3)",
        },
        output_variable="agb_Mg_ha",
        output_unit="Mg/ha",
        notes="Integrates remote sensing canopy structure (TCH) with stand basal area and wood density (R^2 = 0.943 across TropiSAR/AfriSAR).",
    ),
    "SENTINEL2_SPECTRAL_INDICES_AND_AGB": FormulaMetadata(
        formula_id="SENTINEL2_SPECTRAL_INDICES_AND_AGB",
        name="Sentinel-2 Spectral Vegetation Indices (NDVI, EVI, SAVI, NDRE) & Plot Biomass Conversion",
        standard_or_citation="ESA Sentinel-2 MSI Spectral Index Definitions & IPCC (2006) Plot Biomass-to-Carbon Conversion",
        level="remote_sensing_plot",
        expression_latex=r"\text{NDVI} = \frac{B_8 - B_4}{B_8 + B_4}, \quad \text{SAVI} = \frac{1.5(B_8 - B_4)}{B_8 + B_4 + 0.5}, \quad \text{NDRE} = \frac{B_8 - B_5}{B_8 + B_5}",
        expression_code="ndvi = (B8 - B4) / (B8 + B4); carbon_tC_ha = 0.47 * biomass_Mg_ha; co2e_t_ha = carbon_tC_ha * (44/12)",
        input_variables={
            "B2": "Sentinel-2 Band 2 Blue (490 nm)",
            "B4": "Sentinel-2 Band 4 Red (665 nm)",
            "B5": "Sentinel-2 Band 5 Red-Edge 1 (705 nm)",
            "B6": "Sentinel-2 Band 6 Red-Edge 2 (740 nm)",
            "B7": "Sentinel-2 Band 7 Red-Edge 3 (783 nm)",
            "B8": "Sentinel-2 Band 8 NIR (842 nm)",
            "VV": "Sentinel-1 SAR C-band VV backscatter",
            "VH": "Sentinel-1 SAR C-band VH backscatter",
            "ele": "Elevation (m)",
            "slope": "Slope (degrees)",
        },
        output_variable="co2e_tCO2e_ha",
        output_unit="tCO2e/ha",
        notes="Verifies exact spectral index derivation from raw Sentinel-2 surface reflectance bands and converts field plot AGB to tC/ha and tCO2e/ha.",
    ),
    "LASELVA_BROWN_WET_FOREST_PLOT_AGB": FormulaMetadata(
        formula_id="LASELVA_BROWN_WET_FOREST_PLOT_AGB",
        name="Repeated-Census Plot AGB Stock (Brown Tropical Wet Forest Allometry) & Annual Change",
        standard_or_citation="Brown (1997) FAO Forestry Paper 134; Clark et al. (2019) PLOS ONE 14(11):e0224896; IPCC (2006) carbon fraction",
        level="plot_time_series",
        expression_latex=r"\text{AGB}_{\text{Mg/ha}} = \frac{\sum_i \text{EAGB}_i}{1000 \cdot A_{\text{plot}}}, \quad \text{CO}_2e = 0.47 \cdot \text{AGB} \cdot \frac{44}{12}",
        expression_code="co2e_tCO2e_ha = 0.47 * (sum(eagb_kg) / 1000 / plot_area_ha) * (44/12)",
        input_variables={
            "n_stems_ge10cm": "Number of live stems >= 10 cm DBH in the plot-year census",
            "eagb_kg_sum": "Sum of stem-level estimated above-ground biomass (kg) in the plot",
            "plot_area_ha": "Plot area (0.5 ha)",
            "census_year": "Year of the annual diameter census",
        },
        output_variable="co2e_tCO2e_ha",
        output_unit="tCO2e/ha",
        notes="Annual re-measurement of the same plots enables timestamp-specific scoring and year-over-year net change (delta_co2e_tCO2e_ha_yr).",
    ),
}


def compute_chave_environmental_index_E(
    temp_seasonality_sd_100: float | np.ndarray,
    cwd_mm: float | np.ndarray,
    precip_seasonality_cv: float | np.ndarray,
) -> float | np.ndarray:
    """
    Compute Chave et al. (2014) Eq. 6b environmental stress parameter E:
        E = (0.178 * TS - 0.938 * CWD - 6.61 * PS) * 1e-3
    where:
        TS = Temperature seasonality (standard deviation * 100 from WorldClim bio4)
        CWD = Climatic Water Deficit (mm/yr, negative values or magnitude per Chave 2014)
        PS = Precipitation seasonality (coefficient of variation % from WorldClim bio15)
    Note: In Chave et al. (2014) data-raw/Allometry-database-2012n_envsub.csv, CWD is stored
    as negative numbers (e.g. -402.6), so -0.938 * CWD uses the signed CWD directly.
    """
    return (0.178 * temp_seasonality_sd_100 - 0.938 * cwd_mm - 6.61 * precip_seasonality_cv) * 1e-3


def chave_2014_eq4_agb_kg(
    dbh_cm: float | np.ndarray,
    height_m: float | np.ndarray,
    wood_density_g_cm3: float | np.ndarray,
) -> float | np.ndarray:
    """
    Chave et al. (2014) Equation 4 (Pantropical with Tree Height H):
        AGB (kg) = 0.0673 * (WD * D^2 * H)^0.976
    """
    comp = wood_density_g_cm3 * (np.power(dbh_cm, 2)) * height_m
    return 0.0673 * np.power(comp, 0.976)


def chave_2014_eq7_agb_kg(
    dbh_cm: float | np.ndarray,
    wood_density_g_cm3: float | np.ndarray,
    env_index_E: float | np.ndarray,
) -> float | np.ndarray:
    """
    Chave et al. (2014) Equation 7 (Pantropical without Tree Height, using E):
        AGB (kg) = exp(-1.803 - 0.976 * E + 0.976 * ln(WD) + 2.673 * ln(D) - 0.0299 * (ln(D))^2)
    """
    ln_d = np.log(dbh_cm)
    ln_wd = np.log(wood_density_g_cm3)
    log_agb = -1.803 - 0.976 * env_index_E + 0.976 * ln_wd + 2.673 * ln_d - 0.0299 * (ln_d ** 2)
    return np.exp(log_agb)


def ketterings_2001_indonesia_agb_kg(
    dbh_cm: float | np.ndarray,
    wood_density_g_cm3: float | np.ndarray,
) -> float | np.ndarray:
    """
    Ketterings et al. (2001) Indonesian Mixed Secondary Forest Allometric Equation:
        AGB (kg) = 0.11 * WD * D^2.62
    """
    return 0.11 * wood_density_g_cm3 * np.power(dbh_cm, 2.62)


def brown_1997_moist_tropical_agb_kg(
    dbh_cm: float | np.ndarray,
) -> float | np.ndarray:
    """
    Brown (1997) / UNFCCC AR-ACM0003 Moist Tropical Equation:
        AGB (kg) = exp(-2.134 + 2.530 * ln(D))
    """
    return np.exp(-2.134 + 2.530 * np.log(dbh_cm))


def biomass_to_carbon_and_co2e(
    agb: float | np.ndarray,
    carbon_fraction: float = IPCC_DEFAULT_CARBON_FRACTION_TROPICAL,
    include_bgb: bool = False,
    root_to_shoot_ratio: float = IPCC_ROOT_TO_SHOOT_TROPICAL_RAINFOREST,
) -> Dict[str, float | np.ndarray]:
    """
    Convert Above-Ground Biomass (AGB, in kg or Mg/ha) to:
    - Below-Ground Biomass (BGB)
    - Total Biomass (AGB + BGB)
    - Carbon Stock (C = CF * Biomass)
    - Carbon Dioxide Equivalent (CO2e = C * 44 / 12)
    """
    bgb = agb * root_to_shoot_ratio if include_bgb else np.zeros_like(agb, dtype=float)
    total_biomass = agb + bgb
    carbon = total_biomass * carbon_fraction
    co2e = carbon * MOLECULAR_WEIGHT_RATIO_CO2_C
    return {
        "agb": agb,
        "bgb": bgb,
        "total_biomass": total_biomass,
        "carbon": carbon,
        "co2e": co2e,
    }


def compute_ifm_net_credits_tco2e(
    bl_ifm1: float,
    bl_ifm3: float,
    bl_ifm7: float,
    bl_ifm8: float,
    rp_ifm1: float,
    rp_ifm3: float,
    rp_ifm7: float,
    rp_ifm8: float,
    secondary_effects: float = 0.0,
    confidence_deduction: float = 0.0,
) -> float:
    """
    Compute Net GHG Emission Reductions (ARBOCs / VCUs in tCO2e) for Improved Forest Management
    projects under the CARB / Verra VCSOPR / CAR / ACR U.S. Forest Offset Protocol:
        Net Credits = ((RP_IFM1 - BL_IFM1) + (RP_IFM3 - BL_IFM3))
                    + ((RP_IFM7 - BL_IFM7) + (RP_IFM8 - BL_IFM8))
                    + secondary_effects - confidence_deduction
    """
    delta_onsite = (rp_ifm1 - bl_ifm1) + (rp_ifm3 - bl_ifm3)
    delta_hwp = (rp_ifm7 - bl_ifm7) + (rp_ifm8 - bl_ifm8)
    return float(delta_onsite + delta_hwp + secondary_effects - confidence_deduction)


def compute_lidar_plot_agb_mg_ha(
    tch_m: float | np.ndarray,
    basal_area_m2_ha: float | np.ndarray,
    wood_density_g_cm3: float | np.ndarray,
) -> float | np.ndarray:
    """
    Compute plot-level AGB (Mg/ha) from Airborne LiDAR Top-of-Canopy Height (TCH, m),
    stand Basal Area (BA, m^2/ha), and basal-area-weighted Wood Density (WD, g/cm^3)
    using the power-law structural-allometric relationship (Asner & Mascaro 2014 /
    Labrière, Chave, Saatchi et al. 2018):
        AGB_pred (Mg/ha) = 6.021 * (TCH ^ 0.3344) * (BA ^ 0.9605) * (WD ^ 0.7604)
    """
    return 6.021 * (np.power(tch_m, 0.3344)) * (np.power(basal_area_m2_ha, 0.9605)) * (np.power(wood_density_g_cm3, 0.7604))


def compute_sentinel2_spectral_indices(
    b2_blue: float | np.ndarray,
    b4_red: float | np.ndarray,
    b5_re1: float | np.ndarray,
    b6_re2: float | np.ndarray,
    b7_re3: float | np.ndarray,
    b8_nir: float | np.ndarray,
) -> Dict[str, float | np.ndarray]:
    """
    Compute standard optical vegetation indices from Sentinel-2 surface reflectance bands:
    - NDVI = (B8 - B4) / (B8 + B4)
    - SR   = B8 / B4
    - DVI  = B8 - B4
    - SAVI = 1.5 * (B8 - B4) / (B8 + B4 + 0.5)
    - NDRE = (B8 - B5) / (B8 + B5)
    - IRECI = (B7 - B4) / (B5 / B6)
    """
    eps = 1e-12
    ndvi = (b8_nir - b4_red) / (b8_nir + b4_red + eps)
    sr = b8_nir / (b4_red + eps)
    dvi = b8_nir - b4_red
    savi = 1.5 * (b8_nir - b4_red) / (b8_nir + b4_red + 0.5 + eps)
    ndre = (b8_nir - b5_re1) / (b8_nir + b5_re1 + eps)
    ireci = (b7_re3 - b4_red) / ((b5_re1 / (b6_re2 + eps)) + eps)
    return {
        "NDVI_calc": ndvi,
        "SR_calc": sr,
        "DVI_calc": dvi,
        "SAVI_calc": savi,
        "NDRE_calc": ndre,
        "IRECI_calc": ireci,
    }
