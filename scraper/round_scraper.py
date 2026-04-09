"""
Round-level economy scraper for VLR.gg match economy pages.

Populates:
  - match_round_data  (round_num, winning_team_side, team1_economy, team2_economy)
  - match_map_halves  (atk_rounds_won, def_rounds_won per team per map)

URL pattern: https://www.vlr.gg/{match_id}/{slug}/?game={game_id}&tab=economy

Economy class mapping (VLR.gg definitions):
  ''   (empty text) + round 1 or 13 → 'pistol'
  ''   (empty text) + other round   → 'eco'       (0–5k)
  '$'                               → 'semi-eco'  (5–10k)
  '$$'                              → 'semi-buy'  (10–20k)
  '$$$'                             → 'full'      (20k+)
"""

import time
import sqlite3
import logging
import sys
import os
from typing import Optional, Tuple, List, Dict

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scraper.vlr_scraper import VLRScraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)

BASE_URL = 'https://www.vlr.gg'
REQUEST_DELAY = 1.5   # seconds between requests — be polite
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'valorant_stats.db')

DOLLAR_TO_ECON = {
    '$$$': 'full',
    '$$':  'semi-buy',
    '$':   'semi-eco',
    '':    None,   # needs round context: pistol (r1/r13) or eco
}


# ─────────────────────────────────────────────────────────────────────────────
# VLR page fetching (reuses VLRScraper request logic)
# ─────────────────────────────────────────────────────────────────────────────

_scraper = VLRScraper()


def _fetch(url: str) -> Optional[BeautifulSoup]:
    """Fetch a VLR.gg page and return a BeautifulSoup object, or None on error."""
    try:
        raw = _scraper._make_request(url)
        return BeautifulSoup(raw, 'html.parser')
    except Exception as e:
        log.warning(f'Failed to fetch {url}: {e}')
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Game ID → map order discovery
# ─────────────────────────────────────────────────────────────────────────────

def get_game_map_order(match_url: str) -> List[Tuple[str, str, str]]:
    """
    Fetch the match overview page and return:
        [(game_id, map_name, map_number_str), ...]
    Ordered by position on the page (map 1 first).
    Excludes the 'all' aggregate section.
    """
    soup = _fetch(f'{BASE_URL}{match_url}')
    if soup is None:
        return []

    results = []
    map_num = 1
    for section in soup.find_all('div', class_='vm-stats-game'):
        gid = section.get('data-game-id', '')
        if gid == 'all':
            continue

        map_name = 'Unknown'
        map_div = section.find('div', class_='map')
        if map_div:
            # e.g. "Pearl PICK 39:56" — take first word
            raw = map_div.get_text(separator=' ', strip=True)
            import re
            m = re.match(r'([A-Za-z]+)', raw)
            if m:
                map_name = m.group(1)

        results.append((gid, map_name, str(map_num)))
        map_num += 1

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Economy page parsing
# ─────────────────────────────────────────────────────────────────────────────

def _classify_econ(dollar_text: str, round_num: int) -> str:
    """Map VLR.gg dollar-symbol label to our econ class string."""
    if dollar_text in ('$$$', '$$', '$'):
        return DOLLAR_TO_ECON[dollar_text]
    # Empty text: pistol round (1, 13, or OT entry rounds 25, 27, ...) or eco
    if round_num == 1 or round_num == 13 or (round_num >= 25 and round_num % 2 == 1):
        return 'pistol'
    return 'eco'


