"""Two-sided pre-match odds from Wayback Machine snapshots of vlr.gg match pages.

Phase A (index): one CDX prefix query per 4-digit match-id prefix -> cache/wayback/cdx_<p>.json
Phase B (snapshots): for each tier-1 match (from tier1_matches.json + extra_matches.json) whose
  parsed start time is known, download the LAST capture taken within WINDOW_H hours before
  start, using the raw `id_` endpoint -> cache/wayback/snap_<match_id>_<ts>.html
Output: cache/wayback/prematch_odds.json  {match_id: {snapshot_ts, hours_before, rows:[...]}}

archive.org only; >= MIN_INTERVAL s between requests; exponential back-off on refusals.
Ledger: cache/wayback_ledger.csv. Usage: python -m research.wayback_fetch [--index-only]
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from research import vlr_fetch as v
from research.build_db import _parse_one
from research.odds_logger import parse_match_odds

ROOT = Path(__file__).resolve().parent
WB = ROOT / "cache" / "wayback"
LEDGER = ROOT / "cache" / "wayback_ledger.csv"
CDX = "https://web.archive.org/cdx/search/cdx"
MIN_INTERVAL = 4.0
WINDOW_H = 48
UA = "Mozilla/5.0 (compatible; research; low-rate)"
_last = 0.0
_s = requests.Session()
_s.headers["User-Agent"] = UA


def _get(endpoint: str, params: dict | None = None) -> requests.Response:
    global _last
    delay = 60
    for attempt in range(6):
        wait = MIN_INTERVAL - (time.monotonic() - _last)
        if wait > 0:
            time.sleep(wait)
        try:
            r = _s.get(endpoint, params=params, timeout=90)
            _last = time.monotonic()
            with LEDGER.open("a", newline="") as f:
                csv.writer(f).writerow([datetime.now(timezone.utc).isoformat(), r.url[:300], r.status_code])
            if r.status_code in (429, 503) or r.status_code >= 520:
                raise requests.ConnectionError(f"HTTP {r.status_code}")
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            _last = time.monotonic()
            print(f"  backoff {delay}s ({e.__class__.__name__}: {str(e)[:80]})", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 900)
    raise RuntimeError(f"giving up on {endpoint}")


def match_lists() -> list[str]:
    out = []
    for f in ("tier1_matches.json", "extra_matches.json"):
        fp = ROOT / "cache" / f
        if fp.exists():
            out += [m for ms in json.loads(fp.read_text()).values() for m in ms]
    return out


def phase_index(ids: list[str]) -> dict[str, list[str]]:
    """match_id -> sorted list of 200-status capture timestamps."""
    WB.mkdir(parents=True, exist_ok=True)
    prefixes = sorted({i[:4] for i in ids})
    want = set(ids)
    caps: dict[str, list[str]] = {}
    for n, p in enumerate(prefixes):
        fp = WB / f"cdx_{p}.json"
        if not fp.exists():
            r = _get(CDX, {"url": f"vlr.gg/{p}", "matchType": "prefix", "output": "json",
                          "fl": "timestamp,original", "filter": "statuscode:200"})
            rows = r.json() if r.text.strip() else []
            fp.write_text(json.dumps(rows[1:] if rows else []))
            print(f"[{n + 1}/{len(prefixes)}] cdx {p}: {max(0, len(rows) - 1)} captures", flush=True)
        for ts, orig in json.loads(fp.read_text()):
            path = orig.split("vlr.gg", 1)[-1]
            mid = path.strip("/").split("/")[0]
            if mid in want and "?" not in path and "/tab" not in path:
                caps.setdefault(mid, []).append(ts)
    return {k: sorted(set(vs)) for k, vs in caps.items()}


def phase_snapshots(urls: list[str], caps: dict[str, list[str]]) -> dict:
    out_fp = WB / "prematch_odds.json"
    out = json.loads(out_fp.read_text()) if out_fp.exists() else {}
    todo = []
    for u in urls:
        mid = u.strip("/").split("/")[0]
        if mid in out or mid not in caps:
            continue
        d = _parse_one(u)
        if not d or not d.get("date_utc"):
            continue
        start = datetime.strptime(d["date_utc"], "%Y-%m-%d %H:%M:%S")
        pre = [t for t in caps[mid] if 0 < (start - datetime.strptime(t, "%Y%m%d%H%M%S")).total_seconds()
               <= WINDOW_H * 3600]
        if pre:
            todo.append((u, mid, max(pre), start))
    print(f"{len(todo)} snapshots to fetch", flush=True)
    for n, (u, mid, ts, start) in enumerate(todo):
        fp = WB / f"snap_{mid}_{ts}.html"
        if not fp.exists():
            r = _get(f"https://web.archive.org/web/{ts}id_/https://www.vlr.gg{u}")
            fp.write_text(r.text, encoding="utf-8")
        _, rows = parse_match_odds(fp.read_text(encoding="utf-8"))
        hrs = (start - datetime.strptime(ts, "%Y%m%d%H%M%S")).total_seconds() / 3600
        out[mid] = {"match_url": u, "snapshot_ts": ts, "hours_before": round(hrs, 2),
                    "rows": [{k: r[k] for k in ("team", "book", "odds", "status")} for r in rows]}
        if n % 25 == 0:
            out_fp.write_text(json.dumps(out))
            print(f"  {n}/{len(todo)}", flush=True)
    out_fp.write_text(json.dumps(out))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index-only", action="store_true")
    a = ap.parse_args()
    urls = match_lists()
    ids = [u.strip("/").split("/")[0] for u in urls]
    caps = phase_index(ids)
    print(f"index: {len(caps)}/{len(ids)} matches have >=1 capture", flush=True)
    if a.index_only:
        return
    out = phase_snapshots([u for u in urls if v.cached(u)], caps)
    two = sum(1 for o in out.values()
              if sum(1 for r in o["rows"] if r["book"] == "thunderpick" and r["status"] == "pre") == 2)
    print(f"snapshots parsed: {len(out)}; two-sided thunderpick: {two}")


if __name__ == "__main__":
    main()
