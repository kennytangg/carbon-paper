"""
The right grid as the standards define it: every pool, every step, and its uncertainty.

The sealed point values (Chave 2014 Eq. 4, CF 0.47) are not changed. This module adds what a
verifier would ask for on top of them, following IPCC 2006/2019, SNI 7724:2011, CDM AR-TOOL14 and
AR-TOOL03, Verra VM0047 v1.1 and the Gold Standard A/R methodology:

  G1  tree -> plot Monte Carlo (IPCC Approach 2) on HCSA: DBH error (Chave et al. 2004), height
      error 10%, wood-density error by taxonomic level (BIOMASS 2.1.4), allometric residual
      (RSE 0.357), carbon fraction N(0.4713, 0.0206) (Thomas & Martin 2012)
  G2  pools: AGB measured; BGB = R x AGB with IPCC 2006 (0.37, the SNI 7724 Lampiran A value) or
      IPCC 2019 Asia (0.207 / 0.212 by the 125 Mg/ha threshold); dead wood, litter and soil are not
      in the public record and are reported as omitted (conservative)
  G3  allometric-model choice: Chave 2014 Eq. 4 vs Basuki et al. 2009 (East Kalimantan, D + WD)
  G4  project level per region: stratified estimate (AR-TOOL14 Eqs. 14-17) over HCS classes,
      90% uncertainty, the deduction of each standard, AR-TOOL03 plots needed for +/-10% at 90%,
      and the error budget (sampling vs measurement + allometry)
  G5  SAFE sequestration: tree-level Monte Carlo of dAGB/dt with the allometric and height
      residual of a tree held fixed across censuses (permanent plots) or redrawn, and the VM0047
      v1.1 Eq. 28 uncertainty of block removals with and without the t0-t1 correlation rho

Usage: python -m estimation.right_grid_uncertainty
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyreadr
from scipy import stats

from estimation.right_grid import hcsa_trees
from estimation.right_grid_seq import CENSUSES, PLOT_AREA_HA, load_census, wood_density_lookup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "gt_raw"
EST = ROOT / "data" / "estimation"
OUTD = EST / "results"
N_MC = 2000
RSE_CHAVE = 0.357
WD_SD = {"species": 0.0708, "genus": 0.0941, "family": 0.1234, "none": 0.1234}  # BIOMASS 2.1.4 sd_10
CF_MU, CF_SD = 0.4713, 0.0206
R_2006 = 0.37
R_2019 = ((125, 0.207, 0.072), (np.inf, 0.212, 0.077))  # Asia, tropical rainforest, natural
HCS_CLASS = {"high density forest": "HDF", "medium density forest": "MDF", "low density forest": "LDF",
             "young regeneration forest": "YRF", "young regenerating forest": "YRF", "young generation forest": "YRF",
             "young regeneretaion forest": "YRF", "scrub": "S", "open land": "OL", "urban": "OL", "palm oil tree": "OP"}


# ---------------------------------------------------------------- error models
def dbh_draw(d: np.ndarray, rng, n: int) -> np.ndarray:
    """Chave et al. (2004): 95% of stems SD = 0.0062 D + 0.0904 cm, 5% SD = 4.64 cm; truncated to [0.1, 500]."""
    big = rng.random((d.size, n)) < 0.05
    sd = np.where(big, 4.64, (0.0062 * d + 0.0904)[:, None])
    return np.clip(d[:, None] + rng.standard_normal((d.size, n)) * sd, 0.1, 500)


def wd_level(genus: pd.Series, species: pd.Series, family: pd.Series) -> pd.Series:
    wd = pyreadr.read_r(RAW / "wood_density" / "wdData_BIOMASS_v2.1.11.rda")["wdData"]
    sp = set(zip(wd["genus"], wd["species"]))
    ge, fa = set(wd["genus"]), set(wd["family"])
    return pd.Series([("species" if (g, s) in sp else "genus" if g in ge else "family" if f in fa else "none")
                      for g, s, f in zip(genus, species, family)], index=genus.index)


def chave(d, h, wd):
    return 0.0673 * (wd * d ** 2 * h) ** 0.976


# ---------------------------------------------------------------- G1-G3: HCSA trees and plots
def hcsa_monte_carlo(seed: int = 0):
    rng = np.random.default_rng(seed)
    t = hcsa_trees().reset_index(drop=True)
    name = t["Scientific Name"].fillna("").str.strip().str.split()
    t["genus"] = name.str[0].fillna("")
    t["species"] = name.str[1].fillna("")
    t["wd_level"] = wd_level(t["genus"], t["species"], t["Famili"].fillna(""))
    t["hcs_class"] = t["Land Cover Update"].str.strip().str.lower().map(HCS_CLASS).fillna("OTHER")
    d, h, wd = (t[c].to_numpy(float) for c in ("DBH (cm)", "Height (m)", "Wood density (g/cm3)"))
    D = dbh_draw(d, rng, N_MC)
    H = np.clip(h[:, None] * (1 + 0.10 * rng.standard_normal((len(t), N_MC))), 1.3, None)
    WD = np.clip(wd[:, None] + t["wd_level"].map(WD_SD).to_numpy()[:, None] * rng.standard_normal((len(t), N_MC)), 0.08, 1.39)
    eps = rng.standard_normal((len(t), N_MC)) * RSE_CHAVE
    agb_kg = chave(D, H, WD) * np.exp(eps)
    contrib = agb_kg / 1000.0 / t["area_protocol_ha"].to_numpy()[:, None]

    keys, inv = np.unique(t["plot_key"], return_inverse=True)
    plot_mc = np.zeros((len(keys), N_MC))
    np.add.at(plot_mc, inv, contrib)
    det = t.groupby("plot_key")["agb_Mg_ha_contrib"].sum().reindex(keys).to_numpy()
    basuki = (np.exp(-0.744 + 2.188 * np.log(d) + 0.832 * np.log(wd)) * 1.047) / 1000.0 / t["area_protocol_ha"].to_numpy()
    basuki_plot = np.bincount(inv, weights=basuki, minlength=len(keys))
    palm = np.bincount(inv, weights=(t["hcs_class"] == "OP").to_numpy() * t["agb_Mg_ha_contrib"].to_numpy(), minlength=len(keys))

    first = t.groupby("plot_key").first().reindex(keys)
    plots = pd.DataFrame({
        "plot_key": keys, "region": "IDN_" + first["Region"].str.replace(" ", "").to_numpy(),
        "hcs_class": t.groupby("plot_key")["hcs_class"].agg(lambda s: s.mode().iloc[0]).reindex(keys).to_numpy(),
        "agb_det": det, "agb_mc_median": np.median(plot_mc, 1), "agb_mc_mean": plot_mc.mean(1),
        "agb_lo95": np.percentile(plot_mc, 2.5, 1), "agb_hi95": np.percentile(plot_mc, 97.5, 1),
        "agb_mc_sd": plot_mc.std(1), "agb_basuki": basuki_plot, "palm_agb": palm,
        "n_trees": np.bincount(inv, minlength=len(keys))})
    plots["rel_hw95_pct"] = 100 * (plots["agb_hi95"] - plots["agb_lo95"]) / 2 / plots["agb_mc_median"]

    # G2 pools: BGB and carbon, each with its own uncertainty
    cf = np.clip(CF_MU + CF_SD * rng.standard_normal(N_MC), 0.40, 0.55)
    r19 = np.where(plot_mc <= 125, R_2019[0][1], R_2019[1][1])
    r19_sd = np.where(plot_mc <= 125, R_2019[0][2], R_2019[1][2])
    R = np.clip(r19 + r19_sd * rng.standard_normal(plot_mc.shape), 0.02, None)
    total_c_mc = plot_mc * (1 + R) * cf
    plots["c_total_2019_det"] = plots["agb_det"] * (1 + np.where(plots["agb_det"] <= 125, 0.207, 0.212)) * 0.47
    plots["c_total_2006_det"] = plots["agb_det"] * (1 + R_2006) * 0.47
    plots["c_total_mc_median"] = np.median(total_c_mc, 1)
    plots["c_total_lo95"], plots["c_total_hi95"] = np.percentile(total_c_mc, 2.5, 1), np.percentile(total_c_mc, 97.5, 1)
    plots["co2e_2019_det"] = plots["c_total_2019_det"] * 44 / 12

    trees = t[["plot_key", "DBH (cm)", "wd_level", "hcs_class"]].assign(agb_kg=t["agb_kg"])
    return plots, plot_mc, trees


# ---------------------------------------------------------------- G4: project level
def t90(df):
    return stats.t.ppf(0.95, max(df, 1))


def ar_tool14_discount(u: float) -> float:
    """AR-TOOL14 v04.2 Appendix 2: discount as a share of U."""
    share = 0 if u <= 0.10 else 0.25 if u <= 0.15 else 0.50 if u <= 0.20 else 0.75 if u <= 0.30 else 1.0
    return share * u


def ar_tool03_n(w: np.ndarray, s: np.ndarray, mean: float, e: float = 0.10) -> int:
    """AR-TOOL03 Eq. 2 with Neyman allocation, E as a fraction of the mean; iterate t if n < 30."""
    E = e * mean
    n = (stats.norm.ppf(0.95) / E) ** 2 * (w * s).sum() ** 2
    for _ in range(5):
        if n >= 30:
            break
        n = (t90(int(np.ceil(n)) - 1) / E) ** 2 * (w * s).sum() ** 2
    return int(np.ceil(n))


def project_level(plots: pd.DataFrame, plot_mc: np.ndarray) -> pd.DataFrame:
    rows = []
    for reg, g in plots.groupby("region"):
        idx = g.index.to_numpy()
        strata = g.groupby("hcs_class")
        w = strata.size() / len(g)  # plot share stands in for mapped stratum area (not public)
        b_i = strata["agb_det"].mean()
        s_i = strata["agb_det"].std(ddof=1).fillna(0)
        n_i = strata.size()
        b = float((w * b_i).sum())
        var_s = float((w ** 2 * s_i ** 2 / n_i).sum())
        M = len(n_i)
        u90 = t90(len(g) - M) * np.sqrt(var_s) / b
        u95 = stats.t.ppf(0.975, max(len(g) - M, 1)) * np.sqrt(var_s) / b
        # measurement + allometry: Monte Carlo variance of the same stratified mean
        wt = g["hcs_class"].map(w / n_i).to_numpy()
        strat_mc = (plot_mc[idx] * wt[:, None]).sum(0)
        var_m = float(strat_mc.var())
        u_tot = stats.norm.ppf(0.95) * np.sqrt(var_s + var_m) / b
        rows.append({"region": reg, "n_plots": len(g), "n_strata": M, "agb_mean": b, "u90_sampling_pct": 100 * u90,
                     "u95_sampling_pct": 100 * u95, "u90_total_pct": 100 * u_tot,
                     "share_sampling_pct": 100 * var_s / (var_s + var_m), "share_measurement_pct": 100 * var_m / (var_s + var_m),
                     "deduct_VM0047_pct": 100 * min(1.0, max(0.0, u90 - 0.10)),
                     "deduct_ARTOOL14_pct": 100 * ar_tool14_discount(u90),
                     "deduct_GS_pct": 100 * max(0.0, u90 - 0.20),
                     "deduct_VMD0017_pct": 100 * max(0.0, u95 - 0.15),
                     "SNI7724_meets_20pct": bool(u95 <= 0.20),
                     "n_needed_10pct_90": ar_tool03_n(w.to_numpy(), s_i.to_numpy(), b),
                     "agb_basuki_mean": float((w * strata["agb_basuki"].mean()).sum())})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- G5: SAFE sequestration
def safe_monte_carlo(n_mc: int = 400, seed: int = 1):
    rng = np.random.default_rng(seed)
    seq = pd.read_parquet(EST / "seq_right_grid_sealed.parquet")
    seq = seq[~seq["block"].str.startswith("OP")]  # Chave is not valid for oil palm (see paper)
    df = load_census()
    df["PlotID"] = df["PlotID"].astype(str)
    df = df[("SAFE_" + df["PlotID"]).isin(seq["plot_id"])].reset_index(drop=True)
    sp, ge, fa, wd_default = wood_density_lookup()
    df["wd"] = [sp.get((g, s)) or ge.get(g) or fa.get(f) or np.nan for g, s, f in zip(df.get("Genus"), df.get("Species"), df.get("Family"))]
    df["wd_level"] = ["species" if (g, s) in sp else "genus" if g in ge else "family" if f in fa else "none"
                      for g, s, f in zip(df.get("Genus"), df.get("Species"), df.get("Family"))]
    df["wd"] = df["wd"].fillna(df.groupby("PlotID")["wd"].transform("mean")).fillna(wd_default)

    # local H-D model, as in right_grid_seq, with its residual SD
    hd = []
    for c in CENSUSES:
        d = pd.to_numeric(df.get(f"DBH{c}_mm_clean"), errors="coerce") / 10.0
        h = pd.to_numeric(df.get(f"Length_{c}_m"), errors="coerce")
        ok = (d >= 10) & (h > 1.3) & (h < 80)
        hd.append(pd.DataFrame({"d": d[ok], "h": h[ok]}))
    hd = pd.concat(hd)
    b, a = np.polyfit(np.log(hd["d"]), np.log(hd["h"]), 1)
    res = np.log(hd["h"]) - (a + b * np.log(hd["d"]))
    smear, hd_sd = float(np.mean(np.exp(res))), float(res.std())

    n = len(df)
    wd_mc = np.clip(df["wd"].to_numpy()[:, None] + df["wd_level"].map(WD_SD).to_numpy()[:, None] * rng.standard_normal((n, n_mc)), 0.08, 1.39)
    eps_fixed = rng.standard_normal((n, n_mc)) * RSE_CHAVE   # a tree keeps its allometric residual
    h_fixed = rng.standard_normal((n, n_mc)) * hd_sd          # and its height residual
    plot_idx = {p: i for i, p in enumerate(seq["plot_id"])}
    pi = ("SAFE_" + df["PlotID"]).map(plot_idx).to_numpy()

    def plot_agb(census: str, correlated: bool):
        d = pd.to_numeric(df.get(f"DBH{census}_mm_clean"), errors="coerce").to_numpy() / 10.0
        alive = np.nan_to_num(d) >= 10
        dd = dbh_draw(np.where(alive, d, 10.0), rng, n_mc)
        eps = eps_fixed if correlated else rng.standard_normal((n, n_mc)) * RSE_CHAVE
        hres = h_fixed if correlated else rng.standard_normal((n, n_mc)) * hd_sd
        hh = np.exp(a + b * np.log(dd) + hres)
        agb = chave(dd, hh, wd_mc) * np.exp(eps) / 1000.0 / PLOT_AREA_HA
        agb[~alive] = 0.0
        out = np.zeros((len(seq), n_mc))
        np.add.at(out, pi, agb)
        return out

    yrs = seq["years"].to_numpy()[:, None]
    out = {}
    for corr in (True, False):
        a0 = np.zeros((len(seq), n_mc)); a1 = np.zeros((len(seq), n_mc))
        # each plot uses its own first and last census
        for c in set(seq["census_t0"]) | set(seq["census_t1"]):
            m0, m1 = (seq["census_t0"] == c).to_numpy(), (seq["census_t1"] == c).to_numpy()
            if m0.any() or m1.any():
                pa = plot_agb(c, corr)
                a0[m0], a1[m1] = pa[m0], pa[m1]
        out["correlated" if corr else "independent"] = (a1 - a0) / yrs
    plots = seq[["plot_id", "block", "years", "agb_t0_Mg_ha", "agb_t1_Mg_ha", "dagb_Mg_ha_yr"]].copy()
    for k, v in out.items():
        plots[f"dagb_sd_{k}"] = v.std(1)
        plots[f"dagb_lo95_{k}"], plots[f"dagb_hi95_{k}"] = np.percentile(v, 2.5, 1), np.percentile(v, 97.5, 1)

    # block removals: VM0047 v1.1 Eq. 28, sampling SE of mean stocks with and without rho
    rows = []
    for blk, g in plots.groupby("block"):
        if len(g) < 5:
            continue
        k = len(g)
        T = t90(k - 1)
        se0, se1 = g["agb_t0_Mg_ha"].std(ddof=1) / np.sqrt(k), g["agb_t1_Mg_ha"].std(ddof=1) / np.sqrt(k)
        rho = float(np.corrcoef(g["agb_t0_Mg_ha"], g["agb_t1_Mg_ha"])[0, 1])
        dC = float(g["agb_t1_Mg_ha"].mean() - g["agb_t0_Mg_ha"].mean())
        yrs_m = float(g["years"].mean())
        u_rho0 = T * np.sqrt(se0 ** 2 + se1 ** 2) / abs(dC) if dC != 0 else np.inf
        u_rho = T * np.sqrt(max(se0 ** 2 + se1 ** 2 - 2 * rho * se0 * se1, 0)) / abs(dC) if dC != 0 else np.inf
        idx = g.index.map(lambda i: plots.index.get_loc(i)).to_numpy()
        meas_corr = out["correlated"][idx].mean(0).std() * yrs_m
        meas_ind = out["independent"][idx].mean(0).std() * yrs_m
        rows.append({"block": blk, "n_plots": k, "dagb_Mg_ha_yr": dC / yrs_m, "rho_t0_t1": rho,
                     "U90_rho0_pct": 100 * u_rho0, "U90_rho_pct": 100 * u_rho,
                     "deduct_rho0_pct": 100 * min(1, max(0, u_rho0 - 0.10)), "deduct_rho_pct": 100 * min(1, max(0, u_rho - 0.10)),
                     "meas_U90_correlated_pct": 100 * stats.norm.ppf(0.95) * meas_corr / abs(dC) if dC else np.nan,
                     "meas_U90_independent_pct": 100 * stats.norm.ppf(0.95) * meas_ind / abs(dC) if dC else np.nan})
    return plots, pd.DataFrame(rows), {"hd_a": a, "hd_b": b, "hd_sd": hd_sd, "hd_smear": smear}


def main() -> None:
    OUTD.mkdir(parents=True, exist_ok=True)
    plots, plot_mc, trees = hcsa_monte_carlo()
    plots.to_csv(OUTD / "gt_hcsa_plot_uncertainty.csv", index=False)
    print("WD taxonomic level of HCSA stems:", trees["wd_level"].value_counts(normalize=True).round(3).to_dict())
    print("plot 95% half-width (% of median): median", plots["rel_hw95_pct"].median().round(1),
          "IQR", plots["rel_hw95_pct"].quantile([.25, .75]).round(1).tolist())
    print("MC median / deterministic:", (plots["agb_mc_median"] / plots["agb_det"]).median().round(3),
          "| MC mean / deterministic:", (plots["agb_mc_mean"] / plots["agb_det"]).median().round(3))
    print("Basuki / Chave (sum over plots):", (plots["agb_basuki"].sum() / plots["agb_det"].sum()).round(3))
    print("total C ratio IPCC2006 / IPCC2019:", (plots["c_total_2006_det"].sum() / plots["c_total_2019_det"].sum()).round(3))
    palm = plots[plots["palm_agb"] > 0]
    print(f"palm stems: {int((trees['hcs_class'] == 'OP').sum())} in {len(palm)} plots, "
          f"{(palm['palm_agb'] / palm['agb_det']).round(2).tolist()} of those plots' AGB")
    P = project_level(plots, plot_mc)
    P.to_csv(OUTD / "gt_hcsa_project_uncertainty.csv", index=False)
    print(P.round(1).to_string(index=False))

    sp, sb, hd = safe_monte_carlo()
    sp.to_csv(OUTD / "gt_safe_plot_seq_uncertainty.csv", index=False)
    sb.to_csv(OUTD / "gt_safe_block_seq_uncertainty.csv", index=False)
    print("SAFE H-D:", {k: round(v, 3) for k, v in hd.items()})
    print("SAFE plot dAGB SD (Mg/ha/yr), correlated vs independent tree errors:",
          sp["dagb_sd_correlated"].median().round(2), sp["dagb_sd_independent"].median().round(2))
    print(sb.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
