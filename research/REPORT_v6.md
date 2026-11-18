# VALORANT research — round 6 report

_Generated 2026-11-18 08:47 UTC by `research/make_report_v6.py`. Paper only. §1 is **exploratory** (2026 data, no new requests, the k values and buckets fixed by you). CIs are 95% bootstrap clustered by event unless stated; n is given with every number._

## Overview

| # | Item | Verdict |
|---|---|---|
| 1 | De-vig robustness | **k = 5 survives, k = 3 doesn't.** k = 5 net CLV vs Pinnacle close: multiplicative +1.88, power +0.88, Shin +1.19 pts. k = 3 is ≈ 0 under all three. Part of round 5's edge was the multiplicative de-vig shifting probability toward longshots. Stale-at-open CLV barely changes (+6.0% to +6.2%). |
| 2 | PREREG §11 | Frozen at `574c26b`. Shin is primary: it fails on 0 of 579 markets. On 2026 the exact rule gives 38 trades, with net CLV +2.53 pts. Power at look 2 (≈ 38 trades) is ≈ 68% at that effect and ≈ 24% at the smaller Shin estimate. |
| 3 | §10 gap slices | Added as a descriptive slice only (2–3 / 3–5 / > 5 pts); the rule and thresholds are unchanged. |
| 4 | Poll parser test | **Not testable today.** The discovery call found no VALORANT fixtures in the next 4 days (404 FIXTURE_NOT_FOUND). I used 1 of the 2 approved calls and skipped the odds call. Live-poll ledger: 1 call. |
| 5 | Order books | Kept in full; nothing is pruned. |
| 6 | v2 swap | None. `shadow_compare.py` runs on or after Nov 20 and reports v2 vs the Kalshi mid only, with (b)'s coverage noted. |

## 1. EXPLORATORY — de-vig robustness

Methods (`research/devig.py`): **multiplicative** p = (1/o)/Σ(1/o); **power** p = (1/o)^k with Σ = 1; **Shin** (two-outcome insider model, z solved so Σ = 1). Pinnacle fair and Pinnacle close use the same method. Trades are re-selected under each method (fair − ask > k). Net = CLV − the quadratic fee per contract (multiplier 1, unrounded as in rounds 4–5).

Shin validity: **0 of 579 markets fail** (0 of 25,185 active pre-start records).

### Kalshi taking: CLV vs Pinnacle close, pts

| k | ask bucket | multiplicative: n, gross, **net** | power: n, gross, **net** | Shin: n, gross, **net** |
|---|---|---|---|---|
| 3 | all | 340, +1.63 [+1.27, +2.13], **+0.09 [-0.26, +0.58]** | 385, +1.38 [+1.08, +1.80], **-0.16 [-0.46, +0.24]** | 364, +1.37 [+0.97, +1.87], **-0.17 [-0.55, +0.29]** |
| 3 | <0.30 | 75, +3.00 [+2.34, +3.80], **+1.83 [+1.15, +2.62]** | 30, +2.17 [+0.70, +3.45], **+0.96 [-0.51, +2.22]** | 47, +2.47 [+1.28, +3.61], **+1.31 [+0.09, +2.45]** |
| 3 | 0.30-0.70 | 252, +1.26 [+0.83, +1.82], **-0.40 [-0.83, +0.15]** | 275, +1.25 [+0.88, +1.74], **-0.42 [-0.78, +0.07]** | 269, +1.23 [+0.75, +1.75], **-0.44 [-0.91, +0.08]** |
| 3 | >0.70 | 13, +0.83 [-0.20, +2.51], **-0.47 [-1.51, +1.19]** | 80, +1.54 [+0.83, +2.32], **+0.30 [-0.39, +1.08]** | 48, +1.11 [+0.18, +2.00], **-0.14 [-1.08, +0.77]** |
| 5 | all | 105, +3.34 [+2.44, +4.19], **+1.88 [+0.98, +2.68]** | 121, +2.40 [+1.46, +3.85], **+0.88 [-0.07, +2.32]** | 105, +2.71 [+1.60, +4.30], **+1.19 [+0.08, +2.74]** |
| 5 | <0.30 | 40, +4.54 [+3.15, +5.47], **+3.40 [+1.95, +4.33]** | 15, +3.47 [+1.54, +5.40], **+2.28 [+0.25, +4.27]** | 21, +4.05 [+2.48, +5.39], **+2.84 [+1.31, +4.17]** |
| 5 | 0.30-0.70 | 65, +2.60 [+1.41, +3.92], **+0.94 [-0.24, +2.26]** | 80, +2.33 [+1.11, +4.10], **+0.66 [-0.58, +2.43]** | 70, +2.35 [+1.01, +4.04], **+0.68 [-0.68, +2.38]** |
| 5 | >0.70 | 0 | 26, +1.99 [+0.89, +3.23], **+0.73 [-0.38, +1.99]** | 14, +2.54 [+0.88, +5.05], **+1.26 [-0.42, +3.78]** |

