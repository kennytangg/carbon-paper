"""
Level 1 Scraper: Voluntary & Compliance Carbon Registry Forest MRV Datasets.

Sources ingested:
1. Harmonized Global Carbon Registry Database (Verra VCS, Gold Standard, ACR, CAR, ART-TREES, Cercarbono)
   via CarbonPlan OffsetsDB API (`https://carbonplan.org/research/offsets-db/api/query`).
   - Forest carbon projects (`category=forest`) with methodology/protocol codes (e.g. VM0007, VM0015,
     VM0047, AR-ACM0003, Gold Standard A/R, CAR US Forest, ACR IFM), country, status, listing dates,
     first issuance dates, total issued/retired tCO2e.
   - Verified credit issuance transactions (`transaction_type=issuance`) with vintage year,
     issuance transaction timestamp, and issued tCO2e quantity.
2. Biophysical & Pool-Level Forest Carbon MRV Database (`forest-offsets-database-v1.0.csv` &
   `projects-crediting.json` from CarbonPlan / CARB / Verra VCSOPR / CAR / ACR).
   - Contains full project-level input variables (acreage/hectares, centroid coordinates,
     baseline carbon pools IFM-1/3/7/8, reporting period 1 start/end dates & carbon pools IFM-1/3/7/8,
     secondary effects leakage, confidence deduction, buffer pool contribution, initial carbon stock,
     common practice baseline, and species basal area composition), the exact IFM MRV accounting
     formula, and reported vs formula-recalculated tCO2e outcomes.
"""

from __future__ import annotations

import ast
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from src.formulas import (
    ACRES_TO_HECTARES,
    FORMULA_REGISTRY,
    compute_ifm_net_credits_tco2e,
)
from src.scrapers.base import BaseScraper, utc_now_iso


PROTOCOL_FORMULA_MAP: Dict[str, Tuple[str, str]] = {
    "verra-vm0007": (
        "Verra VCS VM0007 REDD+ Methodology Framework (REDD+ MF)",
        "NER_t = (Delta_C_BSL_t - Delta_C_WPS_t - Delta_C_LK_t) * (1 - f_buffer)",
    ),
    "verra-vm0006": (
        "Verra VCS VM0006 Methodology for Carbon Accounting for Mosaic and Landscape-scale REDD Projects",
        "NER_t = (E_BSL_deforest + E_BSL_degrad - E_WPS - E_LK) * (1 - f_buffer)",
    ),
    "verra-vm0009": (
        "Verra VCS VM0009 Methodology for Avoided Ecosystem Conversion",
        "NER_t = (Delta_C_BSL - Delta_C_WPS - Delta_C_LK) * (1 - f_buffer)",
    ),
    "verra-vm0010": (
        "Verra VCS VM0010 Methodology for Improved Forest Management: Conversion from Logged to Protected Forest (LtPF)",
        "NER_t = (Delta_C_WPS_IFM - Delta_C_BSL_logging - E_LK) * (1 - f_buffer)",
    ),
    "verra-vm0015": (
        "Verra VCS VM0015 Methodology for Avoided Unplanned Deforestation",
        "NER_t = (A_BSL_t * C_stock_ha - Delta_C_WPS_t - Delta_C_LK_t) * (1 - f_buffer)",
    ),
    "verra-vm0037": (
        "Verra VCS VM0037 Implementation of Silvicultural Activities in Boreal and Temperate Forests",
        "NER_t = (Delta_C_WPS_silv - Delta_C_BSL - E_LK) * (1 - f_buffer)",
    ),
    "verra-vm0045": (
        "Verra VCS VM0045 Methodology for Improved Forest Management Using Dynamic Matched Baselines from National Forest Inventories",
        "NER_t = Area_ha * (Delta_C_project_ha - Delta_C_matched_NFI_control_ha) - E_LK",
    ),
    "verra-vm0047": (
        "Verra VCS VM0047 Afforestation, Reforestation, and Revegetation (ARR)",
        "NER_t = (Delta_C_ARR_tree_non_tree - Delta_C_BSL_matched - E_LK) * (1 - f_buffer)",
    ),
    "verra-ar-acm0003": (
        "UNFCCC CDM / Verra VCS AR-ACM0003 Afforestation and Reforestation of Lands except Wetlands",
        "Delta_C_AR_t = ((44/12) * CF * sum_stratum(Area_i * (AGB_i * (1 + R_i)))) - Delta_C_BSL_t - GHGE_t - LK_t",
    ),
    "verra-ar-ams0007": (
        "UNFCCC CDM / Verra VCS AR-AMS0007 Simplified A/R Methodology for Small-Scale Forest Projects",
        "Delta_C_AR_t = ((44/12) * CF * Area_ha * Biomass_growth_rate_t_ha) - Delta_C_BSL_t - LK_t",
    ),
    "car-us-forest": (
        "Climate Action Reserve (CAR) / CARB U.S. Forest Protocol (IFM / Reforestation / Avoided Conversion)",
        "CRTs = ((RP_IFM1 - BL_IFM1) + (RP_IFM3 - BL_IFM3)) + ((RP_IFM7 - BL_IFM7) + (RP_IFM8 - BL_IFM8)) + SE - CD",
    ),
    "acr-ifm-nonfed": (
        "American Carbon Registry (ACR) Improved Forest Management on Non-Federal U.S. Forestlands",
        "ERTs = (Delta_C_project_pools - Delta_C_baseline_NPV) * (1 - f_leakage) * (1 - f_uncertainty)",
    ),
    "art-trees": (
        "ART-TREES (The REDD+ Environmental Excellence Standard) Jurisdictional Forest Carbon Standard",
        "TREES_Credits_t = (Crediting_Level_tCO2e_yr - Annual_Jurisdictional_Emissions_tCO2e) * (1 - f_buffer - f_leakage)",
    ),
}


