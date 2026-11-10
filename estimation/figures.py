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


EST = ROOT / "data" / "estimation"
CF, CO2 = 0.47, 44 / 12
EXAMPLE_PLOT = "HCSA_Riau_RU12"   # Indonesian plot with clear Sentinel-2 views, a 1 m height patch, GEDI and radar
FINAL_MODEL = "embeddings + CH + GEDI"


def _example_inputs(pid):
    """Everything the left grid read for one plot, and what it predicted."""
    import json
    chm = next(e for e in json.loads((RES / "chm_examples.json").read_text()) if e["plot_id"] == pid)
    n = int(chm["size"])
    heights = np.array([ord(c) - 35 for c in chm["heights"]], dtype=float).reshape(n, n)
    opt = pd.read_parquet(EST / "left_features_win90.parquet").set_index("plot_id").loc[pid]
    gee = pd.read_parquet(EST / "left_features_gee.parquet").set_index("plot_id").loc[pid]
    pred = pd.read_parquet(RES / "accuracy_embeddings_preds.parquet").set_index("plot_id").loc[pid]
    return dict(heights=heights, r=float(chm["footprint_r_m"]), red=opt["s2_B04"], nir=opt["s2_B08"], ndvi=opt["s2_ndvi"],
                n_clear=int(opt["s2_n_clear"]), vv=opt["s1_vv_db"], ch=gee["meta_plot_mean"], gedi=gee["gedi1k_agbd_mean"],
                agb=pred[FINAL_MODEL], agb_field=pred["agb_Mg_ha"])


def _arrow(fig, x0, x1, y=0.5):
    fig.add_artist(matplotlib.patches.FancyArrowPatch((x0, y), (x1, y), transform=fig.transFigure, arrowstyle="-|>",
                                                      mutation_scale=9, color=INK2, lw=1.0))


def _no_frame(ax):
    ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    for sp in ax.spines.values():
        sp.set_visible(False)


def _s2_patch(pid):
    """The Sentinel-2 patch saved by estimation.extract_s2_patch: true colour and NDVI."""
    z = np.load(RES / f"s2_patch_{pid}.npz")
    stretch = lambda v: np.clip((v - np.percentile(v, 2)) / (np.percentile(v, 98) - np.percentile(v, 2)), 0, 1) ** 0.8
    rgb = np.dstack([stretch(z[b]) for b in ("B04", "B03", "B02")])
    ndvi = (z["B08"] - z["B04"]) / (z["B08"] + z["B04"])
    return rgb, ndvi, float(z["half_m"]) + float(z["pixel_m"]) / 2, str(z["date"])


def _tile(fig, rect, img, extent, r, title, note, **kw):
    """One image tile at a common 140 m view, with the field plot circled."""
    ax = fig.add_axes(rect)
    ax.imshow(img, extent=extent, interpolation="nearest", **kw)
    ax.add_patch(matplotlib.patches.Circle((0, 0), r, fill=False, ec=ORANGE, lw=1.4))
    ax.set_xlim(-70, 70); ax.set_ylim(-70, 70); ax.set_aspect("equal")
    _no_frame(ax)
    ax.set_title(title, loc="left", fontsize=7, pad=2)
    ax.text(-66, -66, note, fontsize=5.8, color="white", va="bottom")
    return ax


