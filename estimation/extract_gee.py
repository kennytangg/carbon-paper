"""
Left-grid features from Google Earth Engine, batch-extracted for every plot in a manifest.

Everything here is read from the plot's coordinates, radius, and date only (the public manifest).

  canopy height  Meta/WRI 1 m canopy height (Tolan et al. 2024), the closest public stand-in for a
                 drone lidar canopy model: mean, percentiles, cover above 5 and 15 m, in the plot
                 and in a 50 m buffer. ETH 10 m canopy height 2020 (Lang et al. 2023).
  GEDI           L4A footprint biomass and L2A relative height (quality-filtered, 2019-04 to 2023-03)
                 within 500 m and 1 km; L4B 1 km gridded biomass.
  ESA CCI        CCI Biomass v6 AGB, year nearest the field date.
  PALSAR         JAXA ALOS/ALOS-2 yearly mosaic HH/HV (dB), year nearest the field date (2007-2024).
  Hansen         GFC v1.13: tree cover in 2000 and forest-loss share up to the field year, 100 m buffer.

Plots are processed in chunks with reduceRegions; each chunk is cached so a rerun is idempotent.

Usage: python -m estimation.extract_gee [--seq]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import ee
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
CACHE = EST / "cache" / "gee"
KEY = ROOT.parent / "service-account-key.json"
CHUNK = 40

CCI_YEARS = [2007, 2010, 2015, 2016, 2017, 2018, 2019, 2020, 2021]
PALSAR_YEARS = [2007, 2008, 2009, 2010, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]


def init() -> None:
    email = json.load(open(KEY))["client_email"]
    ee.Initialize(ee.ServiceAccountCredentials(email, str(KEY)), project="nusacarbon")


def nearest(year: int, years: list) -> int:
    return min(years, key=lambda y: (abs(y - year), -y))


def stats(prefix: str) -> ee.Reducer:
    return (ee.Reducer.mean().combine(ee.Reducer.percentile([50, 90, 98]), sharedInputs=True)
            .combine(ee.Reducer.stdDev(), sharedInputs=True))


def static_images() -> dict:
    meta = ee.ImageCollection("projects/meta-forest-monitoring-okw37/assets/CanopyHeight").mosaic().rename("chm")
    meta = meta.addBands(meta.gt(5).rename("c5")).addBands(meta.gt(15).rename("c15"))
    eth = ee.Image("users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1").rename("eth")

    def l4a(img):
        ok = img.select("l4_quality_flag").eq(1).And(img.select("degrade_flag").eq(0))
        return img.select(["agbd"]).updateMask(ok)

    def l2a(img):
        ok = img.select("quality_flag").eq(1).And(img.select("degrade_flag").eq(0))
        return img.select(["rh98", "rh50"]).updateMask(ok)
    gedi = (ee.ImageCollection("LARSE/GEDI/GEDI04_A_002_MONTHLY").filterDate("2019-04-01", "2023-04-01").map(l4a).mean()
            .addBands(ee.ImageCollection("LARSE/GEDI/GEDI02_A_002_MONTHLY").filterDate("2019-04-01", "2023-04-01").map(l2a).mean()))
    l4b = ee.Image("LARSE/GEDI/GEDI04_B_002").select("MU").rename("l4b")
    return {"meta": meta, "eth": eth, "gedi": gedi, "l4b": l4b}


def reduce(fc: ee.FeatureCollection, img: ee.Image, reducer: ee.Reducer, scale: float) -> list:
    out = img.reduceRegions(collection=fc, reducer=reducer, scale=scale, tileScale=4)
    return [f["properties"] for f in out.getInfo()["features"]]


def chunk_features(rows: pd.DataFrame, imgs: dict) -> pd.DataFrame:
    def fc(buf: str):
        return ee.FeatureCollection([ee.Feature(ee.Geometry.Point([r.lon, r.lat]).buffer(float(getattr(r, buf))), {"key": r.key})
                                     for r in rows.itertuples(index=False)])
    rows = rows.assign(b50=rows["radius_m"].clip(lower=50), b100=100.0, b500=500.0, b1k=1000.0)
    res = {k: {} for k in rows["key"]}

    def put(lst, prefix):
        for p in lst:
            for k, v in p.items():
                if k != "key":
                    res[p["key"]][f"{prefix}{k}"] = v
    plot_fc, b50_fc = fc("radius_m"), fc("b50")
    red = stats("")
    put(reduce(plot_fc, imgs["meta"].select("chm"), red, 1), "meta_plot_")
    put(reduce(plot_fc, imgs["meta"].select(["c5", "c15"]), ee.Reducer.mean(), 1), "meta_plot_")
    put(reduce(b50_fc, imgs["meta"].select("chm"), ee.Reducer.mean().combine(ee.Reducer.percentile([90]), sharedInputs=True), 1), "meta_b50_")
    put(reduce(b50_fc, imgs["meta"].select(["c5", "c15"]), ee.Reducer.mean(), 1), "meta_b50_")
    put(reduce(plot_fc, imgs["eth"], ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True), 10), "eth_plot_")
    put(reduce(b50_fc, imgs["eth"], ee.Reducer.mean(), 10), "eth_b50_")
    cnt = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)
    put(reduce(fc("b500"), imgs["gedi"], cnt, 25), "gedi500_")
    put(reduce(fc("b1k"), imgs["gedi"], cnt, 25), "gedi1k_")
    put(reduce(fc("b100"), imgs["l4b"], ee.Reducer.mean(), 1000), "l4b_")
    # year-dependent layers, grouped by the nearest available year
    for y, g in rows.groupby(rows["year"].map(lambda v: nearest(v, CCI_YEARS))):
        img = ee.ImageCollection("projects/sat-io/open-datasets/ESA/ESA_CCI_AGB").filter(ee.Filter.calendarRange(y, y, "year")).first().select([0]).rename("cci_agb")
        sub = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([r.lon, r.lat]).buffer(100), {"key": r.key}) for r in g.itertuples(index=False)])
        put(reduce(sub, img, ee.Reducer.mean(), 100), "cci_")
        for k in g["key"]:
            res[k]["cci_year"] = y
    for y, g in rows.groupby(rows["year"].map(lambda v: nearest(v, PALSAR_YEARS))):
        pal = ee.ImageCollection("JAXA/ALOS/PALSAR/YEARLY/SAR_EPOCH").filter(ee.Filter.calendarRange(y, y, "year")).first().select(["HH", "HV"])
        pal = pal.pow(2).log10().multiply(10).subtract(83).rename(["pal_hh", "pal_hv"])
        sub = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([r.lon, r.lat]).buffer(max(r.radius_m, 25)), {"key": r.key}) for r in g.itertuples(index=False)])
        put(reduce(sub, pal, ee.Reducer.mean(), 25), "")
        for k in g["key"]:
            res[k]["pal_year"] = y
    gfc = ee.Image("UMD/hansen/global_forest_change_2025_v1_13")
    for y, g in rows.groupby(rows["year"].clip(upper=2025)):
        lossb = gfc.select("lossyear").unmask(0)
        lossb = lossb.gt(0).And(lossb.lt(y - 2000 + 1)).rename("loss_before")
        img = gfc.select("treecover2000").rename("tc2000").addBands(lossb)
        sub = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([r.lon, r.lat]).buffer(100), {"key": r.key}) for r in g.itertuples(index=False)])
        put(reduce(sub, img, ee.Reducer.mean(), 30), "hansen_")
    return pd.DataFrame([{"key": k, **v} for k, v in res.items()])


def run(manifest: pd.DataFrame, tag: str) -> pd.DataFrame:
    init()
    imgs = static_images()
    CACHE.mkdir(parents=True, exist_ok=True)
    parts = []
    for i in range(0, len(manifest), CHUNK):
        rows = manifest.iloc[i:i + CHUNK]
        f = CACHE / f"{tag}_{i:05d}.parquet"
        if f.exists():
            parts.append(pd.read_parquet(f))
            continue
        for attempt in range(4):
            try:
                df = chunk_features(rows, imgs)
                df.to_parquet(f.with_suffix(".tmp"), index=False)
                f.with_suffix(".tmp").replace(f)
                parts.append(df)
                break
            except Exception as e:
                print(f"chunk {i}: attempt {attempt + 1} failed: {str(e)[:150]}", flush=True)
                time.sleep(5 * (attempt + 1))
        print(f"{tag}: {min(i + CHUNK, len(manifest))}/{len(manifest)}", flush=True)
    return pd.concat(parts, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seq", action="store_true")
    args = ap.parse_args()
    if not args.seq:
        m = pd.read_parquet(EST / "plot_manifest.parquet")
        m = m.assign(key=m["plot_id"] + "|" + m["date"], year=pd.to_datetime(m["date"]).dt.year)
        out = run(m[["key", "lat", "lon", "radius_m", "year"]], "stock")
        out[["plot_id", "date"]] = out["key"].str.split("|", expand=True)
        out.drop(columns="key").to_parquet(EST / "left_features_gee.parquet", index=False)
    else:
        m = pd.read_parquet(EST / "seq_plot_manifest.parquet")
        rows = pd.concat([m.assign(date=m["date_t0"]), m.assign(date=m["date_t1"])])
        rows = rows.assign(key=rows["plot_id"] + "|" + rows["date"], year=pd.to_datetime(rows["date"]).dt.year)
        out = run(rows[["key", "lat", "lon", "radius_m", "year"]].drop_duplicates("key"), "seq")
        out[["plot_id", "date"]] = out["key"].str.split("|", expand=True)
        out.drop(columns="key").to_parquet(EST / "left_features_gee_seq.parquet", index=False)
    print("done", out.shape)


if __name__ == "__main__":
    main()
