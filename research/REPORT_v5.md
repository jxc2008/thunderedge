# VALORANT research — round 5 report

_Generated 2026-11-18 07:53 UTC by `research/make_report_v5.py`. Paper only. §2–§3 are **exploratory**: a rescoring of round-4 trades and bets, with no new requests and no new thresholds or filters. CIs are 95% bootstrap clustered by event; n is given with every number._

> **Correction to REPORT_v4 §2.** The Thunderpick stale-at-open rough look used the **Wayback** pre-match snapshot (one per match), not our logger. The logger only started on 2026-11-17, off-season. The numbers in v4 stand; the label was wrong.

## Overview

| # | Item | Verdict |
|---|---|---|
| 0 | Push, `.env.example` | Both research branches are pushed. `origin/feature/market-maker` `.env.example` now has placeholders only (commit `f851d6a`, no history rewrite). Both remote branches that have the file show placeholders. The Kalshi key is still pending. |
| 1 | Tier-2 | Not resumed; qualifiers skipped. Priors for 166 players are exported as an optional feature and not wired into the frozen model. |
| 2 | Kalshi taking rescored | The trades beat **Pinnacle's close** by +1.6 pts (k=3) and +3.3 pts (k=5), with CIs above 0. That is more than the ≈1.5¢ fee. Settlement P&L CIs still include 0 at every k. The edge sits in entries below 30¢ and in markets Kalshi later followed (a split that can't be known at entry). |
| 3 | Stale-at-open follow-ups | The mispricing was still posted at the snapshot in all 25 after-open cases: a lower bound of median 15 h, minimum 5.4 h. CLV comes from 3–5-pt gaps (n=21). Leave-one-event-out range: +2.6% to +7.0%, positive whichever event is dropped. |
| 4 | Pinnacle-open poll | The suggested T−30h..T−18h window catches only 20% of opens. **Enabled instead:** T−96h..start, every 6 h. On the 2026 schedule it catches 94% of opens, with a median delay of 2.7 h. Peak 155 calls/month against the free 250; 30-day cap 180. |
| 5 | Kalshi order books | Added to the logger and running. 5 Kalshi requests per 15-min poll (2 list + batched books, 112 open markets). Storage ≈9.1 MB/week with change-only rows (29 MB/week if every poll were stored). |
| 6 | Shadow summary | Due on or after 2026-11-20. `scripts/shadow_compare.py` is ready. In the preview, (b) prices only 6/158 market sides, because off-season Kalshi markets are mostly teams outside the tier-1 data. Expect a thin summary. |

## 0. Push and `.env.example`

| Ref | Commit | Check |
|---|---|---|
| thunderedge `research/market-structure` | pushed, including this round's commits | No `.env`, `cache/` or `.db` tracked; no OddsPapi key string in the new commits |
| valorant-pricing-model `fix/side-baseline-blend` | pushed, including `6bc24bb` (this round) | same |
| thunderedge `origin/feature/market-maker` | `f851d6a` `.env.example` → `KALSHI_KEY_ID=your-kalshi-key-id`, `KALSHI_PRIVATE_KEY_PATH=/path/to/your/kalshi_private_key.pem` | old ID stays in history (no rewrite, per decision) |
| thunderedge `origin/feature/eco-round-strategy` | unchanged | placeholders (`your-key-id-here`) |
| all other refs, both repos | — | no `.env.example` |

**Verdict:** done. When you send the new Kalshi key, it goes into `valorant-pricing-model/.env` only.

## 1. Tier-2 player priors (optional feature)

| Item | Value |
|---|---|
| Players whose first tier-1 map had tier-2 but no tier-1 history | 166 (first tier-1 season 2025: 34, 2026: 132) |
| Median tier-2 maps before the debut | 64 |
| Prior mean (round-logit units) | mean +0.14, sd 0.15. Promoted players start above the new-player prior. |
| Prior variance at the debut | 0.1 = v0_player for all of them. Drift between the last tier-2 map and the debut restores the cap, so the prior adds a mean shift, not certainty. |
| Where | table `t2_player_priors` in `data/valorant_tier2.db`; `research/out/t2_player_priors.json`; built by pricing `scripts/t2_player_priors.py` (T1+T2 arm params) |

REPORT_v4 counted 136 tier-2-only debut slots in 2026, from lineups. The engine run counts 132 for 2026: it needs a complete five and a known region, which 4 debuts lack. 2025 debutants (34) are added because the tier-2 scrape covers 2025.

