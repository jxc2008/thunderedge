"""Pinnacle reference line from OddsPapi /historical-odds (match winner, market 611).

Shared by the exploratory historical study (research/stale_hist.py) and the frozen Kickoff 2027
evaluation (research/prereg_kickoff2027.py, §10). Raw OddsPapi responses live in
research/cache/hist/op_hist_<fixtureId>.json (gitignored; the terms forbid redistribution).

A history is turned into a step series of records (t, p1, active): at every recorded change, the
latest price of each side is combined into the de-vigged probability of fixture participant 1
(p1 = (1/o1) / (1/o1 + 1/o2)); ``active`` is False while either side is suspended (line pulled).
"""
from __future__ import annotations

import bisect
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "cache" / "hist"
MARKET, OUT1, OUT2 = "611", "611", "612"


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


@dataclass
class Series:
    t: list[datetime]
    p1: list[float]
    active: list[bool]

    def __len__(self) -> int:
        return len(self.t)

    def at(self, when: datetime) -> tuple[float, bool, datetime] | None:
        """(p1, active, time of that record) for the latest record at or before ``when``."""
        i = bisect.bisect_right(self.t, when) - 1
        return None if i < 0 else (self.p1[i], self.active[i], self.t[i])

    def first_change_after(self, when: datetime, min_move: float = 1e-9) -> datetime | None:
        """First record after ``when`` whose price differs from the price standing at ``when``
        (or the first active record if none stood). Suspensions alone are not price changes."""
        base = self.at(when)
        i = bisect.bisect_right(self.t, when)
        for j in range(i, len(self.t)):
            if not self.active[j]:
                continue
            if base is None or not base[1] or abs(self.p1[j] - base[0]) > min_move:
                return self.t[j]
        return None

    def next_active_after(self, when: datetime) -> datetime | None:
        i = bisect.bisect_right(self.t, when)
        for j in range(i, len(self.t)):
            if self.active[j]:
                return self.t[j]
        return None

    def gaps_minutes(self, until: datetime) -> list[float]:
        ts = [x for x in self.t if x < until]
        return [(b - a).total_seconds() / 60 for a, b in zip(ts, ts[1:], strict=False)]


def load(fixture_id: str) -> dict | None:
    fp = CACHE / f"op_hist_{fixture_id}.json"
    if not fp.exists():
        return None
    d = json.loads(fp.read_text())
    return None if "error" in d else d


def series(hist: dict, p1_is_team1: bool = True, book: str = "pinnacle") -> Series | None:
    """Step series of the de-vigged probability of vlr team 1."""
    try:
        oc = hist["bookmakers"][book]["markets"][MARKET]["outcomes"]
        a, b = oc[OUT1]["players"]["0"], oc[OUT2]["players"]["0"]
    except (KeyError, TypeError):
        return None
    ev = sorted([(_t(r["createdAt"]), 0, r) for r in a] + [(_t(r["createdAt"]), 1, r) for r in b],
                key=lambda x: (x[0], x[1]))
    last: list[dict | None] = [None, None]
    T, P, A = [], [], []
    for when, side, r in ev:
        last[side] = r
        if last[0] is None or last[1] is None:
            continue
        o1, o2 = float(last[0]["price"]), float(last[1]["price"])
        if o1 <= 1.0 or o2 <= 1.0:
            continue
        p = (1 / o1) / (1 / o1 + 1 / o2)
        act = bool(last[0]["active"]) and bool(last[1]["active"])
        if T and T[-1] == when:
            P[-1], A[-1] = (p if p1_is_team1 else 1 - p), act
            continue
        T.append(when)
        P.append(p if p1_is_team1 else 1 - p)
        A.append(act)
    return Series(T, P, A) if T else None