def parse_economy_page(
    match_url: str,
    game_id: str,
    map_number: int,
) -> Optional[Dict]:
    """
    Fetch and parse the economy tab for one specific map (game).

    Returns:
    {
        'team1_name': str,
        'team2_name': str,
        'rounds': [
            {
                'round_num': int,
                'winner': 1 | 2,        # which team number won
                'winner_side': str,      # 'atk' or 'def'  (winner's perspective)
                'team1_side': str,       # 'atk' or 'def'
                'team2_side': str,
                'team1_econ': str,       # 'pistol'/'eco'/'semi-eco'/'semi-buy'/'full'
                'team2_econ': str,
                'team1_value': int,      # equipment value in credits
                'team2_value': int,
                'team1_bank': float,     # bank before round (k)
                'team2_bank': float,
            },
            ...
        ]
    }
    """
    econ_url = f'{BASE_URL}{match_url}?game={game_id}&tab=economy'
    soup = _fetch(econ_url)
    if soup is None:
        return None

    # Find the vm-stats-game section for this specific game_id
    section = soup.find('div', attrs={'data-game-id': game_id, 'class': 'vm-stats-game'})
    if section is None:
        log.warning(f'No vm-stats-game section for game_id={game_id}')
        return None

    # Find the round-by-round table (has round-num divs, not the summary table with th headers)
    round_table = None
    for table in section.find_all('table', class_='wf-table-inset'):
        if table.find(class_='round-num'):
            round_table = table
            break

    if round_table is None:
        log.warning(f'No round table for game_id={game_id}')
        return None

    # Extract team names from the label td (first td)
    tds = round_table.find_all('td')
    if not tds:
        return None

    label_td = tds[0]
    team_divs = label_td.find_all('div', class_='team')
    team1_name = team_divs[0].get_text(strip=True) if len(team_divs) > 0 else 'Team1'
    team2_name = team_divs[1].get_text(strip=True) if len(team_divs) > 1 else 'Team2'

    rounds = []
    for td in tds[1:]:  # Skip label td
        round_num_div = td.find(class_='round-num')
        if not round_num_div:
            continue

        try:
            round_num = int(round_num_div.get_text(strip=True))
        except ValueError:
            continue

        rnd_sqs = td.find_all('div', class_='rnd-sq')
        if len(rnd_sqs) < 2:
            continue

        banks = td.find_all('div', class_='bank')
        team1_bank = _parse_bank(banks[0].get_text(strip=True)) if len(banks) > 0 else 0.0
        team2_bank = _parse_bank(banks[1].get_text(strip=True)) if len(banks) > 1 else 0.0

        sq1 = rnd_sqs[0]
        sq2 = rnd_sqs[1]

        sq1_classes = sq1.get('class', [])
        sq2_classes = sq2.get('class', [])

        # Determine winner (exactly one of them should have mod-win)
        t1_won = 'mod-win' in sq1_classes
        t2_won = 'mod-win' in sq2_classes

        if t1_won:
            winner = 1
            winning_sq = sq1
        elif t2_won:
            winner = 2
            winning_sq = sq2
        else:
            # No winner marked — likely a forfeited/incomplete round, skip
            log.debug(f'  Round {round_num}: no winner marked, skipping')
            continue

        # Determine sides from the WINNER's rnd-sq
        if 'mod-ct' in winning_sq.get('class', []):
            winner_side = 'def'    # CT = defense in Valorant
        else:
            winner_side = 'atk'    # T  = attack

        # Loser is on opposite side
        loser_side = 'def' if winner_side == 'atk' else 'atk'

        team1_side = winner_side if winner == 1 else loser_side
        team2_side = winner_side if winner == 2 else loser_side

        # Economy classification
        team1_dollar = sq1.get_text(strip=True)
        team2_dollar = sq2.get_text(strip=True)
        team1_econ = _classify_econ(team1_dollar, round_num)
        team2_econ = _classify_econ(team2_dollar, round_num)

        # Equipment values (title attribute is credits spent as int string)
        try:
            team1_value = int(sq1.get('title', '0').replace(',', ''))
        except ValueError:
            team1_value = 0
        try:
            team2_value = int(sq2.get('title', '0').replace(',', ''))
        except ValueError:
            team2_value = 0

        rounds.append({
            'round_num':    round_num,
            'winner':       winner,
            'winner_side':  winner_side,
            'team1_side':   team1_side,
            'team2_side':   team2_side,
            'team1_econ':   team1_econ,
            'team2_econ':   team2_econ,
            'team1_value':  team1_value,
            'team2_value':  team2_value,
            'team1_bank':   team1_bank,
            'team2_bank':   team2_bank,
        })

    if not rounds:
        return None

    return {
        'team1_name': team1_name,
        'team2_name': team2_name,
        'map_number': map_number,
        'game_id':    game_id,
        'rounds':     rounds,
    }


