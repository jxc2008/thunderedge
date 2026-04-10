# scraper/halves_scraper.py
"""
Scrapes VLR.gg economy tabs to populate the match_map_halves table.

For each match, fetches: https://www.vlr.gg/{vlr_id}/{slug}/?game=all&tab=economy
Parses the round-by-round bank table to compute:
  - atk_rounds_won: rounds won while on T side
  - def_rounds_won: rounds won while on CT side
  - total_rounds: total rounds played on the map

Then writes one row per (match_id, map_number, team_name) into match_map_halves.
"""

import re
import time
import logging
import random
import sqlite3
import urllib.request
import urllib.error
from typing import Optional

from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

VLR_BASE = 'https://www.vlr.gg'

_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
]

RATE_LIMIT_DELAY = 1.5      # seconds between requests
BACKOFF_429 = 30.0          # seconds to wait on 429 / 503
MAX_RETRIES = 4


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #

def _build_headers() -> dict:
    return {
        'User-Agent': random.choice(_USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
    }


def _fetch(url: str) -> Optional[bytes]:
    """Fetch URL with rate-limiting and retry on 429/503. Returns None on permanent failure."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last_err = None

    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0:
            wait = BACKOFF_429 if attempt == 1 else BACKOFF_429 * attempt
            logger.info(f'Retry {attempt}/{MAX_RETRIES} in {wait:.0f}s: {last_err}')
            time.sleep(wait)

        # Base rate-limit throttle between every request
        time.sleep(RATE_LIMIT_DELAY + random.uniform(0, 0.5))

        req = urllib.request.Request(url, headers=_build_headers())
        try:
            resp = opener.open(req, timeout=45)
            return resp.read()
        except urllib.error.HTTPError as e:
            last_err = f'HTTP {e.code}'
            if e.code in (429, 503, 502, 504):
                continue
            if e.code == 404:
                logger.warning(f'404 for {url}')
                return None
            raise
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            last_err = str(e)
            err_lo = last_err.lower()
            if any(t in err_lo for t in ('timed out', 'timeout', 'reset', 'connection', '10054', 'eof')):
                continue
            raise

    logger.error(f'Gave up on {url} after {MAX_RETRIES + 1} attempts: {last_err}')
    return None


# --------------------------------------------------------------------------- #
# HTML parsing
# --------------------------------------------------------------------------- #

def _parse_map_nav(soup: BeautifulSoup) -> dict:
    """
    Returns {game_id: {'map_number': int, 'map_name': str}} for each played map.
    Skips nav items with 'mod-disabled' (map not played).
    """
    result = {}
    for item in soup.find_all('div', class_=re.compile(r'vm-stats-gamesnav-item')):
        classes = item.get('class', [])
        if 'mod-disabled' in classes or 'mod-all' in classes:
            continue
        game_id = item.get('data-game-id')
        if not game_id or game_id == 'all':
            continue
        text = item.get_text(strip=True)
        m = re.match(r'^(\d+)(.+)', text)
        if m:
            result[game_id] = {
                'map_number': int(m.group(1)),
                'map_name': m.group(2).strip(),
            }
    return result


def _parse_game_halves(game_div) -> Optional[list]:
    """
    Parse one vm-stats-game div and return:
      [ {'team_name': str, 'atk_rounds_won': int, 'def_rounds_won': int, 'total_rounds': int}, ... ]
    Returns None if the section cannot be parsed.
    """
    tables = game_div.find_all('table', class_='wf-table-inset')
    # We need the round-by-round bank table (second wf-table-inset in the section)
    bank_table = None
    for t in tables:
        # The bank table has a 'round-num' div inside
        if t.find('div', class_='round-num'):
            bank_table = t
            break
    if bank_table is None:
        return None

    # Extract team names (in order) from the first <td>
    first_td = bank_table.find('td')
    if first_td is None:
        return None
    team_divs = first_td.find_all('div', class_='team')
    if len(team_divs) < 2:
        return None
    team_names = [d.get_text(strip=True) for d in team_divs]

    # Accumulate wins per team index
    atk_wins = [0, 0]
    def_wins = [0, 0]
    total_rounds = 0

    all_tds = bank_table.find_all('td')
    for td in all_tds[1:]:  # skip first td (team labels)
        round_num_div = td.find('div', class_='round-num')
        if not round_num_div:
            continue
        try:
            round_num = int(round_num_div.get_text(strip=True))
        except ValueError:
            continue

        rnd_sqs = td.find_all('div', class_=re.compile(r'rnd-sq'))
        if len(rnd_sqs) < 2:
            continue

        total_rounds = max(total_rounds, round_num)

        for team_idx in range(2):
            sq = rnd_sqs[team_idx]
            sq_classes = sq.get('class', [])
            if 'mod-win' not in sq_classes:
                continue
            if 'mod-t' in sq_classes:
                atk_wins[team_idx] += 1
            elif 'mod-ct' in sq_classes:
                def_wins[team_idx] += 1

    if total_rounds == 0:
        return None

    return [
        {
            'team_name': team_names[i],
            'atk_rounds_won': atk_wins[i],
            'def_rounds_won': def_wins[i],
            'total_rounds': total_rounds,
        }
        for i in range(2)
    ]


def parse_economy_page(html: bytes, db_match_id: int) -> list:
    """
    Parse an economy page's HTML and return list of row dicts for match_map_halves.
    Each dict has: match_id, map_number, map_name, team_name,
                   atk_rounds_won, def_rounds_won, total_rounds
    """
    soup = BeautifulSoup(html, 'html.parser')
    map_nav = _parse_map_nav(soup)

    rows = []
    for game_id, map_info in map_nav.items():
        game_div = soup.find('div', attrs={'data-game-id': game_id, 'class': 'vm-stats-game'})
        if game_div is None:
            logger.warning(f'  game div not found for game_id={game_id}')
            continue

        halves = _parse_game_halves(game_div)
        if halves is None:
            logger.warning(f'  could not parse halves for game_id={game_id}')
            continue

        for team_row in halves:
            rows.append({
                'match_id': db_match_id,
                'map_number': map_info['map_number'],
                'map_name': map_info['map_name'],
                'team_name': team_row['team_name'],
                'atk_rounds_won': team_row['atk_rounds_won'],
                'def_rounds_won': team_row['def_rounds_won'],
                'total_rounds': team_row['total_rounds'],
            })

    return rows


# --------------------------------------------------------------------------- #
# Database helpers
# --------------------------------------------------------------------------- #

def _get_matches(db_path: str, limit: int) -> list:
    """Return list of (db_id, match_url) for matches not yet in match_map_halves."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('''
        SELECT id, match_url
        FROM matches
        WHERE id NOT IN (SELECT DISTINCT match_id FROM match_map_halves)
        ORDER BY id
        LIMIT ?
    ''', (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def _insert_rows(db_path: str, rows: list):
    """Insert parsed rows into match_map_halves, skipping duplicates."""
    if not rows:
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executemany('''
        INSERT OR IGNORE INTO match_map_halves
            (match_id, map_number, map_name, team_name,
             atk_rounds_won, def_rounds_won, total_rounds)
        VALUES
            (:match_id, :map_number, :map_name, :team_name,
             :atk_rounds_won, :def_rounds_won, :total_rounds)
    ''', rows)
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------- #
# Main runner
# --------------------------------------------------------------------------- #

def run(db_path: str, limit: int = 50):
    """
    Scrape the first `limit` unscraped matches and write results to match_map_halves.
    """
    matches = _get_matches(db_path, limit)
    logger.info(f'Found {len(matches)} unscraped matches (limit={limit})')

    total_rows = 0
    skipped = 0

    for db_id, match_url in matches:
        # Build the economy URL from the stored match_url slug
        # match_url looks like: /427991/evil-geniuses-vs-loud-champions-tour-2025-americas-kickoff-ur1
        url = f'{VLR_BASE}{match_url}/?game=all&tab=economy'
        logger.info(f'Scraping match db_id={db_id}: {url}')

        html = _fetch(url)
        if html is None:
            logger.warning(f'  Skipping match {db_id} (fetch failed)')
            skipped += 1
            continue

        rows = parse_economy_page(html, db_id)
        if not rows:
            logger.warning(f'  No rows parsed for match {db_id}')
            skipped += 1
            continue

        _insert_rows(db_path, rows)
        maps_found = len(rows) // 2
        total_rows += len(rows)
        logger.info(f'  Inserted {len(rows)} rows ({maps_found} maps) for match {db_id}')

    logger.info(
        f'Done. Inserted {total_rows} rows total. '
        f'Skipped {skipped}/{len(matches)} matches.'
    )


if __name__ == '__main__':
    import sys
    import os
    import argparse

    parser = argparse.ArgumentParser(description='Scrape VLR.gg economy tabs for half scores')
    parser.add_argument('--db', type=str, default=None,
                        help='Path to valorant_stats.db (default: auto-detect from project root)')
    parser.add_argument('--limit', type=int, default=500,
                        help='Max number of unscraped matches to process (default: 500)')
    args = parser.parse_args()

    if args.db:
        db_path = args.db
    else:
        # Default: look for DB in the main thunderedge repo, not the worktree
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Try going up until we find a data/valorant_stats.db
        search = script_dir
        db_path = None
        for _ in range(5):
            candidate = os.path.join(search, 'data', 'valorant_stats.db')
            if os.path.exists(candidate):
                db_path = candidate
                break
            search = os.path.dirname(search)
        if not db_path:
            # Hard fallback to main repo location
            db_path = r'C:\Users\josep\OneDrive\Desktop\Thunderedge\thunderedge\data\valorant_stats.db'

    logger.info(f'Using DB: {db_path}')
    run(db_path, limit=args.limit)
