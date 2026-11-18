"""Render research/REPORT_v5.md (round 5). Tables first, one-line verdict per item, decisions last.

Inputs: out/stale_hist3.json, out/poll_design.json, out/t2_player_priors.json, out/shadow_compare.json,
data/odds_snapshots.db (kalshi_books, poll_log). Usage: python -m research.make_report_v5
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from research import odds_logger as LG
from research.hist_fetch import CAP_30D

ROOT = Path(__file__).resolve().parent
OD = ROOT / "out"
S3 = json.loads((OD / "stale_hist3.json").read_text())
PD = json.loads((OD / "poll_design.json").read_text())
PR = json.loads((OD / "t2_player_priors.json").read_text())
SC = json.loads((OD / "shadow_compare.json").read_text())
CFG = json.loads((ROOT / "pinnacle_open.json").read_text())


def ci(b: dict | None, d: int = 2, pct: bool = False) -> str:
    if not b or b.get("est") is None:
        return "—"
    if "lo" not in b:
        return f"{100 * b['est']:+.{d}f}%" if pct else f"{b['est']:+.{d}f} (no CI, < 5 events)"
    f = (lambda x: f"{100 * x:+.{d}f}%") if pct else (lambda x: f"{x:+.{d}f}")
    return f"{f(b['est'])} [{f(b['lo'])}, {f(b['hi'])}]"


def books() -> dict:
    con = sqlite3.connect(LG.DB)
    polls = con.execute("SELECT ts_utc, kalshi_requests, n_matches FROM poll_log WHERE ts_utc >= "
                        "(SELECT min(ts_utc) FROM kalshi_books) ORDER BY ts_utc").fetchall()
    per = con.execute("""SELECT ts_utc, count(*), sum(length(ts_utc)+length(ticker)+length(event_ticker)+length(series)
                         +length(yes_bids)+length(no_bids)+ifnull(length(trigger),0)) FROM kalshi_books
                         GROUP BY ts_utc ORDER BY ts_utc""").fetchall()
    open_mk = con.execute("""SELECT count(*) FROM odds_snapshots WHERE source='kalshi'
                             AND ts_utc=(SELECT max(ts_utc) FROM odds_snapshots WHERE source='kalshi')""").fetchone()[0]
    return {"polls": polls, "per": per, "open_markets": open_mk}


def disk_ratio() -> float:
    """Copy kalshi_books into a scratch SQLite file with the same schema/index; file size / raw text bytes."""
    import tempfile  # noqa: PLC0415
    src = sqlite3.connect(LG.DB)
    rows = src.execute("SELECT * FROM kalshi_books").fetchall()
    raw = sum(sum(len(x) for x in r if isinstance(x, str)) for r in rows)
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "b.db"
        con = sqlite3.connect(f)
        con.executescript(LG.SCHEMA)
        con.executemany("INSERT INTO kalshi_books VALUES (?,?,?,?,?,?,?)", rows)
        con.commit()
        con.execute("VACUUM")
        con.close()
        empty = sqlite3.connect(Path(d) / "e.db")
        empty.executescript(LG.SCHEMA)
        empty.commit()
        empty.close()
        size = f.stat().st_size - (Path(d) / "e.db").stat().st_size
    return size / raw if raw else 1.0


def main() -> None:  # noqa: PLR0915
    L: list[str] = []
    w = L.append
    tk, tp = S3["taking"], S3["tp_stale_at_open"]
    du = tp["duration"]
    lo = tp["leave_one_event_out"]
    best = next(d for d in PD["designs"] if d["window_h"] == [CFG["window_early_h"], CFG["window_late_h"]]
                and d["cadence_h"] == CFG["cadence_h"])
    user = next(d for d in PD["designs"] if d["window_h"] == [30, 18] and d["cadence_h"] == 2)
    bk = books()
    n_polls = len(bk["polls"])
    req_per_poll = (sum(p[1] for p in bk["polls"]) / n_polls) if n_polls else None
    first_rows, first_bytes = (bk["per"][0][1], bk["per"][0][2]) if bk["per"] else (0, 0)
    later = bk["per"][1:]
    later_rows = (sum(r[1] for r in later) / len(later)) if later else None
    later_bytes = (sum(r[2] for r in later) / len(later)) if later else None
    ROW_OVERHEAD = disk_ratio()  # on-disk bytes (table + index) per raw text byte, measured
    full_week_mb = first_bytes * ROW_OVERHEAD * 672 / 1e6
    dedup_week_mb = (later_bytes * ROW_OVERHEAD * 672 / 1e6) if later_bytes is not None else None

    w("# VALORANT research — round 5 report")
    w("")
    w(f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `research/make_report_v5.py`. Paper only. "
      "§2–§3 are **exploratory**: a rescoring of round-4 trades and bets, with no new requests and no new "
      "thresholds or filters. CIs are 95% bootstrap clustered by event; n is given with every number._")
    w("")
    w("> **Correction to REPORT_v4 §2.** The Thunderpick stale-at-open rough look used the **Wayback** pre-match "
      "snapshot (one per match), not our logger. The logger only started on 2026-11-17, off-season. The numbers in v4 stand; the label was wrong.")
    w("")
    w("## Overview")
    w("")
    w("| # | Item | Verdict |")
    w("|---|---|---|")
    w("| 0 | Push, `.env.example` | Both research branches are pushed. `origin/feature/market-maker` `.env.example` now has placeholders only (commit `f851d6a`, no history rewrite). Both remote branches that have the file show placeholders. The Kalshi key is still pending. |")
    w(f"| 1 | Tier-2 | Not resumed; qualifiers skipped. Priors for {PR['summary']['n_players']} players are exported as an optional feature and not wired into the frozen model. |")
    k3, k5 = tk["k=3"]["all"], tk["k=5"]["all"]
    w(f"| 2 | Kalshi taking rescored | The trades beat **Pinnacle's close** by +{k3['clv_pinnacle_pts']['est']:.1f} pts (k=3) and "
      f"+{k5['clv_pinnacle_pts']['est']:.1f} pts (k=5), with CIs above 0. That is more than the ≈1.5¢ fee. Settlement P&L CIs still include 0 at every k. "
      "The edge sits in entries below 30¢ and in markets Kalshi later followed (a split that can't be known at entry). |")
    w(f"| 3 | Stale-at-open follow-ups | The mispricing was still posted at the snapshot in all 25 after-open cases: a lower bound of median "
      f"{du['lower_bound_median_h']:.0f} h, minimum {du['lower_bound_min_h']:.1f} h. CLV comes from 3–5-pt gaps (n=21). "
      f"Leave-one-event-out range: {100 * lo['min']:+.1f}% to {100 * lo['max']:+.1f}%, positive whichever event is dropped. |")
    w(f"| 4 | Pinnacle-open poll | The suggested T−30h..T−18h window catches only {100 * user['share_caught_in_window']:.0f}% of opens. "
      f"**Enabled instead:** T−{CFG['window_early_h']}h..start, every {CFG['cadence_h']} h. On the 2026 schedule it catches {100 * best['share_caught_in_window']:.0f}% of opens, with a median delay of "
      f"{best['median_detection_delay_h']:.1f} h. Peak {best['peak_month_calls']} calls/month against the free 250; 30-day cap {CAP_30D['oddspapi_live']}. |")
    store = (f"≈{dedup_week_mb:.1f} MB/week with change-only rows ({full_week_mb:.0f} MB/week if every poll were stored)"
             if dedup_week_mb is not None else f"≤ {full_week_mb:.0f} MB/week (every poll stored; the change-only rate needs more polls)")
    w(f"| 5 | Kalshi order books | Added to the logger and running. {req_per_poll:.0f} Kalshi requests per 15-min poll (2 list + batched books, "
      f"{bk['open_markets']} open markets). Storage {store}. |" if req_per_poll else "| 5 | Kalshi order books | Added; waiting for the first scheduled poll. |")
    w(f"| 6 | Shadow summary | Due on or after 2026-11-20. `scripts/shadow_compare.py` is ready. In the preview, (b) prices only {SC['n_with_b']}/{SC['n_market_teams']} "
      "market sides, because off-season Kalshi markets are mostly teams outside the tier-1 data. Expect a thin summary. |")
    w("")

    # 0
    w("## 0. Push and `.env.example`")
    w("")
    w("| Ref | Commit | Check |")
    w("|---|---|---|")
    w("| thunderedge `research/market-structure` | pushed, including this round's commits | No `.env`, `cache/` or `.db` tracked; no OddsPapi key string in the new commits |")
    w("| valorant-pricing-model `fix/side-baseline-blend` | pushed, including `6bc24bb` (this round) | same |")
    w("| thunderedge `origin/feature/market-maker` | `f851d6a` `.env.example` → `KALSHI_KEY_ID=your-kalshi-key-id`, `KALSHI_PRIVATE_KEY_PATH=/path/to/your/kalshi_private_key.pem` | old ID stays in history (no rewrite, per decision) |")
    w("| thunderedge `origin/feature/eco-round-strategy` | unchanged | placeholders (`your-key-id-here`) |")
    w("| all other refs, both repos | — | no `.env.example` |")
    w("")
    w("**Verdict:** done. When you send the new Kalshi key, it goes into `valorant-pricing-model/.env` only.")
    w("")

    # 1
    s = PR["summary"]
    w("## 1. Tier-2 player priors (optional feature)")
    w("")
    w("| Item | Value |")
    w("|---|---|")
    w(f"| Players whose first tier-1 map had tier-2 but no tier-1 history | {s['n_players']} (first tier-1 season 2025: "
      f"{s['by_first_t1_season'].get('2025', 0)}, 2026: {s['by_first_t1_season'].get('2026', 0)}) |")
    w(f"| Median tier-2 maps before the debut | {s['n_t2_maps_median']} |")
    w("| Prior mean (round-logit units) | mean +0.14, sd 0.15. Promoted players start above the new-player prior. |")
    w(f"| Prior variance at the debut | {s['var_median']} = v0_player for all of them. Drift between the last tier-2 map and the debut restores the cap, so the prior adds a mean shift, not certainty. |")
    w("| Where | table `t2_player_priors` in `data/valorant_tier2.db`; `research/out/t2_player_priors.json`; built by pricing `scripts/t2_player_priors.py` (T1+T2 arm params) |")
    w("")
    w("REPORT_v4 counted 136 tier-2-only debut slots in 2026, from lineups. The engine run counts 132 for 2026: it needs a "
      "complete five and a known region, which 4 debuts lack. 2025 debutants (34) are added because the tier-2 scrape covers 2025.")
    w("")
    w("**Verdict:** available. It isn't in the frozen model, and the round-4 ablation says adding tier-2 to the engine hurts the close fit. "
      "Using the priors needs its own pre-specified test.")
    w("")

    # 2
    w("## 2. EXPLORATORY — Kalshi taking simulation, rescored (same 557 / 340 / 105 trades as REPORT_v4)")
    w("")
    w("Each trade buys 1 contract at the ask when Pinnacle's de-vigged fair minus Kalshi's ask is more than k, "
      "on the first trigger per match × side. Fee = 0.07·P·(1−P), multiplier 1. Pinnacle close = last active "
      "Pinnacle price before the start. P&L is per contract, net of fee, settled 0/1.")
    w("")
    w("| k | slice | n | mean ask | CLV vs Kalshi close, pts | CLV vs Pinnacle close, pts | P&L ¢/contract | ROI |")
    w("|---|---|---|---|---|---|---|---|")
    for k in ("k=2", "k=3", "k=5"):
        x = tk[k]
        rows = [("all", x["all"])] + [(f"ask {lab}", v) for lab, v in x["by_price"].items()] + \
               [("Kalshi followed", x["by_follow"]["followed"]), ("never followed", x["by_follow"]["never_followed"])]
        for lab, v in rows:
            if not v["n"]:
                w(f"| {k[2:]} | {lab} | 0 | — | — | — | — | — |")
                continue
            w(f"| {k[2:]} | {lab} | {v['n']} | {v['mean_ask']:.2f} | {ci(v['clv_kalshi_pts'])} | {ci(v['clv_pinnacle_pts'])} | "
              f"{ci(v['pnl_c_per_contract'])} | {ci(v['roi'], 1, True)} |")
    w("")
    w("\"Kalshi followed\" means that after entry and before the start, Kalshi's mid closed at least 50% of the entry gap to "
      "Pinnacle fair (the round-4 k50 criterion). This uses the future, so it is a diagnostic, not a filter. "
      "Mean fee per trade is 1.46–1.55¢. ROI is averaged per dollar, so cheap contracts weigh more; that is why ROI is positive "
      "where P&L per contract is not (k=2, k=3).")
    w("")
    w("**Verdict:** against the sharp close, the k ≥ 3 entries are +EV after fees (k=5: about +1.9 pts net). Settlement is too noisy "
      "to confirm it (n ≤ 340, 16 events). The value sits in cheap contracts (< 30¢). That is also where a "
      "favourite–longshot bias in Kalshi would show, so the same pattern needs checking on 2027 data before it is trusted.")
    w("")

    # 3
    w("## 3. EXPLORATORY — Thunderpick stale-at-open follow-ups (the REPORT_v4 n = 38 bets, Wayback snapshot, one per match)")
    w("")
    w("**How long the stale price stayed posted.** With one snapshot per match, the duration can only be bounded:")
    w("")
    w("| Measure | n | Value |")
    w("|---|---|---|")
    w(f"| Snapshot taken after Pinnacle opened (Thunderpick still ≥ 2 pts off Pinnacle then): lower bound = snapshot − open | {du['n_bounded']} | "
      f"median **{du['lower_bound_median_h']:.1f} h**, min **{du['lower_bound_min_h']:.1f} h** |")
    w(f"| Snapshot taken before the open: no bound (the 'unchanged until the open' assumption) | {du['n_unbounded_before_open_changed']} | — |")
    w(f"| Thunderpick's winner price unchanged from the snapshot to the close | {round(du['share_unchanged_to_close'] * tp['n_bets'])} of {tp['n_bets']} | "
      "Thunderpick almost always moves before the start |")
    w(f"| Pinnacle open → start | {tp['n_bets']} | median {du['open_to_start_median_h']:.1f} h |")
    w("")
    w("The lower bound is for a price that is mispriced against Pinnacle. It is not proof that the same Thunderpick price stood "
      "since the open, because Thunderpick may have moved and still been off. A logger snapshot at t_open (§4) measures this directly.")
    w("")
    w("**CLV by gap size** (|Pinnacle − Thunderpick| at the snapshot; the 2/3/5-pt bins used in round 4):")
    w("")
    w("| Gap | n bets | events | mean CLV vs Thunderpick close [95% CI] |")
    w("|---|---|---|---|")
    for lab, v in tp["clv_by_signal"].items():
        w(f"| {lab} | {v['n']} | {v['n_events']} | {ci(v['boot'], 1, True) if 'lo' in v['boot'] else (f'{100 * v['mean']:+.1f}% (no CI, n < 5)' if v['mean'] is not None else '—')} |")
    w(f"| all | {tp['n_bets']} | {tp['n_events']} | {ci(tp['clv_all'], 1, True)} |")
    w("")
    w(f"**Leave-one-event-out** (13 events, 1–6 bets each): mean CLV ranges from {100 * lo['min']:+.1f}% to {100 * lo['max']:+.1f}%. "
      f"The most influential event is `{lo['most_influential_event']}` ({lo['bets_per_event'][lo['most_influential_event']]} bets); "
      "dropping it lowers the mean CLV from +6.2% to the minimum.")
    w("")
    w("**Verdict:** the signal holds up to dropping any one event and comes from 3–5-pt gaps. Gaps of 2–3 pts show no CLV. Gaps of ≥ 5 pts (n=3) are too few to judge. "
      "The stale window looks long, ≥ 5 h in every bounded case, so a 6-hourly poll is enough to catch it.")
    w("")

    # 4
    w("## 4. Windowed Pinnacle-open poll")
    w("")
    o = PD["open_hours_before_start_pct"]
    w(f"Pinnacle's first price comes before the start by (2026 tier-1, n = {PD['n_with_open']} of {PD['n_matches']}): p10 {o['p10']} h, "
      f"p25 {o['p25']} h, **median {o['p50']} h**, p75 {o['p75']} h, p90 {o['p90']} h. That spread is too wide for a narrow window.")
    w("")
    w("Replay on the 2026 schedule: a poll is made only while a scheduled match is inside its window and its open hasn't been caught. "
      "1 billable `odds-by-tournaments` call per poll covers every fixture, plus ≤ 1 `fixtures` discovery call per day.")
    w("")
    w("| Window | Cadence | Peak month calls | Mean month calls | Opens caught in window | Already open at window start | Median detection delay |")
    w("|---|---|---|---|---|---|---|")
    for d in PD["designs"]:
        mark = " **(enabled)**" if d is best else ""
        w(f"| T−{d['window_h'][0]}h..T−{d['window_h'][1]}h{mark} | {d['cadence_h']} h | {d['peak_month_calls']} | "
          f"{d['mean_calls_per_active_month']:.0f} | {100 * d['share_caught_in_window']:.0f}% | "
          f"{100 * d['share_already_open_at_window_start']:.0f}% | {d['median_detection_delay_h']:.1f} h |")
    w("")
    w("Monthly calls, enabled design (2026 replay): " + ", ".join(f"{k[5:]}: {v}" for k, v in best["calls_by_month"].items()) +
      ". Free plan: 250/month. Margin at the peak month: " + f"{250 - best['peak_month_calls']} calls, which covers the ≤ 6 billable prereg calls (§4).")
    w("")
    w("| Safeguard | Setting |")
    w("|---|---|")
    w(f"| Rolling 30-day cap | {CAP_30D['oddspapi_live']} under ledger host `oddspapi_live` (`hist_fetch.CAP_30D`) |")
    w("| Tier-1 only | logger tier-1 events, excluding qualifier / open / Ascension / Challengers / Game Changers stages. Without this, "
      "the off-season Brazil qualifiers (8 matches this week) would have triggered polls. |")
    w("| Parser unverified | the first live response is saved. If a priced response parses to zero prices, the poll disables itself and records why. |")
    w("| Cost now | 0. No tier-1 match is pending; the first calls come when Kickoff 2027 fixtures are within 96 h. |")
    w("")
    w("OddsPapi paid plans: the public pricing page lists only Free ($0, 250 requests/month) and \"Custom\" B2C/B2B plans "
      "with no published price, so the cheapest paid plan needs a quote. It isn't needed at this design.")
    w("")
    w("**Verdict:** fits the free plan with margin; enabled.")
    w("")

    # 5
    w("## 5. Kalshi order books in the logger")
    w("")
    w("| Item | Value |")
    w("|---|---|")
    w("| What | top 5 levels each side (YES bids, NO bids; YES ask = 1 − best NO bid), every open KXVALORANTGAME / KXVALORANTMAP market |")
    w("| When | every logger poll (15 min) + event-driven: post-result trigger polls are tagged `post_result`, Pinnacle-open catches `pinnacle_open` |")
    w("| Endpoint | public `GET /markets/orderbooks?tickers=…` (no auth), batches of 50 tickers, 0.25 s apart |")
    if req_per_poll:
        w(f"| Requests | {req_per_poll:.1f} Kalshi requests per poll on average over {n_polls} polls (2 market lists + "
          f"⌈{bk['open_markets']}/50⌉ book batches) ≈ {req_per_poll * 96 * 7:,.0f}/week, ≈ {req_per_poll / 900:.4f} req/s |")
        w(f"| Open markets now | {bk['open_markets']} (off-season: mostly Chinese and tier-2/3 events) |")
        w(f"| Storage | first poll {first_rows} rows, {first_bytes / 1e3:.0f} kB raw. Every poll stored: ≈{full_week_mb:.0f} MB/week. "
          + (f"Change-only (measured off-season on {len(later)} later poll(s): {later_rows:.0f} rows/poll; in season will differ): ≈{dedup_week_mb:.1f} MB/week." if later else
             "Change-only rate: needs more polls.") + " |")
    w("| Storage rule | a row only when a market's top-5 book changed since its last row; event-driven snapshots are always written; forward-fill between rows using `poll_log` |")
    w("| Test | `research/test_odds_logger.py::test_kalshi_books_top5_dedupe_and_trigger` |")
    w("")
    w("**Verdict:** running. The order sizes it records make the size cap in the §2-style taking test enforceable from now on.")
    w("")

    # 6
    w("## 6. Shadow quoting")
    w("")
    w("Shadow quoting is unchanged. `scripts/shadow_compare.py` (pricing repo) takes the last pre-start shadow row per market × team. It adds the frozen "
      "model (b), computed on the same current-pool basis as the shadow v2 quote, and the Kalshi settlement. It then scores v2, (b) and the Kalshi mid (Brier, log loss, "
      "event bootstrap).")
    w("")
    w("| Preview (now) | n |")
    w("|---|---|")
    w(f"| market × team rows | {SC['n_market_teams']} |")
    w(f"| with a Kalshi mid | {SC['n_with_mid']} |")
    w(f"| with (b) (both teams in the tier-1 data) | {SC['n_with_b']} (1 match; the team-name match is unverified) |")
    w(f"| settled so far | {SC['n_settled']} |")
    w(f"| scored (all three + settled) | {SC['n_scored']} |")
    w("")
    w("**Verdict:** I'll run it after the Nov 20 shadow report. Off-season coverage means (b) will be scored on very few markets, "
      "so v2 vs Kalshi mid will carry the summary.")
    w("")

    w("## Decisions needed")
    w("")
    w("1. **Kalshi key:** send it when it's ready. It goes into the local `.env` only.")
    w("2. **Taking strategy (§2):** pre-register a 2027 paper test of k = 5 with live order sizes from the books "
      "(primary metric: CLV vs Pinnacle close, net of fee)? This would be a new §11. I'd freeze it before Kickoff, the same way as §10.")
    w("3. **Ask-price split:** the edge is concentrated below 30¢ entries. Should that go into the pre-registered rule, or stay a reported slice "
      "only (recommended, since it was found on this data)?")
    w("4. **Order-book retention:** keep everything, or prune books for markets more than 7 days from their start?")
    w("5. Still open: VPS hosting, in-season logger cadence, and the v2 swap after the Nov 20 shadow report.")
    w("")
    (ROOT / "REPORT_v5.md").write_text("\n".join(L), encoding="utf-8")
    print("wrote REPORT_v5.md")


if __name__ == "__main__":
    main()
