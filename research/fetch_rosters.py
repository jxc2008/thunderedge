"""Roster snapshots for PREREG_KICKOFF2027.md §3 (a team's expected five before its first 2027 match).

NOT RUN YET: needs the page budget approved (~48 team pages). Every request goes through
research/vlr_fetch.get, which refuses once the ledger exceeds VLR_PAGE_BUDGET, so this script
cannot exceed the cap by accident. The vlr team-page roster layout has not been verified on a
2027 page: run `--validate <team_id>` once (1 page) and check the parsed five by eye first.

Writes roster_snapshots(team_id, team_name, captured_ts, p1..p5, raw_players) into
data/valorant_stats.db.  `refresh=True`: rosters must be fresh, not cached.

Usage:
  VLR_PAGE_BUDGET=<approved> python -m research.fetch_rosters --validate 2593
  VLR_PAGE_BUDGET=<approved> python -m research.fetch_rosters --teams 2593 1001 ...
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from research import vlr_fetch as v

DB = v.ROOT.parent / "data" / "valorant_stats.db"
NOT_PLAYING = re.compile(r"\b(sub|inactive|stand-?in|coach|manager|analyst|staff|head|assistant)\b", re.I)


def parse_roster(html: str) -> tuple[str, list[dict]]:
    s = BeautifulSoup(html, "lxml")
    name_el = s.select_one(".team-header-name h1, .wf-title")
    name = name_el.get_text(" ", strip=True) if name_el else ""
    players = []
    for item in s.select(".team-roster-item"):
        a = item.select_one("a[href^='/player/']")
        if a is None:
            continue
        pid = int(a["href"].split("/")[2])
        tags = " ".join(t.get_text(" ", strip=True) for t in item.select(".wf-tag, .team-roster-item-name-role"))
        alias = item.select_one(".team-roster-item-name-alias")
        players.append({"player_id": pid, "alias": alias.get_text(" ", strip=True) if alias else "",
                        "tags": tags, "active": not NOT_PLAYING.search(tags)})
    return name, players


def snapshot(team_id: int, con: sqlite3.Connection) -> dict:
    html = v.get(f"/team/{team_id}/", refresh=True)
    name, players = parse_roster(html)
    five = [p["player_id"] for p in players if p["active"]]
    row = {"team_id": team_id, "team_name": name, "players": players, "five": five}
    if len(five) == 5:
        con.execute("""CREATE TABLE IF NOT EXISTS roster_snapshots(team_id INTEGER, team_name TEXT,
                       captured_ts TEXT, p1 INTEGER, p2 INTEGER, p3 INTEGER, p4 INTEGER, p5 INTEGER,
                       raw_players TEXT)""")
        con.execute("INSERT INTO roster_snapshots VALUES (?,?,?,?,?,?,?,?,?)",
                    (team_id, name, datetime.now(timezone.utc).isoformat(timespec="seconds"), *five,
                     json.dumps(players)))
        con.commit()
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", type=int)
    ap.add_argument("--teams", type=int, nargs="*")
    a = ap.parse_args()
    con = sqlite3.connect(DB)
    if a.validate:
        print(json.dumps(snapshot(a.validate, con), indent=1))
        return
    for t in a.teams or []:
        r = snapshot(t, con)
        print(t, r["team_name"], "five ok" if len(r["five"]) == 5 else f"NOT 5: {r['five']}")


if __name__ == "__main__":
    main()
