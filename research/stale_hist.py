"""EXPLORATORY historical study (REPORT_v3 §5): Pinnacle as the reference, Kalshi as the stale venue.

Stage R (reference checks, run first):
  R1  Pinnacle record resolution for VALORANT: gaps between consecutive price records pre-match.
  R2  For each result M: time from M's end (vlr: scheduled start + map durations + 10-min breaks)
      to Pinnacle's first price change on each team's next match N; share of N lines absent or
      pulled at end(M) and for how long.
  STOP RULE (user, 2026-11-17): if the median reprice (R2, lines active at end(M)) > 60 min or the
  median record gap (R1) > 15 min, report and do not run the taking simulations (b), (c).
Stage (a) Kalshi lag after results: minutes for Kalshi's mid on N to cover 50% / 90% of Pinnacle's
      move (Pinnacle at end(M)+60 min vs just before end(M)); median, IQR (Kaplan-Meier), by surprise.
Stage (b) taking strategy inside result windows [end(M), end(M)+6 h): buy Kalshi (YES or NO) when
      Pinnacle fair - Kalshi ask > k, k in {2, 3, 5} pts, net of taker fee 0.07*P*(1-P)*multiplier;
      first trigger per (N, side); ROI, CLV vs Kalshi close; CIs by event bootstrap.
Stage (c) the same strategy outside result windows, plus Kalshi's lag to general Pinnacle moves
      (>= 2 pts) outside result windows.
No parameter search beyond the three k values. Usage: python -m research.stale_hist
"""
from __future__ import annotations

import bisect
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np
from bs4 import BeautifulSoup

from research import hist_fetch as H
from research import pinnacle as PN
from research import vlr_fetch as v

OUT = H.ROOT / "out" / "stale_hist.json"
BREAK_MIN = 10
NEXT_WITHIN = timedelta(days=7)
WINDOW = timedelta(hours=6)
PIN_SETTLE = timedelta(minutes=60)
KS = (0.02, 0.03, 0.05)
MIN_MOVE = 0.02
FEE_RATE = 0.07           # Kalshi taker: rate * P * (1-P) per contract (x series multiplier; see main)
NB = 2000
SURPRISE_BINS = (0.0, 0.3, 0.6, 1.01)


# ------------------------------------------------------------------------------ inputs
def durations(url: str) -> list[float] | None:
    try:
        html = v.get(url, budget=v.live_requests_used())  # cache only: any live request would exceed
    except Exception:  # noqa: BLE001
        return None
    out = []
    for t in BeautifulSoup(html, "lxml").select(".map-duration"):
        parts = [int(x) for x in re.findall(r"\d+", t.get_text())]
        if len(parts) == 2:
            out.append(parts[0] + parts[1] / 60)
        elif len(parts) == 3:
            out.append(parts[0] * 60 + parts[1] + parts[2] / 60)
    return out or None


def _f(x) -> float | None:
    if x is None:
        return None
    x = float(x)
    return x / 100 if x > 1.5 else x


class Kalshi:
    """1-min team-1 YES quotes, forward-filled between candles."""

    def __init__(self, d: dict) -> None:
        rows = []
        for c in d.get("candlesticks", []):
            ya, yb = c.get("yes_ask") or {}, c.get("yes_bid") or {}
            a = _f(ya.get("close") if "close" in ya else ya.get("close_dollars"))
            b = _f(yb.get("close") if "close" in yb else yb.get("close_dollars"))
            rows.append((datetime.fromtimestamp(c["end_period_ts"], timezone.utc), b, a))
        rows.sort()
        self.t = [r[0] for r in rows]
        self.bid = [r[1] for r in rows]
        self.ask = [r[2] for r in rows]

    def at(self, when: datetime) -> tuple[float | None, float | None]:
        i = bisect.bisect_right(self.t, when) - 1
        return (None, None) if i < 0 else (self.bid[i], self.ask[i])

    def mid(self, when: datetime) -> float | None:
        b, a = self.at(when)
        return (a + b) / 2 if a is not None and b is not None and 0 < b < a <= 1 else None

    def minutes(self, lo: datetime, hi: datetime) -> list[datetime]:
        i, j = bisect.bisect_left(self.t, lo), bisect.bisect_left(self.t, hi)
        return self.t[i:j]