**Verdict:** k = 3 has no net edge under any method. At k = 5, net CLV is positive under all three, but the size depends on the de-vig: +1.88 (multiplicative) vs +1.19 (Shin), whose CI nearly touches 0. The < 30¢ bucket stays the strongest under every method, but its n falls from 40 to 21 under Shin, because Shin gives longshots less probability. The multiplicative method overstated cheap-contract edges.

### Thunderpick stale-at-open (Wayback set): the same methods on Pinnacle and on Thunderpick

| Method | n bets | events | same bets as multiplicative | mean CLV vs Thunderpick close | 2–3 pts | 3–5 pts | > 5 pts |
|---|---|---|---|---|---|---|---|
| multiplicative | 38 | 13 | 38 | +6.2% [+1.0%, +13.4%] | 14: -0.1% [-5.3%, +3.2%] | 21: +4.6% [+2.8%, +6.6%] | 3: +47.1% (no CI) |
| power | 43 | 13 | 37 | +6.0% [+1.2%, +12.7%] | 16: +2.0% [-1.8%, +5.3%] | 19: +3.2% [+0.6%, +5.3%] | 8: +20.9% [+0.1%, +39.7%] |
| Shin | 42 | 13 | 37 | +6.1% [+1.2%, +12.8%] | 18: +1.1% [-2.6%, +4.3%] | 18: +4.8% [+2.7%, +7.1%] | 6: +25.1% [+0.1%, +52.7%] |

**Verdict:** robust. The overall CLV is the same under each method, and the 2–3-pt bucket stays ≈ 0 under all three.

## 2. PREREG §11 — Kalshi taking at k = 5 (frozen)

| Element | Frozen definition (`PREREG_KICKOFF2027.md` §11) |
|---|---|
| Rule | buy the Kalshi side when Shin fair − ask > 5 pts; first entry per match × side |
| Pinnacle freshness | latest Pinnacle record ≤ 15 min old at the observation time, active and Shin-valid |
| Size | min(1 unit = 100 contracts, displayed size at the best ask) from the logged book; ≥ 1 contract required |
| Fee | Kalshi quadratic, multiplier 1, rounded up per order: ceil(100·0.07·C·P·(1−P))/100 $ |
| Primary | net CLV vs Pinnacle Shin close, per trade; match-level bootstrap |
| Primary de-vig | Shin, by the rule "Shin unless it fails on > 5% of markets", applied to 2026: 0/579 → Shin |
| Look 1 | matches to 2027-06-30: confirm if ≥ 20 trades and the one-sided 99% LB > 0; abandon if ≥ 20 trades and mean ≤ 0; else continue |
| Look 2 | pooled to 2027-10-31: confirm if ≥ 30 trades and the one-sided 96% LB > 0; else abandon (< 30 trades: inconclusive) |
| Secondary | settlement P&L, the < 30¢ slice, multiplicative/power de-vig, gross CLV, CLV vs Kalshi close, contracts filled, blocked-signal counts |
| Code | `research/prereg_s11.py` + `research/devig.py`; thunderedge `574c26b84f21f284e79ae4ee6b9c0c3a17f52911`; tests `research/test_prereg_s11.py` (fee rounding, entry rule, end-to-end on a synthetic logger DB) |