def _parse_bank(text: str) -> float:
    """Parse '9.3k' → 9300.0, '0.2k' → 200.0, '15k' → 15000.0"""
    text = text.strip().lower()
    if not text:
        return 0.0
    try:
        if text.endswith('k'):
            return float(text[:-1]) * 1000
        return float(text)
    except ValueError:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Database wiring
# ─────────────────────────────────────────────────────────────────────────────

def save_round_data(conn: sqlite3.Connection, match_id: int, map_data: Dict) -> int:
    """
    Write parsed round data into match_round_data and match_map_halves.
    Returns number of rounds inserted.
    """
    cur = conn.cursor()
    map_number = map_data['map_number']
    rounds = map_data['rounds']

    # ── match_round_data ───────────────────────────────────────────────
    inserted = 0
    for r in rounds:
        try:
            cur.execute("""
                INSERT OR REPLACE INTO match_round_data
                    (match_id, map_number, round_num, winning_team_side,
                     team1_economy, team2_economy)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                match_id,
                map_number,
                r['round_num'],
                r['winner'],       # 1 or 2
                r['team1_econ'],
                r['team2_econ'],
            ))
            inserted += 1
        except sqlite3.IntegrityError:
            pass

    # ── match_map_halves (atk/def win counts per team) ─────────────────
    for team_num, team_name in [(1, map_data['team1_name']), (2, map_data['team2_name'])]:
        atk_wins = sum(
            1 for r in rounds
            if r['winner'] == team_num and r['team1_side' if team_num == 1 else 'team2_side'] == 'atk'
        )
        def_wins = sum(
            1 for r in rounds
            if r['winner'] == team_num and r['team1_side' if team_num == 1 else 'team2_side'] == 'def'
        )
        total = len(rounds)
        try:
            cur.execute("""
                INSERT OR REPLACE INTO match_map_halves
                    (match_id, map_number, team_name, atk_rounds_won, def_rounds_won, total_rounds)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (match_id, map_number, team_name, atk_wins, def_wins, total))
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    return inserted


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

def get_already_scraped(conn: sqlite3.Connection) -> set:
    """Return set of (match_id, map_number) tuples already in match_round_data."""
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT match_id, map_number FROM match_round_data")
    return set(cur.fetchall())


