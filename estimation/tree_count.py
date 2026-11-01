"""
Left grid, estimator E4: count the trees from space, then apply the field formula.

The right grid turns a list of measured trees into carbon with Chave et al. (2014) Eq. 4. E4 builds
the same list from the 1 m canopy height patch (extract_chm) and applies the same formula, so the
two grids differ only in where each tree's numbers come from. Inputs: the patch and the public
manifest (coordinates, dataset protocol), never a field outcome.

  1 tree tops   local maxima of the canopy height (Gaussian smoothed, sigma 1 m; the map stores whole
                metres, so without smoothing every stair step is a maximum) at least 5 m tall,
                in a window whose radius grows with height, r = 0.06 H + 0.5 m (variable window
                filter, Popescu & Wynne 2004, coefficients of the ForestTools example)
  2 crowns      every canopy pixel is flooded from the top it drains to, highest pixels first, and
                kept while it is at least 2 m tall, at least half the top's height and within 15 m
  3 diameter    D = a (H CD)^b, Jucker et al. (2017), tropical-angiosperm coefficients of the
                plot's realm (as implemented in itcSegment::dbh); trees with D < 5 cm are dropped
  4 wood        a satellite cannot see species, so every tree gets the mean wood density of the
    density     tropical species of its region in the Global Wood Density Database
  5 biomass     AGB = 0.0673 (rho D^2 H)^0.976 per tree, summed over the tops inside the plot
                footprint, divided by its area; carbon = 0.47 AGB, CO2e = 44/12 carbon

Writes data/estimation/left_tree_count.parquet (one row per plot) and left_tree_list.parquet (one
row per detected tree).

Usage: python -m estimation.tree_count
"""

from __future__ import annotations

import heapq
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadr
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
CHM = EST / "cache" / "chm"
HALF = 70  # patch half-width in metres, as written by extract_chm

H_MIN, D_MIN, CROWN_MAX_M = 5.0, 5.0, 15.0
# Jucker et al. 2017, D (cm) = a (H [m] * CD [m])^b, tropical forests, angiosperms
JUCKER = {"Indo-Malaya": (0.486, 0.802), "Afrotropic": (0.428, 0.821), "Neotropic": (0.591, 0.781)}
GWDD_REGION = {"Indo-Malaya": "South-East_Asia_(tropical)", "Afrotropic": "Africa_(tropical)",
               "Neotropic": "South_America_(tropical)", "Central America": "Central_America_(tropical)"}
# plot footprint by dataset protocol: HCSA 0.05 ha circle, Labriere and GEO-TREES 1 ha
FOOTPRINT_HA = {"HCSA_Indonesia": 0.05, "Labriere2018": 1.0, "GEO-TREES": 1.0}


def realm(lon: float, lat: float) -> str:
    if lon < -30:
        return "Neotropic"
    return "Afrotropic" if lon < 60 else "Indo-Malaya"


def default_wood_density() -> dict:
    """Mean over species of the tropical species of each region (each species weighted once)."""
    wd = next(iter(pyreadr.read_r(ROOT / "data" / "gt_raw" / "wood_density" / "wdData_BIOMASS_v2.1.11.rda").values()))
    sp = wd.groupby(["region", "family", "genus", "species"])["wd"].mean().reset_index()
    means = sp.groupby("region")["wd"].mean()
    return {k: float(means[v]) for k, v in GWDD_REGION.items()}


def tree_tops(h: np.ndarray) -> np.ndarray:
    """Variable window filter: a pixel is a top when it is the maximum of a disk of radius 0.06 H + 0.5."""
    tops = np.zeros(h.shape, bool)
    radius = np.round(0.06 * h + 0.5).astype(int)
    for r in np.unique(radius[h >= H_MIN]):
        yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
        mx = ndimage.maximum_filter(h, footprint=(xx ** 2 + yy ** 2) <= r * r, mode="constant", cval=-np.inf)
        tops |= (radius == r) & (h >= H_MIN) & (h >= mx)
    # a flat-topped crown gives several equal maxima: keep one per connected plateau
    lab, n = ndimage.label(tops)
    if n == 0:
        return np.zeros((0, 2), int)
    return np.array(ndimage.center_of_mass(tops, lab, range(1, n + 1))).round().astype(int)


def crowns(h: np.ndarray, tops: np.ndarray) -> np.ndarray:
    """Marker-based flooding from the tops on the canopy height, highest pixels first."""
    lab = np.zeros(h.shape, int)
    top_h = np.zeros(len(tops) + 1)
    heap = []
    for i, (r, c) in enumerate(tops, start=1):
        lab[r, c], top_h[i] = i, h[r, c]
        heapq.heappush(heap, (-h[r, c], r, c, i))
    ny, nx = h.shape
    while heap:
        _, r, c, i = heapq.heappop(heap)
        tr, tc = tops[i - 1]
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < ny and 0 <= cc < nx and lab[rr, cc] == 0:
                v = h[rr, cc]
                if v >= 2.0 and v >= 0.5 * top_h[i] and v <= h[r, c] + 1.0 and np.hypot(rr - tr, cc - tc) <= CROWN_MAX_M:
                    lab[rr, cc] = i
                    heapq.heappush(heap, (-v, rr, cc, i))
    return lab


