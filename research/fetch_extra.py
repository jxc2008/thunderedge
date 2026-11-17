"""Approved extra scope: VCT 2023 (churn baseline for 2024) + Esports World Cup main events.

Discovers events (vlr /vct-2023 hub; EWC via vlr event search), writes cache/extra_matches.json,
then fetches match pages through the cached, throttled, budgeted vlr_fetch.get.
EWC event pages bundle the regional qualifiers (tier-2 sides, not in the approved scope), so only
matches dated inside the main-event window shown in the search result are kept. There was no
VALORANT at EWC 2024; the main events are 2025 (/event/2449) and 2026 (/event/2952).
Usage: python -m research.fetch_extra [--list-only]
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime

from bs4 import BeautifulSoup

from research import vlr_fetch as v

EV = re.compile(r"^/event/(\d+)/([^/?#]+)")
BUDGET = 2020  # approved scopes (tier-1 2024-26 + VCT 2023 + EWC main events) total 2,017


def events_2023() -> list[str]:
    s = BeautifulSoup(v.get("/vct-2023"), "lxml")
    evs = sorted({EV.match(a["href"])[0] for a in s.find_all("a", href=EV)})
    # 2023 international + franchised leagues (LOCK//IN, leagues, Masters Tokyo, LCQs, Champions)
    return [e for e in evs if "2023" in e or "lock-in" in e]


def events_ewc() -> list[tuple[str, tuple[str, str]]]:
    """(event path, (start, end)) for EWC main events. Search results link via
    "/search/r/event/<id>/idx" redirects; the title carries name and date range."""
    s = BeautifulSoup(v.get("/search/?q=esports+world+cup&type=events"), "lxml")
    out = []
    for a in s.select("a.wf-module-item"):
        m = re.match(r"^/search/r/event/(\d+)/", a.get("href", ""))
        title = a.get_text(" ", strip=True)
        y = re.match(r"^Esports World Cup (202[4-6])\b(?!:)", title)  # main event, not qualifiers
        dates = re.findall(r"([A-Z][a-z]{2} \d{1,2}, \d{4})", title)
        if m and y and len(dates) >= 2:
            win = tuple(datetime.strptime(x, "%b %d, %Y").strftime("%Y-%m-%d") for x in dates[:2])
            out.append((f"/event/{m[1]}/esports-world-cup-{y[1]}", win))
    return sorted(out)


def main_event_only(eid: str, win: tuple[str, str]) -> list[str]:
    s = BeautifulSoup(v.get(f"/event/matches/{eid}/?series_id=all"), "lxml")
    cur, ms = None, []
    for el in s.select(".wf-label.mod-large, a.match-item"):
        if "wf-label" in el.get("class", []):
            t = " ".join(el.get_text(" ", strip=True).split()).replace("Today", "").strip()
            try:
                cur = datetime.strptime(t.split(" ", 1)[1].strip(), "%B %d, %Y").strftime("%Y-%m-%d")
            except (IndexError, ValueError):
                cur = None
        elif cur and win[0] <= cur <= win[1]:
            ms.append(el["href"])
    return sorted(set(ms))


def main() -> None:
    e23, ewc = events_2023(), events_ewc()
    print("2023 events:", len(e23), *e23, sep="\n  ")
    print("EWC main events:", len(ewc), *[f"{e} {w}" for e, w in ewc], sep="\n  ")
    out = {}
    for e in e23:
        s = BeautifulSoup(v.get(f"/event/matches/{EV.match(e)[1]}/?series_id=all"), "lxml")
        out[e] = sorted({a["href"] for a in s.select("a.match-item")})
    for e, win in ewc:
        out[e] = main_event_only(EV.match(e)[1], win)
    n = sum(len(x) for x in out.values())
    todo = [m for ms in out.values() for m in ms if not v.cached(m)]
    print(f"{n} match pages listed, {len(todo)} uncached; ledger used {v.live_requests_used()}")
    (v.ROOT / "cache" / "extra_matches.json").write_text(json.dumps(out, indent=1))
    if "--list-only" in sys.argv:
        return
    if v.live_requests_used() + len(todo) > BUDGET:
        print(f"STOP: would exceed the approved {BUDGET}-page vlr budget; ask before continuing")
        sys.exit(2)
    for i, m in enumerate(todo):
        v.get(m, budget=BUDGET)
        if i % 50 == 0:
            print(i, v.live_requests_used(), flush=True)
    print("done; used", v.live_requests_used())


if __name__ == "__main__":
    main()
