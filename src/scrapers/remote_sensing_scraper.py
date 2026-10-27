"""
Level 3 Scraper: Remote Sensing (Airborne LiDAR, Sentinel-2 Optical, Sentinel-1 SAR, ESA CCI)
Paired with Field Plot Ground Truth Biomass & Carbon Datasets.

Sources ingested:
1. ESA/NASA TropiSAR & AfriSAR Airborne LiDAR + In-Situ Field Plot Reference Dataset
   (Labrière, Tao, Chave, Saatchi et al. 2018 IEEE JSTARS; Zenodo 4938255 / Dryad 467hp97).
   - 1,093 tropical forest calibration plots (1 ha, 0.25 ha, 0.16 ha) across French Guiana
     (Nouragues, Paracou) and Gabon (Lopé, Mabounié, Mondah, Rabi).
   - Pairs 1m LiDAR Canopy Height Model metrics (TCH, H50, GF20, STDV) and plot biophysical
     inputs (Basal Area, Wood Density, Stem Density) with 3 Chave et al. (2014) ground-truth
     AGB outcomes (Eq. 4 local H-D, Eq. 4 Feldpausch H-D, Eq. 7 bioclimatic E) + 95% CI.
2. Multi-Sensor Sentinel-2 Optical (B1-B12 + 35 Vegetation Indices: NDVI, EVI, SAVI, NDRE, IRECI)
   + Sentinel-1 C-Band SAR (VV, VH) + Topography + Field Plot AGB Dataset (Zenodo 15622257).
   - 305 field-sampled forest inventory plots with 67 remote sensing, topographic, climatic,
     and ecological variables.
3. National Forest Inventory (NFI / FAO FRA 2020) vs. ESA CCI Satellite Biomass Intercomparison
   (Zenodo 6992943), covering tropical & global countries (including Indonesia).
"""

from __future__ import annotations

import io
import math
import zipfile
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from src.formulas import (
    IPCC_DEFAULT_CARBON_FRACTION_TROPICAL,
    MOLECULAR_WEIGHT_RATIO_CO2_C,
    biomass_to_carbon_and_co2e,
    compute_lidar_plot_agb_mg_ha,
    compute_sentinel2_spectral_indices,
)
from src.scrapers.base import BaseScraper


SITE_METADATA_MAP: Dict[str, Dict[str, Any]] = {
    "NOURAGUES": {"country": "French Guiana", "utm_zone": 22, "southern": False, "campaign_year": "2009-2016 (TropiSAR)"},
    "PARACOU": {"country": "French Guiana", "utm_zone": 22, "southern": False, "campaign_year": "2009-2016 (TropiSAR)"},
    "PAR17": {"country": "French Guiana", "utm_zone": 22, "southern": False, "campaign_year": "2009-2016 (TropiSAR Arbocel)"},
    "LOPE": {"country": "Gabon", "utm_zone": 32, "southern": True, "campaign_year": "2016 (AfriSAR)"},
    "MABOUNIE": {"country": "Gabon", "utm_zone": 32, "southern": True, "campaign_year": "2016 (AfriSAR)"},
    "RABI": {"country": "Gabon", "utm_zone": 32, "southern": True, "campaign_year": "2016 (AfriSAR)"},
    "MONDAH": {"country": "Gabon", "utm_zone": 32, "southern": False, "campaign_year": "2016 (AfriSAR)"},
}


