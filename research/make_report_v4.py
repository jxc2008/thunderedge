"""Render research/REPORT_v4.md (round 4). Tables first, a one-line verdict per item, then decisions.

Inputs: out/stale_hist2.json (exploratory, no new requests), out/rating_ablation.json, out/t2_history_coverage.json,
cache/tier2_matches.json + vlr cache (scrape state), cache/tier2_STOP, the vlr request ledger.
Usage: python -m research.make_report_v4
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from research import vlr_fetch as v
from research.fetch_tier2 import APPROVED, DEFER, EVENTS, LEDGER_AT_APPROVAL, OUT, STOP
from research.pinnacle_open_poll import weekly_cost

ROOT = Path(__file__).resolve().parent
OD = ROOT / "out"
H2 = json.loads((OD / "stale_hist2.json").read_text())
AB = json.loads((OD / "rating_ablation.json").read_text()) if (OD / "rating_ablation.json").exists() else None
COV = json.loads((OD / "t2_history_coverage.json").read_text())
EVAL_T = "034b62fceb7fb5259c7dde18c4e5a217f798900b"
EVAL_P = "5370dafe19433f787fd1fb0ca37529d9078d4930"
FREE_MONTH = 250


def m(x, d: int = 0) -> str:
    return "—" if x is None else f"{x:,.{d}f}"


def hm(minutes) -> str:
    return "never (censored)" if minutes is None else f"{minutes / 60:.1f} h" if minutes >= 120 else f"{minutes:.0f} min"


def ci(b: dict | None, pct: bool = False, d: int = 1, scale: float = 1.0) -> str:
    if not b or b.get("est") is None:
        return "n/a"
    f = (lambda x: f"{100 * x:+.{d}f}%") if pct else (lambda x: f"{scale * x:+.{d}f}")
    return f"{f(b['est'])} [{f(b['lo'])}, {f(b['hi'])}]"


def scrape_state() -> dict:
    out = json.loads(OUT.read_text())
    titles = {k: e["title"].lower() for k, e in json.loads(EVENTS.read_text())["events"].items()}
    keep = {k: x for k, x in out.items() if not any(d in titles[k] for d in DEFER)}
    pages = [p for x in keep.values() for p in x["matches"]]
    deferred = [p for k, x in out.items() if k not in keep for p in x["matches"]]
    return {"events": len(out), "kept_events": len(keep), "kept_pages": len(pages),
            "cached": sum(1 for p in pages if v.cached(p)), "deferred_events": len(out) - len(keep),
            "deferred_pages": len(deferred), "ledger": v.live_requests_used(),
            "stop": STOP.read_text(encoding="utf-8") if STOP.exists() else None}


def main() -> None:  # noqa: PLR0915
    L: list[str] = []
    w = L.append
    sc = scrape_state()
    missing = sc["kept_pages"] - sc["cached"]
    ceiling = LEDGER_AT_APPROVAL + APPROVED
    tp = H2["tp_stale_at_open"]
    bt = H2["b_taking"]

    w("# VALORANT research — round 4 report")
    w("")
    w(f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `research/make_report_v4.py`. Paper only. "
      "§2 is **exploratory** (labelled, no new requests, three fixed thresholds k = 2/3/5, nothing searched). "
      "CIs are 95% bootstrap clustered by event._")
    w("")
    w("## Overview")
    w("")
    w("| # | Item | Verdict |")
    w("|---|---|---|")
    w(f"| 1 | PREREG §10 → stale at open | Re-frozen at thunderedge `{EVAL_T[:7]}` / pricing `{EVAL_P[:7]}`. The Pinnacle-open "
      "poll is built but **disabled**: even hourly it costs ≈175 OddsPapi calls a week against 250 a month on the free plan. §10 runs post hoc without it. |")
    w(f"| 2 | Exploratory (full pre-match window) | Kalshi takes a median {hm(H2['c_lag_all']['k50']['median'])} to follow half of a "
      f"Pinnacle move, and 40% of moves are never followed. Taking at k=3/5 gains CLV (+{bt['k=3']['clv_pts']['est']:.2f} / "
      f"+{bt['k=5']['clv_pts']['est']:.2f} pts), but that is below the ≈1.75-pt taker fee at 50¢, so there is no tradable edge yet. "
      f"Thunderpick stale-at-open: CLV {ci(tp['clv'], True)} on n={tp['n_bets']}, a positive signal from a small sample. |")
    stop_line = ("**stopped itself on 3 consecutive local DNS failures** (not a block)" if sc["stop"] else "complete")
    w(f"| 3 | Tier-2 scrape + ablation | The scrape {stop_line} at {sc['cached']:,}/{sc['kept_pages']:,} pages, and I haven't "
      f"resumed it. Ablation on those pages: {ablation_verdict()} |")
    w("| 4 | Lid close on AC | Set to 'do nothing' (battery: sleep, unchanged). |")
    w("| 5 | Kalshi key rotation | Pre-check done. I'm waiting on the new key; I'll write it only to the local `.env`. One branch "
      "(`origin/feature/market-maker`) still has the old key ID in `.env.example`; no private key is in any commit. |")
    w("")

    # 1 ------------------------------------------------------------------
    w("## 1. PREREG §10 — stale at open")
    w("")
    w("| Element | Frozen definition (`PREREG_KICKOFF2027.md` §10) |")
    w("|---|---|")
    w("| t_open | First active Pinnacle match-winner record in OddsPapi history. |")
    w("| Signal | Pinnacle de-vigged price at t_open minus the de-vigged Thunderpick price standing at t_open (latest snapshot ≤ t_open). |")
    w("| Bet | Side Pinnacle favours, when the signal is at least 2 pts, at the first Thunderpick quote ≥ t_open. Flat stake. |")
    w("| Tag | `post_result_stale` = Thunderpick unchanged since the teams' last completed result, plus `moved_since_result`, `posted_after_result` and `no_result_time`. |")
    w("| Outcome | CLV = log(bet price / Thunderpick close). ROI is secondary. |")
    w("| Stale duration | Minutes from t_open until Thunderpick first changes the standing price (Kaplan–Meier, censored at the start). Also: share still available at the bet. |")
    w("| Fallback | When Pinnacle never posts: model (a) at T−24 h. Reported separately, with no decision. |")
    w("| Success | ≥ 10 bets and a one-sided 95% lower bound on mean CLV > 0 (Pinnacle-referenced bets only). |")
    w(f"| Code hash | thunderedge `{EVAL_T}`; pricing `{EVAL_P}` (§7). Change logged in §9. |")
    w("")
    w("**OddsPapi request cost of the live Pinnacle-open poll** (billable; in season, ≥ 1 tier-1 match within 72 h most days):")
    w("")
    w("| Poll interval | Calls / week | Calls / 30 days | Fits the free plan (250 / month)? | Opening-time resolution |")
    w("|---|---|---|---|---|")
    for iv in (15, 30, 60, 180, 360):
        wk = weekly_cost(iv)
        w(f"| {iv} min | {wk} | {round(wk * 30 / 7)} | {'yes' if wk * 30 / 7 <= FREE_MONTH else 'no'} | ±{iv // 2} min |")
    w("")
    w("The cost is one `fixtures` discovery call a day plus one `odds-by-tournaments` call per poll, and it doesn't "
      "grow with the number of matches. Using up the monthly quota also blocks the non-billable history calls "
      "that §10 needs post hoc. So the poll stays off (`research/pinnacle_open.json`), and §10 takes "
      "t_open from history after each week (≤ 6 billable + ≈120–300 history calls per season, §4). The poll's "
      "only advantage is a Thunderpick snapshot taken right at t_open, instead of the logger's last scheduled poll.")
    w("")
    w("**Verdict:** frozen and runnable post hoc on the free plan. A live poll needs a paid plan, or a 6-hourly "
      "interval, which is too coarse to be useful.")
    w("")

    # 2 ------------------------------------------------------------------
    w("## 2. EXPLORATORY — 2026 tier-1, full pre-match window (no new requests)")
    w("")
    w(f"### (c) Pinnacle → Kalshi lag after each Pinnacle move (≥ 2 pts), n = {H2['c_lag_all']['n']:,} moves, "
      f"{H2['c_lag_all']['n_events']} events")
    w("")
    w("Lag = time until Kalshi's mid covers 50% (k50) or 90% (k90) of the Pinnacle move. Kaplan–Meier; censored at the start.")
    w("")
    w("| Slice | n | k50 median [IQR] | never reaches 50% | k90 median | never reaches 90% |")
    w("|---|---|---|---|---|---|")

    def lagrow(name, x):
        k5, k9 = x["k50"], x["k90"]
        w(f"| {name} | {x['n']:,} | {hm(k5['median'])} [{hm(k5['p25'])}, {hm(k5['p75'])}] | {100 * k5['share_never']:.0f}% "
          f"| {hm(k9['median'])} | {100 * k9['share_never']:.0f}% |")
    lagrow("all moves", H2["c_lag_all"])
    for k, x in H2["c_lag_by_move"].items():
        lagrow(f"move {k.replace('-100', '+')}", x)
    for k, x in H2["c_lag_by_time_to_start"].items():
        lagrow(f"{k} to start", x)
    w("")
    w("**Verdict:** Kalshi follows Pinnacle slowly, and bigger moves are followed more slowly. Close to the start the lag drops to ≈50 min.")
    w("")
    w("### (b) Taking simulation: buy Kalshi when Pinnacle fair − Kalshi ask > k (quadratic fee, multiplier 1)")
    w("")
    w("| k | n trades | matches | mean edge at entry | CLV vs Kalshi close, pts | ROI net of fee |")
    w("|---|---|---|---|---|---|")
    for k in ("k=2", "k=3", "k=5"):
        x = bt[k]
        w(f"| {k[2:]} pts | {x['n']} | {x['n_matches']} | {x['mean_edge_pts']:.1f} pts | {ci(x['clv_pts'], d=2)} | {ci(x['roi'], True)} |")
    w("")
    w("Fills are 1 contract at the candle ask. Kalshi candles carry no displayed size, so \"fill only up to "
      "displayed size\" can't be applied historically. The ROI figures assume 1 contract was always available. "
      "First trigger per (match, side) only. Fee = 0.07·P·(1−P) per contract, unrounded (≈1.75¢ at 50¢). Kalshi rounds "
      "each order's fee up to the cent, so a 1-contract fill pays 2¢ and the ROI here is slightly optimistic.")
    w("")
    w("**Verdict:** CLV is real at k ≥ 3 but smaller than the fee. ROI CIs include 0 at every k. This is not a "
      "strategy until live order-book depth is logged.")
    w("")
    w("### Thunderpick stale-at-open, rough look (own logger snapshots, 2026)")
    w("")
    w("| Slice | n bets | events | CLV vs Thunderpick close |")
    w("|---|---|---|---|")
    w(f"| all | {tp['n_bets']} | {tp['clv']['n_events']} | {ci(tp['clv'], True)} |")
    for k, x in tp["by_regime"].items():
        w(f"| {k} | {x['n_bets']} | {x['clv']['n_events']} | {ci(x['clv'], True)} |")
    w("")
    w(f"Matches with both a Pinnacle open and a Thunderpick snapshot: n = {tp['n_matches']}. Median |signal| = "
      f"{tp['median_abs_signal_pts']:.1f} pts. Pinnacle opens a median {tp['median_hours_open_before_start']:.0f} h "
      f"before the start; our median snapshot is {tp['median_hours_snap_before_start']:.0f} h before. ROI at the "
      f"snapshot price is {ci(tp['roi_at_snapshot_price'], True)}. The logger was not polling at t_open, so the "
      "'before open' rows assume Thunderpick was unchanged from the snapshot to the open. That assumption is "
      "what the live poll would remove.")
    w("")
    w("**Verdict:** positive CLV, mostly from the 13 'before open' rows (7 events). It supports running §10, but is not evidence on its own.")
    w("")

    # 3 ------------------------------------------------------------------
    w("## 3. Tier-2 scrape (2025–26) and tier-1 ablation")
    w("")
    w("| Check | Result |")
    w("|---|---|")
    w("| robots.txt (2026-11-17) | No crawl-delay. `/search/auto` and `/rr/` are disallowed (never requested). 1 extra request, outside the ledger. |")
    w("| Rate | 1 request / 3 s + 0–1 s jitter ≈ 0.29 req/s. Logger ≈ 4 req / 15 min. Combined ≤ 0.3 req/s. |")
    w(f"| Volume found | {sc['events']} events, {sc['kept_pages'] + sc['deferred_pages']:,} completed match pages (vs ≈5,400 approved) |")
    w(f"| Deferred (over approval) | {sc['deferred_events']} open-qualifier events, {sc['deferred_pages']:,} pages, mostly semi-pro sides. Not fetched. |")
    w(f"| Fetched | {sc['cached']:,} / {sc['kept_pages']:,} league-stage match pages + 130 list pages. vlr ledger {sc['ledger']:,} "
      f"(ceiling {ceiling:,}). |")
    if sc["stop"]:
        w("| Stop | 2026-11-18 01:06 UTC, after 3 consecutive `NameResolutionError` (local DNS lookup failed). "
          "There was no 403, 429 or Cloudflare page in the run. The odds logger and shadow job also missed that poll. "
          f"{missing:,} pages left. Resuming would bring the ledger to ≈{sc['ledger'] + missing:,}, which is within the ceiling. |")
    w("| Errors other than the stop | 0 |")
    w("")
    w(f"**Player histories** (2026 tier-1 lineup slots, n = {COV['n_slots_2026_t1']:,}; {COV['n_players']} players):")
    w("")
    w("| Prior maps before the slot | Slots |")
    w("|---|---|")
    w(f"| any tier-1 | {COV['with_prior_t1']:,} |")
    w(f"| any tier-2 (2025–26) | {COV['with_prior_t2']:,} |")
    w(f"| tier-2 only: a cold start the scrape fills | {COV['t2_only']:,} ({COV['players_t2_only']} players, first tier-1 series) |")
    w(f"| neither | {COV['neither']:,} |")
    w("")
    if AB:
        o, ca, cs = AB["outcome_ll"], AB["close_err_median_all"], AB["close_err_median_stable"]
        w(f"**Ablation.** Train on 2024–25 (tier-1 tuning only), test on 2026 tier-1 series: n = {AB['n_test']} (with a close: "
          f"{AB['n_with_close']}; stable lineups: {AB['n_stable']}). Tier-2 maps used: {AB['n_t2_maps']:,}.")
        w("")
        w("| Metric | T1 frozen | T1 re-tuned (control) | T1 + T2 | T1+T2 − control [95% CI] |")
        w("|---|---|---|---|---|")
        w(f"| (b) outcome log loss | {o['t1_frozen']:.4f} | {o['t1_retuned']:.4f} | {o['t1t2']:.4f} | {ci(o['diff_t1t2_minus_t1r'], d=4)} |")
        w(f"| (a) median \\|model − close\\|, all, pts | {ca['t1_frozen']:.2f} | {ca['t1_retuned']:.2f} | {ca['t1t2']:.2f} | "
          f"{ci(ca['diff_t1t2_minus_t1r'], d=2)} |")
        w(f"| (a) same, stable lineups, pts | {cs['t1_frozen']:.2f} | {cs['t1_retuned']:.2f} | {cs['t1t2']:.2f} | "
          f"{ci(cs['diff_t1t2_minus_t1r'], d=2)} |")
        w("")
        pv = AB["params_b_t1t2"].get("v0_tier")
        w(f"The tuned tier offset prior is v0_tier = {pv}, the middle of {{0.05, 0.25, 1.0}}. Re-tuning picked identical engine "
          "params for both arms, so the T1+T2 vs control gap is the tier-2 data. The control differs from the frozen model only in "
          "head (a)'s κ (0.8 → 1.0) and its re-fit coefficients. "
          "Tier-2 2024 was not scraped, so tier-2 histories start in 2025, and the head (a) was fit on a 2025 "
          "rating distribution that only partly includes tier-2. That is one reason the close head degrades. "
          "I tried no other variants, because that would be searching on test data.")
        w("")
    w(f"**Verdict:** {ablation_verdict()}")
    w("")

    # 4/5 ----------------------------------------------------------------
    w("## 4. Lid close on AC")
    w("")
    w("| Setting | Before | After |")
    w("|---|---|---|")
    w("| Lid close, AC (`LIDACTION`) | sleep | **do nothing** (verified with `powercfg /qh`) |")
    w("| Lid close, battery | sleep | sleep (unchanged) |")
    w("")
    w("**Verdict:** done. Polls still stop on battery or when Windows is shut down.")
    w("")
    w("## 5. Kalshi key rotation — pre-check")
    w("")
    w("| Location | `.env.example` | Kalshi entries |")
    w("|---|---|---|")
    w("| thunderedge `research/market-structure`, `main`, other local branches | absent | — |")
    w("| `origin/feature/eco-round-strategy` | present | placeholders (`your…`, `/path…`) ✔ |")
    w("| `origin/feature/market-maker` | present | **real old key ID** (`aba4…`, commit `2415a09`); key path is a placeholder |")
    w("| valorant-pricing-model (all 5 refs) | absent | — |")
    w("| Private key file / PEM in any commit, either repo | none | — |")
    w("| Local `.env` | pricing repo: OddsPapi only; thunderedge: none | none yet |")
    w("")
    w("**Verdict:** once you rotate, the old ID is dead and the leak doesn't matter. A placeholder fix on "
      "`feature/market-maker` is a one-line commit plus a push to a branch I haven't touched; I'll do it only if you ask.")
    w("")

    # decisions ----------------------------------------------------------
    w("## Decisions needed")
    w("")
    w(f"1. **Resume the tier-2 scrape?** {missing:,} league pages are left, inside the approved ceiling. The stop was local DNS, "
      "not vlr. Say \"resume\" and I'll delete `cache/tier2_STOP` and rerun (≈1 h). With the ablation negative, the only "
      "use of those pages is fuller player histories, so it is low value. Recommendation: resume only if a tier-2 "
      "stratum or tier-2 trading is planned.")
    w(f"2. **The {sc['deferred_pages']:,} open-qualifier pages** would exceed the ≈5,400 approval by ≈"
      f"{sc['ledger'] + missing + sc['deferred_pages'] - ceiling:,}. They help cold-start priors only for players who "
      "reach tier 1 through qualifiers. My recommendation is to skip them.")
    w("3. **Live Pinnacle-open poll:** an OddsPapi paid plan (lets you poll every 15–60 min), or keep it off and run §10 "
      "post hoc on the free plan (recommended for Kickoff 2027). Before enabling, `hist_fetch.CAP` needs an "
      "`oddspapi_live` entry (it currently raises KeyError), and the response parser needs one real response to verify against.")
    w("4. **Kalshi:** send the new key when it's ready (local `.env` only). Should I commit placeholders to `origin/feature/market-maker`'s `.env.example`?")
    w("5. **Kalshi depth:** to make the (b) simulation honest about size, the logger needs to snapshot the Kalshi order book. "
      "That is ≈1 request per open market per poll on Kalshi's API, with no vlr.gg cost. Add it?")
    w("6. Still open from earlier rounds: VPS hosting, in-season logger cadence, and the v2 half-rate swap after the shadow report (2026-11-20).")
    w("")
    (ROOT / "REPORT_v4.md").write_text("\n".join(L), encoding="utf-8")
    print("wrote REPORT_v4.md")


def ablation_verdict() -> str:
    if not AB:
        return "pending."
    o, ca = AB["outcome_ll"]["diff_t1t2_minus_t1r"], AB["close_err_median_all"]["diff_t1t2_minus_t1r"]
    both = o["hi"] < 0 and ca["hi"] < 0
    pts = o["est"] < 0 and ca["est"] < 0
    if both:
        return "tier-2 improves both outcome LL and close error (CIs below 0). Keep it."
    if pts:
        return ("tier-2 improves both point estimates but at least one CI includes 0. That is not shown; "
                "don't add it to the frozen model.")
    if ca["lo"] > 0:
        return (f"adding tier-2 makes the close fit **worse** by {ca['est']:+.2f} pts [{ca['lo']:+.2f}, {ca['hi']:+.2f}], "
                f"and outcome LL is unchanged ({o['est']:+.4f} [{o['lo']:+.4f}, {o['hi']:+.4f}]). Keep the model tier-1 only.")
    return "tier-2 does not improve both metrics. Keep the model tier-1 only."


if __name__ == "__main__":
    main()