**The rule on 2026** (`prereg_s11.py --backtest-2026`: candle quotes every 15 min; displayed size unknown, treated as 100):

| Measure | Value |
|---|---|
| Trades | 38 (12 events); 3 in the first 42 days; 26 by 30 Jun |
| Net CLV, Shin (primary) | +2.53 pts, match bootstrap [+0.42, +4.87]; event bootstrap +2.53 [+0.31, +5.15]; sd 7.0 |
| Net CLV, multiplicative | +2.73 pts [+0.68, +4.97] |
| Net CLV, power | +2.41 pts [+0.22, +4.80] |
| Settlement P&L per contract | +7.5¢ [-7.7, +22.6] |
| ask < 0.30 slice | n = 12, net CLV +2.19 [-0.24, +4.40] |
| Observation times blocked | Pinnacle > 15 min old: 26; inactive/invalid: 30 |

The 15-min freshness rule keeps trades that follow recent Pinnacle moves, which is why the backtest's +2.53 is higher than the 1-min, no-age-rule +1.19. Both are selected estimates.

**Power** (normal approximation, sd 7.0 pts):

| True mean net CLV | look 1, n = 26, α = 0.01 | look 2, n = 38, α = 0.04 | n = 60, α = 0.04 | n = 100, α = 0.04 |
|---|---|---|---|---|
| +2.53 (backtest of this rule) | 31% | 68% | 85% | 97% |
| +1.19 (Shin, 1-min, no age rule) | 7% | 24% | 33% | 48% |

Trade counts assume 2027 matches 2026's rate. Kalshi's VALORANT coverage grew through 2026 (Q1 293 events, Q2 675), so 2027 may have more.

**Verdict:** frozen and tested. Two things are outside the code: the Pinnacle history budget (`oddspapi_s11`, ≤ 600 calls, ≤ 40 billable) needs your approval before the first fetch, and displayed sizes can only come from 2027 books.

## 3. §10 gap slices

`_stale_block` now also reports `by_gap_descriptive`: n bets and CLV for |gap| 2–3, 3–5 and > 5 pts, tier by tier. The 2-pt bet threshold, the success rule and the tags are unchanged. The smoke run on 2026 completes (no logger data for 2026, so no rows). Logged in §9.

## 4. Poll parser test

| Step | Result |
|---|---|
| 1. `/v4/fixtures?sportId=61&from=today&to=+4 d` (billable, ledger `oddspapi_live`) | 404 `FIXTURE_NOT_FOUND`: no VALORANT fixtures listed. Kalshi's current markets are Chinese third-party and Kickoff-qualifier events that OddsPapi doesn't carry. |
| 2. `/v4/odds-by-tournaments` | **not made**: nothing priced to compare against |
| Calls used | 1 of the 2 approved |

**Verdict:** the parser is still unverified. Its guard is unchanged: a priced response that parses to nothing turns the poll off. The live poll will make the first real call itself when Kickoff 2027 fixtures fall within 96 h, and that response is saved.

## 5–6.

- **Order books:** kept in full, no pruning (≈ 9 MB/week off-season, REPORT_v5).
- **v2 swap:** none. On or after 2026-11-20: `python scripts/shadow_quotes.py report --since 2026-11-17T08:12`, then `python scripts/shadow_compare.py`, reporting v2 vs the Kalshi mid only, with (b)'s coverage noted (6/158 market sides in the preview).

## Decisions needed

1. **§11 Pinnacle budget:** approve ledger host `oddspapi_s11`: ≤ 600 history calls (non-billable) + ≤ 40 billable fixture-window calls over the 2027 season, run at each look (2027-06-30, 2027-10-31). Histories cached for §10 are reused.
2. **Parser test:** retry with one discovery call once VALORANT fixtures are listed again, likely late December when Kickoff 2027 schedules post? Or leave it to the poll's first live call (it is protected by the self-disable guard).
3. **§11 unit:** 1 unit = 100 contracts (≈ $50 at 50¢). Change it before Kickoff if you want a different unit; changing it later would be a deviation.
4. Still open: Kalshi key (send when ready), VPS hosting, in-season logger cadence.
