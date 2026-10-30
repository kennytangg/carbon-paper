"""
Paper figures, drawn from the result files only (no number is typed here).

Palette: the first three categorical slots of the reference palette, validated all-pairs for
colour-vision deficiency; every series also has its own marker and a direct label, so identity
never rests on colour alone. Grey is context, blue the series the finding is about.

Usage: python -m estimation.figures
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "data" / "estimation" / "results"
OUT = ROOT / "docs" / "figures"

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, GREY = "#0b0b0b", "#52514e", "#e4e3df", "#9a9993"
DS = {"Labriere2018": ("Labrière (1 ha)", BLUE, "o"),
      "GEO-TREES": ("GEO-TREES", ORANGE, "s"),
      "HCSA_Indonesia": ("HCSA Indonesia (0.05 ha)", AQUA, "^")}

plt.rcParams.update({
    "font.family": "serif", "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
    "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "lines.linewidth": 1.4, "pdf.fonttype": 42, "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02})
ONE_COL = 3.45


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.pdf")
    fig.savefig(OUT / f"{name}.png", dpi=200)
    plt.close(fig)


def fig_scatter():
    ev = pd.read_parquet(RES / "evaluation_table.parquet").dropna(subset=["E2_loro_lgbm"])
    ev = ev[ev["agb_Mg_ha"] > 1]
    fig, ax = plt.subplots(figsize=(ONE_COL, 3.0))
    for ds, (lab, col, mk) in DS.items():
        g = ev[ev["dataset"] == ds]
        ax.scatter(g["agb_Mg_ha"], g["E2_loro_lgbm"], s=9, c=col, marker=mk, alpha=0.75, linewidths=0, label=lab)
    lim = [2, 1000]
    ax.plot(lim, lim, color=INK2, lw=0.8, ls="--")
    ax.axhline(300, color=GREY, lw=0.8)
    ax.text(2.3, 330, "saturation near 300", color=INK2, fontsize=6.5)
    ax.text(600, 470, "1:1", color=INK2, fontsize=6.5)
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("Field AGB, standard formula (Mg ha$^{-1}$)")
    ax.set_ylabel("Blind satellite AGB, E2 (Mg ha$^{-1}$)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.16), ncol=2, frameon=False, handletextpad=0.2, columnspacing=0.8)
    save(fig, "fig_scatter")


def fig_cloud_month():
    m = pd.read_csv(RES / "cloud_by_month.csv").set_index("month")
    fig, ax = plt.subplots(figsize=(ONE_COL, 2.1))
    ax.axvspan(4.5, 9.5, color="#f0efec", zorder=0)
    ax.text(7, 0.015, "dry season", ha="center", color=INK2, fontsize=6.5)
    for colname, lab, col, mk in [("Indonesia (HCSA)", "Indonesia (24 loc.)", BLUE, "o"), ("Borneo, Sabah (SAFE)", "Sabah (10 loc.)", ORANGE, "s")]:
        y = m[colname]
        ax.plot(m.index, y, color=col, marker=mk, ms=3.5, label=lab)
    ax.set_xticks(range(1, 13), ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
    ax.set_ylim(0, 0.46)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_ylabel("Acquisitions with plot clear")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), frameon=False, ncol=2)
    save(fig, "fig_cloud_month")


def fig_closing_gap():
    a = pd.read_csv(RES / "aggregation_curve.csv")
    k = pd.read_csv(RES / "kshot_curve.csv")
    pref = {"LAB": "Labriere2018", "GT_": "GEO-TREES", "IDN": "HCSA_Indonesia"}
    a["ds"] = a["region"].str.slice(0, 3).map(pref)
    k["ds"] = k["region"].str.slice(0, 3).map(pref)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(ONE_COL, 2.2), sharey=True)
    for ds, (lab, col, mk) in DS.items():
        g = a[a["ds"] == ds].groupby("n_plots")["mean_abs_err_pct"].median()
        g = g[g.index <= 20]
        ax1.plot(g.index, g.values, color=col, marker=mk, ms=3, label=lab)
        h = k[k["ds"] == ds].groupby("k")["region_total_err_pct"].apply(lambda s: s.abs().median())
        ax2.plot(h.index, h.values, color=col, marker=mk, ms=3)
    for ax in (ax1, ax2):
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
    ax1.set_xticks([1, 2, 5, 10, 20], ["1", "2", "5", "10", "20"])
    ax2.set_xticks([1, 2, 5, 10, 20], ["1", "2", "5", "10", "20"])
    ax1.set_yticks([5, 10, 20, 50, 100, 200], ["5", "10", "20", "50", "100", "200"])
    ax1.set_xlabel("(a) plots averaged, $n$"); ax2.set_xlabel("(b) calibration plots, $k$")
    ax1.set_ylabel("Median abs. error (%)")
    fig.legend(*ax1.get_legend_handles_labels(), loc="lower center", bbox_to_anchor=(0.5, -0.17), ncol=3, frameon=False, fontsize=6, handlelength=1.2)
    save(fig, "fig_closing_gap")


def fig_cloud_intervals():
    c = pd.read_csv(RES / "cloud_aware_cqr.csv")
    order = ["Labriere2018", "GEO-TREES", "HCSA_Indonesia", "all"]
    names = ["Labrière", "GEO-TREES", "HCSA", "All"]
    fig, ax = plt.subplots(figsize=(ONE_COL, 1.9))
    xs = np.arange(len(order))
    w = 0.2
    spec = [("as observed", "plain", -1.5, GREY, "plain CQR, as observed"), ("fully clouded", "plain", -0.5, "#c9c8c2", "plain CQR, all clouded"),
            ("as observed", "aware", 0.5, "#8db8eb", "cloud-aware, as observed"), ("fully clouded", "aware", 1.5, BLUE, "cloud-aware, all clouded")]
    for cond, meth, off, col, lab in spec:
        v = [c[(c["condition"] == cond) & (c["method"] == meth) & (c["subset"] == d)]["coverage"].iloc[0] for d in order]
        ax.bar(xs + off * w, v, width=w * 0.92, color=col, label=lab)
    ax.axhline(0.9, color=INK, lw=0.8, ls="--")
    ax.text(3.62, 0.905, "90% target", ha="right", va="bottom", fontsize=6.5, color=INK)
    ax.set_xticks(xs, names)
    ax.set_ylim(0.6, 1.0)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_ylabel("Interval coverage")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=2, frameon=False, fontsize=6)
    save(fig, "fig_cloud_intervals")


def fig_model_assisted():
    s = pd.read_csv(RES / "project_with_field_plots.csv")
    s = s[s["method"] == "R satellite + k plots (ratio)"]
    fig, ax = plt.subplots(figsize=(ONE_COL, 1.8))
    for ds, (lab, col, mk) in DS.items():
        g = s[s["dataset"] == ds].sort_values("k")
        ax.plot(g["k"], g["rel_efficiency"], color=col, marker=mk, ms=3.5, label=lab)
    ax.axhline(1, color=INK2, lw=0.8, ls="--")
    ax.text(7.5, 0.9, "field only", ha="center", va="top", fontsize=6.5, color=INK2)
    ax.set_xticks([3, 5, 10, 20])
    ax.set_xlabel("Field plots in the project, $k$")
    ax.set_ylabel("Efficiency vs field only")
    ax.set_ylim(0, 2.6)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.3), frameon=False, ncol=3, fontsize=6, handlelength=1.2)
    save(fig, "fig_model_assisted")


def fig_frontier():
    f = pd.read_csv(RES / "crediting_frontier.csv")
    fig, ax = plt.subplots(figsize=(ONE_COL, 2.4))
    curves = [("satellite: conformal plain", "satellite only, conformal", BLUE, "o", "-"),
              ("satellite: parametric two-component bound", "satellite only, parametric bound", GREY, "s", "--"),
              ("satellite + 10 plots: design lower bound", "satellite + 10 plots, design bound", ORANGE, "^", "-")]
    for rule, lab, col, mk, ls in curves:
        g = f[f["rule"] == rule].sort_values("delta")
        g = g[g["delta"] <= 0.3]
        ax.plot(g["over"], g["yield"], color=col, marker=mk, ms=3.5, ls=ls, label=lab)
    for rule, lab, dx, dy in [("satellite: VM0047 deduction", "VM0047, satellite only", 0.012, -0.03),
                              ("satellite + 10 plots: VM0047 deduction", "VM0047, 10 plots", -0.01, -0.06)]:
        r = f[f["rule"] == rule].iloc[0]
        ax.scatter([r["over"]], [r["yield"]], marker="X", s=40, color=INK, zorder=5)
        ax.text(r["over"] + dx, r["yield"] + dy, lab, fontsize=6.5, color=INK, ha="left" if dx > 0 else "right")
    ax.axvline(0.10, color=INK2, lw=0.8, ls=":")
    ax.text(0.103, 0.975, "10% risk", fontsize=6.5, color=INK2, va="top")
    ax.set_xlabel("Over-crediting rate (share of projects)")
    ax.set_ylabel("Credit yield (credited / true)")
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_xlim(-0.01, 0.36); ax.set_ylim(0.45, 1.0)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=1, frameon=False, fontsize=6)
    save(fig, "fig_frontier")


def main():
    fig_frontier()
    fig_scatter()
    fig_cloud_month()
    fig_closing_gap()
    fig_cloud_intervals()
    fig_model_assisted()
    print("figures written to", OUT)


if __name__ == "__main__":
    main()