def load_all() -> tuple[list[dict], dict, dict]:
    mp = json.loads((H.CACHE / "mapping.json").read_text())
    ms = H.vlr_matches(2026)
    pin, kal = {}, {}
    for m in ms:
        k = str(m["match_id"])
        f = mp["oddspapi"].get(k)
        if f:
            h = PN.load(f["fixtureId"])
            s = PN.series(h, f["p1_is_team1"]) if h else None
            if s:
                pin[m["match_id"]] = s
        kk = mp["kalshi"].get(k)
        if kk:
            fp = H.CACHE / f"k_candles_{kk['ticker_team1']}.json"
            if fp.exists():
                d = json.loads(fp.read_text())
                if "candlesticks" in d:
                    kal[m["match_id"]] = Kalshi(d)
        du = durations(m["url"])
        m["end_vlr"] = (m["start"] + timedelta(minutes=sum(du) + BREAK_MIN * (len(du) - 1))) if du else None
        m["y"] = 1.0 if m["winner"] == m["a"] else 0.0
    return ms, pin, kal


def km_quantile(times: list[float], events: list[bool], q: float) -> float | None:
    """Kaplan-Meier time by which a fraction q has 'reached' (events False = censored)."""
    order = sorted(zip(times, events, strict=True))
    n, surv = len(order), 1.0
    for i, (t, e) in enumerate(order):
        if e:
            surv *= 1 - 1 / (n - i)
            if 1 - surv >= q:
                return t
    return None


def boot(rows: list[dict], fn, key: str = "event") -> dict:
    if len(rows) < 5:
        return {"n": len(rows)}
    ev = np.array([r[key] for r in rows])
    uc = np.unique(ev)
    idx = {c: np.nonzero(ev == c)[0] for c in uc}
    rng = np.random.default_rng(0)
    d = []
    for _ in range(NB):
        pick = np.concatenate([idx[c] for c in rng.choice(uc, len(uc))])
        d.append(fn([rows[i] for i in pick]))
    return {"n": len(rows), "n_events": len(uc), "est": float(fn(rows)), "lo": float(np.percentile(d, 2.5)),
            "hi": float(np.percentile(d, 97.5))}


# ------------------------------------------------------------------------------ pairs
def result_pairs(ms: list[dict]) -> list[tuple[dict, dict]]:
    """(M, N): N is the next match (after end(M), within 7 days) of either team of M."""
    by_team = defaultdict(list)
    for m in ms:
        by_team[m["a"]].append(m)
        by_team[m["b"]].append(m)
    out = []
    for m in ms:
        if m["end_vlr"] is None:
            continue
        for t in (m["a"], m["b"]):
            nxt = [n for n in by_team[t] if n["start"] > m["end_vlr"] and n["start"] - m["end_vlr"] <= NEXT_WITHIN]
            if nxt:
                out.append((m, min(nxt, key=lambda n: n["start"])))
    return out


