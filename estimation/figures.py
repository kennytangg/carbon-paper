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


SAT_INPUTS = [("eth_plot_mean", "Height, ETH"), ("meta_plot_mean", "Height, Meta"),
              ("gedi1k_agbd_mean", "GEDI AGB"), ("palsar_hv_db", "PALSAR HV"), ("s1_vh_db", "S1 VH"),
              ("s2_ndvi", "NDVI"), ("E2_loro_lgbm", "E2 map")]
SAT_BANDS = [("100-300", 100, 300), (">=300", 300, np.inf)]


def input_saturation() -> pd.DataFrame:
    """Rank correlation of each input with field AGB in two bands of equal relative width (x3), and binned medians."""
    from scipy.stats import spearmanr
    est = ROOT / "data" / "estimation"
    d = (pd.read_parquet(est / "right_grid_sealed.parquet")[["plot_id", "agb_Mg_ha"]]
         .merge(pd.read_parquet(est / "left_features_win90.parquet"), on="plot_id")
         .merge(pd.read_parquet(est / "left_features_gee.parquet").drop(columns="date"), on="plot_id")
         .merge(pd.read_parquet(RES / "evaluation_table.parquet")[["plot_id", "E2_loro_lgbm"]], on="plot_id"))
    d = d[d["agb_Mg_ha"] > 1]
    rows = []
    for col, name in SAT_INPUTS:
        for band, lo, hi in SAT_BANDS:
            s = d[(d["agb_Mg_ha"] >= lo) & (d["agb_Mg_ha"] < hi)][[col, "agb_Mg_ha"]].dropna()
            rows.append({"input": col, "name": name, "band": band, "n": len(s), "spearman": spearmanr(s[col], s["agb_Mg_ha"])[0]})
    out = pd.DataFrame(rows)
    out.to_csv(RES / "input_saturation.csv", index=False)
    bins = pd.cut(d["agb_Mg_ha"], [0, 50, 100, 200, 300, 400, np.inf])
    med = d.groupby(bins, observed=True)[[c for c, _ in SAT_INPUTS]].median()
    med.insert(0, "field_mean", d.groupby(bins, observed=True)["agb_Mg_ha"].mean())
    med.insert(1, "n", d.groupby(bins, observed=True).size())
    med.to_csv(RES / "input_saturation_bins.csv")
    return out


def fig_saturation():
    """(a) blind E2 against the field; (b) each input's rank correlation with field AGB below and above 300 Mg/ha."""
    ev = pd.read_parquet(RES / "evaluation_table.parquet").dropna(subset=["E2_loro_lgbm"])
    ev = ev[ev["agb_Mg_ha"] > 1]
    sat = input_saturation()
    small = {"fontsize": 6.5, "labelpad": 1}
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(ONE_COL, 1.45), gridspec_kw={"width_ratios": [1, 0.82], "wspace": 0.62})
    for ds, (lab, col, mk) in DS.items():
        g = ev[ev["dataset"] == ds]
        ax1.scatter(g["agb_Mg_ha"], g["E2_loro_lgbm"], s=3.5, c=col, marker=mk, alpha=0.7, linewidths=0,
                    label={"Labriere2018": "Labrière", "GEO-TREES": "GEO-TREES", "HCSA_Indonesia": "HCSA"}[ds])
    lim = [2, 1000]
    ax1.plot(lim, lim, color=INK2, lw=0.7, ls="--")
    ax1.axhline(300, color=GREY, lw=0.7, zorder=0)
    ax1.text(2.3, 340, "300", color=INK2, fontsize=5.5)
    ax1.text(5, 2.6, "1:1", color=INK2, fontsize=6)
    ax1.set_xscale("log"); ax1.set_yscale("log"); ax1.set_xlim(lim); ax1.set_ylim(lim)
    ax1.set_xlabel("Field AGB (Mg ha$^{-1}$)", **small)
    ax1.set_ylabel("Blind E2 (Mg ha$^{-1}$)", **small)
    ax1.set_title("(a) blind error", fontsize=6.5, pad=2)
    ax1.tick_params(labelsize=5.5, pad=1)
    ax1.legend(loc="upper center", bbox_to_anchor=(0.45, -0.25), ncol=3, frameon=False, fontsize=5.5, handletextpad=0.0,
               columnspacing=0.4, markerscale=1.8)
    ys = np.arange(len(SAT_INPUTS))[::-1]
    for y, (col, name) in zip(ys, SAT_INPUTS):
        a = sat[(sat["input"] == col) & (sat["band"] == "100-300")]["spearman"].iloc[0]
        b = sat[(sat["input"] == col) & (sat["band"] == ">=300")]["spearman"].iloc[0]
        ax2.plot([a, b], [y, y], color=GREY, lw=1.0, zorder=1)
        ax2.scatter([a], [y], s=12, c=INK, zorder=2, label="100–300 Mg ha$^{-1}$" if y == ys[0] else None)
        ax2.scatter([b], [y], s=12, facecolors="white", edgecolors=INK, linewidths=0.8, zorder=3, label="≥300" if y == ys[0] else None)
    ax2.axvline(0, color=INK2, lw=0.6)
    ax2.set_yticks(ys, [n for _, n in SAT_INPUTS], fontsize=5.5)
    ax2.set_xlim(-0.25, 0.75); ax2.set_xticks([0, 0.3, 0.6], ["0", "0.3", "0.6"])
    ax2.tick_params(labelsize=5.5, pad=1)
    ax2.set_xlabel("Rank corr. with field", **small)
    ax2.set_title("(b) signal in each input", fontsize=6.5, pad=2)
    ax2.grid(axis="y", visible=False)
    ax2.legend(loc="upper center", bbox_to_anchor=(0.4, -0.25), ncol=2, frameon=False, fontsize=5.5, handletextpad=0.0,
               columnspacing=0.5)
    save(fig, "fig_saturation")


