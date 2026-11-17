"""Historical lines for the exploratory stale-line / lag study (REPORT_v3 §5).

Approved budget (user, 2026-11-17): <= 720 OddsPapi requests, <= 700 Kalshi requests, no Polymarket.
Every request is ledgered (research/cache/hist/ledger.csv) and every response cached, so reruns are
free. Raw OddsPapi data stays under research/cache/ (gitignored): its terms forbid redistribution.

Scope: 2026 tier-1 VCT matches in data/valorant_stats.db.
  - Kalshi: market list reused from the survey (no new listing calls); one 1-min candlestick call
    per mapped event, on the market for vlr team 1, window [start - 72 h, start + 8 h].
  - OddsPapi: fixtures for the 2026 tier-1 tournaments (cached from the survey + Kickoff IDs +
    date windows for Masters Santiago / EWC), then /historical-odds?bookmakers=pinnacle per mapped
    fixture (non-billable, 5 s cooldown).

Usage:
  python -m research.hist_fetch map         # fixtures + mapping report (<= ~10 billable calls)
  python -m research.hist_fetch kalshi      # candles
  python -m research.hist_fetch oddspapi    # Pinnacle history
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache" / "hist"
LEDGER = CACHE / "ledger.csv"
DB = ROOT.parent / "data" / "valorant_stats.db"
SURVEY_RAW = CACHE / "survey"  # index files saved by the 2026-11-17 source survey (gitignored)
ENV = ROOT.parent.parent / "valorant-pricing-model" / ".env"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
ODDSPAPI = "https://api.oddspapi.io/v4"
CAP = {"kalshi": 700, "oddspapi": 720, "oddspapi_prereg": 320}  # prereg: see PREREG §4
SPACING = {"kalshi": 1.2, "oddspapi_hist": 5.5, "oddspapi": 2.2, "oddspapi_prereg": 5.5}
KALSHI_CUTOFF = datetime(2026, 9, 18, tzinfo=timezone.utc)
KICKOFF_TOURNAMENTS = ["902379", "902380", "902381", "904619"]
EXTRA_WINDOWS = [("2026-02-27", "2026-03-08"), ("2026-03-08", "2026-03-16"),   # Masters Santiago
                 ("2026-07-01", "2026-07-07"), ("2026-07-07", "2026-07-13")]   # EWC 2026
STOP = re.compile(r"\b(esports?|gaming|team|club|gc)\b")
UA = {"User-Agent": "research-hist/0.1"}
_last: dict[str, float] = {}


def _key() -> str:
    for line in ENV.read_text().splitlines():
        if line.startswith("ODDSPAPI_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("ODDSPAPI_KEY missing")


def used(host: str) -> int:
    if not LEDGER.exists():
        return 0
    with LEDGER.open() as f:
        return sum(1 for r in csv.reader(f) if r and r[1] == host)


def get(host: str, url: str, params: dict, kind: str | None = None) -> requests.Response:
    if used(host) >= CAP[host]:
        raise RuntimeError(f"{host} budget of {CAP[host]} reached")
    k = kind or host
    wait = SPACING[k] - (time.monotonic() - _last.get(k, 0))
    if wait > 0:
        time.sleep(wait)
    for attempt in range(4):
        r = requests.get(url, params=params, headers=UA, timeout=60)
        _last[k] = time.monotonic()
        CACHE.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", newline="") as f:
            safe = re.sub(r"apiKey=[^&]+", "apiKey=<KEY>", r.url)
            csv.writer(f).writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), host, safe[:300],
                                    r.status_code])
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1))
            continue
        return r
    return r


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", STOP.sub(" ", s))


# ------------------------------------------------------------------------------ vlr side
def vlr_matches(season: int = 2026) -> list[dict]:
    con = sqlite3.connect(DB)
    names: dict[int, set[str]] = {}
    for tid, name, tag in con.execute("SELECT team_id, name, tag FROM teams"):
        names.setdefault(tid, set()).update({norm(name), norm(tag)})
    for alias, tid in con.execute("SELECT alias, team_id FROM team_aliases"):
        names.setdefault(tid, set()).add(norm(alias))
    out = []
    for mid, date, t1, t2, win, ev, url in con.execute(
            """SELECT m.match_id, m.date_utc, m.team1_id, m.team2_id, m.winner_id, e.slug, m.match_url
               FROM research_matches m JOIN events e USING(event_id) WHERE m.season=? ORDER BY m.date_utc""",
            (season,)):
        out.append({"match_id": mid, "start": datetime.fromisoformat(date).replace(tzinfo=timezone.utc),
                    "a": t1, "b": t2, "winner": win, "event": ev, "url": url,
                    "names": {t1: {n for n in names.get(t1, set()) if n}, t2: {n for n in names.get(t2, set()) if n}}})
    return out


def team_hit(name: str, cands: set[str]) -> bool:
    n = norm(name)
    return bool(n) and any(n == c or (min(len(n), len(c)) >= 3 and (n in c or c in n)) for c in cands)


def pair(ms: list[dict], n1: str, n2: str, t: datetime, tol_h: float = 36) -> tuple[dict, int] | None:
    """vlr match with both names within tol_h of t; returns (match, team id of n1)."""
    best = None
    for m in ms:
        dt = abs((m["start"] - t).total_seconds()) / 3600
        if dt > tol_h:
            continue
        for x, y in ((m["a"], m["b"]), (m["b"], m["a"])):
            if team_hit(n1, m["names"][x]) and team_hit(n2, m["names"][y]):
                if best is None or dt < best[2]:
                    best = (m, x, dt)
    return (best[0], best[1]) if best else None


# ------------------------------------------------------------------------------ Kalshi
def kalshi_events() -> dict[str, list[dict]]:
    mk = []
    for f in ("kalshi_hist_markets.json", "kalshi_live_settled.json"):
        d = json.loads((SURVEY_RAW / f).read_text())
        mk += d if isinstance(d, list) else d.get("markets", [])
    ev: dict[str, dict] = {}
    for m in mk:
        ev.setdefault(m["event_ticker"], {})[m["ticker"]] = m
    return {k: list(v.values()) for k, v in ev.items() if len(v) == 2}


def ticker_time(ev_ticker: str, m: dict) -> datetime:
    g = re.search(r"-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})", ev_ticker)
    if g:
        d = datetime.strptime(f"20{g[1]}{g[2]}{g[3]}{g[4]}{g[5]}", "%Y%b%d%H%M")
        rules = m.get("rules_primary") or ""
        off = 4 if "EDT" in rules else 5  # ET -> UTC
        return d.replace(tzinfo=timezone.utc) + timedelta(hours=off)
    return datetime.fromisoformat(m["open_time"].replace("Z", "+00:00")) + timedelta(hours=24)


def team_of(m: dict) -> str:
    return m.get("yes_sub_title") or re.sub(r"\s+wins.*$", "", m.get("title") or "")


# ------------------------------------------------------------------------------ OddsPapi
def fixtures(fetch: bool) -> list[dict]:
    fx: list[dict] = []
    for v in json.loads((SURVEY_RAW / "op_fixtures_by_tournament_2026.json").read_text()).values():
        fx += v
    if fetch:
        K = _key()
        for tid in KICKOFF_TOURNAMENTS:
            fp = CACHE / f"op_fixtures_t{tid}.json"
            if not fp.exists():
                r = get("oddspapi", ODDSPAPI + "/fixtures", {"tournamentId": tid, "apiKey": K})
                fp.write_text(r.text if r.status_code == 200 else "[]")
        for a, b in EXTRA_WINDOWS:
            fp = CACHE / f"op_fixtures_{a}_{b}.json"
            if not fp.exists():
                r = get("oddspapi", ODDSPAPI + "/fixtures", {"sportId": 61, "from": a, "to": b, "apiKey": K})
                fp.write_text(r.text if r.status_code == 200 else "[]")
    for fp in CACHE.glob("op_fixtures_*.json"):
        d = json.loads(fp.read_text() or "[]")
        fx += d if isinstance(d, list) else d.get("data", [])
    seen, out = set(), []
    for f in fx:
        if f["fixtureId"] not in seen:
            seen.add(f["fixtureId"])
            out.append(f)
    return out


def fixture_windows(dates: list[datetime], host: str) -> list[dict]:
    """Fixtures for every <=10-day window covering ``dates`` (billable; cached per window)."""
    if not dates:
        return []
    K, out = _key(), []
    a = min(dates).date()
    while a <= max(dates).date():
        b = a + timedelta(days=9)
        fp = CACHE / f"op_fixtures_{a}_{b}.json"
        if not fp.exists():
            r = get(host, ODDSPAPI + "/fixtures", {"sportId": 61, "from": str(a), "to": str(b), "apiKey": K})
            fp.write_text(r.text if r.status_code == 200 else "[]")
        d = json.loads(fp.read_text() or "[]")
        out += d if isinstance(d, list) else d.get("data", [])
        a = b + timedelta(days=1)
    return out


def map_fixtures(ms: list[dict], fx: list[dict]) -> dict:
    res = {}
    for f in fx:
        st = f.get("trueStartTime") or f.get("startTime")
        if not st:
            continue
        hit = pair(ms, f.get("participant1Name"), f.get("participant2Name"),
                   datetime.fromisoformat(st.replace("Z", "+00:00")))
        if hit:
            m, tid0 = hit
            res[str(m["match_id"])] = {"fixtureId": f["fixtureId"], "p1_is_team1": tid0 == m["a"],
                                       "startTime": f.get("startTime"), "trueStartTime": f.get("trueStartTime"),
                                       "trueEndTime": f.get("trueEndTime")}
    return res


def fetch_history(fixture_id: str, host: str) -> None:
    fp = CACHE / f"op_hist_{fixture_id}.json"
    if fp.exists():
        return
    r = get(host, ODDSPAPI + "/historical-odds", {"fixtureId": fixture_id, "bookmakers": "pinnacle", "apiKey": _key()},
            kind="oddspapi_hist" if host == "oddspapi" else host)
    fp.write_text(r.text if r.status_code == 200 else json.dumps({"error": r.status_code, "body": r.text[:300]}))


def build_map(fetch: bool) -> dict:
    ms = vlr_matches()
    res: dict = {"kalshi": {}, "oddspapi": {}}
    for ev, mks in kalshi_events().items():
        t = ticker_time(ev, mks[0])
        if t.year != 2026:
            continue
        hit = pair(ms, team_of(mks[0]), team_of(mks[1]), t)
        if hit:
            m, tid0 = hit
            mk_a = mks[0] if tid0 == m["a"] else mks[1]
            res["kalshi"][str(m["match_id"])] = {"event": ev, "ticker_team1": mk_a["ticker"],
                                                 "settlement_ts": mk_a.get("settlement_ts"),
                                                 "close_time": mk_a.get("close_time"),
                                                 "open_time": mk_a.get("open_time"), "ticker_time": t.isoformat()}
    res["oddspapi"] = map_fixtures(ms, fixtures(fetch))
    (CACHE / "mapping.json").write_text(json.dumps(res, indent=1))
    n = len(ms)
    both = set(res["kalshi"]) & set(res["oddspapi"])
    print(f"vlr 2026 tier-1 matches {n}; mapped Kalshi {len(res['kalshi'])}, OddsPapi {len(res['oddspapi'])}, both {len(both)}")
    by_ev: dict = {}
    for m in ms:
        k = str(m["match_id"])
        e = by_ev.setdefault(m["event"], [0, 0, 0])
        e[0] += 1
        e[1] += k in res["kalshi"]
        e[2] += k in res["oddspapi"]
    for e, (a, b, c) in by_ev.items():
        print(f"  {e:40s} {a:3d}  kalshi {b:3d}  oddspapi {c:3d}")
    print("ledger:", {h: used(h) for h in CAP})
    return res


def run_kalshi() -> None:
    mp = json.loads((CACHE / "mapping.json").read_text())["kalshi"]
    starts = {str(m["match_id"]): m["start"] for m in vlr_matches()}
    for i, (mid, k) in enumerate(sorted(mp.items())):
        fp = CACHE / f"k_candles_{k['ticker_team1']}.json"
        if fp.exists():
            continue
        s = starts[mid]
        settled = datetime.fromisoformat((k["settlement_ts"] or k["close_time"]).replace("Z", "+00:00"))
        path = (f"/historical/markets/{k['ticker_team1']}/candlesticks" if settled < KALSHI_CUTOFF
                else f"/series/KXVALORANTGAME/markets/{k['ticker_team1']}/candlesticks")
        r = get("kalshi", KALSHI + path, {"start_ts": int((s - timedelta(hours=72)).timestamp()),
                                          "end_ts": int((s + timedelta(hours=8)).timestamp()), "period_interval": 1})
        fp.write_text(r.text if r.status_code == 200 else json.dumps({"error": r.status_code, "body": r.text[:300]}))
        if i % 25 == 0:
            print(f"kalshi {i}/{len(mp)} used {used('kalshi')}", flush=True)
    print("kalshi done; used", used("kalshi"))


def run_oddspapi() -> None:
    mp = json.loads((CACHE / "mapping.json").read_text())["oddspapi"]
    K = _key()
    for i, (_mid, f) in enumerate(sorted(mp.items())):
        fp = CACHE / f"op_hist_{f['fixtureId']}.json"
        if fp.exists():
            continue
        r = get("oddspapi", ODDSPAPI + "/historical-odds", {"fixtureId": f["fixtureId"], "bookmakers": "pinnacle",
                                                           "apiKey": K}, kind="oddspapi_hist")
        fp.write_text(r.text if r.status_code == 200 else json.dumps({"error": r.status_code, "body": r.text[:300]}))
        if i % 25 == 0:
            print(f"oddspapi {i}/{len(mp)} used {used('oddspapi')}", flush=True)
    print("oddspapi done; used", used("oddspapi"))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "map"
    {"map": lambda: build_map(fetch=True), "kalshi": run_kalshi, "oddspapi": run_oddspapi}[cmd]()
