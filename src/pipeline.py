"""
Master Orchestration Pipeline for Forest Carbon MRV Ground Truth Ingestion,
Unified Schema Harmonization, Multi-Format Export (CSV, Parquet, SQLite, JSON),
and Standard Formula Benchmarking.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from src.evaluator import run_standard_formula_benchmarks
from src.formulas import FORMULA_REGISTRY
from src.scrapers.allometry_scraper import AllometryAndPlotScraper
from src.scrapers.base import ProvenanceRecord, utc_now_iso
from src.scrapers.registry_scraper import RegistryMRVScraper
from src.scrapers.remote_sensing_scraper import RemoteSensingPlotScraper
from src.scrapers.time_series_scraper import LongTermPlotTimeSeriesScraper
from src.timestamps import TIMESTAMP_BASIS, normalize_timestamp


class ForestCarbonMRVPipeline:
    """End-to-end ingestion, verification, harmonization, and export pipeline."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.data_dir = base_dir / "data"
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.sqlite_dir = self.data_dir / "sqlite"
        self.metadata_dir = self.data_dir / "metadata"

        for d in [self.raw_dir, self.processed_dir, self.sqlite_dir, self.metadata_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.registry_scraper = RegistryMRVScraper(self.raw_dir)
        self.allometry_scraper = AllometryAndPlotScraper(self.raw_dir)
        self.rs_scraper = RemoteSensingPlotScraper(self.raw_dir)
        self.time_series_scraper = LongTermPlotTimeSeriesScraper(self.raw_dir)

    def run(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Execute all scrapers, build unified dataset, run benchmarks, and export artifacts."""
        pipeline_start_utc = utc_now_iso()
        print(f"[{pipeline_start_utc}] Starting Forest Carbon MRV Ground Truth Ingestion Pipeline...")

        # --- LEVEL 1: Registry Project & Credit Issuance MRV ---
        print("  -> [Level 1] Scraping Verra VCS, Gold Standard, ACR, CAR, ART-TREES, Cercarbono projects...")
        df_reg_projects = self.registry_scraper.fetch_registry_forest_projects(force_refresh=force_refresh)
        print(f"     Ingested {len(df_reg_projects):,} registry forest projects.")

        print("  -> [Level 1] Scraping Registry Credit Issuance Transactions (with vintage & timestamps)...")
        df_reg_issuances = self.registry_scraper.fetch_registry_credit_issuances(force_refresh=force_refresh)
        print(f"     Ingested {len(df_reg_issuances):,} verified credit issuance records.")

        print("  -> [Level 1] Scraping Biophysical Pool-Level IFM MRV Database (Verra VCSOPR / CAR / ACR)...")
        df_ifm_mrv = self.registry_scraper.fetch_biophysical_ifm_mrv_projects(force_refresh=force_refresh)
        print(f"     Ingested & formula-verified {len(df_ifm_mrv):,} biophysical IFM MRV projects.")

        # --- LEVEL 2: Tree & Plot Allometry & Multi-Continent Plot Inventories ---
        print("  -> [Level 2] Scraping Chave et al. (2014) Pantropical Destructive Harvest Tree Database...")
        df_trees = self.allometry_scraper.fetch_chave_pantropical_tree_groundtruth(force_refresh=force_refresh)
        n_idn_trees = int(df_trees["is_indonesia_site"].sum())
        print(f"     Ingested {len(df_trees):,} destructively weighed trees ({n_idn_trees:,} in Indonesia sites).")

        print("  -> [Level 2] Scraping rOpenSci/ForestGEO allodb Allometric Equations Catalog...")
        df_allodb = self.allometry_scraper.fetch_allodb_equations_catalog(force_refresh=force_refresh)
        print(f"     Ingested {len(df_allodb):,} peer-reviewed forest allometric equations.")

        print("  -> [Level 2] Scraping Multi-Continent Field Plot Inventories (USFS FIA, Bennett 2020, 2ndFOR)...")
        df_plots = self.allometry_scraper.fetch_multi_continent_plot_inventories(force_refresh=force_refresh)
        print(f"     Ingested {len(df_plots):,} forest inventory plot records.")

        print("  -> [Level 2] Scraping La Selva repeated-census annual plot AGB time series (1997-2018)...")
        df_time_series = self.time_series_scraper.fetch_la_selva_annual_plot_agb(force_refresh=force_refresh)
        print(f"     Ingested {len(df_time_series):,} plot-year records with census dates.")

        # --- LEVEL 3: Remote Sensing (LiDAR, Sentinel-2 Optical, Sentinel-1 SAR, ESA CCI) + Field Plots ---
        print("  -> [Level 3] Scraping ESA/NASA TropiSAR & AfriSAR Airborne LiDAR + Field Calibration Plots...")
        df_lidar_plots = self.rs_scraper.fetch_tropisar_afrisar_lidar_plots(force_refresh=force_refresh)
        print(f"     Ingested {len(df_lidar_plots):,} LiDAR + field calibration plots.")

        print("  -> [Level 3] Scraping Multi-Sensor Sentinel-2 Optical (NDVI/EVI/RedEdge) + Sentinel-1 SAR Plots...")
        df_sentinel_plots = self.rs_scraper.fetch_sentinel_optical_sar_field_plots(force_refresh=force_refresh)
        print(f"     Ingested {len(df_sentinel_plots):,} Sentinel-2/1 + field plot AGB records.")

        print("  -> [Level 3] Scraping FAO FRA 2020 National Forest Inventory vs. ESA CCI Satellite Biomass...")
        df_nfi_sat = self.rs_scraper.fetch_national_nfi_satellite_intercomparison(force_refresh=force_refresh)
        print(f"     Ingested {len(df_nfi_sat):,} country-level NFI vs. satellite intercomparison records.")

        # --- Build Unified Master Ground-Truth Benchmark Table ---
        print("  -> Building Unified Master Ground-Truth Benchmark Dataset (Input -> Formula -> Outcome + Timestamps)...")
        df_unified = self._build_unified_ground_truth_table(
            df_ifm_mrv=df_ifm_mrv,
            df_reg_projects=df_reg_projects,
            df_trees=df_trees,
            df_plots=df_plots,
            df_lidar_plots=df_lidar_plots,
            df_sentinel_plots=df_sentinel_plots,
            df_nfi_sat=df_nfi_sat,
            df_time_series=df_time_series,
        )
        print(f"     Built unified master table with {len(df_unified):,} standardized ground-truth rows.")

        # --- Run Standard Formula Benchmark Evaluations ---
        print("  -> Running Standard Formula Benchmark Evaluations across all levels...")
        df_benchmarks = run_standard_formula_benchmarks(
            tree_df=df_trees,
            ifm_df=df_ifm_mrv,
            lidar_df=df_lidar_plots,
            nfi_df=df_nfi_sat,
        )

        # --- Export all datasets to CSV, Parquet, and SQLite ---
        tables_to_export: Dict[str, pd.DataFrame] = {
            "level1_registry_projects_mrv": df_reg_projects,
            "level1_registry_credit_issuances": df_reg_issuances,
            "level1_verra_ifm_biophysical_mrv": df_ifm_mrv,
            "level2_tree_allometry_groundtruth": df_trees,
            "level2_allodb_equations_catalog": df_allodb,
            "level2_plot_inventory_fia_neotropical": df_plots,
            "level2_plot_time_series_la_selva": df_time_series,
            "level3_remote_sensing_lidar_sar_plots": df_lidar_plots,
            "level3_remote_sensing_sentinel_optical_sar_plots": df_sentinel_plots,
            "level3_national_nfi_satellite_intercomparison": df_nfi_sat,
            "unified_ground_truth_benchmark": df_unified,
            "standard_formulas_benchmark_evaluation": df_benchmarks,
        }

        sqlite_path = self.sqlite_dir / "forest_carbon_mrv_groundtruth.db"
        if sqlite_path.exists():
            sqlite_path.unlink()

        conn = sqlite3.connect(str(sqlite_path))
        exported_files: Dict[str, Dict[str, Any]] = {}

        try:
            for name, df in tables_to_export.items():
                csv_path = self.processed_dir / f"{name}.csv"
                pq_path = self.processed_dir / f"{name}.parquet"
                df.to_csv(csv_path, index=False)
                df.to_parquet(pq_path, index=False)
                df.to_sql(name, conn, if_exists="replace", index=False)
                exported_files[name] = {
                    "rows": int(len(df)),
                    "columns": int(len(df.columns)),
                    "csv_path": str(csv_path),
                    "parquet_path": str(pq_path),
                }
        finally:
            conn.close()

        # Collect all provenance records
        all_prov: List[ProvenanceRecord] = (
            self.registry_scraper.provenance_records
            + self.allometry_scraper.provenance_records
            + self.rs_scraper.provenance_records
            + self.time_series_scraper.provenance_records
        )

        manifest = {
            "pipeline_version": "1.0.0",
            "pipeline_started_at_utc": pipeline_start_utc,
            "pipeline_completed_at_utc": utc_now_iso(),
            "sqlite_database_path": str(sqlite_path),
            "total_provenance_sources_ingested": len(all_prov),
            "total_records_across_tables": int(sum(len(df) for df in tables_to_export.values())),
            "total_unified_ground_truth_records": int(len(df_unified)),
            "tables": exported_files,
            "formulas_registered": {k: asdict(v) for k, v in FORMULA_REGISTRY.items()},
            "provenance_manifest": [asdict(p) for p in all_prov],
        }

        manifest_path = self.metadata_dir / "ingestion_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        benchmark_report = {
            "generated_at_utc": utc_now_iso(),
            "benchmark_metrics": df_benchmarks.to_dict(orient="records"),
        }
        benchmark_report_path = self.metadata_dir / "benchmark_summary_report.json"
        benchmark_report_path.write_text(json.dumps(benchmark_report, indent=2), encoding="utf-8")

        print(f"[{utc_now_iso()}] Pipeline completed! SQLite DB: {sqlite_path}")
        return manifest

    def _build_unified_ground_truth_table(
        self,
        df_ifm_mrv: pd.DataFrame,
        df_reg_projects: pd.DataFrame,
        df_trees: pd.DataFrame,
        df_plots: pd.DataFrame,
        df_lidar_plots: pd.DataFrame,
        df_sentinel_plots: pd.DataFrame,
        df_nfi_sat: pd.DataFrame,
        df_time_series: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """
        Harmonize records across all 3 MRV levels into a single Unified Benchmark Schema:
        (record_id, observation_level, dataset_source, standard_or_registry, country,
         site_or_project_name, latitude, longitude, area_ha, data_generated_timestamp,
         data_ingested_timestamp_utc, input_variables_json, formula_id, formula_expression,
         ground_truth_outcome_value, ground_truth_outcome_unit,
         standard_formula_predicted_value, standardized_co2e_value, standardized_co2e_unit)
        """
        unified_rows: List[Dict[str, Any]] = []

        # 1. Biophysical IFM Registry Projects (78 projects)
        for _, r in df_ifm_mrv.iterrows():
            inputs = {
                "area_ha": self._clean_num(r["area_ha"]),
                "initial_carbon_stock_tCO2e_ha": self._clean_num(r["input_initial_carbon_stock_tCO2e_ha"]),
                "common_practice_baseline_tCO2e_ha": self._clean_num(r["input_common_practice_baseline_tCO2e_ha"]),
                "bl_ifm1_live_tCO2e": self._clean_num(r["input_bl_ifm1_live_trees_tCO2e"]),
                "bl_ifm3_dead_tCO2e": self._clean_num(r["input_bl_ifm3_standing_dead_tCO2e"]),
                "bl_ifm7_hwp_tCO2e": self._clean_num(r["input_bl_ifm7_in_use_hwp_tCO2e"]),
                "bl_ifm8_landfill_tCO2e": self._clean_num(r["input_bl_ifm8_landfill_hwp_tCO2e"]),
                "rp1_ifm1_live_tCO2e": self._clean_num(r["input_rp1_ifm1_live_trees_tCO2e"]),
                "rp1_ifm3_dead_tCO2e": self._clean_num(r["input_rp1_ifm3_standing_dead_tCO2e"]),
                "rp1_ifm7_hwp_tCO2e": self._clean_num(r["input_rp1_ifm7_in_use_hwp_tCO2e"]),
                "rp1_ifm8_landfill_tCO2e": self._clean_num(r["input_rp1_ifm8_landfill_hwp_tCO2e"]),
                "secondary_effects_leakage_tCO2e": self._clean_num(r["input_secondary_effects_leakage_tCO2e"]),
                "confidence_deduction_tCO2e": self._clean_num(r["input_confidence_deduction_tCO2e"]),
            }
            unified_rows.append(
                {
                    "record_id": f"IFM_MRV_{r['project_id']}",
                    "observation_level": "level1_registry_biophysical_mrv",
                    "dataset_source": "CarbonPlan_CARB_Verra_CAR_ACR_IFM_DB",
                    "standard_or_registry": str(r["registry"]),
                    "country": "United States",
                    "site_or_project_name": str(r["project_name"]),
                    "latitude": self._clean_num(r["latitude"]),
                    "longitude": self._clean_num(r["longitude"]),
                    "area_ha": self._clean_num(r["area_ha"]),
                    "data_generated_timestamp": str(r["data_generated_timestamp"]),
                    "data_ingested_timestamp_utc": str(r["data_ingested_timestamp_utc"]),
                    "input_variables_json": json.dumps(inputs),
                    "formula_id": str(r["formula_id"]),
                    "formula_expression": str(r["formula_expression"]),
                    "ground_truth_outcome_value": self._clean_num(r["outcome_registry_reported_tCO2e"]),
                    "ground_truth_outcome_unit": "tCO2e (project reporting period 1)",
                    "standard_formula_predicted_value": self._clean_num(r["outcome_formula_recalculated_tCO2e"]),
                    "standardized_co2e_value": self._clean_num(r["outcome_registry_reported_tCO2e"]),
                    "standardized_co2e_unit": "tCO2e",
                }
            )

        # 2. Registry Forest Projects with Issued Credits (Verra VCS, Gold Standard, ACR, CAR, ART-TREES, Cercarbono)
        issued_reg_df = df_reg_projects[df_reg_projects["issued_credits_tCO2e"] > 0]
        for _, r in issued_reg_df.iterrows():
            inputs = {
                "registry": r["registry"],
                "project_type": r["project_type"],
                "protocols": r["protocols_list"],
                "country": r["country"],
                "is_compliance": bool(r["is_compliance"]),
                "retired_credits_tCO2e": self._clean_num(r["retired_credits_tCO2e"]),
            }
            unified_rows.append(
                {
                    "record_id": f"REG_PROJ_{r['project_id']}",
                    "observation_level": "level1_registry_project_issuance_summary",
                    "dataset_source": "OffsetsDB_Global_Registries",
                    "standard_or_registry": f"{r['registry']} ({r['methodology_standard_name']})",
                    "country": str(r["country"] or "Unknown"),
                    "site_or_project_name": str(r["project_name"]),
                    "latitude": np.nan,
                    "longitude": np.nan,
                    "area_ha": np.nan,
                    "data_generated_timestamp": str(r["data_generated_timestamp"]),
                    "data_ingested_timestamp_utc": str(r["data_ingested_timestamp_utc"]),
                    "input_variables_json": json.dumps(inputs),
                    "formula_id": str(r["protocols_list"]),
                    "formula_expression": str(r["formula_expression"]),
                    "ground_truth_outcome_value": self._clean_num(r["issued_credits_tCO2e"]),
                    "ground_truth_outcome_unit": "tCO2e (total verified credits issued)",
                    "standard_formula_predicted_value": self._clean_num(r["issued_credits_tCO2e"]),
                    "standardized_co2e_value": self._clean_num(r["issued_credits_tCO2e"]),
                    "standardized_co2e_unit": "tCO2e",
                }
            )

        # 3. Level 2: Chave et al. (2014) Pantropical Destructive Harvest Trees (5,228 trees)
        for _, r in df_trees.iterrows():
            inputs = {
                "dbh_cm": self._clean_num(r["input_dbh_cm"]),
                "height_m": self._clean_num(r["input_height_m"]),
                "wood_density_g_cm3": self._clean_num(r["input_wood_density_g_cm3"]),
                "chave_E_index": self._clean_num(r["input_chave_E_index"]),
                "temp_seasonality_sd100": self._clean_num(r["input_temp_seasonality_sd100"]),
                "precip_seasonality_cv": self._clean_num(r["input_precip_seasonality_cv"]),
                "cwd_mm": self._clean_num(r["input_cwd_mm"]),
                "species": str(r["species_binomial"]),
            }
            fid = str(r["primary_formula_id"])
            fexpr = FORMULA_REGISTRY[fid].expression_code if fid in FORMULA_REGISTRY else ""
            unified_rows.append(
                {
                    "record_id": f"TREE_CHAVE_{int(r['tree_id'])}",
                    "observation_level": "level2_tree_allometry_destructive_harvest",
                    "dataset_source": "Chave_2014_Pantropical_Destructive_Harvest",
                    "standard_or_registry": "Chave et al. (2014) / Verra VM0007 / IPCC Tier 2-3",
                    "country": str(r["country"]),
                    "site_or_project_name": f"{r['full_locality']} ({r['species_binomial']})",
                    "latitude": self._clean_num(r["latitude"]),
                    "longitude": self._clean_num(r["longitude"]),
                    "area_ha": np.nan,
                    "data_generated_timestamp": str(r["data_generated_timestamp"]),
                    "data_ingested_timestamp_utc": str(r["data_ingested_timestamp_utc"]),
                    "input_variables_json": json.dumps(inputs),
                    "formula_id": fid,
                    "formula_expression": fexpr,
                    "ground_truth_outcome_value": self._clean_num(r["groundtruth_observed_agb_kg"]),
                    "ground_truth_outcome_unit": "kg AGB / tree (destructively weighed)",
                    "standard_formula_predicted_value": self._clean_num(r["formula_primary_agb_kg"]),
                    "standardized_co2e_value": self._clean_num(r["groundtruth_observed_co2e_kg"]),
                    "standardized_co2e_unit": "kg CO2e / tree",
                }
            )

        # 4. Level 2: Multi-Continent Field Plot Inventories (USFS FIA, Bennett 2020, Poorter 2ndFOR)
        for _, r in df_plots.iterrows():
            inputs = {
                "stand_age_yr": self._clean_num(r["input_stand_age_yr"]),
                "n_plots": self._clean_num(r["input_n_plots"]),
                "n_trees_sampled": self._clean_num(r["input_n_trees_sampled"]),
                "canopy_height_class": self._clean_num(r["input_canopy_height_class"]),
                "canopy_cover_class": self._clean_num(r["input_canopy_cover_class"]),
                "mean_annual_temp_C": self._clean_num(r["input_mean_annual_temp_C"]),
                "annual_precip_mm": self._clean_num(r["input_annual_precip_mm"]),
                "soil_clay_pct": self._clean_num(r["input_soil_clay_pct"]),
                "soil_ph": self._clean_num(r["input_soil_ph"]),
                "agb_Mg_ha": self._clean_num(r["input_agb_Mg_ha"]),
                "carbon_fraction": self._clean_num(r["input_carbon_fraction"]),
            }
            unified_rows.append(
                {
                    "record_id": str(r["plot_record_id"]),
                    "observation_level": "level2_plot_inventory",
                    "dataset_source": str(r["dataset_source"]),
                    "standard_or_registry": "IPCC 2006/2019 & USFS FIA Forest Inventory Standard",
                    "country": str(r["country"]),
                    "site_or_project_name": f"{r['site_or_region']} - {r['forest_type']}",
                    "latitude": self._clean_num(r["latitude"]),
                    "longitude": self._clean_num(r["longitude"]),
                    "area_ha": self._clean_num(r["input_stratum_area_ha"]),
                    "data_generated_timestamp": str(r["data_generated_timestamp"]),
                    "data_ingested_timestamp_utc": str(r["data_ingested_timestamp_utc"]),
                    "input_variables_json": json.dumps(inputs),
                    "formula_id": str(r["formula_id"]),
                    "formula_expression": str(r["formula_expression"]),
                    "ground_truth_outcome_value": self._clean_num(r["outcome_co2e_tCO2e_ha"]),
                    "ground_truth_outcome_unit": "tCO2e/ha",
                    "standard_formula_predicted_value": self._clean_num(r["formula_recalculated_co2e_tCO2e_ha"]),
                    "standardized_co2e_value": self._clean_num(r["outcome_co2e_tCO2e_ha"]),
                    "standardized_co2e_unit": "tCO2e/ha",
                }
            )

        # 5. Level 3: TropiSAR & AfriSAR Airborne LiDAR + Field Calibration Plots (1,093 plots)
        for _, r in df_lidar_plots.iterrows():
            inputs = {
                "lidar_tch_mean_m": self._clean_num(r["input_lidar_tch_mean_m"]),
                "lidar_h50_median_m": self._clean_num(r["input_lidar_h50_median_m"]),
                "lidar_gap_fraction_20m": self._clean_num(r["input_lidar_gap_fraction_20m"]),
                "lidar_canopy_cover_20m": self._clean_num(r["input_lidar_canopy_cover_20m"]),
                "lidar_height_stdv_m": self._clean_num(r["input_lidar_height_stdv_m"]),
                "basal_area_m2_ha": self._clean_num(r["input_basal_area_m2_ha"]),
                "wood_density_g_cm3": self._clean_num(r["input_wood_density_g_cm3"]),
                "stem_density_ha": self._clean_num(r["input_stem_density_ha"]),
            }
            unified_rows.append(
                {
                    "record_id": f"LIDAR_{r['campaign']}_{r['area_code']}",
                    "observation_level": "level3_remote_sensing_lidar_plot",
                    "dataset_source": "Zenodo_4938255_ESA_NASA_TropiSAR_AfriSAR",
                    "standard_or_registry": "ESA BIOMASS / Chave et al. (2014) Eq. 4 & Labrière et al. (2018)",
                    "country": str(r["country"]),
                    "site_or_project_name": f"{r['site_name']} Plot {r['plot_code']} ({r['area_code']})",
                    "latitude": self._clean_num(r["latitude"]),
                    "longitude": self._clean_num(r["longitude"]),
                    "area_ha": self._clean_num(r["plot_area_ha"]),
                    "data_generated_timestamp": str(r["data_generated_timestamp"]),
                    "data_ingested_timestamp_utc": str(r["data_ingested_timestamp_utc"]),
                    "input_variables_json": json.dumps(inputs),
                    "formula_id": "LABRIERE_CHAVE_2018_LIDAR_AGB",
                    "formula_expression": FORMULA_REGISTRY["LABRIERE_CHAVE_2018_LIDAR_AGB"].expression_code,
                    "ground_truth_outcome_value": self._clean_num(r["outcome_agb_loc_Mg_ha"]),
                    "ground_truth_outcome_unit": "Mg AGB/ha (in-situ Chave Eq.4 local H-D)",
                    "standard_formula_predicted_value": self._clean_num(r["formula_lidar_predicted_agb_Mg_ha"]),
                    "standardized_co2e_value": self._clean_num(r["outcome_co2e_loc_tCO2e_ha"]),
                    "standardized_co2e_unit": "tCO2e/ha",
                }
            )

        # 6. Level 3: Sentinel-2 Optical + Sentinel-1 SAR + Field Plot AGB (305 plots)
        for _, r in df_sentinel_plots.iterrows():
            inputs = {
                "B2_blue": self._clean_num(r["B2"]),
                "B3_green": self._clean_num(r["B3"]),
                "B4_red": self._clean_num(r["B4"]),
                "B5_re1": self._clean_num(r["B5"]),
                "B6_re2": self._clean_num(r["B6"]),
                "B7_re3": self._clean_num(r["B7"]),
                "B8_nir": self._clean_num(r["B8"]),
                "B11_swir1": self._clean_num(r["B11"]),
                "B12_swir2": self._clean_num(r["B12"]),
                "NDVI": self._clean_num(r["NDVI"]),
                "EVI": self._clean_num(r["EVI"]),
                "SAVI": self._clean_num(r["SAVI"]),
                "NDRE": self._clean_num(r["NDRE"]),
                "IRECI": self._clean_num(r["IRECI"]),
                "SAR_VV": self._clean_num(r["VV"]),
                "SAR_VH": self._clean_num(r["VH"]),
                "elevation_m": self._clean_num(r["ele"]),
                "slope_deg": self._clean_num(r["slope"]),
                "temp_C": self._clean_num(r["Temp"]),
                "precip_gsp_mm": self._clean_num(r["GSP"]),
            }
            unified_rows.append(
                {
                    "record_id": f"SENTINEL_PLOT_{int(r['ID'])}",
                    "observation_level": "level3_remote_sensing_optical_sar_plot",
                    "dataset_source": "Zenodo_15622257_Sentinel2_Sentinel1_Field_AGB",
                    "standard_or_registry": "ESA Sentinel-2/1 Multi-Sensor + IPCC (2006) Biomass-to-Carbon",
                    "country": str(r["country"]),
                    "site_or_project_name": f"Forest Inventory Plot {int(r['ID'])} (Zone {r['zone']})",
                    "latitude": self._clean_num(r["latitude"]),
                    "longitude": self._clean_num(r["longitude"]),
                    "area_ha": 0.06,
                    "data_generated_timestamp": str(r["data_generated_timestamp"]),
                    "data_ingested_timestamp_utc": str(r["data_ingested_timestamp_utc"]),
                    "input_variables_json": json.dumps(inputs),
                    "formula_id": str(r["formula_id"]),
                    "formula_expression": str(r["formula_expression"]),
                    "ground_truth_outcome_value": self._clean_num(r["outcome_co2e_tCO2e_ha"]),
                    "ground_truth_outcome_unit": "tCO2e/ha",
                    "standard_formula_predicted_value": self._clean_num(r["outcome_co2e_tCO2e_ha"]),
                    "standardized_co2e_value": self._clean_num(r["outcome_co2e_tCO2e_ha"]),
                    "standardized_co2e_unit": "tCO2e/ha",
                }
            )

        # 7. Level 3: National Forest Inventory (NFI) vs. ESA CCI Spaceborne Biomass
        for idx, r in df_nfi_sat.iterrows():
            inputs = {
                "forest_area_ha": self._clean_num(r.get("Forest_area_FRA2020")),
                "nfi_agb_ton_ha": self._clean_num(r.get("FRA_AGB_ton.ha")),
                "cci_satellite_agb_ton_ha": self._clean_num(r.get("CCI_Map_AGB_ton.ha")),
                "sampling_design": str(r.get("sampling_design") or ""),
                "plot_size_ha": self._clean_num(r.get("plotsize_ha")),
            }
            unified_rows.append(
                {
                    "record_id": f"NFI_CCI_{idx+1}_{str(r['Country']).replace(' ', '_')}",
                    "observation_level": "level3_national_nfi_vs_satellite",
                    "dataset_source": "Zenodo_6992943_FAO_FRA_NFI_vs_ESA_CCI",
                    "standard_or_registry": "FAO FRA 2020 National Forest Inventory & ESA CCI Biomass",
                    "country": str(r["Country"]),
                    "site_or_project_name": f"National Forest Inventory ({r['Country']})",
                    "latitude": np.nan,
                    "longitude": np.nan,
                    "area_ha": self._clean_num(r.get("Forest_area_FRA2020")),
                    "data_generated_timestamp": str(r["data_generated_timestamp"]),
                    "data_ingested_timestamp_utc": str(r["data_ingested_timestamp_utc"]),
                    "input_variables_json": json.dumps(inputs),
                    "formula_id": str(r["formula_id"]),
                    "formula_expression": str(r["formula_expression"]),
                    "ground_truth_outcome_value": self._clean_num(r["outcome_nfi_groundtruth_co2e_tCO2e_ha"]),
                    "ground_truth_outcome_unit": "tCO2e/ha (NFI ground truth)",
                    "standard_formula_predicted_value": self._clean_num(r["outcome_esa_cci_satellite_co2e_tCO2e_ha"]),
                    "standardized_co2e_value": self._clean_num(r["outcome_nfi_groundtruth_co2e_tCO2e_ha"]),
                    "standardized_co2e_unit": "tCO2e/ha",
                }
            )

        # 8. Level 2: La Selva repeated-census plot-year time series
        if df_time_series is not None:
            for _, r in df_time_series.iterrows():
                inputs = {
                    "plot_id": str(r["plot_id"]),
                    "census_year": int(r["census_year"]),
                    "n_stems_ge10cm": int(r["n_stems_ge10cm"]),
                    "eagb_kg_sum": self._clean_num(r["eagb_kg_sum"]),
                    "plot_area_ha": self._clean_num(r["plot_area_ha"]),
                    "survey_date_first": None if pd.isna(r["survey_date_first"]) else str(r["survey_date_first"]),
                    "delta_co2e_tCO2e_ha_yr": self._clean_num(r["delta_co2e_tCO2e_ha_yr"]),
                }
                unified_rows.append(
                    {
                        "record_id": f"LASELVA_{r['plot_id']}_{int(r['census_year'])}",
                        "observation_level": "level2_plot_time_series",
                        "dataset_source": "Zenodo_4574686_LaSelva_Annual_Census",
                        "standard_or_registry": "Repeated-census permanent plots + IPCC (2006) Biomass-to-Carbon",
                        "country": str(r["country"]),
                        "site_or_project_name": f"La Selva plot {r['plot_id']} ({int(r['census_year'])})",
                        "latitude": self._clean_num(r["latitude"]),
                        "longitude": self._clean_num(r["longitude"]),
                        "area_ha": self._clean_num(r["plot_area_ha"]),
                        "data_generated_timestamp": str(r["data_generated_timestamp"]),
                        "data_ingested_timestamp_utc": str(r["data_ingested_timestamp_utc"]),
                        "input_variables_json": json.dumps(inputs),
                        "formula_id": str(r["formula_id"]),
                        "formula_expression": str(r["formula_expression"]),
                        "ground_truth_outcome_value": self._clean_num(r["outcome_co2e_tCO2e_ha"]),
                        "ground_truth_outcome_unit": "tCO2e/ha",
                        "standard_formula_predicted_value": self._clean_num(r["outcome_co2e_tCO2e_ha"]),
                        "standardized_co2e_value": self._clean_num(r["outcome_co2e_tCO2e_ha"]),
                        "standardized_co2e_unit": "tCO2e/ha",
                    }
                )

        df_out = pd.DataFrame(unified_rows)

        # Normalize free-text timestamps into queryable ISO-8601 bounds + precision + basis.
        parsed = df_out["data_generated_timestamp"].map(normalize_timestamp)
        df_out["measurement_date_start"] = parsed.map(lambda d: d["start"])
        df_out["measurement_date_end"] = parsed.map(lambda d: d["end"])
        df_out["timestamp_precision"] = parsed.map(lambda d: d["precision"])
        df_out["timestamp_basis"] = df_out["dataset_source"].map(TIMESTAMP_BASIS).fillna("measurement")
        return df_out

    @staticmethod
    def _clean_num(val: Any) -> float | None:
        if val is None:
            return None
        try:
            f = float(val)
            return None if (np.isnan(f) or np.isinf(f)) else round(f, 6)
        except Exception:
            return None
