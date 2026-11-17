"""Tier-2 (VCL / Challengers) scrape, 2025-26 only — approved 2026-11-17 (~5,400 pages).

Rate: one request every 3 s + 0-1 s jitter (~0.29 req/s). The odds logger runs alongside at
~4 requests / 15 min off-season, so the combined rate stays <= ~0.3 req/s.
robots.txt (checked 2026-11-17): no crawl-delay; /search/auto and /rr/ disallowed (enforced in
vlr_fetch). Resumable: every page is cached, so a rerun only fetches what is missing.
Stops (exit 2, writes research/cache/tier2_STOP) on HTTP 403/429, a Cloudflare challenge page,
3 consecutive errors, or if the page count would exceed the approved ceiling.

Usage:
  python -m research.fetch_tier2 lists    # 134 event match lists -> cache/tier2_matches.json + count
  python -m research.fetch_tier2 matches  # completed match pages
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from research import vlr_fetch as v

ROOT = Path(__file__).resolve().parent
EVENTS = ROOT / "cache" / "t2_events_all.json"
OUT = ROOT / "cache" / "tier2_matches.json"
STOP = ROOT / "cache" / "tier2_STOP"
YEARS = (2025, 2026)
LEDGER_AT_APPROVAL = 2052
APPROVED = 5400          # "~5,400" approved (lists + match pages); above -> stop and report
# 2025-26 has 6,476 completed match pages (> approval). Open/qualifier events (20 events, 1,510 pages,
# mostly semi-pro sides) are deferred until the user decides; league stages + finals + other = 4,966.
DEFER = ("qualifier", "open")
v.MIN_INTERVAL = 3.0     # + vlr_fetch's 0-1 s jitter
CHALLENGE = ("Just a moment...", "cf-chl", "challenge-platform", "Attention Required!")


def stop(reason: str) -> None:
    STOP.write_text(reason, encoding="utf-8")
    print("STOP:", reason, flush=True)
    sys.exit(2)


def fetch(path: str) -> str:
    try:
        html = v.get(path, budget=LEDGER_AT_APPROVAL + APPROVED)
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else None
        if code in (403, 429):
            stop(f"HTTP {code} on {path}")
        raise
    except v.BudgetExceeded as e:
        stop(f"budget: {e}")
    if any(c in html[:5000] for c in CHALLENGE):
        v._key(path).unlink(missing_ok=True)  # do not cache a challenge page
        stop(f"Cloudflare challenge on {path}")
    return html


def lists() -> None:
    evs = json.loads(EVENTS.read_text())["events"]
    todo = sorted(int(k) for k, e in evs.items() if e["year"] in YEARS)
    out: dict = json.loads(OUT.read_text()) if OUT.exists() else {}
    for eid in todo:
        if str(eid) in out:
            continue
        s = BeautifulSoup(fetch(f"/event/matches/{eid}/?series_id=all"), "lxml")
        done, upcoming = [], 0
        for a in s.select("a.match-item"):
            st = a.select_one(".ml-status")
            status = st.get_text(strip=True).lower() if st else ""
            if status in ("upcoming", "live", "tbd"):
                upcoming += 1
            else:
                done.append(a["href"])
        out[str(eid)] = {"slug": evs[str(eid)]["href"], "year": evs[str(eid)]["year"], "matches": sorted(set(done)),
                         "not_completed": upcoming}
        OUT.write_text(json.dumps(out, indent=0))
    n = sum(len(x["matches"]) for x in out.values())
    todo_pages = sum(1 for x in out.values() for m in x["matches"] if not v.cached(m))
    print(f"events {len(out)}; completed match pages {n} ({todo_pages} not cached); ledger {v.live_requests_used()}")
    if v.live_requests_used() + todo_pages > LEDGER_AT_APPROVAL + APPROVED:
        stop(f"match pages ({todo_pages}) would exceed the approved ceiling; ask before continuing")


def matches() -> None:
    if STOP.exists():
        print("STOP file present:", STOP.read_text())
        sys.exit(2)
    out = json.loads(OUT.read_text())
    titles = {k: e["title"].lower() for k, e in json.loads(EVENTS.read_text())["events"].items()}
    keep = {k: x for k, x in out.items() if not any(d in titles[k] for d in DEFER)}
    todo = [m for x in keep.values() for m in x["matches"] if not v.cached(m)]
    if v.live_requests_used() + len(todo) > LEDGER_AT_APPROVAL + APPROVED:
        stop(f"{len(todo)} pages would exceed the approved ceiling")
    print(f"{len(keep)} events kept, {len(out) - len(keep)} deferred; {len(todo)} pages to fetch", flush=True)
    errs = 0
    for i, m in enumerate(todo):
        try:
            fetch(m)
            errs = 0
        except Exception as e:  # noqa: BLE001
            errs += 1
            print(f"error {errs} on {m}: {e}", flush=True)
            if errs >= 3:
                stop(f"3 consecutive errors, last: {e}")
        if i % 100 == 0:
            print(f"{i}/{len(todo)} ledger {v.live_requests_used()}", flush=True)
    print(f"done; ledger {v.live_requests_used()}")


if __name__ == "__main__":
    {"lists": lists, "matches": matches}[sys.argv[1]]()
