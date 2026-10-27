#!/usr/bin/env python3
"""
CLI Runner for the Forest Carbon MRV Ground Truth Ingestion, Verification & Benchmark Pipeline.

Usage:
    python3 run_pipeline.py [--force-refresh]
"""

from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

from src.pipeline import ForestCarbonMRVPipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape, verify, and build the multi-level Forest Carbon MRV Ground Truth dataset."
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Re-download all datasets from remote APIs/servers even if cached in data/raw/",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    pipeline = ForestCarbonMRVPipeline(base_dir=base_dir)
    manifest = pipeline.run(force_refresh=args.force_refresh)

    print("\n" + "=" * 95)
    print("FOREST CARBON MRV GROUND TRUTH PIPELINE SUMMARY")
    print("=" * 95)
    print(f"Pipeline Completed At (UTC): {manifest['pipeline_completed_at_utc']}")
    print(f"Total Provenance Sources   : {manifest['total_provenance_sources_ingested']}")
    print(f"Total Unified Benchmark Rows: {manifest['total_unified_ground_truth_records']:,}")
    print(f"Total Rows Across All Tables: {manifest['total_records_across_tables']:,}")
    print(f"SQLite Database            : {manifest['sqlite_database_path']}")
    print("-" * 95)
    print(f"{'Table Name':<50} | {'Rows':>10} | {'Cols':>6}")
    print("-" * 95)
    for tname, tinfo in manifest["tables"].items():
        print(f"{tname:<50} | {tinfo['rows']:>10,} | {tinfo['columns']:>6}")
    print("=" * 95)

    # Display benchmark summary table
    bench_csv = base_dir / "data" / "processed" / "standard_formulas_benchmark_evaluation.csv"
    if bench_csv.exists():
        bench_df = pd.read_csv(bench_csv)
        print("\nSTANDARD FORMULAS BENCHMARK EVALUATION AGAINST GROUND TRUTH:")
        cols = [
            "subset",
            "model_name",
            "n_samples",
            "unit",
            "rmse",
            "rrmse_pct",
            "mae",
            "r2_score",
            "lins_ccc",
        ]
        print(bench_df[cols].to_string(index=False))
        print("=" * 95)


if __name__ == "__main__":
    main()
