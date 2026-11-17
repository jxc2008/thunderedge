# VALORANT research — phase 2 report

_Generated 2026-11-17 18:56 UTC by `research/make_report_v2.py`. Paper only; no live quoting code touched. CIs: 95%, 2,000 bootstrap resamples of events unless stated; n beside every number. Model fit on 2024–25 (2023 = burn-in), evaluated walk-forward on 2026 with nothing tuned on 2026._

## Summary

- **A. Line history.**
  - **Coverage:** none of Kalshi, Polymarket or OddsPapi covers 2023–24.
  - **Kalshi:** every trade from Sept 2025 (1,783 events, nearly all 2026).
  - **Polymarket:** every fill from Aug 2025.
  - **OddsPapi (free key):** Pinnacle tick-level history for 2026 only. Thunderpick history is locked (HTTP 403), so the Thunderpick-vs-Pinnacle lag could not be measured.
  - **Proposal:** a 2026 historical stale-line test on Pinnacle + Kalshi (§A.3). It needs a request budget.
- **B. Tier-2.**
  - **Size:** ~8,000–13,000 Challengers match pages for 2023–26.
  - **Thunderpick share:** unknown. Tier-1 is 82%.
  - **Next:** a 30-page sample would pin both down. Nothing was scraped; waiting for approval.
- **C/D. Rating model (tier-1 only; tier-2 waits on B).**
  - **(a) close model:** median close error 4.5 [3.7, 5.5] pp on stable-lineup matches (n = 458). That **misses** the ~2-pp bar.
  - **Residuals:** close − model residuals are essentially unpredictable from our features (out-of-sample R² 0.024 [-0.021, 0.062]).
  - **(b) outcome model:** better than the v2 half-win-rate model on point estimate, log loss 0.6559 vs 0.6706, Δ -0.0147 [-0.0367, 0.0028] (n = 650; the CI only just includes 0).
  - **(b) vs the de-vigged close:** level on the clean two-sided rows, Δ -0.0042 [-0.0309, 0.0258] (n = 94).
  - **Benter blend:** adds nothing over the close, Δ 0.0006 [-0.0049, 0.0062].
  - **Where model and market disagree most:** CLV is *negative*, so the market moves away from the model.
  - **Verdict:** no edge against the Thunderpick close.
- **E. Pre-registration.**
  - **Added:** the stale-line study (§10) and a tier-2 stratum.
  - **Code freeze:** evaluation code committed and hash recorded before any 2027 match (thunderedge `da4e5357c89cf8d83d3a907f6362fa95c917685b`, pricing `5370dafe19433f787fd1fb0ca37529d9078d4930`).

## A. Historical line-movement sources (survey only)

Full evidence: `research/LINE_SOURCES_SURVEY.md`. Survey traffic was 79 requests to Kalshi/Polymarket/docs and 33 to the OddsPapi API (26 billable of the 250/month free quota). Three 2026 tier-1 matches were sampled on every source: PRX–LEV (Masters London final), C9–EG (Americas Stage 2) and G2–PRX (Champions).

| Source | Coverage | Earliest | Seasons | Granularity | Pre-match volume (3 samples) | Access / terms |
|---|---|---|---|---|---|---|
| Kalshi `KXVALORANTGAME` | 3,567 settled markets / 1,783 events, tier-1 to VCL, GC and third-party | 2025-09-24 (Champions 2025, 8 events) | 2026 continuous (Q1 293, Q2 675, Q3 609, Q4 198 events); none Oct–Dec 2025 | every trade (µs), 1/60/1440-min candles with bid/ask | 73k / 10k / 92k contracts (644 / 157 / 444 trades); 85–98% of volume trades in-play | public, no auth; pre-2026-09-18 data via `/historical/*`; ToS not reviewed |
| Polymarket | 2,996 closed valorant events (~90% matches) | first match market 2025-08-20 | 2025Q4 228; 2026 Q1–Q4 946/918/605/240 events | every fill (1 s) via Data API v2; 1-min prices | $97k and $291k taker volume in the last 48 h (C9–EG, G2–PRX); moneylines $0.4–1.9M | public; v1 Data API retired; ToS not reviewed |
| OddsPapi (free key) | Valorant incl. tier-2 Challengers fixtures | fixtures ~2025-07; **odds history Jan 2026+** | 2026 only | every price change (sub-second); Pinnacle median gap 40–137 s | Pinnacle 183 / 91 / 174 pre-match updates, from 17–28 h before; no volumes | 250 billable req/month; history calls free but 5 s cooldown, ≤3 books; **Thunderpick 403 on free plan**; ToS: no redistribution |

