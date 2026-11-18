"""EXPLORATORY (REPORT_v6 §1): de-vig robustness, no new requests.

For each de-vig method (multiplicative, power, Shin; research/devig.py), applied to Pinnacle (fair and
close) and, in the stale-at-open set, to Thunderpick's snapshot too:
  - Kalshi taking at k = 3 / 5 (the round-4 rule; trades re-selected with that method's fair):
    n, CLV vs Pinnacle close (same method), CLV net of the quadratic fee, by entry ask < 0.30 / 0.30-0.70 / > 0.70;
  - Thunderpick stale-at-open (Wayback snapshot, REPORT_v4/v5 set): n bets, CLV vs Thunderpick close, and the
    pre-declared |gap| slices 2-3 / 3-5 / > 5 pts;
  - Shin failure rate per market (PREREG §11 primary-method rule: Shin unless it fails on > 5% of markets):
    a market fails if Shin has no valid solution at any active two-sided Pinnacle record before its start.
Usage: python -m research.devig_robust
"""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone

import numpy as np

from research import pinnacle as PN
from research import stale_hist as SH
from research import stale_hist2 as S2
from research import stale_hist3 as S3
from research.devig import METHODS, devig

OUT = SH.H.ROOT / "out" / "devig_robust.json"
KS = (0.03, 0.05)
GAPS = ((0.02, 0.03, "2-3 pts"), (0.03, 0.05, "3-5 pts"), (0.05, 1.0, ">5 pts"))


def pin_series(ms, method: str) -> dict:
    mp = json.loads((SH.H.CACHE / "mapping.json").read_text())
    out = {}
    for m in ms:
        f = mp["oddspapi"].get(str(m["match_id"]))
        if f:
            h = PN.load(f["fixtureId"])
            s = PN.series(h, f["p1_is_team1"], method=method) if h else None
            if s:
                out[m["match_id"]] = s
    return out


def shin_failures(ms, pin_shin: dict) -> dict:
    n = fail = rec = rec_fail = 0
    for m in ms:
        s = pin_shin.get(m["match_id"])
        if s is None:
            continue
        oks = [ok for t, a, ok in zip(s.t, s.active, s.ok, strict=True) if a and t < m["start"]]
        if not oks:
            continue
        n += 1
        fail += not all(oks)
        rec += len(oks)
        rec_fail += sum(1 for x in oks if not x)
    return {"n_markets": n, "n_markets_failed": fail, "share_markets_failed": fail / n if n else None,
            "n_records": rec, "n_records_failed": rec_fail}


def taking(ms, pin, kal) -> dict:
    res = {}
    for k in KS:
        tr = S3.enrich(SH.simulate(ms, pin, kal, {}, False, k, 1.0), ms, pin, kal)
        for x in tr:
            x["clv_pin_net_pts"] = None if x["clv_pin_pts"] is None else x["clv_pin_pts"] - 100 * x["fee"]

        def summ(rows):
            def mean_of(key):
                return lambda rs: float(np.mean([r[key] for r in rs]))
            ok = [r for r in rows if r["clv_pin_pts"] is not None]
            return {"n": len(rows), "clv_pin_pts": SH.boot(ok, mean_of("clv_pin_pts")),
                    "clv_pin_net_pts": SH.boot(ok, mean_of("clv_pin_net_pts")),
                    "clv_kalshi_pts": SH.boot([r for r in rows if r["clv_pts"] is not None], mean_of("clv_pts"))}
        res[f"k={int(k * 100)}"] = {"all": summ(tr),
                                    "by_price": {lab: summ([x for x in tr if lo <= x["ask"] < hi])
                                                 for lo, hi, lab in S3.PRICE_BINS}}
    return res


def tp_stale(ms, pin, method: str) -> dict:
    """stale_hist2.tp_stale_at_open with the Thunderpick snapshot de-vigged by `method` as well."""
    con = sqlite3.connect(SH.H.DB)
    snaps: dict = {}
    for mid, tid, o, ts in con.execute("SELECT match_id, team_id, odds, snapshot_ts FROM prematch_odds WHERE book='thunderpick'"):
        snaps.setdefault(mid, {"ts": ts, "px": {}})["px"][tid] = o
    close = {mid: (tid, o) for mid, tid, o in con.execute(
        "SELECT match_id, team_id, odds FROM match_odds WHERE book='thunderpick' AND observed_side='winner'")}
    bets = []
    for m in ms:
        sn, s = snaps.get(m["match_id"]), pin.get(m["match_id"])
        if sn is None or len(sn["px"]) != 2 or s is None or m["match_id"] not in close:
            continue
        t_snap = datetime.strptime(sn["ts"], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        t_open = next((t for t, a in zip(s.t, s.active, strict=True) if a), None)
        if t_snap >= m["start"] or t_open is None or t_open >= m["start"]:
            continue
        if t_snap < t_open:
            p_ref = s.at(t_open)[0]
        else:
            st = s.at(t_snap)
            if st is None or not st[1]:
                continue
            p_ref = st[0]
        pa, pb = sn["px"].get(m["a"]), sn["px"].get(m["b"])
        if pa is None or pb is None:
            continue
        p_tp = devig(pa, pb, method)[0]
        sig = p_ref - p_tp
        if abs(sig) < S2.SIGNAL_MIN:
            continue
        side = m["a"] if sig > 0 else m["b"]
        wtid, w_o = close[m["match_id"]]
        V = 1 / pa + 1 / pb
        o_close = w_o if wtid == side else (1 / (V - 1 / w_o) if V - 1 / w_o > 0.01 else None)
        if o_close:
            bets.append({"event": m["event"], "match_id": m["match_id"], "signal": sig,
                         "clv": math.log(sn["px"][side] / o_close)})

    def mean_clv(rs):
        return float(np.mean([r["clv"] for r in rs]))
    return {"n_bets": len(bets), "n_events": len({b["event"] for b in bets}), "clv": SH.boot(bets, mean_clv),
            "by_gap": {lab: {"n": len(b := [x for x in bets if lo <= abs(x["signal"]) < hi]),
                             "clv": SH.boot(b, mean_clv), "mean": mean_clv(b) if b else None}
                       for lo, hi, lab in GAPS},
            "match_ids": sorted(b["match_id"] for b in bets)}


def main() -> None:
    ms, pin_mult, kal = SH.load_all()
    pins = {"mult": pin_mult, **{m: pin_series(ms, m) for m in METHODS if m != "mult"}}
    res = {"label": "EXPLORATORY — de-vig robustness; no new requests",
           "shin_failures": shin_failures(ms, pins["shin"]),
           "taking": {m: taking(ms, pins[m], kal) for m in METHODS},
           "tp_stale_at_open": {m: tp_stale(ms, pins[m], m) for m in METHODS}}
    base = set(res["tp_stale_at_open"]["mult"]["match_ids"])
    for m in METHODS:
        ids = set(res["tp_stale_at_open"][m]["match_ids"])
        res["tp_stale_at_open"][m]["overlap_with_mult"] = len(ids & base)
    OUT.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res["shin_failures"]))
    for m in METHODS:
        for k, v in res["taking"][m].items():
            a = v["all"]
            print(m, k, a["n"], {kk: round(a[kk].get("est", float("nan")), 2) for kk in ("clv_pin_pts", "clv_pin_net_pts")})
        t = res["tp_stale_at_open"][m]
        print(m, "TP", t["n_bets"], t["clv"].get("est"), t["overlap_with_mult"])


if __name__ == "__main__":
    main()
