"""Steps 1-3: roster-churn volatility, region lag at internationals, round-variance heterogeneity.

Writes research/out/results.json and research/figs/*.png. Every estimate carries n and a 95%
CI from a bootstrap that resamples EVENTS (2000 reps). Nothing is tuned: the only free choice,
the overround V used to reconstruct winner-only rows, is fixed to the median measured on
two-sided Wayback snapshots and bracketed with V = 1.04 / 1.08.

Usage: python -m research.analysis
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.api as sm  # noqa: E402
from scipy import optimize, stats  # noqa: E402

from research import features as F  # noqa: E402

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
FIG = ROOT / "figs"
NB = 2000

# chart tokens (dataviz reference palette, light mode)
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "font.size": 9, "axes.titlesize": 10, "legend.frameon": False,
    "lines.linewidth": 2, "savefig.dpi": 160, "savefig.bbox": "tight",
})


def _ci(t):
    est, lo, hi, nb = t
    return {"est": _f(est), "lo": _f(lo), "hi": _f(hi), "n_boot_ok": nb}


def _f(x):
    if isinstance(x, (np.ndarray, list)):
        return [_f(v) for v in x]
    return None if x is None or not np.isfinite(x) else float(x)


# --------------------------------------------------------------------------- step 0 summary
def data_summary(m: pd.DataFrame, ov: pd.DataFrame) -> dict:
    t = m[m.season.isin(F.TEST_SEASONS)]
    return {
        "n_matches_2024_26": int(len(t)),
        "n_events_2024_26": int(t.event_id.nunique()),
        "by_season": t.groupby("season").size().to_dict(),
        "mkt_src_counts": t.mkt_src.value_counts().to_dict(),
        "fav_ambiguous": int(t.fav_ambiguous.sum()),
        "churn_available": int(t.churn_max.notna().sum()),
        "overround": {"n": int(len(ov)), "median": _f(ov.overround.median()),
                      "p10": _f(ov.overround.quantile(.1)), "p90": _f(ov.overround.quantile(.9)),
                      "median_hours_before": _f(ov.hours_before.median())},
    }


# --------------------------------------------------------------------------- step 1
def calib_fit(d: pd.DataFrame, interact: bool = False):
    X = pd.DataFrame({"const": 1.0, "L": F.logit(d.p_fav.values)})
    if interact:
        X["churn"] = d.churn_max.values
        X["Lxchurn"] = X.L * X.churn
    r = sm.GLM(d.y_fav.values, X, family=sm.families.Binomial()).fit()
    return r.params.values


def step1(m: pd.DataFrame, V_hat: float) -> dict:
    res: dict = {"V_hat": V_hat}
    base = m[m.season.isin(F.TEST_SEASONS) & m.p1.notna() & ~m.fav_ambiguous].copy()
    sets = {"two_sided": base[base.mkt_src == "two_sided"]}
    for V in (1.04, V_hat, 1.08):
        mv = F.add_market(m, V)
        mv = mv[mv.season.isin(F.TEST_SEASONS) & mv.p1.notna() & ~mv.fav_ambiguous]
        sets[f"all_V{V:.3f}"] = mv
    res["calibration"] = {}
    for name, d in sets.items():
        block = {"n": int(len(d)), "n_events": int(d.event_id.nunique())}
        if len(d) >= 30:
            block["overall"] = _ci(F.cluster_boot(d, lambda x: calib_fit(x)[1], NB))
            block["overall_a"] = _ci(F.cluster_boot(d, lambda x: calib_fit(x)[0], NB))
        block["by_bucket"] = {}
        for b in ["0-6", "7-16", "17+"]:
            db = d[d.wk_bucket == b]
            if len(db) >= 30:
                block["by_bucket"][b] = {"n": int(len(db)), "n_events": int(db.event_id.nunique()),
                                         "b": _ci(F.cluster_boot(db, lambda x: calib_fit(x)[1], NB))}
        dc = d[d.churn_max.notna()]
        if len(dc) >= 50:
            block["interaction"] = {
                "n": int(len(dc)), "n_events": int(dc.event_id.nunique()),
                "b_L": _ci(F.cluster_boot(dc, lambda x: calib_fit(x, True)[1], NB)),
                "d_Lxchurn": _ci(F.cluster_boot(dc, lambda x: calib_fit(x, True)[3], NB)),
                "churn_max_mean": _f(dc.churn_max.mean()),
                "share_churn_ge_0.6": _f((dc.churn_max >= 0.6).mean())}
        res["calibration"][name] = block

    # reliability per bucket (V_hat full + two-sided overlay)
    full = sets[f"all_V{V_hat:.3f}"]
    bins = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    rel = {}
    fig, axs = plt.subplots(1, 3, figsize=(10, 3.4), sharey=True)
    for ax, b in zip(axs, ["0-6", "7-16", "17+"]):
        rel[b] = {}
        for lab, d, col, mk in (("all (V̂)", full, C1, "o"), ("two-sided", sets["two_sided"], C2, "s")):
            db = d[d.wk_bucket == b]
            cut = pd.cut(db.p_fav, bins)
            g = db.groupby(cut).agg(p=("p_fav", "mean"), y=("y_fav", "mean"), n=("y_fav", "size"))
            g = g[g.n >= 5]
            rel[b][lab] = g.reset_index(drop=True).to_dict("list")
            ax.plot(g.p, g.y, marker=mk, ms=6, color=col, label=f"{lab} (n={len(db)})")
            for _, r in g.iterrows():
                ax.annotate(f"{int(r.n)}", (r.p, r.y), textcoords="offset points", xytext=(4, -10),
                            fontsize=7, color=INK2)
        ax.plot([.5, 1], [.5, 1], color=INK2, lw=1, ls="--")
        ax.set_title(f"weeks {b}")
        ax.set_xlabel("de-vigged P(fav)")
        ax.legend(loc="upper left", fontsize=7)
    axs[0].set_ylabel("observed fav win rate")
    fig.suptitle("Reliability by weeks since season start (bin labels = n)", fontsize=10, color=INK)
    fig.savefig(FIG / "s1_reliability_by_bucket.png")
    plt.close(fig)
    res["reliability"] = rel

    # dog ROI by bucket, exact at actual (closing) odds
    roi = {}
    d = full.copy()
    d["dog_pnl"] = F.bet_pnl(d, ~d.fav_is_1)
    d = d[d.dog_pnl.notna()]
    for b in ["all", "0-6", "7-16", "17+"]:
        db = d if b == "all" else d[d.wk_bucket == b]
        roi[b] = {"n_bets": int(len(db)), "n_events": int(db.event_id.nunique()),
                  "dog_hit_rate": _f((db.dog_pnl > 0).mean()),
                  "roi": _ci(F.cluster_boot(db, lambda x: x.dog_pnl.mean(), NB))}
    dc = d[d.churn_max.notna()]
    # offseason turnover is high (median team churn 0.4 = two players), so groups are
    # <=1 change / exactly 2 / >=3 on the more-changed side
    for lab, mask in (("churn_max<=0.2", dc.churn_max <= .2), ("churn_max=0.4", np.isclose(dc.churn_max, .4)),
                      ("churn_max>=0.6", dc.churn_max >= .6)):
        db = dc[mask]
        roi[lab] = {"n_bets": int(len(db)), "n_events": int(db.event_id.nunique()),
                    "roi": _ci(F.cluster_boot(db, lambda x: x.dog_pnl.mean(), NB)) if len(db) >= 20 else None}
    for b in ["0-6"]:
        db = dc[(dc.wk_bucket == b) & (dc.churn_max >= .6)]
        roi[f"{b} & churn_max>=0.6"] = {"n_bets": int(len(db)), "n_events": int(db.event_id.nunique()),
                                        "roi": _ci(F.cluster_boot(db, lambda x: x.dog_pnl.mean(), NB)) if len(db) >= 20 else None}
    res["dog_roi"] = roi
    fig, ax = plt.subplots(figsize=(6, 3.2))
    labs = ["all", "0-6", "7-16", "17+"]
    est = [roi[k]["roi"]["est"] for k in labs]
    lo = [roi[k]["roi"]["est"] - roi[k]["roi"]["lo"] for k in labs]
    hi = [roi[k]["roi"]["hi"] - roi[k]["roi"]["est"] for k in labs]
    ax.bar(range(4), est, color=C1, width=0.55)
    ax.errorbar(range(4), est, yerr=[lo, hi], fmt="none", ecolor=INK2, capsize=4, lw=1)
    ax.axhline(0, color=INK2, lw=1)
    ax.set_xticks(range(4), [f"{k}\nn={roi[k]['n_bets']}" for k in labs])
    ax.set_ylabel("flat-stake ROI per bet")
    ax.set_title("Underdog ROI at Thunderpick closing odds, by weeks since season start (95% CI)")
    fig.savefig(FIG / "s1_dog_roi_by_bucket.png")
    plt.close(fig)

    # b by bucket chart (two-sided primary + V band)
    fig, ax = plt.subplots(figsize=(6, 3.2))
    for j, (name, col, lab) in enumerate((("two_sided", C2, "two-sided"), (f"all_V{V_hat:.3f}", C1, "all, V̂"),
                                          ("all_V1.040", C3, "all, V=1.04"))):
        bb = res["calibration"][name]["by_bucket"]
        xs = [i + (j - 1) * 0.18 for i, b in enumerate(["0-6", "7-16", "17+"]) if b in bb]
        ks = [b for b in ["0-6", "7-16", "17+"] if b in bb]
        e = [bb[k]["b"]["est"] for k in ks]
        ax.errorbar(xs, e, yerr=[[x - bb[k]["b"]["lo"] for x, k in zip(e, ks)],
                                 [bb[k]["b"]["hi"] - x for x, k in zip(e, ks)]],
                    fmt="o", ms=6, color=col, capsize=3, lw=1.2, label=lab)
    ax.axhline(1, color=INK2, lw=1, ls="--")
    ax.set_xticks(range(3), ["weeks 0-6", "weeks 7-16", "weeks 17+"])
    ax.set_ylabel("calibration slope b")
    ax.set_title("Market calibration slope by season phase (b<1: favourites over-priced)")
    ax.legend(fontsize=7)
    fig.savefig(FIG / "s1_slope_by_bucket.png")
    plt.close(fig)
    return res


def step1_round_var(V_hat: float) -> dict:
    mp = F.maps_frame(overround=V_hat)
    mp = mp[mp.season.isin(F.TEST_SEASONS) & mp.p1.notna() & mp.churn_max.notna() & ~mp.fav_ambiguous]
    mp["L1"] = F.logit(mp.p1.values)
    X = sm.add_constant(mp[["L1"]])
    mp["e"] = sm.OLS(mp.rd1, X).fit().resid
    mp["e2"] = mp.e ** 2

    def slope(x):
        return sm.OLS(x.e2, sm.add_constant(x[["churn_max"]])).fit().params["churn_max"]
    terc = [mp.e[mp.churn_max <= .2], mp.e[np.isclose(mp.churn_max, .4)], mp.e[mp.churn_max >= .6]]
    lev = stats.levene(*[t for t in terc if len(t) > 5], center="median")
    return {"n_maps": int(len(mp)), "n_events": int(mp.event_id.nunique()),
            "resid_sd": _f(mp.e.std()),
            "slope_e2_on_churn_max": _ci(F.cluster_boot(mp, slope, NB)),
            "resid_var_by_churn": {k: {"n": int(len(t)), "var": _f(t.var())}
                                   for k, t in zip(["<=0.2", "0.4", ">=0.6"], terc)},
            "levene_brown_forsythe": {"stat": _f(lev.statistic), "p": _f(lev.pvalue)}}


# --------------------------------------------------------------------------- step 2
def step2(m: pd.DataFrame, V_hat: float) -> dict:
    d = m[(m.is_international == 1) & m.season.isin(F.TEST_SEASONS) & (m.home1 != m.home2)
          & m.p1.notna()].sort_values("date_utc").copy()
    rows = []
    for ev, g in d.groupby("event_id"):
        hist = []  # (date, region, resid)
        for r in g.itertuples():
            prior = [h for h in hist if h[0] < r.date_utc]
            R = {}
            N = {}
            for _, reg, e in prior:
                R[reg] = R.get(reg, 0) + e
                N[reg] = N.get(reg, 0) + 1
            rows.append({"match_id": r.match_id, "event_id": ev, "y1": r.y1, "p1": r.p1,
                         "winner_odds": r.winner_odds, "mkt_src": r.mkt_src,
                         "R1": R.get(r.home1, 0.0), "R2": R.get(r.home2, 0.0),
                         "N1": N.get(r.home1, 0), "N2": N.get(r.home2, 0),
                         "home1": r.home1, "home2": r.home2})
            hist.append((r.date_utc, r.home1, r.y1 - r.p1))
            hist.append((r.date_utc, r.home2, (1 - r.y1) - (1 - r.p1)))
    x = pd.DataFrame(rows)
    out = {"n_cross_region_matches": int(len(x)), "n_events": int(x.event_id.nunique()) if len(x) else 0}
    q = x[(x.N1 > 0) & (x.N2 > 0) & (x.R1 != x.R2)].copy()
    # orient on the lagging team (lower region residual so far)
    lag1 = q.R1 < q.R2
    q["y_lag"] = np.where(lag1, q.y1, 1 - q.y1)
    q["p_lag"] = np.where(lag1, q.p1, 1 - q.p1)
    q["gap"] = np.abs(q.R1 - q.R2)
    q["resid"] = q.y_lag - q.p_lag
    q["fade_pnl"] = F.bet_pnl(q, pd.Series(~lag1.values, index=q.index))  # bet on the leader
    strict = q[np.where(lag1, q.R1 < 0, q.R2 < 0)]  # lagging region actually below market
    out["qualifying"] = {"n": int(len(q)), "n_events": int(q.event_id.nunique()),
                         "share_two_sided": _f((q.mkt_src == "two_sided").mean())}

    def logit_gap(z):
        X = pd.DataFrame({"gap": -(z.R1 - z.R2).values})  # >0 when team1 lags
        off = F.logit(z.p1.values)
        r = sm.GLM(z.y1.values, X, family=sm.families.Binomial(), offset=off).fit()
        return r.params["gap"]
    for lab, z in (("lagging_vs_leading", q), ("lagging_region_below_market", strict)):
        if len(z) < 15:
            out[lab] = {"n": int(len(z))}
            continue
        out[lab] = {
            "n": int(len(z)), "n_events": int(z.event_id.nunique()),
            "mean_resid_lag": _ci(F.cluster_boot(z, lambda w: w.resid.mean(), NB)),
            "fade_roi": _ci(F.cluster_boot(z[z.fade_pnl.notna()], lambda w: w.fade_pnl.mean(), NB)),
            "n_fade_bets": int(z.fade_pnl.notna().sum()),
            "coef_per_unit_gap_logodds": _ci(F.cluster_boot(z, logit_gap, NB)),
        }
    if len(q) >= 15:
        bins = pd.cut(q.gap, [0, 0.5, 1.0, 10])
        g = q.groupby(bins).agg(resid=("resid", "mean"), n=("resid", "size")).reset_index()
        out["by_gap"] = {str(k): {"n": int(n), "mean_resid_lag": _f(r)} for k, r, n in g.values}
        fig, ax = plt.subplots(figsize=(5.5, 3))
        ax.bar(range(len(g)), g.resid, color=C1, width=0.55)
        ax.axhline(0, color=INK2, lw=1)
        ax.set_xticks(range(len(g)), [f"{k}\nn={n}" for k, n in zip(g.gap.astype(str), g.n)])
        ax.set_xlabel("region residual gap so far in event (wins − market-expected wins)")
        ax.set_ylabel("lagging team: win − P(fair)")
        ax.set_title("Same-event region lag: lagging-region team vs market")
        fig.savefig(FIG / "s2_region_lag_by_gap.png")
        plt.close(fig)
    return out


# --------------------------------------------------------------------------- step 3
def _het_fit(e: np.ndarray, A: np.ndarray, B: np.ndarray, T: int):
    """Gaussian MLE with log sigma^2_i = c + th[A_i] + th[B_i], sum(th)=0. Returns (llf, c, th)."""
    e2 = e ** 2

    def nll(par):
        c, th = par[0], np.append(par[1:], -par[1:].sum())
        ls = c + th[A] + th[B]
        g = 0.5 * (1 - e2 / np.exp(ls))  # d nll / d ls_i
        G = np.bincount(A, weights=g, minlength=T) + np.bincount(B, weights=g, minlength=T)
        grad = np.concatenate([[g.sum()], G[:-1] - G[-1]])
        return 0.5 * np.sum(ls + e2 / np.exp(ls)), grad
    x0 = np.zeros(T)
    x0[0] = np.log(e.var())
    r = optimize.minimize(nll, x0, jac=True, method="L-BFGS-B")
    th = np.append(r.x[1:], -r.x[1:].sum())
    return -r.fun - 0.5 * len(e) * np.log(2 * np.pi), r.x[0], th


def step3(V_hat: float) -> dict:
    mp = F.maps_frame(overround=V_hat)
    mp = mp[mp.season.isin(F.TEST_SEASONS) & mp.p1.notna() & ~mp.fav_ambiguous].copy()
    mp["L1"] = F.logit(mp.p1.values)
    mp["e"] = sm.OLS(mp.rd1, sm.add_constant(mp[["L1"]])).fit().resid
    cnt = pd.concat([mp.team1_id, mp.team2_id]).value_counts()
    keep = set(cnt[cnt >= 20].index)
    mp = mp[mp.team1_id.isin(keep) & mp.team2_id.isin(keep)].copy()
    teams = sorted(keep)
    ti = {t: i for i, t in enumerate(teams)}
    A = mp.team1_id.map(ti).values
    B = mp.team2_id.map(ti).values
    e = mp.e.values
    T = len(teams)
    ll1, c, th = _het_fit(e, A, B, T)
    ll0 = -0.5 * len(e) * (np.log(e.var()) + 1 + np.log(2 * np.pi))
    LR = 2 * (ll1 - ll0)
    p_chi2 = 1 - stats.chi2.cdf(LR, T - 1)
    rng = np.random.default_rng(1)
    perm = []
    for _ in range(200):
        ep = rng.permutation(e)
        perm.append(2 * (_het_fit(ep, A, B, T)[0] - ll0))
    p_perm = (1 + np.sum(np.array(perm) >= LR)) / (1 + len(perm))
    # Brown-Forsythe Levene on per-team groups (each map counted for both teams -> not independent)
    groups = [np.abs(np.concatenate([e[A == i], -e[B == i]])) for i in range(T)]
    lev = stats.levene(*[np.concatenate([e[A == i], -e[B == i]]) for i in range(T)], center="median")
    names = dict(F._con().execute("SELECT team_id, COALESCE(tag,name) FROM teams").fetchall())
    # team theta CIs: bootstrap events
    ev = mp.event_id.values
    uev = np.unique(ev)
    boots = []
    for _ in range(300):
        pick = np.concatenate([np.nonzero(ev == k)[0] for k in rng.choice(uev, len(uev))])
        boots.append(_het_fit(e[pick], A[pick], B[pick], T)[2])
    boots = np.array(boots)
    tab = pd.DataFrame({"team_id": teams, "team": [names.get(t, t) for t in teams], "theta": th,
                        "lo": np.percentile(boots, 2.5, axis=0), "hi": np.percentile(boots, 97.5, axis=0),
                        "n_maps": [int(cnt[t]) for t in teams],
                        "sd_multiplier": np.exp(th / 2)}).sort_values("theta")
    fig, ax = plt.subplots(figsize=(6, max(4, 0.17 * T)))
    ax.errorbar(tab.theta, range(T), xerr=[tab.theta - tab.lo, tab.hi - tab.theta], fmt="o", ms=5,
                color=C1, ecolor=INK2, capsize=2, lw=1)
    ax.axvline(0, color=INK2, lw=1)
    ax.set_yticks(range(T), [f"{a} ({n})" for a, n in zip(tab.team, tab.n_maps)], fontsize=7)
    ax.set_xlabel("θ: log variance contribution of team (0 = average)")
    ax.set_title("Round-differential residual volatility by team (maps in brackets; 95% CI)")
    fig.savefig(FIG / "s3_team_volatility.png")
    plt.close(fig)

    # persistence: theta per season, teams with >= 20 maps in both seasons
    pers = {}
    by_season = {}
    for s in F.TEST_SEASONS:
        ms = mp[mp.season == s]
        c2 = pd.concat([ms.team1_id, ms.team2_id]).value_counts()
        ks = sorted(set(c2[c2 >= 20].index))
        msk = ms[ms.team1_id.isin(ks) & ms.team2_id.isin(ks)]
        if len(ks) < 5:
            continue
        tj = {t: i for i, t in enumerate(ks)}
        _, _, ths = _het_fit(msk.e.values, msk.team1_id.map(tj).values, msk.team2_id.map(tj).values, len(ks))
        by_season[s] = dict(zip(ks, ths))
    pairs = [(a, b) for a, b in zip(F.TEST_SEASONS, F.TEST_SEASONS[1:]) if a in by_season and b in by_season]
    fig, ax = plt.subplots(figsize=(4.5, 3.6))
    for (a, b), col in zip(pairs, (C1, C2)):
        common = sorted(set(by_season[a]) & set(by_season[b]))
        if len(common) < 5:
            continue
        xa = np.array([by_season[a][t] for t in common])
        xb = np.array([by_season[b][t] for t in common])
        rho, p = stats.spearmanr(xa, xb)
        bs = []
        for _ in range(NB):
            i = rng.integers(0, len(common), len(common))
            bs.append(stats.spearmanr(xa[i], xb[i])[0])
        pers[f"{a}->{b}"] = {"n_teams": len(common), "spearman": _f(rho), "p": _f(p),
                             "lo": _f(np.nanpercentile(bs, 2.5)), "hi": _f(np.nanpercentile(bs, 97.5))}
        ax.scatter(xa, xb, s=30, color=col, edgecolor=SURF, lw=1.5, label=f"{a}→{b} ρ={rho:.2f} (n={len(common)})")
    ax.axhline(0, color=GRID)
    ax.axvline(0, color=GRID)
    ax.set_xlabel("θ in season t")
    ax.set_ylabel("θ in season t+1")
    ax.set_title("Does team volatility persist?")
    ax.legend(fontsize=7)
    fig.savefig(FIG / "s3_persistence.png")
    plt.close(fig)
    top = tab.tail(5)[::-1]
    bot = tab.head(5)
    return {"n_maps": int(len(mp)), "n_teams": T, "n_events": int(mp.event_id.nunique()),
            "resid_sd": _f(e.std()), "LR": _f(LR), "df": T - 1, "p_chi2": _f(p_chi2),
            "p_perm_200": _f(p_perm), "levene_bf": {"stat": _f(lev.statistic), "p": _f(lev.pvalue),
                                                    "caveat": "maps counted for both teams"},
            "most_volatile": top[["team", "theta", "lo", "hi", "sd_multiplier", "n_maps"]].to_dict("records"),
            "least_volatile": bot[["team", "theta", "lo", "hi", "sd_multiplier", "n_maps"]].to_dict("records"),
            "persistence": pers, "_unused": len(groups)}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    FIG.mkdir(exist_ok=True)
    ov = F.overround_table()
    V_hat = float(ov.overround.median()) if len(ov) >= 20 else 1.06
    m = F.matches(overround=V_hat)
    res = {"data": data_summary(m, ov)}
    if len(ov):
        fig, ax = plt.subplots(figsize=(5.5, 3))
        ax.hist(ov.overround, bins=30, color=C1, edgecolor=SURF, lw=1)
        ax.axvline(1.05, color=C2, lw=2, label="assumed in populate_moneyline (1.05)")
        ax.axvline(V_hat, color=INK, lw=1.5, ls="--", label=f"median measured ({V_hat:.3f})")
        ax.set_xlabel("Thunderpick overround (1/o1 + 1/o2)")
        ax.set_ylabel("matches")
        ax.set_title(f"Measured Thunderpick overround, Wayback pre-match snapshots (n={len(ov)})")
        ax.legend(fontsize=7)
        fig.savefig(FIG / "s0_overround.png")
        plt.close(fig)
    print("step1", flush=True)
    res["step1"] = step1(m, V_hat)
    res["step1"]["round_variance_vs_churn"] = step1_round_var(V_hat)
    print("step2", flush=True)
    res["step2"] = step2(m, V_hat)
    print("step3", flush=True)
    res["step3"] = step3(V_hat)
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=_f))
    print("wrote", OUT / "results.json")


if __name__ == "__main__":
    main()
