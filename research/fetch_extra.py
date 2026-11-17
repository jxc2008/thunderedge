"""Approved extra scope: VCT 2023 (churn baseline for 2024) + Esports World Cup 2024-2026.

Discovers events (vlr /vct-2023 hub; EWC via vlr event search), writes cache/extra_matches.json,
then fetches match pages through the cached, throttled, budgeted vlr_fetch.get.
Usage: python -m research.fetch_extra [--list-only]
"""
from __future__ import annotations

import json
import re
import sys

from bs4 import BeautifulSoup

from research import vlr_fetch as v

EV = re.compile(r"^/event/(\d+)/([^/?#]+)")


def events_2023() -> list[str]:
    s = BeautifulSoup(v.get("/vct-2023"), "lxml")
    evs = sorted({EV.match(a["href"])[0] for a in s.find_all("a", href=EV)})
    # 2023 international + franchised leagues (LOCK//IN, leagues, Masters Tokyo, LCQs, Champions)
    keep = [e for e in evs if "2023" in e or "lock-in" in e]
    return keep


def events_ewc() -> list[str]:
    s = BeautifulSoup(v.get("/search/?q=esports+world+cup&type=events"), "lxml")
    evs = sorted({EV.match(a["href"])[0] for a in s.find_all("a", href=EV)})
    return [e for e in evs if "esports-world-cup" in e and re.search(r"202[456]", e)
            and "qualifier" not in e]


def main() -> None:
    e23, ewc = events_2023(), events_ewc()
    print("2023 events:", len(e23), *e23, sep="\n  ")
    print("EWC events:", len(ewc), *ewc, sep="\n  ")
    out = {}
    for e in e23 + ewc:
        eid = EV.match(e)[1]
        s = BeautifulSoup(v.get(f"/event/matches/{eid}/?series_id=all"), "lxml")
        out[e] = sorted({a["href"] for a in s.select("a.match-item")})
    n = sum(len(x) for x in out.values())
    todo = [m for ms in out.values() for m in ms if not v.cached(m)]
    print(f"{n} match pages listed, {len(todo)} uncached; ledger used {v.live_requests_used()}")
    (v.ROOT / "cache" / "extra_matches.json").write_text(json.dumps(out, indent=1))
    if "--list-only" in sys.argv:
        return
    if v.live_requests_used() + len(todo) > 2000:
        print("STOP: would exceed the approved ~2,000-page vlr budget; ask before continuing")
        sys.exit(2)
    for i, m in enumerate(todo):
        v.get(m)
        if i % 50 == 0:
            print(i, v.live_requests_used(), flush=True)
    print("done; used", v.live_requests_used())


if __name__ == "__main__":
    main()
