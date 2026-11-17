# VALORANT research — status

Last updated: 2026-11-17. Covers `thunderedge` (branch `research/market-structure`) and
`valorant-pricing-model` (branch `fix/side-baseline-blend`). Paper only; `src/quoting/` and
`src/main.py` in the pricing repo have not been touched.

## Done

| Phase | Output | Headline |
|---|---|---|
| 1. Market-structure study | `research/REPORT.md` | Churn, region lag and round variance: no edge. v2 half-win rates beat legacy but not the close. Log5 blend fix in the pricing repo. |
| 2. Line sources, tier-2 estimate, rating model | `research/REPORT_v2.md`, `research/LINE_SOURCES_SURVEY.md` | See the bullets below. |
| Pre-registration | `research/PREREG_KICKOFF2027.md` | Churn rule (§3–§5), stale-line study (§10), tier-2 stratum. Code frozen at thunderedge `da4e535` and pricing `5370daf`. |
| Logger hosting proposal | `research/LOGGER_HOSTING.md` | Recommends a ~€5–7/month VPS with SQLite. Not deployed. |

**Phase 2 headlines (REPORT_v2):**
- **Line history:** no source covers 2023–24.
  - Kalshi: every trade from Sept 2025.
  - Polymarket: every fill from Aug 2025.
  - OddsPapi (free key): Pinnacle history for 2026 only. Thunderpick history is locked (403).
- **Tier-2:** ~8–13k Challengers match pages for 2023–26. Thunderpick coverage is unknown.
- **Rating model:**
  - (a) close model: median close error 4.5 pp. That misses the 2 pp bar.
  - (b) outcome model: better than v2 (Δ −0.015 log loss, CI just includes 0), and level with
    the close on two-sided rows.
  - No edge, and CLV is negative where the model disagrees most with the market.

## Running (Windows Task Scheduler on this laptop)

| Task | What | Every | Notes |
|---|---|---|---|
| `ThunderedgeOddsLogger` | `research/odds_logger.py`: vlr Thunderpick + Kalshi → `data/odds_snapshots.db` | 15 min | Now also detects completed matches and snapshots the teams' next matches (`trigger='post_result'`). Misses polls while the laptop sleeps (~10 h missed on 2026-11-17). |
| `PricingShadowQuotes` | pricing `scripts/shadow_quotes.py`: legacy vs v2 pre-match quotes → `data/shadow_quotes.db` | 15 min | Started 2026-11-17 08:12Z. After ≥ 2026-11-20 run `python scripts/shadow_quotes.py report --since 2026-11-17T08:12`, then unregister the task. |

## Waiting on you

1. **Tier-2 Phase 0:** 30 vlr pages, then a Phase 1 budget (REPORT_v2 §B).
2. **Historical stale-line test:** ~720 OddsPapi + ~700 Kalshi calls; Polymarket optional (REPORT_v2 §A.3).
3. **OddsPapi paid plan:** for Thunderpick history and lag.
4. **Pre-registration data:** ~155–175 vlr pages, plus the 1-page roster-parser check (prereg §4, §7).
5. **Logger hosting and in-season cadence** (LOGGER_HOSTING.md). Required before the first Kickoff 2027 match.
6. **v2 rates swap:** after the shadow report.

## Budgets and ledgers

- **vlr.gg research ledger:** 2,017 pages (`research/cache/request_ledger.csv`), over the ~2,000 cap.
  `research/vlr_fetch.py` refuses further requests unless `VLR_PAGE_BUDGET` is raised.
- **archive.org:** 873 logged requests + a 40-match probe (approved ~900).
- **Odds logger:** ~96 vlr requests/day off-season (1 list page per poll). It will be much higher
  in season unless the cadence is tightened.
- **OddsPapi:** key in `valorant-pricing-model/.env` (gitignored). 26 of 250 billable requests used
  this month. Raw OddsPapi data must not go into the public repos.

## Next deadlines

- **Before the first VCT 2027 tier-1 match:**
  - logger on always-on hosting;
  - roster parser validated, roster snapshots captured 2–48 h before each team's first match;
  - pre-registration code unchanged since the freeze, or any changes logged in §9.
- **≥ 2026-11-20:** shadow-quote report for the v2 swap decision.
