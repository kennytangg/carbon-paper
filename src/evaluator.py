"""
Algorithm Benchmarking & Comparison Framework for Forest Carbon MRV Research.

Provides:
1. Standard MRV validation metrics (RMSE, rRMSE%, MAE, MAPE%, Bias, Relative Bias%, R^2,
   Pearson r, and Lin's Concordance Correlation Coefficient CCC).
2. Automated baseline evaluations across all 3 MRV levels:
   - Level 1: Registry Project MRV Accounting Formula vs. Reported/Issued Credits (Verra/CAR/ACR)
   - Level 2: Standard Allometric Equations (Chave 2014 Eq.4, Chave 2014 Eq.7, Ketterings 2001
     Indonesia SNI 7724, Brown 1997 UNFCCC) vs. Destructive Harvest Ground Truth (Global & Indonesia)
   - Level 3: Airborne LiDAR & Spaceborne Satellite Biomass Models vs. Field Plot / NFI Ground Truth
3. Plug-and-play `evaluate_custom_model()` interface so researchers can benchmark their own
   custom algorithm/model directly against the ground-truth dataset and standard formulas.
"""

from __future__ import annotations

from typing import Callable, Dict, Any, List, Optional
import numpy as np
import pandas as pd


def compute_mrv_metrics(
    y_true: np.ndarray | pd.Series,
    y_pred: np.ndarray | pd.Series,
    model_name: str = "Custom_Model",
    target_unit: str = "tCO2e",
    subset_name: str = "All",
) -> Dict[str, Any]:
    """
    Compute standard scientific validation metrics comparing predicted carbon/biomass (`y_pred`)
    against ground-truth reference values (`y_true`).
    """
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(yt) & np.isfinite(yp) & (yt > 0)
    yt = yt[mask]
    yp = yp[mask]

    n = int(len(yt))
    if n == 0:
        return {
            "model_name": model_name,
            "subset": subset_name,
            "n_samples": 0,
            "unit": target_unit,
        }

    residuals = yp - yt
    mean_true = float(np.mean(yt))
    mean_pred = float(np.mean(yp))
    rmse = float(np.sqrt(np.mean(residuals ** 2)))
    rrmse_pct = float((rmse / mean_true) * 100.0) if mean_true != 0 else np.nan
    mae = float(np.mean(np.abs(residuals)))
    mape_pct = float(np.mean(np.abs(residuals / yt)) * 100.0)
    bias = float(np.mean(residuals))
    rel_bias_pct = float((bias / mean_true) * 100.0) if mean_true != 0 else np.nan

    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((yt - mean_true) ** 2))
    r2 = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else np.nan

    if n > 2 and np.std(yt) > 0 and np.std(yp) > 0:
        pearson_r = float(np.corrcoef(yt, yp)[0, 1])
        var_t = float(np.var(yt))
        var_p = float(np.var(yp))
        cov_tp = float(np.mean((yt - mean_true) * (yp - mean_pred)))
        lins_ccc = float((2.0 * cov_tp) / (var_t + var_p + ((mean_true - mean_pred) ** 2)))
    else:
        pearson_r = np.nan
        lins_ccc = np.nan

    return {
        "model_name": model_name,
        "subset": subset_name,
        "n_samples": n,
        "unit": target_unit,
        "mean_ground_truth": round(mean_true, 4),
        "mean_predicted": round(mean_pred, 4),
        "rmse": round(rmse, 4),
        "rrmse_pct": round(rrmse_pct, 2),
        "mae": round(mae, 4),
        "mape_pct": round(mape_pct, 2),
        "bias": round(bias, 4),
        "relative_bias_pct": round(rel_bias_pct, 2),
        "r2_score": round(r2, 4),
        "pearson_r": round(pearson_r, 4),
        "lins_ccc": round(lins_ccc, 4),
    }


