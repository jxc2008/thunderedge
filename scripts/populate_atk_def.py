# scripts/populate_atk_def.py
"""
Populate match_map_halves table with attack/defense round data.

For each match in 2026 events (that doesn't already have data in match_map_halves),
scrapes VLR.gg match pages for halftime scores and saves the attack/defense breakdown.
"""

import sys
import os
import time
import random
import logging
import sqlite3

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import Database
from scraper.vlr_scraper import VLRScraper
from config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_unpopulated_matches(db_path: str, year: int = 2026):
    """Get all match_ids from year events that don't yet have data in match_map_halves."""
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.id, m.match_url, m.team1, m.team2
        FROM matches m
        JOIN vct_events ve ON m.event_id = ve.id
        WHERE ve.year = ?
          AND m.id NOT IN (SELECT DISTINCT match_id FROM match_map_halves)
        ORDER BY m.id
    ''', (year,))
    rows = cursor.fetchall()
    conn.close()
    return [{'id': r[0], 'match_url': r[1], 'team1': r[2], 'team2': r[3]} for r in rows]


def main():
    db = Database(Config.DATABASE_PATH)
    # Ensure table exists
    db._init_db()

    scraper = VLRScraper(database=db)

    matches = get_unpopulated_matches(Config.DATABASE_PATH, year=2026)
    total = len(matches)
    if total == 0:
        print("No unpopulated matches found for 2026. Done.")
        return

    print(f"Found {total} matches to process.")

    maps_saved = 0
    errors = 0

    for idx, match in enumerate(matches, start=1):
        match_id = match['id']
        match_url = match['match_url']
        print(f"[{idx}/{total}] Processing match {match_id}: {match_url} ...")

        try:
            result = scraper.get_match_halftime_scores(match_url)
        except Exception as e:
            logger.error(f"  Error scraping {match_url}: {e}")
            errors += 1
            continue

        if not result or not result.get('maps'):
            print(f"  No halftime data found, skipping.")
            continue

        for map_data in result['maps']:
            map_number = map_data['map_number']
            map_name = map_data['map_name']

            # Save team1 data
            db.save_match_map_halves(
                match_id=match_id,
                map_number=map_number,
                map_name=map_name,
                team_name=map_data['team1_name'],
                atk_rounds=map_data['team1_atk'],
                def_rounds=map_data['team1_def'],
            )
            # Save team2 data
            db.save_match_map_halves(
                match_id=match_id,
                map_number=map_number,
                map_name=map_name,
                team_name=map_data['team2_name'],
                atk_rounds=map_data['team2_atk'],
                def_rounds=map_data['team2_def'],
            )
            maps_saved += 1

        print(f"  Saved {len(result['maps'])} maps.")

        # Rate limiting: 1-2 seconds between requests (the scraper itself also has built-in throttle)
        if idx < total:
            delay = random.uniform(1.0, 2.0)
            time.sleep(delay)

    print(f"\nDone. {idx}/{total} matches processed, {maps_saved} maps saved, {errors} errors.")


if __name__ == '__main__':
    main()
