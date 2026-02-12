# scraper/vlr_scraper.py
import requests
from bs4 import BeautifulSoup
import re
import time
import logging
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VLRScraper:
    def __init__(self, database=None):
        self.base_url = Config.VLR_BASE_URL
        self.headers = Config.HEADERS
        # Remove proxy environment variables to bypass proxy issues
        import os
        for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy']:
            os.environ.pop(key, None)
        # Use requests session but with proxies disabled
        self.session = requests.Session()
        self.session.proxies = {}
        # Also ignore any environment proxy settings (belt-and-suspenders)
        self.session.trust_env = False
        self.db = database  # Optional database for caching
    
    def _make_request(self, url: str, params: dict = None) -> bytes:
        """Make HTTP request using urllib to completely bypass proxy"""
        if params:
            from urllib.parse import urlencode
            url = f"{url}?{urlencode(params)}"
        req = urllib.request.Request(url, headers=self.headers)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            response = opener.open(req, timeout=30)
            return response.read()
        except urllib.error.URLError as e:
            raise Exception(f"Request failed: {e}")
        
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
        # Don't use first-result fallback for placeholder names (OCR failed to match)
        if player_links and len(query) >= 2 and not query_lower.startswith('player_'):
            return player_links[0]['href']
        return None

    def search_player(self, player_name: str) -> Optional[str]:
        """Search for a player and return their profile URL. Tries OCR-style alt spellings if needed."""
        search_url = f"{self.base_url}/search"
        params = {'q': player_name}
        
        try:
            content = self._make_request(search_url, params=params)
            soup = BeautifulSoup(content, 'html.parser')
            
            url = self._try_search(soup, player_name)
            if url:
                return url
            
            # OCR often confuses: 1/l/I, 0/O, 4/A. Try alternates when search fails
            alternates = []
            if '1' in player_name:
                alternates.append(player_name.replace('1', 'l'))
            if 'l' in player_name:
                alternates.append(player_name.replace('l', '1', 1))
            if '0' in player_name:
                alternates.append(player_name.replace('0', 'o'))
            if 'o' in player_name and '0' not in player_name:
                alternates.append(player_name.replace('o', '0', 1))
            if '4' in player_name:
                alternates.append(player_name.replace('4', 'a'))
            if 'a' in player_name and '4' not in player_name:
                alternates.append(player_name.replace('a', '4', 1))
            
            for alt in alternates:
                if alt == player_name:
                    continue
                params = {'q': alt}
                content = self._make_request(search_url, params=params)
                soup = BeautifulSoup(content, 'html.parser')
                url = self._try_search(soup, alt)
                if url:
                    return url
                    
        except Exception as e:
            logger.error(f"Error searching for player {player_name}: {e}")
            
        return None
    
    # Current ongoing VCT 2026 Kickoff events
    VCT_2026_KICKOFF_EVENTS = [
        {'name': 'VCT 2026: Americas Kickoff', 'url': '/event/2682/vct-2026-americas-kickoff', 'region': 'Americas'},
        {'name': 'VCT 2026: EMEA Kickoff', 'url': '/event/2684/vct-2026-emea-kickoff', 'region': 'EMEA'},
        {'name': 'VCT 2026: Pacific Kickoff', 'url': '/event/2683/vct-2026-pacific-kickoff', 'region': 'Pacific'},
        {'name': 'VCT 2026: China Kickoff', 'url': '/event/2685/vct-2026-china-kickoff', 'region': 'China'},
    ]
    
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
            cached_stats = self._get_cached_event_stats(player_name, team, kill_line)
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
    
    def _get_cached_event_stats(self, player_name: str, team: str, kill_line: float) -> List[Dict]:
        """
        Get cached event stats from database for COMPLETED events only.
        Completed events should NEVER be scraped live - only use cache.
        If cache is empty, return empty list (don't scrape completed events).
        """
        cached_events = []
        
        # Check database for cached data from COMPLETED events only
        if self.db:
            logger.info(f"Checking cache for player: {player_name} (completed events only)")
            # Get all cached event stats for this player from completed events
            db_events = self.db.get_player_all_event_stats(player_name)
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
            cached_match_data = self._get_cached_event_match_data(player_name, team_normalized)
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
    
    def _get_ongoing_event_match_data(self, player_name: str, team: str) -> Optional[Dict]:
        """Get match-level data from ongoing 2026 Kickoff events"""
        for kickoff in self.VCT_2026_KICKOFF_EVENTS:
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
    
    def _get_cached_event_match_data(self, player_name: str, team: str) -> List[Dict]:
        """Get match-level data from cached completed events"""
        cached_events = []
        
        if not self.db:
            logger.warning("No database connection available for caching")
            return cached_events
        
        logger.info(f"Checking cache for player: {player_name} (match-level data)")
        
        # Get all cached event stats for this player from completed events
        db_events = self.db.get_player_all_event_stats(player_name)
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
