# Pre-registration: early-season roster-churn underdog rule, VCT Kickoff 2027 (paper trade only)

Status: **registered 2026-11-17, amended 2026-11-17 (§2 tier-2 stratum, §10 stale-line study),
both before any VCT 2027 match.** Changes after the first VCT 2027 tier-1 match starts are not
allowed; any deviation is logged in §9 with a reason and reported alongside the result. No real
money is staked under this document.

## 1. Hypothesis and where it came from

H1: in the first six weeks of a VCT season, when at least one side has replaced three or more
of its five players since the end of the previous season, the Thunderpick underdog is
under-priced, so flat-stake underdog bets have positive expected return.

Source: `research/REPORT.md` §1.2. On 2024–2026 the slice "weeks 0–6 & churn_max ≥ 0.6"
returned **+22.1% [−12.4%, +63.8%]** per bet (n = 119 bets, 13 events). The CI includes 0, it
was 1 of 8 slices examined, and the same data suggested no churn effect in the calibration
interaction. Treat +22% as an optimistic, selected estimate; the test below is designed to
confirm or kill it on data that did not exist when it was chosen.

## 2. Population

- **Matches:** VCT 2027 tier-1 matches (the four regional Kickoffs, plus any other tier-1
  event that starts in the window), with a scheduled start ≤ 42 days (6.0 weeks) after the
  season start. Season start is the earliest start time of any VCT 2027 tier-1 event, the same
  definition `build_db.py` uses (`weeks_since_season_start = days / 7`).
- **Tier-2 stratum (reported separately, never pooled with tier 1, no decision attached):**
  VCT Challengers matches whose start falls in the same 42-day window, with the same rule.
  Tier-2 teams' previous-season lineups come from the tier-2 scrape (§4), so this stratum
  exists only if that scrape is approved. Tier is `events.tier`.
- **Excluded before anything is looked at:** showmatches; forfeits, walkovers and matches not
  completed (bets void, stake returned); matches where either team has no lineup in VCT 2026
  tier-1 data (churn undefined: the backtest excluded these too). Each exclusion is counted
  and reported.

## 3. The rule

1. **Churn, pre-match (primary).** For each team: churn = share of its *expected* five not in
   its last 2026 tier-1 lineup (modal five of its last 2026 tier-1 match, as in
   `features.churn`). Expected five = its five from its previous 2027 tier-1 match. For a
   team's first 2027 match, use the five-man active roster on the team's vlr.gg page,
   captured 2–48 h before the match. Stand-ins are irrelevant here: in weeks 0–6 of 2024–26,
   97.9% of team-matches fielded the same five as the team's previous match (n = 472).
   `churn_max` = max over the two teams.
2. **Trigger:** `churn_max ≥ 0.6` (≥ 3 new players on at least one side).
3. **Side:** back the Thunderpick **underdog**, the team with the higher decimal price in the
   bet snapshot (step 4). Equal prices → no bet.
4. **Price and time:** the bet is placed (paper) at the latest two-sided Thunderpick
   pre-match quote captured by the odds logger at or before T − 60 min (T = scheduled start).
   The quote must be no older than T − 6 h; otherwise no bet (counted as "no price").
5. **Stake:** 1 unit flat. P&L = price − 1 if the backed team wins the series, else −1.
6. **Settlement:** series winner per vlr.gg after completion. Rescheduled matches use the new
   start time; the bet snapshot is re-taken against it.

## 4. Data and collection (requires your approval: page cap)

- **Odds:** `research/odds_logger.py` (Thunderpick + Kalshi every 15 min). It must be running on
  always-on hosting before the first Kickoff match; see `research/LOGGER_HOSTING.md`.
