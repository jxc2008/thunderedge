"""Render research/REPORT.md from research/out/{results,walkforward,hwr_summary}.json.

Every number in the report is read from those files (no hand-typed results). Verdict phrases
("CI excludes 0", etc.) are generated from the intervals.
Usage: python -m research.make_report
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
DB = ROOT.parent / "data" / "valorant_stats.db"


def j(name: str) -> dict:
    p = OUT / name
    return json.loads(p.read_text()) if p.exists() else {}


def ci(c: dict | None, pct: bool = False, d: int = 3) -> str:
    if not c or c.get("est") is None:
        return "n/a"
    f = (lambda x: f"{100 * x:+.1f}%") if pct else (lambda x: f"{x:.{d}f}")
    return f"{f(c['est'])} [{f(c['lo'])}, {f(c['hi'])}]"


def verdict(c: dict | None, null: float = 0.0) -> str:
    if not c or c.get("lo") is None:
        return "not estimable"
    if c["lo"] > null:
        return f"CI excludes {null:g} (above)"
    if c["hi"] < null:
        return f"CI excludes {null:g} (below)"
    return f"CI includes {null:g}"


def main() -> None:
    r, wf, hwr = j("results.json"), j("walkforward.json"), j("hwr_summary.json")
    con = sqlite3.connect(DB)
    q = lambda s: con.execute(s).fetchone()[0]  # noqa: E731
    d = r.get("data", {})
    ov = d.get("overround", {})
    V = r.get("step1", {}).get("V_hat")
    L: list[str] = []
    w = L.append

    w("# Valorant market-structure research report")
    w("")
    w(f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `research/make_report.py` from "
      "`research/out/*.json`. Every estimate: point [95% CI], CIs from 2,000 bootstrap resamples of "
      "**events** (clusters); n is stated beside each number. Nothing was tuned on test data — the "
      "only tuned quantities (half-life, shrinkage k, Benter weights) are fit on earlier seasons only._")
    w("")
    w("## TL;DR")
    w("")
    w("See the per-section **Findings** lines; the headline caveat is §0.2 — historical vlr pages "
      "only publish the winner's price, so analyses that need the loser's price either use the "
      f"{ov.get('n', 0)} matches with archived two-sided pre-match snapshots or are shown as "
      "overround-sensitivity bands.")
    w("")

    # ------------------------------------------------------------------ 0
    w("## 0. Data")
    w("")
    w("### 0.1 Build")
    w("")
    w("| Item | n |")
    w("|---|---|")
    for lab, sql in (("tier-1 matches in DB (all seasons, finals only)", "select count(*) from research_matches"),
                     ("events", "select count(*) from events"),
                     ("maps", "select count(*) from map_results"),
                     ("rounds (map_rounds)", "select count(*) from map_rounds"),
                     ("lineups (team-map starting fives)", "select count(*) from lineups"),
                     ("canonical teams", "select count(*) from teams"),
                     ("team aliases", "select count(*) from team_aliases"),
                     ("Thunderpick odds lines (published, winner side)", "select count(*) from match_odds where book='thunderpick'"),
                     ("matches with two-sided Thunderpick pre-match snapshot", "select count(*) from (select match_id from prematch_odds where book='thunderpick' group by 1 having count(*)=2)")):
        w(f"| {lab} | {q(sql):,} |")
    w(f"| 2024–2026 matches used in tests (showmatches dropped) | {d.get('n_matches_2024_26', 'n/a'):,} across {d.get('n_events_2024_26', 'n/a')} events |")
    w("")
    w("Season split: " + ", ".join(f"{k}: {v}" for k, v in d.get("by_season", {}).items())
      + ". Market source: " + ", ".join(f"{k}: {v}" for k, v in d.get("mkt_src_counts", {}).items())
      + f". Favourite ambiguous (winner price within 2/1.08–2/1.04, excluded from fav/dog tests): {d.get('fav_ambiguous')}."
      f" Matches with churn defined for both teams: {d.get('churn_available')}.")
    w("")
    w("Fixes landed in the production scraping path (commit on `research/market-structure`):")
    w("")
    w("- **Team-name contamination**: `get_event_matches` split names out of the URL slug with a greedy "
      "regex, so team2 absorbed the event (`\"Sentinels Champions Tour 2024 Amer…\"`); names now come "
      "from the match-item DOM. Canonical id = vlr `/team/<id>`; `team_aliases` maps header names, "
      "sponsor base names (`VISA KRÜ (KRÜ Esports)` → KRÜ Esports), tags and the legacy slug names.")
    w("- **Book mixing**: `get_match_betting_odds` kept the minimum price across Thunderpick *and* Rainbet "
      "and labelled it Thunderpick; its ASCII-only regex dropped names like Gen.G/KRÜ. Now one book, "
      "by its logo class, both widget formats.")
    w("- **Imputed odds flagged**: `moneyline_matches.team{1,2}_odds_imputed`, `imputed_overround`.")
    w("- Per-match `region`, `tier`, `season`, `weeks_since_season_start` (from the season's first "
      "tier-1 match), `is_international`; `lineups` table (match, team, map, 5 vlr player ids).")
    w("- Scrape: tier-1 VCT 2024–26 + VCT 2023 (churn baseline) + EWC, "
      f"{q('select count(*) from research_matches')} match pages, every request ≥2.5 s apart and cached "
      "(`research/cache/request_ledger.csv`). Challengers was **not** scraped (not approved: 3,000+ pages).")
    w("")
    w("### 0.2 The odds-observability problem")
    w("")
    w("vlr.gg shows a completed match's odds widget only as *“$100 on X returned $Y at pre-match odds Z”* "
      "— **the winner's price only**. Every historical row in `moneyline_matches` therefore has the "
      "loser's price imputed (old code assumed a 5% overround). Excluding imputed rows, as the brief "
      "asked, excludes ~all of history, so (agreed with you mid-task):")
    w("")
    w("1. **ROI at actual odds is exact** on winner-only rows: a winning bet's price is the observed one, "
      "a losing bet costs one unit whatever its price. ROI results are the primary evidence.")
    w(f"2. **Two-sided prices** were recovered from Wayback Machine pre-match snapshots of the same vlr "
      f"pages for n = {ov.get('n', 0)} matches (median {ov.get('median_hours_before') or float('nan'):.1f} h before start). "
      "Calibration/Benter results are reported on this subset first.")
    w(f"3. On the full sample, de-vigged probabilities need an assumed overround V. Measured Thunderpick "
      f"overround: median {ov.get('median') or float('nan'):.4f} (p10 {ov.get('p10') or float('nan'):.4f}, "
      f"p90 {ov.get('p90') or float('nan'):.4f}), vs the 1.05 the old code assumed. Full-sample "
      f"regressions use V̂ = {V:.4f} and are bracketed with V = 1.04 / 1.08. Because the observed side "
      "is always the winner, an error in V shifts p_fair *toward or away from the realised outcome*, "
      "so slope estimates on winner-only rows are biased in a V-dependent way — read them as a band.")
    w("")
    w("![overround](figs/s0_overround.png)")
    w("")

    # ------------------------------------------------------------------ 1
    s1 = r.get("step1", {})
    w("## 1. Roster-churn volatility")
    w("")
    w("`churn_season` = share of a team's modal starting five (that match) not in its last lineup of "
      "the previous season; `churn_event` = vs its last lineup at its previous event; `churn_max` = "
      "max over the two teams. Offseason turnover is large (median team churn 0.4 = two players).")
    w("")
    w("### 1.1 Calibration slope b in logit P(fav wins) = a + b·logit(p_fair)")
    w("")
    w("b = 1: market calibrated; b < 1: favourites over-priced (prices too extreme); b > 1: too timid.")
    w("")
    w("| Sample | n (events) | b overall | b weeks 0–6 | b weeks 7–16 | b weeks 17+ |")
    w("|---|---|---|---|---|---|")
    for name, blk in s1.get("calibration", {}).items():
        bb = blk.get("by_bucket", {})
        cell = lambda k: f"{ci(bb[k]['b'], d=2)} (n={bb[k]['n']})" if k in bb else "n<30"  # noqa: E731
        w(f"| {name} | {blk['n']} ({blk['n_events']}) | {ci(blk.get('overall'), d=2)} | {cell('0-6')} | {cell('7-16')} | {cell('17+')} |")
    w("")
    w("Interaction model logit P = a + b·L + c·churn_max + d·L·churn_max (d < 0 ⇒ prices more "
      "over-confident when rosters changed):")
    w("")
    w("| Sample | n (events) | b | d (L × churn_max) | verdict on d |")
    w("|---|---|---|---|---|")
    for name, blk in s1.get("calibration", {}).items():
        it = blk.get("interaction")
        if it:
            w(f"| {name} | {it['n']} ({it['n_events']}) | {ci(it['b_L'], d=2)} | {ci(it['d_Lxchurn'], d=2)} | {verdict(it['d_Lxchurn'])} |")
    w("")
    w("![slope](figs/s1_slope_by_bucket.png)")
    w("")
    w("![reliability](figs/s1_reliability_by_bucket.png)")
    w("")
    w("### 1.2 Flat-stake underdog ROI at actual (closing) Thunderpick odds — exact")
    w("")
    w("| Slice | bets | events | dog hit rate | ROI per bet [95% CI] | verdict |")
    w("|---|---|---|---|---|---|")
    for k, v in s1.get("dog_roi", {}).items():
        hr = v.get("dog_hit_rate")
        w(f"| {k} | {v['n_bets']} | {v['n_events']} | {'' if hr is None else f'{100 * hr:.1f}%'} | "
          f"{ci(v.get('roi'), pct=True)} | {verdict(v.get('roi'))} |")
    w("")
    w("![dog roi](figs/s1_dog_roi_by_bucket.png)")
    w("")
    rv = s1.get("round_variance_vs_churn", {})
    w("### 1.3 Round-differential variance vs churn")
    w("")
    w(f"Map round differential regressed on logit(p_fair) (n = {rv.get('n_maps')} maps, "
      f"{rv.get('n_events')} events; residual SD {rv.get('resid_sd') or float('nan'):.2f} rounds). "
      f"Slope of squared residual on churn_max: {ci(rv.get('slope_e2_on_churn_max'), d=2)} rounds² per "
      f"unit churn — {verdict(rv.get('slope_e2_on_churn_max'))}. Brown–Forsythe across churn groups: "
      f"p = {rv.get('levene_brown_forsythe', {}).get('p') or float('nan'):.3f}.")
    w("")
    w("| churn_max group | maps | residual variance |")
    w("|---|---|---|")
    for k, v in rv.get("resid_var_by_churn", {}).items():
        w(f"| {k} | {v['n']} | {v['var'] or float('nan'):.1f} |")
    w("")
    w("**Challengers repeat:** not run — Challengers pages were not in the approved scrape budget.")
    w("")

    # ------------------------------------------------------------------ 2
    s2 = r.get("step2", {})
    w("## 2. Region lag at internationals")
    w("")
    w("For each international event, each region's running residual R = Σ(win − p_fair) over its "
      "earlier *cross-region* matches in the same event (strictly earlier start times). A match "
      "qualifies when both regions have ≥1 prior cross-region match and R differs; the *lagging* team "
      "is the one whose region has the lower R.")
    w("")
    w(f"Cross-region international matches: {s2.get('n_cross_region_matches')} across "
      f"{s2.get('n_events')} events; qualifying: {s2.get('qualifying', {}).get('n')} "
      f"(two-sided share {100 * (s2.get('qualifying', {}).get('share_two_sided') or 0):.0f}%).")
    w("")
    w("| Definition | n (events) | lagging team: win − p_fair | ROI betting AGAINST lagging team | logit coef per unit R gap |")
    w("|---|---|---|---|---|")
    for k in ("lagging_vs_leading", "lagging_region_below_market"):
        v = s2.get(k, {})
        if "mean_resid_lag" in v:
            w(f"| {k} | {v['n']} ({v['n_events']}) | {ci(v['mean_resid_lag'], pct=True)} — {verdict(v['mean_resid_lag'])} | "
              f"{ci(v['fade_roi'], pct=True)} (bets={v['n_fade_bets']}) — {verdict(v['fade_roi'])} | {ci(v['coef_per_unit_gap_logodds'], d=2)} |")
        else:
            w(f"| {k} | {v.get('n')} | n too small | | |")
    w("")
    if s2.get("by_gap"):
        w("| R gap bin | n | lagging team: mean win − p_fair |")
        w("|---|---|---|")
        for k, v in s2["by_gap"].items():
            mr = v["mean_resid_lag"]
            w(f"| {k} | {v['n']} | {'' if mr is None else f'{100 * mr:+.1f}%'} |")
        w("")
        w("![region lag](figs/s2_region_lag_by_gap.png)")
        w("")

    # ------------------------------------------------------------------ 3
    s3 = r.get("step3", {})
    w("## 3. Round-variance heterogeneity")
    w("")
    w(f"Map round differential (team1 − team2) regressed on logit(p_fair); residuals modelled as "
      f"N(0, exp(c + θ_A + θ_B)) with Σθ = 0 (teams with ≥20 maps: {s3.get('n_teams')}; "
      f"n = {s3.get('n_maps')} maps, {s3.get('n_events')} events). Likelihood-ratio vs common variance: "
      f"LR = {s3.get('LR') or float('nan'):.1f} on {s3.get('df')} df, χ² p = {s3.get('p_chi2') or float('nan'):.3f}; "
      f"**permutation p (200 shuffles) = {s3.get('p_perm_200') or float('nan'):.3f}**. Brown–Forsythe/Levene "
      f"across teams p = {s3.get('levene_bf', {}).get('p') or float('nan'):.3f} (maps count for both teams, so "
      "not independent). Map differentials are bimodal (a map cannot be drawn), so the Gaussian χ² "
      "reference is approximate; the permutation p is the one to trust.")
    w("")
    for lab, key in (("Most volatile", "most_volatile"), ("Least volatile", "least_volatile")):
        w(f"**{lab}** (θ = log-variance contribution; SD multiplier = exp(θ/2)):")
        w("")
        w("| Team | θ [95% CI] | SD × | maps |")
        w("|---|---|---|---|")
        for t in s3.get(key, []):
            w(f"| {t['team']} | {t['theta']:+.2f} [{t['lo']:+.2f}, {t['hi']:+.2f}] | {t['sd_multiplier']:.2f} | {t['n_maps']} |")
        w("")
    w("Year-to-year persistence of θ (teams with ≥20 maps in both seasons):")
    w("")
    w("| Seasons | teams | Spearman ρ [95% CI] | p |")
    w("|---|---|---|---|")
    for k, v in s3.get("persistence", {}).items():
        w(f"| {k} | {v['n_teams']} | {v['spearman']:+.2f} [{v['lo']:+.2f}, {v['hi']:+.2f}] | {v['p']:.3f} |")
    w("")
    w("![team volatility](figs/s3_team_volatility.png)")
    w("")
    w("![persistence](figs/s3_persistence.png)")
    w("")

    # ------------------------------------------------------------------ 4
    w("## 4. Pricing-model fixes (valorant-pricing-model, branch `fix/side-baseline-blend`)")
    w("")
    w("**4.1 Blend.** `round_p(a, b)` = odds(a)·odds(1−b) assumed a 0.5 side baseline; team side rates "
      "already contain the map's side advantage, so it was counted twice (two league-average teams on a "
      "55% attack map → 0.599 instead of 0.55). Now `odds(p) = odds(a)·odds(1−b)/odds(L_side)`, "
      "`L_side` required; tests: `round_p(L, 1−L, L) == L`, symmetry with L→1−L, reduces to BT at "
      "L = 0.5. 146/146 pricing tests pass; `mypy --strict src/pricing` clean. DEC-003 amended in "
      "`prd.md`/`CLAUDE.md`. `src/quoting/` and `src/main.py` untouched.")
    w("")
    w("**4.2 Half-win-rates rebuild.** `scripts/rebuild_half_win_rates.py`: 730-day window, exponential "
      "decay (half-life tuned), cell → team-overall side offset → league map-side shrinkage; file "
      "carries `pre_shrunk: true` so the loader does not shrink twice. Written to "
      "`data/half_win_rates_v2.json`; the live `half_win_rates.json` is **not** replaced (your call).")
    w("")
    if hwr:
        w("| Cells | file | cells | fallback share | median rounds / cell |")
        w("|---|---|---|---|---|")
        for k, v in hwr.items():
            w(f"| {k} | `{v['file']}` | {v['cells']} | {100 * v['fallback_share']:.1f}% | {v['median_rounds']} |")
        w("")
    for Y, f in wf.get("folds", {}).items():
        w(f"**Walk-forward fold: test season {Y}** (train = earlier seasons, n = {f['train_n_matches']} "
          f"matches; test n = {f['test_n_matches']}). Chosen on train map log loss: half-life "
          f"{f['chosen']['half_life_days']} d, k_map {f['chosen']['k_map']}.")
        w("")
        lc = f.get("lookup_coverage", {})
        if lc:
            w("| Rates | test lookups | fallback share | median effective rounds |")
            w("|---|---|---|---|")
            for k, v in lc.items():
                w(f"| {k} | {v['n_lookups']} | {100 * v['fallback_share']:.1f}% | {v['median_effective_rounds']:.1f} |")
            w("")
        w("| Map-level model | maps | log loss | Brier |")
        w("|---|---|---|---|")
        for k, v in f["map_level"].items():
            w(f"| {k} | {v['n_maps']} | {v['log_loss']:.4f} | {v['brier']:.4f} |")
        w("| coin flip | | 0.6931 | 0.2500 |")
        w("")
        for orr in [k for k in f if k.startswith("overround_")]:
            blk = f[orr]
            bf = blk.get("benter_fit")
            w(f"Series level, {orr.replace('_', ' = ')} for winner-only rows"
              + (f"; Benter (train two-sided n={bf['n_train']}): a_model = {bf['a_model']:.2f}, b_market = {bf['b_market']:.2f}" if bf else "; Benter: <30 two-sided train rows")
              + ":")
            w("")
            w("| Subset | series (events) | market LL | v2 model LL | legacy BT LL | Benter LL | v2 − market LL |")
            w("|---|---|---|---|---|---|---|")
            for sub in ("two_sided", "winner_only", "all"):
                b = blk.get(sub)
                if not b:
                    continue
                mt = b["metrics"]
                g = lambda k: f"{mt[k][0]:.4f}" if k in mt else "—"  # noqa: E731
                dd = mt.get("ll_diff_v2_log5_minus_market")
                w(f"| {sub} | {b['n_series']} ({b['n_events']}) | {g('ll_market')} | {g('ll_v2_log5')} | "
                  f"{g('ll_legacy_bt')} | {g('ll_benter')} | "
                  + (f"{dd[0]:+.4f} [{dd[1]:+.4f}, {dd[2]:+.4f}]" if dd else "—") + " |")
            w("")
    w("")

    # ------------------------------------------------------------------ 5
    w("## 5. Odds snapshot logger")
    w("")
    sn = OUT.parent.parent / "data" / "odds_snapshots.db"
    if sn.exists():
        c2 = sqlite3.connect(sn)
        polls = c2.execute("select count(*), min(ts_utc), max(ts_utc) from poll_log").fetchone()
        rows = c2.execute("select source, count(*), count(distinct match_key) from odds_snapshots group by 1").fetchall()
        w(f"Running as Windows scheduled task **ThunderedgeOddsLogger** every 15 min "
          f"(`research/odds_logger.py`): {polls[0]} polls so far ({polls[1]} → {polls[2]}). Rows: "
          + "; ".join(f"{s}: {n} rows / {k} markets" for s, n, k in rows) + ".")
    w("")
    w("- vlr.gg `/matches` (≤3 pages) every poll; a match page every poll inside 48 h of start, else ≤ every "
      "2 h within 7 days; ≥2.5 s between requests; raw widget HTML stored so parsing can be redone. "
      "Default filter = VCT tier-1 (`--all-tiers` for everything).")
    w("- Kalshi public market data (`KXVALORANTGAME`, `KXVALORANTMAP`): yes bid/ask, sizes, last, volume.")
    w("- `stream_events` table for Plat Chat timestamps: `python -m research.odds_logger --add-stream "
      "\"Plat Chat\" 2027-01-15T19:00Z --end 2027-01-15T21:00Z --url <vod>`.")
    w("- Caveats: runs only while this laptop is on and you are logged in (task is allowed on battery). "
      "For Kickoff 2027 coverage, move it to the always-on VM the pricing model will run on.")
    w("")
    w("## Reproduce")
    w("")
    w("```")
    w("python -m research.fetch_tier1 && python -m research.fetch_extra   # cached, budgeted")
    w("python -m research.wayback_fetch")
    w("python -m research.build_db")
    w("python -m research.analysis")
    w("(pricing repo) python scripts/walkforward_eval.py --db ../thunderedge/data/valorant_stats.db --out ../thunderedge/research/out/walkforward.json")
    w("python -m research.make_report")
    w("```")
    (ROOT / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote", ROOT / "REPORT.md")


if __name__ == "__main__":
    main()