**Verdict:** available. It isn't in the frozen model, and the round-4 ablation says adding tier-2 to the engine hurts the close fit. Using the priors needs its own pre-specified test.

## 2. EXPLORATORY — Kalshi taking simulation, rescored (same 557 / 340 / 105 trades as REPORT_v4)

Each trade buys 1 contract at the ask when Pinnacle's de-vigged fair minus Kalshi's ask is more than k, on the first trigger per match × side. Fee = 0.07·P·(1−P), multiplier 1. Pinnacle close = last active Pinnacle price before the start. P&L is per contract, net of fee, settled 0/1.

| k | slice | n | mean ask | CLV vs Kalshi close, pts | CLV vs Pinnacle close, pts | P&L ¢/contract | ROI |
|---|---|---|---|---|---|---|---|
| 2 | all | 557 | 0.44 | +0.15 [-0.14, +0.45] | +1.08 [+0.76, +1.47] | -1.29 [-4.69, +1.67] | +1.3% [-8.5%, +10.1%] |
| 2 | ask <0.30 | 100 | 0.21 | +0.72 [-0.02, +1.45] | +2.32 [+1.86, +2.97] | +2.45 [-6.12, +10.46] | +21.7% [-16.2%, +58.6%] |
| 2 | ask 0.30-0.70 | 428 | 0.47 | +0.03 [-0.24, +0.35] | +0.90 [+0.57, +1.28] | -1.73 [-5.40, +1.85] | -2.8% [-10.0%, +5.0%] |
| 2 | ask >0.70 | 29 | 0.75 | +0.02 [-1.50, +2.07] | -0.59 [-1.82, +0.96] | -7.77 [-23.33, +3.89] | -9.5% [-29.5%, +5.8%] |
| 2 | Kalshi followed | 360 | 0.44 | +1.31 [+0.87, +1.69] | +1.74 [+1.35, +2.18] | -0.29 [-3.46, +2.80] | +5.8% [-4.4%, +16.2%] |
| 2 | never followed | 197 | 0.43 | -1.97 [-2.34, -1.60] | -0.12 [-0.45, +0.21] | -3.12 [-9.59, +1.40] | -7.0% [-22.9%, +4.2%] |
| 3 | all | 340 | 0.42 | +0.46 [+0.17, +0.81] | +1.63 [+1.27, +2.13] | -0.02 [-4.33, +3.78] | +6.4% [-6.7%, +18.0%] |
| 3 | ask <0.30 | 75 | 0.22 | +1.05 [+0.49, +1.56] | +3.00 [+2.34, +3.80] | +2.61 [-6.53, +11.12] | +27.7% [-15.7%, +71.2%] |
| 3 | ask 0.30-0.70 | 252 | 0.46 | +0.26 [-0.09, +0.69] | +1.26 [+0.83, +1.82] | -0.03 [-5.52, +5.38] | +1.4% [-11.4%, +14.4%] |
| 3 | ask >0.70 | 13 | 0.75 | +0.81 [-0.57, +2.95] | +0.83 [-0.20, +2.51] | -14.99 [-39.59, +4.16] | -18.8% [-50.5%, +7.0%] |
| 3 | Kalshi followed | 209 | 0.42 | +1.90 [+1.52, +2.29] | +2.56 [+2.20, +3.03] | +3.06 [-1.58, +7.08] | +15.7% [+1.3%, +29.5%] |
| 3 | never followed | 131 | 0.42 | -1.85 [-2.23, -1.51] | +0.14 [-0.35, +0.69] | -4.94 [-11.62, +1.26] | -8.3% [-28.1%, +11.2%] |
| 5 | all | 105 | 0.36 | +0.99 [+0.26, +1.91] | +3.34 [+2.44, +4.19] | +1.95 [-7.12, +10.96] | +15.9% [-22.0%, +62.2%] |
| 5 | ask <0.30 | 40 | 0.21 | +1.98 [+0.84, +2.84] | +4.54 [+3.15, +5.47] | +5.26 [-12.63, +28.21] | +43.8% [-45.7%, +164.6%] |
| 5 | ask 0.30-0.70 | 65 | 0.45 | +0.38 [-0.55, +1.75] | +2.60 [+1.41, +3.92] | -0.09 [-10.65, +7.66] | -1.2% [-26.1%, +17.4%] |
| 5 | ask >0.70 | 0 | — | — | — | — | — |
| 5 | Kalshi followed | 59 | 0.34 | +3.19 [+2.62, +4.16] | +4.77 [+3.94, +5.70] | +8.69 [-6.38, +24.35] | +44.2% [-18.8%, +111.9%] |
| 5 | never followed | 46 | 0.38 | -1.84 [-2.86, -1.11] | +1.50 [-0.24, +3.12] | -6.70 [-18.38, +2.95] | -20.3% [-51.5%, +17.5%] |

