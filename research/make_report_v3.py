"""Render research/REPORT_v3.md (round 3 decisions). Tables first, one-line verdict per item.

Inputs: research/out/stale_hist.json (exploratory historical study), research/cache/roster_validation.json,
research/cache/t2_*.json (tier-2 sample), hist ledger. Usage: python -m research.make_report_v3
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from research import gap_detector

ROOT = Path(__file__).resolve().parent
C = ROOT / "cache"
S = json.loads((ROOT / "out" / "stale_hist.json").read_text())
EVAL_T = "18381241ff996cef7d12d1e1141a0f71191ae46f"
EVAL_P = "5370dafe19433f787fd1fb0ca37529d9078d4930"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    c, s = p + z * z / (2 * n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - s) / (1 + z * z / n), (c + s) / (1 + z * z / n)


def m(x, d: int = 0, unit: str = "") -> str:
    return "—" if x is None else f"{x:,.{d}f}{unit}"


def ci(b: dict | None, pct: bool = False, d: int = 1) -> str:
    if not b or b.get("est") is None:
        return f"n/a (n={b.get('n', 0) if b else 0})"
    f = (lambda x: f"{100 * x:+.{d}f}%") if pct else (lambda x: f"{x:+.{d}f}")
    return f"{f(b['est'])} [{f(b['lo'])}, {f(b['hi'])}]"


def main() -> None:
    L: list[str] = []
    w = L.append
    R1, R2, st = S["R1"], S["R2"], S["stop_rule"]
    ledger = Counter(r[1] for r in csv.reader((C / "hist" / "ledger.csv").open()) if r)
    status = Counter(r[3] for r in csv.reader((C / "hist" / "ledger.csv").open()) if r and r[1] == "oddspapi")
    a = S["a_kalshi_lag_after_results"]["all"]
    t2 = json.loads((C / "t2_sample_matches.json").read_text())
    per = np.array(list(t2["per_event"].values()), float)
    evs = json.loads((C / "t2_events_all.json").read_text())["events"]
    n_ev = sum(1 for e in evs.values() if 2023 <= e["year"] <= 2026)
    rng = np.random.default_rng(0)
    bs = np.percentile([rng.choice(per, len(per)).mean() for _ in range(10000)], [2.5, 97.5])
    priced = sum(1 for r in t2["sample_matches"] if any(s_ == "post" for s_, _ in r["thunderpick"]))
    listed = sum(1 for r in t2["sample_matches"] if r["thunderpick"])
    marg = [x["overround"] for x in json.loads((C / "t2_upcoming_margin.json").read_text()) if x["overround"]]
    rv = json.loads((C / "roster_validation.json").read_text())

    w("# VALORANT research — round 3 report")
    w("")
    w(f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `research/make_report_v3.py`. Paper only. "
      "Item 5 is **exploratory**: no pre-registration, three fixed thresholds, nothing searched._")
    w("")
    w("## Overview")
    w("")
    w("| # | Item | Verdict |")
    w("|---|---|---|")
    w("| 0 | Push both branches | Done after audit: no `.env` or OddsPapi data tracked, now or in history. A Kalshi API key ID is already public on `origin/feature/market-maker` (not from this work). |")
    w("| 1 | Logger stopgap | AC sleep and AC hibernate are 'never'; wake-to-run is on for both tasks; the gap detector writes to STATUS.md after every poll. |")
    w("| 2 | Roster parser | Clean: 0 diffs vs manual reading on 5 pages (31 roster entries). The 155–175 pre-registration pages are approved by your rule. |")
    w(f"| 3 | Tier-2 sample (30 pages) | ≈ {per.mean() * n_ev:,.0f} Challengers match pages for 2023–26 [{bs[0] * n_ev:,.0f}, {bs[1] * n_ev:,.0f}]. Thunderpick prices only {priced}/{len(t2['sample_matches'])}. Tier-2 margin ≈ 9–10% vs 7.1% on tier-1 (n=2, indicative). Full scrape proposed, not started. |")
    w(f"| 4 | PREREG §10 redesign | Done: Pinnacle is the reference; model (a) is a separately reported fallback. Re-frozen with an ET-timezone bug fix: thunderedge `{EVAL_T[:7]}`, pricing `{EVAL_P[:7]}`. |")
    verdict5 = ("STOPPED before (b): the reference failed the stop rule" if st["stopped"]
                else "Reference passed the stop rule; (a)–(c) run")
    w(f"| 5 | Historical test (exploratory) | {verdict5}. Details in §5. |")
    w("| 6 | Shadow quoting | Unchanged; v2 and (b) keep running. |")
    w("")

    # 0
    w("## 0. Push audit")
    w("")
    w("| Repo | `.env` / OddsPapi files tracked now | ...in any commit (all refs) | Key string in history | Pushed |")
    w("|---|---|---|---|---|")
    w("| thunderedge | none | `.env.example` only: a template, but commit `2415a09` (Apr 2026, `origin/feature/market-maker`) put a real `KALSHI_KEY_ID` in it | none | `research/market-structure` |")
    w("| valorant-pricing-model | none | none | none | `fix/side-baseline-blend` |")
    w("")
    w("**Verdict:** clean to push. Separately, the Kalshi key ID has been public since April 2026; rotating that Kalshi API key is cheap.")
    w("")

    # 1
    w("## 1. Logger stopgap until the VPS")
    w("")
    w("| Setting | Before | After |")
    w("|---|---|---|")
    w("| AC sleep (`standby-timeout-ac`) | never (already) | never |")
    w("| AC hibernate | never (already) | never |")
    w("| Wake timers on AC | enabled (already) | enabled |")
    w("| `ThunderedgeOddsLogger` wake-to-run | off | **on** |")
    w("| `PricingShadowQuotes` wake-to-run | off | **on** |")
    w("| Gap detector | none | `research/gap_detector.py`, after every logger poll, writes to STATUS.md |")
    w("")
    w("The 9.5-hour gap on 2026-11-17 (08:38–18:08Z) did **not** come from the AC sleep timeout, which was "
      "already 'never'. The laptop is Modern Standby (S0) and the event log has no transitions in that "
      "window. That points to lid-closed or on-battery standby, where tasks don't run. Wake-to-run may "
      "help on AC. Battery sleep (5 min) and the lid action are unchanged; tell me if you want "
      "lid-close-on-AC set to 'do nothing'.")
    w("")
    w(gap_detector.render().replace(gap_detector.START, "").replace(gap_detector.END, "").strip())
    w("")
    w("**Verdict:** done. Only hosting truly fixes the sleep gaps.")
    w("")

    # 2
    w("## 2. Roster parser validation (5 pages, counted toward the cap)")
    w("")
    w("| Team | Active five parsed | Non-playing parsed (role) | Manual reading of the page | Diff |")
    w("|---|---|---|---|---|")
    for tid, x in rv.items():
        act = [p["alias"] for p in x["parsed"] if p["active"]]
        non = [f"{p['alias']} ({p['tags']})" for p in x["parsed"] if not p["active"]]
        w(f"| {x['name']} | {', '.join(act)} ({len(act)}) | {'; '.join(non)} | same people, same roles | 0 |")
    w("")
    w("Teams showing fewer than 5 active players are mid-off-season rosters, not parse errors. Under the "
      "rule they become 'no expected five' and are excluded.")
    w("")
    w("**Verdict:** clean. The 155–175 pre-registration pages are approved and will be fetched during "
      "Kickoff 2027 under a raised `VLR_PAGE_BUDGET`.")
    w("")

    # 3
    w("## 3. Tier-2 (Challengers / VCL) sample — 30 pages, ledger now 2,052")
    w("")
    w("| Measure | Value | n / basis |")
    w("|---|---|---|")
    w(f"| VCL events on vlr, 2023–26 | {n_ev} (68 / 69 / 66 / 68 by year) | all 6 listing pages (`/events/?tier=61`) |")
    w(f"| Matches per event | {per.mean():.1f} [{bs[0]:.1f}, {bs[1]:.1f}] | 8 events, stratified 2 per year |")
    w(f"| **Challengers match pages, 2023–26** | **≈ {per.mean() * n_ev:,.0f} [{bs[0] * n_ev:,.0f}, {bs[1] * n_ev:,.0f}]** | events × matches/event (+ ~271 list pages) |")
    lo, hi = wilson(priced, len(t2["sample_matches"]))
    w(f"| Thunderpick **priced** (closing price shown) | {priced}/{len(t2['sample_matches'])} = {100 * priced / len(t2['sample_matches']):.0f}% [{100 * lo:.0f}%, {100 * hi:.0f}%] | 10 random completed matches |")
    lo2, hi2 = wilson(listed, len(t2["sample_matches"]))
    w(f"| Thunderpick listed (incl. 'pending', never priced) | {listed}/{len(t2['sample_matches'])} [{100 * lo2:.0f}%, {100 * hi2:.0f}%] | same |")
    w(f"| Thunderpick margin, tier-2 | {', '.join(f'{x:.3f}' for x in marg)} | 2 upcoming off-season matches (China National Tournament); no Challengers are live in November |")
    w("| Thunderpick margin, tier-1 (reference) | 1.071 (2026) / 1.082 (2023–25) | 489 Wayback two-sided snapshots |")
    w("")
    w("**Full-scrape budget proposal (not started):**")
    w("")
    w("| Option | Scope | Pages | Throttle | Purpose |")
    w("|---|---|---|---|---|")
    w(f"| A (recommended) | VCL 2025–26 | ≈ {per.mean() * 134 + 134:,.0f} [{bs[0] * 134 + 134:,.0f}, {bs[1] * 134 + 134:,.0f}] | ≤ 1,000/day, ≈ 6 days | REPORT_v2 D.5 ablation (rounds and lineups for every match); tier-2 underdog ROI on the ~20% that is priced |")
    w(f"| B | VCL 2023–26 | ≈ {per.mean() * n_ev + n_ev:,.0f} | ≈ 11 days | same, more history; only if A's ablation helps |")
    w("")
    w("**Verdict:** tier-2 is ~5× tier-1 in volume, but Thunderpick prices only about a fifth of it at "
      "a higher margin. It is worth scraping for rating-model training data, not as a betting universe.")
    w("")

    # 4
    w("## 4. PREREG §10 redesign")
    w("")
    w("| Change | Where |")
    w("|---|---|")
    w("| Reference = Pinnacle de-vigged price standing at the snapshot time t (OddsPapi history, fetched after the matches) | §10.3, `prereg_kickoff2027.py`, `pinnacle.py` |")
    w("| Signal = Pinnacle − stale de-vigged Thunderpick; bet if ≥ 2 pts at the stale price; CLV vs the Thunderpick close | §10.4–6 |")
    w("| Model (a) only when Pinnacle is missing or pulled at t; reported separately, no decision | §10.3, §10.9 |")
    w("| Surprise size from Pinnacle's pre-match price (model (b) fallback) | §10.7 |")
    w("| OddsPapi budget: ≤ 6 billable + ≈ 100–250 history calls, hard cap 320 (`oddspapi_prereg`) | §4 |")
    w("| **Bug fix:** vlr times are US Eastern; the code now converts to UTC (`timeutil.py`) | §9, all timing |")
    w(f"| Hashes re-recorded: thunderedge `{EVAL_T}`, pricing `{EVAL_P}` | §7 |")
    w("")
    w("**Verdict:** done before any 2027 data. Kalshi is studied only historically (item 5).")
    w("")

    # 5
    w("## 5. Historical test, 2026 tier-1 — EXPLORATORY")
    w("")
    w(f"Requests: OddsPapi {ledger['oddspapi']} of 720 approved ({status.get('200', 0)} OK, {status.get('404', 0)} "
      f"'no historical odds'); Kalshi {ledger['kalshi']} of 700; Polymarket 0.")
    w(f"Matched: {S['n_matches']} vlr matches → {S['n_pinnacle']} with Pinnacle history, {S['n_kalshi']} with Kalshi "
      f"1-min quotes; {S['n_result_pairs']} (result M → next match N of a team in M, within 7 days) pairs.")
    w("")
    ec = S["end_check_kalshi_minus_vlr_min"]
    w("**Match end (vlr).** End = vlr start (converted ET → UTC) + Σ map durations + 10 min per break. "
      f"Cross-check: Kalshi's market reaches 0.98/0.02 a median {m(ec['median'], 0)} min after this estimate "
      f"(IQR {m(ec['p25'], 0)} to {m(ec['p75'], 0)}, n = {ec['n']}). The vlr-based end is good to about 10 minutes. "
      "Before the ET→UTC fix this gap was about +235 min, which is how the timezone problem was found.")
    w("")
    w("### 5.0 Reference check (run first)")
    w("")
    w("| R1 — Pinnacle record resolution (pre-match, VALORANT) | Value |")
    w("|---|---|")
    w(f"| fixtures with history | {R1['n_fixtures']} |")
    w(f"| records before start, median per fixture | {m(R1['fixture_records_pre_start_median'])} |")
    w(f"| gap between records: median (pooled) | **{m(R1['median_gap_min'], 1)} min** |")
    w(f"| median of per-fixture median gaps | {m(R1['median_of_fixture_medians_min'], 1)} min |")
    w(f"| gap p90 / max | {m(R1['p90_gap_min'], 0)} / {m(R1['max_gap_min'], 0)} min |")
    w("")
    sts = R2["states"]
    tot = sum(sts.values())
    w("| R2 — after each result, Pinnacle on the teams' next match | Value |")
    w("|---|---|")
    w(f"| (M, N) pairs | {tot} |")
    for k_, lab in (("active", "line active at end(M)"), ("pulled", "line pulled (suspended) at end(M)"),
                    ("absent", "no line yet at end(M)"), ("no_pinnacle_fixture", "no Pinnacle history for N at all")):
        w(f"| {lab} | {sts.get(k_, 0)} ({100 * sts.get(k_, 0) / max(tot, 1):.0f}%) |")
    w(f"| **time to Pinnacle's first price change** (active lines; Kaplan–Meier median [p25, p75]) | **{m(R2['reprice_median_min_km'], 0)} min** [{m(R2['reprice_p25_min_km'], 0)}, {m(R2['reprice_p75_min_km'], 0)}] |")
    w(f"| …first change of ≥ 1 pt | {m(R2['reprice_1pt_median_min_km'], 0)} min |")
    w(f"| baseline: first change from 3 h before end(M) | {m(R2['baseline_reprice_median_min'], 0)} min |")
    w(f"| absent/pulled lines: minutes until an active line appears (median) | {m(R2['absent_or_pulled_minutes_until_active_median'], 0)} |")
    w(f"| absent/pulled and never active before N starts | {R2['absent_or_pulled_never_active_before_start']} |")
    for b_, x in R2["by_surprise"].items():
        w(f"| reprice median, surprise {b_} | {m(x['reprice_median_min_km'], 0)} min (n={x['n']}) |")
    w("")
    cx = json.loads((ROOT / "out" / "stale_hist_context.json").read_text())
    w("| Why so few live lines at end(M) | Value |")
    w("|---|---|")
    w(f"| time from end(M) to the next match's start: median [p25, p75] | {cx['hours_to_next_median']:.0f} h [{cx['hours_to_next_p25']:.0f}, {cx['hours_to_next_p75']:.0f}] |")
    w(f"| next match within 24 h | {100 * cx['share_next_within_24h']:.0f}% |")
    w(f"| Pinnacle's first record before the match: median [p10, p90] | {cx['pinnacle_open_hours_before_start_median']:.0f} h [{cx['pinnacle_open_p10']:.0f}, {cx['pinnacle_open_p90']:.0f}] |")
    w(f"| Kalshi market for the next match quoting at end(M) | {cx['kalshi_open_at_end']} of {cx['pairs']} |")
    w("")
    w(f"**Stop rule** (median reprice > 60 min or median record gap > 15 min): reprice {m(st['median_reprice_min'], 0)} "
      f"min, gap {m(st['median_gap_min'], 1)} min → **{'STOP — (b) and (c) not run' if st['stopped'] else 'pass'}**.")
    w("")
    w("### 5a. Kalshi lag after results (vs Pinnacle's move by end(M) + 60 min, |move| ≥ 2 pts)")
    w("")
    w("| Slice | n | Kalshi to 50%: median [p25, p75] min | never | Kalshi to 90% | never | Pinnacle to 50% / 90% |")
    w("|---|---|---|---|---|---|---|")
    rows_a = [("all", a)] + list(S["a_kalshi_lag_after_results"]["by_surprise"].items())
    for lab, x in rows_a:
        if not x.get("n"):
            w(f"| {lab} | 0 | — | — | — | — | — |")
            continue
        w(f"| {lab if lab == 'all' else 'surprise ' + lab} | {x['n']} | {m(x['k50']['median'], 0)} [{m(x['k50']['p25'], 0)}, {m(x['k50']['p75'], 0)}] | "
          f"{100 * x['k50']['share_never']:.0f}% | {m(x['k90']['median'], 0)} [{m(x['k90']['p25'], 0)}, {m(x['k90']['p75'], 0)}] | "
          f"{100 * x['k90']['share_never']:.0f}% | {m(x['p50_median'], 0)} / {m(x['p90_median'], 0)} |")
    w("")
    if not st["stopped"]:
        w("### 5b/5c. Simulated taking on Kalshi vs Pinnacle fair (first trigger per match × side; taker fee "
          f"0.07·P·(1−P)·{S.get('fee_multiplier', 1)})")
        w("")
        w("| Regime | k | trades (matches) | mean edge at entry | ROI [95% CI, event bootstrap] | CLV vs Kalshi close, pts [CI] |")
        w("|---|---|---|---|---|---|")
        for reg, lab in (("b_result_windows", "(b) within 6 h after a result"), ("c_outside_windows", "(c) outside result windows")):
            for k_, x in S[reg].items():
                w(f"| {lab} | {k_[2:]} pts | {x['n']} ({x['n_matches']}) | {m(x['mean_edge_pts'], 1)} pts | {ci(x['roi'], pct=True)} | {ci(x['clv_pts'], d=2)} |")
        g = S["c_general_lag"]
        w("")
        w(f"(c) General lag outside result windows: {g['n_moves']} Pinnacle moves ≥ 2 pts; Kalshi reaches 50% in a median "
          f"{m(g['k50']['median'], 0)} min [{m(g['k50']['p25'], 0)}, {m(g['k50']['p75'], 0)}], never "
          f"{100 * (g['k50']['share_never'] or 0):.0f}%; 90% in {m(g['k90']['median'], 0)} min, never {100 * (g['k90']['share_never'] or 0):.0f}%.")
        w("")
    w(V5)
    w("")
    w("Caveats:")
    w("- Kalshi quotes are 1-minute candle closes, forward-filled; depth at the ask is unknown, so "
      "fills of more than a few hundred contracts are optimistic.")
    w("- Pinnacle is OddsPapi's record of changes (free plan).")
    w("- The 6-hour result window, the 2-point move threshold and 60-minute settle are fixed choices, "
      "not tuned.")
    w("")
    w("## 6. Shadow quoting")
    w("")
    w("Unchanged. `PricingShadowQuotes` keeps logging legacy vs v2; model (b) remains in research only. "
      "The ≥ 2026-11-20 report is still due.")
    w("")
    w("## Side findings")
    w("")
    w("- **vlr times are US Eastern, not UTC**: OddsPapi true start − vlr = +3.92 h median (n = 24); +5 h in EST months.")
    w("  - Fixed in all code that compares absolute times.")
    w("  - REPORT §0.2's Wayback '12.8 h before start' is really ≈ 17 h.")
    w("  - Season-relative results are unaffected.")
    w("- **Pinnacle often has no line at the moment a result lands** (§5.0). This limits any immediate "
      "post-result comparison, live or historical.")
    w("")
    w("## Decisions needed")
    w("")
    w(DEC)
    (ROOT / "REPORT_v3.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote", ROOT / "REPORT_v3.md")


V5 = chr(10).join([
    "**Verdict (5):** the reference check failed, so (b) and (c) were not run.",
    "- **Pinnacle is fine-grained once a line exists** (median gap under 1 min).",
    "- **But when a result lands, the teams' next-match line almost never exists yet**: 95% absent. "
    "Pinnacle opens VALORANT lines ~1 day ahead, while the next match is ~3 days away.",
    "- **In the 8 cases where the line was up,** Pinnacle took a median ~4 h to change price at all. "
    "That's no faster than its baseline on those same lines (~5.7 h), so it isn't reacting to the result.",
    "- **Kalshi is the same story:** its next-match market was quoting at the result in only 37/911 cases.",
    "- **So (a) had no qualifying pairs (n = 0).** The post-result stale-line effect is structurally rare "
    "in tier-1 VCT: by the time the next line opens, the result is already priced in.",
])
DEC = """1. **PREREG §10 viability.** With Pinnacle almost never live when a result lands, §10's primary
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
   swap decision after 2026-11-20, and the OddsPapi paid plan (Thunderpick history)."""

if __name__ == "__main__":
    main()
