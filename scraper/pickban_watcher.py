"""
scraper/pickban_watcher.py

Polls VLR.gg for upcoming matches and scrapes pick/ban results.

For each upcoming match, monitors the match page until pick/ban is complete
(all maps determined), then returns structured pick/ban data for the TheoEngine.

Pick/ban data format:
    {
        'team_a': str,
        'team_b': str,
        'maps': [
            {'map': str, 'team_a_side': 'atk'|'def'|None},
            ...
        ],
        'match_url': str,
    }

Starting sides may be None if the match hasn't knifed yet.
Use TheoEngine.series_theo_no_sides() in that case.
"""

import re
import time
import logging
import random
import urllib.request
import urllib.error
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

VLR_BASE = 'https://www.vlr.gg'

_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
]

RATE_LIMIT_DELAY = 2.0
MAX_RETRIES = 3
BACKOFF = 20.0


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

def _fetch(url: str) -> Optional[bytes]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0:
            time.sleep(BACKOFF)
        time.sleep(RATE_LIMIT_DELAY + random.uniform(0, 0.5))
        req = urllib.request.Request(url, headers={
            'User-Agent': random.choice(_USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
        try:
            resp = opener.open(req, timeout=30)
            return resp.read()
        except urllib.error.HTTPError as e:
            last_err = f'HTTP {e.code}'
            if e.code in (429, 500, 502, 503, 504):
                continue
            if e.code == 404:
                return None
            raise
        except (urllib.error.URLError, OSError) as e:
            last_err = str(e)
            continue
    logger.warning('Failed to fetch %s: %s', url, last_err)
    return None


# --------------------------------------------------------------------------- #
# Upcoming match discovery
# --------------------------------------------------------------------------- #

def get_upcoming_matches(max_matches: int = 20) -> list:
    """
    Scrape VLR.gg/matches for upcoming VCT matches.

    Returns list of dicts:
        [{'match_url': str, 'team_a': str, 'team_b': str, 'event': str}, ...]
    """
    html = _fetch(f'{VLR_BASE}/matches')
    if not html:
        logger.warning('Could not fetch /matches page')
        return []

    soup = BeautifulSoup(html, 'html.parser')
    results = []

    for item in soup.find_all('a', class_=re.compile(r'match-item')):
        href = item.get('href', '')
        if not href or '/matches' in href:
            continue

        # Team names
        teams = item.find_all('div', class_=re.compile(r'match-item-vs-team-name'))
        if len(teams) < 2:
            continue
        team_a = teams[0].get_text(strip=True)
        team_b = teams[1].get_text(strip=True)
        if not team_a or not team_b or team_a == 'TBD' or team_b == 'TBD':
            continue

        # Event name (for filtering to VCT only)
        event_div = item.find('div', class_=re.compile(r'match-item-event'))
        event = event_div.get_text(strip=True) if event_div else ''

        results.append({
            'match_url': href if href.startswith('/') else f'/{href}',
            'team_a': team_a,
            'team_b': team_b,
            'event': event,
        })

        if len(results) >= max_matches:
            break

    logger.info('Found %d upcoming matches on VLR.gg', len(results))
    return results


# --------------------------------------------------------------------------- #
# Pick/ban parsing
# --------------------------------------------------------------------------- #

def get_pickban(match_url: str) -> Optional[dict]:
    """
    Scrape a VLR.gg match page and return pick/ban data if available.

    Returns None if pick/ban has not started or cannot be parsed.

    Return format:
        {
            'team_a': str,
            'team_b': str,
            'maps': [{'map': str, 'team_a_side': 'atk'|'def'|None}, ...],
            'match_url': str,
            'complete': bool,   # True if all maps determined
        }
    """
    url = f'{VLR_BASE}{match_url}'
    html = _fetch(url)
    if not html:
        return None

    soup = BeautifulSoup(html, 'html.parser')

    # Team names from the match header
    team_divs = soup.find_all('div', class_=re.compile(r'match-header-link-name'))
    if len(team_divs) < 2:
        return None
    team_a = team_divs[0].get_text(strip=True)
    team_b = team_divs[1].get_text(strip=True)

    # Pick/ban table: div.match-vod-row or div.vm-pick-bans
    pickban_section = (
        soup.find('div', class_=re.compile(r'vm-pick-bans'))
        or soup.find('div', class_=re.compile(r'match-maps'))
    )

    maps = []

    # Primary: parse map stats game nav — each played/picked map appears here
    # This is populated once pick/ban is complete
    for item in soup.find_all('div', class_=re.compile(r'vm-stats-gamesnav-item')):
        classes = item.get('class', [])
        if 'mod-disabled' in classes or 'mod-all' in classes:
            continue
        game_id = item.get('data-game-id')
        if not game_id or game_id == 'all':
            continue
        text = item.get_text(strip=True)
        # text like "1Abyss" or "2Haven"
        m = re.match(r'^\d+(.+)', text)
        if m:
            map_name = m.group(1).strip()
            maps.append({'map': map_name, 'team_a_side': None, 'game_id': game_id})

    # Try to fill in starting sides from the economy/stats tabs
    for map_entry in maps:
        game_id = map_entry.get('game_id')
        game_div = soup.find('div', attrs={'data-game-id': game_id, 'class': 'vm-stats-game'})
        if not game_div:
            continue
        side = _parse_starting_side(game_div, team_a)
        if side:
            map_entry['team_a_side'] = side

    # Clean up internal game_id field
    for m in maps:
        m.pop('game_id', None)

    if not maps:
        return None

    return {
        'team_a': team_a,
        'team_b': team_b,
        'maps': maps,
        'match_url': match_url,
        'complete': len(maps) >= 2,
    }


def _parse_starting_side(game_div, team_a: str) -> Optional[str]:
    """
    Determine which side team_a started on for this map game div.

    Looks for the score summary row that shows which team was atk/def in
    the first half.  Returns 'atk', 'def', or None if not determinable.
    """
    # The team summary table has rows with class mod-t (attack) / mod-ct (defense)
    # Look for the team name and which side they're labeled on
    for row in game_div.find_all('tr'):
        team_cell = row.find('td', class_=re.compile(r'mod-left|team'))
        if not team_cell:
            continue
        cell_text = team_cell.get_text(strip=True)
        if team_a.lower() not in cell_text.lower():
            continue
        # Found team_a's row — check side class
        side_cells = row.find_all('td', class_=re.compile(r'mod-t\b'))
        if side_cells:
            # Team is listed under atk (T side) first
            return 'atk'
        side_cells_ct = row.find_all('td', class_=re.compile(r'mod-ct\b'))
        if side_cells_ct:
            return 'def'
    return None


# --------------------------------------------------------------------------- #
# Blocking watcher — polls until pick/ban complete
# --------------------------------------------------------------------------- #

def wait_for_pickban(
    match_url: str,
    poll_interval: int = 30,
    timeout: int = 600,
) -> Optional[dict]:
    """
    Poll a match page until pick/ban is complete or timeout is reached.

    Args:
        match_url:     VLR.gg match path (e.g. '/596399/...')
        poll_interval: Seconds between polls.
        timeout:       Give up after this many seconds.

    Returns pick/ban dict or None on timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = get_pickban(match_url)
        if result and result.get('complete'):
            logger.info(
                'Pick/ban complete for %s: %s vs %s — maps: %s',
                match_url, result['team_a'], result['team_b'],
                [m['map'] for m in result['maps']],
            )
            return result
        remaining = int(deadline - time.time())
        logger.info(
            'Pick/ban not ready for %s — retrying in %ds (%ds remaining)',
            match_url, poll_interval, remaining,
        )
        time.sleep(poll_interval)

    logger.warning('Timed out waiting for pick/ban on %s', match_url)
    return None
