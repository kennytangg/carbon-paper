"""
Satellite feature extraction from Microsoft Planetary Computer (anonymous STAC + COG reads).

Given a plot centre, a field measurement date and a matching window of +/- W days,
returns cloud-masked, time-matched features. Nothing here can see field outcomes:
the only inputs are coordinates, a date, and a plot radius.
"""

from __future__ import annotations

import math
import os
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional

import numpy as np
import planetary_computer
import pystac_client
import rasterio
from rasterio.warp import transform as warp_transform
from rasterio.windows import Window

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("GDAL_HTTP_MULTIRANGE", "YES")
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
os.environ.setdefault("VSI_CACHE", "TRUE")

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
S2_BANDS = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"]
S2_SCL_CLEAR = {4, 5, 6, 7, 11}  # vegetation, bare, water, unclassified, snow -> clouds/shadows dropped
LANDSAT_BANDS = {"blue": "blue", "green": "green", "red": "red", "nir08": "nir", "swir16": "swir1", "swir22": "swir2"}


@lru_cache(maxsize=1)
def _catalog() -> pystac_client.Client:
    return pystac_client.Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)


def _as_date(d: Any) -> date:
    return d if isinstance(d, date) and not isinstance(d, datetime) else datetime.fromisoformat(str(d)[:10]).date()


def _search(collection: str, lon: float, lat: float, start: date, end: date, query: Optional[dict] = None, limit: int = 200):
    s = _catalog().search(
        collections=[collection],
        intersects={"type": "Point", "coordinates": [lon, lat]},
        datetime=f"{start.isoformat()}/{end.isoformat()}",
        query=query,
        max_items=limit,
    )
    return list(s.items())


def _read_window(href: str, lon: float, lat: float, radius_m: float) -> Optional[np.ndarray]:
    """Read the pixels of an asset whose centres fall inside a square of +/- radius_m around the point."""
    with rasterio.open(href) as ds:
        xs, ys = warp_transform("EPSG:4326", ds.crs, [lon], [lat])
        row, col = ds.index(xs[0], ys[0])
        res = abs(ds.transform.a) if ds.crs.is_projected else abs(ds.transform.a) * 111_320 * math.cos(math.radians(lat))
        half = max(0, int(round(radius_m / res)))
        win = Window(col - half, row - half, 2 * half + 1, 2 * half + 1)
        arr = ds.read(1, window=win, boundless=True, fill_value=ds.nodata if ds.nodata is not None else 0).astype("float64")
        if ds.nodata is not None:
            arr[arr == ds.nodata] = np.nan
        return arr


def _offset_days(item, target: date) -> int:
    return abs((item.datetime.date() - target).days)


def sentinel2_features(lon: float, lat: float, target: date, window_days: int, radius_m: float, max_scenes: int = 10, enough: int = 3) -> Dict[str, Any]:
    items = _search("sentinel-2-l2a", lon, lat, target - timedelta(days=window_days), target + timedelta(days=window_days),
                    query={"eo:cloud_cover": {"lt": 70}})
    items = sorted(items, key=lambda it: (it.properties.get("eo:cloud_cover", 100), _offset_days(it, target)))[:max_scenes]
    stacks: Dict[str, List[float]] = {b: [] for b in S2_BANDS}
    offsets: List[int] = []
    for it in items:
        if len(offsets) >= enough:
            break
        scl = _read_window(it.assets["SCL"].href, lon, lat, radius_m)
        # The 20 m scene classification and the 10 m bands are on different grids, so a scene is
        # used only when every SCL pixel in the window is clear; bands are then plain window means.
        if scl is None or not np.isin(scl, list(S2_SCL_CLEAR)).all():
            continue
        # Processing baseline 04.00+ adds a +1000 offset to L2A DN values.
        offset = 1000.0 if it.properties.get("s2:processing_baseline", "00.00") >= "04.00" else 0.0
        vals = {}
        for b in S2_BANDS:
            arr = _read_window(it.assets[b].href, lon, lat, radius_m)
            vals[b] = (float(np.nanmean(arr)) - offset) / 10000.0 if arr is not None else np.nan
        if all(np.isfinite(list(vals.values()))):
            for b in S2_BANDS:
                stacks[b].append(vals[b])
            offsets.append(_offset_days(it, target))
    out: Dict[str, Any] = {"s2_n_clear": len(offsets), "s2_min_offset_days": min(offsets) if offsets else None}
    if not offsets:
        return out
    m = {b: float(np.median(v)) for b, v in stacks.items()}
    out.update({f"s2_{b}": v for b, v in m.items()})
    b2, b3, b4, b5, b6, b7, b8, b8a, b11, b12 = (m[b] for b in S2_BANDS)
    eps = 1e-9
    out.update({
        "s2_ndvi": (b8 - b4) / (b8 + b4 + eps),
        "s2_evi": 2.5 * (b8 - b4) / (b8 + 6 * b4 - 7.5 * b2 + 1 + eps),
        "s2_ndre": (b8 - b5) / (b8 + b5 + eps),
        "s2_ndmi": (b8 - b11) / (b8 + b11 + eps),
        "s2_nbr": (b8 - b12) / (b8 + b12 + eps),
        "s2_ireci": (b7 - b4) / (b5 / (b6 + eps) + eps),
        "s2_savi": 1.5 * (b8 - b4) / (b8 + b4 + 0.5),
    })
    return out


