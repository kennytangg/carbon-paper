"""
Level 2 Scraper: Individual Tree Allometry, Equation Catalog, and Forest Plot Inventories.

Sources ingested:
1. Chave et al. (2014) Pantropical Destructive Harvest Tree Database (`umr-amap/BIOMASS`
   `Allometry-database-2012m_data.csv` + `Allometry-database-2012n_envsub.csv`).
   - 5,228 destructively harvested and weighed trees across 69 pantropical sites (including
     10 sites in Indonesia: Kalimantan, Sumatra, West Java, Moluccas).
   - Evaluates Chave et al. (2014) Eq. 4, Chave et al. (2014) Eq. 7, Ketterings et al. (2001)
     Indonesian SNI 7724, Brown (1997) UNFCCC, and IPCC (2006/2019) Carbon/CO2e conversions.
2. `ropensci/allodb` Global Allometric Equations Catalog (`equations.csv` + `references.csv`).
   - 570+ peer-reviewed forest biomass & height allometric equations with exact algebraic formulas.
3. Multi-Continent Field Plot Inventories:
   - USFS Forest Inventory & Analysis (FIA / rFIA) assessment area plot biomass & carbon time-series.
   - Bennett et al. (2020) Field Plot Biomass with Bioclimatic & Soil Covariates (Zenodo 3977089, 3,130 plots).
   - Poorter et al. (2016) 2ndFOR Neotropical Secondary Forest Chronosequence Plots (Zenodo 4991473, 1,334 plots).
"""

from __future__ import annotations

import io
import json
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from src.formulas import (
    ACRES_TO_HECTARES,
    FIA_CARB_CARBON_FRACTION,
    FORMULA_REGISTRY,
    IPCC_DEFAULT_CARBON_FRACTION_TROPICAL,
    MOLECULAR_WEIGHT_RATIO_CO2_C,
    SHORT_TON_TO_METRIC_TON,
    biomass_to_carbon_and_co2e,
    brown_1997_moist_tropical_agb_kg,
    chave_2014_eq4_agb_kg,
    chave_2014_eq7_agb_kg,
    compute_chave_environmental_index_E,
    ketterings_2001_indonesia_agb_kg,
)
from src.scrapers.base import BaseScraper


