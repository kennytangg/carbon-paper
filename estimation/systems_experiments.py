"""
Distributed-systems experiments on the left-grid extraction runner (RQ4).

  scaling   strong scaling: the same task set on 1..32 workers, each run on an empty cache
  faults    injected transient faults at rate p; outputs must be bit-identical to the fault-free run
  resume    crash after half the tasks, restart, and count how much work the checkpoint saved

Usage: python -m estimation.systems_experiments --n-tasks 48
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
from pathlib import Path

import pandas as pd

from estimation.backends.pc import extract
from estimation.extract_left import build_tasks
from estimation.runner import ShardedRunner, task_key

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
SCR = EST / "cache" / "sysexp"


def digest(runner: ShardedRunner, tasks) -> dict:
    """Per-task SHA-256 of each finished result; tasks that failed permanently are absent."""
    out = {}
    for t in tasks:
        p = runner._path(task_key(t))
        if p.exists():
            out[task_key(t)] = hashlib.sha256(json.dumps(json.loads(p.read_text())["result"], sort_keys=True).encode()).hexdigest()
    return out


def compare(d: dict, ref: dict) -> dict:
    """Bit-identity on the tasks both runs finished, plus which tasks only one of them finished."""
    common = d.keys() & ref.keys()
    return {"n_common": len(common), "n_mismatch": sum(d[k] != ref[k] for k in common),
            "only_here": len(d.keys() - ref.keys()), "only_in_ref": len(ref.keys() - d.keys()),
            "identical": all(d[k] == ref[k] for k in common)}


def fresh(name: str, workers: int, fault: float = 0.0, seed: int = 0) -> ShardedRunner:
    d = SCR / name
    shutil.rmtree(d, ignore_errors=True)
    return ShardedRunner(extract, d, n_workers=workers, fault_rate=fault, seed=seed)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-tasks", type=int, default=48)
    ap.add_argument("--workers", default="1,2,4,8,16,32")
    args = ap.parse_args()
    manifest = pd.read_parquet(EST / "plot_manifest.parquet")
    all_tasks = [t for t in build_tasks(manifest, 90) if t["sensor"] in ("landsat", "palsar", "static", "s1")]
    tasks = random.Random(7).sample(all_tasks, args.n_tasks)
    out = {"n_tasks": len(tasks), "scaling": [], "faults": [], "resume": {}}

    base_digest = None
    for w in [int(x) for x in args.workers.split(",")]:
        r = fresh(f"scale_w{w}", w)
        stats, fails = r.run(tasks)
        d = digest(r, tasks)
        base_digest = base_digest or d
        out["scaling"].append({"workers": w, **stats.summary(), "vs_w1": compare(d, base_digest)})
        print(out["scaling"][-1])

    w = 8
    for p in (0.1, 0.2, 0.3):
        r = fresh(f"fault_p{p}", w, fault=p, seed=11)
        stats, fails = r.run(tasks)
        out["faults"].append({"workers": w, "fault_rate": p, **stats.summary(), "vs_fault_free": compare(digest(r, tasks), base_digest),
                              "failed_errors": [f["error"][:80] for f in fails]})
        print(out["faults"][-1])

    r = fresh("resume", w)
    s1, _ = r.run(tasks[: len(tasks) // 2])  # simulated crash: only the first half finished
    s2, _ = r.run(tasks)                      # restart over the full task list
    out["resume"] = {"first_run_done": s1.n_done, "restart_cached_skipped": s2.n_cached, "restart_done": s2.n_done,
                     "wall_first_s": round(s1.wall_s, 2), "wall_restart_s": round(s2.wall_s, 2),
                     "vs_fault_free": compare(digest(r, tasks), base_digest)}
    print(out["resume"])
    (EST / "results").mkdir(parents=True, exist_ok=True)
    (EST / "results" / "systems_experiments.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
