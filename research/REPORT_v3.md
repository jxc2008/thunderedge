# VALORANT research — round 3 report

_Generated 2026-11-17 20:20 UTC by `research/make_report_v3.py`. Paper only. Item 5 is **exploratory**: no pre-registration, three fixed thresholds, nothing searched._

## Overview

| # | Item | Verdict |
|---|---|---|
| 0 | Push both branches | Done after audit: no `.env` or OddsPapi data tracked, now or in history. A Kalshi API key ID is already public on `origin/feature/market-maker` (not from this work). |
| 1 | Logger stopgap | AC sleep and AC hibernate are 'never'; wake-to-run is on for both tasks; the gap detector writes to STATUS.md after every poll. |
| 2 | Roster parser | Clean: 0 diffs vs manual reading on 5 pages (31 roster entries). The 155–175 pre-registration pages are approved by your rule. |
| 3 | Tier-2 sample (30 pages) | ≈ 10,738 Challengers match pages for 2023–26 [6,944, 14,160]. Thunderpick prices only 2/10. Tier-2 margin ≈ 9–10% vs 7.1% on tier-1 (n=2, indicative). Full scrape proposed, not started. |
| 4 | PREREG §10 redesign | Done: Pinnacle is the reference; model (a) is a separately reported fallback. Re-frozen with an ET-timezone bug fix: thunderedge `1838124`, pricing `5370daf`. |
| 5 | Historical test (exploratory) | STOPPED before (b): the reference failed the stop rule. Details in §5. |
| 6 | Shadow quoting | Unchanged; v2 and (b) keep running. |

## 0. Push audit

| Repo | `.env` / OddsPapi files tracked now | ...in any commit (all refs) | Key string in history | Pushed |
|---|---|---|---|---|
| thunderedge | none | `.env.example` only: a template, but commit `2415a09` (Apr 2026, `origin/feature/market-maker`) put a real `KALSHI_KEY_ID` in it | none | `research/market-structure` |
| valorant-pricing-model | none | none | none | `fix/side-baseline-blend` |

**Verdict:** clean to push. Separately, the Kalshi key ID has been public since April 2026; rotating that Kalshi API key is cheap.

## 1. Logger stopgap until the VPS

| Setting | Before | After |
|---|---|---|
| AC sleep (`standby-timeout-ac`) | never (already) | never |
| AC hibernate | never (already) | never |
| Wake timers on AC | enabled (already) | enabled |
| `ThunderedgeOddsLogger` wake-to-run | off | **on** |
| `PricingShadowQuotes` wake-to-run | off | **on** |
| Gap detector | none | `research/gap_detector.py`, after every logger poll, writes to STATUS.md |

The 9.5-hour gap on 2026-11-17 (08:38–18:08Z) did **not** come from the AC sleep timeout, which was already 'never'. The laptop is Modern Standby (S0) and the event log has no transitions in that window. That points to lid-closed or on-battery standby, where tasks don't run. Wake-to-run may help on AC. Battery sleep (5 min) and the lid action are unchanged; tell me if you want lid-close-on-AC set to 'do nothing'.

_Auto-updated 2026-11-17 20:20 UTC by `research/gap_detector.py` (last 14 days; a gap = > 20 min between runs)._

| Job | runs | gaps | missed polls | longest gap |
|---|---|---|---|---|
| odds logger | 40 | 2 | 38 | 9:30:02 (11-17 08:38Z) |
| shadow quotes | 12 | 1 | 37 | 9:30:03 (11-17 08:50Z) |

| Job | from (UTC) | to (UTC) | missed |
|---|---|---|---|
| shadow quotes | 2026-11-17 08:50 | 2026-11-17 18:20 | 37 |
| odds logger | 2026-11-17 08:38 | 2026-11-17 18:08 | 37 |
| odds logger | 2026-11-17 06:23 | 2026-11-17 07:04 | 1 |

**Verdict:** done. Only hosting truly fixes the sleep gaps.

## 2. Roster parser validation (5 pages, counted toward the cap)

| Team | Active five parsed | Non-playing parsed (role) | Manual reading of the page | Diff |
|---|---|---|---|---|
| Sentinels | johnqt, keiko, OXY, brawk, canezerra (5) | Zellsis (Sub); Zyto (manager); Ewok (head coach); GUNTER (assistant coach) | same people, same roles | 0 |
| FNATIC | kaajak, Cloud (2) | CoJo (manager) | same people, same roles | 0 |
| Paper Rex | invy, f0rsakeN, something (3) | Tommy (manager); alecks (coach); Panda (performance coach) | same people, same roles | 0 |
| EDward Gaming | ZmjjKK, Jieni7, stew (3) | zjc (Sub); Hibari (manager); Autumn (head coach); Indigo (coach); signed (coach) | same people, same roles | 0 |
| Team Liquid | kamo, GSR (2) | nAts (Inactive); cauzed (manager); Mol (manager); LohaN (head coach); yaotziN. (assistant coach); 7Teen (performance coach) | same people, same roles | 0 |

