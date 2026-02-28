# scripts/populate_round_data.py
"""
Populate match_round_data table with round-level economy data from rib.gg.

Strategy:
  1. For each VCT 2026 kickoff event, enumerate all series via rib.gg event page.
  2. For each series, fetch the series overview to extract:
     - Team names (to cross-reference with our matches table)
     - Per-map rib.gg match IDs
  3. Find the matching match_id in our DB by fuzzy team-name comparison.
  4. For each map, fetch ?tab=economy and parse round data.
  5. Save to match_round_data.

Run once; already-populated maps are skipped (UNIQUE constraint).
Rate limiting: ~1–2s between requests (scraper has built-in 0.6–1.0s throttle).

Usage: python scripts/populate_round_data.py [--dry-run] [--event-id ID]
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
    """Lowercase, collapse spaces, strip non-alphanumeric except spaces."""
    return re.sub(r'[^a-z0-9 ]', '', name.lower()).strip()


def _fuzzy_match(rib_name: str, db_name: str) -> bool:
    """True if the two team names are close enough to be the same team."""
    rn = _normalize(rib_name)
    dn = _normalize(db_name)
    if not rn or not dn:
        return False
    return rn == dn or rn in dn or dn in rn or rn[:6] == dn[:6]


def _get_already_populated(db_path: str) -> set:
    """Return set of (match_id, map_number) that already have round data."""
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT match_id, map_number FROM match_round_data')
    result = set(cursor.fetchall())
    conn.close()
    return result


def _get_2026_matches(db_path: str) -> list:
    """Return all 2026 VCT matches: [{id, match_url, team1, team2}]."""
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.id, m.match_url, m.team1, m.team2
        FROM matches m
        JOIN vct_events ve ON m.event_id = ve.id
        WHERE ve.year = 2026
        ORDER BY m.id
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [{'id': r[0], 'match_url': r[1], 'team1': r[2], 'team2': r[3]} for r in rows]


def _find_db_match(rib_t1: str, rib_t2: str, db_matches: list) -> dict | None:
    """Find a matching DB match by fuzzy team-name comparison."""
    for m in db_matches:
        t1 = m['team1'] or ''
        t2 = m['team2'] or ''
        if (_fuzzy_match(rib_t1, t1) and _fuzzy_match(rib_t2, t2)) or \
           (_fuzzy_match(rib_t1, t2) and _fuzzy_match(rib_t2, t1)):
            return m
    return None


def _is_team1_in_match(rib_t1: str, db_match: dict) -> bool:
    """Return True if rib_t1 corresponds to db_match.team1."""
    return _fuzzy_match(rib_t1, db_match['team1'] or '')


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Populate match_round_data from rib.gg')
    parser.add_argument('--dry-run', action='store_true',
                        help='Fetch and parse but do not write to DB')
    parser.add_argument('--event-id', default=None,
                        help='Process only this rib.gg event ID (e.g. 6242)')
    parser.add_argument('--dump-first', action='store_true',
                        help='Print raw __NEXT_DATA__ of first economy page and exit (debug)')
    args = parser.parse_args()

    db = Database(Config.DATABASE_PATH)
    db._init_db()  # ensure match_round_data table exists

    scraper = RibScraper(database=db)
    db_matches = _get_2026_matches(Config.DATABASE_PATH)
    already_done = _get_already_populated(Config.DATABASE_PATH)

    print(f"DB has {len(db_matches)} 2026 matches, {len(already_done)} (match,map) pairs already populated.")

    events = scraper.VCT_2026_KICKOFF_EVENTS
    if args.event_id:
        events = [e for e in events if e['id'] == args.event_id]
        if not events:
            print(f"Event ID {args.event_id} not found in VCT_2026_KICKOFF_EVENTS.")
            return

    total_rounds_saved = 0
    total_maps_processed = 0
    total_maps_skipped = 0
    match_miss = 0

    for event in events:
        print(f"\n=== Event: {event['name']} (rib.gg id={event['id']}) ===")
        all_series = scraper._get_event_series_slugs(event['slug'], event['id'])
        if not all_series:
            print(f"  No series found (rate-limit or empty event?)")
            continue
        print(f"  {len(all_series)} series found.")

        for s_idx, (s_slug, s_id) in enumerate(all_series, 1):
            print(f"  [{s_idx}/{len(all_series)}] Series {s_id} ({s_slug[:40]})")

            series_info = scraper._get_series_info(s_slug, s_id)
            if not series_info:
                print(f"    Could not fetch series info, skipping.")
                continue

            rib_t1 = series_info.get('team1_name', '')
            rib_t2 = series_info.get('team2_name', '')
            maps = series_info.get('maps', [])

            if not maps:
                print(f"    No map IDs found in series, skipping.")
                continue

            # Cross-reference with our DB
            db_match = _find_db_match(rib_t1, rib_t2, db_matches)
            if db_match is None:
                logger.debug(f"    No DB match for '{rib_t1}' vs '{rib_t2}'")
                match_miss += 1
                continue

            match_id = db_match['id']
            t1_is_rib_t1 = _is_team1_in_match(rib_t1, db_match)

            print(f"    Matched DB match {match_id}: {db_match['team1']} vs {db_match['team2']}")

            for map_idx, (map_name, score, rib_map_id) in enumerate(maps, 1):
                map_number = map_idx

                if (match_id, map_number) in already_done:
                    print(f"      Map {map_number} ({map_name}): already populated, skipping.")
                    total_maps_skipped += 1
                    continue

                print(f"      Map {map_number} ({map_name}, rib_map_id={rib_map_id}): fetching economy...")

                if args.dump_first:
                    # Debug: dump raw content and exit
                    url = f"https://www.rib.gg/series/{s_slug}/{s_id}?match={rib_map_id}&tab=economy"
                    raw = scraper._make_request(url, timeout=90)
                    if raw:
                        import re as _re
                        text = raw.decode('utf-8', errors='replace')
                        nd_match = _re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, _re.DOTALL)
                        if nd_match:
                            print("=== __NEXT_DATA__ (first 4000 chars) ===")
                            print(nd_match.group(1)[:4000])
                        else:
                            print("No __NEXT_DATA__ found. First 2000 chars of page:")
                            print(text[:2000])
                    return

                rounds = scraper.get_map_economy(s_slug, s_id, rib_map_id)

                if not rounds:
                    print(f"        No economy data parsed.")
                    total_maps_processed += 1
                    continue

                # If rib_t1 is db team2, flip winning_team_side
                if not t1_is_rib_t1:
                    for r in rounds:
                        side = r.get('winning_team_side')
                        if side == 1:
                            r['winning_team_side'] = 2
                        elif side == 2:
                            r['winning_team_side'] = 1
                        # Flip economy too
                        r['team1_economy'], r['team2_economy'] = r['team2_economy'], r['team1_economy']

                print(f"        {len(rounds)} rounds parsed.")

                if not args.dry_run:
                    saved = db.save_round_data(match_id, map_number, rounds)
                    total_rounds_saved += saved
                    already_done.add((match_id, map_number))
                else:
                    total_rounds_saved += len(rounds)

                total_maps_processed += 1

            # Rate limit between series
            delay = random.uniform(1.0, 2.0)
            time.sleep(delay)

    print(f"\n=== Done ===")
    print(f"Maps processed: {total_maps_processed}")
    print(f"Maps skipped (already done): {total_maps_skipped}")
    print(f"DB matches not found for rib.gg series: {match_miss}")
    print(f"Rounds {'would be ' if args.dry_run else ''}saved: {total_rounds_saved}")
    if args.dry_run:
        print("(dry-run: nothing was written to DB)")


if __name__ == '__main__':
    main()
