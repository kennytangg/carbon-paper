"""
Google Earth Engine backend: GEDI spaceborne-lidar biomass and the E1 estimator's training data.

E1 is the strictest satellite-only estimator: its labels are GEDI L4A footprint biomass (a space
lidar product), its predictors are satellite composites, and no field plot enters training.

Auth: service account JSON (same key NusaCarbon uses). The account needs
roles/serviceusage.serviceUsageConsumer and Earth Engine access on the project.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Dict

import ee

L4A = "LARSE/GEDI/GEDI04_A_002_MONTHLY"
L2A = "LARSE/GEDI/GEDI02_A_002_MONTHLY"
GEDI_START = date(2019, 4, 18)


def init(key_path: str, project: str) -> None:
    email = json.load(open(key_path))["client_email"]
    ee.Initialize(ee.ServiceAccountCredentials(email, key_path), project=project)


def _d(x: Any) -> date:
    return x if isinstance(x, date) else datetime.fromisoformat(str(x)[:10]).date()


def gedi_l4a(start: date, end: date) -> ee.Image:
    def qa(img):
        ok = img.select("l4_quality_flag").eq(1).And(img.select("degrade_flag").eq(0))
        return img.select(["agbd", "agbd_se"]).updateMask(ok)
    return ee.ImageCollection(L4A).filterDate(str(start), str(end)).map(qa).mean()


def gedi_l2a(start: date, end: date) -> ee.Image:
    def qa(img):
        ok = img.select("quality_flag").eq(1).And(img.select("degrade_flag").eq(0))
        return img.select(["rh98", "rh50"]).updateMask(ok)
    return ee.ImageCollection(L2A).filterDate(str(start), str(end)).map(qa).mean()


def predictors(start: date, end: date) -> ee.Image:
    """Satellite predictor stack used by E1, identical for training pixels and for plots."""
    def s2mask(img):
        scl = img.select("SCL")
        clear = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(7))
        return img.updateMask(clear).divide(10000)
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterDate(str(start), str(end))
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 70)).map(s2mask)
          .select(["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]).median())
    idx = ee.Image.cat([
        s2.normalizedDifference(["B8", "B4"]).rename("ndvi"),
        s2.normalizedDifference(["B8", "B5"]).rename("ndre"),
        s2.normalizedDifference(["B8", "B11"]).rename("ndmi"),
        s2.normalizedDifference(["B8", "B12"]).rename("nbr"),
    ])
    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filterDate(str(start), str(end))
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
          .select(["VV", "VH"]).median())
    yr = min(max(start.year, 2015), 2023)
    pal = (ee.ImageCollection("JAXA/ALOS/PALSAR/YEARLY/SAR_EPOCH").filterDate(f"{yr}-01-01", f"{yr + 1}-01-01")
           .first().select(["HH", "HV"]))
    pal_db = pal.pow(2).log10().multiply(10).subtract(83).rename(["palsar_hh", "palsar_hv"])
    dem = ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1").select("DEM").mosaic().rename("elev")
    slope = ee.Terrain.slope(dem).rename("slope")
    return ee.Image.cat([s2.rename([f"s2_{b}" for b in ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]]),
                         idx.rename([f"s2_{n}" for n in ["ndvi", "ndre", "ndmi", "nbr"]]),
                         s1.rename(["s1_vv", "s1_vh"]), pal_db, dem, slope]).float()


def plot_features(task: Dict[str, Any]) -> Dict[str, Any]:
    """Direct GEDI reads near the plot plus the E1 predictor stack at the plot (one task = one plot)."""
    t = _d(task["date"])
    w = int(task.get("window_days", 365))
    start, end = max(t - timedelta(days=w), GEDI_START), t + timedelta(days=w)
    pt = ee.Geometry.Point([float(task["lon"]), float(task["lat"])])
    out: Dict[str, Any] = {}
    if end > GEDI_START:
        near = pt.buffer(float(task.get("gedi_radius_m", 500)))
        g = gedi_l4a(start, end).addBands(gedi_l2a(start, end))
        r = g.reduceRegion(ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True), near, 25, maxPixels=1e8).getInfo()
        out.update({"gedi_agbd_mean": r.get("agbd_mean"), "gedi_n": r.get("agbd_count"),
                    "gedi_rh98_mean": r.get("rh98_mean"), "gedi_rh50_mean": r.get("rh50_mean")})
    yr0 = max(t.year, 2019)
    pstart, pend = date(yr0, 1, 1), date(yr0, 12, 31)
    area = pt.buffer(float(task.get("radius_m", 20)))
    r = predictors(pstart, pend).reduceRegion(ee.Reducer.mean(), area, 10, maxPixels=1e8).getInfo()
    out.update({f"e1_{k}": v for k, v in r.items()})
    return out


def sample_gedi_training(task: Dict[str, Any]) -> Dict[str, Any]:
    """E1 training data: GEDI L4A footprints (labels) with the predictor stack, sampled in a buffer
    around a region centroid. One task = one region. Returns rows as a list of dicts."""
    t = _d(task["date"])
    yr0 = max(t.year, 2019)
    start, end = date(yr0, 1, 1), date(yr0, 12, 31)
    zone = ee.Geometry.Point([float(task["lon"]), float(task["lat"])]).buffer(float(task.get("buffer_m", 30_000)))
    label = gedi_l4a(start, end).select("agbd")
    stack = predictors(start, end).addBands(label)
    fc = stack.updateMask(label.mask()).sample(region=zone, scale=25, numPixels=int(task.get("n", 4000)),
                                               seed=int(task.get("seed", 0)), dropNulls=True, tileScale=4)
    rows = [f["properties"] for f in fc.limit(int(task.get("n", 4000))).getInfo()["features"]]
    return {"rows": rows, "n": len(rows)}