- **vlr.gg pages the evaluation needs**, all fetched through `research/vlr_fetch.py`
  (≥ 2.5 s, cached, ledgered):
  - ~48 team roster pages (12 partner teams × 4 regions; once each, 2–48 h before a team's first match);
  - ~5 event match lists;
  - ~100–120 completed match pages (results and lineups).

  Total ≈ **155–175 pages**. The research ledger already stands at 2,017, so this exceeds the
  ~2,000-page cap and is **not started until approved.**
- **Stale-line study (§10):** the logger's post-result trigger adds ≈ 1–2 match-page fetches per
  completed match (≈ 100–250 over the window). These count toward the logger's request
  volume, which is a separate decision (`LOGGER_HOSTING.md`).
- **Pinnacle reference (§10):** OddsPapi, run once after the window with
  `prereg_kickoff2027.py --fetch-pinnacle`. It needs ≤ 6 billable fixture-window calls plus one
  non-billable `/historical-odds` call per match in the window (≈ 120–300 calls), hard-capped
  at 320 under `oddspapi_prereg`. Raw OddsPapi data stays in `research/cache/` (gitignored; the
  terms forbid redistribution).
- **Optional live Pinnacle-open poll** (`research/pinnacle_open_poll.py`). It snapshots
  Thunderpick and the Kalshi books the moment the poll sees Pinnacle open. **Enabled 2026-11-18**
  (user decision on REPORT_v4) in windowed form: tier-1 matches only, from T − 96 h until the start,
  one poll every 6 h while a match is pending. The 2026 replay peaks at 155 billable calls a month.
  It has a rolling 30-day cap of 180 (`hist_fetch.CAP_30D`), so it plus the ≤ 6 billable calls above
  stay inside the free 250/month. §10 does not depend on it: when its snapshots exist they are simply
  the earliest Thunderpick quotes after t_open.
- **Tier-2 stratum:** needs the 2026 tier-2 lineups and the 2027 Challengers window pages from
  the tier-2 scrape. Its budget is requested separately (`REPORT_v2.md` §B).
- The 2026 baseline lineups are already in `data/valorant_stats.db`.

## 5. Primary metric and decision

Primary metric: mean P&L per bet (flat-stake ROI) over all qualifying bets.

Inference uses a match-level bootstrap (10,000 resamples), at most one bet per match. Event
clustering, used in the report, is not usable with ~4 events.

Two looks, with α split so the overall one-sided error is ≤ 0.05:

| Look | Data | Confirm if | Abandon if | Otherwise |
|---|---|---|---|---|
| 1. After the last week-0–6 match of 2027 has settled | 2027 bets | one-sided 99% lower bound on ROI > 0 (α₁ = 0.01) | ROI point estimate ≤ 0 | run the identical rule on Kickoff 2028 |
| 2. After the last week-0–6 match of 2028 has settled | 2027 + 2028 bets pooled | one-sided 96% lower bound > 0 (α₂ = 0.04) | — | abandon |

- "Confirm" means it is worth discussing real stakes, with sizing via the pricing repo's
  portfolio Kelly. It does not mean deploying automatically.
- **No other looks.** Interim reads are limited to data-health checks: logger uptime, the share
  of qualifying matches with a price, and exclusion counts. No P&L is computed before look 1.
- If fewer than 20 qualifying bets have a price at look 1, the look is void (data failure,
  reported as such). The rule then runs again in 2028 as if it were look 1.

**Power (be clear about this):**
- The backtest averaged ~40 qualifying bets per season, with a median underdog price of ≈ 2.4.
- I simulated returns at those prices (20,000 draws; normal-approximation bound). The chance of
  clearing a one-sided 95% bound:

  | True ROI | 40 bets | 80 bets |
  |---|---|---|
  | +22% | 24% | 41% |
  | +10% | 10% | 14% |

- The α₁ = 0.01 first look is stricter still.

The most likely outcome of this pre-registration is "inconclusive", unless the effect is as
large as the selected backtest estimate. The abandon rule (ROI ≤ 0 at look 1) is what stops
this from running forever.

## 6. Secondary outputs (descriptive; no decisions)

- **Closing-line value:** log(bet price / last Thunderpick price before T), averaged. If
  positive, the price moved toward the underdog after the bet. This has more statistical power
  than ROI, and is the most informative early signal.
- **Kalshi:** the same bets at the Kalshi best ask for the underdog's YES contract at
  T − 60 min, where a market exists. Matching Kalshi tickers to vlr matches needs fuzzy
  team/time matching, so this is computed by a separate descriptive script and is **not** part
  of the frozen code.
- **Realised-lineup variant:** churn computed from the five who actually played (the backtest's
  definition), for comparability with REPORT §1.2.
- **Complement slices:** underdog ROI when churn_max < 0.6 in weeks 0–6, and when
  churn_max ≥ 0.6 after week 6. These are context, not tests.

## 7. Code freeze

The frozen evaluation is the code at the commits below, committed before any 2027 match:

- `research/prereg_kickoff2027.py` (§3–§6 churn rule, §10 stale-line study, both tiers).
- `research/fetch_rosters.py` (roster snapshots, §3).
- `research/odds_logger.py` (post-result trigger) and `research/pinnacle_open_poll.py` (optional live Pinnacle-open snapshots), §10.
- `research/pinnacle.py`, `research/hist_fetch.py` and `research/timeutil.py` (Pinnacle reference, fixture mapping, vlr ET→UTC, §10).
- `research/prereg_s11.py` and `research/devig.py` (§11 Kalshi taking vs Pinnacle; Shin primary).
- The rating model used for §10's model (a): `valorant-pricing-model/src/rating/` plus the frozen
  parameters and head-(a) coefficients in `research/out/rating_eval.json`.
- **Inputs:** `valorant_stats.db` (with the 2027 pages), `odds_snapshots.db`, `roster_snapshots`.
- **Outputs:** bet lists and the §5, §6 and §10 numbers (`research/out/prereg_2027.json`); §11 trades and decision (`research/out/prereg_s11_2027_look{1,2}.json`).

Results are produced only by these commits. A bug fix is allowed but logged in §9 with a diff.
`fetch_rosters.py` parses a vlr page layout that has not been checked on a 2027 page; the
one-page validation in its docstring comes first, and any parser fix is logged in §9.

- thunderedge evaluation commit: `574c26b84f21f284e79ae4ee6b9c0c3a17f52911` (re-frozen 2026-11-18 for §11; previous `034b62f`)
- valorant-pricing-model rating-engine commit: `5370dafe19433f787fd1fb0ca37529d9078d4930`

## 8. What would change the plan

- Thunderpick disappears from vlr.gg: switch to the vlr-listed book with the most coverage in
  the 2026 Wayback snapshots, logged in §9 before any 2027 bet is evaluated.
- Kickoff format changes so that weeks 0–6 contain far fewer matches: no change to the rule;
  the look waits for the 20-bet minimum.

## 9. Deviations log

| Date | Change | Reason |
|---|---|---|
| 2026-11-17 | Added §10 stale-line study and the tier-2 stratum (§2) | User request, before any 2027 match and before any 2027 data exists |
| 2026-11-17 | §10 redesigned: the reference is Pinnacle's de-vigged price at the snapshot time; model (a) only as a separately reported fallback; surprise from Pinnacle's pre-match price. Code re-frozen (§7) | User request, before any 2027 match and before any 2027 data exists |
| 2026-11-17 | Bug fix: vlr match times (`research_matches.date_utc`) are US Eastern wall-clock, not UTC. The frozen code now converts them (`research/timeutil.py`) before comparing with logger, roster and OddsPapi times. Without it, the T − 60 min bet, the roster window and the close would all be 4–5 h early. Code re-frozen (§7) | Found in the historical study before any 2027 match; no 2027 data exists |
| 2026-11-17 | §10 replaced by "stale at open": Pinnacle's first posted price vs the standing Thunderpick line; CLV vs the Thunderpick close; stale duration; post-result-stale tag; success = CLV lower bound > 0 with ≥ 10 bets. Code re-frozen (§7) | User decision on REPORT_v3, before any 2027 match and before any 2027 data exists |
| 2026-11-18 | `research/build_db.py` gains `--lists/--db/--tier` options (commit `1082b84`) to build a separate tier-2 DB. With the defaults (tier 1), the output is unchanged: the new code paths are gated on `--tier 2`. The frozen evaluation code (§7) is not modified and the hash stands | Tier-2 ablation (REPORT_v4); no 2027 data exists |
| 2026-11-18 | Live Pinnacle-open poll enabled in windowed form (§4). `hist_fetch.py` gains a rolling 30-day cap for the new ledger host `oddspapi_live`; the existing hosts and their caps are unchanged. The odds logger adds Kalshi order-book snapshots (new table `kalshi_books`; `odds_snapshots` is unchanged). None of this changes the frozen evaluation (§7) | User decisions on REPORT_v4; no 2027 data exists |
| 2026-11-18 | §11 added (Kalshi taking vs Pinnacle, k = 5, Shin primary by the stated rule; 0/579 2026 markets fail Shin). §10 unchanged except a descriptive `by_gap_descriptive` slice (2–3 / 3–5 / > 5 pts; no new threshold, no decision). `pinnacle.series` and `prereg_kickoff2027.pinnacle_series` gain a de-vig `method` argument whose default reproduces the frozen multiplicative output exactly. New ledger hosts `oddspapi_s11` (cap 600, approval pending) and `kalshi_prereg` (20). Code re-frozen (§7) | User decisions on REPORT_v5; no 2027 data exists |

## 10. Stale at open (reference = Pinnacle; amended 2026-11-17, round 4)

**Question:** when Pinnacle first posts a match, is the Thunderpick line already standing stale?
In particular, has it been left unchanged since the teams' last result? Background: in 2026,
Pinnacle's next-match line did not exist yet when 95% of results landed (REPORT_v3 §5). A rough
2026 look at Wayback snapshots found a closing-line value of +6.2% [+1.0, +13.4] on 38 bets
(REPORT_v4, exploratory).

1. **Pinnacle open.** t_open is the first active Pinnacle match-winner record for the match,
   taken from OddsPapi `/historical-odds` after the matches are played (§4).
   p_open = de-vigged price of team 1 at t_open.
2. **Standing Thunderpick line.** The latest two-sided Thunderpick quote stored by the odds
   logger at or before t_open, at any trigger. The logger fetches a match page every 15 min
   within 48 h of the start, so the quote is at most 15 min old where the line exists.
   - If no Thunderpick line was up before t_open, the match has no row.
3. **Signal.** Signal = p_open − de-vigged standing Thunderpick price.
4. **Paper bet.** If |signal| ≥ 2 percentage points, back the side Pinnacle favours, 1 unit, at
   the first Thunderpick quote at or after t_open. That is the price a 15-minute poller would
   get. Also reported: whether that quote still equals the standing price.
5. **Outcome.** CLV = log(bet price / Thunderpick closing price) for the backed side. The close is
   the last two-sided quote before the start.
6. **Stale duration.** Minutes from t_open until Thunderpick's price first changes, on either side.
   Kaplan–Meier, censored at the start.
7. **Tags.**
   - **post-result stale:** the standing price equals the first Thunderpick quote after the most
     recent result of either team, and did not change in between. "Result" = the logger's
     `match_status.completed_ts`.
   - **moved since result:** the price changed after that result.
   - **posted after result:** Thunderpick had no line before the result.
   - **no result time:** no earlier completed match of either team was seen.
8. **Fallback.** If Pinnacle never posts before the start, the reference is the frozen model (a)
   at T − 24 h. Those rows are reported separately and carry no decision.
9. **Metrics, per tier and per reference type.** All use a match-level bootstrap (10,000
   resamples): mean CLV overall and by tag, ROI at the bet price, the stale-duration
   distribution, and the share of bets where the standing price was still available.
10. **Success (tier 1, Pinnacle-referenced, look 1 only, no interim looks).**
    - **success:** at least 10 bets and the one-sided 95% lower bound on mean CLV > 0;
    - **not supported:** at least 10 bets and the bound ≤ 0;
    - fewer than 10 bets → "too few bets", reported as such.

    Tags and tier 2 are descriptive.
11. **What "success" licenses:** a live paper-trading test of a stale-at-open rule (Pinnacle open →
    Thunderpick). Nothing more.

## 11. Kalshi taking against Pinnacle, k = 5 (added 2026-11-18, round 6; frozen before Kickoff 2027)

**Question:** when Kalshi's ask is more than 5 points below Pinnacle's de-vigged fair, does buying it
beat Pinnacle's close after Kalshi's fee? Background (exploratory, 2026, REPORT_v4–v6): the same rule
on 1-min candles gave net CLV vs Pinnacle close of +1.88 pts (multiplicative de-vig) / +1.19 pts
[+0.08, +2.74] (Shin), n = 105. With this section's exact rule (15-min observation times, Pinnacle
≤ 15 min old, Shin) it gave **+2.53 pts [+0.31, +5.15]** (event bootstrap), n = 38 trades, 12 events.
k = 5 was chosen from {2, 3, 5} on that data, so these estimates are selected and optimistic.