# ------------------------------------------------------------------------------ stages
def stage_r(ms, pin, pairs) -> dict:
    gaps, per_fix = [], []
    for m in ms:
        s = pin.get(m["match_id"])
        if s:
            g = s.gaps_minutes(m["start"])
            gaps += g
            if g:
                per_fix.append(float(np.median(g)))
    r1 = {"n_fixtures": len(per_fix), "n_gaps": len(gaps), "median_gap_min": float(np.median(gaps)),
          "p90_gap_min": float(np.percentile(gaps, 90)), "max_gap_min": float(max(gaps)),
          "median_of_fixture_medians_min": float(np.median(per_fix)),
          "fixture_records_pre_start_median": float(np.median([len([x for x in pin[m["match_id"]].t if x < m["start"]])
                                                               for m in ms if m["match_id"] in pin]))}
    rows = []
    for M, N in pairs:
        s = pin.get(N["match_id"])
        if s is None:
            rows.append({"state": "no_pinnacle_fixture"})
            continue
        end = M["end_vlr"]
        st = s.at(end)
        surprise = None
        sm = pin.get(M["match_id"])
        if sm is not None and sm.at(M["start"]) is not None:
            p_pre = sm.at(M["start"])[0]
            surprise = abs(M["y"] - p_pre)
        row = {"state": "absent" if st is None else ("active" if st[1] else "pulled"), "surprise": surprise,
               "event": N["event"], "hours_to_next": (N["start"] - end).total_seconds() / 3600}
        if st is None or not st[1]:
            na = s.next_active_after(end)
            row["minutes_until_active"] = (na - end).total_seconds() / 60 if na and na < N["start"] else None
        else:
            fc = s.first_change_after(end)
            fc1 = s.first_change_after(end, min_move=0.01)
            cap = (N["start"] - end).total_seconds() / 60
            row["reprice_min"] = min((fc - end).total_seconds() / 60, cap) if fc else cap
            row["reprice_observed"] = bool(fc and fc < N["start"])
            row["reprice_1pt_min"] = min((fc1 - end).total_seconds() / 60, cap) if fc1 else cap
            row["reprice_1pt_observed"] = bool(fc1 and fc1 < N["start"])
            # routine tick rate for comparison: same line, 3 h before end(M) if it was active then
            base = end - timedelta(hours=3)
            b0 = s.at(base)
            if b0 is not None and b0[1]:
                fb = s.first_change_after(base)
                row["baseline_reprice_min"] = (fb - base).total_seconds() / 60 if fb else None
        rows.append(row)
    act = [r for r in rows if r["state"] == "active"]
    st_counts = defaultdict(int)
    for r in rows:
        st_counts[r["state"]] += 1
    r2 = {"n_pairs": len(rows), "states": dict(st_counts),
          "reprice_median_min_km": km_quantile([r["reprice_min"] for r in act], [r["reprice_observed"] for r in act], .5),
          "reprice_p25_min_km": km_quantile([r["reprice_min"] for r in act], [r["reprice_observed"] for r in act], .25),
          "reprice_p75_min_km": km_quantile([r["reprice_min"] for r in act], [r["reprice_observed"] for r in act], .75),
          "reprice_1pt_median_min_km": km_quantile([r["reprice_1pt_min"] for r in act],
                                                   [r["reprice_1pt_observed"] for r in act], .5),
          "baseline_reprice_median_min": float(np.median([r["baseline_reprice_min"] for r in act
                                                          if r.get("baseline_reprice_min") is not None]))
          if any(r.get("baseline_reprice_min") is not None for r in act) else None,
          "absent_or_pulled_minutes_until_active_median": float(np.median(
              [r["minutes_until_active"] for r in rows if r.get("minutes_until_active") is not None]))
          if any(r.get("minutes_until_active") is not None for r in rows) else None,
          "absent_or_pulled_never_active_before_start": sum(1 for r in rows if r["state"] in ("absent", "pulled")
                                                            and r.get("minutes_until_active") is None)}
    r2["by_surprise"] = {}
    for lo, hi in zip(SURPRISE_BINS[:-1], SURPRISE_BINS[1:], strict=True):
        a = [r for r in act if r["surprise"] is not None and lo <= r["surprise"] < hi]
        r2["by_surprise"][f"{lo}-{hi}"] = {"n": len(a), "reprice_median_min_km": km_quantile(
            [r["reprice_min"] for r in a], [r["reprice_observed"] for r in a], .5) if a else None}
    return {"R1": r1, "R2": r2}


def lag(k: Kalshi, t0: datetime, k0: float, delta: float, frac: float, until: datetime) -> tuple[float, bool]:
    for t in k.minutes(t0, until):
        md = k.mid(t)
        if md is not None and math.copysign(1, delta) * (md - k0) >= frac * abs(delta):
            return (t - t0).total_seconds() / 60, True
    return (until - t0).total_seconds() / 60, False


