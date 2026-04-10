# scripts/populate_database.py
"""
Comprehensive database population script for 2025 VCT event data.

This script:
1. Scrapes all 2025 VCT events from VLR.gg
2. For each event, gets all matches
3. For each match, extracts comprehensive player stats per map:
   - Map name (Bind, Haven, etc.)
   - Agent played
   - Kills, Deaths, Assists
   - ACS (Average Combat Score)
   - ADR (Average Damage per Round)
   - KAST (Kill, Assist, Survive, Trade %)
   - First Bloods
   - Map score (e.g., "13-6")
4. Extracts match pick/ban sequences (first_ban, second_ban, first_pick, second_pick, decider)
5. Stores everything in the SQLite database

Run this to populate/repopulate the cache with comprehensive stats.
The main app will use cached data for completed events and only scrape ongoing events.
"""

import sys
import os
import re
import time
import logging
import urllib.request
import urllib.error
from bs4 import BeautifulSoup
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import Database
from config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 2025 VCT Events to populate (completed events only)
# ALL URLs VERIFIED FROM VLR.gg 2026-01-24
VCT_2025_EVENTS = [
    # Americas
    {'url': '/event/2274/vct-2025-americas-kickoff', 'name': 'VCT 2025: Americas Kickoff', 'region': 'Americas', 'year': 2025},
    {'url': '/event/2347/vct-2025-americas-stage-1', 'name': 'VCT 2025: Americas Stage 1', 'region': 'Americas', 'year': 2025},
    {'url': '/event/2501/vct-2025-americas-stage-2', 'name': 'VCT 2025: Americas Stage 2', 'region': 'Americas', 'year': 2025},

    # EMEA
    {'url': '/event/2276/vct-2025-emea-kickoff', 'name': 'VCT 2025: EMEA Kickoff', 'region': 'EMEA', 'year': 2025},
    {'url': '/event/2380/vct-2025-emea-stage-1', 'name': 'VCT 2025: EMEA Stage 1', 'region': 'EMEA', 'year': 2025},
    {'url': '/event/2498/vct-2025-emea-stage-2', 'name': 'VCT 2025: EMEA Stage 2', 'region': 'EMEA', 'year': 2025},

    # Pacific
    {'url': '/event/2277/vct-2025-pacific-kickoff', 'name': 'VCT 2025: Pacific Kickoff', 'region': 'Pacific', 'year': 2025},
    {'url': '/event/2379/vct-2025-pacific-stage-1', 'name': 'VCT 2025: Pacific Stage 1', 'region': 'Pacific', 'year': 2025},
    {'url': '/event/2500/vct-2025-pacific-stage-2', 'name': 'VCT 2025: Pacific Stage 2', 'region': 'Pacific', 'year': 2025},

    # China
    {'url': '/event/2275/vct-2025-china-kickoff', 'name': 'VCT 2025: China Kickoff', 'region': 'China', 'year': 2025},
    {'url': '/event/2359/vct-2025-china-stage-1', 'name': 'VCT 2025: China Stage 1', 'region': 'China', 'year': 2025},
    {'url': '/event/2499/vct-2025-china-stage-2', 'name': 'VCT 2025: China Stage 2', 'region': 'China', 'year': 2025},
]

# 2026 VCT Kickoff events (all 4 regions completed)
# Event IDs verified from VLR.gg on 2026-02-27
VCT_2026_KICKOFF_EVENTS = [
    {'url': '/event/2682/vct-2026-americas-kickoff', 'name': 'VCT 2026: Americas Kickoff', 'region': 'Americas', 'year': 2026},
    {'url': '/event/2684/vct-2026-emea-kickoff',     'name': 'VCT 2026: EMEA Kickoff',     'region': 'EMEA',     'year': 2026},
    {'url': '/event/2683/vct-2026-pacific-kickoff',  'name': 'VCT 2026: Pacific Kickoff',  'region': 'Pacific',  'year': 2026},
    {'url': '/event/2685/vct-2026-china-kickoff',    'name': 'VCT 2026: China Kickoff',    'region': 'China',    'year': 2026},
]