def sentinel1_features(lon: float, lat: float, target: date, window_days: int, radius_m: float, max_scenes: int = 6) -> Dict[str, Any]:
    items = _search("sentinel-1-rtc", lon, lat, target - timedelta(days=window_days), target + timedelta(days=window_days))
    items = sorted(items, key=lambda it: _offset_days(it, target))[:max_scenes]
    vv, vh, offs = [], [], []
    for it in items:
        if "vv" not in it.assets or "vh" not in it.assets:
            continue
        a = _read_window(it.assets["vv"].href, lon, lat, radius_m)
        b = _read_window(it.assets["vh"].href, lon, lat, radius_m)
        if a is None or b is None:
            continue
        a, b = np.nanmean(a), np.nanmean(b)
        if a > 0 and b > 0:
            vv.append(10 * math.log10(a)); vh.append(10 * math.log10(b)); offs.append(_offset_days(it, target))
    if not vv:
        return {"s1_n": 0}
    vvm, vhm = float(np.median(vv)), float(np.median(vh))
    return {"s1_n": len(vv), "s1_min_offset_days": min(offs), "s1_vv_db": vvm, "s1_vh_db": vhm,
            "s1_vh_minus_vv": vhm - vvm, "s1_rvi": 4 * 10 ** (vhm / 10) / (10 ** (vvm / 10) + 10 ** (vhm / 10))}


def palsar_features(lon: float, lat: float, target: date, radius_m: float) -> Dict[str, Any]:
    year = min(max(target.year, 2015), 2021)
    items = _search("alos-palsar-mosaic", lon, lat, date(year, 1, 1), date(year, 12, 31))
    if not items:
        return {"palsar_year": None}
    it = items[0]
    out: Dict[str, Any] = {"palsar_year": year, "palsar_year_gap": abs(year - target.year)}
    for pol in ("HH", "HV"):
        if pol in it.assets:
            dn = _read_window(it.assets[pol].href, lon, lat, radius_m)
            dn = dn[np.isfinite(dn) & (dn > 0)] if dn is not None else np.array([])
            # JAXA mosaic DN -> gamma0 (dB) = 10*log10(DN^2) - 83.0
            out[f"palsar_{pol.lower()}_db"] = float(np.mean(10 * np.log10(dn.astype("float64") ** 2) - 83.0)) if dn.size else None
    if out.get("palsar_hh_db") is not None and out.get("palsar_hv_db") is not None:
        out["palsar_hv_minus_hh"] = out["palsar_hv_db"] - out["palsar_hh_db"]
    return out


