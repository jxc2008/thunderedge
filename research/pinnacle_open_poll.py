"""Windowed Pinnacle-open poll: catch Pinnacle's opening price for scheduled tier-1 matches and snapshot
Thunderpick (vlr match page) and the Kalshi order books at that moment. Design and cost: REPORT_v5 §4,
research/poll_design.py (simulated on the 2026 schedule).

Runs after each odds-logger poll (research/odds_logger_task.cmd); does nothing unless
research/pinnacle_open.json has "enabled": true. Per run:
  1. pending = upcoming tier-1 matches (logger match_status 'upcoming', start known, event not a
     qualifier / open / Ascension / Challengers / Game Changers stage) with
     start - window_early_h <= now < start - window_late_h whose Pinnacle open has not been caught;
     none -> no request, no cost;
  2. not due (last poll < cadence_h ago) -> nothing;
  3. fixture discovery (billable /v4/fixtures), only when a pending match has no mapped fixture, at
     most once per 24 h; mapped by team names and time (hist_fetch.map_fixtures);
  4. one billable /v4/odds-by-tournaments?bookmaker=pinnacle call covering every mapped fixture;
  5. each pending fixture with a two-sided Pinnacle price is "caught": stored in pinnacle_open, its vlr
     page fetched (rows trigger='pinnacle_open', ref_match=fixtureId), Kalshi books snapshotted
     (kalshi_books.trigger='pinnacle_open').
Billable calls go through hist_fetch.get under ledger host 'oddspapi_live' with a rolling 30-day cap
(hist_fetch.CAP_30D). The odds-by-tournaments layout is parsed defensively and is verified on the first
live response, which is saved to cache/hist/live_first_response.json.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "pinnacle_open.json"
STATE = ROOT / "cache" / "hist" / "pinnacle_open_state.json"
HOST = "oddspapi_live"
# the logger's VCT regex also matches "VCT 2027: ... Qualifier" events (tier 3, no Pinnacle market)
NOT_TIER1 = re.compile(r"qualifier|open|ascension|challengers|game changers|vcl", re.I)


def weekly_cost(interval_min: float) -> int:
    """Round-4 unwindowed design (REPORT_v4): one poll per interval all week + 7 discovery calls."""
    return int(7 * 24 * 60 / interval_min) + 7


def polls_per_30d_upper(cadence_h: float) -> int:
    """Upper bound if some match is always pending: one poll per cadence + one discovery a day."""
    return int(30 * 24 / cadence_h) + 30


def parse_pinnacle_prices(payload) -> dict[str, tuple[float, float]]:
    """fixtureId -> (price participant 1, price participant 2) for market 611 (match winner)."""
    out: dict[str, tuple[float, float]] = {}
    items = payload if isinstance(payload, list) else payload.get("data", []) if isinstance(payload, dict) else []
    for f in items:
        books = f.get("bookmakerOdds") or f.get("bookmakers") or {}
        pin = books.get("pinnacle") or {}
        oc = ((pin.get("markets") or {}).get("611") or {}).get("outcomes") or {}

        def price(o):
            x = oc.get(o) or {}
            pl = (x.get("players") or {}).get("0", x)
            if isinstance(pl, list):
                pl = pl[-1] if pl else {}
            return pl.get("price") if isinstance(pl, dict) and pl.get("active", True) else None

        p1, p2 = price("611"), price("612")
        if p1 and p2:
            out[str(f["fixtureId"])] = (float(p1), float(p2))
    return out


def pending_matches(con: sqlite3.Connection, now: datetime, early_h: float, late_h: float,
                    caught: set[str]) -> dict[str, tuple[str, str, datetime]]:
    from research.timeutil import vlr_to_utc  # noqa: PLC0415
    out = {}
    for key, team1, team2, event in con.execute(
            "SELECT match_key, team1, team2, event FROM match_status WHERE status='upcoming'"):
        if key in caught or NOT_TIER1.search(event or ""):
            continue
        r = con.execute("SELECT max(start_utc) FROM odds_snapshots WHERE match_key=? AND source='vlr'", (key,)).fetchone()
        if r and r[0]:
            try:
                t = vlr_to_utc(r[0])
            except ValueError:
                continue
            if t - timedelta(hours=early_h) <= now < t - timedelta(hours=late_h):
                out[key] = (team1, team2, t)
    return out


def run() -> None:
    cfg = json.loads(CONFIG.read_text())
    if not cfg.get("enabled"):
        return
    from research import hist_fetch as H, odds_logger as LG  # noqa: PLC0415
    now = datetime.now(timezone.utc)
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    st.setdefault("last_poll", None)
    st.setdefault("last_discovery", None)
    st.setdefault("fixtures", {})   # fixtureId -> {match_key, p1_is_team1, tournamentId}
    st.setdefault("caught", {})     # match_key -> ts
    con = sqlite3.connect(LG.DB, timeout=30)
    con.executescript(LG.SCHEMA)
    con.execute("""CREATE TABLE IF NOT EXISTS pinnacle_open(fixture_id TEXT PRIMARY KEY, match_key TEXT, first_seen TEXT,
                   price1 REAL, price2 REAL, p1_is_team1 INTEGER)""")
    pend = pending_matches(con, now, cfg["window_early_h"], cfg["window_late_h"], set(st["caught"]))
    if not pend:
        return
    if st["last_poll"] and now - datetime.fromisoformat(st["last_poll"]) < timedelta(hours=cfg["cadence_h"]) - timedelta(minutes=5):
        return
    K = H._key()  # noqa: SLF001
    mapped = {v["match_key"] for v in st["fixtures"].values()}
    if any(k not in mapped for k in pend) and (
            not st["last_discovery"] or now - datetime.fromisoformat(st["last_discovery"]) > timedelta(hours=24)):
        r = H.get(HOST, H.ODDSPAPI + "/fixtures", {"sportId": 61, "from": str(now.date()),
                                                    "to": str((now + timedelta(hours=cfg["window_early_h"] + 24)).date()),
                                                    "apiKey": K})
        fx = r.json() if r.status_code == 200 else []
        fx = fx if isinstance(fx, list) else fx.get("data", [])
        ms = [{"match_id": int(k.split(":")[1]), "start": t, "a": 1, "b": 2,
               "names": {1: {H.norm(a)}, 2: {H.norm(b)}}} for k, (a, b, t) in pend.items()]
        for mid, f in H.map_fixtures(ms, fx).items():
            tid = next((x.get("tournamentId") for x in fx if x.get("fixtureId") == f["fixtureId"]), None)
            st["fixtures"][str(f["fixtureId"])] = {"match_key": f"vlr:{mid}", "p1_is_team1": f["p1_is_team1"],
                                                   "tournamentId": tid}
        st["last_discovery"] = now.isoformat()
    tids = sorted({str(v["tournamentId"]) for v in st["fixtures"].values()
                   if v.get("tournamentId") and v["match_key"] in pend})
    if tids:
        r = H.get(HOST, H.ODDSPAPI + "/odds-by-tournaments", {"bookmaker": "pinnacle", "tournamentIds": ",".join(tids),
                                                              "apiKey": K})
        first = H.CACHE / "live_first_response.json"
        if not first.exists():
            first.write_text(r.text)
        prices = parse_pinnacle_prices(r.json()) if r.status_code == 200 else {}
        if r.status_code == 200 and not prices and '"price"' in r.text:
            # prices present but none parsed: the unverified layout guess is wrong -> stop spending quota
            cfg["enabled"] = False
            cfg["disabled_reason"] = f"{now:%Y-%m-%d %H:%M}Z parser found no prices in a priced response; see {first.name}"
            CONFIG.write_text(json.dumps(cfg, indent=1))
        f = LG.Fetcher()
        books_done = False
        for fid, (o1, o2) in prices.items():
            meta = st["fixtures"].get(fid)
            if meta is None or meta["match_key"] not in pend or meta["match_key"] in st["caught"]:
                continue
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            st["caught"][meta["match_key"]] = ts
            con.execute("INSERT OR IGNORE INTO pinnacle_open VALUES (?,?,?,?,?,?)",
                        (fid, meta["match_key"], ts, o1, o2, int(meta["p1_is_team1"])))
            url = con.execute("SELECT url FROM match_status WHERE match_key=?", (meta["match_key"],)).fetchone()[0]
            start, rows = LG.parse_match_odds(f.get(LG.VLR + url).text)
            con.executemany(f"INSERT INTO odds_snapshots VALUES ({','.join('?' * 19)})",
                            [(ts, "vlr", meta["match_key"], url, None, start, o["team"], o["book"], o["odds"], None, None,
                              None, None, None, None, o["status"], o["raw"], "pinnacle_open", fid) for o in rows])
            if not books_done:  # all open VALORANT books once per catch batch
                mk = con.execute("""SELECT DISTINCT match_url, match_key, event FROM odds_snapshots WHERE source='kalshi'
                                    AND ts_utc = (SELECT max(ts_utc) FROM odds_snapshots WHERE source='kalshi')""").fetchall()
                LG.snapshot_books(con, [(t, e.split(":", 1)[1], s_) for t, e, s_ in mk], ts, trigger="pinnacle_open")
                books_done = True
    st["last_poll"] = now.isoformat()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st))
    con.commit()


if __name__ == "__main__":
    run()