Teams showing fewer than 5 active players are mid-off-season rosters, not parse errors. Under the rule they become 'no expected five' and are excluded.

**Verdict:** clean. The 155–175 pre-registration pages are approved and will be fetched during Kickoff 2027 under a raised `VLR_PAGE_BUDGET`.

## 3. Tier-2 (Challengers / VCL) sample — 30 pages, ledger now 2,052

| Measure | Value | n / basis |
|---|---|---|
| VCL events on vlr, 2023–26 | 271 (68 / 69 / 66 / 68 by year) | all 6 listing pages (`/events/?tier=61`) |
| Matches per event | 39.6 [25.6, 52.2] | 8 events, stratified 2 per year |
| **Challengers match pages, 2023–26** | **≈ 10,738 [6,944, 14,160]** | events × matches/event (+ ~271 list pages) |
| Thunderpick **priced** (closing price shown) | 2/10 = 20% [6%, 51%] | 10 random completed matches |
| Thunderpick listed (incl. 'pending', never priced) | 8/10 [49%, 94%] | same |
| Thunderpick margin, tier-2 | 1.093, 1.100 | 2 upcoming off-season matches (China National Tournament); no Challengers are live in November |
| Thunderpick margin, tier-1 (reference) | 1.071 (2026) / 1.082 (2023–25) | 489 Wayback two-sided snapshots |

**Full-scrape budget proposal (not started):**

| Option | Scope | Pages | Throttle | Purpose |
|---|---|---|---|---|
| A (recommended) | VCL 2025–26 | ≈ 5,444 [3,568, 7,136] | ≤ 1,000/day, ≈ 6 days | REPORT_v2 D.5 ablation (rounds and lineups for every match); tier-2 underdog ROI on the ~20% that is priced |
| B | VCL 2023–26 | ≈ 11,009 | ≈ 11 days | same, more history; only if A's ablation helps |

**Verdict:** tier-2 is ~5× tier-1 in volume, but Thunderpick prices only about a fifth of it at a higher margin. It is worth scraping for rating-model training data, not as a betting universe.

## 4. PREREG §10 redesign

| Change | Where |
|---|---|
| Reference = Pinnacle de-vigged price standing at the snapshot time t (OddsPapi history, fetched after the matches) | §10.3, `prereg_kickoff2027.py`, `pinnacle.py` |
| Signal = Pinnacle − stale de-vigged Thunderpick; bet if ≥ 2 pts at the stale price; CLV vs the Thunderpick close | §10.4–6 |
| Model (a) only when Pinnacle is missing or pulled at t; reported separately, no decision | §10.3, §10.9 |
| Surprise size from Pinnacle's pre-match price (model (b) fallback) | §10.7 |
| OddsPapi budget: ≤ 6 billable + ≈ 100–250 history calls, hard cap 320 (`oddspapi_prereg`) | §4 |
| **Bug fix:** vlr times are US Eastern; the code now converts to UTC (`timeutil.py`) | §9, all timing |
| Hashes re-recorded: thunderedge `18381241ff996cef7d12d1e1141a0f71191ae46f`, pricing `5370dafe19433f787fd1fb0ca37529d9078d4930` | §7 |

**Verdict:** done before any 2027 data. Kalshi is studied only historically (item 5).

## 5. Historical test, 2026 tier-1 — EXPLORATORY

Requests: OddsPapi 643 of 720 approved (607 OK, 36 'no historical odds'); Kalshi 571 of 700; Polymarket 0.
Matched: 650 vlr matches → 599 with Pinnacle history, 567 with Kalshi 1-min quotes; 911 (result M → next match N of a team in M, within 7 days) pairs.

**Match end (vlr).** End = vlr start (converted ET → UTC) + Σ map durations + 10 min per break. Cross-check: Kalshi's market reaches 0.98/0.02 a median -6 min after this estimate (IQR -12 to 2, n = 524). The vlr-based end is good to about 10 minutes. Before the ET→UTC fix this gap was about +235 min, which is how the timezone problem was found.

### 5.0 Reference check (run first)

| R1 — Pinnacle record resolution (pre-match, VALORANT) | Value |
|---|---|
| fixtures with history | 579 |
| records before start, median per fixture | 38 |
| gap between records: median (pooled) | **0.9 min** |
| median of per-fixture median gaps | 1.5 min |
| gap p90 / max | 116 / 10,121 min |