def run_standard_formula_benchmarks(
    tree_df: pd.DataFrame,
    ifm_df: pd.DataFrame,
    lidar_df: pd.DataFrame,
    nfi_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Run comprehensive benchmark comparisons of established standard formulas against
    ground-truth outcomes across all levels (Tree Allometry Global & Indonesia,
    Remote Sensing LiDAR Plot Calibration, Registry IFM Pool Accounting, and NFI vs Satellite).
    """
    results: List[Dict[str, Any]] = []

    # 1. Level 2: Tree Allometry (Global Pantropical Destructive Harvest)
    if not tree_df.empty:
        for col, name in [
            ("formula_chave2014_eq4_co2e_kg", "Chave et al. (2014) Eq. 4 (D, H, WD)"),
            ("formula_chave2014_eq7_co2e_kg", "Chave et al. (2014) Eq. 7 (D, WD, Climate E)"),
            ("formula_ketterings2001_idn_co2e_kg", "Ketterings et al. (2001) Indonesia SNI 7724 (D, WD)"),
            ("formula_brown1997_unfccc_co2e_kg", "Brown (1997) UNFCCC AR-ACM0003 (D only)"),
        ]:
            results.append(
                compute_mrv_metrics(
                    y_true=tree_df["groundtruth_observed_co2e_kg"],
                    y_pred=tree_df[col],
                    model_name=name,
                    target_unit="kg CO2e / tree",
                    subset_name="Level 2: Pantropical Destructive Harvest (All Sites)",
                )
            )

        # Indonesian sites subset (Kalimantan, Sumatra, West Java, Moluccas)
        idn_df = tree_df[tree_df["is_indonesia_site"] == True]
        if not idn_df.empty:
            for col, name in [
                ("formula_chave2014_eq4_co2e_kg", "Chave et al. (2014) Eq. 4 (D, H, WD)"),
                ("formula_chave2014_eq7_co2e_kg", "Chave et al. (2014) Eq. 7 (D, WD, Climate E)"),
                ("formula_ketterings2001_idn_co2e_kg", "Ketterings et al. (2001) Indonesia SNI 7724 (D, WD)"),
                ("formula_brown1997_unfccc_co2e_kg", "Brown (1997) UNFCCC AR-ACM0003 (D only)"),
            ]:
                results.append(
                    compute_mrv_metrics(
                        y_true=idn_df["groundtruth_observed_co2e_kg"],
                        y_pred=idn_df[col],
                        model_name=name,
                        target_unit="kg CO2e / tree",
                        subset_name="Level 2: Indonesia Forest Sites (Kalimantan, Sumatra, Java, Moluccas)",
                    )
                )

    # 2. Level 3: Remote Sensing LiDAR + Plot Biomass (TropiSAR & AfriSAR)
    if not lidar_df.empty:
        results.append(
            compute_mrv_metrics(
                y_true=lidar_df["outcome_co2e_loc_tCO2e_ha"],
                y_pred=lidar_df["formula_lidar_predicted_co2e_tCO2e_ha"],
                model_name="Labrière et al. (2018) Airborne LiDAR TCH + BA + WD Model",
                target_unit="tCO2e / ha",
                subset_name="Level 3: TropiSAR & AfriSAR Calibration Plots (1,093 plots)",
            )
        )
        results.append(
            compute_mrv_metrics(
                y_true=lidar_df["outcome_co2e_loc_tCO2e_ha"],
                y_pred=lidar_df["outcome_co2e_fph_tCO2e_ha"],
                model_name="Chave (2014) Eq. 4 + Feldpausch Regional H-D Curve",
                target_unit="tCO2e / ha",
                subset_name="Level 3: TropiSAR & AfriSAR Calibration Plots (1,093 plots)",
            )
        )
        results.append(
            compute_mrv_metrics(
                y_true=lidar_df["outcome_co2e_loc_tCO2e_ha"],
                y_pred=lidar_df["outcome_co2e_chv_tCO2e_ha"],
                model_name="Chave (2014) Eq. 7 Bioclimatic E (No Height)",
                target_unit="tCO2e / ha",
                subset_name="Level 3: TropiSAR & AfriSAR Calibration Plots (1,093 plots)",
            )
        )

    # 3. Level 1: Registry Project MRV Pool Accounting (Verra VCSOPR / CAR / ACR)
    if not ifm_df.empty:
        results.append(
            compute_mrv_metrics(
                y_true=ifm_df["outcome_registry_reported_tCO2e"],
                y_pred=ifm_df["outcome_formula_recalculated_tCO2e"],
                model_name="CARB / Verra / CAR / ACR IFM Pool Accounting Formula",
                target_unit="tCO2e / project",
                subset_name="Level 1: Registry IFM Projects (Verra VCSOPR, CAR, ACR)",
            )
        )

    # 4. Level 3: National Forest Inventory (NFI) vs. Spaceborne ESA CCI Biomass Map
    if not nfi_df.empty:
        results.append(
            compute_mrv_metrics(
                y_true=nfi_df["outcome_nfi_groundtruth_co2e_tCO2e_ha"],
                y_pred=nfi_df["outcome_esa_cci_satellite_co2e_tCO2e_ha"],
                model_name="ESA CCI Spaceborne Global Biomass Map vs. FAO FRA NFI Ground Truth",
                target_unit="tCO2e / ha",
                subset_name="Level 3: National Forest Inventories (Tropical & Global Countries)",
            )
        )

    return pd.DataFrame(results)


def evaluate_custom_algorithm(
    df: pd.DataFrame,
    custom_predict_fn: Callable[[pd.DataFrame], np.ndarray | pd.Series],
    ground_truth_col: str,
    standard_formula_col: str,
    custom_model_name: str = "Our_Proposed_MRV_Algorithm",
    standard_model_name: str = "Standard_Registry_Formula",
    target_unit: str = "tCO2e/ha",
    subset_name: str = "Evaluation_Dataset",
) -> pd.DataFrame:
    """
    Plug-and-play helper for comparing the user's custom algorithm against both the
    ground-truth column and the existing standard formula column on any ingested DataFrame.
    """
    custom_preds = custom_predict_fn(df)
    m_std = compute_mrv_metrics(
        y_true=df[ground_truth_col],
        y_pred=df[standard_formula_col],
        model_name=standard_model_name,
        target_unit=target_unit,
        subset_name=subset_name,
    )
    m_custom = compute_mrv_metrics(
        y_true=df[ground_truth_col],
        y_pred=custom_preds,
        model_name=custom_model_name,
        target_unit=target_unit,
        subset_name=subset_name,
    )
    return pd.DataFrame([m_std, m_custom])
