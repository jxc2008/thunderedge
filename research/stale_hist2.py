"""EXPLORATORY (REPORT_v4 §2): full pre-match window, no new requests (cached Pinnacle + Kalshi + Wayback).

(c) Pinnacle -> Kalshi lag: every Pinnacle move >= 2 pts (anchor method: from the last anchor, the
    first record >= 2 pts away is a move; the anchor resets there). Kalshi lag = minutes from the
    move until Kalshi's mid covers 50% / 90% of it, measured from Kalshi's mid at the anchor.
    Kaplan-Meier median / IQR (censored at the match start), by move size.
(b) Taking simulation over the whole pre-match window: buy Kalshi YES or NO when Pinnacle de-vigged
    fair - Kalshi ask > k (k = 2, 3, 5 pts only), taker fee 0.07*P*(1-P) (series multiplier 1),
    first trigger per match x side, 1 contract (Kalshi's historical candles carry no displayed
    size, so the size cap cannot be applied beyond the 1-contract minimum that any displayed ask
    covers). ROI per contract; CLV = Kalshi close mid - entry ask (pts); event-bootstrap CIs.
(TP) Rough stale-at-open look: the 2026 Wayback Thunderpick two-sided snapshot (one per match)
    against Pinnacle's opening price (snapshot before Pinnacle opened) or Pinnacle's standing price
    (snapshot after it opened). Bet if |signal| >= 2 pts at the snapshot price; CLV vs the
    Thunderpick close (winner's published close; the loser's close backed out with the snapshot's
    overround). Rough: one snapshot per match, so "standing at open" assumes no change in between.
Usage: python -m research.stale_hist2
"""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone

import numpy as np

from research import stale_hist as SH

OUT = SH.H.ROOT / "out" / "stale_hist2.json"
MOVE_BINS = (0.02, 0.03, 0.05, 1.0)
KS = (0.02, 0.03, 0.05)
SIGNAL_MIN = 0.02


def moves(ms, pin, kal) -> list[dict]:
    rows = []
    for m in ms:
        s, kq = pin.get(m["match_id"]), kal.get(m["match_id"])
        if s is None or kq is None:
            continue
        anchor = None
        for t, p, act in zip(s.t, s.p1, s.active, strict=True):
            if t >= m["start"]:
                break
            if not act:
                anchor = None
                continue
            if anchor is None:
                anchor = (t, p)
                continue
            d = p - anchor[1]
            if abs(d) >= SH.MIN_MOVE:
                k0 = kq.mid(anchor[0])
                if k0 is not None:
                    r = {"event": m["event"], "delta": d, "hours_to_start": (m["start"] - t).total_seconds() / 3600}
                    for frac in (0.5, 0.9):
                        r[f"k{int(frac * 100)}"], r[f"k{int(frac * 100)}_hit"] = SH.lag(kq, t - timedelta(minutes=1), k0, d,
                                                                                       frac, m["start"])
                    rows.append(r)
                anchor = (t, p)
    return rows


def lag_summary(rows: list[dict]) -> dict:
    out = {"n": len(rows), "n_events": len({r["event"] for r in rows})}
    for f in ("k50", "k90"):
        ts, ev = [r[f] for r in rows], [r[f + "_hit"] for r in rows]
        out[f] = {"median": SH.km_quantile(ts, ev, .5), "p25": SH.km_quantile(ts, ev, .25),
                  "p75": SH.km_quantile(ts, ev, .75), "share_never": float(np.mean([not e for e in ev])) if rows else None}
    return out


