"""Timestamped pre-match odds logger: vlr.gg (Thunderpick + other books) and Kalshi.

One invocation = one poll. Schedule every 15 min (see research/odds_logger_task.cmd).
Writes to data/odds_snapshots.db (gitignored):

  odds_snapshots(ts_utc, source, match_key, match_url, event, start_utc, team, book,
                 odds_decimal, yes_bid, yes_ask, yes_bid_size, yes_ask_size, last_price,
                 volume, status, raw)
  poll_log(ts_utc, vlr_requests, kalshi_requests, n_matches, n_rows, errors)
  stream_events(id, show, start_utc, end_utc, url, notes)     -- Plat Chat etc., manual entry
  match_status(match_key, url, event, team1, team2, status, first_seen, last_seen, completed_ts)

Post-result trigger (stale-line study, PREREG_KICKOFF2027.md §10): a match seen as "live" that
has left the /matches list is marked completed; in the same poll every upcoming match of either
team is fetched regardless of cadence and its rows carry trigger='post_result' and
ref_match=<completed match_key>. Detection latency is at most one poll (15 min).

Load control (vlr): the /matches list is fetched every poll; an individual match page
is fetched every poll only when the match starts within NEAR_HOURS, otherwise at most
once per FAR_EVERY_MIN. Live requests are >= 2.5 s apart. Pages are not cached (we
need fresh prices). The raw odds widget HTML is stored so parsing can be redone.

CLI:
  python -m research.odds_logger                    # one poll
  python -m research.odds_logger --all-tiers        # include non-VCT matches
  python -m research.odds_logger --add-stream "Plat Chat" 2027-01-15T19:00Z [--end ...] [--url ...]
  python -m research.odds_logger --list-streams
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from research.timeutil import vlr_to_utc

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "odds_snapshots.db"
VLR = "https://www.vlr.gg"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_SERIES = ["KXVALORANTGAME", "KXVALORANTMAP"]
NEAR_HOURS = 48
FAR_EVERY_MIN = 120
HORIZON_DAYS = 7
MAX_LIST_PAGES = 3
MIN_INTERVAL = 2.5
UA = "Mozilla/5.0 (compatible; odds-snapshot-logger; 15-min cadence)"
TIER1 = re.compile(r"\bVCT\b|Champions Tour|Masters|VALORANT Champions|Esports World Cup", re.I)
OLD_POST = re.compile(r"\$100 on (.+?) returned \$[\d.,]+ at ([\d.]+) pre-match odds")

SCHEMA = """
CREATE TABLE IF NOT EXISTS odds_snapshots(
  ts_utc TEXT NOT NULL, source TEXT NOT NULL, match_key TEXT NOT NULL, match_url TEXT,
  event TEXT, start_utc TEXT, team TEXT, book TEXT, odds_decimal REAL,
  yes_bid REAL, yes_ask REAL, yes_bid_size REAL, yes_ask_size REAL, last_price REAL,
  volume REAL, status TEXT, raw TEXT);
CREATE INDEX IF NOT EXISTS ix_snap_key ON odds_snapshots(match_key, ts_utc);
CREATE TABLE IF NOT EXISTS match_status(match_key TEXT PRIMARY KEY, url TEXT, event TEXT,
  team1 TEXT, team2 TEXT, status TEXT, first_seen TEXT, last_seen TEXT, completed_ts TEXT);
CREATE TABLE IF NOT EXISTS poll_log(ts_utc TEXT, vlr_requests INTEGER, kalshi_requests INTEGER,
  n_matches INTEGER, n_rows INTEGER, errors TEXT);
CREATE TABLE IF NOT EXISTS stream_events(id INTEGER PRIMARY KEY AUTOINCREMENT, show TEXT NOT NULL,
  start_utc TEXT NOT NULL, end_utc TEXT, url TEXT, notes TEXT);