def stage_a(pairs, pin, kal) -> dict:
    rows = []
    for M, N in pairs:
        s, k = pin.get(N["match_id"]), kal.get(N["match_id"])
        if s is None or k is None:
            continue
        end = M["end_vlr"]
        p0, p1 = s.at(end - timedelta(minutes=1)), s.at(end + PIN_SETTLE)
        k0 = k.mid(end - timedelta(minutes=1))
        if p0 is None or p1 is None or not p0[1] or not p1[1] or k0 is None or end + PIN_SETTLE >= N["start"]:
            continue
        d = p1[0] - p0[0]
        if abs(d) < MIN_MOVE:
            continue
        sm = pin.get(M["match_id"])
        sur = abs(M["y"] - sm.at(M["start"])[0]) if sm is not None and sm.at(M["start"]) else None
        r = {"event": N["event"], "delta": d, "surprise": sur}
        for frac in (0.5, 0.9):
            r[f"k{int(frac * 100)}"], r[f"k{int(frac * 100)}_hit"] = lag(k, end, k0, d, frac, N["start"])
            # Pinnacle's own time to the same fraction (always within the settle window by construction)
            pl = next(((t - end).total_seconds() / 60 for t in s.t if end <= t <= end + PIN_SETTLE
                       and math.copysign(1, d) * (s.at(t)[0] - p0[0]) >= frac * abs(d)), None)
            r[f"p{int(frac * 100)}"] = pl
        rows.append(r)

    def summ(rs):
        out = {"n": len(rs)}
        for f in ("k50", "k90"):
            ts, ev = [r[f] for r in rs], [r[f + "_hit"] for r in rs]
            out[f] = {"median": km_quantile(ts, ev, .5), "p25": km_quantile(ts, ev, .25),
                      "p75": km_quantile(ts, ev, .75), "share_never": float(np.mean([not e for e in ev])) if rs else None}
        for f in ("p50", "p90"):
            xs = [r[f] for r in rs if r[f] is not None]
            out[f + "_median"] = float(np.median(xs)) if xs else None
        return out

    res = {"all": summ(rows), "by_surprise": {}}
    for lo, hi in zip(SURPRISE_BINS[:-1], SURPRISE_BINS[1:], strict=True):
        res["by_surprise"][f"{lo}-{hi}"] = summ([r for r in rows if r["surprise"] is not None and lo <= r["surprise"] < hi])
    return res


def windows_by_match(pairs) -> dict[int, list[tuple[datetime, datetime]]]:
    w = defaultdict(list)
    for M, N in pairs:
        w[N["match_id"]].append((M["end_vlr"], min(M["end_vlr"] + WINDOW, N["start"])))
    return w


def simulate(ms, pin, kal, wins, inside: bool, k_thr: float, mult: float) -> list[dict]:
    """First trigger per (match, side) in the regime; buy at the ask, pay taker fee, settle at 0/1."""
    out = []
    for m in ms:
        s, kq = pin.get(m["match_id"]), kal.get(m["match_id"])
        if s is None or kq is None:
            continue
        lo = max(kq.t[0] if kq.t else m["start"], s.t[0])
        ws = wins.get(m["match_id"], [])
        close_mid = kq.mid(m["start"] - timedelta(minutes=1))
        done = set()
        for t in kq.minutes(lo, m["start"]):
            in_w = any(a <= t < b for a, b in ws)
            if in_w != inside:
                continue
            ps = s.at(t)
            b, a = kq.at(t)
            if ps is None or not ps[1] or a is None or b is None or not (0 < b < a <= 1):
                continue
            for side, fair, ask in (("yes", ps[0], a), ("no", 1 - ps[0], 1 - b)):
                if side in done or not 0.01 <= ask <= 0.99:
                    continue
                fee = FEE_RATE * mult * ask * (1 - ask)
                if fair - ask > k_thr:
                    won = (m["y"] == 1.0) == (side == "yes")
                    cost = ask + fee
                    cm = None if close_mid is None else (close_mid if side == "yes" else 1 - close_mid)
                    out.append({"event": m["event"], "match_id": m["match_id"], "side": side, "t": t.isoformat(),
                                "edge": fair - ask, "ask": ask, "fee": fee, "roi": ((1.0 if won else 0.0) - cost) / cost,
                                "clv_pts": None if cm is None else 100 * (cm - ask)})
                    done.add(side)
            if len(done) == 2:
                break
    return out


