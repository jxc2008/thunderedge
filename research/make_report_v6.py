"""Render research/REPORT_v6.md (round 6). Tables first, one-line verdicts, decisions last.

Inputs: out/devig_robust.json, out/s11_backtest_2026.json, cache/hist/ledger.csv, cache/hist/parser_test_fixtures.json.
Usage: python -m research.make_report_v6
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path
from statistics import NormalDist

from research.hist_fetch import CACHE

ROOT = Path(__file__).resolve().parent
DR = json.loads((ROOT / "out" / "devig_robust.json").read_text())
BT = json.loads((ROOT / "out" / "s11_backtest_2026.json").read_text())["summary"]
EVAL = "574c26b84f21f284e79ae4ee6b9c0c3a17f52911"
M = ("mult", "power", "shin")
NAMES = {"mult": "multiplicative", "power": "power", "shin": "Shin"}


def ci(b: dict | None, d: int = 2, pct: bool = False) -> str:
    if not b or b.get("est") is None:
        return "—"
    f = (lambda x: f"{100 * x:+.{d}f}%") if pct else (lambda x: f"{x:+.{d}f}")
    return f"{f(b['est'])} [{f(b['lo'])}, {f(b['hi'])}]"


def power(mu: float, sd: float, n: int, a: float) -> float:
    z = NormalDist().inv_cdf
    return NormalDist().cdf(mu * sqrt(n) / sd - z(1 - a))


def main() -> None:  # noqa: PLR0915
    L: list[str] = []
    w = L.append
    sf = DR["shin_failures"]
    tk, tp = DR["taking"], DR["tp_stale_at_open"]
    prim = BT["primary_net_clv_pts"]
    led = [r for r in csv.reader((CACHE / "ledger.csv").open()) if r and r[1] == "oddspapi_live"]
    sd = prim["sd"]
    mu_bt, mu_lo = prim["mean"], tk["shin"]["k=5"]["all"]["clv_pin_net_pts"]["est"]

    w("# VALORANT research — round 6 report")
    w("")
    w(f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `research/make_report_v6.py`. Paper only. "
      "§1 is **exploratory** (2026 data, no new requests, the k values and buckets fixed by you). CIs are 95% bootstrap "
      "clustered by event unless stated; n is given with every number._")
    w("")
    w("## Overview")
    w("")
    w("| # | Item | Verdict |")
    w("|---|---|---|")
    s5 = {m: tk[m]["k=5"]["all"]["clv_pin_net_pts"] for m in M}
    s3 = {m: tk[m]["k=3"]["all"]["clv_pin_net_pts"] for m in M}
    w(f"| 1 | De-vig robustness | **k = 5 survives, k = 3 doesn't.** k = 5 net CLV vs Pinnacle close: multiplicative {s5['mult']['est']:+.2f}, "
      f"power {s5['power']['est']:+.2f}, Shin {s5['shin']['est']:+.2f} pts. k = 3 is ≈ 0 under all three. Part of round 5's edge was the "
      f"multiplicative de-vig shifting probability toward longshots. Stale-at-open CLV barely changes (+6.0% to +6.2%). |")
    w(f"| 2 | PREREG §11 | Frozen at `{EVAL[:7]}`. Shin is primary: it fails on {sf['n_markets_failed']} of {sf['n_markets']} markets. On 2026 the exact rule gives "
      f"{prim['n']} trades, with net CLV {mu_bt:+.2f} pts. Power at look 2 (≈ 38 trades) is ≈ {100 * power(mu_bt, sd, 38, .04):.0f}% at that effect and "
      f"≈ {100 * power(mu_lo, sd, 38, .04):.0f}% at the smaller Shin estimate. |")
    w("| 3 | §10 gap slices | Added as a descriptive slice only (2–3 / 3–5 / > 5 pts); the rule and thresholds are unchanged. |")
    w(f"| 4 | Poll parser test | **Not testable today.** The discovery call found no VALORANT fixtures in the next 4 days (404 FIXTURE_NOT_FOUND). "
      f"I used 1 of the 2 approved calls and skipped the odds call. Live-poll ledger: {len(led)} call. |")
    w("| 5 | Order books | Kept in full; nothing is pruned. |")
    w("| 6 | v2 swap | None. `shadow_compare.py` runs on or after Nov 20 and reports v2 vs the Kalshi mid only, with (b)'s coverage noted. |")
    w("")

    # 1
    w("## 1. EXPLORATORY — de-vig robustness")
    w("")
    w("Methods (`research/devig.py`): **multiplicative** p = (1/o)/Σ(1/o); **power** p = (1/o)^k with Σ = 1; **Shin** (two-outcome "
      "insider model, z solved so Σ = 1). Pinnacle fair and Pinnacle close use the same method. Trades are re-selected under each method "
      "(fair − ask > k). Net = CLV − the quadratic fee per contract (multiplier 1, unrounded as in rounds 4–5).")
    w("")
    w(f"Shin validity: **{sf['n_markets_failed']} of {sf['n_markets']} markets fail** ({sf['n_records_failed']} of {sf['n_records']:,} active pre-start records).")
    w("")
    w("### Kalshi taking: CLV vs Pinnacle close, pts")
    w("")
    w("| k | ask bucket | " + " | ".join(f"{NAMES[m]}: n, gross, **net**" for m in M) + " |")
    w("|---|---|" + "---|" * len(M))
    for k in ("k=3", "k=5"):
        for lab in ("all", "<0.30", "0.30-0.70", ">0.70"):
            cells = []
            for m in M:
                v = tk[m][k]["all"] if lab == "all" else tk[m][k]["by_price"][lab]
                cells.append(f"{v['n']}, {ci(v['clv_pin_pts'])}, **{ci(v['clv_pin_net_pts'])}**" if v["n"] else "0")
            w(f"| {k[2:]} | {lab} | " + " | ".join(cells) + " |")
    w("")
    w("**Verdict:** k = 3 has no net edge under any method. At k = 5, net CLV is positive under all three, but the size depends on the "
      f"de-vig: {s5['mult']['est']:+.2f} (multiplicative) vs {s5['shin']['est']:+.2f} (Shin), whose CI nearly touches 0. The < 30¢ bucket stays "
      "the strongest under every method, but its n falls from 40 to 21 under Shin, because Shin gives longshots less probability. "
      "The multiplicative method overstated cheap-contract edges.")
    w("")
    w("### Thunderpick stale-at-open (Wayback set): the same methods on Pinnacle and on Thunderpick")
    w("")
    w("| Method | n bets | events | same bets as multiplicative | mean CLV vs Thunderpick close | 2–3 pts | 3–5 pts | > 5 pts |")
    w("|---|---|---|---|---|---|---|---|")
    for m in M:
        t = tp[m]
        g = t["by_gap"]

        def gcell(x):
            if not x["n"]:
                return "0"
            return f"{x['n']}: {ci(x['clv'], 1, True)}" if "lo" in x["clv"] else f"{x['n']}: {100 * x['mean']:+.1f}% (no CI)"
        w(f"| {NAMES[m]} | {t['n_bets']} | {t['n_events']} | {t['overlap_with_mult']} | {ci(t['clv'], 1, True)} | "
          f"{gcell(g['2-3 pts'])} | {gcell(g['3-5 pts'])} | {gcell(g['>5 pts'])} |")
    w("")
    w("**Verdict:** robust. The overall CLV is the same under each method, and the 2–3-pt bucket stays ≈ 0 under all three.")
    w("")

    # 2
    w("## 2. PREREG §11 — Kalshi taking at k = 5 (frozen)")
    w("")
    w("| Element | Frozen definition (`PREREG_KICKOFF2027.md` §11) |")
    w("|---|---|")
    w("| Rule | buy the Kalshi side when Shin fair − ask > 5 pts; first entry per match × side |")
    w("| Pinnacle freshness | latest Pinnacle record ≤ 15 min old at the observation time, active and Shin-valid |")
    w("| Size | min(1 unit = 100 contracts, displayed size at the best ask) from the logged book; ≥ 1 contract required |")
    w("| Fee | Kalshi quadratic, multiplier 1, rounded up per order: ceil(100·0.07·C·P·(1−P))/100 $ |")
    w("| Primary | net CLV vs Pinnacle Shin close, per trade; match-level bootstrap |")
    w(f"| Primary de-vig | Shin, by the rule \"Shin unless it fails on > 5% of markets\", applied to 2026: {sf['n_markets_failed']}/{sf['n_markets']} → Shin |")
    w("| Look 1 | matches to 2027-06-30: confirm if ≥ 20 trades and the one-sided 99% LB > 0; abandon if ≥ 20 trades and mean ≤ 0; else continue |")
    w("| Look 2 | pooled to 2027-10-31: confirm if ≥ 30 trades and the one-sided 96% LB > 0; else abandon (< 30 trades: inconclusive) |")
    w("| Secondary | settlement P&L, the < 30¢ slice, multiplicative/power de-vig, gross CLV, CLV vs Kalshi close, contracts filled, blocked-signal counts |")
    w(f"| Code | `research/prereg_s11.py` + `research/devig.py`; thunderedge `{EVAL}`; tests `research/test_prereg_s11.py` (fee rounding, entry rule, end-to-end on a synthetic logger DB) |")
    w("")
    w("**The rule on 2026** (`prereg_s11.py --backtest-2026`: candle quotes every 15 min; displayed size unknown, treated as 100):")
    w("")
    w("| Measure | Value |")
    w("|---|---|")
    w(f"| Trades | {prim['n']} ({BT['n_events']} events); {BT['n_trades_first_42_days']} in the first 42 days; {BT['n_trades_to_jun30']} by 30 Jun |")
    w(f"| Net CLV, Shin (primary) | {prim['mean']:+.2f} pts, match bootstrap [{prim['ci95'][0]:+.2f}, {prim['ci95'][1]:+.2f}]; event bootstrap "
      f"{ci(BT['event_boot_primary'])}; sd {sd:.1f} |")
    for m, b in BT["secondary"]["other_devig"].items():
        w(f"| Net CLV, {NAMES[m]} | {b['mean']:+.2f} pts [{b['ci95'][0]:+.2f}, {b['ci95'][1]:+.2f}] |")
    sp = BT["secondary"]["settlement_pnl_per_contract_c"]
    w(f"| Settlement P&L per contract | {sp['mean']:+.1f}¢ [{sp['ci95'][0]:+.1f}, {sp['ci95'][1]:+.1f}] |")
    ch = BT["secondary"]["ask_below_0.30"]
    w(f"| ask < 0.30 slice | n = {ch['n']}, net CLV {ch['net_clv']['mean']:+.2f} [{ch['net_clv']['ci95'][0]:+.2f}, {ch['net_clv']['ci95'][1]:+.2f}] |")
    w(f"| Observation times blocked | Pinnacle > 15 min old: {BT['secondary']['blocked_signals'].get('pinnacle_older_than_15min', 0)}; "
      f"inactive/invalid: {BT['secondary']['blocked_signals'].get('pinnacle_inactive_or_invalid', 0)} |")
    w("")
    w("The 15-min freshness rule keeps trades that follow recent Pinnacle moves, which is why the backtest's +2.53 is higher than the 1-min, no-age-rule +1.19. "
      "Both are selected estimates.")
    w("")
    w(f"**Power** (normal approximation, sd {sd:.1f} pts):")
    w("")
    w("| True mean net CLV | look 1, n = 26, α = 0.01 | look 2, n = 38, α = 0.04 | n = 60, α = 0.04 | n = 100, α = 0.04 |")
    w("|---|---|---|---|---|")
    for lab, mu in ((f"{mu_bt:+.2f} (backtest of this rule)", mu_bt), (f"{mu_lo:+.2f} (Shin, 1-min, no age rule)", mu_lo)):
        w(f"| {lab} | {100 * power(mu, sd, 26, .01):.0f}% | {100 * power(mu, sd, 38, .04):.0f}% | {100 * power(mu, sd, 60, .04):.0f}% | "
          f"{100 * power(mu, sd, 100, .04):.0f}% |")
    w("")
    w("Trade counts assume 2027 matches 2026's rate. Kalshi's VALORANT coverage grew through 2026 (Q1 293 events, Q2 675), so 2027 may have more.")
    w("")
    w("**Verdict:** frozen and tested. Two things are outside the code: the Pinnacle history budget (`oddspapi_s11`, ≤ 600 calls, ≤ 40 billable) "
      "needs your approval before the first fetch, and displayed sizes can only come from 2027 books.")
    w("")

    # 3
    w("## 3. §10 gap slices")
    w("")
    w("`_stale_block` now also reports `by_gap_descriptive`: n bets and CLV for |gap| 2–3, 3–5 and > 5 pts, tier by tier. The 2-pt bet "
      "threshold, the success rule and the tags are unchanged. The smoke run on 2026 completes (no logger data for 2026, so no rows). Logged in §9.")
    w("")

    # 4
    w("## 4. Poll parser test")
    w("")
    w("| Step | Result |")
    w("|---|---|")
    w(f"| 1. `/v4/fixtures?sportId=61&from=today&to=+4 d` (billable, ledger `oddspapi_live`) | 404 `FIXTURE_NOT_FOUND`: no VALORANT fixtures listed. "
      "Kalshi's current markets are Chinese third-party and Kickoff-qualifier events that OddsPapi doesn't carry. |")
    w("| 2. `/v4/odds-by-tournaments` | **not made**: nothing priced to compare against |")
    w("| Calls used | 1 of the 2 approved |")
    w("")
    w("**Verdict:** the parser is still unverified. Its guard is unchanged: a priced response that parses to nothing turns the poll off. "
      "The live poll will make the first real call itself when Kickoff 2027 fixtures fall within 96 h, and that response is saved.")
    w("")

    w("## 5–6.")
    w("")
    w("- **Order books:** kept in full, no pruning (≈ 9 MB/week off-season, REPORT_v5).")
    w("- **v2 swap:** none. On or after 2026-11-20: `python scripts/shadow_quotes.py report --since 2026-11-17T08:12`, then "
      "`python scripts/shadow_compare.py`, reporting v2 vs the Kalshi mid only, with (b)'s coverage noted (6/158 market sides in the preview).")
    w("")
    w("## Decisions needed")
    w("")
    w("1. **§11 Pinnacle budget:** approve ledger host `oddspapi_s11`: ≤ 600 history calls (non-billable) + ≤ 40 billable fixture-window "
      "calls over the 2027 season, run at each look (2027-06-30, 2027-10-31). Histories cached for §10 are reused.")
    w("2. **Parser test:** retry with one discovery call once VALORANT fixtures are listed again, likely late December when Kickoff 2027 schedules "
      "post? Or leave it to the poll's first live call (it is protected by the self-disable guard).")
    w("3. **§11 unit:** 1 unit = 100 contracts (≈ $50 at 50¢). Change it before Kickoff if you want a different unit; changing it later would be a deviation.")
    w("4. Still open: Kalshi key (send when ready), VPS hosting, in-season logger cadence.")
    w("")
    (ROOT / "REPORT_v6.md").write_text("\n".join(L), encoding="utf-8")
    print("wrote REPORT_v6.md")


if __name__ == "__main__":
    main()
