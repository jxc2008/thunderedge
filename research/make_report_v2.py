"""Render research/REPORT_v2.md (next phase: line sources, tier-2 estimate, dual-output rating model).

Model numbers come from research/out/rating_eval.json (valorant-pricing-model/scripts/rating_eval.py);
source-survey numbers from research/LINE_SOURCES_SURVEY.md (transcribed below, with request counts).
Usage: python -m research.make_report_v2
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
R = json.loads((ROOT / "out" / "rating_eval.json").read_text())


def ci(c: dict | None, d: int = 2, pct: bool = False, scale: float = 1.0) -> str:
    if not c or c.get("est") is None:
        return "n/a"
    f = (lambda x: f"{100 * x * scale:+.1f}%") if pct else (lambda x: f"{x * scale:.{d}f}")
    return f"{f(c['est'])} [{f(c['lo'])}, {f(c['hi'])}]"


def excl0(c: dict | None) -> str:
    if not c or c.get("lo") is None:
        return "—"
    return "CI excludes 0" if c["lo"] > 0 or c["hi"] < 0 else "CI includes 0"


def head(repo: Path) -> str:
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def main() -> None:
    L: list[str] = []
    w = L.append
    n = R["n"]
    d1, d2, d3, d4, s2 = R["D1_close_error"], R["D2_residuals"], R["D3_outcome"], R["D4_gap"], R["stage2"]
    stable = d1.get("all|stable", {}).get("p_a", {})
    w("# VALORANT research — phase 2 report")
    w("")
    w(f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `research/make_report_v2.py`. Paper only; "
      "no live quoting code touched. CIs: 95%, 2,000 bootstrap resamples of events unless stated; n beside every "
      "number. Model fit on 2024–25 (2023 = burn-in), evaluated walk-forward on 2026 with nothing tuned on 2026._")
    w("")
    w("## Summary")
    w("")
    w("- **A. Line history.**")
    w("  - **Coverage:** none of Kalshi, Polymarket or OddsPapi covers 2023–24.")
    w("  - **Kalshi:** every trade from Sept 2025 (1,783 events, nearly all 2026).")
    w("  - **Polymarket:** every fill from Aug 2025.")
    w("  - **OddsPapi (free key):** Pinnacle tick-level history for 2026 only. Thunderpick history "
      "is locked (HTTP 403), so the Thunderpick-vs-Pinnacle lag could not be measured.")
    w("  - **Proposal:** a 2026 historical stale-line test on Pinnacle + Kalshi (§A.3). It needs a "
      "request budget.")
    w("- **B. Tier-2.**")
    w("  - **Size:** ~8,000–13,000 Challengers match pages for 2023–26.")
    w("  - **Thunderpick share:** unknown. Tier-1 is 82%.")
    w("  - **Next:** a 30-page sample would pin both down. Nothing was scraped; waiting for approval.")
    w(f"- **C/D. Rating model (tier-1 only; tier-2 waits on B).**")
    w(f"  - **(a) close model:** median close error {ci(stable.get('median'), 1)} pp on "
      f"stable-lineup matches (n = {stable.get('median', {}).get('n')}). That **misses** the ~2-pp bar.")
    w(f"  - **Residuals:** close − model residuals are essentially unpredictable from our features "
      f"(out-of-sample R² {ci(d2['oos_r2_linear'], 3)}).")
    w(f"  - **(b) outcome model:** better than the v2 half-win-rate model on point estimate, log loss "
      f"{d3['all']['p_b']:.4f} vs {d3['all']['p_v2']:.4f}, Δ {ci(d3['all']['b_minus_v2'], 4)} (n = {d3['all']['n']}; "
      "the CI only just includes 0).")
    w(f"  - **(b) vs the de-vigged close:** level on the clean two-sided rows, Δ "
      f"{ci(d3['two_sided_V']['b_minus_close'], 4)} (n = {d3['two_sided_V']['n']}).")
    w(f"  - **Benter blend:** adds nothing over the close, Δ {ci(d4['benter_minus_close_ll'], 4)}.")
    w("  - **Where model and market disagree most:** CLV is *negative*, so the market moves away "
      "from the model.")
    w("  - **Verdict:** no edge against the Thunderpick close.")
    w("- **E. Pre-registration.**")
    w("  - **Added:** the stale-line study (§10) and a tier-2 stratum.")
    w(f"  - **Code freeze:** evaluation code committed and hash recorded before any 2027 match "
      f"(thunderedge `{PREREG_T}`, pricing `{PREREG_P}`).")
    w("")

    # ---------------------------------------------------------------- A
    w("## A. Historical line-movement sources (survey only)")
    w("")
    w("Full evidence: `research/LINE_SOURCES_SURVEY.md`. Survey traffic was 79 requests to "
      "Kalshi/Polymarket/docs and 33 to the OddsPapi API (26 billable of the 250/month free quota). "
      "Three 2026 tier-1 matches were sampled on every source: PRX–LEV (Masters London final), C9–EG "
      "(Americas Stage 2) and G2–PRX (Champions).")
    w("")
    w("| Source | Coverage | Earliest | Seasons | Granularity | Pre-match volume (3 samples) | Access / terms |")
    w("|---|---|---|---|---|---|---|")
    w("| Kalshi `KXVALORANTGAME` | 3,567 settled markets / 1,783 events, tier-1 to VCL, GC and third-party | 2025-09-24 (Champions 2025, 8 events) | 2026 continuous (Q1 293, Q2 675, Q3 609, Q4 198 events); none Oct–Dec 2025 | every trade (µs), 1/60/1440-min candles with bid/ask | 73k / 10k / 92k contracts (644 / 157 / 444 trades); 85–98% of volume trades in-play | public, no auth; pre-2026-09-18 data via `/historical/*`; ToS not reviewed |")
    w("| Polymarket | 2,996 closed valorant events (~90% matches) | first match market 2025-08-20 | 2025Q4 228; 2026 Q1–Q4 946/918/605/240 events | every fill (1 s) via Data API v2; 1-min prices | $97k and $291k taker volume in the last 48 h (C9–EG, G2–PRX); moneylines $0.4–1.9M | public; v1 Data API retired; ToS not reviewed |")
    w("| OddsPapi (free key) | Valorant incl. tier-2 Challengers fixtures | fixtures ~2025-07; **odds history Jan 2026+** | 2026 only | every price change (sub-second); Pinnacle median gap 40–137 s | Pinnacle 183 / 91 / 174 pre-match updates, from 17–28 h before; no volumes | 250 billable req/month; history calls free but 5 s cooldown, ≤3 books; **Thunderpick 403 on free plan**; ToS: no redistribution |")
    w("")
    w("### A.1 Polymarket per-trade history")
    w("")
    w("**Retrievable.**")
    w("- **Every fill:** Data API v2 `/v2/trades?condition=<conditionId>`, paged newest-first. It "
      "can't be time-filtered per market, so busy in-play markets need many pages: PRX–LEV's last "
      "5,000 fills were all in-play.")
    w("- **1-minute prices:** CLOB `prices-history` with explicit `startTs`/`endTs`. "
      "`interval=max` returns empty for resolved markets.")
    w("")
    w("### A.2 Thunderpick vs Pinnacle lag")
    w("")
    w("**Not measured.** Pinnacle history is available on the free key, but Thunderpick's returns "
      "`403 RESTRICTED_ACCESS`. The method is written up in the survey (§4) and is ready to run on "
      "~10 fixtures if a plan with Thunderpick is bought. Its price and the start of its "
      "Thunderpick history are unverified.")
    w("")
    w("### A.3 Recommendation and proposed historical stale-line test (needs a request budget)")
    w("")
    w("**Recommendation:**")
    w("1. **Pinnacle via OddsPapi** is the best *reference* line. It is sharp, two-sided and "
      "tick-timestamped, and it fixes the main weakness of this report: vlr only publishes the "
      "winner's close, so the close target here carries overround noise.")
    w("   - ~700 history calls, which are not billable, plus ~20 billable fixture listings.")
    w("   - At the 5 s cooldown that is about 1 h, within the free plan.")
    w("   - The raw data stays out of the public repo (the ToS forbids redistribution).")
    w("2. **Kalshi** is the *tradable* venue with full 2026 trade history and public access. "
      "Polymarket has more volume and is the second tradable venue.")
    w("3. **Thunderpick history** (the book we actually price against) needs a paid OddsPapi plan. "
      "Decide after the Pinnacle study shows whether lines move.")
    w("")
    w("**Stale-line test on 2026 tier-1 (≈650 matches):**")
    w("1. For each completed match M, find the same teams' next match N.")
    w("2. **M's end time:** the settlement or last in-play trade of M's Kalshi market. vlr has no "
      "end times.")
    w("3. **Stale price:** N's de-vigged price at end(M) + {5, 15, 60} min. This is the Pinnacle "
      "price, and the Kalshi bid/ask mid where the spread is ≤ 4¢.")
    w("4. **Signal:** model (a) — the frozen rating engine updated through M — minus the stale price.")
    w("5. **Outcome:** N's close (the last pre-start price) and its result.")
    w("6. **Metrics:**")
    w("   - CLV of a paper bet on the signalled side, overall and by surprise size |y_M − p_b(M)|;")
    w("   - the slope of (close − stale price) on the signal;")
    w("   - how long Pinnacle and Kalshi take to move after end(M).")
    w("7. **Success:** the same bar as prereg §10 — positive CLV that grows with surprise size.")
    w("8. **Request budget:**")
    w("   - OddsPapi: ~720, mostly non-billable.")
    w("   - Kalshi: ~700, one 1-min candle call per event plus listings, at ≤ 1 req/s because one "
      "429 was hit at ~1/s.")
    w("   - Polymarket, if wanted: ~800.")
    w("   - Total ≈ 1.4–2.2k API calls over 2–3 hours.")
    w("")

    # ---------------------------------------------------------------- B
    w("## B. Tier-2 (Challengers) volume — estimate only, nothing scraped")
    w("")
    w("No vlr page was fetched for this, because the research ledger is already at 2,017, over the "
      "~2,000 cap. The cached VCT hub pages list only tier-1 events, so they can't count Challengers. "
      "The estimate below is structural and checked against the line-source survey.")
    w("")
    w("| Input | Value | Basis |")
    w("|---|---|---|")
    w("| Challengers leagues per year (2024–26) | ~20–25 | Americas 4, EMEA ~10, Pacific ~8, China 1–2 (structure, not counted) |")
    w("| Matches per league per year | ~80–150 | 2–3 splits × round robin + playoffs |")
    w("| Tier-2 matches per year | ~1,600–3,750 (≈ 2,500) | product; cross-check: Polymarket listed 663 Challengers/VCL match events created Jan–Apr 20 2026; Kalshi lists 122 VCL North America events in 2026; OddsPapi has 94 Challengers Korea fixtures Jul 2025–Jul 2026 |")
    w("| 2023–26 match pages | **~8,000–13,000** | 4 seasons, + ~2% event/list pages |")
    w("| Share with Thunderpick odds on vlr | **unknown** | tier-1 is 1,594 / 1,951 = 82%; tier-2 is plausibly 30–70% |")
    w("| Fetch time | ~6–9 h of requests at ≥ 2.5 s | throttled to ~1,500 pages/day ⇒ 6–9 days |")
    w("")
    w("**Proposal (waiting for your approval; nothing runs before it):**")
    w("- **Phase 0 — 30 vlr pages.** 10 Challengers event match-lists spread over regions and years, "
      "plus 20 random match pages. This gives real per-event counts and the Thunderpick share, and "
      "turns the range above into a ±15% estimate.")
    w("- **Phase 1 — separate budget, set after Phase 0.** Throttled over several days and cached, "
      "using the same fetcher and ledger. Suggested scope: 2025–26 Challengers in leagues where "
      "Thunderpick prices ≥ 50% of matches (likely ~4–6k pages); 2023–24 only if the §D.5 "
      "ablation needs more history.")
    w("")
    w("## C. Dual-output dynamic rating model")
    w("")
    w("Code is in `valorant-pricing-model`: `src/rating/engine.py`, `src/rating/dp_table.py` and "
      f"`scripts/rating_eval.py` (commit `{PREREG_P[:7]}`). It is not wired into `live_theo` or `src/quoting`.")
    w("")
    w("**Engine** (one shared implementation). Every state is Gaussian, in round-logit units:")
    w("- **Strength:** latent strength per player; team strength = mean of its current five.")
    w("- **Offsets:** region offsets (identified by cross-region maps), a team × map offset, a league "
      "attack offset per map, and a tier offset (inert until tier-2 data exists).")
    w("- **Update:** after every map, a Laplace (Newton) step from the two halves' round counts, "
      "with the round likelihood weighted by κ because rounds within a map are correlated.")
    w("- **Variance:** inflates with time and at season boundaries, and new players start wide. A "
      "new player's prior mean is w × the mean of his known teammates.")
    w("- **Approximation:** marginals are kept independent, Glicko/TrueSkill-style.")
    w("")
    w("**Two outputs.** The market price is never a model input.")
    w("- **(b) true win probability.** Per map, A's attack/defence round logits are d ± δ_map, with d "
      "the strength difference integrated over its uncertainty (5-point Gauss–Hermite). These feed "
      "the **production map DP**, tabulated exactly once over a 61×61 logit grid (max interpolation "
      "error 0.0004 against direct DP calls). Series = composition over the actual veto order.")
    w("  - Engine settings tuned by coordinate descent on **2024–25 map log loss**.")
    w("- **(a) predicted de-vigged close.** A linear head on the logit scale: close ~ 1 + x + "
      "x·lineup_change + x·international, where x is the series logit from the engine run with its "
      "own settings.")
    w("  - Settings and head fit on **2024–25 closes**.")
    w("  - **Close target:** the winner's published Thunderpick close (vlr) de-vigged with the same "
      "match's measured overround, or the season median.")
    w("  - **Caveat:** only the winner's close is published, so the target carries ≈ ±0.25 pp of "
      "outcome-correlated noise.")
    w("")
    w("| Setting | (b) outcome | (a) close |")
    w("|---|---|---|")
    for k in ("kappa", "v0_player", "q_player", "v_offseason", "w_newplayer", "v0_region", "v0_teammap"):
        w(f"| {k} | {R['params_b'][k]:g} | {R['params_a'][k]:g} |")
    b = R["head_a_beta"]
    w(f"| head (a) | — | logit close = {b[0]:+.3f} {b[1]:+.3f}·x {b[2]:+.3f}·x·lineup_change {b[3]:+.3f}·x·intl |")
    w("")
    w(f"2024–25 map log loss for (b) after tuning: {R['map_ll_train_b']:.4f} (coin 0.6931). The "
      "(a) head's x-coefficient below 1 means the close is less extreme than the outcome-tuned ratings.")
    w("")

    # ---------------------------------------------------------------- D
    w("## D. Evaluation — tier-1, walk-forward 2026")
    w("")
    w(f"Test set: {n['test']} 2026 tier-1 series (16 events); {n['test_with_close']} have a "
      f"Thunderpick close; {n['test_two_sided']} also have a two-sided Wayback snapshot (per-match "
      f"overround). Training: 2024–25 ({n['train']} series). **Tier-2 is not reported:** no tier-2 data "
      "(§B).")
    w("")
    w("### D.1 Close error of (a) — |model − de-vigged close|, probability points")
    w("")
    w("| Rows | Lineups | n | (a) median | (a) p90 | (b) median | v2 median |")
    w("|---|---|---|---|---|---|---|")
    for k, v in d1.items():
        rows, split = k.split("|")
        w(f"| {rows} | {split} | {v['p_a']['median']['n']} | {ci(v['p_a']['median'], 1)} | "
          f"{ci(v['p_a']['p90'], 1)} | {ci(v['p_b']['median'], 1)} | {ci(v['p_v2']['median'], 1)} |")
    w("")
    w(f"**Result:** the success bar (median < ~2 pp on stable-lineup tier-1) is **not met**: "
      f"{ci(stable.get('median'), 1)} pp. Model (a) is ~2.5 pp closer to the close than v2, but "
      "still far from replicating it. Lineup-change matches are worse, with a wide CI.")
    w("")
    w("### D.2 Are residuals (close − model (a)) predictable?")
    w("")
    w("- **Method:** training residuals were cross-fitted (5 folds by event). Ridge and LightGBM "
      "(fixed settings) were fit on 2024–25 and scored on 2026.")
    w("- **Features:** churn, lineup change, international, weeks into season, rating uncertainty, "
      "days since last match, recent surprise difference, best-of, and |model logit|.")
    w("")
    w("| Residual model | out-of-sample R² on 2026 (n) | verdict |")
    w("|---|---|---|")
    w(f"| ridge | {ci(d2['oos_r2_linear'], 3)} ({d2['oos_r2_linear']['n']}) | {excl0(d2['oos_r2_linear'])} |")
    w(f"| LightGBM | {ci(d2['oos_r2_lightgbm'], 3)} ({d2['oos_r2_lightgbm']['n']}) | {excl0(d2['oos_r2_lightgbm'])} (overfits) |")
    w("")
    cr = sorted(((k, v) for k, v in d2["corr_test"].items() if v is not None), key=lambda kv: -abs(kv[1]))
    w(f"Residual SD on 2026: {d2['test_resid_sd_logit']:.3f} logit. Largest raw correlations with the "
      "2026 residual: " + ", ".join(f"{k} {v:+.2f}" for k, v in cr[:4]) + ".")
    w("")
    w("**Result:** our pre-match features explain ≤ ~6% of the gap to the close (upper CI bound). The "
      "market's extra information is not in these features. Pinnacle closes (§A.3) would separate "
      "real disagreement from target noise.")
    w("")
    w("### D.3 Outcome log loss, series level (lower is better; coin flip 0.6931)")
    w("")
    w("| Rows | n | (b) | v2 | close | (b) − v2 | (b) − close |")
    w("|---|---|---|---|---|---|---|")
    for k in ("all", "with_close", "two_sided_V"):
        v = d3[k]
        cl = f"{v['close']:.4f}" if "close" in v else "—"
        w(f"| {k} | {v['n']} | {v['p_b']:.4f} | {v['p_v2']:.4f} | {cl} | {ci(v['b_minus_v2'], 4)} | "
          f"{ci(v.get('b_minus_close'), 4)} |")
    mp = d3["map_level"]
    w(f"| map level | {mp['n_maps']} maps | {mp['b']:.4f} | {mp['v2']:.4f} | — | — | — |")
    w("")
    w("- **Close on the `with_close` rows:** de-vigged with the season median overround, so its "
      "log loss is mildly flattered (see REPORT.md §0.2).")
    w("- **`two_sided_V` rows:** use the match's own overround; this is the clean comparison.")
    w("- **(b) vs v2:** (b) is better than v2 by ~0.015 at series level (the CI only just includes 0) "
      "and by 0.007 at map level.")
    w("- **(b) vs the close:** on the clean rows (b) is indistinguishable from the close. On all "
      "rows it trails by 0.008 (CI includes 0).")
    w("")
    w("### D.4 The gap (b − a): Benter blend, ROI and CLV by gap size")
    w("")
    bb = d4["benter_beta"]
    w(f"Benter blend fit on 2024–25 rows with a close (n = {bb['n_train']}): logit p = {bb['model_b']:.2f}·logit(b) + "
      f"{bb['close']:.2f}·logit(close). On 2026, Benter − close log loss = {ci(d4['benter_minus_close_ll'], 4)} "
      f"→ {excl0(d4['benter_minus_close_ll'])}.")
    w("")
    w("Paper bets back the side the gap favours, 1 unit at the actual Thunderpick closing price. P&L "
      "is exact: a win is paid at the published winner price.")
    w("")
    w("CLV uses the two-sided Wayback snapshot (median ~13 h pre-start) as the bet price against the "
      "close. The loser's close is backed out with the match's own overround.")
    w("")
    w("| Gap definition | gap size (abs) | bets | ROI [CI] | CLV bets | mean CLV [CI] |")
    w("|---|---|---|---|---|---|")
    for g, lab in (("b_minus_a", "(b) − (a)"), ("b_minus_close", "(b) − close")):
        for bk, v in d4[g].items():
            w(f"| {lab} | {bk} | {v['n_bets']} | {ci(v.get('roi'), pct=True)} | {v['n_clv']} | "
              f"{ci(v.get('clv'), pct=True)} |")
    w("")
    w("**Result:** no bucket shows positive ROI or CLV.")
    w("- **Where the model disagrees with the market by > 5 pp:** CLV is significantly *negative*. "
      "The price moves further from the model before the start, so the market knows something the "
      "model doesn't.")
    w("- **Two buckets have ROI CIs entirely below 0:** (b)−(a) under 2 pp and (b)−close 2–5 pp. The "
      "side the model prefers loses more than the bookmaker margin alone would cost. That fits a "
      "better-informed market, but with 8 buckets, treat it as indicative.")
    w("")
    w("### D.5 Ablation with tier-2 training data")
    w("")
    w("**Not run.** It needs the tier-2 scrape (§B). The engine already carries a tier offset, so the "
      "ablation is a re-run of `scripts/rating_eval.py` with tier-2 maps added. Keep tier-2 only if "
      "tier-1 close error *and* outcome log loss both improve.")
    w("")
    w("### Optional stage 2 (LightGBM on rating features; fixed settings, same protocol)")
    w("")
    w(f"- Outcome log loss, LightGBM − (b): {ci(s2['outcome_ll_b2_minus_b'], 4)} → no gain.")
    w(f"- Median close error, LightGBM (a): {ci(s2['close_err_median_a2'], 1)} pp vs linear (a) "
      f"{ci(s2['close_err_median_a'], 1)} pp → no gain.")
    w("- Not adopted.")
    w("")

    # ---------------------------------------------------------------- E
    w("## E. Pre-registration updates (`research/PREREG_KICKOFF2027.md`)")
    w("")
    w("1. **§10 stale-line study:**")
    w("   - The odds logger now detects completed matches and snapshots the same teams' upcoming "
      "matches in that poll (`trigger='post_result'`, latency ≤ 15 min). It has an offline test.")
    w("   - Signal = frozen model (a) − de-vigged stale price; ≥ 2 pp → paper bet; CLV against the "
      "close.")
    w("   - Reported overall, by surprise size, and as a slope.")
    w("   - **Success:** positive CLV that grows with surprise size.")
    w("2. **Tier-2 stratum:** Challengers matches in the same window, same rule, reported separately "
      "with no decision. It exists only if the tier-2 scrape is approved.")
    w(f"3. **Code freeze:** evaluation code and frozen model parameters committed, hashes recorded: "
      f"thunderedge `{PREREG_T}`, valorant-pricing-model `{PREREG_P}`.")
    w("   - Smoke-tested on 2026: 49 qualifying matches, the same 49 as the backtest slice. The "
      "pre-match churn proxy agrees with realised-lineup churn on 48/49.")
    w("   - The stale-line path was run end-to-end on synthetic triggers.")
    w("")
    w("## Side findings")
    w("")
    w("- **Production DP, known limitation:** anti-eco rounds 14–15 reuse the round-1 pistol winner. "
      "This is documented in `src/pricing/dp.py` as a Phase-2 follow-up. It affects v2 and (b) equally.")
    w("- **`_within_map_p_a_wins`:** its `starting_side` argument does not drive the round "
      "probabilities (REPORT.md §4.2). Still worth removing.")
    w("")
    w("## Decisions needed")
    w("")
    w("1. **Tier-2 Phase 0:** 30 vlr pages (ledger 2,017 → ~2,047) to measure Challengers volume and "
      "Thunderpick coverage. Phase 1's budget would then be set from those numbers (§B).")
    w("2. **Historical stale-line test (§A.3):** about 720 OddsPapi calls (mostly non-billable; raw "
      "Pinnacle data kept out of the public repo) and about 700 Kalshi calls. Polymarket (+~800) is "
      "optional.")
    w("3. **OddsPapi paid plan:** needed for Thunderpick history and the Thunderpick-vs-Pinnacle lag. "
      "Price and history depth are unverified. My suggestion: decide after the Pinnacle study.")
    w("4. **Still open from last round:**")
    w("   - the pre-registration's ~155–175 vlr pages, plus the 1-page roster-parser check;")
    w("   - logger hosting and in-season cadence. The laptop slept ~10 h on 2026-11-17 and the "
      "logger missed ~40 polls.")
    w("5. **v2 rates swap:**")
    w("   - The shadow window ends ≥ 2026-11-20.")
    w("   - Model (b) is a candidate pre-match input in place of v2, but its gain is not yet "
      "significant. I'd keep both in shadow through Kickoff 2027 rather than swap now.")
    w("")
    w("## Reproduce")
    w("")
    w("```")
    w("(pricing repo) uv sync --group research")
    w("(pricing repo) python scripts/rating_eval.py --db ../thunderedge/data/valorant_stats.db --out ../thunderedge/research/out/rating_eval.json")
    w("python -m research.make_report_v2")
    w("```")
    (ROOT / "REPORT_v2.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote", ROOT / "REPORT_v2.md")


PREREG_T = "da4e5357c89cf8d83d3a907f6362fa95c917685b"
PREREG_P = "5370dafe19433f787fd1fb0ca37529d9078d4930"

if __name__ == "__main__":
    main()
