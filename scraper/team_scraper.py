# scraper/team_scraper.py
from bs4 import BeautifulSoup
import re
import logging
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TeamScraper:
    def __init__(self, database=None):
        self.base_url = Config.VLR_BASE_URL
        self.headers = Config.HEADERS
        # Remove proxy environment variables
        import os
        for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy']:
            os.environ.pop(key, None)
        self.db = database
    
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
    
    def search_team(self, team_name: str) -> Optional[str]:
        """Search for a team and return their profile URL"""
        search_url = f"{self.base_url}/search"
        params = {'q': team_name}
        
        try:
            content = self._make_request(search_url, params=params)
            soup = BeautifulSoup(content, 'html.parser')
            
            team_links = soup.find_all('a', href=re.compile(r'/team/\d+/'))
            
            for link in team_links:
                link_text = link.get_text(strip=True).lower()
                if team_name.lower() in link_text:
                    return link['href']
            
            if team_links:
                return team_links[0]['href']
                    
        except Exception as e:
            logger.error(f"Error searching for team {team_name}: {e}")
            
        return None
    
    def get_team_roster(self, team_url: str) -> List[str]:
        """Get current roster (5 players) from team page"""
        full_url = f"{self.base_url}{team_url}"
        roster = []
        
        try:
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find roster section - try multiple selectors
            roster_section = soup.find('div', class_='team-roster')
            if not roster_section:
                roster_section = soup.find('div', {'data-module': 'TeamRoster'})
            if not roster_section:
                # Try finding in team stats
                roster_section = soup.find('div', class_='team-stats-container')
            
            if roster_section:
                player_links = roster_section.find_all('a', href=re.compile(r'/player/\d+/'))
                for link in player_links[:5]:  # Get first 5 players
                    # Extract just the IGN using text-of div (same as populate_database.py)
                    name_div = link.find('div', class_='text-of')
                    if name_div:
                        player_name = name_div.get_text(strip=True)
                    else:
                        # Fallback: look for div with font-weight style
                        name_div = link.find('div', style=lambda x: x and 'font-weight' in str(x))
                        if name_div:
                            player_name = name_div.get_text(strip=True)
                        else:
                            # Last resort: take first part of text
                            full_text = link.get_text(strip=True)
                            player_name = full_text.split()[0] if full_text else ''
                    
                    if player_name and player_name not in roster:
                        roster.append(player_name)
            
            # Fallback: try finding player names in team stats table
            if not roster or len(roster) < 5:
                stats_table = soup.find('table', class_='wf-table')
                if stats_table:
                    rows = stats_table.find_all('tr')
                    for row in rows[1:6]:  # Skip header, get 5 players
                        player_link = row.find('a', href=re.compile(r'/player/\d+/'))
                        if player_link:
                            # Extract just the IGN using text-of div
                            name_div = player_link.find('div', class_='text-of')
                            if name_div:
                                player_name = name_div.get_text(strip=True)
                            else:
                                # Fallback: look for div with font-weight style
                                name_div = player_link.find('div', style=lambda x: x and 'font-weight' in str(x))
                                if name_div:
                                    player_name = name_div.get_text(strip=True)
                                else:
                                    # Last resort: take first part of text
                                    full_text = player_link.get_text(strip=True)
                                    player_name = full_text.split()[0] if full_text else ''
                            
                            if player_name and player_name not in roster:
                                roster.append(player_name)
                                if len(roster) >= 5:
                                    break
            
            # Additional fallback: look for any player links on the page
            if not roster or len(roster) < 3:
                all_player_links = soup.find_all('a', href=re.compile(r'/player/\d+/'))
                for link in all_player_links[:10]:  # Check first 10 player links
                    # Extract just the IGN using text-of div
                    name_div = link.find('div', class_='text-of')
                    if name_div:
                        player_name = name_div.get_text(strip=True)
                    else:
                        # Fallback: look for div with font-weight style
                        name_div = link.find('div', style=lambda x: x and 'font-weight' in str(x))
                        if name_div:
                            player_name = name_div.get_text(strip=True)
                        else:
                            # Last resort: take first part of text
                            full_text = link.get_text(strip=True)
                            player_name = full_text.split()[0] if full_text else ''
                    
                    if player_name and len(player_name) > 2 and player_name not in roster:
                        roster.append(player_name)
                        if len(roster) >= 5:
                            break
            
            logger.info(f"Final roster extracted (IGNs only): {roster} ({len(roster)} players)")
            
        except Exception as e:
            logger.error(f"Error getting roster from {team_url}: {e}")
        
        # Return roster as-is (already cleaned to IGNs only)
        return roster[:5]  # Return max 5 players
    
    def get_match_pick_bans(self, match_url: str, team_name: str) -> Dict:
        """
        Extract pick/ban data from a match page.
        
        IMPORTANT: The text format shows each team's FIRST action, but NOT necessarily in chronological order.
        For example: "100T ban Abyss; SEN ban Haven" means:
        - 100T's FIRST ban is Abyss
        - SEN's FIRST ban is Haven
        But we don't know which happened first chronologically.
        
        The text may show actions in any order (e.g., all of team1's actions, then team2's, or alternating).
        We collect all actions for each team and assign first_ban, second_ban, first_pick, second_pick
        based on the order they appear for that team in the text.
        """
        full_url = f"{self.base_url}{match_url}"
        result = {
            'first_ban': None,
            'second_ban': None,
            'first_pick': None,
            'second_pick': None,
            'team_side': None
        }
        
        try:
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find team names from match header
            team_names = []
            team_elements = soup.find_all('div', class_='wf-title-med')
            for elem in team_elements[:2]:
                name = elem.get_text(strip=True)
                if name and len(name) > 0:
                    team_names.append(name)
            
            # Determine which team is which
            team_name_lower = team_name.lower()
            team_index = None
            team1_name = None
            team2_name = None
            
            if team_names:
                team1_name = team_names[0]
                if len(team_names) > 1:
                    team2_name = team_names[1]
                
                # Find which team is ours
                team_variants = [
                    team_name_lower,
                    team_name_lower.replace(' ', '-'),
                    team_name_lower.replace(' ', ''),
                    team_name_lower.split()[0] if team_name else ''
                ]
                
                if team1_name:
                    team1_lower = team1_name.lower()
                    if any(variant in team1_lower or team1_lower in variant for variant in team_variants if variant):
                        team_index = 0
                        result['team_side'] = 'team1'
                
                if team_index is None and team2_name:
                    team2_lower = team2_name.lower()
                    if any(variant in team2_lower or team2_lower in variant for variant in team_variants if variant):
                        team_index = 1
                        result['team_side'] = 'team2'
            
            if team_index is None:
                logger.warning(f"Could not identify team {team_name} in match {match_url}")
                return result
            
            # Find pick/ban sequence text.
            # VLR shows something like:
            # "100T ban Abyss; SEN ban Haven; 100T pick Corrode; SEN pick Split; 100T ban Breeze; SEN ban Bind; Pearl remains"
            #
            # IMPORTANT:
            # - "100T ban Abyss" means Abyss is 100T's *first ban* (not necessarily the first ban overall).
            # - Same for picks.
            #
            # The text placement on VLR varies by layout; prefer the smallest "note" blocks first.
            candidate_texts = []
            for cls in [
                'match-header-note',
                'match-header-vs-note',
                'match-header',
                'match-summary',
                'vm-stats-game-header',
            ]:
                for el in soup.find_all('div', class_=cls):
                    t = el.get_text(" ", strip=True)
                    if t:
                        candidate_texts.append(t)
            header_text = ''
            if candidate_texts:
                header_text = max(
                    candidate_texts,
                    key=lambda t: (t.lower().count(' ban') + t.lower().count(' pick')),
                )
            
            valorant_maps = ['Bind', 'Haven', 'Split', 'Ascent', 'Icebox', 'Breeze', 'Fracture', 
                           'Pearl', 'Lotus', 'Sunset', 'Abyss', 'Corrode']
            
            if header_text:
                # Single pattern that covers: "ban/bans/pick/picks"
                action_pattern = re.compile(
                    r'([A-Za-z0-9\s]+?)\s+(ban|bans|pick|picks)\s+([A-Za-z]+)',
                    re.IGNORECASE,
                )

                actions = []  # List of (team_index, action_type, map_name)
                seen_actions = set()  # de-dupe just in case header_text contains repeats

                matches = action_pattern.findall(header_text)
                for team_str, action, map_name in matches:
                    action = action.lower()
                    action = 'ban' if action.startswith('ban') else 'pick'
                        
                    # Clean team name
                    team_str = team_str.strip().upper()
                    # Check which team this is
                    action_team_index = None
                    
                    # Try full name match first
                    if team1_name:
                        team1_upper = team1_name.upper()
                        if team1_upper in team_str or team_str in team1_upper:
                            action_team_index = 0
                    
                    if action_team_index is None and team2_name:
                        team2_upper = team2_name.upper()
                        if team2_upper in team_str or team_str in team2_upper:
                            action_team_index = 1
                    
                    # Try matching by abbreviation (first letters of each word)
                    # Common team abbreviations
                    team_abbrev_map = {
                        'EVIL GENIUSES': 'EG',
                        'SENTINELS': 'SEN',
                        'LOUD': 'LOUD',
                        'FNATIC': 'FNC',
                        'TEAM LIQUID': 'TL',
                        '100 THIEVES': '100T',
                        'CLOUD9': 'C9',
                        'NRG ESPORTS': 'NRG',
                        'G2 ESPORTS': 'G2',
                        'FURIA': 'FURIA',
                        'KR ESPORTS': 'KR',
                        'MIBR': 'MIBR'
                    }
                    
                    if action_team_index is None:
                        if team1_name:
                            team1_words = team1_name.split()
                            team1_abbrev = ''.join([w[0].upper() for w in team1_words if w])
                            # Also try common abbreviations
                            if team1_abbrev and (team1_abbrev in team_str or team_str in team1_abbrev):
                                action_team_index = 0
                            # Check for common team abbreviations
                            team1_upper_clean = team1_name.upper().strip()
                            if team1_upper_clean in team_abbrev_map:
                                abbrev = team_abbrev_map[team1_upper_clean]
                                if abbrev in team_str:
                                    action_team_index = 0
                        
                        if action_team_index is None and team2_name:
                            team2_words = team2_name.split()
                            team2_abbrev = ''.join([w[0].upper() for w in team2_words if w])
                            if team2_abbrev and (team2_abbrev in team_str or team_str in team2_abbrev):
                                action_team_index = 1
                            # Check for common team abbreviations
                            team2_upper_clean = team2_name.upper().strip()
                            if team2_upper_clean in team_abbrev_map:
                                abbrev = team_abbrev_map[team2_upper_clean]
                                if abbrev in team_str:
                                    action_team_index = 1
                        
                    if action_team_index is not None:
                        # Validate map name
                        map_name_clean = map_name.capitalize()
                        if map_name_clean in valorant_maps:
                            key = (action_team_index, action, map_name_clean)
                            if key not in seen_actions:
                                seen_actions.add(key)
                                actions.append(key)
                
                # Track THIS team's actions (first ban, second ban, first pick, second pick)
                # The text shows each team's FIRST action, but not necessarily in chronological order.
                # We collect all actions for our team in the order they appear in the text.
                team_bans = []
                team_picks = []
                
                for action_team_index, action_type, map_name in actions:
                    if action_team_index == team_index:  # This is our team's action
                        if action_type == 'ban':
                            team_bans.append(map_name)
                        elif action_type == 'pick':
                            team_picks.append(map_name)
                
                # Assign results based on order in text (first appearance = first action for that team)
                # Note: The text format shows each team's FIRST action, so team_bans[0] is the team's first ban,
                # regardless of whether it appeared first or second in the overall text sequence.
                if len(team_bans) >= 1:
                    result['first_ban'] = team_bans[0]
                if len(team_bans) >= 2:
                    result['second_ban'] = team_bans[1]
                if len(team_picks) >= 1:
                    result['first_pick'] = team_picks[0]
                if len(team_picks) >= 2:
                    result['second_pick'] = team_picks[1]
            
            # Fallback: If we can't parse the sequence, try to get from played maps
            # Played maps are picks (first played = first pick, etc.)
            if not result['first_pick']:
                game_sections = soup.find_all('div', class_='vm-stats-game')
                played_maps = []
                for section in game_sections:
                    game_id = section.get('data-game-id', '')
                    if game_id == 'all':
                        continue
                    map_elem = section.find('div', class_='map')
                    if map_elem:
                        map_name = map_elem.get_text(strip=True)
                        # Clean map name (remove any timestamps)
                        map_name = re.sub(r'\d+:\d+', '', map_name).strip()
                        if map_name and map_name.capitalize() in valorant_maps:
                            played_maps.append(map_name.capitalize())
                
                # Determine which maps our team picked (first map = team1's pick, second = team2's pick)
                if len(played_maps) >= 1:
                    if team_index == 0:  # We're team1, first map is our first pick
                        result['first_pick'] = played_maps[0]
                    elif len(played_maps) >= 2:  # We're team2, second map is our first pick
                        result['first_pick'] = played_maps[1]
                
                # NOTE: Do NOT infer second_pick from played maps.
                # In BO3, the 3rd map is a decider (not a team's "second pick"), and this inference
                # creates incorrect "second pick" rates.
            
        except Exception as e:
            logger.error(f"Error getting pick/bans from {match_url}: {e}")
        
        return result

    def _parse_number(self, text: str) -> int:
        """Parse number from text, removing non-numeric characters"""
        try:
            cleaned = re.sub(r'[^\d]', '', text.strip())
            return int(cleaned) if cleaned else 0
        except:
            return 0
    
    def _get_team_event_rounds_from_event_stats(self, event_url: str, team_name: str) -> int:
        """
        Get rounds played for a team in an event from the event stats page.

        Why: rounds played should match *any* player's RND column for that team (e.g., johnqt = 141),
        and is more reliable than inferring rounds from match pages.
        
        IMPORTANT: Only reads from the specific event URL provided, not aggregated across events.
        """
        try:
            stats_url = event_url
            if '/event/' in event_url and '/stats/' not in event_url:
                stats_url = event_url.replace('/event/', '/event/stats/')

            full_url = f"{self.base_url}{stats_url}"
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')

            # Verify we're on the correct event page by checking the page title/header
            page_title = soup.find('title')
            if page_title:
                page_title_text = page_title.get_text().lower()
                # Extract event identifier from URL to verify
                event_id_match = re.search(r'/event/(\d+)/', event_url)
                if event_id_match:
                    expected_event_id = event_id_match.group(1)
                    # Verify the page is for the correct event (basic check)
                    if expected_event_id not in full_url:
                        logger.warning(f"Event URL mismatch: expected {event_url}, got page for different event")

            table = soup.find('table', class_='wf-table')
            if not table:
                return 0
            tbody = table.find('tbody')
            if not tbody:
                return 0

            team_name_lower = (team_name or '').lower().strip()
            team_variants = {
                team_name_lower,
                team_name_lower.replace(' ', ''),
                team_name_lower.replace(' ', '-'),
                (team_name_lower.split()[0] if team_name_lower else ''),
            }
            team_variants = {v for v in team_variants if v}

            rounds_values = []
            for row in tbody.find_all('tr'):
                cols = row.find_all('td')
                if len(cols) < 4:
                    continue

                # Team label is usually in the first cell under stats-player-country
                team_div = cols[0].find('div', class_='stats-player-country')
                row_team = team_div.get_text(strip=True).lower() if team_div else ''
                if row_team and not any(v in row_team or row_team in v for v in team_variants):
                    continue

                # Rounds column is the same index used elsewhere in this repo (cols[2])
                rounds = self._parse_number(cols[2].get_text(strip=True))
                if rounds > 0:
                    rounds_values.append(rounds)

            # All players from the same team in the same event should have the same rounds
            # Return the most common value (or max if all different, which shouldn't happen)
            if rounds_values:
                # Use the most common value (should be consistent for all team players)
                from collections import Counter
                rounds_counter = Counter(rounds_values)
                most_common_rounds = rounds_counter.most_common(1)[0][0]
                logger.info(f"Team {team_name} in event {event_url}: Found rounds values {rounds_values}, using {most_common_rounds}")
                return most_common_rounds
            return 0
        except Exception as e:
            logger.error(f"Error reading team rounds from event stats {event_url}: {e}")
            return 0
    
    def get_team_match_stats(self, match_url: str, team_name: str, roster: List[str]) -> Dict:
        """
        Get team stats from a match using the same approach as player scraper.
        Returns: {
            'total_kills': int,
            'total_deaths': int,
            'total_rounds': int,
            'maps': [{'map_name': str, 'kills': int, 'deaths': int, 'rounds': int}]
        }
        """
        full_url = f"{self.base_url}{match_url}"
        result = {
            'total_kills': 0,
            'total_deaths': 0,
            'total_rounds': 0,
            'maps': []
        }
        
        try:
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find all map sections (same as player scraper)
            # Process ALL game sections, including individual maps
            game_sections = soup.find_all('div', class_='vm-stats-game')
            
            logger.info(f"Found {len(game_sections)} game sections in match {match_url}")
            
            for section in game_sections:
                game_id = section.get('data-game-id', '')
                if game_id == 'all':
                    continue  # Skip aggregate stats
                
                # Get map name - try multiple selectors
                map_name_elem = section.find('div', class_='map')
                if not map_name_elem:
                    map_name_elem = section.find('span', class_='map')
                if not map_name_elem:
                    # Try finding in header
                    header = section.find('div', class_='vm-stats-game-header')
                    if header:
                        map_name_elem = header.find('div', class_='map')
                
                map_name = None
                if map_name_elem:
                    map_name = map_name_elem.get_text(strip=True)
                    # Clean map name (remove timestamps, extra text)
                    map_name = re.sub(r'\d+:\d+', '', map_name).strip()
                    map_name = re.sub(r'PICK|BAN', '', map_name, flags=re.IGNORECASE).strip()
                
                if not map_name or len(map_name) < 3:
                    # Fallback: use game_id or try to extract from section
                    map_name = f"Map {game_id}" if game_id else "Unknown Map"
                
                logger.debug(f"Processing map: {map_name} (game_id: {game_id})")
                
                # Get stats tables (same approach as populate_database.py - process ALL tables)
                # We'll identify our team's table by matching roster players, not team names
                tables = section.find_all('table')
                if not tables:
                    logger.info(f"No tables found in map {map_name}")
                    continue
                
                logger.info(f"Found {len(tables)} tables in map {map_name}")
                
                # Process all tables to find our team's table
                # In VLR, there are usually 2 tables (one per team) or sometimes combined
                map_kills = 0
                map_deaths = 0
                rounds = 0
                
                # Get rounds from score first.
                # VLR usually renders 2 separate score elements (one per team), so we must sum them.
                # Example: 13-11 => 24 rounds.
                score_divs = section.find_all('div', class_='score')
                score_nums = []
                for score_div in score_divs:
                    m = re.search(r'\d+', score_div.get_text())
                    if m:
                        score_nums.append(int(m.group()))
                if len(score_nums) >= 2:
                    rounds = score_nums[0] + score_nums[1]
                
                # Try to find our team's table
                team_table = None
                roster_lower = [p.lower().strip() for p in roster]
                
                for table in tables:
                    # Check if this table belongs to our team by checking player names
                    tbody = table.find('tbody')
                    if not tbody:
                        continue
                    
                    rows = tbody.find_all('tr')
                    # Check if any player in this table matches our roster
                    found_roster_player = False
                    players_matched = 0
                    
                    for row in rows:
                        player_link = row.find('a', href=re.compile(r'/player/\d+/'))
                        if player_link:
                            # Extract player name properly
                            name_div = player_link.find('div', class_='text-of')
                            if name_div:
                                player_name_clean = name_div.get_text(strip=True).lower()
                            else:
                                player_name = player_link.get_text(strip=True)
                                player_name_clean = player_name.split('\n')[0].strip().lower()
                            
                            # Check if this player is in our roster
                            for roster_player_clean in roster_lower:
                                if roster_player_clean == player_name_clean or \
                                   roster_player_clean in player_name_clean or \
                                   player_name_clean in roster_player_clean:
                                    players_matched += 1
                                    found_roster_player = True
                                    break
                    
                    # If we found at least 2 roster players, this is likely our team's table
                    if players_matched >= 2:
                        team_table = table
                        logger.debug(f"Found team table by roster match: {players_matched} players matched")
                        break
                    elif found_roster_player and not team_table:
                        # Keep this as a candidate but continue looking for better match
                        team_table = table
                
                # Fallback: if we have 2 tables and roster matching didn't work, try both tables
                if not team_table and len(tables) >= 2:
                    # Try both tables and pick the one with more roster matches
                    best_match_count = 0
                    for table in tables:
                        tbody = table.find('tbody')
                        if not tbody:
                            continue
                        rows = tbody.find_all('tr')
                        match_count = 0
                        for row in rows:
                            player_link = row.find('a', href=re.compile(r'/player/\d+/'))
                            if player_link:
                                name_div = player_link.find('div', class_='text-of')
                                if name_div:
                                    player_name_clean = name_div.get_text(strip=True).lower()
                                else:
                                    full_text = player_link.get_text(strip=True)
                                    player_name_clean = full_text.split()[0].lower() if full_text else ''
                                
                                for roster_player_clean in roster_lower:
                                    if roster_player_clean == player_name_clean or \
                                       roster_player_clean in player_name_clean or \
                                       player_name_clean in roster_player_clean:
                                        if len(roster_player_clean) >= 3 and len(player_name_clean) >= 3:
                                            match_count += 1
                                            break
                        
                        if match_count > best_match_count:
                            best_match_count = match_count
                            team_table = table
                    
                    if best_match_count > 0:
                        logger.debug(f"Found team table via fallback: {best_match_count} players matched")
                elif not team_table and len(tables) == 1:
                    team_table = tables[0]
                
                if not team_table:
                    logger.debug(f"Could not find team table for {team_name} in map {map_name}")
                    continue
                
                tbody = team_table.find('tbody')
                if not tbody:
                    continue
                
                rows = tbody.find_all('tr')
                
                # Sum kills and deaths for roster players
                # roster_lower is already defined above
                players_found = 0
                all_player_names = []  # Track all player names found for debugging
                logger.info(f"Looking for roster players: {roster_lower} in map {map_name}")
                
                for row in rows:
                    player_link = row.find('a', href=re.compile(r'/player/\d+/'))
                    if not player_link:
                        continue
                    
                    # Extract player name properly (same as populate_database.py)
                    name_div = player_link.find('div', class_='text-of')
                    if name_div:
                        player_name_clean = name_div.get_text(strip=True).lower()
                    else:
                        # Fallback: look for div with font-weight style
                        name_div = player_link.find('div', style=lambda x: x and 'font-weight' in str(x))
                        if name_div:
                            player_name_clean = name_div.get_text(strip=True).lower()
                        else:
                            # Last resort: take first part of text (before team name)
                            full_text = player_link.get_text(strip=True)
                            player_name_clean = full_text.split()[0].lower() if full_text else ''
                    
                    if not player_name_clean:
                        continue
                    
                    all_player_names.append(player_name_clean)
                    
                    # Check if player is in roster (flexible matching)
                    matched = False
                    for roster_player_clean in roster_lower:
                        # Exact match
                        if roster_player_clean == player_name_clean:
                            matched = True
                            players_found += 1
                            logger.info(f"✓ Matched player: {player_name_clean} == {roster_player_clean}")
                            break
                        # Substring match (IGN in full name or vice versa)
                        elif roster_player_clean in player_name_clean or player_name_clean in roster_player_clean:
                            # Additional check: make sure it's not too short (avoid false matches)
                            if len(roster_player_clean) >= 3 and len(player_name_clean) >= 3:
                                matched = True
                                players_found += 1
                                logger.info(f"✓ Matched player: {player_name_clean} contains {roster_player_clean}")
                                break
                    
                    if not matched:
                        continue
                    
                    # Extract kills and deaths (same approach as populate_database.py)
                    stat_cells = row.find_all('td', class_='mod-stat')
                    if len(stat_cells) >= 4:
                        # Column order: R, ACS, K, D, A, ...
                        # K column (index 2)
                        k_cell = stat_cells[2]
                        both_span = k_cell.find('span', class_='mod-both')
                        if both_span:
                            kills_text = both_span.get_text(strip=True)
                        else:
                            kills_text = k_cell.get_text(strip=True)
                        
                        numbers = re.findall(r'\d+', kills_text)
                        if numbers:
                            kill_value = int(numbers[0])
                            if 0 <= kill_value <= 60:  # Sanity check
                                map_kills += kill_value
                        
                        # D column (index 3)
                        d_cell = stat_cells[3]
                        both_span = d_cell.find('span', class_='mod-both')
                        if both_span:
                            deaths_text = both_span.get_text(strip=True)
                        else:
                            deaths_text = d_cell.get_text(strip=True)
                        
                        numbers = re.findall(r'\d+', deaths_text)
                        if numbers:
                            death_value = int(numbers[0])
                            if 0 <= death_value <= 60:  # Sanity check
                                map_deaths += death_value
                
                logger.info(f"Map {map_name}: Found {len(all_player_names)} total players: {all_player_names}")
                logger.info(f"Map {map_name}: Matched {players_found}/{len(roster)} roster players")
                
                # If we found roster players, add the map stats
                # Always add the map if we found at least some players (even if stats are 0)
                # This ensures we count all maps played
                if players_found > 0:
                    # If rounds not found, try to recover from score or use default
                    if rounds == 0:
                        # Try again (sometimes the first lookup hits a weird container)
                        score_divs = section.find_all('div', class_='score')
                        score_nums = []
                        for score_div in score_divs:
                            m = re.search(r'\d+', score_div.get_text())
                            if m:
                                score_nums.append(int(m.group()))
                        if len(score_nums) >= 2:
                            rounds = score_nums[0] + score_nums[1]

                        # If still no rounds, do NOT estimate from kills/deaths (that produced inflated totals).
                        # Use a conservative default to avoid obviously wrong data.
                        if rounds == 0:
                            rounds = 24
                    
                    logger.debug(f"Map {map_name}: Found {players_found}/{len(roster)} players, Kills: {map_kills}, Deaths: {map_deaths}, Rounds: {rounds}")
                    
                    result['maps'].append({
                        'map_name': map_name,
                        'kills': map_kills,
                        'deaths': map_deaths,
                        'rounds': rounds if rounds > 0 else 24  # Default to 24 if still 0
                    })
                    result['total_kills'] += map_kills
                    result['total_deaths'] += map_deaths
                    result['total_rounds'] += (rounds if rounds > 0 else 24)
                else:
                    logger.warning(f"Map {map_name}: No roster players found, skipping stats. Roster: {roster_lower}, Found players: {all_player_names if 'all_player_names' in locals() else 'N/A'}")
        
        except Exception as e:
            logger.error(f"Error getting team match stats from {match_url}: {e}")
        
        return result
    
    def _get_cached_team_event_stats(self, team_name: str, event_url: str) -> Optional[Dict]:
        """Get cached team stats from database for completed events"""
        if not self.db:
            return None
        
        try:
            import sqlite3
            # Get event from database
            event = self.db.get_vct_event(event_url)
            if not event or event.get('status') != 'completed':
                return None
            
            # Get team event stats
            conn = sqlite3.connect(self.db.db_path, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT fights_per_round, total_kills, total_deaths, total_rounds, matches_played
                FROM team_event_stats
                WHERE event_id = ? AND team_name = ?
            ''', (event['id'], team_name.lower()))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'fights_per_round': row[0],
                    'total_kills': row[1],
                    'total_deaths': row[2],
                    'total_rounds': row[3],
                    'matches_played': row[4]
                }
        except Exception as e:
            logger.error(f"Error getting cached team stats: {e}")
        
        return None
    
    def _get_cached_team_pick_bans(self, team_name: str, event_id: int) -> Dict:
        """Get cached pick/ban data from database"""
        pick_bans = {
            'first_ban': {},
            'second_ban': {},
            'first_pick': {},
            'second_pick': {}
        }
        
        if not self.db:
            return pick_bans
        
        try:
            import sqlite3
            conn = sqlite3.connect(self.db.db_path, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT first_ban, second_ban, first_pick, second_pick
                FROM team_pick_bans
                WHERE match_id IN (
                    SELECT id FROM matches WHERE event_id = ?
                ) AND team_name = ?
            ''', (event_id, team_name.lower()))
            
            for row in cursor.fetchall():
                if row[0]:  # first_ban
                    pick_bans['first_ban'][row[0]] = pick_bans['first_ban'].get(row[0], 0) + 1
                if row[1]:  # second_ban
                    pick_bans['second_ban'][row[1]] = pick_bans['second_ban'].get(row[1], 0) + 1
                if row[2]:  # first_pick
                    pick_bans['first_pick'][row[2]] = pick_bans['first_pick'].get(row[2], 0) + 1
                if row[3]:  # second_pick
                    pick_bans['second_pick'][row[3]] = pick_bans['second_pick'].get(row[3], 0) + 1
            
            conn.close()
        except Exception as e:
            logger.error(f"Error getting cached pick/bans: {e}")
        
        return pick_bans
    
    def get_team_events_data(self, team_name: str, region: str = None) -> Dict:
        """
        Get team data for current event + past 2 events.
        Uses database cache for completed events, scrapes live for current event.
        """
        # Search for team
        team_url = self.search_team(team_name)
        if not team_url:
            return {'error': 'Team not found'}
        
        # Get roster
        roster = self.get_team_roster(team_url)
        logger.info(f"Found roster for {team_name}: {roster} ({len(roster)} players)")
        if len(roster) < 3:
            logger.warning(f"Team {team_name} has less than 3 players in roster: {roster}")
        
        # Determine which events to scrape (current + past 2)
        from scraper.vlr_scraper import VLRScraper
        
        # Current event (2026 Kickoff) - always scrape live
        current_event = None
        for event in VLRScraper.VCT_2026_KICKOFF_EVENTS:
            if not region or event['region'] == region:
                current_event = event
                break
        
        # Past 2 events (2025 Stage 2 and Stage 1) - use cache
        past_events = []
        for event in VLRScraper.VCT_2025_EVENTS:
            if not region or event['region'] == region:
                past_events.append(event)
                if len(past_events) >= 2:
                    break
        
        events_to_process = []
        if current_event:
            events_to_process.append(('live', current_event))
        for event in past_events:
            events_to_process.append(('cached', event))
        
        events_data = []
        
        for event_type, event in events_to_process:
            event_data = {
                'event_name': event['name'],
                'event_url': event['url'],
                'region': event['region'],
                'roster': roster,
                'fights_per_round': 0,
                'total_kills': 0,
                'total_deaths': 0,
                'total_rounds': 0,
                'matches_played': 0,
                'pick_bans': {
                    'first_ban': {},
                    'second_ban': {},
                    'first_pick': {},
                    'second_pick': {}
                },
                'cached': event_type == 'cached'
            }
            
            # Try to get from cache first for completed events
            # IMPORTANT: Never use cache for live events - always scrape fresh
            if event_type == 'cached':
                cached_stats = self._get_cached_team_event_stats(team_name, event['url'])
                if cached_stats:
                    event_data.update(cached_stats)
                    # Get cached pick/bans
                    event_db = self.db.get_vct_event(event['url'])
                    if event_db:
                        cached_pick_bans = self._get_cached_team_pick_bans(team_name, event_db['id'])
                        event_data['pick_bans'] = cached_pick_bans
                    events_data.append(event_data)
                    continue
            
            # For live events, always scrape fresh (never use cache)
            # This ensures we get the most up-to-date data and don't use incorrect cached values
            # Clear any existing cached data for this event to prevent stale data
            if event_type == 'live' and self.db:
                try:
                    import sqlite3
                    event_db = self.db.get_vct_event(event['url'])
                    if event_db:
                        conn = sqlite3.connect(self.db.db_path, timeout=30.0)
                        cursor = conn.cursor()
                        # Delete cached team stats for this event to force fresh scrape
                        cursor.execute('''
                            DELETE FROM team_event_stats
                            WHERE event_id = ? AND team_name = ?
                        ''', (event_db['id'], team_name.lower()))
                        conn.commit()
                        logger.info(f"Cleared cached team stats for {team_name} in event {event['name']} to force fresh scrape")
                        conn.close()
                except Exception as e:
                    logger.error(f"Error clearing cached team stats: {e}")
            
            # Scrape live (for current event or if cache miss)
            matches_url = event['url'].replace('/event/', '/event/matches/')
            full_matches_url = f"{self.base_url}{matches_url}/?series_id=all"
            
            try:
                content = self._make_request(full_matches_url)
                soup = BeautifulSoup(content, 'html.parser')
                
                # Find all match links - try multiple patterns
                match_patterns = [
                    re.compile(r'/\d+/[\w-]+-vs-[\w-]+'),
                    re.compile(r'/match/\d+'),
                    re.compile(r'/\d+/.*vs.*')
                ]
                
                match_links = []
                for pattern in match_patterns:
                    links = soup.find_all('a', href=pattern)
                    match_links.extend(links)
                
                # Remove duplicates
                seen_urls = set()
                unique_links = []
                for link in match_links:
                    url = link.get('href', '')
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        unique_links.append(link)
                
                match_links = unique_links
                logger.info(f"Found {len(match_links)} total match links for event {event['name']}")
                
                team_matches = []
                # Create more comprehensive team name variants for matching
                team_name_lower = team_name.lower().strip()
                team_name_variants = [
                    team_name_lower.replace(' ', '-').replace('.', '').replace("'", ''),
                    team_name_lower.replace(' ', '').replace('.', '').replace("'", ''),
                    team_name_lower.replace(' ', '-'),
                    team_name_lower.replace(' ', ''),
                    team_name_lower.split()[0] if team_name else '',
                    # Common abbreviations
                    'sentinels' if 'sentinel' in team_name_lower else None,
                    'eg' if 'evil geniuses' in team_name_lower or 'evil-geniuses' in team_name_lower else None,
                    'loud' if team_name_lower == 'loud' else None,
                    'fnatic' if team_name_lower == 'fnatic' else None,
                ]
                team_name_variants = [v for v in team_name_variants if v]  # Remove None values
                logger.info(f"Looking for team variants: {team_name_variants}")
                
                for link in match_links:
                    match_url = link.get('href', '')
                    match_url_lower = match_url.lower()
                    link_text = link.get_text(strip=True).lower()
                    
                    # Check if this match involves our team
                    # Try both URL and link text
                    matched = False
                    for variant in team_name_variants:
                        if variant:
                            # Check URL
                            if variant in match_url_lower or match_url_lower in variant:
                                matched = True
                                break
                            # Check link text (team names might be in the displayed text)
                            if variant in link_text or link_text in variant:
                                matched = True
                                break
                    
                    if matched:
                        team_matches.append(match_url)
                        logger.debug(f"Found matching match: {match_url} (text: {link_text})")
                
                logger.info(f"Found {len(team_matches)} matches for team {team_name} in event {event['name']}")
                
                # Process each match
                seen_matches = set()
                matches_processed = []
                for match_url in team_matches:
                    # Normalize match URL to avoid duplicates
                    match_url_normalized = match_url
                    if not match_url_normalized.startswith('/'):
                        match_url_normalized = '/' + match_url_normalized
                    
                    if match_url_normalized in seen_matches:
                        logger.debug(f"Skipping duplicate match: {match_url}")
                        continue
                    seen_matches.add(match_url_normalized)
                    
                    # Verify match URL belongs to this event (basic check)
                    # Event URL format: /event/2682/vct-2026-americas-kickoff
                    # Match URLs should be relative paths like /123456/team1-vs-team2
                    # We can't easily verify event ID in match URL, but we trust the matches page
                    # since it's constructed from the event URL
                    
                    # Get match stats
                    logger.info(f"Processing match {match_url_normalized} for team {team_name} in event {event['name']}")
                    match_stats = self.get_team_match_stats(match_url_normalized, team_name, roster)
                    logger.info(f"Match {match_url_normalized} returned {len(match_stats['maps'])} maps, {match_stats['total_kills']} kills, {match_stats['total_deaths']} deaths, {match_stats['total_rounds']} rounds")
                    
                    # Only count match if we found at least one map with stats AND the match has been played
                    # Unplayed matches (TBD, scheduled) will have 0 kills/deaths
                    match_has_stats = len(match_stats['maps']) > 0
                    match_has_been_played = match_stats['total_kills'] > 0 or match_stats['total_deaths'] > 0
                    
                    logger.info(f"Match {match_url_normalized}: has_stats={match_has_stats}, has_been_played={match_has_been_played}, kills={match_stats['total_kills']}, deaths={match_stats['total_deaths']}, maps={len(match_stats['maps'])}, rounds={match_stats['total_rounds']}")
                    
                    if match_has_stats and match_has_been_played:
                        event_data['total_kills'] += match_stats['total_kills']
                        event_data['total_deaths'] += match_stats['total_deaths']
                        event_data['total_rounds'] += match_stats['total_rounds']
                        event_data['matches_played'] += 1
                        matches_processed.append({
                            'url': match_url_normalized,
                            'maps': len(match_stats['maps']),
                            'rounds': match_stats['total_rounds'],
                            'kills': match_stats['total_kills'],
                            'deaths': match_stats['total_deaths']
                        })
                        logger.info(f"✓ Counted match {match_url_normalized}: {len(match_stats['maps'])} maps, {match_stats['total_kills']} kills, {match_stats['total_deaths']} deaths, {match_stats['total_rounds']} rounds")
                        
                        # Get pick/bans (only if we have map data and match was played)
                        pick_bans = self.get_match_pick_bans(match_url_normalized, team_name)
                        
                        # Track pick/ban rates
                        if pick_bans['first_ban']:
                            map_name = pick_bans['first_ban']
                            event_data['pick_bans']['first_ban'][map_name] = event_data['pick_bans']['first_ban'].get(map_name, 0) + 1
                        
                        if pick_bans['second_ban']:
                            map_name = pick_bans['second_ban']
                            event_data['pick_bans']['second_ban'][map_name] = event_data['pick_bans']['second_ban'].get(map_name, 0) + 1
                        
                        if pick_bans['first_pick']:
                            map_name = pick_bans['first_pick']
                            event_data['pick_bans']['first_pick'][map_name] = event_data['pick_bans']['first_pick'].get(map_name, 0) + 1
                        
                        if pick_bans['second_pick']:
                            map_name = pick_bans['second_pick']
                            event_data['pick_bans']['second_pick'][map_name] = event_data['pick_bans']['second_pick'].get(map_name, 0) + 1
                        
                        # Save to database if current event
                        if event_type == 'live' and self.db:
                            try:
                                import sqlite3
                                event_db = self.db.get_vct_event(event['url'])
                                if event_db:
                                    match_db = self.db.get_match(match_url_normalized)
                                    if match_db:
                                        conn = sqlite3.connect(self.db.db_path, timeout=30.0)
                                        cursor = conn.cursor()
                                        cursor.execute('''
                                            INSERT OR REPLACE INTO team_pick_bans
                                            (match_id, team_name, first_ban, second_ban, first_pick, second_pick)
                                            VALUES (?, ?, ?, ?, ?, ?)
                                        ''', (
                                            match_db['id'],
                                            team_name.lower(),
                                            pick_bans['first_ban'],
                                            pick_bans['second_ban'],
                                            pick_bans['first_pick'],
                                            pick_bans['second_pick']
                                        ))
                                        conn.commit()
                                        conn.close()
                            except Exception as e:
                                logger.error(f"Error saving pick/bans to database: {e}")
                    elif not match_has_stats:
                        logger.warning(f"✗ Skipped match {match_url_normalized}: No maps found with stats")
                    elif not match_has_been_played:
                        logger.info(f"✗ Skipped match {match_url_normalized}: Match not yet played (0 kills/deaths) - likely scheduled/TBD")
                    else:
                        logger.warning(f"✗ Skipped match {match_url_normalized}: Unknown reason")
                
                logger.info(f"Event {event['name']}: Processed {len(matches_processed)} matches. Total: {event_data['matches_played']} matches, {event_data['total_rounds']} rounds")
                if matches_processed:
                    logger.info(f"Match details: {matches_processed}")
                    
                    # Save to database if current event
                    if event_type == 'live' and self.db:
                        try:
                            import sqlite3
                            event_db = self.db.get_vct_event(event['url'])
                            if event_db:
                                match_db = self.db.get_match(match_url)
                                if match_db:
                                    conn = sqlite3.connect(self.db.db_path, timeout=30.0)
                                    cursor = conn.cursor()
                                    cursor.execute('''
                                        INSERT OR REPLACE INTO team_pick_bans
                                        (match_id, team_name, first_ban, second_ban, first_pick, second_pick)
                                        VALUES (?, ?, ?, ?, ?, ?)
                                    ''', (
                                        match_db['id'],
                                        team_name.lower(),
                                        pick_bans['first_ban'],
                                        pick_bans['second_ban'],
                                        pick_bans['first_pick'],
                                        pick_bans['second_pick']
                                    ))
                                    conn.commit()
                                    conn.close()
                        except Exception as e:
                            logger.error(f"Error saving pick/bans to database: {e}")
                
                # Calculate fights per round
                # IMPORTANT: Always use match-calculated rounds for accuracy
                # Event stats page may include data from other events or be incorrect
                match_calculated_rounds = event_data['total_rounds']
                
                # For LIVE events, log event stats for debugging but NEVER use them
                # Event stats can be wrong (include other events, wrong team, etc.)
                if event_type == 'live' and match_calculated_rounds > 0:
                    stats_rounds = self._get_team_event_rounds_from_event_stats(event['url'], team_name)
                    if stats_rounds > 0:
                        diff_percent = abs(stats_rounds - match_calculated_rounds) / max(match_calculated_rounds, 1) * 100
                        logger.info(f"Event stats rounds: {stats_rounds}, Match-calculated rounds: {match_calculated_rounds} (diff: {diff_percent:.1f}%) - Using match-calculated")
                        if diff_percent > 10:
                            logger.warning(f"⚠️ Event stats rounds ({stats_rounds}) differs from match-calculated ({match_calculated_rounds}). Using match-calculated for accuracy.")
                    # Always use match-calculated rounds - never override
                elif event_type == 'live' and match_calculated_rounds == 0:
                    # Fallback: if no match-calculated rounds, try event stats but warn
                    stats_rounds = self._get_team_event_rounds_from_event_stats(event['url'], team_name)
                    if stats_rounds > 0:
                        event_data['total_rounds'] = stats_rounds
                        logger.warning(f"⚠️ No match-calculated rounds found. Using event stats rounds: {stats_rounds} (may be inaccurate - check if matches were processed correctly)")

                if event_data['total_rounds'] > 0:
                    event_data['fights_per_round'] = (event_data['total_kills'] + event_data['total_deaths']) / event_data['total_rounds']
                
                # Save team event stats to database if current event
                if event_type == 'live' and self.db:
                    try:
                        import sqlite3
                        event_db = self.db.get_vct_event(event['url'])
                        if event_db:
                            conn = sqlite3.connect(self.db.db_path, timeout=30.0)
                            cursor = conn.cursor()
                            cursor.execute('''
                                INSERT OR REPLACE INTO team_event_stats
                                (event_id, team_name, fights_per_round, total_kills, total_deaths, total_rounds, matches_played)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                event_db['id'],
                                team_name.lower(),
                                event_data['fights_per_round'],
                                event_data['total_kills'],
                                event_data['total_deaths'],
                                event_data['total_rounds'],
                                event_data['matches_played']
                            ))
                            conn.commit()
                            conn.close()
                    except Exception as e:
                        logger.error(f"Error saving team event stats to database: {e}")
                
                events_data.append(event_data)
                
            except Exception as e:
                logger.error(f"Error processing event {event['name']}: {e}")
        
        return {
            'team_name': team_name,
            'team_url': team_url,
            'roster': roster,
            'events': events_data
        }
