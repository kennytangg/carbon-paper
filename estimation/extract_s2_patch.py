"""
One Sentinel-2 image patch around a plot, for the paper's pixel-to-carbon figure.

Reads the clearest Sentinel-2 L2A scene within +/- W days of the plot's field date from the
Planetary Computer, keeps a square of +/- HALF_M metres around the plot centre at 10 m, and saves
blue, green, red and near-infrared reflectance with the scene id and date. Clearest means the most
patch pixels labelled vegetation, bare or water by the scene classification (SCL). Like the left
grid, it reads only the plot's coordinates and date.

Usage: python -m estimation.extract_s2_patch [--plot HCSA_Riau_RU12]
"""

from __future__ import annotations

import argparse
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from estimation.backends.pc import S2_SCL_CLEAR, _as_date, _read_window, _search

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
RES = EST / "results"
HALF_M = 70.0
WINDOW_DAYS = 365
BANDS = ("B02", "B03", "B04", "B08")


def clear_share(item, lon: float, lat: float) -> float:
    scl = _read_window(item.assets["SCL"].href, lon, lat, HALF_M)
    return float(np.isin(scl, list(S2_SCL_CLEAR)).mean()) if scl is not None else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plot", default="HCSA_Riau_RU12")
    a = ap.parse_args()
    m = pd.read_parquet(EST / "plot_manifest.parquet").set_index("plot_id").loc[a.plot]
    t = _as_date(m["date"])
    items = _search("sentinel-2-l2a", m["lon"], m["lat"], t - timedelta(days=WINDOW_DAYS), t + timedelta(days=WINDOW_DAYS),
                    query={"eo:cloud_cover": {"lt": 40}})
    if not items:
        raise SystemExit(f"no Sentinel-2 scene within {WINDOW_DAYS} days of {t} for {a.plot}")
    items = sorted(items, key=lambda it: it.properties.get("eo:cloud_cover", 100))[:15]
    best = max(items, key=lambda it: clear_share(it, m["lon"], m["lat"]))
    share = clear_share(best, m["lon"], m["lat"])
    if share < 0.99:
        raise SystemExit(f"clearest scene {best.id} is only {share:.0%} clear over the patch")
    # L2A reflectance: DN / 10000, minus the 0.1 offset of processing baseline 04.00 (scenes from 2022 on)
    offset = 0.1 if best.datetime.date().year >= 2022 else 0.0
    bands = {b: _read_window(best.assets[b].href, m["lon"], m["lat"], HALF_M) / 10_000 - offset for b in BANDS}
    out = RES / f"s2_patch_{a.plot}.npz"
    np.savez_compressed(out, **bands, scene=best.id, date=str(best.datetime.date()), pixel_m=10.0, half_m=HALF_M)
    print(f"{a.plot}: {best.id} ({best.datetime.date()}), {share:.0%} clear, {bands['B04'].shape} pixels -> {out.name}")


if __name__ == "__main__":
    main()