"""


class Fetcher:
    def __init__(self) -> None:
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.last = 0.0
        self.n = 0

    def get(self, url: str, **kw) -> requests.Response:
        wait = MIN_INTERVAL + random.uniform(0, 0.8) - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        r = self.s.get(url, timeout=30, **kw)
        self.last = time.monotonic()
        self.n += 1
        r.raise_for_status()
        return r


def _num(s: str | None) -> float | None:
    try:
        return float(str(s).strip())
    except (TypeError, ValueError):
        return None


def parse_upcoming(html: str, all_tiers: bool) -> list[dict]:
    s = BeautifulSoup(html, "lxml")
    out = []
    for a in s.select("a.match-item"):
        ev = a.select_one(".match-item-event")
        ev_txt = re.sub(r"\s+", " ", ev.get_text(" ", strip=True)) if ev else ""
        status = a.select_one(".ml-status")
        st = status.get_text(strip=True).lower() if status else ""
        if st not in ("upcoming", "live"):
            continue
        if not all_tiers and not TIER1.search(ev_txt):
            continue
        names = [x.get_text(" ", strip=True) for x in a.select(".match-item-vs-team-name .text-of")]
        out.append({"url": a["href"], "event": ev_txt[:200], "status": st,
                    "teams": [n for n in names if n][:2]})
    return out


def parse_match_odds(html: str) -> tuple[str | None, list[dict]]:
    """Return (start_utc, odds rows). Handles pre-match two-sided and post-match widgets."""
    s = BeautifulSoup(html, "lxml")
    ts = s.select_one(".match-header-date .moment-tz-convert[data-utc-ts]")
    start = ts["data-utc-ts"] if ts else None
    names = [x.get_text(" ", strip=True) for x in s.select(".match-header-vs .wf-title-med")]
    rows = []
    for b in s.select("a.match-bet-item"):
        cls = b.get("class", [])
        img = b.select_one("img")
        book = None
        if img is not None:
            mods = [c[4:] for c in img.get("class", []) if c.startswith("mod-")]
            book = mods[0] if mods else img.get("src", "").rsplit("/", 1)[-1].split(".")[0]
        raw = str(b)[:4000]
        if "mod-noodds" in cls:
            rows.append({"team": None, "book": book, "odds": None, "status": "pending", "raw": raw})
            continue
        found = False
        for half, idx in ((".match-bet-item-half.mod-1", 0), (".match-bet-item-half.mod-2", 1)):
            h = b.select_one(half)
            if h is None:
                continue
            o = h.select_one(".match-bet-item-odds")
            team_el = (h.select_one(".match-bet-item-team-name")
                       or h.select_one(".match-bet-item-team, .match-bet-item-teamzzz"))
            val = _num(o.get_text(strip=True)) if o else None
            if val is None:
                continue
            team = team_el.get_text(" ", strip=True) if team_el else (names[idx] if idx < len(names) else None)
            rows.append({"team": team, "book": book, "odds": val, "status": "pre", "raw": raw})
            found = True
        if not found:
            # older layout (archived 2023-25 pages): plain halves, odds spans carry mod-1 / mod-2
            for idx, mod in ((0, "mod-1"), (1, "mod-2")):
                o = b.select_one(f".match-bet-item-odds.{mod}")
                val = _num(o.get_text(strip=True)) if o else None
                if val is None:
                    continue
                t = o.find_parent(class_="match-bet-item-half")
                team_el = t.select_one(".match-bet-item-team") if t else None
                team = team_el.get_text(" ", strip=True) if team_el else (names[idx] if idx < len(names) else None)
                rows.append({"team": team, "book": book, "odds": val, "status": "pre", "raw": raw})
                found = True
        if not found:
            txt = " ".join(b.get_text(" ", strip=True).split())
            m = OLD_POST.search(txt)
            if m:
                rows.append({"team": m[1], "book": book, "odds": _num(m[2]), "status": "post", "raw": raw})
                continue
            if txt.endswith("Pending"):
                rows.append({"team": None, "book": book, "odds": None, "status": "pending", "raw": raw})
                continue
            short = b.select_one(".match-bet-item-return-short .match-bet-item-odds")
            tm = b.select_one(".match-bet-item-return-msg .match-bet-item-teamzzz")
            rows.append({"team": tm.get_text(" ", strip=True) if tm else None, "book": book,
                         "odds": _num(short.get_text(strip=True)) if short else None,
                         "status": "post" if "mod-post-odds" in cls else "unparsed", "raw": raw})
    return start, rows


def poll(all_tiers: bool = False) -> dict:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=30)
    con.executescript(SCHEMA)
    now = datetime.now(timezone.utc)
    ts = now.isoformat(timespec="seconds")
    f = Fetcher()
    errors: list[str] = []
    rows: list[tuple] = []
    n_matches = 0

    # --- vlr.gg
    ups: list[dict] = []
    for page in range(1, MAX_LIST_PAGES + 1):
        try:
            html = f.get(VLR + "/matches" + (f"/?page={page}" if page > 1 else "")).text
        except Exception as e:  # noqa: BLE001
            errors.append(f"vlr list p{page}: {e}")
            break
        ups += parse_upcoming(html, all_tiers)
        if f"page={page + 1}" not in html:
            break
    # --- results detection: previously live, now gone from the list -> completed
    for c in ("trigger", "ref_match"):
        if c not in [r[1] for r in con.execute("PRAGMA table_info(odds_snapshots)")]:
            con.execute(f"ALTER TABLE odds_snapshots ADD COLUMN {c} TEXT")
    cur = {"vlr:" + m["url"].strip("/").split("/")[0]: m for m in ups}
    completed: dict[str, set[str]] = {}
    if not errors:  # only list-page errors exist at this point; a failed list must not "complete" matches
        for key, st, t1, t2 in con.execute(
                "SELECT match_key, status, team1, team2 FROM match_status WHERE completed_ts IS NULL").fetchall():
            if st == "live" and key not in cur:
                con.execute("UPDATE match_status SET completed_ts=? WHERE match_key=?", (ts, key))
                completed[key] = {x.lower() for x in (t1, t2) if x}
    for key, m in cur.items():
        t = m["teams"] + [None, None]
        con.execute("""INSERT INTO match_status(match_key,url,event,team1,team2,status,first_seen,last_seen)
                       VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(match_key) DO UPDATE SET
                       status=excluded.status, last_seen=excluded.last_seen""",
                    (key, m["url"], m["event"], t[0], t[1], m["status"], ts, ts))
    trigger_for: dict[str, str] = {}
    for done_key, teams in completed.items():
        for key, m in cur.items():
            if m["status"] == "upcoming" and teams & {x.lower() for x in m["teams"]}:
                trigger_for.setdefault(key, done_key)

    for m in ups:
        key = "vlr:" + m["url"].strip("/").split("/")[0]
        forced = key in trigger_for
        prev = con.execute("SELECT max(ts_utc), max(start_utc) FROM odds_snapshots WHERE match_key=?",
                           (key,)).fetchone()
        start_known = prev[1]
        if start_known and prev[0] and not forced:
            try:
                st = vlr_to_utc(start_known)  # vlr data-utc-ts is ET wall-clock
                last = datetime.fromisoformat(prev[0])
                if st - now > timedelta(days=HORIZON_DAYS):
                    continue
                if st - now > timedelta(hours=NEAR_HOURS) and now - last < timedelta(minutes=FAR_EVERY_MIN):
                    continue
            except ValueError:
                pass
        try:
            start, odds = parse_match_odds(f.get(VLR + m["url"]).text)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{m['url']}: {e}")
            continue
        n_matches += 1
        if not odds:
            odds = [{"team": None, "book": None, "odds": None, "status": "no_widget", "raw": None}]
        for o in odds:
            rows.append((ts, "vlr", key, m["url"], m["event"], start, o["team"], o["book"], o["odds"],
                         None, None, None, None, None, None, o["status"], o["raw"],
                         "post_result" if forced else None, trigger_for.get(key)))

    # --- Kalshi (public market data, no auth)
    k_req = 0
    for series in KALSHI_SERIES:
        cursor = None
        while True:
            params = {"series_ticker": series, "status": "open", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            try:
                r = requests.get(KALSHI + "/markets", params=params, timeout=30,
                                 headers={"User-Agent": UA})
                k_req += 1
                r.raise_for_status()
                d = r.json()
            except Exception as e:  # noqa: BLE001
                errors.append(f"kalshi {series}: {e}")
                break
            for mk in d.get("markets", []):
                n_matches += 1
                rows.append((ts, "kalshi", "kalshi:" + mk["event_ticker"], mk["ticker"], series,
                             mk.get("occurrence_datetime") or mk.get("expected_expiration_time"),
                             mk.get("yes_sub_title"), "kalshi", None,
                             _num(mk.get("yes_bid_dollars")), _num(mk.get("yes_ask_dollars")),
                             _num(mk.get("yes_bid_size_fp")), _num(mk.get("yes_ask_size_fp")),
                             _num(mk.get("last_price_dollars")), _num(mk.get("volume_fp")),
                             mk.get("status"), json.dumps({k: mk.get(k) for k in (
                                 "title", "no_sub_title", "open_interest_fp", "close_time")}), None, None))
            cursor = d.get("cursor")
            if not cursor:
                break

    con.executemany(f"INSERT INTO odds_snapshots VALUES ({','.join('?' * 19)})", rows)
    con.execute("INSERT INTO poll_log VALUES (?,?,?,?,?,?)",
                (ts, f.n, k_req, n_matches, len(rows), json.dumps(errors) if errors else None))
    con.commit()
    con.close()
    return {"ts": ts, "vlr_requests": f.n, "kalshi_requests": k_req, "rows": len(rows),
            "errors": errors}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-tiers", action="store_true")
    ap.add_argument("--add-stream", nargs=2, metavar=("SHOW", "START_UTC"))
    ap.add_argument("--end")
    ap.add_argument("--url")
    ap.add_argument("--notes")
    ap.add_argument("--list-streams", action="store_true")
    a = ap.parse_args()
    if a.add_stream or a.list_streams:
        DB.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(DB)
        con.executescript(SCHEMA)
        if a.add_stream:
            show, start = a.add_stream
            datetime.fromisoformat(start.replace("Z", "+00:00"))  # validate
            con.execute("INSERT INTO stream_events(show,start_utc,end_utc,url,notes) VALUES (?,?,?,?,?)",
                        (show, start, a.end, a.url, a.notes))
            con.commit()
        for r in con.execute("SELECT * FROM stream_events ORDER BY start_utc"):
            print(r)
        return
    print(json.dumps(poll(a.all_tiers)))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 — pythonw has no console; persist the traceback
        import traceback
        DB.parent.mkdir(parents=True, exist_ok=True)
        with open(DB.parent / "odds_logger.err", "a", encoding="utf-8") as fh:
            fh.write("--- " + datetime.now(timezone.utc).isoformat() + "\n" + traceback.format_exc())
        raise