### A.1 Polymarket per-trade history

**Retrievable.**
- **Every fill:** Data API v2 `/v2/trades?condition=<conditionId>`, paged newest-first. It can't be time-filtered per market, so busy in-play markets need many pages: PRX–LEV's last 5,000 fills were all in-play.
- **1-minute prices:** CLOB `prices-history` with explicit `startTs`/`endTs`. `interval=max` returns empty for resolved markets.

### A.2 Thunderpick vs Pinnacle lag

**Not measured.** Pinnacle history is available on the free key, but Thunderpick's returns `403 RESTRICTED_ACCESS`. The method is written up in the survey (§4) and is ready to run on ~10 fixtures if a plan with Thunderpick is bought. Its price and the start of its Thunderpick history are unverified.

### A.3 Recommendation and proposed historical stale-line test (needs a request budget)

**Recommendation:**
1. **Pinnacle via OddsPapi** is the best *reference* line. It is sharp, two-sided and tick-timestamped, and it fixes the main weakness of this report: vlr only publishes the winner's close, so the close target here carries overround noise.
   - ~700 history calls, which are not billable, plus ~20 billable fixture listings.
   - At the 5 s cooldown that is about 1 h, within the free plan.
   - The raw data stays out of the public repo (the ToS forbids redistribution).
2. **Kalshi** is the *tradable* venue with full 2026 trade history and public access. Polymarket has more volume and is the second tradable venue.
3. **Thunderpick history** (the book we actually price against) needs a paid OddsPapi plan. Decide after the Pinnacle study shows whether lines move.

**Stale-line test on 2026 tier-1 (≈650 matches):**
1. For each completed match M, find the same teams' next match N.
2. **M's end time:** the settlement or last in-play trade of M's Kalshi market. vlr has no end times.
3. **Stale price:** N's de-vigged price at end(M) + {5, 15, 60} min. This is the Pinnacle price, and the Kalshi bid/ask mid where the spread is ≤ 4¢.
4. **Signal:** model (a) — the frozen rating engine updated through M — minus the stale price.
5. **Outcome:** N's close (the last pre-start price) and its result.
6. **Metrics:**
   - CLV of a paper bet on the signalled side, overall and by surprise size |y_M − p_b(M)|;
   - the slope of (close − stale price) on the signal;
   - how long Pinnacle and Kalshi take to move after end(M).
7. **Success:** the same bar as prereg §10 — positive CLV that grows with surprise size.
8. **Request budget:**
   - OddsPapi: ~720, mostly non-billable.
   - Kalshi: ~700, one 1-min candle call per event plus listings, at ≤ 1 req/s because one 429 was hit at ~1/s.
   - Polymarket, if wanted: ~800.
   - Total ≈ 1.4–2.2k API calls over 2–3 hours.

## B. Tier-2 (Challengers) volume — estimate only, nothing scraped

No vlr page was fetched for this, because the research ledger is already at 2,017, over the ~2,000 cap. The cached VCT hub pages list only tier-1 events, so they can't count Challengers. The estimate below is structural and checked against the line-source survey.

| Input | Value | Basis |
|---|---|---|
| Challengers leagues per year (2024–26) | ~20–25 | Americas 4, EMEA ~10, Pacific ~8, China 1–2 (structure, not counted) |
| Matches per league per year | ~80–150 | 2–3 splits × round robin + playoffs |
| Tier-2 matches per year | ~1,600–3,750 (≈ 2,500) | product; cross-check: Polymarket listed 663 Challengers/VCL match events created Jan–Apr 20 2026; Kalshi lists 122 VCL North America events in 2026; OddsPapi has 94 Challengers Korea fixtures Jul 2025–Jul 2026 |
| 2023–26 match pages | **~8,000–13,000** | 4 seasons, + ~2% event/list pages |
| Share with Thunderpick odds on vlr | **unknown** | tier-1 is 1,594 / 1,951 = 82%; tier-2 is plausibly 30–70% |
| Fetch time | ~6–9 h of requests at ≥ 2.5 s | throttled to ~1,500 pages/day ⇒ 6–9 days |

