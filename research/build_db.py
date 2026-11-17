"""Build research tables in data/valorant_stats.db from cached vlr.gg match pages.

Tables written (all rebuilt idempotently):
  teams(team_id PK, name, tag, home_region)            canonical vlr team id
  team_aliases(alias PK, team_id)                       lowercase names/tags/slug-names -> id
  events(event_id PK, slug, name, season, region, tier, is_international, start_utc)
  research_matches(match_id PK, match_url, event_id, date_utc, best_of, team1_id, team2_id,
                   team1_maps, team2_maps, winner_id, season, region, is_international,
                   weeks_since_season_start, series_text)
  match_odds(match_id, book, team_id, odds, observed_side)   every odds line as published
  moneyline_matches  (app table; + team ids, imputation flags, book, vig assumption)
  map_results(match_id, game_id PK, map_num, map_name, picked_by_id, team1_score, team2_score,
              team1_atk, team1_def, team2_atk, team2_def, team1_start_side)
  map_rounds(game_id, round_num, winner_id, winner_side)
  lineups(match_url, match_id, game_id, map_name, team_id, p1..p5)   sorted player ids
  player_map_stats_v2(game_id, player_id, player_name, team_id, agent, rating2, acs, kills,
                      deaths, assists, kast, adr, fb, fd)

Usage: python -m research.build_db [--workers 8]
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

from research import parse_match as P
from research import vlr_fetch as v

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DB = REPO / "data" / "valorant_stats.db"
PARSED = ROOT / "cache" / "parsed"
MATCH_LISTS = ["tier1_matches.json", "extra_matches.json"]
ASSUMED_OVERROUND = 1.05  # what populate_moneyline.py assumed when imputing


def _parse_one(url: str) -> dict | None:
    fp = PARSED / (url.strip("/").split("/")[0] + ".json")
    if fp.exists():
        return json.loads(fp.read_text(encoding="utf-8"))
    if not v.cached(url):
        return None
    d = P.parse(v.get(url), url)
    for mp in d["maps"]:
        mp["team1_start_side"] = P.team1_start_side(mp)
    fp.write_text(json.dumps(d), encoding="utf-8")
    return d


def event_meta(slug: str, name: str | None = None) -> dict:
    s = slug.lower()
    yr = re.search(r"20(2\d)", s)
    season = int("20" + yr[1]) if yr else None
    intl = any(k in s for k in ("masters", "valorant-champions", "lock-in", "lockin",
                                "esports-world-cup", "last-chance"))
    region = None
    for r in ("americas", "emea", "pacific", "china"):
        if r in s:
            region = r
    if "lcq" in s or "last-chance" in s:
        intl = False  # LCQs are intra-region
    if intl:
        region = "international"
    return {"slug": slug, "name": name or slug, "season": season, "region": region,
            "tier": 1, "is_international": int(intl)}


SCHEMA = """
DROP TABLE IF EXISTS teams; DROP TABLE IF EXISTS team_aliases; DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS research_matches; DROP TABLE IF EXISTS match_odds;
DROP TABLE IF EXISTS map_results; DROP TABLE IF EXISTS map_rounds; DROP TABLE IF EXISTS lineups;
DROP TABLE IF EXISTS player_map_stats_v2;
CREATE TABLE teams(team_id INTEGER PRIMARY KEY, name TEXT, tag TEXT, home_region TEXT);
CREATE TABLE team_aliases(alias TEXT PRIMARY KEY, team_id INTEGER, source TEXT);
CREATE TABLE events(event_id INTEGER PRIMARY KEY, slug TEXT, name TEXT, season INTEGER,
  region TEXT, tier INTEGER, is_international INTEGER, start_utc TEXT);
CREATE TABLE research_matches(match_id INTEGER PRIMARY KEY, match_url TEXT UNIQUE, event_id INTEGER,
  date_utc TEXT, best_of INTEGER, team1_id INTEGER, team2_id INTEGER, team1_maps INTEGER,
  team2_maps INTEGER, winner_id INTEGER, season INTEGER, region TEXT, is_international INTEGER,
  weeks_since_season_start REAL, series_text TEXT);