BAND = "#f0efec"  # the +/-25% band around the field amount
SIM_METHODS = [("map_pct", "Map", "o", INK, INK), ("credited_pct", "Credit", "o", "white", INK),
               ("e4cal_pct", "E4 scaled", "s", "white", INK2), ("e4_pct", "E4", "^", INK2, INK2)]


def _pct_axis(ax, xmax):
    ax.axvspan(75, 125, color=BAND, zorder=0, lw=0)
    ax.axvline(100, color=INK2, lw=0.7, ls="--", zorder=1)
    ax.set_xlim(0, xmax)
    ax.grid(axis="y", visible=False)
    ax.tick_params(labelsize=6.2, pad=1)


def fig_projects():
    """(a) the ten first simulated projects, method by method; (b) all 1,000: median, 5th-95th percentile, share within 25%."""
    s = pd.read_csv(RES / "simulations.csv").sort_values("sim")
    ten = s.head(10)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(ONE_COL, 1.82), sharex=True, gridspec_kw={"height_ratios": [10, 4.2]})
    # labels stay inside the column width, so the figure is printed at its own size, not shrunk
    fig.subplots_adjust(left=0.41, right=0.89, top=0.95, bottom=0.21, hspace=0.4)
    ys = np.arange(len(ten))[::-1]
    for col, lab, mk, fc, ec in SIM_METHODS:
        ax1.scatter(ten[col].clip(upper=198), ys, s=10, marker=mk, facecolors=fc, edgecolors=ec, linewidths=0.8, zorder=3, label=lab)
    names = [f"{r.sim} {r.site.replace('Labriere', 'Labrière')}, {r.field_tCO2e / 1000:.0f} kt" for r in ten.itertuples()]
    ax1.set_yticks(ys, names, fontsize=6.2)
    _pct_axis(ax1, 200)
    ax1.set_title("(a) ten projects", fontsize=6.5, pad=2, loc="left")
    fig.legend(*ax1.get_legend_handles_labels(), loc="upper center", bbox_to_anchor=(0.6, 0.06), ncol=4, frameon=False, fontsize=6.2,
               handletextpad=0.1, columnspacing=1.2)
    yb = np.arange(len(SIM_METHODS))[::-1]
    for y, (col, lab, mk, fc, ec) in zip(yb, SIM_METHODS):
        v = s[col]
        lo, med, hi = v.quantile([0.05, 0.5, 0.95])
        within = 100 * ((v - 100).abs() <= 25).mean()
        ax2.plot([lo, hi], [y, y], color=GREY, lw=1.6, solid_capstyle="butt", zorder=2)
        ax2.scatter([med], [y], s=10, marker=mk, facecolors=fc, edgecolors=ec, linewidths=0.8, zorder=3)
        ax2.text(203, y, f"{within:.0f}%", fontsize=6.2, va="center", color=INK, clip_on=False)
    ax2.set_yticks(yb, [m[1] for m in SIM_METHODS], fontsize=6.2)
    ax2.set_ylim(-0.6, len(SIM_METHODS) - 0.4)
    _pct_axis(ax2, 200)
    ax2.set_title("(b) all 1,000: median, 5th–95th pct.", fontsize=6.5, pad=2, loc="left")
    ax2.text(1.01, 1.08, "±25%", transform=ax2.transAxes, fontsize=6.2, va="bottom", color=INK2)
    ax2.set_xlabel("Carbon found, % of the field amount", fontsize=6.5, labelpad=1)
    ax2.set_xticks([0, 50, 100, 150, 200])
    save(fig, "fig_projects")


