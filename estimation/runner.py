"""
Sharded, idempotent, fault-tolerant executor for satellite feature extraction.

Each task is one (plot, measurement date, sensor) request. Tasks are grouped by a
spatial tile and tiles are placed on workers with a consistent-hash ring, so a
worker reuses the scenes it already opened for neighbouring plots. Results are
written to a content-addressed cache (SHA-256 of the canonical task), which makes
re-execution idempotent and doubles as the checkpoint: a crashed run resumes by
skipping every task whose result file already exists.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def task_key(task: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(task, sort_keys=True, default=str).encode()).hexdigest()


def tile_of(task: Dict[str, Any], deg: float = 0.5) -> str:
    return f"{int(task['lat'] // deg)}:{int(task['lon'] // deg)}"


class HashRing:
    """Consistent hashing with virtual nodes (Karger et al. 1997)."""

    def __init__(self, n_workers: int, vnodes: int = 64) -> None:
        self.ring: List[tuple[int, int]] = sorted(
            (int(hashlib.md5(f"w{w}#{v}".encode()).hexdigest(), 16), w)
            for w in range(n_workers) for v in range(vnodes)
        )
        self.keys = [h for h, _ in self.ring]

    def owner(self, key: str) -> int:
        h = int(hashlib.md5(key.encode()).hexdigest(), 16)
        return self.ring[bisect.bisect(self.keys, h) % len(self.ring)][1]


@dataclass
class RunStats:
    n_tasks: int = 0
    n_cached: int = 0
    n_done: int = 0
    n_failed: int = 0
    n_retries: int = 0
    wall_s: float = 0.0
    per_worker_tasks: Dict[int, int] = field(default_factory=dict)
    latencies_s: List[float] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        loads = list(self.per_worker_tasks.values()) or [0]
        mean_load = sum(loads) / len(loads)
        return {
            "n_tasks": self.n_tasks, "n_cached": self.n_cached, "n_done": self.n_done,
            "n_failed": self.n_failed, "n_retries": self.n_retries, "wall_s": round(self.wall_s, 2),
            "throughput_tasks_per_s": round(self.n_done / self.wall_s, 3) if self.wall_s else None,
            "load_imbalance": round(max(loads) / mean_load, 3) if mean_load else None,
        }


class ShardedRunner:
    def __init__(
        self,
        extract_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        cache_dir: Path,
        n_workers: int = 4,
        max_retries: int = 4,
        fault_rate: float = 0.0,
        seed: int = 0,
        placement: str = "lpt",
    ) -> None:
        self.extract_fn = extract_fn
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.n_workers = n_workers
        self.max_retries = max_retries
        self.fault_rate = fault_rate
        self.rng = random.Random(seed)
        self.lock = threading.Lock()
        self.placement = placement

    def _path(self, key: str) -> Path:
        return self.cache_dir / key[:2] / f"{key}.json"

    def _run_one(self, task: Dict[str, Any], stats: RunStats) -> Optional[Dict[str, Any]]:
        key = task_key(task)
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                with self.lock:
                    inject = self.rng.random() < self.fault_rate
                if inject:
                    raise ConnectionError("injected transient fault")
                out = self.extract_fn(task)
                p = self._path(key)
                p.parent.mkdir(exist_ok=True)
                tmp = p.with_suffix(".tmp")
                tmp.write_text(json.dumps({"task": task, "result": out}, default=str))
                tmp.replace(p)  # atomic rename: a crash never leaves a half-written result
                with self.lock:
                    stats.latencies_s.append(time.perf_counter() - t0)
                return out
            except Exception:
                if attempt == self.max_retries:
                    raise
                with self.lock:
                    stats.n_retries += 1
                time.sleep(min(8.0, 0.25 * 2 ** attempt) * (0.5 + self.rng.random()))
        return None

    def _worker(self, tasks: List[Dict[str, Any]], stats: RunStats) -> List[Dict[str, Any]]:
        failures = []
        for t in tasks:
            try:
                self._run_one(t, stats)
                with self.lock:
                    stats.n_done += 1
            except Exception as e:  # permanent failure after retries
                with self.lock:
                    stats.n_failed += 1
                failures.append({"task": t, "error": str(e)[:300]})
        return failures

    def place(self, tasks: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
        """Group tasks into buckets by spatial tile, split hot tiles, then assign buckets to workers.

        Tiles keep neighbouring plots on one worker (scene reuse), but field plots cluster heavily
        (one research site can hold 90 plots), so a tile holding more than the per-worker mean is split
        into sub-buckets by plot id. All sensors of one plot always stay in the same bucket.
        placement="ring" uses consistent hashing; "lpt" assigns largest buckets first to the least
        loaded worker (Graham's longest-processing-time rule).
        """
        tiles: Dict[str, List[Dict[str, Any]]] = {}
        for t in tasks:
            tiles.setdefault(tile_of(t), []).append(t)
        target = max(1, -(-len(tasks) // self.n_workers))
        buckets: Dict[str, List[Dict[str, Any]]] = {}
        for tile, ts in tiles.items():
            n_sub = -(-len(ts) // target) if self.placement != "tile" else 1
            for t in ts:
                sub = int(hashlib.md5(str(t.get("plot_id", t["lat"])).encode()).hexdigest(), 16) % n_sub
                buckets.setdefault(f"{tile}#{sub}", []).append(t)
        shards: Dict[int, List[Dict[str, Any]]] = {w: [] for w in range(self.n_workers)}
        if self.placement == "lpt":
            for key, ts in sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0])):
                w = min(shards, key=lambda i: (len(shards[i]), i))
                shards[w].extend(ts)
        else:
            ring = HashRing(self.n_workers)
            for key, ts in buckets.items():
                shards[ring.owner(key)].extend(ts)
        return shards

    def run(self, tasks: List[Dict[str, Any]]) -> tuple[RunStats, List[Dict[str, Any]]]:
        stats = RunStats(n_tasks=len(tasks))
        pending = []
        for t in tasks:
            if self._path(task_key(t)).exists():
                stats.n_cached += 1
            else:
                pending.append(t)
        shards = self.place(pending)
        stats.per_worker_tasks = {w: len(v) for w, v in shards.items()}

        t0 = time.perf_counter()
        failures: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=self.n_workers) as pool:
            futs = [pool.submit(self._worker, shard, stats) for shard in shards.values() if shard]
            for f in as_completed(futs):
                failures.extend(f.result())
        stats.wall_s = time.perf_counter() - t0
        return stats, failures

    def collect(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows = []
        for t in tasks:
            p = self._path(task_key(t))
            if p.exists():
                rows.append({**t, **json.loads(p.read_text())["result"]})
        return rows