CREATE TABLE match_odds(match_id INTEGER, book TEXT, team_id INTEGER, odds REAL,
  observed_side TEXT, PRIMARY KEY(match_id, book, team_id));
CREATE TABLE map_results(game_id INTEGER PRIMARY KEY, match_id INTEGER, map_num INTEGER,
  map_name TEXT, picked_by_id INTEGER, team1_score INTEGER, team2_score INTEGER,
  team1_atk INTEGER, team1_def INTEGER, team2_atk INTEGER, team2_def INTEGER,
  team1_start_side TEXT, n_rounds_parsed INTEGER);
CREATE TABLE map_rounds(game_id INTEGER, round_num INTEGER, winner_id INTEGER, winner_side TEXT,
  PRIMARY KEY(game_id, round_num));
CREATE TABLE lineups(match_url TEXT, match_id INTEGER, game_id INTEGER, map_name TEXT,
  team_id INTEGER, p1 INTEGER, p2 INTEGER, p3 INTEGER, p4 INTEGER, p5 INTEGER,
  PRIMARY KEY(game_id, team_id));
CREATE TABLE player_map_stats_v2(game_id INTEGER, match_id INTEGER, player_id INTEGER,
  player_name TEXT, team_id INTEGER, agent TEXT, rating2 REAL, acs REAL, kills REAL, deaths REAL,
  assists REAL, kast REAL, adr REAL, fb REAL, fd REAL, PRIMARY KEY(game_id, player_id));