def landsat_features(lon: float, lat: float, target: date, window_days: int, radius_m: float, max_scenes: int = 8) -> Dict[str, Any]:
    items = _search("landsat-c2-l2", lon, lat, target - timedelta(days=window_days), target + timedelta(days=window_days),
                    query={"eo:cloud_cover": {"lt": 70}, "platform": {"in": ["landsat-5", "landsat-7", "landsat-8", "landsat-9"]}})
    items = sorted(items, key=lambda it: (it.properties.get("eo:cloud_cover", 100), _offset_days(it, target)))[:max_scenes]
    stacks: Dict[str, List[float]] = {v: [] for v in LANDSAT_BANDS.values()}
    offs: List[int] = []
    for it in items:
        if len(offs) >= 3:
            break
        qa = _read_window(it.assets["qa_pixel"].href, lon, lat, radius_m)
        if qa is None:
            continue
        qa = np.nan_to_num(qa).astype("int64")
        clear = ((qa >> 6) & 1) == 1  # QA_PIXEL bit 6 = clear
        if clear.mean() < 0.5:
            continue
        vals = {}
        for asset, name in LANDSAT_BANDS.items():
            if asset not in it.assets:
                break
            arr = _read_window(it.assets[asset].href, lon, lat, radius_m)
            vals[name] = float(np.nanmean(np.where(clear, arr, np.nan))) * 2.75e-05 - 0.2
        if len(vals) == len(LANDSAT_BANDS) and all(np.isfinite(list(vals.values()))):
            for k, v in vals.items():
                stacks[k].append(v)
            offs.append(_offset_days(it, target))
    if not offs:
        return {"ls_n_clear": 0}
    m = {k: float(np.median(v)) for k, v in stacks.items()}
    eps = 1e-9
    return {"ls_n_clear": len(offs), "ls_min_offset_days": min(offs), **{f"ls_{k}": v for k, v in m.items()},
            "ls_ndvi": (m["nir"] - m["red"]) / (m["nir"] + m["red"] + eps),
            "ls_ndmi": (m["nir"] - m["swir1"]) / (m["nir"] + m["swir1"] + eps),
            "ls_nbr": (m["nir"] - m["swir2"]) / (m["nir"] + m["swir2"] + eps)}


def static_features(lon: float, lat: float, target: date, radius_m: float) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    dem = _search("cop-dem-glo-30", lon, lat, date(2021, 1, 1), date(2021, 12, 31))
    if dem:
        arr = _read_window(dem[0].assets["data"].href, lon, lat, max(radius_m, 90))
        if arr is not None and np.isfinite(arr).any():
            out["dem_elev_m"] = float(np.nanmean(arr))
            gy, gx = np.gradient(arr, 30.0)
            out["dem_slope_deg"] = float(np.degrees(np.arctan(np.nanmean(np.hypot(gx, gy)))))
    # Off-the-shelf satellite biomass products (zero-shot baselines; never trained on our plots)
    yr = min(max(target.year, 2003), 2019)
    chl = _search("chloris-biomass", lon, lat, date(yr, 1, 1), date(yr, 12, 31))
    if chl:
        v = _read_window(chl[0].assets["biomass"].href, lon, lat, radius_m)
        # Chloris stores total AGB (tonnes) per ~4.6 km pixel; convert to Mg/ha using pixel area.
        if v is not None and np.isfinite(v).any():
            with rasterio.open(chl[0].assets["biomass"].href) as ds:
                px_area_ha = abs(ds.transform.a * ds.transform.e) / 10_000 if ds.crs.is_projected else None
            out["chloris_agb_t_px"] = float(np.nanmean(v))
            out["chloris_agb_Mg_ha"] = float(np.nanmean(v)) / px_area_ha if px_area_ha else None
            out["chloris_year"] = yr
    hgb = _search("hgb", lon, lat, date(2010, 1, 1), date(2010, 12, 31))
    if hgb:
        v = _read_window(hgb[0].assets["aboveground"].href, lon, lat, radius_m)
        if v is not None and np.isfinite(v).any():
            out["hgb2010_raw"] = float(np.nanmean(v))  # Spawn et al. 2020 AGB carbon density, 2010 epoch; scale checked in analysis
    return out


def extract(task: Dict[str, Any]) -> Dict[str, Any]:
    lon, lat = float(task["lon"]), float(task["lat"])
    target = _as_date(task["date"])
    w, r = int(task.get("window_days", 60)), float(task.get("radius_m", 20))
    sensor = task["sensor"]
    if sensor == "s2":
        return sentinel2_features(lon, lat, target, w, r)
    if sensor == "s1":
        return sentinel1_features(lon, lat, target, w, r)
    if sensor == "palsar":
        return palsar_features(lon, lat, target, r)
    if sensor == "landsat":
        return landsat_features(lon, lat, target, w, r)
    if sensor == "static":
        return static_features(lon, lat, target, r)
    raise ValueError(f"unknown sensor {sensor}")
