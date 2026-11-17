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
  non-billable `/historical-odds` call per match involved in a trigger. That is ≈ 100–250
  calls, hard-capped at 320 under the ledger label `oddspapi_prereg`. Raw OddsPapi data stays in
  `research/cache/` (gitignored; the terms forbid redistribution).
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
- `research/odds_logger.py` (post-result trigger, §10).
- `research/pinnacle.py`, `research/hist_fetch.py` and `research/timeutil.py` (Pinnacle reference, fixture mapping, vlr ET→UTC, §10).
- The rating model used for §10's model (a): `valorant-pricing-model/src/rating/` plus the frozen
  parameters and head-(a) coefficients in `research/out/rating_eval.json`.
- **Inputs:** `valorant_stats.db` (with the 2027 pages), `odds_snapshots.db`, `roster_snapshots`.
- **Outputs:** bet lists and the §5, §6 and §10 numbers (`research/out/prereg_2027.json`).

Results are produced only by these commits. A bug fix is allowed but logged in §9 with a diff.
`fetch_rosters.py` parses a vlr page layout that has not been checked on a 2027 page; the
one-page validation in its docstring comes first, and any parser fix is logged in §9.

- thunderedge evaluation commit: `18381241ff996cef7d12d1e1141a0f71191ae46f`
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

## 10. Stale-line study (reference = Pinnacle; amended 2026-11-17)

**Question:** after a result, are the same teams' *next* Thunderpick lines slow to update? The
reference for the fair price is **Pinnacle**, not our model: Pinnacle is sharp and reprices quickly,
so it defines fair value at the moment of the snapshot.

1. **Trigger.** The odds logger marks a match completed when it leaves vlr's live list. In the
   same poll it fetches every upcoming match involving either team, and stores those rows with
   `trigger = 'post_result'` and `ref_match` set to the finished match. Detection latency is at
   most one poll (15 min); if Thunderpick moves faster than that, this study cannot see it.
2. **Stale price.** The first two-sided Thunderpick quote stored by that trigger, at time t.
3. **Reference.** Pinnacle's de-vigged match-winner price standing at t. It comes from OddsPapi
   `/historical-odds`, fetched after the matches are played (see §4), using the latest Pinnacle
   record at or before t.
   - If Pinnacle has no record before t, or its line is suspended at t, the frozen model (a)
     is the reference instead (rating engine updated through t, head (a), 7-map pool).
   - **Those fallback rows are reported separately and carry no decision.**
4. **Signal.** Signal = reference − de-vigged stale Thunderpick price, for the upcoming match's
   team 1.
5. **Paper bet.** If |signal| ≥ 2 percentage points, back the side the signal favours at the
   stale Thunderpick price, 1 unit flat.
6. **Close.** The last two-sided Thunderpick quote before the match starts.
   CLV = log(stale price / closing price) for the backed side.
7. **Surprise size.** |result − pre-match probability| of the finished match. The pre-match
   probability is Pinnacle's price standing at that match's start, or model (b)'s if Pinnacle
   is missing.
8. **Metrics, per tier and per reference type.** All use a match-level bootstrap (10,000
   resamples):
   - mean CLV;
   - CLV by surprise bucket (0–0.3, 0.3–0.6, 0.6–1);
   - the OLS slope of CLV on surprise size;
   - the slope of (Thunderpick close − stale price) on the signal;
   - ROI at the stale price (descriptive).
9. **Success (tier 1, Pinnacle-referenced rows only)**, at look 1 only, with no interim looks:
   - **success:** the one-sided 95% lower bound on mean CLV is > 0, and the slope of CLV on
     surprise size is > 0 with its one-sided 95% lower bound > 0;
   - **partial:** CLV > 0 by that bound, and the slope is positive but not established;
   - **not supported:** otherwise.

   Tier 2 and model-(a)-referenced rows are descriptive.
10. **Kalshi** is studied historically (exploratory, `REPORT_v3.md`), not in this pre-registration.
11. **What "success" licenses:** a follow-up live paper-trading test of a stale-line rule in the
   pricing repo. Nothing more.
