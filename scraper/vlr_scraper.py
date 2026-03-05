# scraper/vlr_scraper.py
import requests
from bs4 import BeautifulSoup
import re
import time
import random
import logging
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Realistic browser User-Agents to rotate so each request looks different
_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0',
]

# Retry backoff schedule in seconds (attempt 1, 2, 3, 4, 5)
_RETRY_BACKOFFS = [10, 20, 45, 90, 120]

class VLRScraper:
    def __init__(self, database=None):
        self.base_url = Config.VLR_BASE_URL
        # Remove proxy environment variables to bypass proxy issues
        import os
        for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy']:
            os.environ.pop(key, None)
        # Use requests session but with proxies disabled (kept for compatibility)
        self.session = requests.Session()
        self.session.proxies = {}
        self.session.trust_env = False
        self.db = database  # Optional database for caching
        # In-memory URL cache: player_name (lower) → VLR profile path
        self._url_cache: Dict[str, str] = {}

    def _build_headers(self) -> dict:
        """Build realistic browser headers with a randomly selected User-Agent."""
        return {
            'User-Agent': random.choice(_USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        }

    def _make_request(self, url: str, params: dict = None) -> bytes:
        """Make HTTP request with aggressive retry/backoff for 503, timeouts, and connection resets."""
        if params:
            from urllib.parse import urlencode
            url = f"{url}?{urlencode(params)}"

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        last_err = None
        max_attempts = len(_RETRY_BACKOFFS) + 1  # 6 total attempts

        for attempt in range(max_attempts):
            if attempt > 0:
                delay = _RETRY_BACKOFFS[attempt - 1]
                jitter = random.uniform(0, min(5, delay * 0.2))
                wait = delay + jitter
                logger.info(f"VLR retry {attempt}/{max_attempts - 1} in {wait:.1f}s after: {last_err}")
                time.sleep(wait)

            # Base throttle (1s) + random jitter (0–1.5s) between every request
            time.sleep(1.0 + random.uniform(0, 1.5))

            req = urllib.request.Request(url, headers=self._build_headers())
            try:
                response = opener.open(req, timeout=45)
                return response.read()
            except urllib.error.HTTPError as e:
                last_err = f"HTTP {e.code}: {e.reason}"
                if e.code in (503, 429, 502, 504):
                    continue  # Retry on rate-limit / gateway errors
                raise Exception(f"Request failed: {last_err}")
            except urllib.error.URLError as e:
                last_err = str(e)
                err_lower = last_err.lower()
                retryable = any(t in err_lower for t in (
                    '503', '429', '502', '504', 'timed out', '10054',
                    'connection', 'forcibly closed', 'reset', 'eof',
                ))
                if retryable:
                    continue
                raise Exception(f"Request failed: {e}")
            except (OSError, TimeoutError) as e:
                last_err = str(e)
                err_lower = last_err.lower()
                retryable = any(t in err_lower for t in (
                    '10054', 'timed out', 'timeout', 'reset', 'connection',
                ))
                if retryable:
                    continue
                raise

        raise Exception(f"VLR request failed after {max_attempts} attempts: {last_err}")
        
    def set_database(self, database):
        """Set the database for caching"""
        self.db = database
    
    def _try_search(self, soup, query: str) -> Optional[str]:
        """Try to find player in search results by matching query to link text."""
        player_links = soup.find_all('a', href=re.compile(r'/player/\d+/'))
        query_lower = query.lower()
        for link in player_links:
            link_text = link.get_text(strip=True).lower()
            if query_lower in link_text or link_text in query_lower:
                return link['href']
        # Don't use first-result fallback for placeholder names or likely team fragments
        skip_fallback = (query_lower.startswith('player_') or query_lower.startswith('unknown_') or
                        len(query) < 3 or query_lower in ('natus', 'today', 'karmi', 'vincere'))
        if player_links and len(query) >= 2 and not skip_fallback:
            return player_links[0]['href']
        return None

    def search_player(self, player_name: str) -> Optional[str]:
        """Search for a player and return their profile URL.
        
        Checks in-memory cache and DB cache first so the VLR /search endpoint is
        only ever hit once per player name across the lifetime of the process.
        """
        q = str(player_name).strip()
        q = re.sub(r'\.{2,}$|…+$', '', q).strip('.\t ')
        if not q or q.lower().startswith('unknown_'):
            return None

        q_lower = q.lower()

        # 1. In-memory cache (fastest, within this session)
        if q_lower in self._url_cache:
            logger.info(f"URL cache hit (memory) for '{q}': {self._url_cache[q_lower]}")
            return self._url_cache[q_lower]

        # 2. Persistent DB cache (survives restarts — zero VLR traffic for known players)
        if self.db:
            cached_url = self.db.get_vlr_player_url(q)
            if cached_url:
                logger.info(f"URL cache hit (DB) for '{q}': {cached_url}")
                self._url_cache[q_lower] = cached_url
                return cached_url

        # 3. Live search on VLR /search
        search_url = f"{self.base_url}/search"

        def _search_and_cache(query: str) -> Optional[str]:
            try:
                content = self._make_request(search_url, params={'q': query})
                soup = BeautifulSoup(content, 'html.parser')
                found = self._try_search(soup, query)
                if found:
                    self._url_cache[q_lower] = found
                    if self.db:
                        self.db.save_vlr_player_url(q, found)
                return found
            except Exception as e:
                logger.error(f"Error searching VLR for '{query}': {e}")
                return None

        url = _search_and_cache(q)
        if url:
            return url

        # 4. Try common OCR-confusion alternates (1↔l, 0↔o, 4↔a) only if primary failed
        alternates = []
        if '1' in q:
            alternates.append(q.replace('1', 'l'))
        if 'l' in q:
            alternates.append(q.replace('l', '1', 1))
        if '0' in q:
            alternates.append(q.replace('0', 'o'))
        if 'o' in q and '0' not in q:
            alternates.append(q.replace('o', '0', 1))
        if '4' in q:
            alternates.append(q.replace('4', 'a'))
        if 'a' in q and '4' not in q:
            alternates.append(q.replace('a', '4', 1))

        for alt in alternates:
            if alt == q:
                continue
            url = _search_and_cache(alt)
            if url:
                return url

        return None
    
    # Current VCT 2026 Tier-1 events (Kickoff + International).
    # Live-scraped only when the event is NOT yet completed in the DB;
    # once populate_database.py has cached it, _get_ongoing_event_match_data
    # skips it so we never show the same event as both LIVE and CACHED.
    VCT_2026_KICKOFF_EVENTS = [
        {'name': 'VCT 2026: Americas Kickoff',     'url': '/event/2682/vct-2026-americas-kickoff',       'region': 'Americas'},
        {'name': 'VCT 2026: EMEA Kickoff',          'url': '/event/2684/vct-2026-emea-kickoff',           'region': 'EMEA'},
        {'name': 'VCT 2026: Pacific Kickoff',       'url': '/event/2683/vct-2026-pacific-kickoff',        'region': 'Pacific'},
        {'name': 'VCT 2026: China Kickoff',         'url': '/event/2685/vct-2026-china-kickoff',          'region': 'China'},
        {'name': 'Valorant Masters Santiago 2026',  'url': '/event/2760/valorant-masters-santiago-2026',  'region': 'International'},
    ]

    # Current ongoing Challengers 2026 events (live scrape for OCR leaderboard)
    CHALLENGERS_2026_ONGOING = [
        {'name': 'Challengers 2026: North America ACE Stage 1', 'url': '/event/2783/challengers-2026-north-america-ace-stage-1', 'region': 'Americas'},
        {'name': 'Challengers 2026: Brazil Gamers Club Stage 1', 'url': '/event/2787/challengers-2026-brazil-gamers-club-stage-1', 'region': 'Americas'},
        {'name': 'Challengers 2026: LATAM North ACE Stage 1', 'url': '/event/2777/challengers-2026-latam-north-ace-stage-1', 'region': 'Americas'},
        {'name': 'Challengers 2026: LATAM South ACE Stage 1', 'url': '/event/2778/challengers-2026-latam-south-ace-stage-1', 'region': 'Americas'},
        {'name': 'Challengers 2026: DACH Evolution Stage 1', 'url': '/event/2781/challengers-2026-dach-evolution-stage-1', 'region': 'EMEA'},
        {'name': 'Challengers 2026: NORTH//EAST Stage 1', 'url': '/event/2834/challengers-2026-north-east-stage-1', 'region': 'EMEA'},
        {'name': 'Challengers 2026: Japan Split 1', 'url': '/event/2847/challengers-2026-japan-split-1', 'region': 'Pacific'},
        {'name': 'Challengers 2026: Korea WDG Split 1', 'url': '/event/2830/challengers-2026-korea-wdg-split-1', 'region': 'Pacific'},
        {'name': 'Challengers 2026: Southeast Asia Split 1', 'url': '/event/2823/challengers-2026-southeast-asia-split-1', 'region': 'Pacific'},
    ]
    
    @classmethod
    def get_teams_from_vct_events(cls, events: list = None) -> set:
        """
        Scrape VLR event matches to extract team name fragments for OCR blacklist.
        Returns lowercase fragments (e.g. 'bbl', 'esports', 'rex', 'regum') from all teams.
        Uses events list or defaults to VCT 2026 Kickoff (all 4 regions).
        """
        if events is None:
            events = cls.VCT_2026_KICKOFF_EVENTS
        fragments = set()
        base_url = Config.VLR_BASE_URL
        headers = Config.HEADERS
        import urllib.request
        import urllib.error
        for event in events:
            matches_url = event['url'].replace('/event/', '/event/matches/')
            full_url = f"{base_url}{matches_url}/?series_id=all"
            try:
                req = urllib.request.Request(full_url, headers=headers)
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                content = opener.open(req, timeout=15).read()
                soup = BeautifulSoup(content, 'html.parser')
                match_pattern = re.compile(r'/\d+/[\w-]+-vs-[\w-]+')
                for link in soup.find_all('a', href=match_pattern):
                    href = link.get('href', '')
                    m = re.match(r'/\d+/([\w-]+)-vs-([\w-]+)', href)
                    if m:
                        for t in (m.group(1), m.group(2)):
                            for part in t.split('-'):
                                if len(part) >= 2 and part.isalnum():
                                    fragments.add(part.lower())
            except Exception as e:
                logger.warning(f"Could not fetch teams from {event.get('name', 'event')}: {e}")
        return fragments

    # VLR rankings regions - scrape team slugs for comprehensive blacklist.
    # Includes World + all regional rankings (NA, EU, BR, APAC, KR, CN, JP, LAS, LAN, OCE, MENA, GC, Collegiate).
    VLR_RANKINGS_REGIONS = [
        '', 'north-america', 'europe', 'brazil', 'asia-pacific', 'korea', 'china', 'japan',
        'la-s', 'la-n', 'oceania', 'mena', 'gc', 'collegiate',
    ]

    @classmethod
    def get_teams_from_vlr_rankings(cls, regions: list = None) -> set:
        """
        Scrape VLR rankings pages to extract team slugs for OCR blacklist.
        Returns lowercase tokens: full slugs (e.g. 'sleepers', '9z-team') and
        hyphen-separated parts (e.g. '9z', 'team') so team names are never
        mistaken for player IGNs.
        """
        if regions is None:
            regions = cls.VLR_RANKINGS_REGIONS
        tokens = set()
        base_url = Config.VLR_BASE_URL
        headers = Config.HEADERS
        team_link_re = re.compile(r'^/team/\d+/([\w-]+)$')
        import urllib.request
        import urllib.error
        for region in regions:
            path = f"/rankings/{region}" if region else "/rankings"
            full_url = f"{base_url}{path}"
            try:
                req = urllib.request.Request(full_url, headers=headers)
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                content = opener.open(req, timeout=15).read()
                soup = BeautifulSoup(content, 'html.parser')
                for link in soup.find_all('a', href=team_link_re):
                    href = link.get('href', '')
                    m = team_link_re.match(href)
                    if m:
                        slug = m.group(1).lower()
                        tokens.add(slug)
                        for part in slug.split('-'):
                            if len(part) >= 2 and part.isalnum():
                                tokens.add(part)
            except Exception as e:
                logger.warning(f"Could not fetch teams from VLR rankings {path}: {e}")
        return tokens

    # VLR tier IDs: 60=VCT, 61=VCL (Challengers), 62=T3, 63=GC, 64=Collegiate, 67=Offseason
    VCL_TIER_ID = 61

    def get_challengers_leagues(self, max_pages: int = 10) -> List[Dict]:
        """
        Scrape VLR events page for all Challengers (tier 2 / VCL) leagues.
        Returns list of {name, url, event_id, status, prize_pool, dates}.
        """
        results = []
        base_url = f"{self.base_url}/events"
        event_link_re = re.compile(r'^/event/(\d+)/[\w-]+$')

        for page in range(1, max_pages + 1):
            params = {'tier': self.VCL_TIER_ID}
            if page > 1:
                params['page'] = page
            try:
                content = self._make_request(base_url, params=params)
                soup = BeautifulSoup(content, 'html.parser')
                # Find event links - VLR uses a.events-col-item or similar
                event_items = soup.select('a.events-col-item') or soup.find_all('a', href=re.compile(r'^/event/\d+/'))
                if not event_items:
                    # Fallback: any link to /event/ID/slug
                    event_items = soup.find_all('a', href=event_link_re)

                page_count = 0
                for a in event_items:
                    href = a.get('href', '')
                    m = re.match(r'^/event/(\d+)/([\w-]+)$', href)
                    if not m:
                        continue
                    event_id, slug = m.group(1), m.group(2)
                    # Extract display text (event name) - first text node or inner text
                    name = a.get_text(strip=True)
                    # Clean up: remove "ongoing/completed Status $X Prize Pool Jan 1—Mar 1 Dates Region"
                    for suffix in ('ongoing', 'completed', 'upcoming', 'Status', 'Prize Pool', 'Dates', 'Region'):
                        if suffix in name:
                            name = name.split(suffix)[0].strip()
                    # Also trim common trailing metadata
                    for sep in ('$', 'TBD', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'):
                        if sep in name and name.index(sep) < len(name) - 5:
                            name = name.split(sep)[0].strip()
                    if len(name) < 3:
                        continue
                    # Dedupe by event_id
                    if any(r.get('event_id') == event_id for r in results):
                        continue
                    results.append({
                        'event_id': event_id,
                        'name': name,
                        'url': href,
                        'slug': slug,
                    })
                    page_count += 1

                if page_count == 0:
                    break
                time.sleep(0.5)  # Be nice to VLR
            except Exception as e:
                logger.warning(f"Error fetching Challengers page {page}: {e}")
                break
        return results

    # 2025 VCT events (completed - use cache)
    # ALL URLs VERIFIED FROM VLR.gg 2026-01-24
    VCT_2025_EVENTS = [
        # Americas
        {'name': 'VCT 2025: Americas Stage 2', 'url': '/event/2501/vct-2025-americas-stage-2', 'region': 'Americas'},
        {'name': 'VCT 2025: Americas Stage 1', 'url': '/event/2347/vct-2025-americas-stage-1', 'region': 'Americas'},
        {'name': 'VCT 2025: Americas Kickoff', 'url': '/event/2274/vct-2025-americas-kickoff', 'region': 'Americas'},
        # EMEA
        {'name': 'VCT 2025: EMEA Stage 2', 'url': '/event/2498/vct-2025-emea-stage-2', 'region': 'EMEA'},
        {'name': 'VCT 2025: EMEA Stage 1', 'url': '/event/2380/vct-2025-emea-stage-1', 'region': 'EMEA'},
        {'name': 'VCT 2025: EMEA Kickoff', 'url': '/event/2276/vct-2025-emea-kickoff', 'region': 'EMEA'},
        # Pacific
        {'name': 'VCT 2025: Pacific Stage 2', 'url': '/event/2500/vct-2025-pacific-stage-2', 'region': 'Pacific'},
        {'name': 'VCT 2025: Pacific Stage 1', 'url': '/event/2379/vct-2025-pacific-stage-1', 'region': 'Pacific'},
        {'name': 'VCT 2025: Pacific Kickoff', 'url': '/event/2277/vct-2025-pacific-kickoff', 'region': 'Pacific'},
        # China
        {'name': 'VCT 2025: China Stage 2', 'url': '/event/2499/vct-2025-china-stage-2', 'region': 'China'},
        {'name': 'VCT 2025: China Stage 1', 'url': '/event/2359/vct-2025-china-stage-1', 'region': 'China'},
        {'name': 'VCT 2025: China Kickoff', 'url': '/event/2275/vct-2025-china-kickoff', 'region': 'China'},
    ]
    
    def get_player_stats(self, player_url: str, kill_line: float = 15.5) -> Dict:
        """Get player statistics from VCT events, using cache when available"""
        full_url = f"{self.base_url}{player_url}"
        
        try:
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            
            player_name = self._extract_player_name(soup)
            team = self._extract_current_team(soup)
            
            logger.info(f"Player: {player_name}, Team: {team}")
            
            event_stats = []
            all_map_kills = []
            
            # 1. Check ongoing 2026 Kickoff events (always scrape live)
            kickoff_stats = self._get_ongoing_event_stats(player_name, team, kill_line)
            if kickoff_stats:
                event_stats.append(kickoff_stats)
                all_map_kills.extend(kickoff_stats.get('map_kills', []))
            
            # 2. Get cached 2025 event data (or scrape if not cached)
            cached_stats = self._get_cached_event_stats(player_name, team, kill_line, tier=1)
            for stats in cached_stats[:2]:  # Take top 2 most recent
                event_stats.append(stats)
                all_map_kills.extend(stats.get('map_kills', []))
            
            # Calculate over/under
            over_count = sum(1 for k in all_map_kills if k > kill_line)
            under_count = sum(1 for k in all_map_kills if k <= kill_line)
            total_maps = len(all_map_kills)
            
            over_percentage = (over_count / total_maps * 100) if total_maps > 0 else 0
            under_percentage = (under_count / total_maps * 100) if total_maps > 0 else 0
            
            player_data = {
                'ign': player_name,
                'team': team,
                'events': event_stats,
                'kill_line': kill_line,
                'all_map_kills': all_map_kills,
                'over_count': over_count,
                'under_count': under_count,
                'total_maps': total_maps,
                'over_percentage': round(over_percentage, 1),
                'under_percentage': round(under_percentage, 1),
                'overall_stats': {},
                'last_updated': datetime.now().isoformat()
            }
            
            return player_data
            
        except Exception as e:
            logger.error(f"Error fetching player stats from {player_url}: {e}")
            return {}
    
    def _get_ongoing_event_stats(self, player_name: str, team: str, kill_line: float) -> Optional[Dict]:
        """Get stats from ongoing 2026 Kickoff events (always live scrape)"""
        for kickoff in self.VCT_2026_KICKOFF_EVENTS:
            # Check if player is in this event
            stats = self._get_player_event_kpr(kickoff['url'], player_name)
            if stats:
                # Get map kills with scores for this event (filter by team)
                map_data = self._get_player_team_map_kills_with_scores(kickoff['url'], player_name, team)
                map_kills = [m['kills'] for m in map_data]
                
                stats['event_name'] = kickoff['name']
                stats['event_url'] = kickoff['url']
                stats['map_kills'] = map_kills
                stats['map_data'] = map_data  # Include scores for win/loss analysis
                stats['event_over'] = sum(1 for k in map_kills if k > kill_line)
                stats['event_under'] = sum(1 for k in map_kills if k <= kill_line)
                stats['event_maps'] = len(map_kills)
                stats['cached'] = False  # Live scraped
                
                logger.info(f"Found player in {kickoff['name']}: KPR={stats['kpr']}, Maps={len(map_kills)}")
                return stats
        
        return None
    
    def _get_player_team_map_kills_with_scores(self, event_url: str, player_name: str, team: str) -> List[Dict]:
        """Get map kills with scores for a player by filtering matches by their team"""
        map_data = []
        
        # Get all matches from this event
        matches_url = event_url.replace('/event/', '/event/matches/')
        full_url = f"{self.base_url}{matches_url}/?series_id=all"
        
        try:
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find all match links
            match_pattern = re.compile(r'/\d+/[\w-]+-vs-[\w-]+')
            match_links = soup.find_all('a', href=match_pattern)
            
            seen_matches = set()
            team_lower = team.lower().replace(' ', '-').replace('.', '')
            
            team_variants = [
                team_lower,
                team_lower.replace('-esports', ''),
                team_lower.replace('-', ''),
                team.lower().split()[0] if team else ''
            ]
            
            for link in match_links:
                match_url = link.get('href', '')
                
                if match_url in seen_matches:
                    continue
                
                match_url_lower = match_url.lower()
                team_in_match = any(t in match_url_lower for t in team_variants if t)
                
                if not team_in_match:
                    continue
                
                seen_matches.add(match_url)
                
                # Get kills and scores for this match
                match_kills, match_scores = self._get_match_map_kills_and_scores(match_url, player_name)
                if match_kills:
                    for kills, score in zip(match_kills, match_scores):
                        map_data.append({'kills': kills, 'map_score': score})
                
        except Exception as e:
            logger.error(f"Error fetching matches with scores from {event_url}: {e}")
        
        return map_data
    
    def _get_cached_event_stats(self, player_name: str, team: str, kill_line: float, tier: Optional[int] = None) -> List[Dict]:
        """
        Get cached event stats from database for COMPLETED events only.
        tier: 1=VCT, 2=Challengers, None=all (VCT default).
        """
        cached_events = []
        
        # Check database for cached data from COMPLETED events only
        if self.db:
            logger.info(f"Checking cache for player: {player_name} (tier={tier or 'all'})")
            db_events = self.db.get_player_all_event_stats(player_name, tier=tier)
            logger.info(f"Found {len(db_events)} cached events for {player_name}")
            
            events_added = 0
            for db_event in db_events:  # Check all events
                if events_added >= 2:  # Only take top 2 events WITH map data
                    break
                    
                event_url = db_event['event_url']
                logger.info(f"Processing event: {db_event['event_name']} ({event_url})")
                
                # Verify this is a completed event (should only get completed from DB query)
                event_db = self.db.get_vct_event(event_url)
                if event_db and event_db.get('status') == 'completed':
                    # Get map kills with scores
                    map_data = self.db.get_player_map_kills_with_scores_for_event(player_name, event_db['id'])
                    map_kills = [m['kills'] for m in map_data]
                    logger.info(f"  Found {len(map_kills)} map kills for {player_name} in {db_event['event_name']}")
                    
                    # Skip events with no map kills (useless for analysis)
                    if len(map_kills) == 0:
                        logger.warning(f"  Skipping {db_event['event_name']} - no map kills found")
                        continue
                    
                    cached_events.append({
                        'kpr': db_event['kpr'],
                        'rounds_played': db_event['rounds_played'],
                        'rating': db_event['rating'],
                        'acs': db_event['acs'],
                        'adr': db_event['adr'],
                        'kills': db_event['kills'],
                        'deaths': db_event['deaths'],
                        'maps_played': 0,
                        'event_name': db_event['event_name'],
                        'event_url': event_url,
                        'map_kills': map_kills,
                        'map_data': map_data,  # Include scores for win/loss analysis
                        'event_over': sum(1 for k in map_kills if k > kill_line),
                        'event_under': sum(1 for k in map_kills if k <= kill_line),
                        'event_maps': len(map_kills),
                        'cached': True
                    })
                    events_added += 1
                    logger.info(f"Loaded from cache: {db_event['event_name']} ({len(map_kills)} maps)")
                else:
                    logger.warning(f"  Event not found in database or not completed: {event_url}")
        else:
            logger.warning("No database connection available for caching")
        
        # IMPORTANT: Do NOT fall back to live scraping for completed events
        # Completed events should ONLY come from cache. If cache is empty, that's it.
        # This ensures we never scrape completed events live, only use cached data.
        if not cached_events:
            logger.info(f"No cached data found for {player_name} in completed events. Cache may need to be populated.")
        
        return cached_events
    
    def _get_player_team_map_kills(self, event_url: str, player_name: str, team: str) -> List[int]:
        """Get all map kills for a player by filtering matches by their team"""
        map_kills = []
        
        # Get all matches from this event
        matches_url = event_url.replace('/event/', '/event/matches/')
        full_url = f"{self.base_url}{matches_url}/?series_id=all"
        
        try:
            logger.info(f"Fetching matches from: {full_url}")
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find all match links
            match_pattern = re.compile(r'/\d+/[\w-]+-vs-[\w-]+')
            match_links = soup.find_all('a', href=match_pattern)
            
            seen_matches = set()
            team_lower = team.lower().replace(' ', '-').replace('.', '')
            
            # Also try common team name variations
            team_variants = [
                team_lower,
                team_lower.replace('-esports', ''),
                team_lower.replace('-', ''),
                team.lower().split()[0] if team else ''  # First word of team name
            ]
            
            for link in match_links:
                match_url = link.get('href', '')
                
                if match_url in seen_matches:
                    continue
                
                # Check if this match involves the player's team
                match_url_lower = match_url.lower()
                team_in_match = any(t in match_url_lower for t in team_variants if t)
                
                if not team_in_match:
                    continue
                
                seen_matches.add(match_url)
                
                # Scrape this match for player kills
                match_kills = self._get_match_map_kills(match_url, player_name)
                if match_kills:
                    map_kills.extend(match_kills)
                    logger.info(f"  Match {match_url}: kills = {match_kills}")
                
        except Exception as e:
            logger.error(f"Error fetching matches from {event_url}: {e}")
        
        return map_kills
    
    def _get_player_team_match_data(self, event_url: str, event_name: str, player_name: str, team: str) -> List[Dict]:
        """Get match-level data for PrizePicks (returns list of matches with their map kills and scores)"""
        match_data_list = []
        
        # Get all matches from this event
        matches_url = event_url.replace('/event/', '/event/matches/')
        full_url = f"{self.base_url}{matches_url}/?series_id=all"
        
        try:
            logger.info(f"Fetching matches from: {full_url}")
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find all match links
            match_pattern = re.compile(r'/\d+/[\w-]+-vs-[\w-]+')
            match_links = soup.find_all('a', href=match_pattern)
            
            seen_matches = set()
            team_lower = team.lower().replace(' ', '-').replace('.', '')
            
            # Also try common team name variations
            team_variants = [
                team_lower,
                team_lower.replace('-esports', ''),
                team_lower.replace('-', ''),
                team.lower().split()[0] if team else ''  # First word of team name
            ]
            
            for link in match_links:
                match_url = link.get('href', '')
                
                if match_url in seen_matches:
                    continue
                
                # Check if this match involves the player's team
                match_url_lower = match_url.lower()
                team_in_match = any(t in match_url_lower for t in team_variants if t)
                
                if not team_in_match:
                    continue
                
                seen_matches.add(match_url)
                
                # Scrape this match for player kills and map scores (0-kill maps = unplayed, excluded in _get_match_full_map_stats)
                match_kills, map_scores = self._get_match_map_kills_and_scores(match_url, player_name)
                # Filter out any 0-kill maps that might slip through (unplayed)
                filtered = [(k, s) for k, s in zip(match_kills, map_scores) if k is not None and k > 0]
                match_kills = [x[0] for x in filtered]
                map_scores = [x[1] for x in filtered]
                if match_kills and len(match_kills) >= 1:  # Include even 1-map matches (ongoing)
                    # Only add if at least 2 maps, or if it's an ongoing match with 1 map
                    if len(match_kills) >= 2 or len(match_kills) == 1:
                        match_data_list.append({
                            'match_url': match_url,
                            'event_name': event_name,
                            'map_kills': match_kills,
                            'map_scores': map_scores,
                            'num_maps': len(match_kills)
                        })
                        logger.info(f"  Match {match_url}: {len(match_kills)} maps, kills = {match_kills}, scores = {map_scores}")
                
        except Exception as e:
            logger.error(f"Error fetching matches from {event_url}: {e}")
        
        return match_data_list
    
    def _get_match_map_kills(self, match_url: str, player_name: str) -> List[int]:
        """Get per-map kills for a player from a specific match"""
        kills, _ = self._get_match_map_kills_and_scores(match_url, player_name)
        return kills
    
    def _get_match_map_kills_and_scores(self, match_url: str, player_name: str) -> Tuple[List[int], List[str]]:
        """Get per-map kills and scores for a player from a specific match"""
        full_stats = self._get_match_full_map_stats(match_url, player_name)
        map_kills = [stats['kills'] for stats in full_stats]
        map_scores = [stats['map_score'] for stats in full_stats]
        return map_kills, map_scores
    
    def _get_match_full_map_stats(self, match_url: str, player_name: str) -> List[Dict]:
        """
        Get comprehensive per-map stats for a player from a specific match.
        Returns a list of dicts with: kills, deaths, assists, map_name, map_score, agent, acs, adr, kast, first_bloods
        """
        map_stats = []
        full_url = f"{self.base_url}{match_url}"
        
        try:
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            player_name_lower = player_name.lower()
            
            # Find all map stat sections
            game_sections = soup.find_all('div', class_='vm-stats-game')
            
            for section in game_sections:
                game_id = section.get('data-game-id', '')
                if game_id == 'all':
                    continue
                
                # Extract map name and score from the header
                map_name = 'Unknown'
                score_text = 'N/A'
                header = section.find('div', class_='map')
                if header:
                    # Map name
                    map_name_div = header.find('div', style=lambda x: x and 'font-weight' in str(x) and '700' in str(x))
                    if map_name_div:
                        # Get text from first span
                        first_span = map_name_div.find('span')
                        if first_span:
                            map_name = first_span.get_text(strip=True)
                        else:
                            map_name = map_name_div.get_text(strip=True)
                        # Clean up whitespace and remove PICK/BAN keywords
                        map_name = ' '.join(map_name.split())
                        map_name = re.sub(r'(PICK|BAN|pick|ban)', '', map_name).strip()
                    
                    # Score - look for div.score elements (not span!)
                    score_divs = section.find_all('div', class_='score')
                    if len(score_divs) >= 2:
                        team1_score = score_divs[0].get_text(strip=True)
                        team2_score = score_divs[1].get_text(strip=True)
                        score_text = f"{team1_score}-{team2_score}"
                
                table = section.find('table')
                if not table:
                    continue
                
                tbody = table.find('tbody')
                if not tbody:
                    continue
                
                rows = tbody.find_all('tr')
                
                for row in rows:
                    player_link = row.find('a', href=re.compile(r'/player/\d+/'))
                    if not player_link:
                        continue
                    
                    link_text = player_link.get_text(strip=True).lower()
                    if player_name_lower not in link_text:
                        continue
                    
                    # Found player - extract all stats
                    # Agent: Usually in an image tag or span near the player name
                    agent = 'Unknown'
                    agent_td = row.find('td', class_='mod-agents')
                    if agent_td:
                        agent_img = agent_td.find('img')
                        if agent_img:
                            agent_alt = agent_img.get('alt', '')
                            agent_title = agent_img.get('title', '')
                            agent = agent_title or agent_alt or 'Unknown'
                            # Clean up agent name (sometimes has extra text)
                            agent = agent.split()[0] if agent else 'Unknown'
                    
                    # Get stat cells - VLR table structure:
                    # Rating, ACS, K, D, A, +/-, KAST, ADR, HS%, FK, FD, +/-
                    stat_cells = row.find_all('td', class_='mod-stat')
                    
                    stats_dict = {
                        'map_name': map_name,
                        'map_score': score_text,
                        'agent': agent,
                        'kills': 0,
                        'deaths': 0,
                        'assists': 0,
                        'acs': 0,
                        'adr': 0,
                        'kast': 0.0,
                        'first_bloods': 0
                    }
                    
                    if len(stat_cells) >= 11:
                        # Helper to extract stat value properly from mod-both span
                        def extract_cell_stat(cell):
                            both_span = cell.find('span', class_='mod-both')
                            if both_span:
                                return both_span.get_text(strip=True)
                            return cell.get_text(strip=True)
                        
                        # Rating (0), ACS (1), K (2), D (3), A (4), +/- (5), KAST (6), ADR (7), HS% (8), FK (9), FD (10)
                        try:
                            # ACS
                            stats_dict['acs'] = self._parse_number(extract_cell_stat(stat_cells[1]))
                            
                            # Kills
                            stats_dict['kills'] = self._parse_number(extract_cell_stat(stat_cells[2]))
                            
                            # Deaths
                            stats_dict['deaths'] = self._parse_number(extract_cell_stat(stat_cells[3]))
                            
                            # Assists
                            stats_dict['assists'] = self._parse_number(extract_cell_stat(stat_cells[4]))
                            
                            # KAST (percentage)
                            kast_text = extract_cell_stat(stat_cells[6]).replace('%', '')
                            stats_dict['kast'] = self._parse_float(kast_text)
                            
                            # ADR
                            stats_dict['adr'] = self._parse_number(extract_cell_stat(stat_cells[7]))
                            
                            # First Bloods (FK column)
                            stats_dict['first_bloods'] = self._parse_number(extract_cell_stat(stat_cells[9]))
                            
                        except Exception as e:
                            logger.warning(f"Error parsing stats for {player_name} on {map_name}: {e}")
                    
                    # Only add if kills are valid (exclude 0 = unplayed maps)
                    if stats_dict['kills'] > 0 and stats_dict['kills'] <= 60:
                        map_stats.append(stats_dict)
                    
                    break  # Found player in this map
                    
        except Exception as e:
            logger.error(f"Error fetching match data from {match_url}: {e}")
        
        return map_stats
    
    def _extract_player_name(self, soup: BeautifulSoup) -> str:
        """Extract player IGN from profile page"""
        try:
            name_element = soup.find('h1', class_='wf-title')
            if name_element:
                return name_element.get_text(strip=True)
        except Exception as e:
            logger.error(f"Error extracting player name: {e}")
        return "Unknown"
    
    def _extract_current_team(self, soup: BeautifulSoup) -> str:
        """Extract current team name"""
        try:
            # Look for team in player header
            team_header = soup.find('div', class_='player-header-team-name')
            if team_header:
                return team_header.get_text(strip=True)
            
            team_link = soup.find('a', href=re.compile(r'/team/\d+/'))
            if team_link:
                team_div = team_link.find('div', class_='wf-title-med')
                if team_div:
                    return team_div.get_text(strip=True)
                team_name = team_link.get_text(strip=True)
                if team_name:
                    # Clean up team name
                    team_name = team_name.split('joined')[0].strip()
                    return team_name
        except Exception as e:
            logger.error(f"Error extracting team: {e}")
        return "Unknown"
    
    def _get_player_event_kpr(self, event_url: str, player_name: str) -> Optional[Dict]:
        """Get a specific player's KPR from an event stats page"""
        stats_url = event_url
        if '/event/' in event_url and '/stats/' not in event_url:
            stats_url = event_url.replace('/event/', '/event/stats/')
        
        full_url = f"{self.base_url}{stats_url}"
        
        try:
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            
            stats_table = soup.find('table', class_='wf-table')
            if not stats_table:
                return None
            
            tbody = stats_table.find('tbody')
            if not tbody:
                return None
            
            rows = tbody.find_all('tr')
            player_name_lower = player_name.lower()
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 9:
                    continue
                
                player_cell = cols[0]
                row_player_name = ''
                
                player_link = player_cell.find('a')
                if player_link:
                    name_div = player_link.find('div', class_='text-of')
                    if name_div:
                        row_player_name = name_div.get_text(strip=True)
                    else:
                        name_div = player_link.find('div', style=lambda x: x and 'font-weight' in str(x))
                        if name_div:
                            row_player_name = name_div.get_text(strip=True)
                        else:
                            row_player_name = player_link.get_text(strip=True)
                
                if player_name_lower not in row_player_name.lower():
                    continue
                
                team_div = player_cell.find('div', class_='stats-player-country')
                team = team_div.get_text(strip=True) if team_div else ''
                
                rounds = self._parse_number(cols[2].get_text(strip=True))
                rating = self._parse_float(cols[3].get_text(strip=True))
                acs = self._parse_float(cols[4].get_text(strip=True))
                adr = self._parse_float(cols[7].get_text(strip=True))
                kpr = self._parse_float(cols[8].get_text(strip=True))
                kills = self._parse_number(cols[16].get_text(strip=True)) if len(cols) > 16 else 0
                deaths = self._parse_number(cols[17].get_text(strip=True)) if len(cols) > 17 else 0
                
                if not (0 < kpr < 2):
                    return None
                
                return {
                    'kpr': kpr,
                    'rounds_played': rounds,
                    'maps_played': 0,
                    'rating': rating,
                    'acs': acs,
                    'adr': adr,
                    'kills': kills,
                    'deaths': deaths,
                    'team': team,
                    'date': ''
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching player KPR from {event_url}: {e}")
            return None
    
    def _parse_number(self, text: str) -> int:
        try:
            cleaned = re.sub(r'[^\d]', '', text.strip())
            return int(cleaned) if cleaned else 0
        except:
            return 0
    
    def _parse_float(self, text: str) -> float:
        try:
            cleaned = re.sub(r'[^\d.\-]', '', text.strip())
            return float(cleaned) if cleaned else 0.0
        except:
            return 0.0
    
    def get_player_by_ign(self, ign: str, kill_line: float = 15.5) -> Dict:
        """Complete pipeline: search and fetch player stats"""
        logger.info(f"Searching for player: {ign}")
        player_url = self.search_player(ign)
        
        if player_url:
            logger.info(f"Found player URL: {player_url}")
            return self.get_player_stats(player_url, kill_line)
        
        logger.warning(f"Player not found: {ign}")
        return {}
    
    def get_player_prizepicks_data(self, ign: str, kill_line: float = 30.5) -> Dict:
        """Get player data for PrizePicks analysis (match-level data)"""
        logger.info(f"Searching for player (PrizePicks): {ign}")
        player_url = self.search_player(ign)
        
        if not player_url:
            logger.warning(f"Player not found: {ign}")
            return {}
        
        full_url = f"{self.base_url}{player_url}"
        
        try:
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            
            player_name = self._extract_player_name(soup)
            team = self._extract_current_team(soup)
            
            # Normalize team name for URL matching (remove accents)
            import unicodedata
            team_normalized = unicodedata.normalize('NFD', team)
            team_normalized = ''.join(c for c in team_normalized if unicodedata.category(c) != 'Mn')
            
            logger.info(f"Player: {player_name}, Team: {team} (normalized: {team_normalized})")
            
            event_stats = []
            all_match_combinations = []
            
            # 1. Check ongoing 2026 Kickoff events (always scrape live)
            kickoff_match_data = self._get_ongoing_event_match_data(player_name, team_normalized)
            if kickoff_match_data:
                event_stats.append(kickoff_match_data['event_stats'])
                all_match_combinations.extend(kickoff_match_data['match_data'])
            
            # 2. Get cached 2025 event data (all events, not just 2)
            cached_match_data = self._get_cached_event_match_data(player_name, team_normalized, tier=1)
            for match_data in cached_match_data:  # Take ALL cached events
                event_stats.append(match_data['event_stats'])
                all_match_combinations.extend(match_data['match_data'])
            
            player_data = {
                'ign': player_name,
                'team': team,
                'events': event_stats,
                'kill_line': kill_line,
                'match_combinations': all_match_combinations,
                'overall_stats': {},
                'last_updated': datetime.now().isoformat()
            }
            
            return player_data
            
        except Exception as e:
            logger.error(f"Error fetching PrizePicks data for {ign}: {e}")
            return {}
    
    def get_player_challengers_data(self, ign: str, kill_line: float = 15.5) -> Dict:
        """Get player stats from Challengers (tier 2) events only. Uses database cache."""
        logger.info(f"Searching for player (Challengers): {ign}")
        player_url = self.search_player(ign)
        if not player_url:
            logger.warning(f"Player not found: {ign}")
            return {}
        full_url = f"{self.base_url}{player_url}"
        try:
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            player_name = self._extract_player_name(soup)
            team = self._extract_current_team(soup)
            event_stats = []
            all_map_kills = []
            cached_stats = self._get_cached_event_stats(player_name, team, kill_line, tier=2)
            for stats in cached_stats[:4]:
                event_stats.append(stats)
                all_map_kills.extend(stats.get('map_kills', []))
            over_count = sum(1 for k in all_map_kills if k > kill_line)
            under_count = sum(1 for k in all_map_kills if k <= kill_line)
            total_maps = len(all_map_kills)
            over_percentage = (over_count / total_maps * 100) if total_maps > 0 else 0
            under_percentage = (under_count / total_maps * 100) if total_maps > 0 else 0
            return {
                'ign': player_name,
                'team': team,
                'events': event_stats,
                'kill_line': kill_line,
                'all_map_kills': all_map_kills,
                'over_count': over_count,
                'under_count': under_count,
                'total_maps': total_maps,
                'over_percentage': round(over_percentage, 1),
                'under_percentage': round(under_percentage, 1),
                'overall_stats': {},
                'last_updated': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error fetching Challengers data for {ign}: {e}")
            return {}
    
    def get_player_prizepicks_data_challengers(self, ign: str, kill_line: float = 30.5) -> Dict:
        """Get player data for PrizePicks analysis using Challengers (tier 2) stats only."""
        logger.info(f"Searching for player (PrizePicks Challengers): {ign}")
        player_url = self.search_player(ign)
        if not player_url:
            logger.warning(f"Player not found: {ign}")
            return {}
        full_url = f"{self.base_url}{player_url}"
        try:
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            player_name = self._extract_player_name(soup)
            team = self._extract_current_team(soup)
            import unicodedata
            team_normalized = unicodedata.normalize('NFD', team)
            team_normalized = ''.join(c for c in team_normalized if unicodedata.category(c) != 'Mn')
            event_stats = []
            all_match_combinations = []
            # 1. Check ongoing 2026 Challengers events (live scrape)
            ongoing_match_data = self._get_ongoing_challengers_event_match_data(player_name, team_normalized)
            if ongoing_match_data:
                event_stats.append(ongoing_match_data['event_stats'])
                all_match_combinations.extend(ongoing_match_data['match_data'])
            # 2. Get cached 2025 event data
            cached_match_data = self._get_cached_event_match_data(player_name, team_normalized, tier=2)
            for match_data in cached_match_data:
                event_stats.append(match_data['event_stats'])
                all_match_combinations.extend(match_data['match_data'])
            return {
                'ign': player_name,
                'team': team,
                'events': event_stats,
                'kill_line': kill_line,
                'match_combinations': all_match_combinations,
                'overall_stats': {},
                'last_updated': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error fetching PrizePicks Challengers data for {ign}: {e}")
            return {}
    
    def _get_ongoing_event_match_data(self, player_name: str, team: str) -> Optional[Dict]:
        """Get match-level data from ongoing 2026 Kickoff/International events.
        Skips events that are already completed in the DB — those are served by
        _get_cached_event_match_data instead, which prevents showing the same
        event as both LIVE and CACHED.
        """
        for kickoff in self.VCT_2026_KICKOFF_EVENTS:
            # Skip if this event is already fully cached in the DB
            if self.db:
                event_db = self.db.get_vct_event(kickoff['url'])
                if event_db and event_db.get('status') == 'completed':
                    continue
            # Check if player is in this event
            stats = self._get_player_event_kpr(kickoff['url'], player_name)
            if stats:
                # Get match-level data for this event
                match_data = self._get_player_team_match_data(kickoff['url'], kickoff['name'], player_name, team)
                
                event_stats = {
                    'event_name': kickoff['name'],
                    'event_url': kickoff['url'],
                    'kpr': stats.get('kpr', 0),
                    'rounds_played': stats.get('rounds_played', 0),
                    'rating': stats.get('rating', 0),
                    'acs': stats.get('acs', 0),
                    'cached': False
                }
                
                logger.info(f"Found player in {kickoff['name']}: {len(match_data)} matches")
                return {
                    'event_stats': event_stats,
                    'match_data': match_data
                }
        
        return None
    
    def _get_ongoing_challengers_event_match_data(self, player_name: str, team: str) -> Optional[Dict]:
        """Get match-level data from ongoing 2026 Challengers events (live scrape)"""
        for event in self.CHALLENGERS_2026_ONGOING:
            stats = self._get_player_event_kpr(event['url'], player_name)
            if stats:
                match_data = self._get_player_team_match_data(event['url'], event['name'], player_name, team)
                if match_data:
                    event_stats = {
                        'event_name': event['name'],
                        'event_url': event['url'],
                        'kpr': stats.get('kpr', 0),
                        'rounds_played': stats.get('rounds_played', 0),
                        'rating': stats.get('rating', 0),
                        'acs': stats.get('acs', 0),
                        'cached': False
                    }
                    logger.info(f"Found player in {event['name']}: {len(match_data)} matches")
                    return {
                        'event_stats': event_stats,
                        'match_data': match_data
                    }
        return None
    
    def _get_match_pick_bans(self, match_url: str) -> Dict:
        """
        Extract pick/ban sequence from match page (chronological order).
        Returns: {first_ban, second_ban, first_pick, second_pick, decider}
        """
        full_url = f"{self.base_url}{match_url}"
        result = {
            'first_ban': None,
            'second_ban': None,
            'first_pick': None,
            'second_pick': None,
            'decider': None
        }
        
        try:
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find pick/ban text in header
            candidate_texts = []
            for cls in ['match-header-note', 'match-header-vs-note', 'match-header']:
                for el in soup.find_all('div', class_=cls):
                    t = el.get_text(" ", strip=True)
                    if t and ('ban' in t.lower() or 'pick' in t.lower()):
                        candidate_texts.append(t)
            
            header_text = ''
            if candidate_texts:
                # Pick the one with most ban/pick mentions
                header_text = max(
                    candidate_texts,
                    key=lambda t: (t.lower().count('ban') + t.lower().count('pick')),
                )
            
            if header_text:
                # Extract bans and picks in order
                action_pattern = re.compile(
                    r'([A-Za-z0-9\s]+?)\s+(ban|bans|pick|picks)\s+([A-Za-z]+)',
                    re.IGNORECASE,
                )
                
                bans = []
                picks = []
                
                matches = action_pattern.findall(header_text)
                for team_str, action, map_name in matches:
                    action = action.lower()
                    map_name = map_name.strip()
                    
                    # Check if valid Valorant map
                    valorant_maps = ['Bind', 'Haven', 'Split', 'Ascent', 'Icebox', 'Breeze', 
                                    'Fracture', 'Pearl', 'Lotus', 'Sunset', 'Abyss', 'Corrode']
                    
                    if any(m.lower() == map_name.lower() for m in valorant_maps):
                        if action.startswith('ban'):
                            bans.append(map_name)
                        else:
                            picks.append(map_name)
                
                # Assign to result
                if len(bans) >= 1:
                    result['first_ban'] = bans[0]
                if len(bans) >= 2:
                    result['second_ban'] = bans[1]
                if len(picks) >= 1:
                    result['first_pick'] = picks[0]
                if len(picks) >= 2:
                    result['second_pick'] = picks[1]
                
                # Decider: look for "remains" keyword
                remains_match = re.search(r'([A-Za-z]+)\s+remains', header_text, re.IGNORECASE)
                if remains_match:
                    result['decider'] = remains_match.group(1).strip()
                    
        except Exception as e:
            logger.warning(f"Error extracting pick/bans from {match_url}: {e}")
        
        return result
    
    def get_match_result(self, match_url: str, team1: str, team2: str) -> Optional[Dict]:
        """
        Get match result (winner, map scores) from VLR match page.
        Returns {winner, team1_maps, team2_maps} or None.
        """
        full_url = f"{self.base_url}{match_url}"
        try:
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            game_sections = soup.find_all('div', class_='vm-stats-game')
            t1_wins, t2_wins = 0, 0
            t1_lower, t2_lower = team1.lower(), team2.lower()
            for section in game_sections:
                if section.get('data-game-id') == 'all':
                    continue
                score_divs = section.find_all('div', class_='score')
                if len(score_divs) >= 2:
                    try:
                        s1 = int(score_divs[0].get_text(strip=True))
                        s2 = int(score_divs[1].get_text(strip=True))
                        if s1 > s2:
                            t1_wins += 1
                        elif s2 > s1:
                            t2_wins += 1
                    except (ValueError, TypeError):
                        pass
            if t1_wins == 0 and t2_wins == 0:
                return None
            winner = team1 if t1_wins > t2_wins else team2
            return {'winner': winner, 'team1_maps': t1_wins, 'team2_maps': t2_wins}
        except Exception as e:
            logger.warning(f"Error getting match result from {match_url}: {e}")
            return None
    
    def get_match_halftime_scores(self, match_url: str) -> Optional[Dict]:
        """
        Get attack/defense round breakdown for each map in a match.

        Parses the half-time score spans (mod-t / mod-ct) from the VLR match page.
        Each map section has div.team-name elements whose parent div contains
        span.mod-t (attack rounds won) and span.mod-ct (defense rounds won).

        Returns:
            {
              "maps": [
                {
                  "map_number": 1,
                  "map_name": "Pearl",
                  "team1_name": "NRG",
                  "team2_name": "Cloud9",
                  "team1_atk": 10,
                  "team1_def": 3,
                  "team2_atk": 0,
                  "team2_def": 2,
                }
              ]
            }
            or None on failure.
        """
        full_url = f"{self.base_url}{match_url}"
        try:
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')

            maps = []
            map_number = 0
            game_sections = soup.find_all('div', class_='vm-stats-game')

            for section in game_sections:
                if section.get('data-game-id') == 'all':
                    continue

                # Extract map name
                map_name = 'Unknown'
                header = section.find('div', class_='map')
                if header:
                    map_name_div = header.find('div', style=lambda x: x and 'font-weight' in str(x) and '700' in str(x))
                    if map_name_div:
                        first_span = map_name_div.find('span')
                        if first_span:
                            map_name = first_span.get_text(strip=True)
                        else:
                            map_name = map_name_div.get_text(strip=True)
                        map_name = ' '.join(map_name.split())
                        map_name = re.sub(r'(PICK|BAN|pick|ban)', '', map_name).strip()

                # Find half-score team-name divs
                team_name_divs = section.find_all('div', class_='team-name')
                if len(team_name_divs) < 2:
                    continue

                team_halves = []
                for tnd in team_name_divs:
                    parent = tnd.parent
                    t_span = parent.find('span', class_='mod-t')
                    ct_span = parent.find('span', class_='mod-ct')
                    name = tnd.get_text(strip=True)
                    try:
                        atk = int(t_span.get_text(strip=True)) if t_span else 0
                        dfn = int(ct_span.get_text(strip=True)) if ct_span else 0
                    except (ValueError, TypeError):
                        atk, dfn = 0, 0
                    team_halves.append({'name': name, 'atk': atk, 'def': dfn})

                if len(team_halves) >= 2:
                    map_number += 1
                    maps.append({
                        'map_number': map_number,
                        'map_name': map_name,
                        'team1_name': team_halves[0]['name'],
                        'team2_name': team_halves[1]['name'],
                        'team1_atk': team_halves[0]['atk'],
                        'team1_def': team_halves[0]['def'],
                        'team2_atk': team_halves[1]['atk'],
                        'team2_def': team_halves[1]['def'],
                    })

            if not maps:
                return None

            return {'maps': maps}

        except Exception as e:
            logger.error(f"Error fetching halftime scores from {match_url}: {e}")
            return None

    def get_match_betting_odds(self, match_url: str) -> Optional[Dict]:
        """
        Scrape Thunderpick pre-match odds from a VLR match page.
        VLR displays betting links like "$100 on NRG returned $155 at pre-match odds 1.55".
        Returns decimal odds (e.g. 1.55) per team, or None if no odds found.
        
        Returns:
            {'teams': [{'name': 'NRG', 'decimal_odds': 1.55}, ...], 'source': 'Thunderpick'}
            or None if no odds found.
        """
        full_url = f"{self.base_url}{match_url}"
        odds_by_team: Dict[str, float] = {}
        try:
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            # Betting links: href contains /rr/bet/, text contains "pre-match odds X.XX"
            bet_links = soup.find_all('a', href=re.compile(r'/rr/bet/\d+'))
            odds_re = re.compile(r'pre-match odds (\d+\.\d+)')
            team_re = re.compile(r'on\s+([A-Za-z0-9\s]+?)\s+returned', re.IGNORECASE)
            for link in bet_links:
                text = link.get_text(" ", strip=True)
                m_odds = odds_re.search(text)
                m_team = team_re.search(text)
                if m_odds and m_team:
                    team_name = m_team.group(1).strip()
                    decimal_odds = float(m_odds.group(1))
                    if decimal_odds > 1.0 and team_name and abs(decimal_odds - 1.0) >= 0.01:
                        if team_name not in odds_by_team or decimal_odds < odds_by_team[team_name]:
                            odds_by_team[team_name] = decimal_odds
            if not odds_by_team:
                return None
            teams = [{'name': t, 'decimal_odds': odds_by_team[t]} for t in odds_by_team]
            return {'teams': teams, 'source': 'Thunderpick'}
        except Exception as e:
            logger.warning(f"Error fetching betting odds from {match_url}: {e}")
            return None
    
    def _get_cached_event_match_data(self, player_name: str, team: str, tier: Optional[int] = None) -> List[Dict]:
        """Get match-level data from cached completed events. tier: 1=VCT, 2=Challengers, None=all."""
        cached_events = []
        
        if not self.db:
            logger.warning("No database connection available for caching")
            return cached_events
        
        logger.info(f"Checking cache for player: {player_name} (match-level, tier={tier or 'all'})")
        db_events = self.db.get_player_all_event_stats(player_name, tier=tier)
        logger.info(f"Found {len(db_events)} cached events for {player_name}")
        
        # Process ALL events (not just 2)
        for db_event in db_events:
            event_url = db_event['event_url']
            logger.info(f"Processing event: {db_event['event_name']} ({event_url})")
            
            # Verify this is a completed event
            event_db = self.db.get_vct_event(event_url)
            if event_db and event_db.get('status') == 'completed':
                # Get match-level data from database (not scraping!)
                match_data = self.db.get_player_match_data_for_event(player_name, event_db['id'])
                logger.info(f"  Found {len(match_data)} matches for {player_name} in {db_event['event_name']}")
                
                # Skip events with no match data
                if len(match_data) == 0:
                    logger.warning(f"  Skipping {db_event['event_name']} - no match data found")
                    continue
                
                event_stats = {
                    'event_name': db_event['event_name'],
                    'event_url': event_url,
                    'kpr': db_event['kpr'],
                    'rounds_played': db_event['rounds_played'],
                    'rating': db_event['rating'],
                    'acs': db_event['acs'],
                    'cached': True
                }
                
                cached_events.append({
                    'event_stats': event_stats,
                    'match_data': match_data
                })
                logger.info(f"Loaded from cache: {db_event['event_name']} ({len(match_data)} matches)")
            else:
                logger.warning(f"  Event not found in database or not completed: {event_url}")
        
        return cached_events
