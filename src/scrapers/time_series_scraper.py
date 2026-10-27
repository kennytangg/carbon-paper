"""
Level 2 Scraper: Long-term repeated-census plot time series (true multi-year timestamps).

Sources ingested:
1. La Selva Biological Station (Costa Rica) annual census, Clark et al. (Dryad 10.5061/dryad.fn2z34tst,
   mirrored at Zenodo 4574686, CC0). Stem-level estimated above-ground biomass (EAGB, kg; Brown tropical
   wet forest allometry) for all stems >= 10 cm DBH in 18 x 0.50 ha plots, censused every year 1997-2018,
   aggregated here to plot-year AGB stock (Mg/ha) and tCO2e/ha. The companion annual canopy-height survey
   supplies the exact field-survey calendar dates, which are attached to each plot-year.

   Because each plot is re-measured every year, this table lets a DMRV algorithm be scored *at a specific
   timestamp* and on *year-over-year change* (net removals), the quantity registries actually issue credits on.
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd

from src.formulas import (
    IPCC_DEFAULT_CARBON_FRACTION_TROPICAL,
    MOLECULAR_WEIGHT_RATIO_CO2_C,
)
from src.scrapers.base import BaseScraper

LA_SELVA_PLOT_AREA_HA = 0.5


class LongTermPlotTimeSeriesScraper(BaseScraper):
    """Ingests repeated-census plots with one record per plot per measurement year."""

    LA_SELVA_EAGB_URL = (
        "https://zenodo.org/api/records/4574686/files/Estimated_Above-Ground_Biomass_1997-2018.xlsx/content"
    )
    LA_SELVA_CANOPY_URL = "https://zenodo.org/api/records/4574686/files/Canopy_heights_1999-2018.csv/content"

    def fetch_la_selva_annual_plot_agb(self, force_refresh: bool = False) -> pd.DataFrame:
        """Return plot-year AGB/carbon/CO2e ground truth with census year, survey dates and annual change."""
        common = dict(
            observation_level="plot_time_series",
            doi_or_registry="10.5061/dryad.fn2z34tst (Zenodo 4574686)",
            data_generated_period="1997-2018 (annual census)",
            force_refresh=force_refresh,
        )
        eagb_bytes, prov = self.fetch_bytes(
            url=self.LA_SELVA_EAGB_URL,
            cache_filename="laselva_estimated_agb_1997_2018.xlsx",
            source_id="ZENODO_4574686_LASELVA_EAGB",
            source_name="La Selva Costa Rica Annual Stem-Level Estimated AGB 1997-2018 (Clark et al.)",
            description="Stem-level EAGB (kg) in 18 x 0.5 ha plots, censused annually 1997-2018.",
            **common,
        )

        canopy_dates_df: pd.DataFrame | None = None
        try:
            canopy_bytes, prov_canopy = self.fetch_bytes(
                url=self.LA_SELVA_CANOPY_URL,
                cache_filename="laselva_canopy_heights_1999_2018.csv",
                source_id="ZENODO_4574686_LASELVA_CANOPY_DATES",
                source_name="La Selva Costa Rica Annual Canopy Height Survey 1999-2018 (survey dates)",
                description="Annual canopy-height survey in the same plots; supplies exact field survey dates.",
                **common,
            )
            canopy = pd.read_csv(
                io.StringIO(canopy_bytes.decode("utf-8", errors="replace")),
                header=None,
                usecols=[0, 2, 6],
                names=["census_year", "plot_id", "survey_date"],
            )
            canopy["survey_date"] = pd.to_datetime(canopy["survey_date"], format="%d-%b-%y", errors="coerce")
            canopy = canopy.dropna(subset=["survey_date"])
            dates = (
                canopy.groupby(["plot_id", "census_year"])["survey_date"]
                .agg(survey_date_first="min", survey_date_last="max")
                .reset_index()
            )
            for c in ("survey_date_first", "survey_date_last"):
                dates[c] = dates[c].dt.strftime("%Y-%m-%d")
            prov_canopy.record_count = len(canopy)
            canopy_dates_df = dates
        except Exception:
            # Fall back gracefully if canopy heights CSV is not cached or network is unavailable
            canopy_dates_df = None

        raw = pd.read_excel(io.BytesIO(eagb_bytes), header=None)
        # Header notes occupy leading rows beginning with '*'; data rows are stem, plot, year, eBMkg_SB.
        raw = raw[~raw[0].astype(str).str.startswith("*")]
        stems = raw.iloc[:, :4].copy()
        stems.columns = ["stem_id", "plot_id", "census_year", "eagb_kg"]
        stems = stems.dropna(subset=["plot_id", "census_year", "eagb_kg"])
        stems["census_year"] = stems["census_year"].astype(int)
        stems["eagb_kg"] = stems["eagb_kg"].astype(float)

        agg = (
            stems.groupby(["plot_id", "census_year"])
            .agg(n_stems_ge10cm=("stem_id", "nunique"), eagb_kg_sum=("eagb_kg", "sum"))
            .reset_index()
        )

        if canopy_dates_df is not None:
            df = agg.merge(canopy_dates_df, on=["plot_id", "census_year"], how="left").sort_values(["plot_id", "census_year"])
        else:
            df = agg.sort_values(["plot_id", "census_year"]).copy()
            df["survey_date_first"] = None
            df["survey_date_last"] = None

        df["plot_area_ha"] = LA_SELVA_PLOT_AREA_HA
        df["outcome_agb_Mg_ha"] = df["eagb_kg_sum"] / 1000.0 / LA_SELVA_PLOT_AREA_HA
        df["outcome_carbon_tC_ha"] = df["outcome_agb_Mg_ha"] * IPCC_DEFAULT_CARBON_FRACTION_TROPICAL
        df["outcome_co2e_tCO2e_ha"] = df["outcome_carbon_tC_ha"] * MOLECULAR_WEIGHT_RATIO_CO2_C

        # Year-over-year change only where the previous consecutive census exists.
        prev_year = df.groupby("plot_id")["census_year"].shift(1)
        prev_co2e = df.groupby("plot_id")["outcome_co2e_tCO2e_ha"].shift(1)
        consecutive = (df["census_year"] - prev_year) == 1
        df["delta_co2e_tCO2e_ha_yr"] = np.where(consecutive, df["outcome_co2e_tCO2e_ha"] - prev_co2e, np.nan)

        # Timestamp: exact survey date when available (1999+), otherwise the census year.
        df["data_generated_timestamp"] = np.where(
            df["survey_date_last"].notna(), df["survey_date_last"], df["census_year"].astype(str)
        )
        df["data_ingested_timestamp_utc"] = prov.ingested_at_utc
        df["country"] = "Costa Rica"
        df["latitude"] = 10.43
        df["longitude"] = -83.98
        df["formula_id"] = "LASELVA_BROWN_WET_FOREST_PLOT_AGB"
        df["formula_expression"] = (
            "AGB_Mg_ha = sum_stems(EAGB_kg_Brown_tropical_wet) / 1000 / 0.5 ha; "
            "carbon_tC_ha = 0.47 * AGB; co2e_tCO2e_ha = carbon_tC_ha * (44/12)"
        )
        prov.record_count = len(df)
        return df.reset_index(drop=True)