**Proposal (waiting for your approval; nothing runs before it):**
- **Phase 0 — 30 vlr pages.** 10 Challengers event match-lists spread over regions and years, plus 20 random match pages. This gives real per-event counts and the Thunderpick share, and turns the range above into a ±15% estimate.
- **Phase 1 — separate budget, set after Phase 0.** Throttled over several days and cached, using the same fetcher and ledger. Suggested scope: 2025–26 Challengers in leagues where Thunderpick prices ≥ 50% of matches (likely ~4–6k pages); 2023–24 only if the §D.5 ablation needs more history.

## C. Dual-output dynamic rating model

Code is in `valorant-pricing-model`: `src/rating/engine.py`, `src/rating/dp_table.py` and `scripts/rating_eval.py` (commit `5370daf`). It is not wired into `live_theo` or `src/quoting`.

**Engine** (one shared implementation). Every state is Gaussian, in round-logit units:
- **Strength:** latent strength per player; team strength = mean of its current five.
- **Offsets:** region offsets (identified by cross-region maps), a team × map offset, a league attack offset per map, and a tier offset (inert until tier-2 data exists).
- **Update:** after every map, a Laplace (Newton) step from the two halves' round counts, with the round likelihood weighted by κ because rounds within a map are correlated.
- **Variance:** inflates with time and at season boundaries, and new players start wide. A new player's prior mean is w × the mean of his known teammates.
- **Approximation:** marginals are kept independent, Glicko/TrueSkill-style.

**Two outputs.** The market price is never a model input.
- **(b) true win probability.** Per map, A's attack/defence round logits are d ± δ_map, with d the strength difference integrated over its uncertainty (5-point Gauss–Hermite). These feed the **production map DP**, tabulated exactly once over a 61×61 logit grid (max interpolation error 0.0004 against direct DP calls). Series = composition over the actual veto order.
  - Engine settings tuned by coordinate descent on **2024–25 map log loss**.
- **(a) predicted de-vigged close.** A linear head on the logit scale: close ~ 1 + x + x·lineup_change + x·international, where x is the series logit from the engine run with its own settings.
  - Settings and head fit on **2024–25 closes**.
  - **Close target:** the winner's published Thunderpick close (vlr) de-vigged with the same match's measured overround, or the season median.
  - **Caveat:** only the winner's close is published, so the target carries ≈ ±0.25 pp of outcome-correlated noise.

| Setting | (b) outcome | (a) close |
|---|---|---|
| kappa | 0.3 | 0.8 |
| v0_player | 0.1 | 0.1 |
| q_player | 0.0008 | 0 |
| v_offseason | 0.02 | 0.03 |
| w_newplayer | 0.5 | 0.5 |
| v0_region | 0.005 | 0.1 |
| v0_teammap | 0.003 | 0 |
| head (a) | — | logit close = +0.088 +0.794·x +0.008·x·lineup_change -0.083·x·intl |

2024–25 map log loss for (b) after tuning: 0.6727 (coin 0.6931). The (a) head's x-coefficient below 1 means the close is less extreme than the outcome-tuned ratings.

## D. Evaluation — tier-1, walk-forward 2026

Test set: 650 2026 tier-1 series (16 events); 555 have a Thunderpick close; 94 also have a two-sided Wayback snapshot (per-match overround). Training: 2024–25 (951 series). **Tier-2 is not reported:** no tier-2 data (§B).

### D.1 Close error of (a) — |model − de-vigged close|, probability points

| Rows | Lineups | n | (a) median | (a) p90 | (b) median | v2 median |
|---|---|---|---|---|---|---|
| all | all | 555 | 4.8 [3.9, 5.7] | 13.4 [11.9, 14.5] | 5.1 [4.5, 6.0] | 7.2 [6.2, 8.0] |
| all | stable | 458 | 4.5 [3.7, 5.5] | 12.9 [11.4, 13.8] | 4.9 [4.5, 5.9] | 7.0 [6.1, 7.9] |
| all | lineup_change | 97 | 6.0 [4.1, 8.2] | 15.2 [11.8, 21.4] | 5.2 [4.2, 8.7] | 7.4 [5.1, 9.5] |
| two_sided_V | all | 94 | 5.0 [3.8, 6.0] | 12.5 [10.5, 14.5] | 5.5 [3.9, 7.0] | 5.5 [4.8, 7.0] |
| two_sided_V | stable | 75 | 4.8 [3.8, 5.9] | 12.3 [10.1, 14.3] | 5.6 [4.0, 6.5] | 5.5 [4.6, 6.9] |
| two_sided_V | lineup_change | 19 | 5.4 [2.9, 11.3] | 13.5 [5.8, 21.9] | 4.3 [3.4, 9.3] | 6.9 [5.0, 10.5] |

