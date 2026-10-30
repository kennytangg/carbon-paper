"""
Left grid, step 1: time-matched satellite feature extraction for every plot in the PUBLIC manifest.

This module never opens right_grid_sealed.parquet. Usage:
    python -m estimation.extract_left --workers 24 --window 90
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from estimation.backends.pc import extract
from estimation.runner import ShardedRunner

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
SENSORS_ALWAYS = ["landsat", "s1", "palsar", "static"]


def build_tasks(manifest: pd.DataFrame, window_days: int) -> list[dict]:
    tasks = []
    for r in manifest.itertuples():
        sensors = SENSORS_ALWAYS + (["s2"] if r.date >= "2017-01-01" else [])
        for s in sensors:
            tasks.append({"plot_id": r.plot_id, "lat": round(float(r.lat), 6), "lon": round(float(r.lon), 6),
                          "date": r.date, "radius_m": float(r.radius_m), "window_days": window_days, "sensor": s})
    return tasks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--window", type=int, default=90)
    ap.add_argument("--fault-rate", type=float, default=0.0)
    ap.add_argument("--datasets", default="", help="comma list; default all")
    ap.add_argument("--sensors", default="", help="comma list; default all")
    ap.add_argument("--seq", action="store_true", help="extract SAFE plots at both census dates")
    args = ap.parse_args()

    if args.seq:
        # Sequestration: every SAFE plot is observed at its first and its last census date
        sm = pd.read_parquet(EST / "seq_plot_manifest.parquet")
        manifest = pd.concat([sm.assign(date=sm["date_t0"]), sm.assign(date=sm["date_t1"])], ignore_index=True)
    else:
        manifest = pd.read_parquet(EST / "plot_manifest.parquet")
    if args.datasets:
        manifest = manifest[manifest["dataset"].isin(args.datasets.split(","))]
    tasks = build_tasks(manifest, args.window)
    if args.sensors:
        tasks = [t for t in tasks if t["sensor"] in args.sensors.split(",")]
    tag = f"win{args.window}" + (f"_{args.datasets.replace(',', '+')}" if args.datasets else "") + ("_seq" if args.seq else "")
    runner = ShardedRunner(extract, EST / "cache" / "pc", n_workers=args.workers, fault_rate=args.fault_rate)
    stats, failures = runner.run(tasks)
    print(json.dumps(stats.summary(), indent=1))
    (EST / "runs").mkdir(exist_ok=True)
    (EST / "runs" / f"extract_w{args.workers}_{tag}.json").write_text(
        json.dumps({"summary": stats.summary(), "failures": failures[:50], "n_failures": len(failures)}, indent=1, default=str))

    rows = runner.collect(tasks)
    long = pd.DataFrame(rows)
    keys = ["plot_id", "date", "window_days"]
    wide = long.drop(columns=["sensor", "lat", "lon", "radius_m"]).groupby(keys, as_index=False).first()
    wide.to_parquet(EST / f"left_features_{tag}.parquet", index=False)
    print(f"features: {wide.shape} -> left_features_{tag}.parquet")


if __name__ == "__main__":
    main()