"Kalshi followed" means that after entry and before the start, Kalshi's mid closed at least 50% of the entry gap to Pinnacle fair (the round-4 k50 criterion). This uses the future, so it is a diagnostic, not a filter. Mean fee per trade is 1.46–1.55¢. ROI is averaged per dollar, so cheap contracts weigh more; that is why ROI is positive where P&L per contract is not (k=2, k=3).

**Verdict:** against the sharp close, the k ≥ 3 entries are +EV after fees (k=5: about +1.9 pts net). Settlement is too noisy to confirm it (n ≤ 340, 16 events). The value sits in cheap contracts (< 30¢). That is also where a favourite–longshot bias in Kalshi would show, so the same pattern needs checking on 2027 data before it is trusted.

## 3. EXPLORATORY — Thunderpick stale-at-open follow-ups (the REPORT_v4 n = 38 bets, Wayback snapshot, one per match)

**How long the stale price stayed posted.** With one snapshot per match, the duration can only be bounded:

| Measure | n | Value |
|---|---|---|
| Snapshot taken after Pinnacle opened (Thunderpick still ≥ 2 pts off Pinnacle then): lower bound = snapshot − open | 25 | median **15.3 h**, min **5.4 h** |
| Snapshot taken before the open: no bound (the 'unchanged until the open' assumption) | 13 | — |
| Thunderpick's winner price unchanged from the snapshot to the close | 1 of 38 | Thunderpick almost always moves before the start |
| Pinnacle open → start | 38 | median 27.4 h |

The lower bound is for a price that is mispriced against Pinnacle. It is not proof that the same Thunderpick price stood since the open, because Thunderpick may have moved and still been off. A logger snapshot at t_open (§4) measures this directly.

**CLV by gap size** (|Pinnacle − Thunderpick| at the snapshot; the 2/3/5-pt bins used in round 4):

| Gap | n bets | events | mean CLV vs Thunderpick close [95% CI] |
|---|---|---|---|
| 2-3 pts | 14 | 10 | -0.1% [-5.3%, +3.2%] |
| 3-5 pts | 21 | 12 | +4.6% [+2.8%, +6.6%] |
| >=5 pts | 3 | 2 | +47.1% (no CI, n < 5) |
| all | 38 | 13 | +6.2% [+1.0%, +13.4%] |

**Leave-one-event-out** (13 events, 1–6 bets each): mean CLV ranges from +2.6% to +7.0%. The most influential event is `vct-2026-americas-stage-1` (4 bets); dropping it lowers the mean CLV from +6.2% to the minimum.

**Verdict:** the signal holds up to dropping any one event and comes from 3–5-pt gaps. Gaps of 2–3 pts show no CLV. Gaps of ≥ 5 pts (n=3) are too few to judge. The stale window looks long, ≥ 5 h in every bounded case, so a 6-hourly poll is enough to catch it.

## 4. Windowed Pinnacle-open poll

Pinnacle's first price comes before the start by (2026 tier-1, n = 579 of 650): p10 11.0 h, p25 16.7 h, **median 28.8 h**, p75 49.5 h, p90 80.6 h. That spread is too wide for a narrow window.

Replay on the 2026 schedule: a poll is made only while a scheduled match is inside its window and its open hasn't been caught. 1 billable `odds-by-tournaments` call per poll covers every fixture, plus ≤ 1 `fixtures` discovery call per day.

| Window | Cadence | Peak month calls | Mean month calls | Opens caught in window | Already open at window start | Median detection delay |
|---|---|---|---|---|---|---|
| T−30h..T−18h | 1 h | 428 | 222 | 20% | 49% | 0.5 h |
| T−30h..T−18h | 2 h | 241 | 121 | 20% | 49% | 1.1 h |
| T−48h..T−12h | 2 h | 337 | 207 | 62% | 26% | 0.9 h |
| T−48h..T−12h | 3 h | 236 | 146 | 62% | 26% | 1.5 h |
| T−72h..T−6h | 3 h | 271 | 177 | 84% | 12% | 1.6 h |
| T−72h..T−6h | 4 h | 211 | 139 | 84% | 12% | 2.1 h |
| T−96h..T−0h | 4 h | 217 | 153 | 94% | 6% | 2.1 h |
| T−96h..T−0h **(enabled)** | 6 h | 155 | 110 | 94% | 6% | 2.7 h |
| T−72h..T−6h | 6 h | 151 | 100 | 84% | 12% | 2.7 h |

