"""Catch Pinnacle's opening price for upcoming tier-1 matches and snapshot Thunderpick at the same moment.

DISABLED unless research/pinnacle_open.json has "enabled": true (user decision: OddsPapi cost).
Runs after each odds-logger poll (research/odds_logger_task.cmd). Per run, when enabled and due:
  1. upcoming tier-1 matches from the logger (match_status 'upcoming', start within 72 h); none -> no cost;
  2. fixture discovery: /v4/fixtures?sportId=61&from&to (billable), at most once a day, mapped to vlr
     matches by team names and time (research/hist_fetch.map_fixtures); tournament ids collected;
  3. /v4/odds-by-tournaments?bookmaker=pinnacle&tournamentIds=... (one billable call for all fixtures);
  4. for each mapped fixture with a two-sided Pinnacle match-winner price not seen before: store it in
     pinnacle_open and fetch the vlr match page right away (Thunderpick rows tagged trigger='pinnacle_open').
Billable calls go through hist_fetch.get under the ledger label 'oddspapi_live' with a weekly cap.
The odds-by-tournaments response layout is parsed defensively and has NOT been verified against the
live API (no quota spent); the first response is saved to cache/hist/live_first_response.json.

Cost in season (one match within 72 h most days): polls/week = 10,080 / interval_min, + 7 discovery calls.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "pinnacle_open.json"
STATE = ROOT / "cache" / "hist" / "pinnacle_open_state.json"
HOST = "oddspapi_live"


def weekly_cost(interval_min: float) -> int:
    return int(7 * 24 * 60 / interval_min) + 7


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
            out[f["fixtureId"]] = (float(p1), float(p2))
    return out


def run() -> None:
    cfg = json.loads(CONFIG.read_text())
    if not cfg.get("enabled"):
        return
    from research import hist_fetch as H, odds_logger as LG  # noqa: PLC0415
    from research.timeutil import vlr_to_utc  # noqa: PLC0415
    now = datetime.now(timezone.utc)
    st = json.loads(STATE.read_text()) if STATE.exists() else {"last_poll": None, "last_discovery": None,
                                                                "fixtures": {}, "seen": {}}
    if st["last_poll"] and now - datetime.fromisoformat(st["last_poll"]) < timedelta(minutes=cfg["interval_min"]):
        return
    week = [r for r in (H.CACHE / "ledger.csv").read_text().splitlines() if f",{HOST}," in r
            and datetime.fromisoformat(r.split(",")[0]) > now - timedelta(days=7)] if (H.CACHE / "ledger.csv").exists() else []
    if len(week) >= cfg["weekly_cap"]:
        return
    con = sqlite3.connect(LG.DB, timeout=30)
    con.execute("""CREATE TABLE IF NOT EXISTS pinnacle_open(fixture_id TEXT PRIMARY KEY, match_key TEXT, first_seen TEXT,
                   price1 REAL, price2 REAL, p1_is_team1 INTEGER)""")
    ups = {}
    for key, team1, team2 in con.execute("SELECT match_key, team1, team2 FROM match_status WHERE status='upcoming'"):
        r = con.execute("SELECT max(start_utc) FROM odds_snapshots WHERE match_key=?", (key,)).fetchone()
        if r and r[0]:
            t = vlr_to_utc(r[0])
            if now < t <= now + timedelta(hours=72):
                ups[key] = (team1, team2, t)
    if not ups:
        return
    K = H._key()
    if not st["last_discovery"] or now - datetime.fromisoformat(st["last_discovery"]) > timedelta(hours=24):
        r = H.get(HOST, H.ODDSPAPI + "/fixtures", {"sportId": 61, "from": str(now.date()),
                                                    "to": str((now + timedelta(days=4)).date()), "apiKey": K})
        fx = r.json() if r.status_code == 200 else []
        ms = [{"match_id": int(k.split(":")[1]), "start": t, "a": 1, "b": 2,
               "names": {1: {H.norm(a)}, 2: {H.norm(b)}}} for k, (a, b, t) in ups.items()]
        for mid, f in H.map_fixtures(ms, fx if isinstance(fx, list) else fx.get("data", [])).items():
            tid = next((x.get("tournamentId") for x in fx if x.get("fixtureId") == f["fixtureId"]), None)
            st["fixtures"][f["fixtureId"]] = {"match_key": f"vlr:{mid}", "p1_is_team1": f["p1_is_team1"], "tournamentId": tid}
        st["last_discovery"] = now.isoformat()
    tids = sorted({str(v["tournamentId"]) for v in st["fixtures"].values() if v.get("tournamentId")})
    if tids:
        r = H.get(HOST, H.ODDSPAPI + "/odds-by-tournaments", {"bookmaker": "pinnacle", "tournamentIds": ",".join(tids),
                                                              "apiKey": K})
        first = H.CACHE / "live_first_response.json"
        if not first.exists():
            first.write_text(r.text)
        prices = parse_pinnacle_prices(r.json()) if r.status_code == 200 else {}
        f = LG.Fetcher()
        for fid, (o1, o2) in prices.items():
            meta = st["fixtures"].get(fid)
            if meta is None or fid in st["seen"]:
                continue
            st["seen"][fid] = now.isoformat()
            con.execute("INSERT OR IGNORE INTO pinnacle_open VALUES (?,?,?,?,?,?)",
                        (fid, meta["match_key"], now.isoformat(timespec="seconds"), o1, o2, int(meta["p1_is_team1"])))
            url = con.execute("SELECT url FROM match_status WHERE match_key=?", (meta["match_key"],)).fetchone()[0]
            start, rows = LG.parse_match_odds(f.get(LG.VLR + url).text)
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            con.executemany(f"INSERT INTO odds_snapshots VALUES ({','.join('?' * 19)})",
                            [(ts, "vlr", meta["match_key"], url, None, start, o["team"], o["book"], o["odds"], None, None,
                              None, None, None, None, o["status"], o["raw"], "pinnacle_open", fid) for o in rows])
    st["last_poll"] = now.isoformat()
    STATE.write_text(json.dumps(st))
    con.commit()


if __name__ == "__main__":
    run()