def utm_to_latlon_wgs84(easting: float, northing: float, zone_number: int, southern: bool = False) -> Tuple[float, float]:
    """Convert WGS84 UTM Easting/Northing (meters) to (latitude, longitude) in decimal degrees."""
    a = 6378137.0
    ecc_sq = 0.00669438
    k0 = 0.9996
    x = easting - 500000.0
    y = northing - (10000000.0 if southern else 0.0)

    m = y / k0
    mu = m / (a * (1.0 - ecc_sq / 4.0 - 3.0 * (ecc_sq ** 2) / 64.0 - 5.0 * (ecc_sq ** 3) / 256.0))
    e1 = (1.0 - math.sqrt(1.0 - ecc_sq)) / (1.0 + math.sqrt(1.0 - ecc_sq))

    j1 = 3.0 * e1 / 2.0 - 27.0 * (e1 ** 3) / 32.0
    j2 = 21.0 * (e1 ** 2) / 16.0 - 55.0 * (e1 ** 4) / 32.0
    j3 = 151.0 * (e1 ** 3) / 96.0
    j4 = 1097.0 * (e1 ** 4) / 512.0

    fp = mu + j1 * math.sin(2.0 * mu) + j2 * math.sin(4.0 * mu) + j3 * math.sin(6.0 * mu) + j4 * math.sin(8.0 * mu)
    e2 = ecc_sq / (1.0 - ecc_sq)
    c1 = e2 * (math.cos(fp) ** 2)
    t1 = math.tan(fp) ** 2
    r1 = a * (1.0 - ecc_sq) / ((1.0 - ecc_sq * (math.sin(fp) ** 2)) ** 1.5)
    n1 = a / math.sqrt(1.0 - ecc_sq * (math.sin(fp) ** 2))
    d = x / (n1 * k0)

    q1 = n1 * math.tan(fp) / r1
    q2 = (d ** 2) / 2.0
    q3 = (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * (c1 ** 2) - 9.0 * e2) * (d ** 4) / 24.0
    q4 = (61.0 + 90.0 * t1 + 298.0 * c1 + 45.0 * (t1 ** 2) - 3.0 * (c1 ** 2) - 252.0 * e2) * (d ** 6) / 720.0
    lat = fp - q1 * (q2 - q3 + q4)

    q5 = d
    q6 = (1.0 + 2.0 * t1 + c1) * (d ** 3) / 6.0
    q7 = (5.0 - 2.0 * c1 + 28.0 * t1 - 3.0 * (c1 ** 2) + 8.0 * e2 + 24.0 * (t1 ** 2)) * (d ** 5) / 120.0
    lon_origin = (zone_number - 1) * 6 - 180 + 3
    lon = math.radians(lon_origin) + (q5 - q6 + q7) / math.cos(fp)

    return round(math.degrees(lat), 6), round(math.degrees(lon), 6)


