"""
Plot-level cloud climatology (cloud experiment C1).

For a set of plot locations, read the Sentinel-2 L2A scene classification (SCL) at the plot for
every acquisition in a multi-year period and record, per acquisition:
  scene_cloud_pct   the scene-level metadata cloud percentage (what scene filters such as
                    CLOUDY_PIXEL_PERCENTAGE < 30 use)
  clear_frac        fraction of SCL pixels in the plot window that are clear
  all_clear         every pixel clear (the rule used by our extractor)

From this we estimate the per-acquisition clear probability p, its seasonality, the temporal
autocorrelation of cloudiness, the probability that a +/- W day window contains at least one clear
look (empirical vs the independence model 1 - (1-p)^m), and how well the scene metadata predicts
the plot condition.

Usage: python -m estimation.cloud_climatology --start 2021-01-01 --end 2023-12-31
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from estimation.backends.pc import S2_SCL_CLEAR, _read_window, _search

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
CACHE = EST / "cache" / "cloud"
OUTD = EST / "results"
RADIUS_M = 30.0  # 5 x 5 SCL pixels at 20 m, i.e. about a 0.1 ha plot plus geolocation margin


def locations() -> pd.DataFrame:
    """One location per ~0.1 degree cell, so clustered plots are not counted many times."""
    stock = pd.read_parquet(EST / "plot_manifest.parquet")[["plot_id", "dataset", "region", "lat", "lon"]]
    seq = pd.read_parquet(EST / "seq_plot_manifest.parquet")[["plot_id", "dataset", "region", "lat", "lon"]]
    df = pd.concat([stock, seq], ignore_index=True)
    df["cell"] = (df["lat"] / 0.1).round().astype(int).astype(str) + "_" + (df["lon"] / 0.1).round().astype(int).astype(str)
    return df.groupby("cell").first().reset_index()


def read_one(loc: dict, item) -> dict:
    scl = _read_window(item.assets["SCL"].href, loc["lon"], loc["lat"], RADIUS_M)
    valid = scl[np.isfinite(scl) & (scl > 0)] if scl is not None else np.array([])
    clear = np.isin(valid, list(S2_SCL_CLEAR))
    return {"cell": loc["cell"], "date": item.datetime.date().isoformat(), "tile": item.properties.get("s2:mgrs_tile"),
            "scene_cloud_pct": item.properties.get("eo:cloud_cover"), "n_px": int(valid.size),
            "clear_frac": float(clear.mean()) if valid.size else np.nan,
            "all_clear": bool(valid.size and clear.all()),
            "cloud_frac": float(np.isin(valid, [8, 9, 10]).mean()) if valid.size else np.nan,  # cloud med/high, cirrus
            "shadow_frac": float((valid == 3).mean()) if valid.size else np.nan}


def series(loc: dict, start: date, end: date, pool: ThreadPoolExecutor) -> list:
    f = CACHE / f"{loc['cell']}_{start}_{end}.json"
    if f.exists():
        return json.loads(f.read_text())
    items = _search("sentinel-2-l2a", loc["lon"], loc["lat"], start, end, limit=2000)
    rows = []
    for fut in as_completed([pool.submit(read_one, loc, it) for it in items]):
        try:
            rows.append(fut.result())
        except Exception as e:  # unreadable scene: recorded, not fatal
            rows.append({"cell": loc["cell"], "error": str(e)[:120]})
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows))
    tmp.replace(f)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2021-01-01")
    ap.add_argument("--end", default="2023-12-31")
    ap.add_argument("--threads", type=int, default=24)
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    locs = locations()
    print(f"{len(locs)} locations")
    allrows = []
    with ThreadPoolExecutor(args.threads) as pool:
        for i, loc in enumerate(locs.to_dict("records")):
            rows = series(loc, start, end, pool)
            allrows += [dict(r, dataset=loc["dataset"], region=loc["region"], lat=loc["lat"], lon=loc["lon"]) for r in rows]
            print(f"[{i + 1}/{len(locs)}] {loc['region']}: {len(rows)} acquisitions", flush=True)
    df = pd.DataFrame(allrows)
    df.to_parquet(OUTD / "cloud_series.parquet", index=False)
    print(df.groupby("dataset")[["all_clear", "clear_frac"]].mean().round(3))


if __name__ == "__main__":
    main()
