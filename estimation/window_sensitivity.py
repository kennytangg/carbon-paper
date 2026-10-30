"""
Temporal-window sensitivity (RQ1) on the Indonesian HCSA plots.

For W in {30, 90, 180, 365} days the optical and C-band features of the HCSA plots are re-extracted
with only scenes inside [t - W, t + W]; every other plot keeps its W = 90 features. E2 is then rerun
leave-one-region-out, and the HCSA plots are scored. Also reports how many plots had at least one
clear optical scene, which is what a tighter window costs.

Usage: python -m estimation.window_sensitivity
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from estimation.models import feature_columns, leave_one_region_out, score

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "estimation"
OUTD = EST / "results"
WINDOWS = (30, 90, 180, 365)
SWAPPED = ("s2_", "ls_", "s1_")


def main() -> None:
    manifest = pd.read_parquet(EST / "plot_manifest.parquet")
    base = manifest.merge(pd.read_parquet(EST / "left_features_win90.parquet"), on=["plot_id", "date"], how="left")
    gt = pd.read_parquet(EST / "right_grid_sealed.parquet")[["plot_id", "agb_Mg_ha"]]
    feats = feature_columns(base)
    rows = []
    for w in WINDOWS:
        df = base.copy()
        if w != 90:
            alt = pd.read_parquet(EST / f"left_features_win{w}_HCSA_Indonesia.parquet").set_index("plot_id")
            hcsa = df["dataset"] == "HCSA_Indonesia"
            for c in [c for c in df.columns if c.startswith(SWAPPED)]:
                df.loc[hcsa, c] = df.loc[hcsa, "plot_id"].map(alt[c]) if c in alt else float("nan")
        df = df.merge(gt, on="plot_id")
        df = df[df["agb_Mg_ha"] > 1]
        e = leave_one_region_out(df, "agb_Mg_ha", "region", feats)
        h = e[e["dataset"] == "HCSA_Indonesia"]
        m = score(h, "agb_Mg_ha", "pred", f"E2 W={w}", "Mg AGB/ha", "HCSA_Indonesia")
        hf = df[df["dataset"] == "HCSA_Indonesia"]
        m.update({"window_days": w,
                  "frac_s2_clear": float((hf.get("s2_n_clear", 0) > 0).mean()),
                  "frac_ls_clear": float((hf.get("ls_n_clear", 0) > 0).mean()),
                  "frac_s1": float(hf.filter(like="s1_vv").notna().any(axis=1).mean())})
        rows.append(m)
    out = pd.DataFrame(rows)
    out.to_csv(OUTD / "window_sensitivity.csv", index=False)
    print(out[["window_days", "n_samples", "rrmse_pct", "relative_bias_pct", "r2_score", "lins_ccc",
               "frac_s2_clear", "frac_ls_clear", "frac_s1"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
