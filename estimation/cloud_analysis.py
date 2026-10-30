"""
Analysis of the plot-level cloud climatology (cloud experiment C1).

  p_clear       share of acquisitions in which every SCL pixel in the plot window is clear
  p_half        share with at least half of the window clear (usable by per-pixel compositing)
  window        P(at least one clear acquisition within +/- W days of a random date), measured,
                against the independence model 1 - (1 - p)^m with m acquisitions in the window;
                the ratio shows how much clouds cluster in time
  gap           median and 90th-percentile days between consecutive clear acquisitions
  scene filter  how a scene-level metadata filter (eo:cloud_cover < 30, the CLOUDY_PIXEL_PERCENTAGE
                rule of many GEE pipelines) agrees with the plot condition

Usage: python -m estimation.cloud_analysis
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTD = ROOT / "data" / "estimation" / "results"
WINDOWS = (15, 30, 45, 90, 180)


def load() -> pd.DataFrame:
    df = pd.read_parquet(OUTD / "cloud_series.parquet")
    df = df[df.get("error").isna() & (df["n_px"] > 0)] if "error" in df else df[df["n_px"] > 0]
    df["date"] = pd.to_datetime(df["date"])
    # one row per location and acquisition date: reprocessed duplicates and tile overlaps collapse
    df = df.sort_values("n_px", ascending=False).drop_duplicates(["cell", "date"])
    df["group"] = np.select([df["dataset"].eq("HCSA_Indonesia"), df["dataset"].eq("SAFE_Sabah"),
                             df["region"].str.startswith("GT_AS"), df["region"].str.startswith("GT_AF") | df["region"].isin(["LAB_LOPE", "LAB_MABOUNIE", "LAB_MONDAH", "LAB_RABI"]),
                             df["region"].str.startswith("GT_AM") | df["region"].isin(["LAB_NOURAGUES", "LAB_PARACOU"])],
                            ["Indonesia (HCSA)", "Borneo, Sabah (SAFE)", "Asia, other", "Africa", "Americas"], "other")
    return df


def window_probability(g: pd.DataFrame, w: int, n_targets: int = 400, seed: int = 0):
    rng = np.random.default_rng(seed)
    d = g["date"].to_numpy("datetime64[D]").astype(int)
    clear = g["all_clear"].to_numpy(bool)
    lo, hi = d.min() + w, d.max() - w
    if hi <= lo:
        return np.nan, np.nan
    t = rng.integers(lo, hi, n_targets)
    inwin = np.abs(d[None, :] - t[:, None]) <= w
    emp = (inwin & clear[None, :]).any(1).mean()
    p = clear.mean()
    m = inwin.sum(1)
    model = (1 - (1 - p) ** m).mean()
    return float(emp), float(model)


def main() -> None:
    df = load()
    print(f"{df['cell'].nunique()} locations, {len(df)} unique acquisitions")
    loc = df.groupby(["group", "cell"]).agg(n_acq=("date", "size"), p_clear=("all_clear", "mean"),
                                            p_half=("clear_frac", lambda s: (s >= 0.5).mean())).reset_index()
    rows = []
    for (grp, cell), g in df.groupby(["group", "cell"]):
        g = g.sort_values("date")
        cd = g.loc[g["all_clear"], "date"]
        gaps = cd.diff().dt.days.dropna()
        r = {"group": grp, "cell": cell, "median_gap_days": gaps.median() if len(gaps) else np.nan,
             "p90_gap_days": gaps.quantile(0.9) if len(gaps) else np.nan, "max_gap_days": gaps.max() if len(gaps) else np.nan}
        for w in WINDOWS:
            r[f"P_win{w}_emp"], r[f"P_win{w}_indep"] = window_probability(g, w)
        rows.append(r)
    loc = loc.merge(pd.DataFrame(rows), on=["group", "cell"])
    loc.to_csv(OUTD / "cloud_by_location.csv", index=False)
    summ = loc.groupby("group").median(numeric_only=True)
    summ["n_locations"] = loc.groupby("group").size()
    summ.to_csv(OUTD / "cloud_by_group.csv")
    cols = ["n_locations", "n_acq", "p_clear", "p_half", "median_gap_days", "p90_gap_days"] + \
           [f"P_win{w}_{k}" for w in WINDOWS for k in ("emp", "indep")]
    print(summ[cols].round(3).T.to_string())

    df["month"] = df["date"].dt.month
    mon = df.groupby(["group", "month"])["all_clear"].mean().unstack(0)
    mon.to_csv(OUTD / "cloud_by_month.csv")
    print(mon.round(3).to_string())

    # scene-level metadata filter vs plot condition
    srows = []
    for grp, g in list(df.groupby("group")) + [("all", df)]:
        for thr in (10, 30, 40, 70):
            passes = g["scene_cloud_pct"] < thr
            srows.append({"group": grp, "scene_threshold_pct": thr, "share_passing": passes.mean(),
                          "plot_clear_given_pass": g.loc[passes, "all_clear"].mean(),
                          "clear_plots_rejected": 1 - g.loc[g["all_clear"], "scene_cloud_pct"].lt(thr).mean(),
                          "plot_cloudy_given_pass": 1 - g.loc[passes, "all_clear"].mean()})
    S = pd.DataFrame(srows)
    S.to_csv(OUTD / "cloud_scene_filter.csv", index=False)
    print(S.round(3).to_string(index=False))
    # within-scene correlation: how well does scene cloud % predict the plot?
    print("Spearman(scene cloud %, plot clear fraction):",
          round(df[["scene_cloud_pct", "clear_frac"]].corr("spearman").iloc[0, 1], 3))


if __name__ == "__main__":
    main()