def resolve_protocol_formula(protocols: List[str], registry: str, project_type: str) -> Tuple[str, str]:
    """Return human-readable methodology name and algebraic formula for a registry project."""
    for p in protocols:
        p_lower = str(p).lower().strip()
        if p_lower in PROTOCOL_FORMULA_MAP:
            return PROTOCOL_FORMULA_MAP[p_lower]
    reg_lower = str(registry).lower()
    ptype_lower = str(project_type).lower()
    if "gold-standard" in reg_lower:
        return (
            "Gold Standard Afforestation/Reforestation (A/R) & Land Use Forests Methodology",
            "GS_VER_t = (sum_stratum(Area_i * (AGB_i + BGB_i) * CF * 44/12) - Baseline_C_t - Leakage_t) * (1 - Buffer_pool)",
        )
    if "verra" in reg_lower:
        if "redd" in ptype_lower:
            return PROTOCOL_FORMULA_MAP["verra-vm0007"]
        if "afforestation" in ptype_lower or "reforestation" in ptype_lower:
            return PROTOCOL_FORMULA_MAP["verra-ar-acm0003"]
        if "improved forest" in ptype_lower:
            return PROTOCOL_FORMULA_MAP["verra-vm0010"]
    if "climate-action-reserve" in reg_lower:
        return PROTOCOL_FORMULA_MAP["car-us-forest"]
    if "american-carbon-registry" in reg_lower:
        return PROTOCOL_FORMULA_MAP["acr-ifm-nonfed"]
    if "art-trees" in reg_lower:
        return PROTOCOL_FORMULA_MAP["art-trees"]
    return (
        f"{registry.upper()} Forest Carbon Standard ({project_type or 'Forestry'})",
        "Net_tCO2e = (Project_Carbon_Stock_tCO2e - Baseline_Carbon_Stock_tCO2e - Leakage_tCO2e) * (1 - Buffer_Fraction)",
    )


