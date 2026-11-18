"""EXPLORATORY (REPORT_v5 §2-3): rescoring of the round-4 results, no new requests, no new thresholds.

§2 Kalshi taking simulation (k = 2/3/5 pts, the same trades as stale_hist2 / REPORT_v4): each trade is
   scored three ways —
     (i)  CLV vs Kalshi's close mid (as before), pts;
     (ii) CLV vs Pinnacle's de-vigged close = last active Pinnacle price before the start, pts;
     (iii) settlement: P&L per contract net of the quadratic taker fee 0.07*P*(1-P) (multiplier 1), and ROI.
   Splits: entry ask < 0.30 / 0.30-0.70 / > 0.70; "Kalshi followed" = after entry and before the start,
   Kalshi's mid (team-1 YES terms) closed >= 50% of the entry gap between Pinnacle fair and Kalshi's mid
   (the same 50% criterion as the round-4 lag study), else "never followed".
§3 Thunderpick stale-at-open on the same n = 38 bets (Wayback, one snapshot per match):
   - stale duration bounds: one snapshot per match, so the duration is only bounded.
       lower bound = snapshot time - Pinnacle open (snapshot taken after the open; price still up then);
       if Thunderpick's published winner close equals the snapshot's winner price, the price is taken
       to have stayed up until the start (duration = start - open, right-censored);
   - CLV by |signal| bucket 2-3 / 3-5 / >= 5 pts (the move buckets used in round 4);
   - leave-one-event-out range of mean CLV.
Usage: python -m research.stale_hist3
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import numpy as np

from research import stale_hist as SH
from research import stale_hist2 as S2

OUT = SH.H.ROOT / "out" / "stale_hist3.json"
PRICE_BINS = ((0.0, 0.30, "<0.30"), (0.30, 0.70, "0.30-0.70"), (0.70, 1.01, ">0.70"))
SIG_BINS = ((0.02, 0.03, "2-3 pts"), (0.03, 0.05, "3-5 pts"), (0.05, 1.0, ">=5 pts"))


def pin_close(s, start: datetime) -> float | None:
    """Last active Pinnacle team-1 de-vigged price strictly before the start."""
    for t, p, a in zip(reversed(s.t), reversed(s.p1), reversed(s.active), strict=True):
        if t < start and a:
            return p
    return None


def enrich(trades: list[dict], ms, pin, kal) -> list[dict]:
    by = {m["match_id"]: m for m in ms}
    out = []
    for r in trades:
        m, s, kq = by[r["match_id"]], pin[r["match_id"]], kal[r["match_id"]]
        t = datetime.fromisoformat(r["t"])
        won = (m["y"] == 1.0) == (r["side"] == "yes")
        pc = pin_close(s, m["start"])
        pc_side = None if pc is None else (pc if r["side"] == "yes" else 1 - pc)
        fair_side = r["ask"] + r["edge"]
        fair_yes = fair_side if r["side"] == "yes" else 1 - fair_side
        mid0 = kq.mid(t)
        followed = None
        if mid0 is not None and abs(fair_yes - mid0) > 1e-9:
            _, followed = SH.lag(kq, t + timedelta(seconds=1), mid0, fair_yes - mid0, 0.5, m["start"])
        out.append({**r, "won": won, "pnl_c": 100 * ((1.0 if won else 0.0) - r["ask"] - r["fee"]),
                    "clv_pin_pts": None if pc_side is None else 100 * (pc_side - r["ask"]),
                    "followed": followed})
    return out


def summarize(rows: list[dict]) -> dict:
    def mean_of(k):
        return lambda rs: float(np.mean([x[k] for x in rs]))
    return {"n": len(rows), "n_matches": len({x["match_id"] for x in rows}),
            "mean_ask": float(np.mean([x["ask"] for x in rows])) if rows else None,
            "mean_fee_c": float(np.mean([100 * x["fee"] for x in rows])) if rows else None,
            "clv_kalshi_pts": SH.boot([x for x in rows if x["clv_pts"] is not None], mean_of("clv_pts")),
            "clv_pinnacle_pts": SH.boot([x for x in rows if x["clv_pin_pts"] is not None], mean_of("clv_pin_pts")),
            "pnl_c_per_contract": SH.boot(rows, mean_of("pnl_c")),
            "roi": SH.boot(rows, mean_of("roi"))}


def taking(ms, pin, kal) -> dict:
    res = {}
    for k in S2.KS:
        tr = enrich(SH.simulate(ms, pin, kal, {}, False, k, 1.0), ms, pin, kal)
        res[f"k={int(k * 100)}"] = {
            "all": summarize(tr),
            "by_price": {lab: summarize([x for x in tr if lo <= x["ask"] < hi]) for lo, hi, lab in PRICE_BINS},
            "by_follow": {"followed": summarize([x for x in tr if x["followed"] is True]),
                          "never_followed": summarize([x for x in tr if x["followed"] is False]),
                          "no_mid_at_entry": len([x for x in tr if x["followed"] is None])}}
    return res


def tp_followups(ms, pin) -> dict:
    rows = S2.tp_stale_at_open(ms, pin)
    bets = [r for r in rows if r.get("clv") is not None]
    con = sqlite3.connect(SH.H.DB)
    snap = {}
    for mid, tid, o, ts in con.execute("SELECT match_id, team_id, odds, snapshot_ts FROM prematch_odds WHERE book='thunderpick'"):
        snap.setdefault(mid, {"ts": ts, "px": {}})["px"][tid] = o
    close = {mid: (tid, o) for mid, tid, o in con.execute(
        "SELECT match_id, team_id, odds FROM match_odds WHERE book='thunderpick' AND observed_side='winner'")}
    by = {m["match_id"]: m for m in ms}
    dur = []
    for r in bets:
        m, s = by[r["match_id"]], pin[r["match_id"]]
        t_open = next(t for t, a in zip(s.t, s.active, strict=True) if a)
        t_snap = datetime.strptime(snap[r["match_id"]]["ts"], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        wtid, w_close = close[r["match_id"]]
        unchanged = abs(snap[r["match_id"]]["px"].get(wtid, -1) - w_close) < 1e-9
        lb = max(0.0, (t_snap - t_open).total_seconds() / 3600)
        to_start = (m["start"] - t_open).total_seconds() / 3600
        dur.append({"event": r["event"], "after_open": t_snap >= t_open, "unchanged_to_close": unchanged,
                    "lower_bound_h": to_start if unchanged else (lb if t_snap >= t_open else None),
                    "open_to_start_h": to_start, "snap_after_open_h": (t_snap - t_open).total_seconds() / 3600})
    lbs = [d["lower_bound_h"] for d in dur if d["lower_bound_h"] is not None]
    events = sorted({r["event"] for r in bets})
    loeo = {e: float(np.mean([r["clv"] for r in bets if r["event"] != e])) for e in events}
    return {
        "n_bets": len(bets), "n_events": len(events),
        "duration": {"n_bounded": len(lbs), "n_unbounded_before_open_changed": len(dur) - len(lbs),
                     "share_unchanged_to_close": float(np.mean([d["unchanged_to_close"] for d in dur])),
                     "lower_bound_median_h": float(np.median(lbs)) if lbs else None,
                     "lower_bound_min_h": float(min(lbs)) if lbs else None,
                     "open_to_start_median_h": float(np.median([d["open_to_start_h"] for d in dur])),
                     "rows": dur},
        "clv_all": SH.boot(bets, lambda rs: float(np.mean([x["clv"] for x in rs]))),
        "clv_by_signal": {lab: {"n": len(b := [x for x in bets if lo <= abs(x["signal"]) < hi]),
                                "n_events": len({x["event"] for x in b}),
                                "mean": float(np.mean([x["clv"] for x in b])) if b else None,
                                "boot": SH.boot(b, lambda rs: float(np.mean([x["clv"] for x in rs])))}
                          for lo, hi, lab in SIG_BINS},
        "clv_by_duration_class": {
            lab: {"n": len(b := [x for x, d in zip(bets, dur, strict=True) if f(d)]),
                  "mean": float(np.mean([x["clv"] for x in b])) if b else None}
            for lab, f in (("unchanged_to_close", lambda d: d["unchanged_to_close"]),
                           ("changed_before_close", lambda d: not d["unchanged_to_close"]))},
        "leave_one_event_out": {"min": min(loeo.values()), "max": max(loeo.values()),
                                "most_influential_event": min(loeo, key=loeo.get), "by_event": loeo,
                                "bets_per_event": {e: sum(1 for r in bets if r["event"] == e) for e in events}}}


def main() -> None:
    ms, pin, kal = SH.load_all()
    res = {"label": "EXPLORATORY — rescoring of round-4 trades/bets; no new requests, thresholds or filters",
           "taking": taking(ms, pin, kal), "tp_stale_at_open": tp_followups(ms, pin)}
    OUT.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: v for k, v in res["tp_stale_at_open"].items() if k != "duration"}, indent=1, default=str))
    print(json.dumps({k: {kk: vv for kk, vv in v["duration"].items() if kk != "rows"}
                      for k, v in {"tp": res["tp_stale_at_open"]}.items()}, indent=1, default=str))
    for k, v in res["taking"].items():
        print(k, json.dumps(v["all"], default=str))


if __name__ == "__main__":
    main()