# 2026 VCT Stage 1 events (ongoing — Americas starts 2026-04-10)
# Event IDs verified from VLR.gg on 2026-04-09
VCT_2026_STAGE1_EVENTS = [
    {'url': '/event/2860/vct-2026-americas-stage-1', 'name': 'VCT 2026: Americas Stage 1', 'region': 'Americas', 'year': 2026},
    {'url': '/event/2863/vct-2026-emea-stage-1',     'name': 'VCT 2026: EMEA Stage 1',     'region': 'EMEA',     'year': 2026},
    {'url': '/event/2775/vct-2026-pacific-stage-1',  'name': 'VCT 2026: Pacific Stage 1',  'region': 'Pacific',  'year': 2026},
    {'url': '/event/2864/vct-2026-china-stage-1',    'name': 'VCT 2026: China Stage 1',    'region': 'China',    'year': 2026},
]

class DatabasePopulator:
    def __init__(self):
        self.db = Database(Config.DATABASE_PATH)
        self.base_url = Config.VLR_BASE_URL
        self.headers = Config.HEADERS
        
        # Remove all proxy environment variables to bypass proxy
        import os
        for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy']:
            os.environ.pop(key, None)
        
        self.stats = {
            'events_processed': 0,
            'matches_processed': 0,
            'player_stats_saved': 0,
            'errors': 0
        }
    
    def _make_request(self, url: str) -> bytes:
        """Make HTTP request using urllib, completely bypassing proxy"""
        # Create request with headers
        req = urllib.request.Request(url, headers=self.headers)
        # Create opener with no proxy handler
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            response = opener.open(req, timeout=30)
            return response.read()
        except urllib.error.URLError as e:
            raise Exception(f"Request failed: {e}")
    
    def populate_all_events(self, events: list = None):
        """Populate database with all specified events"""
        if events is None:
            events = VCT_2025_EVENTS
        
        logger.info(f"Starting population of {len(events)} VCT events...")
        start_time = time.time()
        
        for i, event in enumerate(events):
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing event {i+1}/{len(events)}: {event['name']}")
            logger.info(f"{'='*60}")
            
            try:
                self.populate_event(event)
                self.stats['events_processed'] += 1
            except Exception as e:
                logger.error(f"Error processing event {event['name']}: {e}")
                self.stats['errors'] += 1
            
            # Be nice to VLR.gg servers
            time.sleep(1)
        
        elapsed = time.time() - start_time
        logger.info(f"\n{'='*60}")
        logger.info(f"POPULATION COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"Time elapsed: {elapsed:.1f} seconds")
        logger.info(f"Events processed: {self.stats['events_processed']}")
        logger.info(f"Matches processed: {self.stats['matches_processed']}")
        logger.info(f"Player stats saved: {self.stats['player_stats_saved']}")
        logger.info(f"Errors: {self.stats['errors']}")
    
    def populate_event(self, event: dict):
        """Populate database with data from a single event"""
        event_url = event['url']
        event_name = event['name']
        region = event.get('region', '')
        year = event.get('year', 2025)
        
        # Save event to database
        event_id = self.db.save_vct_event(
            event_url=event_url,
            event_name=event_name,
            region=region,
            year=year,
            status='completed'
        )
        
        if not event_id:
            logger.error(f"Failed to save event: {event_name}")
            return
        
        logger.info(f"Saved event: {event_name} (ID: {event_id})")
        
        # Get all matches for this event
        matches = self.get_event_matches(event_url)
        logger.info(f"Found {len(matches)} matches")
        
        # Process each match
        for i, match in enumerate(matches):
            logger.info(f"  Processing match {i+1}/{len(matches)}: {match['url']}")
            
            try:
                self.process_match(match, event_id)
                self.stats['matches_processed'] += 1
            except Exception as e:
                logger.error(f"    Error processing match: {e}")
                self.stats['errors'] += 1
            
            # Rate limiting
            time.sleep(0.5)
        
        # Also get player event stats (KPR, rounds, etc.)
        self.populate_event_player_stats(event_url, event_id)
    
    def get_event_matches(self, event_url: str) -> list:
        """Get all matches from an event"""
        matches_url = event_url.replace('/event/', '/event/matches/')
        full_url = f"{self.base_url}{matches_url}/?series_id=all"
        
        try:
            # Use urllib to bypass proxy completely
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find all match links
            match_pattern = re.compile(r'/\d+/[\w-]+-vs-[\w-]+')
            match_links = soup.find_all('a', href=match_pattern)
            
            matches = []
            seen = set()
            
            for link in match_links:
                href = link.get('href', '')
                if href in seen:
                    continue
                seen.add(href)
                
                # Extract team names from URL
                # Format: /123456/team1-vs-team2-event-name
                match = re.match(r'/\d+/([\w-]+)-vs-([\w-]+)', href)
                if match:
                    team1 = match.group(1).replace('-', ' ').title()
                    team2 = match.group(2).replace('-', ' ').title()
                    matches.append({
                        'url': href,
                        'team1': team1,
                        'team2': team2
                    })
            
            return matches
            
        except Exception as e:
            logger.error(f"Error getting matches from {event_url}: {e}")
            return []
    
    def _match_already_scraped(self, match_url: str) -> bool:
        """Return True if this match already has player_map_stats rows in the DB."""
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db.db_path, timeout=10)
        cur = conn.cursor()
        cur.execute('''
            SELECT COUNT(*) FROM player_map_stats pms
            JOIN matches m ON m.id = pms.match_id
            WHERE m.match_url = ?
        ''', (match_url,))
        count = cur.fetchone()[0]
        conn.close()
        return count > 0

    def process_match(self, match: dict, event_id: int):
        """Process a single match and save all comprehensive player map stats + pick/bans"""
        match_url = match['url']
        full_url = f"{self.base_url}{match_url}"

        # Checkpoint: skip if we already have stats for this match
        if self._match_already_scraped(match_url):
            logger.info(f"    [SKIP] Already scraped: {match_url}")
            self.stats['matches_processed'] += 1
            return

        try:
            # Use urllib to bypass proxy completely
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            
            # Save match to database
            match_id = self.db.save_match(
                match_url=match_url,
                event_id=event_id,
                team1=match['team1'],
                team2=match['team2']
            )
            
            if not match_id:
                logger.error(f"    Failed to save match: {match_url}")
                return
            
            # Extract and save pick/ban data
            pick_bans = self._extract_pick_bans(soup)
            if pick_bans:
                self.db.save_match_pick_bans(
                    match_id=match_id,
                    first_ban=pick_bans.get('first_ban'),
                    second_ban=pick_bans.get('second_ban'),
                    first_pick=pick_bans.get('first_pick'),
                    second_pick=pick_bans.get('second_pick'),
                    decider=pick_bans.get('decider')
                )
            
            # Find all map stat sections
            game_sections = soup.find_all('div', class_='vm-stats-game')
            map_number = 0
            
            for section in game_sections:
                game_id = section.get('data-game-id', '')
                if game_id == 'all':
                    continue
                
                map_number += 1
                
                # Extract map name and score from header
                map_name = 'Unknown'
                map_score = 'N/A'
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
                    
                    # Score - look for div.score elements in the entire section (not just header!)
                    score_divs = section.find_all('div', class_='score')
                    if len(score_divs) >= 2:
                        team1_score = score_divs[0].get_text(strip=True)
                        team2_score = score_divs[1].get_text(strip=True)
                        map_score = f"{team1_score}-{team2_score}"
                
                # Find ALL stats tables (one per team - usually 2)
                tables = section.find_all('table')
                if not tables:
                    continue
                
                for table in tables:
                    tbody = table.find('tbody')
                    if not tbody:
                        continue
                    
                    rows = tbody.find_all('tr')
                    
                    for row in rows:
                        # Get player name
                        player_link = row.find('a', href=re.compile(r'/player/\d+/'))
                        if not player_link:
                            continue
                        
                        # Extract just the player IGN
                        name_div = player_link.find('div', class_='text-of')
                        if name_div:
                            player_name = name_div.get_text(strip=True)
                        else:
                            name_div = player_link.find('div', style=lambda x: x and 'font-weight' in str(x))
                            if name_div:
                                player_name = name_div.get_text(strip=True)
                            else:
                                full_text = player_link.get_text(strip=True)
                                player_name = full_text.split()[0] if full_text else ''
                        
                        # Extract agent
                        agent = 'Unknown'
                        agent_td = row.find('td', class_='mod-agents')
                        if agent_td:
                            agent_img = agent_td.find('img')
                            if agent_img:
                                agent_alt = agent_img.get('alt', '')
                                agent_title = agent_img.get('title', '')
                                agent = agent_title or agent_alt or 'Unknown'
                                # Clean up agent name
                                agent = agent.split()[0] if agent else 'Unknown'
                        
                        # Get stats from cells
                        # VLR table structure: Rating, ACS, K, D, A, +/-, KAST, ADR, HS%, FK, FD, +/-
                        stat_cells = row.find_all('td', class_='mod-stat')
                        
                        if len(stat_cells) >= 11:
                            # Helper to extract stat value properly from mod-both span
                            def extract_cell_stat(cell):
                                both_span = cell.find('span', class_='mod-both')
                                if both_span:
                                    return both_span.get_text(strip=True)
                                return cell.get_text(strip=True)
                            
                            # Extract all stats
                            acs = self._extract_stat_value(stat_cells[1])
                            kills = self._extract_stat_value(stat_cells[2])
                            deaths = self._extract_stat_value(stat_cells[3])
                            assists = self._extract_stat_value(stat_cells[4])
                            kast_text = extract_cell_stat(stat_cells[6]).replace('%', '')
                            kast = self._parse_float(kast_text)
                            adr = self._extract_stat_value(stat_cells[7])
                            first_bloods = self._extract_stat_value(stat_cells[9])
                            
                            # Save to database with all new fields
                            self.db.save_player_map_stat(
                                match_id=match_id,
                                player_name=player_name,
                                map_number=map_number,
                                kills=kills,
                                deaths=deaths,
                                assists=assists,
                                map_name=map_name,
                                agent=agent,
                                acs=acs,
                                adr=adr,
                                kast=kast,
                                first_bloods=first_bloods,
                                map_score=map_score
                            )
                            self.stats['player_stats_saved'] += 1
            
            logger.info(f"    Saved {map_number} maps with comprehensive stats + pick/bans")
            
        except Exception as e:
            logger.error(f"    Error processing match {match_url}: {e}")
    
    def _extract_stat_value(self, cell) -> int:
        """Extract numeric stat value from a table cell"""
        try:
            # Look for mod-both span (total value)
            both_span = cell.find('span', class_='mod-both')
            if both_span:
                text = both_span.get_text(strip=True)
            else:
                text = cell.get_text(strip=True)
            
            # Extract first number
            numbers = re.findall(r'\d+', text)
            if numbers:
                return int(numbers[0])
        except:
            pass
        return 0
    
    def populate_event_player_stats(self, event_url: str, event_id: int):
        """Populate player aggregate stats (KPR, rounds) for an event"""
        stats_url = event_url.replace('/event/', '/event/stats/')
        full_url = f"{self.base_url}{stats_url}"
        
        try:
            # Use urllib to bypass proxy completely
            content = self._make_request(full_url)
            soup = BeautifulSoup(content, 'html.parser')
            
            stats_table = soup.find('table', class_='wf-table')
            if not stats_table:
                return
            
            tbody = stats_table.find('tbody')
            if not tbody:
                return
            
            rows = tbody.find_all('tr')
            players_saved = 0
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 9:
                    continue
                
                # Extract player info
                player_cell = cols[0]
                player_link = player_cell.find('a')
                if not player_link:
                    continue
                
                # Extract just the player IGN
                name_div = player_link.find('div', class_='text-of')
                if name_div:
                    player_name = name_div.get_text(strip=True)
                else:
                    name_div = player_link.find('div', style=lambda x: x and 'font-weight' in str(x))
                    if name_div:
                        player_name = name_div.get_text(strip=True)
                    else:
                        player_name = player_link.get_text(strip=True).split()[0]
                
                # Extract team
                team_div = player_cell.find('div', class_='stats-player-country')
                team = team_div.get_text(strip=True) if team_div else ''
                
                # Extract stats
                rounds = self._parse_number(cols[2].get_text(strip=True))
                rating = self._parse_float(cols[3].get_text(strip=True))
                acs = self._parse_float(cols[4].get_text(strip=True))
                adr = self._parse_float(cols[7].get_text(strip=True))
                kpr = self._parse_float(cols[8].get_text(strip=True))
                kills = self._parse_number(cols[16].get_text(strip=True)) if len(cols) > 16 else 0
                deaths = self._parse_number(cols[17].get_text(strip=True)) if len(cols) > 17 else 0
                
                # Validate KPR
                if not (0 < kpr < 2):
                    continue
                
                # Save to database
                self.db.save_player_event_stats(
                    event_id=event_id,
                    player_name=player_name,
                    team=team,
                    kpr=kpr,
                    rounds_played=rounds,
                    rating=rating,
                    acs=acs,
                    adr=adr,
                    kills=kills,
                    deaths=deaths
                )
                players_saved += 1
            
            logger.info(f"  Saved event stats for {players_saved} players")
            
        except Exception as e:
            logger.error(f"Error getting player event stats: {e}")
    
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
    
    def _extract_pick_bans(self, soup: BeautifulSoup) -> dict:
        """Extract pick/ban sequence from match page"""
        result = {
            'first_ban': None,
            'second_ban': None,
            'first_pick': None,
            'second_pick': None,
            'decider': None
        }
        
        try:
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
            logger.warning(f"Error extracting pick/bans: {e}")
        
        return result


