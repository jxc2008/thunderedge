# scraper/rib_scraper.py
"""
RIB.GG scraper for Valorant player statistics.
Primary data source for PrizePicks analysis (VLR.gg IP-banned).

Lookup priority for every player:
  1. Full player_data_cache (player_data_cache / player_data_cache_challengers table)
  2. DB match data (player_map_stats / player_event_stats tables from populate scripts)
  3. Live rib.gg scrape

URL patterns:
  Event page:  https://www.rib.gg/events/{slug}/{id}
  Series page: https://www.rib.gg/series/{slug}/{id}          ← plain URL has Head-to-Head map IDs
  Per-map:     https://www.rib.gg/series/{slug}/{id}?match={match_id}&tab=player-stats
"""
import re
import time
import json
import random
import logging
import threading
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0',
]

_RETRY_BACKOFFS = [8, 20, 45]


class RibScraper:
    BASE_URL = "https://www.rib.gg"

    VCT_2026_KICKOFF_EVENTS = [
        {'name': 'VCT 2026: Americas Kickoff', 'slug': 'vct-2026-americas-kickoff',   'id': '6242', 'region': 'Americas', 'tier': 1},
        {'name': 'VCT 2026: EMEA Kickoff',     'slug': 'vct-2026-emea-kickoff',       'id': '6240', 'region': 'EMEA',     'tier': 1},
        {'name': 'VCT 2026: Pacific Kickoff',  'slug': 'vct-2026-pacific-kickoff',    'id': '6244', 'region': 'Pacific',  'tier': 1},
        {'name': 'VCT 2026: China Kickoff',    'slug': 'vct-2026-china-kickoff',      'id': '6246', 'region': 'China',    'tier': 1},
    ]

    # VCL Challengers 2026 events
    CHALLENGERS_2026_EVENTS = [
        {'name': 'Challengers 2026: NA ACE Stage 1',      'slug': 'challengers-league-2026-north-america-ace-stage-1', 'id': '6272', 'region': 'Americas', 'tier': 2},
        {'name': 'Challengers 2026: Brazil Stage 1',       'slug': 'challengers-2026-brazil-gamers-club-stage-1',       'id': '6356', 'region': 'Americas', 'tier': 2},
        {'name': 'Challengers 2026: LATAM North Stage 1',  'slug': 'challengers-2026-latam-north-ace-stage-1',          'id': '6338', 'region': 'Americas', 'tier': 2},
        {'name': 'Challengers 2026: LATAM South Stage 1',  'slug': 'challengers-2026-latam-south-ace-stage-1',          'id': '6333', 'region': 'Americas', 'tier': 2},
        {'name': 'Challengers 2026: DACH Stage 1',         'slug': 'challengers-league-2026-dach-evolution-split-1',    'id': '6266', 'region': 'EMEA',     'tier': 2},
        {'name': 'Challengers 2026: Japan Split 1',        'slug': 'challengers-league-2026-japan-split-1',             'id': '6363', 'region': 'Pacific',  'tier': 2},
        {'name': 'Challengers 2026: Turkiye Kickoff',      'slug': 'challengers-2026-turkiye-birlik-kickoff',           'id': '6293', 'region': 'EMEA',     'tier': 2},
        {'name': 'Challengers 2026: MENA Kickoff',         'slug': 'challengers-league-2026-mena-resilience-kickoff',   'id': '6300', 'region': 'MENA',     'tier': 2},
    ]

    # Game Changers 2026 events
    GC_2026_EVENTS = [
        {'name': 'Game Changers 2026: EMEA Stage 1',       'slug': 'game-changers-2026-emea-stage-1',                   'id': '6348', 'region': 'EMEA',     'tier': 3},
        {'name': 'Game Changers 2026: EMEA Kickoff',       'slug': 'game-changers-2026-emea-kickoff',                   'id': '6328', 'region': 'EMEA',     'tier': 3},
        {'name': 'Game Changers 2026: Brazil Kickoff',     'slug': 'game-changers-2026-brazil-kickoff',                 'id': '6359', 'region': 'LATAM',    'tier': 3},
        {'name': 'Game Changers 2026: LATAM Kickoff',      'slug': 'game-changers-2026-latam-kickoff',                  'id': '6369', 'region': 'LATAM',    'tier': 3},
        {'name': 'Equal Esports Queens 2026: Split 1',     'slug': 'equal-esports-queens-2026-split-1',                 'id': '6306', 'region': 'EMEA',     'tier': 3},
    ]

    # All events searched for the "challengers" leaderboard: VCT + VCL + GC
    # VCT is included because PrizePicks Challengers boards include VCT players too
    ALL_NON_VCT_EVENTS = CHALLENGERS_2026_EVENTS + GC_2026_EVENTS
    ALL_EVENTS = VCT_2026_KICKOFF_EVENTS + CHALLENGERS_2026_EVENTS + GC_2026_EVENTS

    def __init__(self, database=None):
        import os
        for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy']:
            os.environ.pop(key, None)
        self.db = database
        # Session caches — persist for the life of the process
        self._player_info_cache: Dict[str, Optional[dict]] = {}  # ign_lower → player info or None
        self._event_series_cache: Dict[str, List] = {}           # event_id → [(slug, id)]
        # Thread safety: lock protects shared caches; semaphore caps concurrent HTTP requests
        self._cache_lock = threading.Lock()
        self._request_sem = threading.Semaphore(3)  # max 3 simultaneous rib.gg requests

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _build_headers(self) -> dict:
        return {
            'User-Agent': random.choice(_USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        }

    def _make_request(self, url: str, timeout: int = 90) -> Optional[bytes]:
        """Fetch a rib.gg page with retry/backoff. Returns bytes or None on failure.
        Uses a semaphore to cap concurrent requests and a lighter throttle for parallel use."""
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        last_err = None
        max_attempts = len(_RETRY_BACKOFFS) + 1

        with self._request_sem:  # at most 3 simultaneous HTTP requests to rib.gg
            for attempt in range(max_attempts):
                if attempt > 0:
                    wait = _RETRY_BACKOFFS[attempt - 1] + random.uniform(0, 4)
                    logger.info(f"RIB retry {attempt}/{max_attempts - 1} in {wait:.1f}s after: {last_err}")
                    time.sleep(wait)

                time.sleep(0.6 + random.uniform(0, 0.4))  # 0.6–1.0s throttle per request

                req = urllib.request.Request(url, headers=self._build_headers())
                try:
                    response = opener.open(req, timeout=timeout)
                    return response.read()
                except urllib.error.HTTPError as e:
                    last_err = f"HTTP {e.code}: {e.reason}"
                    if e.code in (503, 429, 502, 504):
                        continue
                    logger.warning(f"RIB HTTP {e.code} for {url}")
                    return None
                except Exception as e:
                    last_err = str(e)
                    if any(t in last_err.lower() for t in ('timeout', 'timed out', '10054', 'reset', 'connection', 'eof')):
                        continue
                    logger.warning(f"RIB request failed: {url} — {e}")
                    return None

        logger.error(f"RIB: gave up after {max_attempts} attempts for {url}: {last_err}")
        return None

    # ------------------------------------------------------------------
    # Database-first lookups (uses existing populate_challengers data)
    # ------------------------------------------------------------------

    def _get_match_combos_from_db(self, ign: str, tier: Optional[int] = None) -> Tuple[List[dict], str, List[dict]]:
        """
        Query existing player_map_stats / player_event_stats tables for a player.
        Returns (match_combinations, team_name, events_with_kpr).
        Works for any tier: 1=VCT, 2=Challengers, 3=GC, None=all.
        Case-insensitive name matching (same as DB queries).
        """
        if not self.db:
            return [], 'Unknown', []

        # get_player_all_event_stats uses LOWER() — case insensitive
        db_events = self.db.get_player_all_event_stats(ign, tier=tier)
        if not db_events:
            return [], 'Unknown', []

        match_combinations: List[dict] = []
        team = db_events[0].get('team', 'Unknown') if db_events else 'Unknown'
        events_for_kpr: List[dict] = []

        for db_event in db_events:
            event_db = self.db.get_vct_event(db_event['event_url'])
            if not event_db or event_db.get('status') != 'completed':
                continue
            # get_player_match_data_for_event also uses LOWER() — case insensitive
            matches = self.db.get_player_match_data_for_event(ign, event_db['id'])
            for m in matches:
                if m.get('map_kills') and len(m['map_kills']) >= 1:
                    match_combinations.append(m)
            # Build event dict with kpr/rounds_played for PrizePicksProcessor.calculate_weighted_kpr
            kpr = db_event.get('kpr') or 0
            rounds = db_event.get('rounds_played') or 0
            if kpr > 0 and rounds > 0:
                events_for_kpr.append({
                    'kpr': kpr,
                    'rounds_played': rounds,
                    'event_name': db_event.get('event_name', ''),
                    'rating': db_event.get('rating', 0),
                    'acs': db_event.get('acs', 0),
                })

        return match_combinations, team, events_for_kpr

    # ------------------------------------------------------------------
    # Event → series link parsing (session-cached)
    # ------------------------------------------------------------------

    def _get_event_series_slugs(self, event_slug: str, event_id: str) -> List[Tuple[str, str]]:
        """Return list of (series_slug, series_id) for an event. Results cached per session."""
        with self._cache_lock:
            if event_id in self._event_series_cache:
                return self._event_series_cache[event_id]

        url = f"{self.BASE_URL}/events/{event_slug}/{event_id}"
        content = self._make_request(url)
        if not content:
            with self._cache_lock:
                self._event_series_cache[event_id] = []
            return []

        soup = BeautifulSoup(content, 'html.parser')
        pattern = re.compile(r'^/series/([\w-]+)/(\d+)$')
        seen: set = set()
        results = []
        for a in soup.find_all('a', href=pattern):
            m = pattern.match(a['href'])
            if m:
                key = (m.group(1), m.group(2))
                if key not in seen:
                    seen.add(key)
                    results.append(key)

        logger.info(f"RIB event {event_slug}: found {len(results)} series")
        with self._cache_lock:
            self._event_series_cache[event_id] = results
        return results

    # ------------------------------------------------------------------
    # Series page parsing
    # ------------------------------------------------------------------

    def _parse_series_player_kills(self, soup: BeautifulSoup) -> Dict[str, int]:
        """
        Parse player kills from the rib.gg scoreboard table.

        Column order in the rendered HTML TDs: K | D | A | +/- | KD | ...
        ACS appears in the header label but is embedded in the player-cell element
        (not a separate <td>), so the FIRST integer parsed per row is K (kills).

        Verified empirically:
          Jduh (GC map): 22 7 8 +15 3.14  → K=22 (nums[0]), KD=22/7=3.14 ✓
          aspas (VCT):   82 59 13 +23 1.39 → K=82 (nums[0]), KD=82/59=1.39 ✓

        Returns {ign_lower: kills}.
        """
        kills_map: Dict[str, int] = {}
        for row in soup.find_all('tr'):
            pl = row.find('a', href=re.compile(r'^/players/'))
            if not pl:
                continue
            ign = pl.get_text(strip=True).lower()
            if not ign:
                continue
            nums = []
            for cell in row.find_all('td'):
                text = cell.get_text(strip=True)
                # Skip the player-cell text (contains name + possibly ACS label)
                if pl.get_text(strip=True) in text:
                    continue
                try:
                    nums.append(int(text))
                except ValueError:
                    try:
                        nums.append(int(text.lstrip('+')))
                    except ValueError:
                        pass
            # nums[0] = K (kills), nums[1] = D (deaths), nums[2] = A, nums[3] = +/-
            if nums:
                kills_map[ign] = nums[0]
        return kills_map

    def _parse_series_map_ids(self, soup: BeautifulSoup) -> List[Tuple[str, str, str]]:
        """
        Extract per-map match IDs from the Head-to-Head section.
        These appear as links: /series/{slug}/{id}?match=227708
        IMPORTANT: only appears on the PLAIN series URL (not ?tab=player-stats).
        Returns list of (map_name, score, match_id).
        """
        match_id_re = re.compile(r'[?&]match=(\d+)')
        seen: set = set()
        maps = []

        for a in soup.find_all('a', href=True):
            href = a['href']
            m = match_id_re.search(href)
            if not m:
                continue
            match_id = m.group(1)
            if match_id == '0' or match_id in seen:
                continue
            seen.add(match_id)

            text = a.get_text(strip=True)
            # "13-9Bind", "13-5Corrode", etc.
            score_match = re.match(r'(\d+-\d+)(.+)?', text)
            if score_match:
                score = score_match.group(1)
                map_name = (score_match.group(2) or 'Unknown').strip()
            else:
                score = 'N/A'
                map_name = text or 'Unknown'

            maps.append((map_name, score, match_id))

        return maps

    def _get_series_info(self, series_slug: str, series_id: str) -> Optional[dict]:
        """
        Fetch the PLAIN series page (no ?tab parameter) to get BOTH:
          - player kills for player detection
          - per-map match IDs from the Head-to-Head section
        Returns dict with player_kills, maps, team slugs/names.
        """
        # CRITICAL: must use plain URL — ?tab=player-stats removes the Head-to-Head section
        url = f"{self.BASE_URL}/series/{series_slug}/{series_id}"
        content = self._make_request(url)
        if not content:
            return None

        soup = BeautifulSoup(content, 'html.parser')
        kills = self._parse_series_player_kills(soup)
        maps = self._parse_series_map_ids(soup)

        # Extract team info
        team_re = re.compile(r'^/teams/([\w-]+)/(\d+)$')
        team_slugs, team_names = [], []
        for a in soup.find_all('a', href=team_re):
            m = team_re.match(a['href'])
            if m:
                slug = m.group(1)
                name = a.get_text(strip=True)
                if slug not in team_slugs:
                    team_slugs.append(slug)
                    team_names.append(name)

        return {
            'player_kills': kills,
            'maps': maps,
            'team1_slug': team_slugs[0] if len(team_slugs) > 0 else '',
            'team2_slug': team_slugs[1] if len(team_slugs) > 1 else '',
            'team1_name': team_names[0] if len(team_names) > 0 else '',
            'team2_name': team_names[1] if len(team_names) > 1 else '',
        }

    def _get_map_kills(self, series_slug: str, series_id: str, match_id: str, player_name_lower: str) -> Optional[int]:
        """
        Fetch a per-map ?match={id}&tab=player-stats page and return kill count for the player.
        Uses a 90s timeout since these pages can be slow to server-side render.
        """
        url = f"{self.BASE_URL}/series/{series_slug}/{series_id}?match={match_id}&tab=player-stats"
        content = self._make_request(url, timeout=90)
        if not content:
            return None

        soup = BeautifulSoup(content, 'html.parser')
        kills_map = self._parse_series_player_kills(soup)

        if player_name_lower in kills_map:
            return kills_map[player_name_lower]
        for ign, k in kills_map.items():
            if player_name_lower in ign or ign in player_name_lower:
                return k
        return None

    # ------------------------------------------------------------------
    # Player lookup across events (rib.gg only — used when DB misses)
    # ------------------------------------------------------------------

    def _find_player_info(self, player_name: str, events: List[dict]) -> Optional[dict]:
        """
        Find which event/team/series a player participated in by scanning series pages.
        Checks in-memory cache, then DB cache, then live scan.

        Returns: {event_name, event_id, event_slug, tier, team_name, team_slug,
                  series: [(slug, id), ...]}
        """
        p_lower = player_name.lower()

        with self._cache_lock:
            if p_lower in self._player_info_cache:
                return self._player_info_cache[p_lower]

        if self.db:
            cached_raw = self.db.get_vlr_player_url(f"rib:{p_lower}")
            if cached_raw:
                try:
                    info = json.loads(cached_raw)
                    with self._cache_lock:
                        self._player_info_cache[p_lower] = info
                    return info
                except Exception:
                    pass

        for event in events:
            event_id = event['id']
            event_slug = event['slug']

            all_series = self._get_event_series_slugs(event_slug, event_id)
            if not all_series:
                continue

            found_team_slug = None
            found_team_name = None

            for s_slug, s_id in all_series:
                if found_team_slug:
                    break

                info_raw = self._get_series_info(s_slug, s_id)
                if not info_raw:
                    continue

                # Check if player is in this series (exact or fuzzy name match)
                player_found = any(
                    p_lower == ign or p_lower in ign or ign in p_lower
                    for ign in info_raw['player_kills']
                )
                if not player_found:
                    continue

                # Determine team slug from series URL
                vs_match = re.match(r'^([\w-]+?)-vs-([\w-]+?)-', s_slug)
                if vs_match:
                    found_team_slug = vs_match.group(1)
                    found_team_name = info_raw['team1_name']
                else:
                    found_team_slug = info_raw.get('team1_slug', '')
                    found_team_name = info_raw.get('team1_name', '')

            if not found_team_slug:
                continue

            # Filter all event series that include this team
            event_suffixes = ['-vct-', '-challengers-', '-valorant-', '-esports-world-', '-champions-',
                              '-game-changers-', '-gcq-', '-equal-', '-ascension-']
            team_series = []
            for s_slug, s_id in all_series:
                vs_parts = s_slug.split('-vs-', 1)
                if len(vs_parts) != 2:
                    continue
                t1s = vs_parts[0]
                t2_raw = vs_parts[1]
                t2s = t2_raw
                for sfx in event_suffixes:
                    if sfx in t2_raw:
                        t2s = t2_raw.split(sfx)[0]
                        break
                if (found_team_slug == t1s or found_team_slug in t1s or t1s in found_team_slug or
                        found_team_slug == t2s or found_team_slug in t2s or t2s in found_team_slug):
                    team_series.append((s_slug, s_id))

            player_info = {
                'event_name': event['name'],
                'event_id': event_id,
                'event_slug': event_slug,
                'tier': event.get('tier', 1),
                'team_name': found_team_name,
                'team_slug': found_team_slug,
                'series': team_series,
            }

            with self._cache_lock:
                self._player_info_cache[p_lower] = player_info
            if self.db:
                self.db.save_vlr_player_url(f"rib:{p_lower}", json.dumps(player_info))

            logger.info(f"RIB: found '{player_name}' on {found_team_name} in {event['name']} ({len(team_series)} series)")
            return player_info

        logger.warning(f"RIB: player '{player_name}' not found in {len(events)} events")
        with self._cache_lock:
            self._player_info_cache[p_lower] = None
        return None

    # ------------------------------------------------------------------
    # Per-series match combinations (rib.gg scrape)
    # ------------------------------------------------------------------

    def _build_match_combos_from_rib(self, player_name: str, player_info: dict) -> List[dict]:
        """
        For each series the player was in, fetch per-map kills from rib.gg.
        Returns match_combinations list compatible with PrizePicksProcessor.
        """
        p_lower = player_name.lower()
        match_combinations = []

        for s_slug, s_id in player_info['series']:
            series_info = self._get_series_info(s_slug, s_id)
            if not series_info:
                continue

            maps = series_info['maps']
            total_kills = series_info['player_kills']

            if not maps:
                logger.warning(f"RIB: no map IDs found in series {s_id} (Head-to-Head section absent?)")
                continue

            per_map_kills = []
            per_map_scores = []

            for map_name, score, match_id in maps:
                kills = self._get_map_kills(s_slug, s_id, match_id, p_lower)
                if kills is None:
                    # Fallback: total kills / number of maps
                    total_k = next(
                        (k for ign, k in total_kills.items()
                         if p_lower == ign or p_lower in ign or ign in p_lower),
                        None
                    )
                    if total_k is not None and len(maps) > 0:
                        kills = round(total_k / len(maps))
                    else:
                        continue

                if kills is not None and kills > 0:
                    per_map_kills.append(kills)
                    per_map_scores.append(score)

            if len(per_map_kills) >= 1:
                match_combinations.append({
                    'match_url': f'/series/{s_slug}/{s_id}',
                    'event_name': player_info['event_name'],
                    'map_kills': per_map_kills,
                    'map_scores': per_map_scores,
                    'num_maps': len(per_map_kills),
                })
                logger.info(f"RIB: series {s_id} → {player_name}: {per_map_kills}")

        return match_combinations

    # ------------------------------------------------------------------
    # Public interface (matches VLRScraper API)
    # ------------------------------------------------------------------

    def _build_player_result(self, ign: str, team: str, match_combinations: List[dict],
                              kill_line: float, event_name: str = '',
                              events_with_kpr: Optional[List[dict]] = None) -> dict:
        # events_with_kpr: list of {kpr, rounds_played, event_name, ...} for PrizePicksProcessor
        events = events_with_kpr if events_with_kpr else (
            [{'event_name': event_name, 'cached': True}] if event_name else []
        )
        return {
            'ign': ign,
            'team': team,
            'events': events,
            'kill_line': kill_line,
            'match_combinations': match_combinations,
            'overall_stats': {},
            'last_updated': datetime.now().isoformat(),
        }

    def get_player_prizepicks_data(self, ign: str, kill_line: float = 30.5) -> dict:
        """
        PrizePicks match-level data for a VCT tier-1 player.
        Priority: DB cache → live rib.gg (VCT events).
        """
        logger.info(f"RIB: PrizePicks VCT lookup: {ign}")

        # 1. Try DB with tier=1 (VCT) first
        result = self._get_match_combos_from_db(ign, tier=1)
        combos, team, events_kpr = result[0], result[1], result[2]
        if combos:
            logger.info(f"RIB: DB hit (VCT) for '{ign}' — {len(combos)} matches")
            return self._build_player_result(ign, team, combos, kill_line, 'DB (VCT)', events_kpr)

        # 2. Try DB without tier filter (catches mixed-tier data)
        result = self._get_match_combos_from_db(ign, tier=None)
        combos, team, events_kpr = result[0], result[1], result[2]
        if combos:
            logger.info(f"RIB: DB hit (any tier) for '{ign}' — {len(combos)} matches")
            return self._build_player_result(ign, team, combos, kill_line, 'DB', events_kpr)

        # 3. Live rib.gg scrape — VCT events only (no KPR from rib.gg, processor may fail)
        player_info = self._find_player_info(ign, self.VCT_2026_KICKOFF_EVENTS)
        if not player_info:
            logger.warning(f"RIB: '{ign}' not found in VCT events")
            return {}

        combos = self._build_match_combos_from_rib(ign, player_info)
        if not combos:
            return {}

        # Live scrape: compute KPR from map kills for processor
        events_kpr = []
        for m in combos:
            kills = m.get('map_kills', [])
            if kills:
                total_k = sum(kills)
                total_rounds = len(kills) * 24  # approx rounds per map
                if total_rounds > 0:
                    events_kpr.append({
                        'kpr': total_k / total_rounds,
                        'rounds_played': total_rounds,
                        'event_name': m.get('event_name', ''),
                    })
        result = self._build_player_result(ign, player_info.get('team_name', 'Unknown'),
                                            combos, kill_line, player_info['event_name'], events_kpr)
        if self.db:
            self.db.save_player_data_cache(ign, result)
        return result

    def get_player_prizepicks_data_challengers(self, ign: str, kill_line: float = 30.5) -> dict:
        """
        PrizePicks match-level data for Challengers/GC/VCT players.
        The PrizePicks Challengers board mixes VCL, GC, and sometimes VCT players.

        Priority:
          1. DB match data (any tier — uses populate_challengers / populate_moneyline data)
          2. Live rib.gg scrape across Challengers + GC + VCT events
        """
        logger.info(f"RIB: PrizePicks Challengers lookup: {ign}")

        # 1. Try DB across ALL tiers (Challengers DB has tier 2; VCT DB has tier 1)
        #    get_player_all_event_stats uses LOWER() — case insensitive
        result = self._get_match_combos_from_db(ign, tier=None)
        combos, team, events_kpr = result[0], result[1], result[2]
        if combos:
            logger.info(f"RIB: DB hit for '{ign}' — {len(combos)} matches, team={team}")
            return self._build_player_result(ign, team, combos, kill_line, 'DB', events_kpr)

        # 2. Live rib.gg — search ALL events: VCT + Challengers + GC
        player_info = self._find_player_info(ign, self.ALL_EVENTS)
        if not player_info:
            logger.warning(f"RIB: '{ign}' not found in any event")
            return {}

        combos = self._build_match_combos_from_rib(ign, player_info)
        if not combos:
            return {}

        events_kpr = []
        for m in combos:
            kills = m.get('map_kills', [])
            if kills:
                total_k = sum(kills)
                total_rounds = len(kills) * 24
                if total_rounds > 0:
                    events_kpr.append({
                        'kpr': total_k / total_rounds,
                        'rounds_played': total_rounds,
                        'event_name': m.get('event_name', ''),
                    })
        result = self._build_player_result(ign, player_info.get('team_name', 'Unknown'),
                                            combos, kill_line, player_info['event_name'], events_kpr)
        if self.db:
            self.db.save_player_data_cache_challengers(ign, result)
        return result

    def set_database(self, database) -> None:
        self.db = database