1. **Population.** VCT 2027 tier-1 matches as seen by the odds logger: `match_status` events matching
   the logger's tier-1 pattern and not a qualifier / open / Ascension / Challengers / Game Changers stage
   (`pinnacle_open_poll.NOT_TIER1`), with a KXVALORANTGAME market for vlr team 1. Look 1: matches
   starting up to 2027-06-30. Look 2: matches starting up to 2027-10-31, pooled with look 1.
2. **Observation times.** Every odds-logger poll at which the market was listed open and the book request
   succeeded (`poll_log.errors` without "kalshi books"), plus event-driven book snapshots
   (`kalshi_books.trigger`). Book at t = the latest `kalshi_books` row at or before t (rows are stored
   only when the top-5 book changes).
3. **Fair.** Pinnacle match-winner price from OddsPapi `/historical-odds`, de-vigged by **Shin**
   (`research/devig.py`). The record used is the latest at or before t. It must be active, Shin-valid,
   and **at most 15 min old** (t − record time ≤ 15 min).
   - **Primary de-vig rule** (stated before any 2027 data): Shin, unless Shin fails on more than 5% of
     markets, in which case multiplicative. A market fails if Shin has no valid solution at any active
     pre-start record. Applied to 2026 (579 markets, 25,185 records): **0 failures → Shin.** Fixed in
     code as `PRIMARY_DEVIG = "shin"`.
