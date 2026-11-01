"""
Left grid: the 1 m canopy height raster around every plot, for counting trees from space.

The Meta/WRI 1 m canopy height map (Tolan et al. 2024) is read from Earth Engine as a 140 x 140 m
patch on the local UTM grid at 1 m, centred on the plot coordinates of the public manifest. The
patch is larger than the plot so that crowns cut by the plot edge can be delineated whole.

Each patch is cached as data/estimation/cache/chm/<plot_id>.npy (float32, metres, NaN = no data).

Usage: python -m estimation.extract_chm
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import ee
import numpy as np
import pandas as pd
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
CACHE = EST / "cache" / "chm"
KEY = ROOT.parent / "service-account-key.json"
HALF = 70  # metres either side of the plot centre


def utm_epsg(lon: float, lat: float) -> int:
    return (32600 if lat >= 0 else 32700) + int((lon + 180) // 6) + 1


def fetch(img: ee.Image, plot_id: str, lon: float, lat: float) -> str:
    out = CACHE / f"{plot_id}.npy"
    if out.exists():
        return "cached"
    epsg = utm_epsg(lon, lat)
    x, y = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True).transform(lon, lat)
    grid = {"dimensions": {"width": 2 * HALF, "height": 2 * HALF},
            "affineTransform": {"scaleX": 1, "shearX": 0, "translateX": x - HALF, "shearY": 0, "scaleY": -1, "translateY": y + HALF},
            "crsCode": f"EPSG:{epsg}"}
    for attempt in range(4):
        try:
            arr = ee.data.computePixels({"expression": img, "fileFormat": "NUMPY_NDARRAY", "grid": grid})
            a = np.asarray(arr["chm"], dtype="float32")
            np.save(out, a)
            return "ok"
        except Exception as e:  # quota or transient
            err = str(e)
            time.sleep(3 * (attempt + 1))
    return f"failed: {err[:120]}"


def main() -> None:
    email = json.load(open(KEY))["client_email"]
    ee.Initialize(ee.ServiceAccountCredentials(email, str(KEY)), project="nusacarbon")
    CACHE.mkdir(parents=True, exist_ok=True)
    m = pd.read_parquet(EST / "plot_manifest.parquet")
    # canopy height, metres; masked pixels (no data) become NaN through unmask(-1)
    img = (ee.ImageCollection("projects/meta-forest-monitoring-okw37/assets/CanopyHeight").mosaic()
           .rename("chm").toFloat().unmask(-1))
    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(fetch, img, r.plot_id, r.lon, r.lat): r.plot_id for r in m.itertuples(index=False)}
        for f in as_completed(futs):
            status = f.result()
            done += 1
            if status.startswith("failed"):
                print(futs[f], status, flush=True)
            if done % 50 == 0:
                print(f"{done}/{len(m)}", flush=True)
    n = len(list(CACHE.glob("*.npy")))
    print(f"patches cached: {n}/{len(m)}")


if __name__ == "__main__":
    main()