def fig_fixes():
    """Each fix on the 1,000 projects (median, 5th-95th percentile, share within 25%) and its total on the 35 Danum plots."""
    cf = pd.read_csv(RES / "crediting_fixes.csv")
    cf = cf[cf["subset"] == "All"]
    he = pd.read_csv(RES / "height_equations_projects.csv")
    dz = pd.read_csv(RES / "external_danum.csv").set_index("estimate")["total_pct_of_field"]
    dq = pd.read_csv(RES / "external_danum_equations.csv").set_index("estimate")["total_pct_of_field"]

    def row(df, mp, est):
        r = df[(df["map"] == mp) & (df["estimate"] == est)].iloc[0]
        return r["median_pct"], r["p5_pct"], r["p95_pct"], r["within_25pct"]

    j = he[(he["estimate"] == "Jucker 2018 Eq 10 [CHMv2]") & (he["subset"] == "All")].iloc[0]
    rows = [("Map, E2 + CH + GEDI", row(cf, "best map", "map_pct"), None),
            ("Embeddings map", row(cf, "embeddings + CH + GEDI", "map_pct"), dz["map"]),
            ("× realm bias (estimate)", row(cf, "embeddings + CH + GEDI", "map_mu_realm_pct"), dz["estimate"]),
            ("Credit, region-level q", row(cf, "embeddings + CH + GEDI", "credit_region_q"), dz["credit"]),
            ("Jucker 2018, 2026 map", (j["median_pct"], j["p5_pct"], j["p95_pct"], j["within_25pct"]), dq["Jucker 2018 Eq 10 [CHMv2]"])]
    fig, ax = plt.subplots(figsize=(ONE_COL, 1.08))
    fig.subplots_adjust(left=0.39, right=0.88, top=0.84, bottom=0.26)
    ys = np.arange(len(rows))[::-1]
    for y, (lab, (med, lo, hi, within), danum) in zip(ys, rows):
        ax.plot([lo, hi], [y, y], color=GREY, lw=1.6, solid_capstyle="butt", zorder=2)
        ax.scatter([med], [y], s=10, c=INK, zorder=3, label="1,000 projects, median" if y == ys[0] else None)
        if danum is not None:
            ax.scatter([danum], [y], s=20, marker="D", facecolors="white", edgecolors=INK, linewidths=0.9, zorder=4,
                       label="35 unseen Danum plots" if y == ys[1] else None)
        ax.text(203, y, f"{within:.1f}%", fontsize=6.2, va="center", color=INK, clip_on=False)
    ax.text(1.01, 1.0, "±25%", transform=ax.transAxes, fontsize=6.2, va="bottom", color=INK2)
    ax.set_yticks(ys, [r[0] for r in rows], fontsize=6.2)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    _pct_axis(ax, 200)
    ax.set_xticks([0, 50, 100, 150, 200])
    ax.set_xlabel("Carbon found, % of the field amount", fontsize=6.5, labelpad=1)
    ax.legend(loc="lower center", bbox_to_anchor=(0.36, 0.98), ncol=2, frameon=False, fontsize=6.2, handletextpad=0.1, columnspacing=1.0)
    save(fig, "fig_fixes")


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
    fig_saturation()
    fig_cloud_month()
    fig_closing_gap()
    fig_cloud_intervals()
    fig_model_assisted()
    print("figures written to", OUT)


if __name__ == "__main__":
    main()
