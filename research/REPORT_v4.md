# VALORANT research — round 4 report

_Generated 2026-11-18 02:24 UTC by `research/make_report_v4.py`. Paper only. §2 is **exploratory** (labelled, no new requests, three fixed thresholds k = 2/3/5, nothing searched). CIs are 95% bootstrap clustered by event._

## Overview

| # | Item | Verdict |
|---|---|---|
| 1 | PREREG §10 → stale at open | Re-frozen at thunderedge `034b62f` / pricing `5370daf`. The Pinnacle-open poll is built but **disabled**: even hourly it costs ≈175 OddsPapi calls a week against 250 a month on the free plan. §10 runs post hoc without it. |
| 2 | Exploratory (full pre-match window) | Kalshi takes a median 3.3 h to follow half of a Pinnacle move, and 40% of moves are never followed. Taking at k=3/5 gains CLV (+0.46 / +0.99 pts), but that is below the ≈1.75-pt taker fee at 50¢, so there is no tradable edge yet. Thunderpick stale-at-open: CLV +6.2% [+1.0%, +13.4%] on n=38, a positive signal from a small sample. |
| 3 | Tier-2 scrape + ablation | The scrape **stopped itself on 3 consecutive local DNS failures** (not a block) at 4,276/4,966 pages, and I haven't resumed it. Ablation on those pages: adding tier-2 makes the close fit **worse** by +0.89 pts [+0.28, +1.40], and outcome LL is unchanged (+0.0031 [-0.0119, +0.0164]). Keep the model tier-1 only. |
| 4 | Lid close on AC | Set to 'do nothing' (battery: sleep, unchanged). |
| 5 | Kalshi key rotation | Pre-check done. I'm waiting on the new key; I'll write it only to the local `.env`. One branch (`origin/feature/market-maker`) still has the old key ID in `.env.example`; no private key is in any commit. |

## 1. PREREG §10 — stale at open

| Element | Frozen definition (`PREREG_KICKOFF2027.md` §10) |
|---|---|
| t_open | First active Pinnacle match-winner record in OddsPapi history. |
| Signal | Pinnacle de-vigged price at t_open minus the de-vigged Thunderpick price standing at t_open (latest snapshot ≤ t_open). |
| Bet | Side Pinnacle favours, when the signal is at least 2 pts, at the first Thunderpick quote ≥ t_open. Flat stake. |
| Tag | `post_result_stale` = Thunderpick unchanged since the teams' last completed result, plus `moved_since_result`, `posted_after_result` and `no_result_time`. |
| Outcome | CLV = log(bet price / Thunderpick close). ROI is secondary. |
| Stale duration | Minutes from t_open until Thunderpick first changes the standing price (Kaplan–Meier, censored at the start). Also: share still available at the bet. |
| Fallback | When Pinnacle never posts: model (a) at T−24 h. Reported separately, with no decision. |
| Success | ≥ 10 bets and a one-sided 95% lower bound on mean CLV > 0 (Pinnacle-referenced bets only). |
| Code hash | thunderedge `034b62fceb7fb5259c7dde18c4e5a217f798900b`; pricing `5370dafe19433f787fd1fb0ca37529d9078d4930` (§7). Change logged in §9. |

**OddsPapi request cost of the live Pinnacle-open poll** (billable; in season, ≥ 1 tier-1 match within 72 h most days):

| Poll interval | Calls / week | Calls / 30 days | Fits the free plan (250 / month)? | Opening-time resolution |
|---|---|---|---|---|
| 15 min | 679 | 2910 | no | ±7 min |
| 30 min | 343 | 1470 | no | ±15 min |
| 60 min | 175 | 750 | no | ±30 min |
| 180 min | 63 | 270 | no | ±90 min |
| 360 min | 35 | 150 | yes | ±180 min |

The cost is one `fixtures` discovery call a day plus one `odds-by-tournaments` call per poll, and it doesn't grow with the number of matches. Using up the monthly quota also blocks the non-billable history calls that §10 needs post hoc. So the poll stays off (`research/pinnacle_open.json`), and §10 takes t_open from history after each week (≤ 6 billable + ≈120–300 history calls per season, §4). The poll's only advantage is a Thunderpick snapshot taken right at t_open, instead of the logger's last scheduled poll.

**Verdict:** frozen and runnable post hoc on the free plan. A live poll needs a paid plan, or a 6-hourly interval, which is too coarse to be useful.

## 2. EXPLORATORY — 2026 tier-1, full pre-match window (no new requests)

### (c) Pinnacle → Kalshi lag after each Pinnacle move (≥ 2 pts), n = 2,725 moves, 16 events