def scrape_all_rounds(
    db_path: str = DB_PATH,
    limit: Optional[int] = None,
    skip_existing: bool = True,
    delay: float = REQUEST_DELAY,
) -> Dict:
    """
    Main entry point: iterate over all matches, scrape economy data for each map.

    Args:
        db_path: path to SQLite database
        limit: stop after this many matches (for testing)
        skip_existing: skip (match_id, map_number) combos already in DB
        delay: seconds to wait between HTTP requests

    Returns summary stats dict.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT id, match_url, team1, team2 FROM matches")
    matches = cur.fetchall()
    if limit:
        matches = matches[:limit]

    already_done = get_already_scraped(conn) if skip_existing else set()

    stats = {
        'matches_processed': 0,
        'maps_scraped': 0,
        'rounds_inserted': 0,
        'maps_skipped_existing': 0,
        'maps_failed': 0,
    }

    for match_id, match_url, team1, team2 in matches:
        log.info(f'Match {match_id}: {team1} vs {team2}')

        # Step 1: get game_id → map_number mapping
        game_map_order = get_game_map_order(match_url)
        if not game_map_order:
            log.warning(f'  No game IDs found for match {match_id}')
            stats['matches_processed'] += 1
            continue
        time.sleep(delay)

        # Step 2: for each map, scrape economy
        for game_id, map_name, map_num_str in game_map_order:
            map_number = int(map_num_str)

            if skip_existing and (match_id, map_number) in already_done:
                log.debug(f'  Map {map_number} ({map_name}) already scraped, skipping')
                stats['maps_skipped_existing'] += 1
                continue

            log.info(f'  Map {map_number} ({map_name}, game_id={game_id})')

            map_data = parse_economy_page(match_url, game_id, map_number)
            time.sleep(delay)

            if map_data is None:
                log.warning(f'  Failed to parse map {map_number}')
                stats['maps_failed'] += 1
                continue

            n = save_round_data(conn, match_id, map_data)
            log.info(f'  → {n} rounds inserted')
            stats['rounds_inserted'] += n
            stats['maps_scraped'] += 1

        stats['matches_processed'] += 1

    conn.close()
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Quick test against one known match
# ─────────────────────────────────────────────────────────────────────────────

def test_single_match(match_url: str = '/644717/bbl-esports-vs-eternal-fire-vct-2026-emea-stage-1-w2'):
    """Parse a single match and print results — for development/testing."""
    print(f'\nTest: {match_url}')
    game_map_order = get_game_map_order(match_url)
    print(f'Found {len(game_map_order)} maps: {[(g, m) for g, m, _ in game_map_order]}')

    for game_id, map_name, map_num_str in game_map_order:
        map_number = int(map_num_str)
        print(f'\nMap {map_number}: {map_name} (game_id={game_id})')
        time.sleep(1.0)

        map_data = parse_economy_page(match_url, game_id, map_number)
        if not map_data:
            print('  FAILED to parse')
            continue

        rounds = map_data['rounds']
        print(f'  Teams: {map_data["team1_name"]} vs {map_data["team2_name"]}')
        print(f'  Rounds parsed: {len(rounds)}')
        print(f'  Score: {sum(1 for r in rounds if r["winner"]==1)}-{sum(1 for r in rounds if r["winner"]==2)}')

        # Print first 5 rounds
        print(f'\n  {"Rnd":>4} {"Winner":>8} {"T1side":>8} {"T2side":>8} {"T1econ":>10} {"T2econ":>10} {"T1val":>8} {"T2val":>8}')
        print('  ' + '-' * 70)
        for r in rounds[:8]:
            print(f'  {r["round_num"]:>4} '
                  f'{"T1" if r["winner"]==1 else "T2":>8} '
                  f'{r["team1_side"]:>8} '
                  f'{r["team2_side"]:>8} '
                  f'{r["team1_econ"]:>10} '
                  f'{r["team2_econ"]:>10} '
                  f'{r["team1_value"]:>8} '
                  f'{r["team2_value"]:>8}')

        # Econ matchup summary
        from collections import Counter
        matchups = Counter()
        for r in rounds:
            t1e = r['team1_econ']
            t2e = r['team2_econ']
            winner = 'T1' if r['winner'] == 1 else 'T2'
            matchups[(t1e, t2e, winner)] += 1

        print(f'\n  Eco matchup summary:')
        print(f'  {"T1_econ":>10} {"T2_econ":>10} {"Winner":>8} {"Count":>6}')
        for (t1e, t2e, w), cnt in sorted(matchups.items(), key=lambda x: -x[1]):
            print(f'  {t1e:>10} {t2e:>10} {w:>8} {cnt:>6}')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Scrape round-level economy data from VLR.gg')
    parser.add_argument('--test', action='store_true', help='Run test on one known match')
    parser.add_argument('--limit', type=int, default=None, help='Max matches to process')
    parser.add_argument('--delay', type=float, default=REQUEST_DELAY, help='Seconds between requests')
    parser.add_argument('--no-skip', action='store_true', help='Re-scrape already-done maps')
    args = parser.parse_args()

    if args.test:
        test_single_match()
    else:
        print(f'Starting full scrape (limit={args.limit}, delay={args.delay}s)')
        result = scrape_all_rounds(
            limit=args.limit,
            skip_existing=not args.no_skip,
            delay=args.delay,
        )
        print('\nScrape complete:')
        for k, v in result.items():
            print(f'  {k}: {v}')