class AllometryAndPlotScraper(BaseScraper):
    """Ingests tree-level destructive harvest ground truth, allometric equation catalogs, and plot inventories."""

    CHAVE_TREES_URL = (
        "https://raw.githubusercontent.com/umr-amap/BIOMASS/master/data-raw/Allometry-database-2012m_data.csv"
    )
    CHAVE_ENV_URL = (
        "https://raw.githubusercontent.com/umr-amap/BIOMASS/master/data-raw/Allometry-database-2012n_envsub.csv"
    )
    ALLODB_EQUATIONS_URL = (
        "https://raw.githubusercontent.com/ropensci/allodb/master/data-raw/csv_database/equations.csv"
    )
    ALLODB_REFERENCES_URL = (
        "https://raw.githubusercontent.com/ropensci/allodb/master/data-raw/csv_database/references.csv"
    )
    RFIA_CSV_URL = (
        "https://carbonplan-forests.s3.us-west-2.amazonaws.com/offsets/archive/intermediate/rfia/assessment_areas/rfia_all/1.csv"
    )
    FIA_FORTYP_URL = (
        "https://carbonplan-forests.s3.us-west-2.amazonaws.com/offsets/archive/inputs/ancillary/fia_fortyp_to_common_name.json"
    )
    BENNETT_ZENODO_URL = (
        "https://zenodo.org/api/records/3977089/files/Bennett_et_al_2020_Ecography_BPL_data_cleaned.csv/content"
    )
    POORTER_2NDFOR_URL = (
        "https://zenodo.org/api/records/4991473/files/Aboveground%20biomass%202ndFOR%20database.csv/content"
    )

    def fetch_chave_pantropical_tree_groundtruth(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Fetch and merge the Chave et al. (2014) Pantropical Destructive Harvest dataset (5,228 trees)
        with site environmental covariates and compute standard allometric formula outputs.
        """
        trees_bytes, prov_trees = self.fetch_bytes(
            url=self.CHAVE_TREES_URL,
            cache_filename="chave_2014_allometry_trees.csv",
            source_id="CHAVE_2014_PANTROPICAL_TREES",
            source_name="Chave et al. (2014) Pantropical Destructive Harvest Tree Biomass Database",
            observation_level="tree_allometry",
            doi_or_registry="10.1111/gcb.12629",
            data_generated_period="1950-2013 (Compiled in Chave05 [2005] & Chave10 [2014])",
            description="5,228 destructively felled and weighed tropical trees with DBH, total height, wood specific gravity, and dry weight components.",
            force_refresh=force_refresh,
        )
        env_bytes, prov_env = self.fetch_bytes(
            url=self.CHAVE_ENV_URL,
            cache_filename="chave_2014_allometry_envsub.csv",
            source_id="CHAVE_2014_PANTROPICAL_ENV",
            source_name="Chave et al. (2014) Site Coordinates & Bioclimatic Covariates (TS, PS, CWD)",
            observation_level="tree_allometry",
            doi_or_registry="10.1111/gcb.12629",
            data_generated_period="2005-2014",
            description="Latitude, longitude, temperature seasonality, precipitation seasonality, and climatic water deficit for 69 pantropical harvest sites.",
            force_refresh=force_refresh,
        )

        trees_df = pd.read_csv(io.BytesIO(trees_bytes), na_values=["NA", "", "nan"])
        env_df = pd.read_csv(io.BytesIO(env_bytes), na_values=["NA", "", "nan"])
        prov_trees.record_count = len(trees_df)
        prov_env.record_count = len(env_df)
        ingested_ts = prov_trees.ingested_at_utc

        merged = trees_df.merge(env_df, on="Locality", how="left")

        dbh = pd.to_numeric(merged["Trunk.diameter..cm."], errors="coerce")
        height = pd.to_numeric(merged["Total.height..m."], errors="coerce")
        wd = pd.to_numeric(merged["Wood.specific.gravity"], errors="coerce")
        obs_agb = pd.to_numeric(merged["Dry.total.AGB..kg."], errors="coerce")
        obs_trunk = pd.to_numeric(merged["Dry.weight.trunk..kg."], errors="coerce")
        obs_branch = pd.to_numeric(merged["Dry.weight.branch..kg."], errors="coerce")
        obs_leaf = pd.to_numeric(merged["Dry.weight.leaf..kg."], errors="coerce")

        ts_raw = pd.to_numeric(merged["Temp.Seasonality..SD.100."], errors="coerce")
        ps_raw = pd.to_numeric(merged["Precip.Seasonality..CV."], errors="coerce")
        cwd_raw = pd.to_numeric(merged["CWD"], errors="coerce")

        env_E = compute_chave_environmental_index_E(ts_raw, cwd_raw, ps_raw)

        # Evaluate the 4 standard allometric equations
        agb_chave_eq4 = chave_2014_eq4_agb_kg(dbh, height, wd)
        agb_chave_eq7 = chave_2014_eq7_agb_kg(dbh, wd, env_E)
        agb_ketterings = ketterings_2001_indonesia_agb_kg(dbh, wd)
        agb_brown = brown_1997_moist_tropical_agb_kg(dbh)

        # Convert observed and predicted AGB (kg) to Carbon (kg C) and CO2e (kg CO2e) via IPCC CF = 0.47
        cf = IPCC_DEFAULT_CARBON_FRACTION_TROPICAL
        co2_factor = MOLECULAR_WEIGHT_RATIO_CO2_C

        obs_carbon_kg = obs_agb * cf
        obs_co2e_kg = obs_carbon_kg * co2_factor

        eq4_co2e_kg = agb_chave_eq4 * cf * co2_factor
        eq7_co2e_kg = agb_chave_eq7 * cf * co2_factor
        kett_co2e_kg = agb_ketterings * cf * co2_factor
        brown_co2e_kg = agb_brown * cf * co2_factor

        # Derive Country from fulllocality
        full_loc = merged["fulllocality"].fillna(merged["Locality"]).astype(str)
        countries = full_loc.apply(lambda x: x.split("_")[0] if "_" in x else x)
        is_indonesia = full_loc.str.contains("Indonesia|Kaliman|Sumatra|Moluccas|WestJava", case=False, na=False)

        dataset_tag = merged["dataset"].fillna("Chave14").astype(str)
        gen_year = np.where(dataset_tag == "Chave05", "2005 (Chave et al. 2005 Oecologia)", "2014 (Chave et al. 2014 GCB)")

        # Primary formula selection: Eq. 4 when Height is available, otherwise Eq. 7
        has_height = height.notna() & (height >= 1.3)
        primary_formula_id = np.where(has_height, "CHAVE_2014_EQ4", "CHAVE_2014_EQ7")
        primary_formula_agb = np.where(has_height, agb_chave_eq4, agb_chave_eq7)
        primary_formula_co2e = np.where(has_height, eq4_co2e_kg, eq7_co2e_kg)

        out_df = pd.DataFrame(
            {
                "tree_id": merged["number"],
                "locality_code": merged["Locality"],
                "full_locality": full_loc,
                "country": countries,
                "is_indonesia_site": is_indonesia,
                "latitude": pd.to_numeric(merged["LAT"], errors="coerce"),
                "longitude": pd.to_numeric(merged["LONG"], errors="coerce"),
                "family": merged["Family"],
                "genus": merged["genus"],
                "species_binomial": merged["Latin_Binomial"],
                "wsg_taxolevel": merged["wsg.taxolevel"],
                "data_generated_timestamp": gen_year,
                "data_ingested_timestamp_utc": ingested_ts,
                # Input variables
                "input_dbh_cm": dbh,
                "input_height_m": height,
                "input_wood_density_g_cm3": wd,
                "input_temp_seasonality_sd100": ts_raw,
                "input_precip_seasonality_cv": ps_raw,
                "input_cwd_mm": cwd_raw,
                "input_chave_E_index": env_E,
                # True Destructive Harvest Ground Truth Outcomes
                "groundtruth_observed_trunk_kg": obs_trunk,
                "groundtruth_observed_branch_kg": obs_branch,
                "groundtruth_observed_leaf_kg": obs_leaf,
                "groundtruth_observed_agb_kg": obs_agb,
                "groundtruth_observed_carbon_kg": obs_carbon_kg,
                "groundtruth_observed_co2e_kg": obs_co2e_kg,
                # Standard Formula Predictions (for direct benchmark comparison)
                "primary_formula_id": primary_formula_id,
                "formula_chave2014_eq4_agb_kg": agb_chave_eq4,
                "formula_chave2014_eq4_co2e_kg": eq4_co2e_kg,
                "formula_chave2014_eq7_agb_kg": agb_chave_eq7,
                "formula_chave2014_eq7_co2e_kg": eq7_co2e_kg,
                "formula_ketterings2001_idn_agb_kg": agb_ketterings,
                "formula_ketterings2001_idn_co2e_kg": kett_co2e_kg,
                "formula_brown1997_unfccc_agb_kg": agb_brown,
                "formula_brown1997_unfccc_co2e_kg": brown_co2e_kg,
                "formula_primary_agb_kg": primary_formula_agb,
                "formula_primary_co2e_kg": primary_formula_co2e,
                "residual_primary_vs_observed_agb_kg": primary_formula_agb - obs_agb,
            }
        )
        return out_df

    def fetch_allodb_equations_catalog(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Fetch the `ropensci/allodb` database of 570+ peer-reviewed forest allometric equations
        with exact algebraic expressions, input/output variables, taxa, and coordinates.
        """
        eq_bytes, prov_eq = self.fetch_bytes(
            url=self.ALLODB_EQUATIONS_URL,
            cache_filename="allodb_equations.csv",
            source_id="ALLODB_EQUATIONS_CATALOG",
            source_name="rOpenSci/ForestGEO allodb Extratropical & Global Allometric Equation Database",
            observation_level="allometric_equation_catalog",
            doi_or_registry="10.1111/2041-210X.13765 (Gonzalez-Akre et al. 2022 Methods in Ecology and Evolution)",
            data_generated_period="1966-2021 (Peer-Reviewed Allometric Studies)",
            description="570+ standardized forest biomass and height allometric equations with algebraic formula strings.",
            force_refresh=force_refresh,
        )
        ref_bytes, prov_ref = self.fetch_bytes(
            url=self.ALLODB_REFERENCES_URL,
            cache_filename="allodb_references.csv",
            source_id="ALLODB_REFERENCES_CATALOG",
            source_name="rOpenSci/ForestGEO allodb Bibliographic References",
            observation_level="allometric_equation_catalog",
            doi_or_registry="10.1111/2041-210X.13765",
            data_generated_period="1966-2021",
            description="Bibliographic citations and publication years for allodb equations.",
            force_refresh=force_refresh,
        )

        eq_df = pd.read_csv(
            io.StringIO(eq_bytes.decode("latin1")),
            na_values=["NA", "NI", "NRA", ""],
        )
        ref_df = pd.read_csv(
            io.StringIO(ref_bytes.decode("latin1")),
            na_values=["NA", "NI", "NRA", ""],
        )
        prov_eq.record_count = len(eq_df)
        prov_ref.record_count = len(ref_df)
        ingested_ts = prov_eq.ingested_at_utc

        if "ref_id" in eq_df.columns and "ref_id" in ref_df.columns:
            eq_df = eq_df.merge(ref_df, on="ref_id", how="left")

        eq_df["data_generated_timestamp"] = (
            eq_df.get("ref_year", pd.Series(dtype=str)).fillna(eq_df.get("ref_id", "")).astype(str)
        )
        eq_df["data_ingested_timestamp_utc"] = ingested_ts
        return eq_df

    def fetch_multi_continent_plot_inventories(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Fetch and harmonize 3 major field plot inventory datasets:
        1. USFS FIA / rFIA Assessment Area Inventory (`rfia_all/1.csv`)
        2. Bennett et al. (2020) Continental Plot Biomass & Bioclimatic/Soil Dataset (`Zenodo 3977089`)
        3. Poorter et al. (2016) 2ndFOR Neotropical Secondary Forest Recovery Plots (`Zenodo 4991473`)
        """
        # 1. USFS FIA / rFIA
        rfia_bytes, prov_rfia = self.fetch_bytes(
            url=self.RFIA_CSV_URL,
            cache_filename="usfs_rfia_assessment_area_1.csv",
            source_id="USFS_RFIA_ASSESSMENT_AREA_INVENTORY",
            source_name="USFS Forest Inventory and Analysis (FIA / rFIA) Stratum Plot Biomass & Carbon",
            observation_level="plot_inventory",
            doi_or_registry="USFS FIA / 10.1016/j.envsoft.2020.104664",
            data_generated_period="2005-2019 (Annual FIA Inventory Cycles)",
            description="USFS FIA forest type plot aggregations with biomass/acre, carbon/acre, variances, plot counts, and tree counts.",
            force_refresh=force_refresh,
        )
        fortyp_json, _ = self.fetch_json(
            url=self.FIA_FORTYP_URL,
            cache_filename="fia_fortyp_to_common_name.json",
            source_id="USFS_FIA_FORTYP_LOOKUP",
            source_name="USFS FIA Forest Type Code to Common Name Lookup",
            observation_level="plot_inventory",
            doi_or_registry="USFS FIA Handbook Appendix D",
            data_generated_period="2015",
            description="Mapping from FIA forest type code (FORTYPCD) to species group name.",
            force_refresh=force_refresh,
        )

        rfia_df = pd.read_csv(io.BytesIO(rfia_bytes))
        prov_rfia.record_count = len(rfia_df)

        # 2. Bennett et al. 2020 (Zenodo 3977089)
        bennett_bytes, prov_bennett = self.fetch_bytes(
            url=self.BENNETT_ZENODO_URL,
            cache_filename="bennett_2020_plot_biomass_climate_soil.csv",
            source_id="ZENODO_3977089_BENNETT_2020",
            source_name="Bennett et al. (2020) Continental Forest Plot Biomass, Climate & Soil Dataset",
            observation_level="plot_inventory",
            doi_or_registry="10.5061/dryad.dr7sqv9w9",
            data_generated_period="2020-08-08 (Ecography Publication & Plot Inventory)",
            description="3,130 field plots with aboveground dry biomass (Mg/ha), canopy height/cover classes, 8 WorldClim bioclimatic variables, and 6 soil variables.",
            force_refresh=force_refresh,
        )
        bennett_df = pd.read_csv(io.StringIO(bennett_bytes.decode("utf-8", errors="replace")))
        prov_bennett.record_count = len(bennett_df)

        # 3. Poorter et al. 2016 2ndFOR (Zenodo 4991473)
        secfor_bytes, prov_secfor = self.fetch_bytes(
            url=self.POORTER_2NDFOR_URL,
            cache_filename="poorter_2ndfor_neotropical_secondary_forest_agb.csv",
            source_id="ZENODO_4991473_POORTER_2NDFOR",
            source_name="Poorter et al. (2016) 2ndFOR Neotropical Secondary Forest Chronosequence Biomass Database",
            observation_level="plot_inventory",
            doi_or_registry="10.5061/dryad.82vr4 (Nature 530:211-214)",
            data_generated_period="1995-2016 (Published 2016 Nature / 2021 Zenodo)",
            description="1,334 secondary forest chronosequence plots across the Neotropics with stand age (yr) and field-measured AGB (Mg/ha).",
            force_refresh=force_refresh,
        )
        secfor_df = pd.read_csv(io.StringIO(secfor_bytes.decode("latin1")))
        prov_secfor.record_count = len(secfor_df)

        records: List[Dict[str, Any]] = []

        # Process USFS FIA rows
        for idx, r in rfia_df.iterrows():
            fortyp_code = str(int(r["FORTYPCD"])) if pd.notna(r.get("FORTYPCD")) else "unknown"
            fortyp_name = fortyp_json.get(fortyp_code, f"FIA_Type_{fortyp_code}")
            bio_acre_short_tons = float(r.get("BIO_ACRE") or 0.0)
            carb_acre_short_tons = float(r.get("CARB_ACRE") or 0.0)

            # Convert short tons / acre -> metric Mg / ha
            conv_ton_acre_to_mg_ha = SHORT_TON_TO_METRIC_TON / ACRES_TO_HECTARES
            agb_mg_ha = bio_acre_short_tons * conv_ton_acre_to_mg_ha
            carbon_tc_ha = carb_acre_short_tons * conv_ton_acre_to_mg_ha
            co2e_t_ha = carbon_tc_ha * MOLECULAR_WEIGHT_RATIO_CO2_C
            recalc_carbon_tc_ha = agb_mg_ha * FIA_CARB_CARBON_FRACTION
            recalc_co2e_t_ha = recalc_carbon_tc_ha * MOLECULAR_WEIGHT_RATIO_CO2_C

            records.append(
                {
                    "plot_record_id": f"FIA_AA1_{idx+1}",
                    "dataset_source": "USFS_FIA_rFIA",
                    "country": "United States",
                    "site_or_region": str(r.get("SSection") or "Adirondacks & Green Mountains"),
                    "biome_or_ecoregion": "Temperate Broadleaf & Mixed Forest",
                    "forest_type": fortyp_name,
                    "latitude": 43.95,
                    "longitude": -74.25,
                    "data_generated_timestamp": str(int(r["YEAR"])) if pd.notna(r.get("YEAR")) else "2005",
                    "data_ingested_timestamp_utc": prov_rfia.ingested_at_utc,
                    # Input variables
                    "input_stand_age_yr": np.nan,
                    "input_n_plots": int(r.get("nPlots_TREE") or 0),
                    "input_n_trees_sampled": int(r.get("N") or 0),
                    "input_stratum_area_ha": float(r.get("AREA_TOTAL") or 0.0) * ACRES_TO_HECTARES,
                    "input_canopy_height_class": np.nan,
                    "input_canopy_cover_class": np.nan,
                    "input_mean_annual_temp_C": np.nan,
                    "input_annual_precip_mm": np.nan,
                    "input_soil_clay_pct": np.nan,
                    "input_soil_ph": np.nan,
                    "input_agb_Mg_ha": agb_mg_ha,
                    "input_carbon_fraction": FIA_CARB_CARBON_FRACTION,
                    # Formula & Outcomes
                    "formula_id": "USFS_FIA_CARB_CONVERSION",
                    "formula_expression": "carbon_tC_ha = 0.50 * agb_Mg_ha; co2e_tCO2e_ha = carbon_tC_ha * (44/12)",
                    "outcome_agb_Mg_ha": agb_mg_ha,
                    "outcome_carbon_tC_ha": carbon_tc_ha,
                    "outcome_co2e_tCO2e_ha": co2e_t_ha,
                    "formula_recalculated_co2e_tCO2e_ha": recalc_co2e_t_ha,
                    "verification_residual_tCO2e_ha": recalc_co2e_t_ha - co2e_t_ha,
                }
            )

        # Process Bennett et al. 2020 rows
        for _, r in bennett_df.iterrows():
            agb_mg_ha = float(r.get("agb_drymass_ha") or np.nan)
            conv = biomass_to_carbon_and_co2e(
                agb_mg_ha, carbon_fraction=IPCC_DEFAULT_CARBON_FRACTION_TROPICAL, include_bgb=False
            )
            records.append(
                {
                    "plot_record_id": f"BENNETT_{r.get('ID')}",
                    "dataset_source": "Zenodo_3977089_Bennett2020",
                    "country": "Australia",
                    "site_or_region": str(r.get("State") or "AU"),
                    "biome_or_ecoregion": f"{r.get('Biome', '')} - {r.get('ECOREGION', '')}",
                    "forest_type": f"{r.get('FOR_CAT', '')} / {r.get('FOR_TYPE', '')}",
                    "latitude": float(r.get("Lat") or np.nan),
                    "longitude": float(r.get("Long") or np.nan),
                    "data_generated_timestamp": "2020-08-08",
                    "data_ingested_timestamp_utc": prov_bennett.ingested_at_utc,
                    # Input variables
                    "input_stand_age_yr": np.nan,
                    "input_n_plots": 1,
                    "input_n_trees_sampled": np.nan,
                    "input_stratum_area_ha": np.nan,
                    "input_canopy_height_class": float(r.get("HEIGHT") or np.nan),
                    "input_canopy_cover_class": float(r.get("COVER") or np.nan),
                    "input_mean_annual_temp_C": float(r.get("bio_1") or np.nan),
                    "input_annual_precip_mm": float(r.get("bio_12") or np.nan),
                    "input_soil_clay_pct": float(r.get("cly_0_5") or np.nan),
                    "input_soil_ph": float(r.get("phc_0_5") or np.nan),
                    "input_agb_Mg_ha": agb_mg_ha,
                    "input_carbon_fraction": IPCC_DEFAULT_CARBON_FRACTION_TROPICAL,
                    # Formula & Outcomes
                    "formula_id": "IPCC_2006_2019_CARBON_CONVERSION",
                    "formula_expression": "carbon_tC_ha = 0.47 * agb_Mg_ha; co2e_tCO2e_ha = carbon_tC_ha * (44/12)",
                    "outcome_agb_Mg_ha": agb_mg_ha,
                    "outcome_carbon_tC_ha": float(conv["carbon"]),
                    "outcome_co2e_tCO2e_ha": float(conv["co2e"]),
                    "formula_recalculated_co2e_tCO2e_ha": float(conv["co2e"]),
                    "verification_residual_tCO2e_ha": 0.0,
                }
            )

        # Process Poorter et al. 2016 2ndFOR rows
        import re
        for idx, r in secfor_df.iterrows():
            try:
                agb_mg_ha = float(r.get("AGB"))
            except (TypeError, ValueError):
                agb_mg_ha = np.nan
            raw_age = str(r.get("Age") or "").strip()
            if raw_age.upper() == "OG":
                age_yr = 100.0  # Old-Growth reference forest stand
                stage_label = "Old-Growth Reference Forest"
            else:
                try:
                    age_yr = float(raw_age)
                except (TypeError, ValueError):
                    age_yr = np.nan
                stage_label = "Secondary Forest Recovery"
            conv = biomass_to_carbon_and_co2e(
                agb_mg_ha, carbon_fraction=IPCC_DEFAULT_CARBON_FRACTION_TROPICAL, include_bgb=False
            )
            ref_str = str(r.get("Reference") or "Poorter et al. 2016 Nature")
            m = re.search(r"(19\d{2}|20\d{2})", ref_str)
            pub_year = m.group(1) if m else "2016"

            records.append(
                {
                    "plot_record_id": f"2NDFOR_{idx+1}",
                    "dataset_source": "Zenodo_4991473_Poorter_2ndFOR",
                    "country": "Neotropics (Multi-Country Secondary Forest Network)",
                    "site_or_region": str(r.get("Chronosequence") or "Neotropical Site"),
                    "biome_or_ecoregion": "Neotropical Moist & Dry Secondary Forests",
                    "forest_type": f"{stage_label} (PI: {r.get('PI', '2ndFOR')})",
                    "latitude": np.nan,
                    "longitude": np.nan,
                    "data_generated_timestamp": pub_year,
                    "data_ingested_timestamp_utc": prov_secfor.ingested_at_utc,
                    # Input variables
                    "input_stand_age_yr": age_yr,
                    "input_n_plots": 1,
                    "input_n_trees_sampled": np.nan,
                    "input_stratum_area_ha": np.nan,
                    "input_canopy_height_class": np.nan,
                    "input_canopy_cover_class": np.nan,
                    "input_mean_annual_temp_C": np.nan,
                    "input_annual_precip_mm": np.nan,
                    "input_soil_clay_pct": np.nan,
                    "input_soil_ph": np.nan,
                    "input_agb_Mg_ha": agb_mg_ha,
                    "input_carbon_fraction": IPCC_DEFAULT_CARBON_FRACTION_TROPICAL,
                    # Formula & Outcomes
                    "formula_id": "IPCC_2006_2019_CARBON_CONVERSION",
                    "formula_expression": "carbon_tC_ha = 0.47 * agb_Mg_ha; co2e_tCO2e_ha = carbon_tC_ha * (44/12)",
                    "outcome_agb_Mg_ha": agb_mg_ha,
                    "outcome_carbon_tC_ha": float(conv["carbon"]),
                    "outcome_co2e_tCO2e_ha": float(conv["co2e"]),
                    "formula_recalculated_co2e_tCO2e_ha": float(conv["co2e"]),
                    "verification_residual_tCO2e_ha": 0.0,
                }
            )

        return pd.DataFrame(records)
