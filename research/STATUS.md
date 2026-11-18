# VALORANT research — status

Last updated: 2026-11-18 (round 5). Covers `thunderedge` (branch `research/market-structure`) and
`valorant-pricing-model` (branch `fix/side-baseline-blend`), both pushed (through round 5). Paper only; `src/quoting/`
and `src/main.py` in the pricing repo have not been touched.

## Done

| Phase | Output | Headline |
|---|---|---|
| 1. Market-structure study | `research/REPORT.md` | Churn, region lag and round variance: no edge. v2 half-win rates beat legacy but not the close. |
| 2. Line sources, tier-2 estimate, rating model | `research/REPORT_v2.md`, `research/LINE_SOURCES_SURVEY.md` | No edge vs the Thunderpick close; (b) better than v2 (not significant). |
| 3. Round-3 decisions | `research/REPORT_v3.md` | Push audit, logger stopgap, roster parser, tier-2 sample, §10 redesign, exploratory Pinnacle/Kalshi study. |
| 4. Round-4 decisions | `research/REPORT_v4.md` | §10 stale at open, exploratory full-window Pinnacle/Kalshi study, tier-2 scrape (partial) + ablation, lid, Kalshi pre-check. |
| 5. Round-5 decisions | `research/REPORT_v5.md` | Push + placeholder `.env.example`, tier-2 priors, taking sim rescored vs Pinnacle close, stale-at-open follow-ups, windowed Pinnacle-open poll (enabled), Kalshi order books. |
| Pre-registration | `research/PREREG_KICKOFF2027.md` | Churn rule + §10 stale at open (Pinnacle reference) + tier-2 stratum. Frozen at thunderedge `034b62f`, pricing `5370daf`. |
| Logger hosting proposal | `research/LOGGER_HOSTING.md` | ~€5–7/month VPS with SQLite. Not deployed. |

**Important data fact (round 3):** vlr's `date_utc` / `data-utc-ts` is **US Eastern wall-clock, not UTC**.
Use `research/timeutil.py` (`vlr_to_utc`) whenever vlr times meet UTC timestamps.

## Running (Windows Task Scheduler on this laptop)

| Task | What | Every | Notes |
|---|---|---|---|
| `ThunderedgeOddsLogger` | `research/odds_logger.py` + `research/gap_detector.py` | 15 min | Post-result trigger; wake-to-run on; AC never sleeps; lid on AC does nothing. Logs Kalshi top-5 order books (`kalshi_books`, change-only). Also runs `pinnacle_open_poll.py`: **enabled**, tier-1 only, T−96h..start, every 6 h; 30-day cap 180 (`hist_fetch.CAP_30D`); costs 0 until Kickoff 2027 fixtures are within 96 h. The gap table below is auto-updated. |
| `PricingShadowQuotes` | pricing `scripts/shadow_quotes.py` (legacy vs v2) | 15 min | Wake-to-run on. After ≥ 2026-11-20: `python scripts/shadow_quotes.py report --since 2026-11-17T08:12`, then `python scripts/shadow_compare.py` (v2 vs (b) vs Kalshi mid). Unchanged per decision 6. |

## Approved (not yet used)

- **Pre-registration vlr pages: 155–175**, after the roster parser validated cleanly (5/5 pages,
  0 diffs). Fetch during Kickoff 2027 with `VLR_PAGE_BUDGET=2227`.
- **Pinnacle reference for prereg §10:** OddsPapi `oddspapi_prereg` cap 320 (≤ 6 billable),
  run after the window.

## Waiting on you

See the "Decisions needed" section of `research/REPORT_v5.md` (supersedes v4).

## Budgets and ledgers

- **vlr.gg research ledger:** 6,450 = 2,052 (round 3) + 4,398 tier-2 scrape (130 lists + match pages;
  approved ~5,400, ceiling 7,452). Scrape stopped on a local DNS failure with 690 pages left and is **closed** (user decision, round 5);
  open qualifiers skipped. `cache/tier2_STOP` stays in place. `vlr_fetch.py` refuses beyond `VLR_PAGE_BUDGET` (default 2000).
- **archive.org:** 873 logged requests + a 40-match probe (approved ~900).
- **Historical study (round 3):** see `research/cache/hist/ledger.csv`.
  - Kalshi: 571 used of 700 approved (570 candles + 1 series call).
  - OddsPapi: ≤ 720 approved (8 billable fixture calls + history).
- **Odds logger:** ~96 vlr requests/day off-season; more in season, plus 1–2 per result for the
  post-result trigger.
- **OddsPapi key:** in `valorant-pricing-model/.env` (gitignored). Raw OddsPapi data stays in
  `research/cache/` only (the terms forbid redistribution).

## Next deadlines

- **Before the first VCT 2027 tier-1 match:**
  - logger on always-on hosting;
  - roster parser validated, roster snapshots captured 2–48 h before each team's first match;
  - pre-registration code unchanged since the freeze, or any changes logged in §9.
- **≥ 2026-11-20:** shadow-quote report for the v2 swap decision.

## Missed polls

<!-- gaps:start -->

_Auto-updated 2026-11-18 07:53 UTC by `research/gap_detector.py` (last 14 days; a gap = > 20 min between runs)._

| Job | runs | gaps | missed polls | longest gap |
|---|---|---|---|---|
| odds logger | 74 | 7 | 50 | 9:30:02 (11-17 08:38Z) |
| shadow quotes | 41 | 4 | 53 | 9:30:03 (11-17 08:50Z) |

| Job | from (UTC) | to (UTC) | missed |
|---|---|---|---|
| odds logger | 2026-11-18 05:27 | 2026-11-18 07:07 | 5 |
| odds logger | 2026-11-18 04:53 | 2026-11-18 05:27 | 1 |
| shadow quotes | 2026-11-18 04:50 | 2026-11-18 07:20 | 8 |
| odds logger | 2026-11-18 03:08 | 2026-11-18 04:10 | 3 |
| shadow quotes | 2026-11-18 03:05 | 2026-11-18 04:20 | 4 |
| odds logger | 2026-11-18 01:25 | 2026-11-18 02:22 | 2 |
| shadow quotes | 2026-11-18 01:06 | 2026-11-18 02:35 | 4 |
| odds logger | 2026-11-18 00:53 | 2026-11-18 01:25 | 1 |
| shadow quotes | 2026-11-17 08:50 | 2026-11-17 18:20 | 37 |
| odds logger | 2026-11-17 08:38 | 2026-11-17 18:08 | 37 |
| odds logger | 2026-11-17 06:23 | 2026-11-17 07:04 | 1 |

<!-- gaps:end -->
