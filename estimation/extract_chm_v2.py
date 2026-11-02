"""
Left grid: the Meta/WRI canopy height map v2 (CHMv2, Brandt et al. 2026) around every plot.

CHMv2 is not on Earth Engine. It is read anonymously from the open AWS bucket (CC BY 4.0) as
cloud-optimised GeoTIFF tiles, one per zoom-10 quadkey, ~1.2 m in Web Mercator, whole metres
(uint8). Each patch is warped (nearest) onto the same 140 x 140 m local UTM grid at 1 m as
extract_chm, so the tree count and the plot features compare one map with the other pixel for pixel.

Writes data/estimation/cache/chm_v2/<plot_id>.npy (float32, metres) and
left_features_chm_v2.parquet: mean, percentiles and cover above 5 and 15 m in the plot footprint
and within 50 m around it (prefix chm2_), as extract_gee does for v1 (prefix meta_).

Usage: python -m estimation.extract_chm_v2
"""

from __future__ import annotations

import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from rasterio.windows import from_bounds

from estimation.extract_chm import HALF, utm_epsg

os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
CACHE = EST / "cache" / "chm_v2"
URL = "/vsicurl/https://dataforgood-fb-data.s3.amazonaws.com/forests/v2/global/dinov3_global_chm_v2_ml3/chm/{}.tif"
ZOOM = 10


def quadkey(lon: float, lat: float, z: int = ZOOM) -> str:
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    s = math.sin(math.radians(lat))
    y = int((0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n)
    return "".join(str((1 if x & (1 << (i - 1)) else 0) + (2 if y & (1 << (i - 1)) else 0)) for i in range(z, 0, -1))


def fetch(plot_id: str, lon: float, lat: float) -> str:
    out = CACHE / f"{plot_id}.npy"
    if out.exists():
        return "cached"
    epsg = utm_epsg(lon, lat)
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    to_ll = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    x, y = to_utm.transform(lon, lat)
    dst = np.full((2 * HALF, 2 * HALF), np.nan, dtype="float32")
    dst_tf = from_origin(x - HALF, y + HALF, 1, 1)
    corners = [to_ll.transform(x + dx, y + dy) for dx in (-HALF - 5, HALF + 5) for dy in (-HALF - 5, HALF + 5)]
    for qk in sorted({quadkey(cx, cy) for cx, cy in corners}):
        try:
            with rasterio.open(URL.format(qk)) as ds:
                mx, my = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True).transform(*zip(*corners))
                win = from_bounds(min(mx), min(my), max(mx), max(my), ds.transform).round_offsets().round_lengths()
                src = ds.read(1, window=win, boundless=True, fill_value=255).astype("float32")
                src[src == 255] = np.nan
                part = np.full_like(dst, np.nan)
                reproject(src, part, src_transform=ds.window_transform(win), src_crs=ds.crs, src_nodata=np.nan,
                          dst_transform=dst_tf, dst_crs=f"EPSG:{epsg}", dst_nodata=np.nan, resampling=Resampling.nearest)
                dst = np.where(np.isnan(dst), part, dst)
        except rasterio.errors.RasterioIOError as e:
            return f"failed {qk}: {str(e)[:100]}"
    np.save(out, dst)
    return "ok"


def patch_features(h: np.ndarray, radius_m: float, prefix: str) -> dict:
    yy, xx = np.mgrid[0:2 * HALF, 0:2 * HALF]
    dist = np.hypot(yy + 0.5 - HALF, xx + 0.5 - HALF)
    out = {}
    for tag, mask in [("plot_", dist <= radius_m), ("b50_", dist <= radius_m + 50)]:
        v = h[mask]
        v = v[np.isfinite(v)]
        if len(v) == 0:
            continue
        out.update({f"{prefix}{tag}mean": v.mean(), f"{prefix}{tag}p90": np.percentile(v, 90),
                    f"{prefix}{tag}c5": (v > 5).mean(), f"{prefix}{tag}c15": (v > 15).mean()})
        if tag == "plot_":
            out.update({f"{prefix}{tag}p50": np.percentile(v, 50), f"{prefix}{tag}p98": np.percentile(v, 98),
                        f"{prefix}{tag}stdDev": v.std()})
    return out


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    m = pd.read_parquet(EST / "plot_manifest.parquet")
    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(fetch, r.plot_id, r.lon, r.lat): r.plot_id for r in m.itertuples(index=False)}
        for f in as_completed(futs):
            status = f.result()
            done += 1
            if status.startswith("failed"):
                print(futs[f], status, flush=True)
            if done % 100 == 0:
                print(f"{done}/{len(m)}", flush=True)
    rows = []
    for r in m.itertuples(index=False):
        f = CACHE / f"{r.plot_id}.npy"
        if f.exists():
            rows.append({"plot_id": r.plot_id, "date": r.date, **patch_features(np.load(f), float(r.radius_m), "chm2_")})
    F = pd.DataFrame(rows)
    F.to_parquet(EST / "left_features_chm_v2.parquet", index=False)
    print(f"patches: {len(F)}/{len(m)}; plot mean height median {F['chm2_plot_mean'].median():.1f} m")


if __name__ == "__main__":
    main()