def general_lag(ms, pin, kal, wins) -> dict:
    rows = []
    for m in ms:
        s, kq = pin.get(m["match_id"]), kal.get(m["match_id"])
        if s is None or kq is None:
            continue
        ws = wins.get(m["match_id"], [])
        anchor = None
        for t, p, act in zip(s.t, s.p1, s.active, strict=True):
            if t >= m["start"]:
                break
            if not act or any(a <= t < b for a, b in ws):
                anchor = None
                continue
            if anchor is None:
                anchor = (t, p)
                continue
            d = p - anchor[1]
            if abs(d) >= MIN_MOVE:
                k0 = kq.mid(anchor[0])
                if k0 is not None:
                    r = {"event": m["event"], "delta": d}
                    for frac in (0.5, 0.9):
                        # Kalshi measured from the anchor level; lag counted from Pinnacle's move time t
                        r[f"k{int(frac * 100)}"], r[f"k{int(frac * 100)}_hit"] = lag(kq, t - timedelta(minutes=1), k0, d,
                                                                                    frac, m["start"])
                    rows.append(r)
                anchor = (t, p)
    out = {"n_moves": len(rows)}
    for f in ("k50", "k90"):
        ts, ev = [r[f] for r in rows], [r[f + "_hit"] for r in rows]
        out[f] = {"median": km_quantile(ts, ev, .5), "p25": km_quantile(ts, ev, .25), "p75": km_quantile(ts, ev, .75),
                  "share_never": float(np.mean([not e for e in ev])) if rows else None}
    return out


def strat_summary(rows: list[dict]) -> dict:
    return {"n": len(rows), "n_matches": len({r["match_id"] for r in rows}),
            "roi": boot(rows, lambda rs: float(np.mean([r["roi"] for r in rs]))),
            "clv_pts": boot([r for r in rows if r["clv_pts"] is not None],
                            lambda rs: float(np.mean([r["clv_pts"] for r in rs]))),
            "mean_edge_pts": float(np.mean([100 * r["edge"] for r in rows])) if rows else None}


def main() -> None:
    ms, pin, kal = load_all()
    pairs = result_pairs(ms)
    res: dict = {"label": "EXPLORATORY", "n_matches": len(ms), "n_pinnacle": len(pin), "n_kalshi": len(kal),
                 "n_end_vlr": sum(1 for m in ms if m["end_vlr"]), "n_result_pairs": len(pairs)}
    # end-time cross-check: vlr estimate vs Kalshi's own market reaching 0.98/0.02
    diffs = []
    for m in ms:
        kq = kal.get(m["match_id"])
        if kq is None or m["end_vlr"] is None:
            continue
        for t in kq.minutes(m["start"], m["start"] + timedelta(hours=8)):
            b, a = kq.at(t)
            if (b is not None and b >= 0.98) or (a is not None and a <= 0.02):
                diffs.append((t - m["end_vlr"]).total_seconds() / 60)
                break
    res["end_check_kalshi_minus_vlr_min"] = {"n": len(diffs), "median": float(np.median(diffs)) if diffs else None,
                                             "p25": float(np.percentile(diffs, 25)) if diffs else None,
                                             "p75": float(np.percentile(diffs, 75)) if diffs else None}
    res.update(stage_r(ms, pin, pairs))
    med_rep = res["R2"]["reprice_median_min_km"]
    stop = (med_rep is None or med_rep > 60) or res["R1"]["median_gap_min"] > 15
    res["stop_rule"] = {"median_reprice_min": med_rep, "median_gap_min": res["R1"]["median_gap_min"], "stopped": stop}
    res["a_kalshi_lag_after_results"] = stage_a(pairs, pin, kal)
    if not stop:
        mult = json.loads((H.CACHE / "kalshi_series.json").read_text()).get("series", {}).get("fee_multiplier", 1) \
            if (H.CACHE / "kalshi_series.json").exists() else 1
        res["fee_multiplier"] = mult
        wins = windows_by_match(pairs)
        res["b_result_windows"] = {f"k={int(k * 100)}": strat_summary(simulate(ms, pin, kal, wins, True, k, float(mult)))
                                   for k in KS}
        res["c_outside_windows"] = {f"k={int(k * 100)}": strat_summary(simulate(ms, pin, kal, wins, False, k, float(mult)))
                                    for k in KS}
        res["c_general_lag"] = general_lag(ms, pin, kal, wins)
    OUT.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: res[k] for k in res if k not in ("b_result_windows", "c_outside_windows")}, indent=1,
                     default=str)[:4000])
    if not stop:
        for reg in ("b_result_windows", "c_outside_windows"):
            for k, blk in res[reg].items():
                print(reg, k, blk["n"], blk["roi"].get("est"), blk["roi"].get("lo"), blk["roi"].get("hi"),
                      "clv", blk["clv_pts"].get("est"))


if __name__ == "__main__":
    main()