"""

MONEYLINE_COLS = {
    "team1_id": "INTEGER", "team2_id": "INTEGER", "odds_book": "TEXT",
    "team1_odds_imputed": "INTEGER DEFAULT 0", "team2_odds_imputed": "INTEGER DEFAULT 0",
    "imputed_overround": "REAL", "season": "INTEGER", "region": "TEXT",
    "is_international": "INTEGER", "weeks_since_season_start": "REAL",
}


def ensure_app_schema(con: sqlite3.Connection) -> None:
    """Create app tables via backend.database, then add moneyline columns additively."""
    import sys
    sys.path.insert(0, str(REPO))
    from backend.database import Database  # noqa: E402
    Database(str(DB))
    have = {r[1] for r in con.execute("PRAGMA table_info(moneyline_matches)")}
    for c, t in MONEYLINE_COLS.items():
        if c not in have:
            con.execute(f"ALTER TABLE moneyline_matches ADD COLUMN {c} {t}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    PARSED.mkdir(parents=True, exist_ok=True)
    DB.parent.mkdir(parents=True, exist_ok=True)

    lists: dict[str, list[str]] = {}
    for f in MATCH_LISTS:
        fp = ROOT / "cache" / f
        if fp.exists():
            lists.update(json.loads(fp.read_text()))
    urls = [(ev, m) for ev, ms in lists.items() for m in ms]
    with ProcessPoolExecutor(args.workers) as ex:
        parsed = list(ex.map(_parse_one, [m for _, m in urls], chunksize=8))

    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    ensure_app_schema(con)

    names: dict[int, Counter] = defaultdict(Counter)
    tags: dict[int, Counter] = defaultdict(Counter)
    aliases: dict[str, tuple[int, str]] = {}
    events: dict[int, dict] = {}
    rows = []
    skipped = Counter()
    for (ev_path, url), d in zip(urls, parsed):
        if d is None:
            skipped["not_cached"] += 1
            continue
        if d["status"] != "final" or not d["team1"]["id"] or not d["team2"]["id"]:
            skipped["not_final_or_tbd"] += 1
            continue
        eid = int(ev_path.split("/")[2])
        if eid not in events:
            events[eid] = {"event_id": eid, **event_meta(ev_path.split("/")[3])}
        rows.append((eid, d))
        for k in ("team1", "team2"):
            t = d[k]
            names[t["id"]][t["name"]] += 1
            aliases.setdefault(t["name"].lower(), (t["id"], "header"))
        # legacy slug-derived names (what populate_database.get_event_matches produced)
        sm = re.match(r"/\d+/([\w-]+)-vs-([\w-]+)", url)
        if sm:
            for k, g in (("team1", 1), ("team2", 2)):
                legacy = sm[g].replace("-", " ").title().lower()
                aliases.setdefault(legacy, (d[k]["id"], "legacy_slug"))
        for mp in d["maps"]:
            for p in mp["players"]:
                tid = d["team1" if p["team_idx"] == 1 else "team2"]["id"]
                if p["team_tag"]:
                    tags[tid][p["team_tag"]] += 1

    # event start + season start
    for eid, d in rows:
        dt = d["date_utc"]
        if dt and (events[eid].get("start_utc") is None or dt < events[eid]["start_utc"]):
            events[eid]["start_utc"] = dt
    season_start: dict[int, str] = {}
    for e in events.values():
        if e["season"] and e.get("start_utc"):
            s0 = season_start.get(e["season"])
            season_start[e["season"]] = min(s0, e["start_utc"]) if s0 else e["start_utc"]

    # home region = modal regional-league region per team (all seasons)
    reg_counts: dict[int, Counter] = defaultdict(Counter)
    for eid, d in rows:
        r = events[eid]["region"]
        if r and r != "international":
            reg_counts[d["team1"]["id"]][r] += 1
            reg_counts[d["team2"]["id"]][r] += 1

    for tid, c in names.items():
        tag = tags[tid].most_common(1)[0][0] if tags[tid] else None
        home = reg_counts[tid].most_common(1)[0][0] if reg_counts[tid] else None
        con.execute("INSERT INTO teams VALUES (?,?,?,?)", (tid, c.most_common(1)[0][0], tag, home))
        if tag:
            aliases.setdefault(tag.lower(), (tid, "tag"))
    con.executemany("INSERT OR IGNORE INTO team_aliases VALUES (?,?,?)",
                    [(a, t, s) for a, (t, s) in aliases.items()])
    for e in events.values():
        con.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?)",
                    (e["event_id"], e["slug"], e["name"], e["season"], e["region"], e["tier"],
                     e["is_international"], e.get("start_utc")))

    def tid_for_name(d: dict, name: str | None) -> int | None:
        if not name:
            return None
        n = name.strip().lower()
        for k in ("team1", "team2"):
            if d[k]["name"] and d[k]["name"].strip().lower() == n:
                return d[k]["id"]
        for k in ("team1", "team2"):  # tag fallback (odds widget sometimes shows tag)
            tid = d[k]["id"]
            if tags[tid] and n in {t.lower() for t in tags[tid]}:
                return tid
        return None

    n_odds_unmatched = 0
    for eid, d in rows:
        e = events[eid]
        t1, t2 = d["team1"]["id"], d["team2"]["id"]
        win = t1 if d["winner"] == 1 else t2 if d["winner"] == 2 else None
        wk = None
        if d["date_utc"] and season_start.get(e["season"]):
            fmt = "%Y-%m-%d %H:%M:%S"
            wk = (datetime.strptime(d["date_utc"], fmt)
                  - datetime.strptime(season_start[e["season"]], fmt)).days / 7.0
        con.execute("INSERT INTO research_matches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (d["match_id"], d["match_url"], eid, d["date_utc"], d["best_of"], t1, t2,
                     d["team1_maps"], d["team2_maps"], win, e["season"], e["region"],
                     e["is_international"], wk, d["series_text"]))
        tp: dict[int, float] = {}
        for o in d["odds"]:
            tid = tid_for_name(d, o["team_name"])
            if tid is None or o["odds"] is None or o["odds"] <= 1.01:
                n_odds_unmatched += 1
                continue
            side = "winner" if tid == win else "loser"
            con.execute("INSERT OR IGNORE INTO match_odds VALUES (?,?,?,?,?)",
                        (d["match_id"], o["book"], tid, o["odds"], side))
            if o["book"] == "thunderpick":
                tp[tid] = o["odds"]
        # moneyline_matches: Thunderpick only; impute missing side at ASSUMED_OVERROUND, flagged
        o1, o2 = tp.get(t1), tp.get(t2)
        imp1 = imp2 = 0
        if o1 and not o2:
            o2, imp2 = round(1.0 / (ASSUMED_OVERROUND - 1.0 / o1), 2), 1
        elif o2 and not o1:
            o1, imp1 = round(1.0 / (ASSUMED_OVERROUND - 1.0 / o2), 2), 1
        wname = d["team1"]["name"] if d["winner"] == 1 else d["team2"]["name"] if d["winner"] == 2 else None
        con.execute("""INSERT INTO moneyline_matches (match_url, event_name, event_url, team1, team2,
              team1_odds, team2_odds, winner, team1_maps, team2_maps, match_date, team1_id, team2_id,
              odds_book, team1_odds_imputed, team2_odds_imputed, imputed_overround, season, region,
              is_international, weeks_since_season_start)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(match_url) DO UPDATE SET event_name=excluded.event_name,
              event_url=excluded.event_url, team1=excluded.team1, team2=excluded.team2,
              team1_odds=excluded.team1_odds, team2_odds=excluded.team2_odds, winner=excluded.winner,
              team1_maps=excluded.team1_maps, team2_maps=excluded.team2_maps,
              match_date=excluded.match_date, team1_id=excluded.team1_id, team2_id=excluded.team2_id,
              odds_book=excluded.odds_book, team1_odds_imputed=excluded.team1_odds_imputed,
              team2_odds_imputed=excluded.team2_odds_imputed,
              imputed_overround=excluded.imputed_overround, season=excluded.season,
              region=excluded.region, is_international=excluded.is_international,
              weeks_since_season_start=excluded.weeks_since_season_start""",
                    (d["match_url"], e["name"], f"/event/{eid}/{e['slug']}", d["team1"]["name"],
                     d["team2"]["name"], o1, o2, wname, d["team1_maps"], d["team2_maps"],
                     d["date_utc"], t1, t2, "thunderpick" if tp else None, imp1, imp2,
                     ASSUMED_OVERROUND if (imp1 or imp2) else None, e["season"], e["region"],
                     e["is_international"], wk))
        for i, mp in enumerate(d["maps"], start=1):
            pick = t1 if mp["picked_by"] == 1 else t2 if mp["picked_by"] == 2 else None
            s1, s2 = mp["team1_sides"], mp["team2_sides"]
            con.execute("INSERT OR REPLACE INTO map_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (mp["game_id"], d["match_id"], i, mp["map_name"], pick, mp["team1_score"],
                         mp["team2_score"], s1.get("t"), s1.get("ct"), s2.get("t"), s2.get("ct"),
                         mp.get("team1_start_side"), len(mp["rounds"])))
            con.executemany("INSERT OR REPLACE INTO map_rounds VALUES (?,?,?,?)",
                            [(mp["game_id"], r["round"], t1 if r["winner"] == 1 else t2,
                              r["winner_side"]) for r in mp["rounds"]])
            for ti, tid in ((1, t1), (2, t2)):
                ps = sorted(p["player_id"] for p in mp["players"]
                            if p["team_idx"] == ti and p["player_id"])
                if len(ps) == 5:
                    con.execute("INSERT OR REPLACE INTO lineups VALUES (?,?,?,?,?,?,?,?,?,?)",
                                (d["match_url"], d["match_id"], mp["game_id"], mp["map_name"],
                                 tid, *ps))
            con.executemany(
                "INSERT OR REPLACE INTO player_map_stats_v2 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(mp["game_id"], d["match_id"], p["player_id"], p["player_name"],
                  t1 if p["team_idx"] == 1 else t2, p["agent"], p["rating2"], p["acs"],
                  p["kills"], p["deaths"], p["assists"], p["kast"], p["adr"], p["fb"], p["fd"])
                 for p in mp["players"] if p["player_id"]])
    con.commit()
    q = lambda s: con.execute(s).fetchone()[0]  # noqa: E731
    print(f"matches {q('select count(*) from research_matches')} | skipped {dict(skipped)}")
    print(f"maps {q('select count(*) from map_results')} | rounds {q('select count(*) from map_rounds')}"
          f" | lineups {q('select count(*) from lineups')} | teams {q('select count(*) from teams')}")
    print(f"odds lines {q('select count(*) from match_odds')} (unmatched {n_odds_unmatched}) | "
          f"moneyline w/ thunderpick {q('select count(*) from moneyline_matches where odds_book is not null')}"
          f" | both sides observed {q('select count(*) from moneyline_matches where odds_book is not null and team1_odds_imputed=0 and team2_odds_imputed=0')}")
    con.close()


if __name__ == "__main__":
    main()
