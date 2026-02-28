# scripts/populate_round_data.py
"""
Populate match_round_data table with round-level economy data from rib.gg.

All economy data (loadout tier, round winner) is embedded in the series page's
__NEXT_DATA__ JSON — no separate ?tab=economy request needed.

Strategy:
  1. For each VCT 2026 kickoff event, enumerate all series via rib.gg event page.
  2. For each series, call get_series_economy_data() to extract:
     - Team names (to cross-reference with our matches table)
     - Per-map economy data (rounds with tier + winner)
  3. Cross-reference rib.gg team names with our DB matches by fuzzy comparison.
  4. Save round data to match_round_data.

Run once; already-populated (match_id, map_number) pairs are skipped.

Usage:
  python scripts/populate_round_data.py
  python scripts/populate_round_data.py --dry-run
  python scripts/populate_round_data.py --event-id 6242   # Americas only
"""

import sys
import os
import re
import time
import random
import argparse
import logging
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import Database
from scraper.rib_scraper import RibScraper
from config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    return re.sub(r'[^a-z0-9 ]', '', name.lower()).strip()


def _fuzzy_match(rib_name: str, db_name: str) -> bool:
    rn = _normalize(rib_name)
    dn = _normalize(db_name)
    if not rn or not dn:
        return False
    return rn == dn or rn in dn or dn in rn or rn[:6] == dn[:6]


def _get_already_populated(db_path: str) -> set:
    conn = sqlite3.connect(db_path, timeout=30.0)
    c = conn.cursor()
    c.execute('SELECT DISTINCT match_id, map_number FROM match_round_data')
    result = set(c.fetchall())
    conn.close()
    return result


def _get_2026_matches(db_path: str) -> list:
    conn = sqlite3.connect(db_path, timeout=30.0)
    c = conn.cursor()
    c.execute('''
        SELECT m.id, m.match_url, m.team1, m.team2
        FROM matches m
        JOIN vct_events ve ON m.event_id = ve.id
        WHERE ve.year = 2026
        ORDER BY m.id
    ''')
    rows = c.fetchall()
    conn.close()
    return [{'id': r[0], 'match_url': r[1], 'team1': r[2], 'team2': r[3]} for r in rows]


def _find_db_match(rib_t1: str, rib_t2: str, db_matches: list) -> dict | None:
    for m in db_matches:
        t1 = m['team1'] or ''
        t2 = m['team2'] or ''
        if (_fuzzy_match(rib_t1, t1) and _fuzzy_match(rib_t2, t2)) or \
           (_fuzzy_match(rib_t1, t2) and _fuzzy_match(rib_t2, t1)):
            return m
    return None


def _rib_t1_is_db_team1(rib_t1: str, db_match: dict) -> bool:
    return _fuzzy_match(rib_t1, db_match['team1'] or '')


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true',
                        help='Parse but do not write to DB')
    parser.add_argument('--event-id', default=None,
                        help='Only process this rib.gg event ID')
    args = parser.parse_args()

    db = Database(Config.DATABASE_PATH)
    db._init_db()

    scraper = RibScraper(database=db)
    db_matches = _get_2026_matches(Config.DATABASE_PATH)
    already_done = _get_already_populated(Config.DATABASE_PATH)

    print(f"DB: {len(db_matches)} 2026 matches | {len(already_done)} (match,map) pairs already populated")

    events = scraper.VCT_2026_KICKOFF_EVENTS
    if args.event_id:
        events = [e for e in events if e['id'] == args.event_id]
        if not events:
            print(f"Event ID {args.event_id} not found.")
            return

    total_rounds = 0
    total_maps = 0
    total_skipped = 0
    match_miss = 0

    for event in events:
        print(f"\n=== {event['name']} (id={event['id']}) ===")
        all_series = scraper._get_event_series_slugs(event['slug'], event['id'])
        if not all_series:
            print("  No series found.")
            continue
        print(f"  {len(all_series)} series")

        for s_idx, (s_slug, s_id) in enumerate(all_series, 1):
            print(f"  [{s_idx}/{len(all_series)}] {s_slug[:50]}")

            econ = scraper.get_series_economy_data(s_slug, s_id)
            if econ is None:
                print("    Failed to fetch, skipping.")
                continue

            rib_t1 = econ['team1_name']
            rib_t2 = econ['team2_name']
            maps = econ['maps']

            if not maps:
                print(f"    No map data ({rib_t1} vs {rib_t2}), skipping.")
                continue

            db_match = _find_db_match(rib_t1, rib_t2, db_matches)
            if db_match is None:
                logger.debug(f"    No DB match for '{rib_t1}' vs '{rib_t2}'")
                match_miss += 1
                continue

            match_id = db_match['id']
            t1_is_rib_t1 = _rib_t1_is_db_team1(rib_t1, db_match)
            print(f"    {rib_t1} vs {rib_t2} -> DB match {match_id}")

            for map_data in maps:
                map_number = map_data['map_number']
                map_name = map_data['map_name']
                rounds = map_data['rounds']

                if (match_id, map_number) in already_done:
                    total_skipped += 1
                    continue

                if not rounds:
                    continue

                # If rib team1 is our DB team2, flip side assignments
                if not t1_is_rib_t1:
                    for r in rounds:
                        side = r.get('winning_team_side')
                        if side == 1:
                            r['winning_team_side'] = 2
                        elif side == 2:
                            r['winning_team_side'] = 1
                        r['team1_economy'], r['team2_economy'] = \
                            r['team2_economy'], r['team1_economy']

                print(f"      Map {map_number} ({map_name}): {len(rounds)} rounds")

                if not args.dry_run:
                    saved = db.save_round_data(match_id, map_number, rounds)
                    total_rounds += saved
                    already_done.add((match_id, map_number))
                else:
                    total_rounds += len(rounds)

                total_maps += 1

            # Rate limit between series (scraper already throttles 0.6–1s per request)
            time.sleep(random.uniform(0.5, 1.0))

    print(f"\n=== Done ===")
    print(f"Maps processed: {total_maps} | skipped: {total_skipped} | DB miss: {match_miss}")
    print(f"Rounds {'(dry-run) ' if args.dry_run else ''}saved: {total_rounds}")


if __name__ == '__main__':
    main()