def fig_pixel_to_carbon():
    """One real plot, from what the satellite records to the carbon number."""
    x = _example_inputs(EXAMPLE_PLOT)
    rgb, ndvi, s2_half, s2_date = _s2_patch(EXAMPLE_PLOT)
    fig = plt.figure(figsize=(7.1, 1.82))
    bottom, height = 0.17, 0.60

    # (a) three views of the same 140 m around the plot: colour, greenness, height
    th, tb = 0.39, 0.27
    h = x["heights"]
    fig.text(0.002, bottom + height + 0.05, "(a) What the satellites see", fontsize=8, va="bottom")
    _tile(fig, [0.0, tb, 0.1, th], rgb, [-s2_half, s2_half, -s2_half, s2_half], x["r"], "colour, 10 m", "140 m")
    _tile(fig, [0.105, tb, 0.1, th], ndvi, [-s2_half, s2_half, -s2_half, s2_half], x["r"], "NDVI", "0.6 to 0.9",
          cmap="YlGn", vmin=0.6, vmax=0.92)
    _tile(fig, [0.21, tb, 0.1, th], h, [-70, 70, -70, 70], x["r"], "height, 1 m", "0 to 40 m", cmap="viridis", vmin=0, vmax=40)
    _arrow(fig, 0.318, 0.345)

    # (b) every number the satellites give for this plot, with its source
    ax = fig.add_axes([0.355, bottom, 0.17, height]); ax.axis("off")
    ax.set_title("(b) As numbers", loc="left")
    rows = [("Sentinel-2", None), ("red (B4)", f"{x['red']:.2f}"), ("near-IR (B8)", f"{x['nir']:.2f}"),
            ("NDVI", f"{x['ndvi']:.2f}"), ("Sentinel-1 radar", None), ("VV backscatter", f"{x['vv']:.1f} dB"),
            ("Published maps", None), ("canopy height", f"{x['ch']:.0f} m"),
            ("GEDI biomass", f"{x['gedi']:.0f} Mg/ha"), ("AlphaEarth", "64 values")]
    for i, (k, v) in enumerate(rows):
        y = 0.98 - i * 0.108
        if v is None:
            ax.text(0.0, y, k, fontsize=6.1, color=INK2, va="center", style="italic", transform=ax.transAxes)
        else:
            ax.text(0.05, y, k, fontsize=6.3, color=INK, va="center", transform=ax.transAxes)
            ax.text(1.0, y, v, fontsize=6.3, color=INK, va="center", ha="right", transform=ax.transAxes)
    _arrow(fig, 0.532, 0.56)

    # (c) the model learns on other regions' field plots, then predicts this one blind
    ax = fig.add_axes([0.565, bottom, 0.165, height]); ax.axis("off")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_title("(c) Learn, then predict", loc="left")
    ax.text(0.5, 1.0, "other regions:\nnumbers $+$ field biomass", fontsize=6.1, color=INK, ha="center", va="top", linespacing=1.1)
    for i in range(6):
        ax.add_patch(matplotlib.patches.Circle((0.15 + i * 0.14, 0.72), 0.035, fc=AQUA, ec="none"))
    ax.annotate("", (0.5, 0.55), (0.5, 0.67), arrowprops=dict(arrowstyle="-|>", color=INK2, lw=0.9, mutation_scale=7))
    ax.add_patch(matplotlib.patches.FancyBboxPatch((0.06, 0.34), 0.88, 0.19, boxstyle="round,pad=0,rounding_size=0.05",
                                                   fc="#e8f0fa", ec=BLUE, lw=0.8))
    ax.text(0.5, 0.435, "model learns\nnumbers $\\to$ biomass", fontsize=6.2, color=INK, ha="center", va="center", linespacing=1.15)
    ax.annotate("", (0.5, 0.16), (0.5, 0.32), arrowprops=dict(arrowstyle="-|>", color=INK2, lw=0.9, mutation_scale=7))
    ax.add_patch(matplotlib.patches.Circle((0.5, 0.08), 0.035, fc="white", ec=ORANGE, lw=1.2))
    ax.text(0.5, 0.0, "this plot: numbers only,\nits field value never used", fontsize=6.1, color=INK, ha="center", va="top", linespacing=1.1)
    _arrow(fig, 0.735, 0.765)

    # (d) biomass -> carbon -> CO2e, the satellite guess against the sealed field value
    ax = fig.add_axes([0.8, bottom, 0.195, height])
    sat = np.array([x["agb"], x["agb"] * CF, x["agb"] * CF * CO2])
    fld = np.array([x["agb_field"], x["agb_field"] * CF, x["agb_field"] * CF * CO2])
    xs = np.arange(3)
    ax.set_axisbelow(True)
    ax.bar(xs, sat, width=0.38, color=BLUE, label="satellite")
    ax.scatter(xs, fld, marker="_", s=170, color=INK, lw=1.5, zorder=4, label="field")
    for xi, v in zip(xs, sat):
        ax.text(xi, v / 2, f"{v:.0f}", ha="center", va="center", fontsize=6.3, color="white")
    for x0, lab in [(0.5, "$\\times$0.47"), (1.5, "$\\times$44/12")]:
        ax.text(x0, 8, lab, ha="center", va="bottom", fontsize=5.4, color=INK2)
    ax.set_xticks(xs, ["biomass\nMg/ha", "carbon\nt C/ha", "CO$_2$e\nt/ha"])
    ax.tick_params(axis="x", labelsize=6.3)
    ax.set_ylim(0, 250); ax.set_yticks([0, 100, 200]); ax.grid(axis="x", visible=False)
    ax.set_title("(d) Biomass $\\to$ carbon", loc="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, 1.0), frameon=False, fontsize=6, handlelength=1.0, borderaxespad=0.1, labelspacing=0.25)
    save(fig, "fig_pixel_to_carbon")


DANUM = EST / "external"


def fig_unseen():
    """The blind test on Danum: what was sealed, what was committed, and the 35 plots after the reveal."""
    import json
    led = [json.loads(l) for l in (DANUM / "danum_ledger.jsonl").read_text().splitlines()]
    seal, commit = led[0], led[1]
    dp = pd.read_csv(RES / "external_danum_plots.csv").sort_values("agb_Mg_ha").reset_index(drop=True)
    dz = pd.read_csv(RES / "external_danum.csv").set_index("estimate")["total_pct_of_field"]
    fig = plt.figure(figsize=(7.1, 1.5))

    # (a) the protocol, top to bottom, with the ledger's own fingerprints
    ax = fig.add_axes([0.0, 0.02, 0.27, 0.86]); ax.axis("off")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_title("(a) Blind test protocol", loc="left")
    steps = [(0.88, "1. Seal", "field carbon of the 35 plots", f"hash {seal['sealed_sha256'][:10]}"),
             (0.49, "2. Predict", "trained without Danum, committed", f"hash {commit['predictions_sha256'][:10]}"),
             (0.10, "3. Reveal", "open the seal, compare", "same hash as step 1")]
    for y, head, lab, sub in steps:
        ax.text(0.0, y + 0.08, head, fontsize=7.2, color=INK, va="center", fontweight="bold")
        ax.text(0.0, y, lab, fontsize=6.6, color=INK, va="center")
        ax.text(0.0, y - 0.08, sub, fontsize=6, color=INK2, va="center", family="monospace")
    for y in (0.76, 0.37):
        ax.annotate("", (0.04, y - 0.15), (0.04, y), arrowprops=dict(arrowstyle="-|>", color=INK2, lw=0.9, mutation_scale=7))

    # (b) the 35 plots after the reveal, sorted by field biomass
    ax = fig.add_axes([0.355, 0.2, 0.635, 0.68])
    ax.set_axisbelow(True)
    xs = np.arange(len(dp))
    ax.bar(xs, dp["agb_Mg_ha"], width=0.75, color="#cfe3c4", label="field (sealed)")
    ax.scatter(xs, dp["map_agb_Mg_ha"], s=12, fc="white", ec=GREY, lw=0.9, zorder=3, label=f"map, {dz['map']:.0f}% of field total")
    ax.scatter(xs, dp["estimate_agb_Mg_ha"], s=12, color=BLUE, zorder=4, label=f"estimate, {dz['estimate']:.0f}%")
    ax.scatter(xs, dp["credit_agb_Mg_ha"], s=22, marker="_", color=ORANGE, lw=1.4, zorder=4, label=f"credit, {dz['credit']:.0f}%")
    ax.set_xlim(-0.8, len(dp) - 0.2); ax.set_xticks([])
    ax.set_xlabel("35 unseen Danum plots, sorted by field biomass", labelpad=2)
    ax.set_ylabel("AGB, Mg/ha", labelpad=1); ax.set_ylim(0, 800); ax.set_yticks([0, 200, 400, 600, 800])
    ax.grid(axis="x", visible=False)
    ax.set_title("(b) After the reveal", loc="left")
    ax.legend(loc="upper left", frameon=False, fontsize=6.3, handlelength=1.2, borderaxespad=0.2, labelspacing=0.3)
    save(fig, "fig_unseen")


def main():
    fig_pixel_to_carbon()
    fig_unseen()
    fig_frontier()
    fig_scatter()
    fig_cloud_month()
    fig_closing_gap()
    fig_cloud_intervals()
    fig_model_assisted()
    print("figures written to", OUT)


if __name__ == "__main__":
    main()