4. **Entry.** YES side: ask = 1 − best NO bid; NO side: ask = 1 − best YES bid. Enter when fair − ask
   > 0.05, 0.01 ≤ ask ≤ 0.99, and the displayed size at that ask ≥ 1 contract. At most one entry per
   match × side (the first). Contracts C = min(1 unit, displayed size at the best ask); **1 unit = 100
   contracts**. No walking the book.
5. **Fee.** Kalshi quadratic taker fee, multiplier 1, rounded up per order:
   ceil(100 × 0.07 × C × ask × (1 − ask)) / 100 dollars.
6. **Primary metric.** Net CLV per trade (pts) = 100 × (Pinnacle Shin close for the side − ask) −
   100 × fee / C. Pinnacle close = the last active Shin-valid record before the start. The mean is over
   trades, with a match-level bootstrap (10,000 resamples). Event clustering is not used, because a
   look has few events.
7. **Looks and decisions** (overall one-sided α ≤ 0.05):

   | Look | Data | Confirm if | Abandon if | Otherwise |
   |---|---|---|---|---|
   | 1 | matches to 2027-06-30 | ≥ 20 trades and one-sided 99% lower bound > 0 (α₁ = 0.01) | ≥ 20 trades and mean ≤ 0 | continue to look 2 (also when < 20 trades) |
   | 2 | matches to 2027-10-31, pooled | ≥ 30 trades and one-sided 96% lower bound > 0 (α₂ = 0.04) | otherwise | — (< 30 trades: "inconclusive", reported) |

   No other looks. Interim checks are limited to data health: logger uptime, book-request errors and
   mapping counts. "Confirm" licenses a discussion of small live stakes. It does not license automatic
   deployment.