| R2 — after each result, Pinnacle on the teams' next match | Value |
|---|---|
| (M, N) pairs | 911 |
| line active at end(M) | 8 (1%) |
| line pulled (suspended) at end(M) | 1 (0%) |
| no line yet at end(M) | 864 (95%) |
| no Pinnacle history for N at all | 38 (4%) |
| **time to Pinnacle's first price change** (active lines; Kaplan–Meier median [p25, p75]) | **241 min** [102, 449] |
| …first change of ≥ 1 pt | 645 min |
| baseline: first change from 3 h before end(M) | 344 min |
| absent/pulled lines: minutes until an active line appears (median) | 2,801 |
| absent/pulled and never active before N starts | 17 |
| reprice median, surprise 0.0-0.3 | 241 min (n=4) |
| reprice median, surprise 0.3-0.6 | 227 min (n=1) |
| reprice median, surprise 0.6-1.01 | 365 min (n=3) |

| Why so few live lines at end(M) | Value |
|---|---|
| time from end(M) to the next match's start: median [p25, p75] | 71 h [45, 140] |
| next match within 24 h | 14% |
| Pinnacle's first record before the match: median [p10, p90] | 23 h [9, 65] |
| Kalshi market for the next match quoting at end(M) | 37 of 911 |

**Stop rule** (median reprice > 60 min or median record gap > 15 min): reprice 241 min, gap 0.9 min → **STOP — (b) and (c) not run**.

### 5a. Kalshi lag after results (vs Pinnacle's move by end(M) + 60 min, |move| ≥ 2 pts)

| Slice | n | Kalshi to 50%: median [p25, p75] min | never | Kalshi to 90% | never | Pinnacle to 50% / 90% |
|---|---|---|---|---|---|---|
| all | 0 | — | — | — | — | — |
| 0.0-0.3 | 0 | — | — | — | — | — |
| 0.3-0.6 | 0 | — | — | — | — | — |
| 0.6-1.01 | 0 | — | — | — | — | — |

**Verdict (5):** the reference check failed, so (b) and (c) were not run.
- **Pinnacle is fine-grained once a line exists** (median gap under 1 min).
- **But when a result lands, the teams' next-match line almost never exists yet**: 95% absent. Pinnacle opens VALORANT lines ~1 day ahead, while the next match is ~3 days away.
- **In the 8 cases where the line was up,** Pinnacle took a median ~4 h to change price at all. That's no faster than its baseline on those same lines (~5.7 h), so it isn't reacting to the result.
- **Kalshi is the same story:** its next-match market was quoting at the result in only 37/911 cases.
- **So (a) had no qualifying pairs (n = 0).** The post-result stale-line effect is structurally rare in tier-1 VCT: by the time the next line opens, the result is already priced in.

Caveats:
- Kalshi quotes are 1-minute candle closes, forward-filled; depth at the ask is unknown, so fills of more than a few hundred contracts are optimistic.
- Pinnacle is OddsPapi's record of changes (free plan).
- The 6-hour result window, the 2-point move threshold and 60-minute settle are fixed choices, not tuned.

## 6. Shadow quoting

Unchanged. `PricingShadowQuotes` keeps logging legacy vs v2; model (b) remains in research only. The ≥ 2026-11-20 report is still due.

## Side findings

- **vlr times are US Eastern, not UTC**: OddsPapi true start − vlr = +3.92 h median (n = 24); +5 h in EST months.
  - Fixed in all code that compares absolute times.
  - REPORT §0.2's Wayback '12.8 h before start' is really ≈ 17 h.
  - Season-relative results are unaffected.
- **Pinnacle often has no line at the moment a result lands** (§5.0). This limits any immediate post-result comparison, live or historical.

## Decisions needed

1. **PREREG §10 viability.** With Pinnacle almost never live when a result lands, §10's primary
   (Pinnacle-referenced) rows will be few; most rows fall back to model (a). Options:
   - **(A)** keep §10 as is and accept a small, mostly descriptive sample;
   - **(B)** re-target §10 to "stale at open": when Pinnacle first posts the next match, compare it
     with the Thunderpick price already standing. This tests whether Thunderpick lines set before
     the result are stale;
   - **(C)** drop §10.

   I'd pick (B). Any change must be logged in §9 and re-frozen before Kickoff.
2. **Item 5 follow-up.** Run (c)'s *general* Pinnacle→Kalshi lag and the k = 2/3/5 taking simulation
   over the whole pre-match period (not just post-result windows)? It uses data already downloaded
   (0 new requests) and stays exploratory. The stop rule blocked it as written, so it needs your
   go-ahead.
3. **Tier-2 full scrape:** option A (VCL 2025–26, ≈ 5.4k pages over ~6 days) or B (2023–26, ≈ 11k),
   or neither. Tier-2 is mainly rating-model training data: Thunderpick prices only ~20% of it.
4. **Laptop:** set lid-close-on-AC to "do nothing"? That's the remaining sleep cause short of the VPS.
5. **Kalshi key:** consider rotating the Kalshi API key whose ID is public in `.env.example`
   history (`origin/feature/market-maker`, commit `2415a09`, April 2026).
6. **Still open:** VPS hosting choice and in-season cadence (LOGGER_HOSTING.md), the shadow-report
   swap decision after 2026-11-20, and the OddsPapi paid plan (Thunderpick history).