**Result:** the success bar (median < ~2 pp on stable-lineup tier-1) is **not met**: 4.5 [3.7, 5.5] pp. Model (a) is ~2.5 pp closer to the close than v2, but still far from replicating it. Lineup-change matches are worse, with a wide CI.

### D.2 Are residuals (close − model (a)) predictable?

- **Method:** training residuals were cross-fitted (5 folds by event). Ridge and LightGBM (fixed settings) were fit on 2024–25 and scored on 2026.
- **Features:** churn, lineup change, international, weeks into season, rating uncertainty, days since last match, recent surprise difference, best-of, and |model logit|.

| Residual model | out-of-sample R² on 2026 (n) | verdict |
|---|---|---|
| ridge | 0.024 [-0.021, 0.062] (555) | CI includes 0 |
| LightGBM | -0.120 [-0.206, -0.043] (555) | CI excludes 0 (overfits) |

Residual SD on 2026: 0.355 logit. Largest raw correlations with the 2026 residual: days_since +0.14, abs_x -0.11, lineup_change +0.09, best_of +0.05.

**Result:** our pre-match features explain ≤ ~6% of the gap to the close (upper CI bound). The market's extra information is not in these features. Pinnacle closes (§A.3) would separate real disagreement from target noise.

### D.3 Outcome log loss, series level (lower is better; coin flip 0.6931)

| Rows | n | (b) | v2 | close | (b) − v2 | (b) − close |
|---|---|---|---|---|---|---|
| all | 650 | 0.6559 | 0.6706 | — | -0.0147 [-0.0367, 0.0028] | n/a |
| with_close | 555 | 0.6440 | 0.6588 | 0.6363 | -0.0147 [-0.0372, 0.0038] | 0.0078 [-0.0046, 0.0220] |
| two_sided_V | 94 | 0.6657 | 0.6735 | 0.6699 | -0.0078 [-0.0635, 0.0334] | -0.0042 [-0.0309, 0.0258] |
| map level | 1664 maps | 0.6746 | 0.6819 | — | — | — |

- **Close on the `with_close` rows:** de-vigged with the season median overround, so its log loss is mildly flattered (see REPORT.md §0.2).
- **`two_sided_V` rows:** use the match's own overround; this is the clean comparison.
- **(b) vs v2:** (b) is better than v2 by ~0.015 at series level (the CI only just includes 0) and by 0.007 at map level.
- **(b) vs the close:** on the clean rows (b) is indistinguishable from the close. On all rows it trails by 0.008 (CI includes 0).

### D.4 The gap (b − a): Benter blend, ROI and CLV by gap size

Benter blend fit on 2024–25 rows with a close (n = 806): logit p = 0.38·logit(b) + 0.55·logit(close). On 2026, Benter − close log loss = 0.0006 [-0.0049, 0.0062] → CI includes 0.

Paper bets back the side the gap favours, 1 unit at the actual Thunderpick closing price. P&L is exact: a win is paid at the published winner price.

CLV uses the two-sided Wayback snapshot (median ~13 h pre-start) as the bet price against the close. The loser's close is backed out with the match's own overround.

| Gap definition | gap size (abs) | bets | ROI [CI] | CLV bets | mean CLV [CI] |
|---|---|---|---|---|---|
| (b) − (a) | 0-2pp | 178 | -15.6% [-31.7%, -0.6%] | 28 | +2.4% [-2.7%, +9.5%] |
| (b) − (a) | 2-5pp | 234 | -4.1% [-18.3%, +12.2%] | 38 | +0.6% [-1.7%, +3.9%] |
| (b) − (a) | 5-10pp | 131 | -5.0% [-18.7%, +9.9%] | 26 | -3.4% [-7.0%, -0.1%] |
| (b) − (a) | 10-100pp | 12 | n/a | 2 | n/a |
| (b) − close | 0-2pp | 117 | -13.1% [-29.1%, +4.8%] | 16 | -1.7% [-4.3%, +2.7%] |
| (b) − close | 2-5pp | 158 | -14.3% [-24.2%, -2.1%] | 28 | -1.2% [-5.2%, +1.5%] |
| (b) − close | 5-10pp | 160 | +2.4% [-11.8%, +17.6%] | 33 | -3.5% [-5.5%, -1.6%] |
| (b) − close | 10-100pp | 120 | +1.0% [-22.5%, +27.5%] | 17 | -7.4% [-16.1%, -1.2%] |