Monthly calls, enabled design (2026 replay): 01: 102, 02: 90, 03: 96, 04: 140, 05: 111, 06: 94, 07: 155, 08: 151, 09: 78, 10: 81. Free plan: 250/month. Margin at the peak month: 95 calls, which covers the ≤ 6 billable prereg calls (§4).

| Safeguard | Setting |
|---|---|
| Rolling 30-day cap | 180 under ledger host `oddspapi_live` (`hist_fetch.CAP_30D`) |
| Tier-1 only | logger tier-1 events, excluding qualifier / open / Ascension / Challengers / Game Changers stages. Without this, the off-season Brazil qualifiers (8 matches this week) would have triggered polls. |
| Parser unverified | the first live response is saved. If a priced response parses to zero prices, the poll disables itself and records why. |
| Cost now | 0. No tier-1 match is pending; the first calls come when Kickoff 2027 fixtures are within 96 h. |

OddsPapi paid plans: the public pricing page lists only Free ($0, 250 requests/month) and "Custom" B2C/B2B plans with no published price, so the cheapest paid plan needs a quote. It isn't needed at this design.

**Verdict:** fits the free plan with margin; enabled.

## 5. Kalshi order books in the logger

| Item | Value |
|---|---|
| What | top 5 levels each side (YES bids, NO bids; YES ask = 1 − best NO bid), every open KXVALORANTGAME / KXVALORANTMAP market |
| When | every logger poll (15 min) + event-driven: post-result trigger polls are tagged `post_result`, Pinnacle-open catches `pinnacle_open` |
| Endpoint | public `GET /markets/orderbooks?tickers=…` (no auth), batches of 50 tickers, 0.25 s apart |
| Requests | 5.0 Kalshi requests per poll on average over 2 polls (2 market lists + ⌈112/50⌉ book batches) ≈ 3,360/week, ≈ 0.0056 req/s |
| Open markets now | 112 (off-season: mostly Chinese and tier-2/3 events) |
| Storage | first poll 120 rows, 29 kB raw. Every poll stored: ≈29 MB/week. Change-only (measured off-season on 1 later poll(s): 37 rows/poll; in season will differ): ≈9.1 MB/week. |
| Storage rule | a row only when a market's top-5 book changed since its last row; event-driven snapshots are always written; forward-fill between rows using `poll_log` |
| Test | `research/test_odds_logger.py::test_kalshi_books_top5_dedupe_and_trigger` |

**Verdict:** running. The order sizes it records make the size cap in the §2-style taking test enforceable from now on.

## 6. Shadow quoting

Shadow quoting is unchanged. `scripts/shadow_compare.py` (pricing repo) takes the last pre-start shadow row per market × team. It adds the frozen model (b), computed on the same current-pool basis as the shadow v2 quote, and the Kalshi settlement. It then scores v2, (b) and the Kalshi mid (Brier, log loss, event bootstrap).

| Preview (now) | n |
|---|---|
| market × team rows | 158 |
| with a Kalshi mid | 158 |
| with (b) (both teams in the tier-1 data) | 6 (1 match; the team-name match is unverified) |
| settled so far | 38 |
| scored (all three + settled) | 0 |

**Verdict:** I'll run it after the Nov 20 shadow report. Off-season coverage means (b) will be scored on very few markets, so v2 vs Kalshi mid will carry the summary.

## Decisions needed

1. **Kalshi key:** send it when it's ready. It goes into the local `.env` only.
2. **Taking strategy (§2):** pre-register a 2027 paper test of k = 5 with live order sizes from the books (primary metric: CLV vs Pinnacle close, net of fee)? This would be a new §11. I'd freeze it before Kickoff, the same way as §10.
3. **Ask-price split:** the edge is concentrated below 30¢ entries. Should that go into the pre-registered rule, or stay a reported slice only (recommended, since it was found on this data)?
4. **Order-book retention:** keep everything, or prune books for markets more than 7 days from their start?
5. Still open: VPS hosting, in-season logger cadence, and the v2 swap after the Nov 20 shadow report.