8. **Secondary (no decisions).** Settlement P&L per contract and per trade (C contracts, net of fee);
   the ask < 0.30 slice; net CLV under multiplicative and power de-vig; gross CLV; CLV vs the Kalshi
   close mid; mean contracts filled; counts of observation times blocked by Pinnacle age, invalid or
   inactive Pinnacle, and missing displayed size.
9. **Power** (normal approximation, per-trade sd 7.0 pts from the 2026 backtest, look-specific α):

   | True mean net CLV | n = 26 (2026 trades to 30 Jun) | n = 38 (2026 season) | n = 60 | n = 100 | n for 80% (α = 0.04) |
   |---|---|---|---|---|---|
   | +2.53 pts (backtest, this rule) | 31% (α₁) / 53% (α₂) | 46% / 68% | 68% / 85% | 90% / 97% | 52 |
   | +1.19 pts (Shin, 1-min, no age rule) | 7% / 19% | 10% / 24% | 16% / 33% | 26% / 48% | 234 |

   At 2026's trade rate, look 1 (≈ 26 trades) is unlikely to confirm. Look 2 (≈ 38) has about a 2-in-3
   chance if the backtest effect is real, and about 1-in-4 if the smaller estimate is. The 2026
   Kickoff window had only 3 trades, which is why the looks are not tied to Kickoff.
10. **Data and budget.** Kalshi books come from the odds logger (no extra requests). Pinnacle fixture ids
    come from the live poll's mapping where it caught the match, otherwise from fixture windows (billable,
    ≤ 40). History comes from `/historical-odds` (non-billable, but impossible once the month's quota is
    used). All of this is under ledger host `oddspapi_s11`, cap 600, **to be approved before the first
    `--fetch`**. Histories already cached for §10 are reused. Kalshi settlement: public `/markets?tickers=`,
    cap 20 (`kalshi_prereg`).
11. **Code.** `research/prereg_s11.py` (`--season 2027 --look 1|2 [--fetch]`), with `research/devig.py`,
    `research/pinnacle.py`, `research/hist_fetch.py` and the logger's `kalshi_books`. Tests:
    `research/test_prereg_s11.py`. Commit hash in §7.
