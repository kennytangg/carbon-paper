#!/usr/bin/env python3
"""
Template & Example Script: Comparing Your Custom MRV Algorithm Against Ground Truth & Standard Formulas.

Usage:
    python3 compare_custom_algorithm.py
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from src.evaluator import evaluate_custom_algorithm
from src.formulas import IPCC_DEFAULT_CARBON_FRACTION_TROPICAL, MOLECULAR_WEIGHT_RATIO_CO2_C


def example_custom_tree_model_indonesia(df: pd.DataFrame) -> np.ndarray:
    """
    CONTOH ALGORITMA KUSTOM (Level 2 - Tree/Plot Allometry Indonesia):
    Ganti fungsi ini dengan algoritma / model machine learning / persamaan baru milik Anda!
    Input yang tersedia di `df`:
      - df["input_dbh_cm"] (Diameter setinggi dada D, cm)
      - df["input_height_m"] (Tinggi pohon H, m)
      - df["input_wood_density_g_cm3"] (Kerapatan kayu WD, g/cm3)
      - df["input_chave_E_index"] (Indeks bioklimatik E)
    Output yang dikembalikan:
      - Estimasi karbon ekuivalen per pohon dalam kg CO2e
    """
    d = df["input_dbh_cm"].to_numpy(dtype=float)
    h = df["input_height_m"].to_numpy(dtype=float)
    wd = df["input_wood_density_g_cm3"].to_numpy(dtype=float)
    env_e = df["input_chave_E_index"].to_numpy(dtype=float)

    # Contoh: Hybrid Ensemble Allometric Algorithm (menggabungkan Chave Eq.4 bila H ada,
    # dan koreksi non-linear berbasis kerapatan kayu & indeks E untuk hutan dipterocarpaceae Indonesia)
    agb_eq4 = 0.0673 * ((wd * (d ** 2) * h) ** 0.976)
    agb_eq7_idn = np.exp(-1.785 - 0.950 * env_e + 0.985 * np.log(wd) + 2.665 * np.log(d) - 0.0295 * (np.log(d) ** 2))
    agb_custom_kg = np.where(np.isfinite(h) & (h >= 1.3), agb_eq4, agb_eq7_idn)

    # Konversi ke kg CO2e menggunakan IPCC CF = 0.47 dan 44/12
    return agb_custom_kg * IPCC_DEFAULT_CARBON_FRACTION_TROPICAL * MOLECULAR_WEIGHT_RATIO_CO2_C


def example_custom_remote_sensing_lidar_model(df: pd.DataFrame) -> np.ndarray:
    """
    CONTOH ALGORITMA KUSTOM (Level 3 - Remote Sensing LiDAR + Plot):
    Ganti fungsi ini dengan model Remote Sensing MRV milik Anda!
    Input yang tersedia di `df`:
      - df["input_lidar_tch_mean_m"] (Top-of-Canopy Height LiDAR, m)
      - df["input_lidar_h50_median_m"] (Median Canopy Height LiDAR, m)
      - df["input_lidar_canopy_cover_20m"] (Tutupan kanopi pada 20m)
      - df["input_lidar_height_stdv_m"] (Heterogenitas vertikal kanopi, m)
      - df["input_basal_area_m2_ha"] (Basal area, m2/ha)
      - df["input_wood_density_g_cm3"] (Wood density, g/cm3)
    Output:
      - Estimasi stok karbon dalam tCO2e/ha
    """
    tch = df["input_lidar_tch_mean_m"].to_numpy(dtype=float)
    ba = df["input_basal_area_m2_ha"].to_numpy(dtype=float)
    wd = df["input_wood_density_g_cm3"].to_numpy(dtype=float)
    cc20 = df["input_lidar_canopy_cover_20m"].to_numpy(dtype=float)

    # Contoh model struktural kanopi yang memperhitungkan tutupan kanopi 20m (cc20):
    agb_mg_ha = 5.85 * (tch ** 0.34) * (ba ** 0.95) * (wd ** 0.78) * ((0.85 + 0.15 * cc20) ** 0.25)
    return agb_mg_ha * IPCC_DEFAULT_CARBON_FRACTION_TROPICAL * MOLECULAR_WEIGHT_RATIO_CO2_C


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    proc_dir = base_dir / "data" / "processed"

    print("=" * 95)
    print("KOMPARASI ALGORITMA KUSTOM VS. GROUND TRUTH & FORMULA STANDAR")
    print("=" * 95)

    # 1. Evaluasi pada Data Pohon Hutan Indonesia (Kalimantan, Sumatra, Jawa Barat, Maluku)
    tree_df = pd.read_csv(proc_dir / "level2_tree_allometry_groundtruth.csv")
    idn_df = tree_df[tree_df["is_indonesia_site"] == True].copy()

    comp_idn = evaluate_custom_algorithm(
        df=idn_df,
        custom_predict_fn=example_custom_tree_model_indonesia,
        ground_truth_col="groundtruth_observed_co2e_kg",
        standard_formula_col="formula_ketterings2001_idn_co2e_kg",
        custom_model_name="Algoritma_Kustom_Kita (Hybrid Allometric IDN)",
        standard_model_name="Standar_SNI_Ketterings_2001 (0.11 * WD * D^2.62)",
        target_unit="kg CO2e / tree",
        subset_name="Hutan Indonesia (Kalimantan, Sumatra, Jawa, Maluku - 537 pohon)",
    )
    print("\n[1] Hasil Komparasi Level 2 (Pohon Hutan Indonesia):")
    print(comp_idn[["model_name", "n_samples", "rmse", "rrmse_pct", "mae", "r2_score", "lins_ccc"]].to_string(index=False))

    # 2. Evaluasi pada Data Remote Sensing LiDAR + Plot (TropiSAR & AfriSAR - 1,093 plot)
    lidar_df = pd.read_csv(proc_dir / "level3_remote_sensing_lidar_sar_plots.csv")
    comp_lidar = evaluate_custom_algorithm(
        df=lidar_df,
        custom_predict_fn=example_custom_remote_sensing_lidar_model,
        ground_truth_col="outcome_co2e_loc_tCO2e_ha",
        standard_formula_col="formula_lidar_predicted_co2e_tCO2e_ha",
        custom_model_name="Algoritma_Kustom_Kita (LiDAR TCH + CanopyCover + BA + WD)",
        standard_model_name="Standar_Asner_Labriere_LiDAR_Formula",
        target_unit="tCO2e / ha",
        subset_name="Plot Kalibrasi TropiSAR & AfriSAR (1,093 plot)",
    )
    print("\n[2] Hasil Komparasi Level 3 (Remote Sensing LiDAR + Plot Lapangan):")
    print(comp_lidar[["model_name", "n_samples", "rmse", "rrmse_pct", "mae", "r2_score", "lins_ccc"]].to_string(index=False))
    print("=" * 95)


if __name__ == "__main__":
    main()