**Result:** no bucket shows positive ROI or CLV.
- **Where the model disagrees with the market by > 5 pp:** CLV is significantly *negative*. The price moves further from the model before the start, so the market knows something the model doesn't.
- **Two buckets have ROI CIs entirely below 0:** (b)−(a) under 2 pp and (b)−close 2–5 pp. The side the model prefers loses more than the bookmaker margin alone would cost. That fits a better-informed market, but with 8 buckets, treat it as indicative.

### D.5 Ablation with tier-2 training data

**Not run.** It needs the tier-2 scrape (§B). The engine already carries a tier offset, so the ablation is a re-run of `scripts/rating_eval.py` with tier-2 maps added. Keep tier-2 only if tier-1 close error *and* outcome log loss both improve.

### Optional stage 2 (LightGBM on rating features; fixed settings, same protocol)

- Outcome log loss, LightGBM − (b): 0.0116 [-0.0049, 0.0255] → no gain.
- Median close error, LightGBM (a): 5.4 [4.6, 6.1] pp vs linear (a) 4.8 [3.9, 5.7] pp → no gain.
- Not adopted.

## E. Pre-registration updates (`research/PREREG_KICKOFF2027.md`)

1. **§10 stale-line study:**
   - The odds logger now detects completed matches and snapshots the same teams' upcoming matches in that poll (`trigger='post_result'`, latency ≤ 15 min). It has an offline test.
   - Signal = frozen model (a) − de-vigged stale price; ≥ 2 pp → paper bet; CLV against the close.
   - Reported overall, by surprise size, and as a slope.
   - **Success:** positive CLV that grows with surprise size.
2. **Tier-2 stratum:** Challengers matches in the same window, same rule, reported separately with no decision. It exists only if the tier-2 scrape is approved.
3. **Code freeze:** evaluation code and frozen model parameters committed, hashes recorded: thunderedge `da4e5357c89cf8d83d3a907f6362fa95c917685b`, valorant-pricing-model `5370dafe19433f787fd1fb0ca37529d9078d4930`.
   - Smoke-tested on 2026: 49 qualifying matches, the same 49 as the backtest slice. The pre-match churn proxy agrees with realised-lineup churn on 48/49.
   - The stale-line path was run end-to-end on synthetic triggers.

## Side findings

- **Production DP, known limitation:** anti-eco rounds 14–15 reuse the round-1 pistol winner. This is documented in `src/pricing/dp.py` as a Phase-2 follow-up. It affects v2 and (b) equally.
- **`_within_map_p_a_wins`:** its `starting_side` argument does not drive the round probabilities (REPORT.md §4.2). Still worth removing.

## Decisions needed

1. **Tier-2 Phase 0:** 30 vlr pages (ledger 2,017 → ~2,047) to measure Challengers volume and Thunderpick coverage. Phase 1's budget would then be set from those numbers (§B).
2. **Historical stale-line test (§A.3):** about 720 OddsPapi calls (mostly non-billable; raw Pinnacle data kept out of the public repo) and about 700 Kalshi calls. Polymarket (+~800) is optional.
3. **OddsPapi paid plan:** needed for Thunderpick history and the Thunderpick-vs-Pinnacle lag. Price and history depth are unverified. My suggestion: decide after the Pinnacle study.
4. **Still open from last round:**
   - the pre-registration's ~155–175 vlr pages, plus the 1-page roster-parser check;
   - logger hosting and in-season cadence. The laptop slept ~10 h on 2026-11-17 and the logger missed ~40 polls.
5. **v2 rates swap:**
   - The shadow window ends ≥ 2026-11-20.
   - Model (b) is a candidate pre-match input in place of v2, but its gain is not yet significant. I'd keep both in shadow through Kickoff 2027 rather than swap now.

## Reproduce

```
(pricing repo) uv sync --group research
(pricing repo) python scripts/rating_eval.py --db ../thunderedge/data/valorant_stats.db --out ../thunderedge/research/out/rating_eval.json
python -m research.make_report_v2
```
