# VALORANT research — status

Last updated: 2026-11-17 (round 3). Covers `thunderedge` (branch `research/market-structure`) and
`valorant-pricing-model` (branch `fix/side-baseline-blend`), both pushed. Paper only; `src/quoting/`
and `src/main.py` in the pricing repo have not been touched.

## Done

| Phase | Output | Headline |
|---|---|---|
| 1. Market-structure study | `research/REPORT.md` | Churn, region lag and round variance: no edge. v2 half-win rates beat legacy but not the close. |
| 2. Line sources, tier-2 estimate, rating model | `research/REPORT_v2.md`, `research/LINE_SOURCES_SURVEY.md` | No edge vs the Thunderpick close; (b) better than v2 (not significant). |
| 3. Round-3 decisions | `research/REPORT_v3.md` | Push audit, logger stopgap, roster parser, tier-2 sample, §10 redesign, exploratory Pinnacle/Kalshi study. |
| Pre-registration | `research/PREREG_KICKOFF2027.md` | Churn rule + stale-line study (Pinnacle reference) + tier-2 stratum. Frozen at thunderedge `1838124`, pricing `5370daf`. |
| Logger hosting proposal | `research/LOGGER_HOSTING.md` | ~€5–7/month VPS with SQLite. Not deployed. |

**Important data fact (round 3):** vlr's `date_utc` / `data-utc-ts` is **US Eastern wall-clock, not UTC**.
Use `research/timeutil.py` (`vlr_to_utc`) whenever vlr times meet UTC timestamps.

## Running (Windows Task Scheduler on this laptop)

| Task | What | Every | Notes |
|---|---|---|---|
| `ThunderedgeOddsLogger` | `research/odds_logger.py` + `research/gap_detector.py` | 15 min | Post-result trigger; wake-to-run on; AC never sleeps. The gap table below is auto-updated. |
| `PricingShadowQuotes` | pricing `scripts/shadow_quotes.py` (legacy vs v2) | 15 min | Wake-to-run on. After ≥ 2026-11-20: `python scripts/shadow_quotes.py report --since 2026-11-17T08:12`. Unchanged per decision 6. |

## Approved (not yet used)

- **Pre-registration vlr pages: 155–175**, after the roster parser validated cleanly (5/5 pages,
  0 diffs). Fetch during Kickoff 2027 with `VLR_PAGE_BUDGET=2227`.
- **Pinnacle reference for prereg §10:** OddsPapi `oddspapi_prereg` cap 320 (≤ 6 billable),
  run after the window.

## Waiting on you

See the "Decisions needed" section of `research/REPORT_v3.md`.

## Budgets and ledgers

- **vlr.gg research ledger:** 2,052 = 2,017 + 5 roster-validation pages + 30 tier-2 sample pages,
  all approved. `vlr_fetch.py` refuses beyond `VLR_PAGE_BUDGET` (default 2000).
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

_Auto-updated 2026-11-17 20:08 UTC by `research/gap_detector.py` (last 14 days; a gap = > 20 min between runs)._

| Job | runs | gaps | missed polls | longest gap |
|---|---|---|---|---|
| odds logger | 40 | 2 | 38 | 9:30:02 (11-17 08:38Z) |
| shadow quotes | 12 | 1 | 37 | 9:30:03 (11-17 08:50Z) |

| Job | from (UTC) | to (UTC) | missed |
|---|---|---|---|
| shadow quotes | 2026-11-17 08:50 | 2026-11-17 18:20 | 37 |
| odds logger | 2026-11-17 08:38 | 2026-11-17 18:08 | 37 |
| odds logger | 2026-11-17 06:23 | 2026-11-17 07:04 | 1 |

<!-- gaps:end -->