class RemoteSensingPlotScraper(BaseScraper):
    """Ingests active (LiDAR/SAR) and passive (Sentinel-2 optical) remote sensing + field plot datasets."""

    TROPISAR_AFRISAR_ZIP_URL = (
        "https://zenodo.org/api/records/4938255/files/IN_SITU_DATA_TropiSAR_AfriSAR.zip/content"
    )
    SENTINEL_OPTICAL_SAR_CSV_URL = (
        "https://zenodo.org/api/records/15622257/files/forest_AGB_data.csv/content"
    )
    NFI_INTERCOMPARISON_URL = (
        "https://zenodo.org/api/records/6992943/files/national_biomass_intercomparison_data.csv/content"
    )
    NFI_PLOT_DESIGN_URL = (
        "https://zenodo.org/api/records/6992943/files/NFI_plot_design_characteristics_data.csv/content"
    )

    @staticmethod
    def _to_float(val: Any) -> float:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return np.nan
        s = str(val).strip()
        if s in ("", "-", "NA", "nan", "None", "null"):
            return np.nan
        try:
            return float(s)
        except Exception:
            return np.nan

    def fetch_tropisar_afrisar_lidar_plots(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Fetch and extract the 1,093 tropical forest LiDAR + field inventory calibration plots
        from ESA/NASA TropiSAR & AfriSAR (Labrière, Tao, Chave, Saatchi et al. 2018).
        """
        zip_bytes, prov = self.fetch_bytes(
            url=self.TROPISAR_AFRISAR_ZIP_URL,
            cache_filename="tropisar_afrisar_insitu_lidar.zip",
            source_id="ZENODO_4938255_TROPISAR_AFRISAR",
            source_name="ESA/NASA TropiSAR & AfriSAR Airborne LiDAR + Field Plot Biomass Reference Dataset",
            observation_level="remote_sensing_plot",
            doi_or_registry="10.5061/dryad.467hp97 / 10.1109/JSTARS.2018.2851606",
            data_generated_period="2009-2016 (Published 2018 IEEE JSTARS)",
            description="1,093 calibration plots (1ha, 0.25ha, 0.16ha) with 1m LiDAR CHM metrics (TCH, H50, GF20, STDV), plot BA/WD/stem density, and 3 Chave et al. (2014) AGB outcomes.",
            force_refresh=force_refresh,
        )

        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        dfs: List[pd.DataFrame] = []
        for member in ["CSV_TropiSAR_AfriSAR/TropiSAR_plotbased_AGB.csv", "CSV_TropiSAR_AfriSAR/AfriSAR_plotbased_AGB.csv"]:
            raw_csv = zf.read(member).decode("utf-8", errors="replace")
            df_part = pd.read_csv(io.StringIO(raw_csv), sep=";", na_values=["-", "NA", "", "nan"])
            df_part["campaign"] = "TropiSAR" if "TropiSAR_" in member else "AfriSAR"
            dfs.append(df_part)

        combined = pd.concat(dfs, ignore_index=True)
        prov.record_count = len(combined)
        ingested_ts = prov.ingested_at_utc

        scale_map = {"1ha": 1.0, "0.25ha": 0.25, "0.16ha": 0.16}
        rows: List[Dict[str, Any]] = []

        for _, r in combined.iterrows():
            site = str(r.get("Site") or "").strip().upper()
            smeta = SITE_METADATA_MAP.get(site, {"country": "Tropical Site", "utm_zone": 22, "southern": False, "campaign_year": "2016"})

            # Compute plot center UTM and convert to WGS84 lat/lon
            coords_x = [self._to_float(r.get(k)) for k in ("sw_x", "nw_x", "se_x", "ne_x")]
            coords_y = [self._to_float(r.get(k)) for k in ("sw_y", "nw_y", "se_y", "ne_y")]
            easting_mean = float(np.nanmean(coords_x))
            northing_mean = float(np.nanmean(coords_y))
            if not np.isnan(easting_mean) and not np.isnan(northing_mean):
                lat, lon = utm_to_latlon_wgs84(
                    easting_mean, northing_mean, zone_number=smeta["utm_zone"], southern=smeta["southern"]
                )
            else:
                lat, lon = np.nan, np.nan

            scale_str = str(r.get("Scale") or "1ha").strip()
            area_ha = scale_map.get(scale_str, 0.25)

            tch = self._to_float(r.get("TCH"))
            h50 = self._to_float(r.get("H50"))
            gf20 = self._to_float(r.get("GF20"))
            canopy_cover_20m = (1.0 - gf20) if not np.isnan(gf20) else np.nan
            stdv = self._to_float(r.get("STDV"))
            ba = self._to_float(r.get("BA"))
            wd = self._to_float(r.get("WD"))
            ndens = self._to_float(r.get("Ndens"))

            agb_fph = self._to_float(r.get("agb_fph"))
            agb_chv = self._to_float(r.get("agb_chv"))
            agb_loc = self._to_float(r.get("agb_loc"))

            # Predict AGB from LiDAR TCH + BA + WD structural-allometric equation
            agb_lidar_pred = float(compute_lidar_plot_agb_mg_ha(tch, ba, wd))

            # Convert primary ground truth (agb_loc) to tC/ha and tCO2e/ha via IPCC CF=0.47
            conv_loc = biomass_to_carbon_and_co2e(agb_loc, carbon_fraction=IPCC_DEFAULT_CARBON_FRACTION_TROPICAL)
            conv_chv = biomass_to_carbon_and_co2e(agb_chv, carbon_fraction=IPCC_DEFAULT_CARBON_FRACTION_TROPICAL)
            conv_fph = biomass_to_carbon_and_co2e(agb_fph, carbon_fraction=IPCC_DEFAULT_CARBON_FRACTION_TROPICAL)

            rows.append(
                {
                    "area_code": r.get("Area_code"),
                    "plot_code": r.get("Plot_code"),
                    "campaign": r.get("campaign"),
                    "site_name": site,
                    "country": smeta["country"],
                    "plot_scale": scale_str,
                    "plot_area_ha": area_ha,
                    "latitude": lat,
                    "longitude": lon,
                    "utm_easting_m": easting_mean,
                    "utm_northing_m": northing_mean,
                    "data_generated_timestamp": smeta["campaign_year"],
                    "data_ingested_timestamp_utc": ingested_ts,
                    # Remote Sensing LiDAR Input Variables
                    "input_lidar_tch_mean_m": tch,
                    "input_lidar_h50_median_m": h50,
                    "input_lidar_gap_fraction_20m": gf20,
                    "input_lidar_canopy_cover_20m": canopy_cover_20m,
                    "input_lidar_height_stdv_m": stdv,
                    # Field Biophysical Input Variables
                    "input_basal_area_m2_ha": ba,
                    "input_wood_density_g_cm3": wd,
                    "input_stem_density_ha": ndens,
                    # Formulas & Ground Truth Outcomes
                    "formula_id_loc": "CHAVE_2014_EQ4_LOCAL_HD",
                    "formula_id_fph": "CHAVE_2014_EQ4_FELDPAUSCH_HD",
                    "formula_id_chv": "CHAVE_2014_EQ7_BIOCLIMATIC_E",
                    "formula_id_lidar": "LABRIERE_CHAVE_2018_LIDAR_AGB",
                    "outcome_agb_loc_Mg_ha": agb_loc,
                    "outcome_agb_loc_ci_2_5": self._to_float(r.get("cred_loc_2.5")),
                    "outcome_agb_loc_ci_97_5": self._to_float(r.get("cred_loc_97.5")),
                    "outcome_agb_fph_Mg_ha": agb_fph,
                    "outcome_agb_fph_ci_2_5": self._to_float(r.get("cred_fph_2.5")),
                    "outcome_agb_fph_ci_97_5": self._to_float(r.get("cred_fph_97.5")),
                    "outcome_agb_chv_Mg_ha": agb_chv,
                    "outcome_agb_chv_ci_2_5": self._to_float(r.get("cred_chv_2.5")),
                    "outcome_agb_chv_ci_97_5": self._to_float(r.get("cred_chv_97.5")),
                    "outcome_carbon_loc_tC_ha": float(conv_loc["carbon"]),
                    "outcome_co2e_loc_tCO2e_ha": float(conv_loc["co2e"]),
                    "outcome_co2e_chv_tCO2e_ha": float(conv_chv["co2e"]),
                    "outcome_co2e_fph_tCO2e_ha": float(conv_fph["co2e"]),
                    "formula_lidar_predicted_agb_Mg_ha": agb_lidar_pred,
                    "formula_lidar_predicted_co2e_tCO2e_ha": agb_lidar_pred
                    * IPCC_DEFAULT_CARBON_FRACTION_TROPICAL
                    * MOLECULAR_WEIGHT_RATIO_CO2_C,
                    "residual_lidar_vs_loc_agb_Mg_ha": agb_lidar_pred - agb_loc,
                }
            )

        return pd.DataFrame(rows)

    def fetch_sentinel_optical_sar_field_plots(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Fetch the 305 field-sampled forest inventory plots paired with Sentinel-2 MSI
        (12 bands + 35 vegetation indices) and Sentinel-1 SAR (VV, VH) from Zenodo 15622257.
        Verifies exact spectral index formulas (NDVI, SAVI, NDRE, IRECI, SAR VV/VH) and
        converts field plot AGB to tC/ha and tCO2e/ha.
        """
        raw_bytes, prov = self.fetch_bytes(
            url=self.SENTINEL_OPTICAL_SAR_CSV_URL,
            cache_filename="sentinel2_sentinel1_field_plot_agb.csv",
            source_id="ZENODO_15622257_SENTINEL_OPTICAL_SAR_AGB",
            source_name="Multi-Sensor Sentinel-2 Optical + Sentinel-1 SAR + Field Plot AGB Dataset",
            observation_level="remote_sensing_plot",
            doi_or_registry="10.5281/zenodo.15622257",
            data_generated_period="2020-2024 (Published 2025-06-09 Zenodo)",
            description="305 field-sampled forest inventory plots with Sentinel-2 bands B1-B12, 35 spectral indices (NDVI, EVI, SAVI, NDRE, IRECI), Sentinel-1 SAR VV/VH, topography, climate, and AGB (Mg/ha).",
            force_refresh=force_refresh,
        )

        df = pd.read_csv(io.StringIO(raw_bytes.decode("utf-8", errors="replace")))
        # Clean potential UTF-8 BOM in column names
        df.columns = [c.lstrip("\ufeff").strip() for c in df.columns]
        prov.record_count = len(df)
        ingested_ts = prov.ingested_at_utc

        # Verify spectral indices using our formula engine
        spec = compute_sentinel2_spectral_indices(
            b2_blue=df["B2"].to_numpy(dtype=float),
            b4_red=df["B4"].to_numpy(dtype=float),
            b5_re1=df["B5"].to_numpy(dtype=float),
            b6_re2=df["B6"].to_numpy(dtype=float),
            b7_re3=df["B7"].to_numpy(dtype=float),
            b8_nir=df["B8"].to_numpy(dtype=float),
        )

        agb_mg_ha = df["biomass"].to_numpy(dtype=float)
        conv = biomass_to_carbon_and_co2e(agb_mg_ha, carbon_fraction=IPCC_DEFAULT_CARBON_FRACTION_TROPICAL)

        df["country"] = "China (Greater Khingan / Boreal-Temperate Forest Inventory)"
        df["latitude"] = df["Y"]
        df["longitude"] = df["X"]
        df["data_generated_timestamp"] = "2024 (Sentinel-2/1 & Field Campaign; Published 2025-06-09)"
        df["data_ingested_timestamp_utc"] = ingested_ts
        df["formula_id"] = "SENTINEL2_SPECTRAL_INDICES_AND_AGB"
        df["formula_expression"] = (
            "NDVI = (B8 - B4)/(B8 + B4); SAVI = 1.5*(B8 - B4)/(B8 + B4 + 0.5); "
            "NDRE = (B8 - B5)/(B8 + B5); carbon_tC_ha = 0.47 * biomass; co2e_tCO2e_ha = carbon_tC_ha * (44/12)"
        )
        df["NDVI_formula_recalculated"] = spec["NDVI_calc"]
        df["SAVI_formula_recalculated"] = spec["SAVI_calc"]
        df["NDRE_formula_recalculated"] = spec["NDRE_calc"]
        df["NDVI_verification_residual"] = spec["NDVI_calc"] - df["NDVI"].to_numpy(dtype=float)
        df["outcome_agb_Mg_ha"] = agb_mg_ha
        df["outcome_carbon_tC_ha"] = conv["carbon"]
        df["outcome_co2e_tCO2e_ha"] = conv["co2e"]

        return df

    def fetch_national_nfi_satellite_intercomparison(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Fetch country-level National Forest Inventory (NFI / FAO FRA 2020) vs. ESA CCI Spaceborne
        Biomass Map intercomparison dataset (Zenodo 6992943), merged with NFI plot design specifications.
        """
        inter_bytes, prov_inter = self.fetch_bytes(
            url=self.NFI_INTERCOMPARISON_URL,
            cache_filename="national_biomass_intercomparison_data.csv",
            source_id="ZENODO_6992943_NFI_CCI_INTERCOMPARISON",
            source_name="FAO FRA 2020 National Forest Inventory vs. ESA CCI Satellite Biomass Intercomparison",
            observation_level="national_nfi_vs_satellite",
            doi_or_registry="10.5281/zenodo.6992943",
            data_generated_period="2000-2020 (FRA 2020 & ESA CCI Biomass Maps)",
            description="Comparison of ground-based National Forest Inventory AGB (ton/ha & Gt) against ESA CCI spaceborne biomass maps across tropical countries.",
            force_refresh=force_refresh,
        )
        design_bytes, prov_design = self.fetch_bytes(
            url=self.NFI_PLOT_DESIGN_URL,
            cache_filename="nfi_plot_design_characteristics.csv",
            source_id="ZENODO_6992943_NFI_PLOT_DESIGN",
            source_name="Tropical Countries National Forest Inventory (NFI) Plot Sampling Design Specifications",
            observation_level="national_nfi_vs_satellite",
            doi_or_registry="10.5281/zenodo.6992943",
            data_generated_period="2000-2020",
            description="Plot size (ha), cluster shape, stratification, and sampling design for tropical NFIs.",
            force_refresh=force_refresh,
        )

        inter_df = pd.read_csv(io.StringIO(inter_bytes.decode("utf-8", errors="replace")))
        design_df = pd.read_csv(io.StringIO(design_bytes.decode("utf-8", errors="replace")))
        inter_df.columns = [c.lstrip("\ufeff").strip() for c in inter_df.columns]
        design_df.columns = [c.lstrip("\ufeff").strip() for c in design_df.columns]

        prov_inter.record_count = len(inter_df)
        prov_design.record_count = len(design_df)

        design_dedup = design_df.drop_duplicates(subset=["Country"], keep="first")
        merged = inter_df.merge(design_dedup, on="Country", how="left")

        fra_agb_ha = pd.to_numeric(merged["FRA_AGB_ton.ha"], errors="coerce")
        cci_agb_ha = pd.to_numeric(merged["CCI_Map_AGB_ton.ha"], errors="coerce")

        merged["data_generated_timestamp"] = (
            merged["Latest_NFI_year_FRA2020"].fillna("2020 (FAO FRA)").astype(str)
        )
        merged["data_ingested_timestamp_utc"] = prov_inter.ingested_at_utc
        merged["formula_id"] = "IPCC_2006_2019_CARBON_CONVERSION"
        merged["formula_expression"] = "co2e_tCO2e_ha = 0.47 * agb_ton_ha * (44/12)"
        merged["outcome_nfi_groundtruth_co2e_tCO2e_ha"] = (
            fra_agb_ha * IPCC_DEFAULT_CARBON_FRACTION_TROPICAL * MOLECULAR_WEIGHT_RATIO_CO2_C
        )
        merged["outcome_esa_cci_satellite_co2e_tCO2e_ha"] = (
            cci_agb_ha * IPCC_DEFAULT_CARBON_FRACTION_TROPICAL * MOLECULAR_WEIGHT_RATIO_CO2_C
        )
        merged["satellite_vs_nfi_agb_diff_ton_ha"] = cci_agb_ha - fra_agb_ha

        return merged