def main():
    print("\n" + "="*60)
    print("  VCT Database Population Script")
    print("="*60)
    print("\nSelect events to populate:")
    print("  1) VCT 2026 Stage 1 (ongoing — EMEA/Pacific/China have matches, Americas starts tomorrow)")
    print("  2) VCT 2026 Kickoff (all 4 regions, completed)")
    print("  3) Both 2026 Stage 1 + 2026 Kickoff  [RECOMMENDED]")
    print("  4) VCT 2025 (all 12 events, historical)")
    print("  5) Everything (2026 Stage 1 + Kickoff + 2025)")
    print("\n  Note: already-scraped matches are skipped automatically (checkpoint).")
    print("\n" + "-"*60)

    choice = input("Choice [1/2/3/4/5]: ").strip()
    if choice == '1':
        events = VCT_2026_STAGE1_EVENTS
    elif choice == '2':
        events = VCT_2026_KICKOFF_EVENTS
    elif choice == '3':
        events = VCT_2026_STAGE1_EVENTS + VCT_2026_KICKOFF_EVENTS
    elif choice == '4':
        events = VCT_2025_EVENTS
    elif choice == '5':
        events = VCT_2026_STAGE1_EVENTS + VCT_2026_KICKOFF_EVENTS + VCT_2025_EVENTS
    else:
        print("Aborted.")
        return

    print(f"\nEvents to process: {len(events)}")
    print("Estimated time: ~2 min per event")
    print("\n" + "-"*60)

    response = input("Continue? (y/n): ").strip().lower()
    if response != 'y':
        print("Aborted.")
        return

    populator = DatabasePopulator()
    populator.populate_all_events(events)

    # Print final database stats
    print("\n" + "-"*60)
    print("Database Stats:")
    stats = populator.db.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == '__main__':
    main()