Lag = time until Kalshi's mid covers 50% (k50) or 90% (k90) of the Pinnacle move. Kaplan–Meier; censored at the start.

| Slice | n | k50 median [IQR] | never reaches 50% | k90 median | never reaches 90% |
|---|---|---|---|---|---|
| all moves | 2,725 | 3.3 h [10 min, 19.0 h] | 40% | 10.7 h | 54% |
| move 2-3pts | 1,870 | 2.9 h [8 min, 17.6 h] | 39% | 7.4 h | 51% |
| move 3-5pts | 743 | 4.1 h [13 min, 21.8 h] | 40% | 15.9 h | 59% |
| move 5+pts | 112 | 11.2 h [86 min, never (censored)] | 54% | 48.2 h | 81% |
| <2h to start | 726 | 50 min [5 min, never (censored)] | 59% | never (censored) | 73% |
| 2-12h to start | 950 | 4.5 h [34 min, never (censored)] | 41% | 8.8 h | 55% |
| >=12h to start | 1,049 | 3.7 h [6 min, 21.8 h] | 25% | 14.4 h | 40% |

**Verdict:** Kalshi follows Pinnacle slowly, and bigger moves are followed more slowly. Close to the start the lag drops to ≈50 min.

### (b) Taking simulation: buy Kalshi when Pinnacle fair − Kalshi ask > k (quadratic fee, multiplier 1)

| k | n trades | matches | mean edge at entry | CLV vs Kalshi close, pts | ROI net of fee |
|---|---|---|---|---|---|
| 2 pts | 557 | 445 | 3.1 pts | +0.15 [-0.14, +0.45] | +1.3% [-8.5%, +10.1%] |
| 3 pts | 340 | 302 | 4.1 pts | +0.46 [+0.17, +0.81] | +6.4% [-6.7%, +18.0%] |
| 5 pts | 105 | 102 | 6.6 pts | +0.99 [+0.26, +1.91] | +15.9% [-22.0%, +62.2%] |

Fills are 1 contract at the candle ask. Kalshi candles carry no displayed size, so "fill only up to displayed size" can't be applied historically. The ROI figures assume 1 contract was always available. First trigger per (match, side) only. Fee = 0.07·P·(1−P) per contract, unrounded (≈1.75¢ at 50¢). Kalshi rounds each order's fee up to the cent, so a 1-contract fill pays 2¢ and the ROI here is slightly optimistic.

**Verdict:** CLV is real at k ≥ 3 but smaller than the fee. ROI CIs include 0 at every k. This is not a strategy until live order-book depth is logged.

### Thunderpick stale-at-open, rough look (own logger snapshots, 2026)

| Slice | n bets | events | CLV vs Thunderpick close |
|---|---|---|---|
| all | 38 | 13 | +6.2% [+1.0%, +13.4%] |
| snapshot_after_open (Pinnacle standing at snapshot) | 25 | 13 | +2.3% [-0.2%, +4.2%] |
| snapshot_before_open (TP assumed unchanged to open) | 13 | 7 | +13.7% [+1.8%, +35.0%] |

Matches with both a Pinnacle open and a Thunderpick snapshot: n = 80. Median |signal| = 1.9 pts. Pinnacle opens a median 29 h before the start; our median snapshot is 16 h before. ROI at the snapshot price is +3.7% [-31.4%, +40.9%]. The logger was not polling at t_open, so the 'before open' rows assume Thunderpick was unchanged from the snapshot to the open. That assumption is what the live poll would remove.

**Verdict:** positive CLV, mostly from the 13 'before open' rows (7 events). It supports running §10, but is not evidence on its own.

## 3. Tier-2 scrape (2025–26) and tier-1 ablation

| Check | Result |
|---|---|
| robots.txt (2026-11-17) | No crawl-delay. `/search/auto` and `/rr/` are disallowed (never requested). 1 extra request, outside the ledger. |
| Rate | 1 request / 3 s + 0–1 s jitter ≈ 0.29 req/s. Logger ≈ 4 req / 15 min. Combined ≤ 0.3 req/s. |
| Volume found | 134 events, 6,476 completed match pages (vs ≈5,400 approved) |
| Deferred (over approval) | 20 open-qualifier events, 1,510 pages, mostly semi-pro sides. Not fetched. |
| Fetched | 4,276 / 4,966 league-stage match pages + 130 list pages. vlr ledger 6,450 (ceiling 7,452). |
| Stop | 2026-11-18 01:06 UTC, after 3 consecutive `NameResolutionError` (local DNS lookup failed). There was no 403, 429 or Cloudflare page in the run. The odds logger and shadow job also missed that poll. 690 pages left. Resuming would bring the ledger to ≈7,140, which is within the ceiling. |
| Errors other than the stop | 0 |

