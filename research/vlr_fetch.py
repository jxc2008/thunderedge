"""Polite, cached vlr.gg fetcher for research scripts.

- >= MIN_INTERVAL seconds between live requests (default 2.5s + jitter)
- Every response cached to research/cache/vlr/ (gitignored); cache hits cost nothing
- Every live request appended to research/cache/request_ledger.csv so the
  page budget is auditable (`python -m research.vlr_fetch --budget`)
- Hard budget guard: raises once live requests in the ledger exceed BUDGET
  unless the caller raises the budget explicitly.
"""
from __future__ import annotations

import csv
import hashlib
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://www.vlr.gg"
ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache" / "vlr"
LEDGER = ROOT / "cache" / "request_ledger.csv"
MIN_INTERVAL = 2.5
BUDGET = int(os.environ.get("VLR_PAGE_BUDGET", "2000"))
UA = "Mozilla/5.0 (compatible; research-scraper; low-rate, cached)"
DISALLOWED = ("/search/auto", "/rr/")

_last = 0.0
_session = requests.Session()
_session.headers["User-Agent"] = UA


class BudgetExceeded(RuntimeError):
    pass


def _key(path: str) -> Path:
    h = hashlib.sha1(path.encode()).hexdigest()[:16]
    slug = "".join(c if c.isalnum() else "_" for c in path)[:80]
    return CACHE / f"{slug}__{h}.html"


def live_requests_used() -> int:
    if not LEDGER.exists():
        return 0
    with LEDGER.open() as f:
        return max(0, sum(1 for _ in f) - 1)


def cached(path: str) -> bool:
    return _key(path).exists()


def get(path: str, *, refresh: bool = False, budget: int | None = None) -> str:
    """Return HTML for a vlr.gg path (e.g. '/event/matches/2682/?series_id=all')."""
    global _last
    if path.startswith(BASE):
        path = path[len(BASE):]
    if not path.startswith("/") or ":" in path.split("?")[0]:
        raise ValueError(f"not a vlr.gg path: {path!r}")
    if any(path.startswith(d) for d in DISALLOWED):
        raise ValueError(f"robots.txt disallows {path}")
    fp = _key(path)
    if fp.exists() and not refresh:
        return fp.read_text(encoding="utf-8")
    limit = BUDGET if budget is None else budget
    used = live_requests_used()
    if used >= limit:
        raise BudgetExceeded(f"{used} live requests used; budget {limit}")
    wait = MIN_INTERVAL + random.uniform(0, 1.0) - (time.monotonic() - _last)
    if wait > 0:
        time.sleep(wait)
    for attempt in range(4):
        r = _session.get(BASE + path, timeout=30)
        _last = time.monotonic()
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(30 * (attempt + 1))
            continue
        break
    r.raise_for_status()
    CACHE.mkdir(parents=True, exist_ok=True)
    fp.write_text(r.text, encoding="utf-8")
    new = not LEDGER.exists()
    with LEDGER.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["utc", "path", "status", "bytes"])
        w.writerow([datetime.now(timezone.utc).isoformat(), path, r.status_code, len(r.content)])
    return r.text


if __name__ == "__main__":
    if "--budget" in sys.argv:
        print(f"live requests used: {live_requests_used()} / {BUDGET}")
