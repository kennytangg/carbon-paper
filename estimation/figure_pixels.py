"""
Figure "from pixels to carbon": what the left grid sees around one HCSA plot.

Three panels on the same 140 m window: Sentinel-2 true colour at 10 m, its NDVI, and the 1 m canopy
height map with the tree tops E4 finds. The Sentinel-2 chip is read once from Planetary Computer
(the clearest scene within +/-180 days of the plot date, every pixel clear in the scene
classification) and cached; the canopy height comes from the extract_chm cache.

Usage: python -m estimation.figure_pixels
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from estimation.backends.pc import S2_SCL_CLEAR, _as_date, _read_window, _search
from estimation.figures import INK, INK2, ONE_COL, ORANGE, plt, save
from estimation.tree_count import CHM, EST, HALF, default_wood_density, plot_trees, realm

PLOT = "HCSA_Central_Kalimantan_KT30"
CACHE = EST / "cache" / "fig" / f"{PLOT}_s2.npz"
BANDS = ["B04", "B03", "B02", "B08"]


def s2_chip(lon: float, lat: float, target) -> dict:
    if CACHE.exists():
        z = np.load(CACHE, allow_pickle=True)
        return {k: z[k] for k in z.files}
    items = _search("sentinel-2-l2a", lon, lat, target - timedelta(days=365), target + timedelta(days=365),
                    query={"eo:cloud_cover": {"lt": 40}})
    best, best_ndvi = None, -1.0
    for it in sorted(items, key=lambda i: i.properties.get("eo:cloud_cover", 100))[:25]:
        scl = _read_window(it.assets["SCL"].href, lon, lat, HALF)  # 20 m
        if scl is None or not np.isin(scl, list(S2_SCL_CLEAR)).all():
            continue
        # processing baseline 04.00+ adds +1000 to L2A values, as in the backend
        offset = 1000.0 if it.properties.get("s2:processing_baseline", "00.00") >= "04.00" else 0.0
        out = {b: (_read_window(it.assets[b].href, lon, lat, HALF) - offset) / 10000.0 for b in BANDS}
        # the scene classification passes thin haze as vegetation; keep the greenest fully clear scene
        ndvi = np.nanmedian((out["B08"] - out["B04"]) / (out["B08"] + out["B04"]))
        if ndvi > best_ndvi:
            best, best_ndvi = out, ndvi
            best["date"] = np.array(str(it.datetime.date()))
    if best is None:
        raise RuntimeError("no fully clear scene")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez(CACHE, **best)
    return best


def main() -> None:
    m = pd.read_parquet(EST / "plot_manifest.parquet").set_index("plot_id").loc[PLOT]
    gt = pd.read_parquet(EST / "right_grid_sealed.parquet").set_index("plot_id").loc[PLOT]
    s2 = s2_chip(m.lon, m.lat, _as_date(m.date))
    h = np.load(CHM / f"{PLOT}.npy")
    reg = realm(m.lon, m.lat)
    trees = plot_trees(h, reg, default_wood_density()[reg])

    r_plot = np.sqrt(0.05 * 1e4 / np.pi)  # 0.05 ha footprint
    rgb = np.dstack([s2[b] for b in ("B04", "B03", "B02")])
    rgb = np.clip(rgb / np.percentile(rgb, 99) * 0.9, 0, 1) ** 0.8
    ndvi = (s2["B08"] - s2["B04"]) / (s2["B08"] + s2["B04"])
    e10 = s2["B04"].shape[0] * 10 / 2  # the 10 m chip is centred on the pixel holding the plot
    ext10, ext1 = [-e10, e10, -e10, e10], [-HALF, HALF, -HALF, HALF]  # metres from the plot centre

    fig, axs = plt.subplots(1, 3, figsize=(ONE_COL, 1.18), gridspec_kw={"wspace": 0.05})
    axs[0].imshow(rgb, extent=ext10, interpolation="nearest")
    im1 = axs[1].imshow(ndvi, extent=ext10, interpolation="nearest", cmap="Greens", vmin=0.5, vmax=1.0)
    im2 = axs[2].imshow(h, extent=ext1, interpolation="nearest", cmap="viridis", vmin=0, vmax=40)
    ty, tx = HALF - trees["row"].to_numpy() - 0.5, trees["col"].to_numpy() - HALF + 0.5
    axs[2].scatter(tx, ty, s=3.5, c="white", edgecolors=INK, linewidths=0.3, zorder=3)
    titles = ["(a) Sentinel-2, 10 m", "(b) NDVI", "(c) Height, 1 m"]
    for ax, t in zip(axs, titles):
        ax.add_patch(plt.Circle((0, 0), r_plot, fill=False, ec=ORANGE, lw=1.1, zorder=4))
        ax.set_xlim(-HALF, HALF), ax.set_ylim(-HALF, HALF)
        ax.set_title(t, fontsize=6.5, color=INK, pad=2)
        ax.set_xticks([]), ax.set_yticks([]), ax.grid(False)
        for s in ax.spines.values():
            s.set_visible(False)
    # scales are stated on the panels instead of colour bars, to keep the figure one band high
    axs[0].text(-HALF + 3, -HALF + 4, "140 m", color="white", fontsize=5.5)
    axs[1].text(-HALF + 3, -HALF + 4, "0.5 to 1", color="white", fontsize=5.5)
    axs[2].text(-HALF + 3, -HALF + 4, "0 to 40 m", color="white", fontsize=5.5)
    save(fig, "fig_pixels")
    inside = (np.hypot(tx, ty) <= r_plot).sum()
    print(f"{PLOT}: scene {s2['date']}, NDVI plot median {np.nanmedian(ndvi):.2f}, trees in window {len(trees)}, "
          f"inside plot {inside}, field {gt.agb_Mg_ha:.0f} Mg/ha from {int(gt.n_trees)} stems")


if __name__ == "__main__":
    main()
