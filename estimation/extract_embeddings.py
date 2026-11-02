"""
Left-grid features from the AlphaEarth Foundations satellite embedding (Google, 2025).

GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL holds one 64-dimensional embedding per 10 m pixel and year
(2017 onward), learnt from Sentinel-1/2, Landsat, GEDI and other inputs. For every plot it reads the
year nearest the field date and averages the 64 bands in the plot and in a 100 m radius around it.
Plots measured before 2017 get the 2017 embedding; the paper says so.

Read from the public manifest only (coordinates, radius, date). Chunks are cached, so a rerun is
idempotent.

Usage: python -m estimation.extract_embeddings
"""

from __future__ import annotations

import json
from pathlib import Path

import ee
import pandas as pd

from estimation.extract_gee import init, nearest

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
CACHE = EST / "cache" / "embeddings"
ASSET = "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"
YEARS = list(range(2017, 2026))
CHUNK = 40
BUFFER_M = 100.0


def year_image(year: int) -> ee.Image:
    return ee.ImageCollection(ASSET).filterDate(f"{year}-01-01", f"{year + 1}-01-01").mosaic()


def chunk_rows(rows: pd.DataFrame, year: int) -> list:
    img = year_image(year)
    out = {}
    for tag, radius in [("emb_", None), ("embb_", BUFFER_M)]:
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([r.lon, r.lat]).buffer(float(radius or r.radius_m)), {"plot_id": r.plot_id})
                                   for r in rows.itertuples(index=False)])
        feats = img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=10, tileScale=4).getInfo()["features"]
        for f in feats:
            p = f["properties"]
            out.setdefault(p["plot_id"], {"plot_id": p["plot_id"], "emb_year": year})
            out[p["plot_id"]].update({tag + k: v for k, v in p.items() if k.startswith("A")})
    return list(out.values())


def main() -> None:
    init()
    CACHE.mkdir(parents=True, exist_ok=True)
    m = pd.read_parquet(EST / "plot_manifest.parquet")
    m["emb_year"] = pd.to_datetime(m["date"]).dt.year.map(lambda y: nearest(int(y), YEARS))
    rows = []
    for year, g in m.groupby("emb_year"):
        for i in range(0, len(g), CHUNK):
            part = g.iloc[i:i + CHUNK]
            path = CACHE / f"{year}_{i:04d}.json"
            if not path.exists():
                path.write_text(json.dumps(chunk_rows(part, int(year))))
            rows += json.loads(path.read_text())
            print(f"{year}: {min(i + CHUNK, len(g))}/{len(g)}", flush=True)
    E = pd.DataFrame(rows)
    E = m[["plot_id", "date"]].merge(E, on="plot_id", how="left")
    E.to_parquet(EST / "left_features_embeddings.parquet", index=False)
    print(f"{E['emb_A00'].notna().sum()} of {len(E)} plots have an embedding")


if __name__ == "__main__":
    main()