def plot_trees(h: np.ndarray, reg: str, rho: float, sigma: float = 1.0) -> pd.DataFrame:
    hs = np.nan_to_num(h, nan=0.0)
    hs = ndimage.gaussian_filter(hs, sigma=sigma) if sigma > 0 else hs
    tops = tree_tops(hs)
    if len(tops) == 0:
        return pd.DataFrame(columns=["row", "col", "H_m", "crown_m2", "CD_m", "D_cm", "rho", "agb_kg"])
    lab = crowns(hs, tops)
    area = np.bincount(lab.ravel(), minlength=len(tops) + 1)[1:].astype(float)
    a, b = JUCKER[reg]
    t = pd.DataFrame({"row": tops[:, 0], "col": tops[:, 1], "H_m": h[tops[:, 0], tops[:, 1]], "crown_m2": area})
    t["H_m"] = t["H_m"].fillna(pd.Series(hs[tops[:, 0], tops[:, 1]]))
    t["CD_m"] = 2 * np.sqrt(t["crown_m2"] / np.pi)
    t["D_cm"] = a * (t["H_m"] * t["CD_m"]) ** b
    t["rho"] = rho
    t["agb_kg"] = 0.0673 * (t["rho"] * t["D_cm"] ** 2 * t["H_m"]) ** 0.976
    return t[t["D_cm"] >= D_MIN].reset_index(drop=True)


def main() -> None:
    m = pd.read_parquet(EST / "plot_manifest.parquet")
    rho = default_wood_density()
    print("default wood density (GWDD species mean):", {k: round(v, 3) for k, v in rho.items()})
    yy, xx = np.mgrid[0:2 * HALF, 0:2 * HALF]
    dist = np.hypot(yy + 0.5 - HALF, xx + 0.5 - HALF)
    rows, trees = [], []
    for p in m.itertuples(index=False):
        f = CHM / f"{p.plot_id}.npy"
        if not f.exists():
            continue
        h = np.load(f).astype("float64")
        h[h < 0] = np.nan  # no data
        reg = realm(p.lon, p.lat)
        wd_key = "Central America" if (reg == "Neotropic" and p.lat > 8) else reg
        area_ha = FOOTPRINT_HA[p.dataset]
        r_fp = np.sqrt(area_ha * 10_000 / np.pi)
        inside = dist <= r_fp
        t = plot_trees(h, reg, rho[wd_key])
        t = t[inside[t["row"], t["col"]]] if len(t) else t
        # sensitivity: no smoothing, so every stair step of the integer map can become a top
        t0 = plot_trees(h, reg, rho[wd_key], sigma=0.0)
        t0 = t0[inside[t0["row"], t0["col"]]] if len(t0) else t0
        rows.append({
            "plot_id": p.plot_id, "dataset": p.dataset, "region": p.region, "realm": reg, "footprint_ha": area_ha,
            "chm_valid_frac": float(np.isfinite(h[inside]).mean()),
            "chm_mean_m": float(np.nanmean(h[inside])) if np.isfinite(h[inside]).any() else np.nan,
            "canopy_cover_5m": float(np.nanmean(h[inside] >= 5)) if np.isfinite(h[inside]).any() else np.nan,
            "rho_default": rho[wd_key],
            "sat_trees": len(t), "sat_trees_ha": len(t) / area_ha,
            "sat_trees_d15_ha": float((t["D_cm"] >= 15).sum()) / area_ha if len(t) else 0.0,
            "sat_top_h_mean_m": float(t["H_m"].mean()) if len(t) else np.nan,
            "sat_D_mean_cm": float(t["D_cm"].mean()) if len(t) else np.nan,
            "sat_agb_Mg_ha": float(t["agb_kg"].sum()) / 1000 / area_ha if len(t) else 0.0,
            "sat_trees_ha_unsmoothed": len(t0) / area_ha,
            "sat_agb_Mg_ha_unsmoothed": float(t0["agb_kg"].sum()) / 1000 / area_ha if len(t0) else 0.0,
        })
        if len(t):
            trees.append(t.assign(plot_id=p.plot_id))
    R = pd.DataFrame(rows)
    R["sat_carbon_tC_ha"] = R["sat_agb_Mg_ha"] * 0.47
    R["sat_co2e_t_ha"] = R["sat_carbon_tC_ha"] * 44 / 12
    R.to_parquet(EST / "left_tree_count.parquet", index=False)
    pd.concat(trees, ignore_index=True).to_parquet(EST / "left_tree_list.parquet", index=False)
    pd.set_option("display.width", 200)
    print(R.groupby("dataset")[["chm_valid_frac", "sat_trees_ha", "sat_trees_d15_ha", "sat_top_h_mean_m", "sat_agb_Mg_ha"]].median().round(2))
    print(f"plots: {len(R)}")


if __name__ == "__main__":
    main()
