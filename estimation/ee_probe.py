"""Probe which Earth Engine assets the NusaCarbon service account can read."""
import json, sys, ee

key = sys.argv[1]
email = json.load(open(key))["client_email"]
ee.Initialize(ee.ServiceAccountCredentials(email, key), project=sys.argv[2])
pt = ee.Geometry.Point([113.9, -1.6])  # Central Kalimantan

def probe(name, fn):
    try:
        print(f"OK   {name}: {fn()}")
    except Exception as e:
        print(f"FAIL {name}: {str(e)[:160]}")

probe("S2_SR_HARMONIZED", lambda: ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(pt).filterDate("2023-01-01","2023-03-01").size().getInfo())
probe("S1_GRD", lambda: ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(pt).filterDate("2023-01-01","2023-03-01").size().getInfo())
probe("GEDI L4A monthly", lambda: ee.ImageCollection("LARSE/GEDI/GEDI04_A_002_MONTHLY").filterBounds(pt).size().getInfo())
probe("GEDI L2A monthly", lambda: ee.ImageCollection("LARSE/GEDI/GEDI02_A_002_MONTHLY").filterBounds(pt).size().getInfo())
probe("GEDI L4B gridded", lambda: ee.Image("LARSE/GEDI/GEDI04_B_002").bandNames().getInfo())
probe("ETH canopy height 2020", lambda: ee.Image("users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1").reduceRegion(ee.Reducer.first(), pt, 10).getInfo())
probe("Meta canopy height", lambda: ee.ImageCollection("projects/meta-forest-monitoring-okw37/assets/CanopyHeight").size().getInfo())
probe("ALOS PALSAR yearly", lambda: ee.ImageCollection("JAXA/ALOS/PALSAR/YEARLY/SAR_EPOCH").aggregate_array("system:index").getInfo())
probe("ESA CCI biomass (sat-io)", lambda: ee.ImageCollection("projects/sat-io/open-datasets/ESA/ESA_CCI_AGB").aggregate_array("system:index").getInfo())
probe("Hansen GFC", lambda: ee.Image("UMD/hansen/global_forest_change_2023_v1_11").bandNames().getInfo())
probe("Landsat 8 C2 L2", lambda: ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").filterBounds(pt).filterDate("2020-01-01","2020-12-31").size().getInfo())
probe("Copernicus DEM", lambda: ee.ImageCollection("COPERNICUS/DEM/GLO30").size().getInfo())