def tp_stale_at_open(ms, pin) -> list[dict]:
    from research.timeutil import vlr_to_utc  # noqa: F401  (match starts already UTC via hist_fetch)
    con = sqlite3.connect(SH.H.DB)
    snaps: dict = {}
    for mid, tid, o, ts in con.execute("""SELECT match_id, team_id, odds, snapshot_ts FROM prematch_odds
                                          WHERE book='thunderpick'"""):
        snaps.setdefault(mid, {"ts": ts, "px": {}})["px"][tid] = o
    close = {mid: (tid, o) for mid, tid, o in con.execute(
        "SELECT match_id, team_id, odds FROM match_odds WHERE book='thunderpick' AND observed_side='winner'")}
    rows = []
    for m in ms:
        sn, s = snaps.get(m["match_id"]), pin.get(m["match_id"])
        if sn is None or len(sn["px"]) != 2 or s is None or m["match_id"] not in close:
            continue
        t_snap = datetime.strptime(sn["ts"], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)  # Wayback ts is UTC
        if t_snap >= m["start"]:
            continue
        t_open = next((t for t, a in zip(s.t, s.active, strict=True) if a), None)
        if t_open is None or t_open >= m["start"]:
            continue
        if t_snap < t_open:
            p_ref, regime = s.at(t_open)[0], "snapshot_before_open (TP assumed unchanged to open)"
        else:
            st = s.at(t_snap)
            if st is None or not st[1]:
                continue
            p_ref, regime = st[0], "snapshot_after_open (Pinnacle standing at snapshot)"
        pa, pb = sn["px"].get(m["a"]), sn["px"].get(m["b"])
        if pa is None or pb is None:
            continue
        V = 1 / pa + 1 / pb
        p_tp = (1 / pa) / V
        sig = p_ref - p_tp
        row = {"event": m["event"], "match_id": m["match_id"], "regime": regime, "signal": sig,
               "hours_snap_before_start": (m["start"] - t_snap).total_seconds() / 3600,
               "hours_open_before_start": (m["start"] - t_open).total_seconds() / 3600}
        if abs(sig) >= SIGNAL_MIN:
            side = m["a"] if sig > 0 else m["b"]
            o_bet = sn["px"][side]
            wtid, w_o = close[m["match_id"]]
            if wtid == side:
                o_close = w_o
            else:
                rest = V - 1 / w_o
                o_close = 1 / rest if rest > 0.01 else None
            row.update(side=side, pnl=(o_bet - 1) if m["winner"] == side else -1.0,
                       clv=math.log(o_bet / o_close) if o_close else None)
        rows.append(row)
    return rows


def main() -> None:
    ms, pin, kal = SH.load_all()
    res: dict = {"label": "EXPLORATORY — full pre-match window; no new requests"}
    mv = moves(ms, pin, kal)
    res["c_lag_all"] = lag_summary(mv)
    res["c_lag_by_move"] = {f"{lo * 100:.0f}-{hi * 100:.0f}pts": lag_summary([r for r in mv if lo <= abs(r["delta"]) < hi])
                            for lo, hi in zip(MOVE_BINS[:-1], MOVE_BINS[1:], strict=True)}
    res["c_lag_by_time_to_start"] = {lab: lag_summary([r for r in mv if lo <= r["hours_to_start"] < hi])
                                     for lab, lo, hi in (("<2h", 0, 2), ("2-12h", 2, 12), (">=12h", 12, 1e9))}
    res["b_taking"] = {f"k={int(k * 100)}": SH.strat_summary(SH.simulate(ms, pin, kal, {}, False, k, 1.0)) for k in KS}
    tp = tp_stale_at_open(ms, pin)
    bets = [r for r in tp if r.get("clv") is not None]
    res["tp_stale_at_open"] = {
        "n_matches": len(tp), "by_regime": {g: sum(1 for r in tp if r["regime"] == g) for g in {r["regime"] for r in tp}},
        "median_abs_signal_pts": float(np.median([100 * abs(r["signal"]) for r in tp])) if tp else None,
        "n_bets": len(bets),
        "clv": SH.boot(bets, lambda rs: float(np.mean([r["clv"] for r in rs]))),
        "roi_at_snapshot_price": SH.boot(bets, lambda rs: float(np.mean([r["pnl"] for r in rs]))),
        "by_regime": {g: {"n_bets": len(b := [r for r in bets if r["regime"] == g]),
                          "clv": SH.boot(b, lambda rs: float(np.mean([r["clv"] for r in rs])))}
                      for g in {r["regime"] for r in bets}},
        "median_hours_open_before_start": float(np.median([r["hours_open_before_start"] for r in tp])) if tp else None,
        "median_hours_snap_before_start": float(np.median([r["hours_snap_before_start"] for r in tp])) if tp else None}
    OUT.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
