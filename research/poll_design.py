"""Windowed Pinnacle-open poll: cost / capture simulation on the 2026 tier-1 schedule (REPORT_v5 §4).

Inputs (cached, no requests): 2026 tier-1 vlr matches (start, UTC) and Pinnacle's first active record per
match (OddsPapi history). A design = (window [T - early, T - late], cadence c hours). Polls sit on a
fixed c-hour grid; a poll is made only if at least one scheduled match is inside its window and its
Pinnacle open has not been caught yet. One billable `odds-by-tournaments` call per poll covers every
fixture; plus one billable `fixtures` discovery call per UTC day with a poll (upper bound: in practice
only when a new match enters the window). Caught = the open falls inside the window; detection
delay = first poll at/after the open minus the open (opens before the window starts are caught at
the window start and counted as "already open").
Usage: python -m research.poll_design
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import timedelta

import numpy as np

from research import stale_hist as SH

OUT = SH.H.ROOT / "out" / "poll_design.json"
DESIGNS = [(30, 18, 1), (30, 18, 2), (48, 12, 2), (48, 12, 3), (72, 6, 3), (72, 6, 4), (96, 0, 4), (96, 0, 6),
           (72, 6, 6)]
FREE = 250


def simulate(ms: list[tuple], early: float, late: float, c: float) -> dict:
    t0 = min(s for s, _ in ms) - timedelta(hours=early + c)
    t1 = max(s for s, _ in ms)
    step = timedelta(hours=c)
    grid = []
    t = t0.replace(minute=0, second=0, microsecond=0)
    while t <= t1:
        grid.append(t)
        t += step
    polls = []
    for g in grid:
        if any(s - timedelta(hours=early) <= g < s - timedelta(hours=late) and (o is None or g <= o + step)
               for s, o in ms):
            polls.append(g)
    per_month = Counter(f"{g:%Y-%m}" for g in polls)
    disc = Counter(f"{d[:7]}" for d in {f"{g:%Y-%m-%d}" for g in polls})
    tot = {k: per_month[k] + disc[k] for k in per_month}
    caught, delays, already = 0, [], 0
    pset = sorted(polls)
    import bisect
    for s, o in ms:
        if o is None:
            continue
        w0, w1 = s - timedelta(hours=early), s - timedelta(hours=late)
        if o < w0:
            already += 1
            continue
        if o >= w1:
            continue
        i = bisect.bisect_left(pset, o)
        if i < len(pset) and pset[i] < w1 + step:
            caught += 1
            delays.append((pset[i] - o).total_seconds() / 3600)
    n = sum(1 for _, o in ms if o is not None)
    return {"window_h": [early, late], "cadence_h": c, "calls_by_month": dict(sorted(tot.items())),
            "peak_month_calls": max(tot.values()) if tot else 0,
            "mean_calls_per_active_month": float(np.mean(list(tot.values()))) if tot else 0,
            "n_opens": n, "share_caught_in_window": caught / n, "share_already_open_at_window_start": already / n,
            "share_open_after_window": 1 - (caught + already) / n,
            "median_detection_delay_h": float(np.median(delays)) if delays else None,
            "fits_free_with_margin": bool(tot) and max(tot.values()) <= 0.8 * FREE}


def main() -> None:
    ms, pin, _ = SH.load_all()
    rows = []
    for m in ms:
        s = pin.get(m["match_id"])
        o = next((t for t, a in zip(s.t, s.active, strict=True) if a), None) if s else None
        rows.append((m["start"], o if o is not None and o < m["start"] else None))
    h = np.array([(s - o).total_seconds() / 3600 for s, o in rows if o is not None])
    res = {"n_matches": len(rows), "n_with_open": int(len(h)),
           "open_hours_before_start_pct": dict(zip(("p5", "p10", "p25", "p50", "p75", "p90", "p95"),
                                                   np.percentile(h, [5, 10, 25, 50, 75, 90, 95]).round(1).tolist(),
                                                   strict=True)),
           "designs": [simulate(rows, *d) for d in DESIGNS]}
    OUT.write_text(json.dumps(res, indent=1, default=str))
    for d in res["designs"]:
        print({k: d[k] for k in ("window_h", "cadence_h", "peak_month_calls", "mean_calls_per_active_month",
                                 "share_caught_in_window", "share_already_open_at_window_start",
                                 "median_detection_delay_h", "fits_free_with_margin")})


if __name__ == "__main__":
    main()