class RegistryMRVScraper(BaseScraper):
    """Ingests Registry-level Forest Carbon Projects, Issuances, and Biophysical IFM MRV data."""

    OFFSETS_DB_QUERY_URL = "https://carbonplan.org/research/offsets-db/api/query"
    FOREST_OFFSETS_CSV_URL = (
        "https://carbonplan-forests.s3.us-west-2.amazonaws.com/offsets/database/forest-offsets-database-v1.0.csv"
    )
    PROJECTS_CREDITING_JSON_URL = (
        "https://raw.githubusercontent.com/carbonplan/forest-offsets-web/main/data/projects-crediting.json"
    )

    def fetch_registry_forest_projects(
        self,
        max_pages_per_registry: Dict[str, int] | None = None,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Scrape forest carbon projects across Verra (VCS), Gold Standard (GLD),
        American Carbon Registry (ACR), Climate Action Reserve (CAR), ART-TREES, and Cercarbono.
        """
        if max_pages_per_registry is None:
            # Pull comprehensive samples from every major registry (all Gold Standard, ART-TREES, Cercarbono,
            # plus 500 Verra VCS, 200 ACR, 200 CAR projects = ~1,040 projects)
            max_pages_per_registry = {
                "verra": 5,
                "gold-standard": 1,
                "american-carbon-registry": 2,
                "climate-action-reserve": 2,
                "art-trees": 1,
                "cercarbono": 1,
            }

        all_rows: List[Dict[str, Any]] = []
        for reg, max_pages in max_pages_per_registry.items():
            for page in range(1, max_pages + 1):
                url = (
                    f"{self.OFFSETS_DB_QUERY_URL}?path=projects/&category=forest"
                    f"&registry={reg}&current_page={page}&per_page=100"
                )
                cache_fn = f"offsets_db_projects_{reg}_page{page}.json"
                payload, prov = self.fetch_json(
                    url=url,
                    cache_filename=cache_fn,
                    source_id=f"OFFSETS_DB_PROJECTS_{reg.upper()}_P{page}",
                    source_name=f"OffsetsDB Harmonized Forest Carbon Projects ({reg}, page {page})",
                    observation_level="registry_project_mrv",
                    doi_or_registry=reg.upper(),
                    data_generated_period="1999-2025 (Registry Listing & Issuance Dates)",
                    description=f"Forest carbon credit projects registered under {reg}",
                    force_refresh=force_refresh,
                )
                items = payload.get("data", [])
                prov.record_count = len(items)
                ingested_ts = prov.ingested_at_utc

                for item in items:
                    protocols = item.get("protocol") or []
                    if isinstance(protocols, str):
                        protocols = [protocols]
                    method_name, formula_expr = resolve_protocol_formula(
                        protocols, item.get("registry", reg), item.get("project_type", "")
                    )
                    gen_ts = (
                        item.get("first_issuance_at")
                        or item.get("listed_at")
                        or (item.get("clips", [{}])[0].get("date") if item.get("clips") else None)
                        or "unknown"
                    )
                    issued = float(item.get("issued") or 0.0)
                    retired = float(item.get("retired") or 0.0)
                    active_stock = issued - retired

                    all_rows.append(
                        {
                            "project_id": item.get("project_id"),
                            "project_name": item.get("name"),
                            "registry": item.get("registry", reg),
                            "category": item.get("category", "forest"),
                            "project_type": item.get("project_type") or "Forestry",
                            "project_type_source": item.get("project_type_source"),
                            "protocols_list": ",".join(protocols) if protocols else "registry-default",
                            "methodology_standard_name": method_name,
                            "formula_expression": formula_expr,
                            "country": item.get("country"),
                            "proponent": item.get("proponent"),
                            "status": item.get("status"),
                            "is_compliance": bool(item.get("is_compliance", False)),
                            "listed_at_timestamp": item.get("listed_at"),
                            "first_issuance_at_timestamp": item.get("first_issuance_at"),
                            "first_retirement_at_timestamp": item.get("first_retirement_at"),
                            "data_generated_timestamp": gen_ts,
                            "data_ingested_timestamp_utc": ingested_ts,
                            "issued_credits_tCO2e": issued,
                            "retired_credits_tCO2e": retired,
                            "remaining_active_credits_tCO2e": active_stock,
                            "project_registry_url": item.get("project_url"),
                        }
                    )
                pagination = payload.get("pagination", {})
                if page >= int(pagination.get("total_pages", 1)):
                    break

        df = pd.DataFrame(all_rows)
        if not df.empty:
            df = df.drop_duplicates(subset=["project_id"]).reset_index(drop=True)
        return df

    def fetch_registry_credit_issuances(
        self,
        max_pages_per_registry: Dict[str, int] | None = None,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Scrape forest carbon credit issuance transactions across Verra VCS, Gold Standard,
        ACR, CAR, ART-TREES, and Cercarbono, capturing vintage year, transaction_date, and quantity (tCO2e).
        """
        if max_pages_per_registry is None:
            max_pages_per_registry = {
                "verra": 5,
                "gold-standard": 2,
                "american-carbon-registry": 2,
                "climate-action-reserve": 2,
                "art-trees": 1,
                "cercarbono": 1,
            }

        issuance_rows: List[Dict[str, Any]] = []
        for reg, max_pages in max_pages_per_registry.items():
            for page in range(1, max_pages + 1):
                url = (
                    f"{self.OFFSETS_DB_QUERY_URL}?path=credits/&category=forest"
                    f"&registry={reg}&transaction_type=issuance&current_page={page}&per_page=100"
                )
                cache_fn = f"offsets_db_issuances_{reg}_page{page}.json"
                payload, prov = self.fetch_json(
                    url=url,
                    cache_filename=cache_fn,
                    source_id=f"OFFSETS_DB_ISSUANCES_{reg.upper()}_P{page}",
                    source_name=f"OffsetsDB Verified Forest Credit Issuances ({reg}, page {page})",
                    observation_level="registry_credit_issuance",
                    doi_or_registry=reg.upper(),
                    data_generated_period="2002-2025 (Issuance Transaction Dates & Vintages)",
                    description=f"Verified forest carbon credit issuance records for {reg}",
                    force_refresh=force_refresh,
                )
                items = payload.get("data", [])
                prov.record_count = len(items)
                ingested_ts = prov.ingested_at_utc

                for item in items:
                    projs = item.get("projects") or [{}]
                    proj_info = projs[0] if projs else {}
                    proj_id = proj_info.get("project_id") or item.get("project_id")
                    proj_type = proj_info.get("project_type") or "Forestry"
                    method_name, formula_expr = resolve_protocol_formula([], reg, proj_type)
                    tx_date = item.get("transaction_date")
                    vintage = item.get("vintage")

                    issuance_rows.append(
                        {
                            "issuance_id": item.get("id"),
                            "project_id": proj_id,
                            "registry": reg,
                            "category": proj_info.get("category", "forest"),
                            "project_type": proj_type,
                            "vintage_year": vintage,
                            "transaction_date": tx_date,
                            "transaction_type": item.get("transaction_type", "issuance"),
                            "quantity_issued_tCO2e": float(item.get("quantity") or 0.0),
                            "methodology_standard_name": method_name,
                            "formula_expression": formula_expr,
                            "data_generated_timestamp": tx_date or str(vintage),
                            "data_ingested_timestamp_utc": ingested_ts,
                        }
                    )
                pagination = payload.get("pagination", {})
                if page >= int(pagination.get("total_pages", 1)):
                    break

        df = pd.DataFrame(issuance_rows)
        if not df.empty:
            df = df.drop_duplicates(subset=["issuance_id"]).reset_index(drop=True)
        return df

    def fetch_biophysical_ifm_mrv_projects(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Ingest the 78 detailed Forest Carbon Offset MRV projects (`forest-offsets-database-v1.0.csv`
        and `projects-crediting.json`), containing pool-by-pool carbon stocks, baseline vs reporting
        period 1 values, species basal areas, and exact IFM crediting formula verification.
        """
        csv_bytes, prov_csv = self.fetch_bytes(
            url=self.FOREST_OFFSETS_CSV_URL,
            cache_filename="forest_offsets_database_v1.0.csv",
            source_id="CARBONPLAN_FOREST_OFFSETS_DB_V1",
            source_name="CarbonPlan / CARB / Verra VCSOPR / CAR / ACR Biophysical Forest Offsets MRV Database",
            observation_level="registry_project_mrv",
            doi_or_registry="10.1111/gcb.15943 (Badgley et al. 2022 Global Change Biology)",
            data_generated_period="2013-2020 (Project Reporting Period 1 Start/End Dates)",
            description="Complete biophysical & pool-level MRV inputs, baselines, species basal areas, and verified credits for 78 forest offset projects.",
            force_refresh=force_refresh,
        )
        cred_json, prov_json = self.fetch_json(
            url=self.PROJECTS_CREDITING_JSON_URL,
            cache_filename="forest_offsets_projects_crediting.json",
            source_id="CARBONPLAN_PROJECTS_CREDITING_JSON",
            source_name="CarbonPlan Forest Offsets Crediting & Over-Crediting Metadata",
            observation_level="registry_project_mrv",
            doi_or_registry="10.1111/gcb.15943",
            data_generated_period="2013-2020",
            description="Project location, developers, owners, initial carbon stock, common practice, and alternative baseline metrics.",
            force_refresh=force_refresh,
        )

        cred_map: Dict[str, Dict[str, Any]] = {item["id"]: item for item in cred_json if "id" in item}
        raw_df = pd.read_csv(io.BytesIO(csv_bytes))
        prov_csv.record_count = len(raw_df)
        prov_json.record_count = len(cred_json)
        ingested_ts = prov_csv.ingested_at_utc

        formula_meta = FORMULA_REGISTRY["CARB_VERRA_ACR_CAR_IFM_CREDITING"]
        rows: List[Dict[str, Any]] = []

        for _, row in raw_df.iterrows():
            opr_id = str(row.get("opr_id") or row.get("id"))
            cred_info = cred_map.get(opr_id, {})

            # Parse nested dicts safely
            baseline_dict = self._safe_eval_dict(row.get("baseline"))
            rp1_dict = self._safe_eval_dict(row.get("rp_1"))
            centroids = self._safe_eval_list(row.get("shape_centroid"))
            supersections = self._safe_eval_list(row.get("supersection_ids"))
            assessment_areas = self._safe_eval_list(row.get("assessment_areas"))

            lon, lat = (np.nan, np.nan)
            if centroids and isinstance(centroids[0], (list, tuple)) and len(centroids[0]) >= 2:
                lon, lat = float(centroids[0][0]), float(centroids[0][1])
            elif cred_info.get("shape_centroid") and len(cred_info["shape_centroid"]) >= 2:
                lon, lat = float(cred_info["shape_centroid"][0]), float(cred_info["shape_centroid"][1])

            acreage = float(row.get("acreage") or cred_info.get("area") or np.nan)
            area_ha = acreage * ACRES_TO_HECTARES if not np.isnan(acreage) else np.nan

            bl_ifm1 = float(baseline_dict.get("ifm_1") or 0.0)
            bl_ifm3 = float(baseline_dict.get("ifm_3") or 0.0)
            bl_ifm7 = float(baseline_dict.get("ifm_7") or 0.0)
            bl_ifm8 = float(baseline_dict.get("ifm_8") or 0.0)

            rp_ifm1 = float(rp1_dict.get("ifm_1") or 0.0)
            rp_ifm3 = float(rp1_dict.get("ifm_3") or 0.0)
            rp_ifm7 = float(rp1_dict.get("ifm_7") or 0.0)
            rp_ifm8 = float(rp1_dict.get("ifm_8") or 0.0)
            sec_eff = float(rp1_dict.get("secondary_effects") or 0.0)
            conf_ded = float(rp1_dict.get("confidence_deduction") or 0.0)

            rp_start = rp1_dict.get("start_date") or "unknown"
            rp_end = rp1_dict.get("end_date") or "unknown"

            # Recompute credits using the exact IFM formula
            recalc_arbocs = compute_ifm_net_credits_tco2e(
                bl_ifm1=bl_ifm1,
                bl_ifm3=bl_ifm3,
                bl_ifm7=bl_ifm7,
                bl_ifm8=bl_ifm8,
                rp_ifm1=rp_ifm1,
                rp_ifm3=rp_ifm3,
                rp_ifm7=rp_ifm7,
                rp_ifm8=rp_ifm8,
                secondary_effects=sec_eff,
                confidence_deduction=conf_ded,
            )

            arbocs_calc_col = float(row.get("arbocs_calculated") or np.nan)
            arbocs_rep_col = float(row.get("arbocs_reported") or np.nan)
            arbocs_iss_col = float(row.get("arbocs_issuance") or np.nan)

            init_c_acre = float(row.get("carbon_initial_carbon_stock") or np.nan)
            cp_c_acre = float(row.get("carbon_common_practice") or np.nan)
            slag_c_acre = float(row.get("carbon_average_slag_baseline") or np.nan)

            # Convert tCO2e/acre to tCO2e/ha (divide by 0.40468564224)
            init_c_ha = init_c_acre / ACRES_TO_HECTARES if not np.isnan(init_c_acre) else np.nan
            cp_c_ha = cp_c_acre / ACRES_TO_HECTARES if not np.isnan(cp_c_acre) else np.nan
            slag_c_ha = slag_c_acre / ACRES_TO_HECTARES if not np.isnan(slag_c_acre) else np.nan

            # Determine registry from opr_id prefix (VCSOPR -> Verra VCS, CAR -> Climate Action Reserve, ACR -> American Carbon Registry)
            if opr_id.startswith("VCS"):
                registry_name = "Verra (VCS / ARB Compliance)"
            elif opr_id.startswith("CAR"):
                registry_name = "Climate Action Reserve (CAR / ARB)"
            elif opr_id.startswith("ACR"):
                registry_name = "American Carbon Registry (ACR / ARB)"
            else:
                registry_name = "CARB / Registry IFM"

            # Summarize species basal area from assessment_areas
            species_records = []
            n_strata = 0
            for aa in assessment_areas:
                if isinstance(aa, dict):
                    if aa.get("code") == 999:
                        species_records = aa.get("species", [])
                    else:
                        n_strata += 1

            rows.append(
                {
                    "project_id": opr_id,
                    "arb_id": row.get("arb_id"),
                    "project_name": row.get("name"),
                    "registry": registry_name,
                    "location": cred_info.get("location", "United States"),
                    "latitude": lat,
                    "longitude": lon,
                    "area_acres": acreage,
                    "area_ha": area_ha,
                    "n_assessment_strata": n_strata,
                    "n_dominant_species": len(species_records),
                    "supersection_ids": json.dumps(supersections),
                    "species_basal_area_json": json.dumps(species_records),
                    "rp1_start_date": rp_start,
                    "rp1_end_date": rp_end,
                    "data_generated_timestamp": f"{rp_start}/{rp_end}",
                    "data_ingested_timestamp_utc": ingested_ts,
                    # Input variables (Carbon Pools & Baseline parameters)
                    "input_initial_carbon_stock_tCO2e_acre": init_c_acre,
                    "input_initial_carbon_stock_tCO2e_ha": init_c_ha,
                    "input_common_practice_baseline_tCO2e_acre": cp_c_acre,
                    "input_common_practice_baseline_tCO2e_ha": cp_c_ha,
                    "input_average_slag_baseline_tCO2e_ha": slag_c_ha,
                    "input_bl_ifm1_live_trees_tCO2e": bl_ifm1,
                    "input_bl_ifm3_standing_dead_tCO2e": bl_ifm3,
                    "input_bl_ifm7_in_use_hwp_tCO2e": bl_ifm7,
                    "input_bl_ifm8_landfill_hwp_tCO2e": bl_ifm8,
                    "input_rp1_ifm1_live_trees_tCO2e": rp_ifm1,
                    "input_rp1_ifm3_standing_dead_tCO2e": rp_ifm3,
                    "input_rp1_ifm7_in_use_hwp_tCO2e": rp_ifm7,
                    "input_rp1_ifm8_landfill_hwp_tCO2e": rp_ifm8,
                    "input_secondary_effects_leakage_tCO2e": sec_eff,
                    "input_confidence_deduction_tCO2e": conf_ded,
                    "input_buffer_pool_contribution_tCO2e": float(row.get("buffer_contribution") or 0.0),
                    # Formula metadata
                    "formula_id": formula_meta.formula_id,
                    "formula_name": formula_meta.name,
                    "formula_expression": formula_meta.expression_code,
                    # Outcomes
                    "outcome_formula_recalculated_tCO2e": recalc_arbocs,
                    "outcome_db_calculated_tCO2e": arbocs_calc_col,
                    "outcome_registry_reported_tCO2e": arbocs_rep_col,
                    "outcome_registry_issued_tCO2e": arbocs_iss_col,
                    "outcome_credits_per_ha_tCO2e": (arbocs_iss_col / area_ha) if (area_ha and area_ha > 0) else np.nan,
                    "verification_residual_vs_db_calc": recalc_arbocs - arbocs_calc_col,
                    "verification_residual_vs_reported": recalc_arbocs - arbocs_rep_col,
                }
            )

        return pd.DataFrame(rows)

    @staticmethod
    def _safe_eval_dict(val: Any) -> Dict[str, Any]:
        if isinstance(val, dict):
            return val
        if not isinstance(val, str) or not val.strip() or val.strip() == "nan":
            return {}
        try:
            res = ast.literal_eval(val)
            return res if isinstance(res, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _safe_eval_list(val: Any) -> List[Any]:
        if isinstance(val, list):
            return val
        if not isinstance(val, str) or not val.strip() or val.strip() == "nan":
            return []
        try:
            res = ast.literal_eval(val)
            return res if isinstance(res, list) else []
        except Exception:
            return []