**Player histories** (2026 tier-1 lineup slots, n = 6,505; 386 players):

| Prior maps before the slot | Slots |
|---|---|
| any tier-1 | 6,354 |
| any tier-2 (2025–26) | 3,048 |
| tier-2 only: a cold start the scrape fills | 136 (136 players, first tier-1 series) |
| neither | 15 |

**Ablation.** Train on 2024–25 (tier-1 tuning only), test on 2026 tier-1 series: n = 650 (with a close: 555; stable lineups: 458). Tier-2 maps used: 9,661.

| Metric | T1 frozen | T1 re-tuned (control) | T1 + T2 | T1+T2 − control [95% CI] |
|---|---|---|---|---|
| (b) outcome log loss | 0.6559 | 0.6559 | 0.6589 | +0.0031 [-0.0119, +0.0164] |
| (a) median \|model − close\|, all, pts | 4.82 | 4.66 | 5.55 | +0.89 [+0.28, +1.40] |
| (a) same, stable lineups, pts | 4.54 | 4.50 | 5.35 | +0.84 [+0.45, +1.38] |

The tuned tier offset prior is v0_tier = 0.25, the middle of {0.05, 0.25, 1.0}. Re-tuning picked identical engine params for both arms, so the T1+T2 vs control gap is the tier-2 data. The control differs from the frozen model only in head (a)'s κ (0.8 → 1.0) and its re-fit coefficients. Tier-2 2024 was not scraped, so tier-2 histories start in 2025, and the head (a) was fit on a 2025 rating distribution that only partly includes tier-2. That is one reason the close head degrades. I tried no other variants, because that would be searching on test data.

**Verdict:** adding tier-2 makes the close fit **worse** by +0.89 pts [+0.28, +1.40], and outcome LL is unchanged (+0.0031 [-0.0119, +0.0164]). Keep the model tier-1 only.

## 4. Lid close on AC

| Setting | Before | After |
|---|---|---|
| Lid close, AC (`LIDACTION`) | sleep | **do nothing** (verified with `powercfg /qh`) |
| Lid close, battery | sleep | sleep (unchanged) |

**Verdict:** done. Polls still stop on battery or when Windows is shut down.

## 5. Kalshi key rotation — pre-check

| Location | `.env.example` | Kalshi entries |
|---|---|---|
| thunderedge `research/market-structure`, `main`, other local branches | absent | — |
| `origin/feature/eco-round-strategy` | present | placeholders (`your…`, `/path…`) ✔ |
| `origin/feature/market-maker` | present | **real old key ID** (`aba4…`, commit `2415a09`); key path is a placeholder |
| valorant-pricing-model (all 5 refs) | absent | — |
| Private key file / PEM in any commit, either repo | none | — |
| Local `.env` | pricing repo: OddsPapi only; thunderedge: none | none yet |

**Verdict:** once you rotate, the old ID is dead and the leak doesn't matter. A placeholder fix on `feature/market-maker` is a one-line commit plus a push to a branch I haven't touched; I'll do it only if you ask.

## Decisions needed

1. **Resume the tier-2 scrape?** 690 league pages are left, inside the approved ceiling. The stop was local DNS, not vlr. Say "resume" and I'll delete `cache/tier2_STOP` and rerun (≈1 h). With the ablation negative, the only use of those pages is fuller player histories, so it is low value. Recommendation: resume only if a tier-2 stratum or tier-2 trading is planned.
2. **The 1,510 open-qualifier pages** would exceed the ≈5,400 approval by ≈1,198. They help cold-start priors only for players who reach tier 1 through qualifiers. My recommendation is to skip them.
3. **Live Pinnacle-open poll:** an OddsPapi paid plan (lets you poll every 15–60 min), or keep it off and run §10 post hoc on the free plan (recommended for Kickoff 2027). Before enabling, `hist_fetch.CAP` needs an `oddspapi_live` entry (it currently raises KeyError), and the response parser needs one real response to verify against.
4. **Kalshi:** send the new key when it's ready (local `.env` only). Should I commit placeholders to `origin/feature/market-maker`'s `.env.example`?
5. **Kalshi depth:** to make the (b) simulation honest about size, the logger needs to snapshot the Kalshi order book. That is ≈1 request per open market per poll on Kalshi's API, with no vlr.gg cost. Add it?
6. Still open from earlier rounds: VPS hosting, in-season logger cadence, and the v2 half-rate swap after the shadow report (2026-11-20).
