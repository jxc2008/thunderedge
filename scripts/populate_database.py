# scripts/populate_database.py
"""
One-time population script to cache all 2025 VCT event data.

This script:
1. Scrapes all 2025 VCT events from VLR.gg
2. For each event, gets all matches
3. For each match, extracts all player stats per map
4. Stores everything in the SQLite database

Run once to populate the cache, then the main app will use cached data
for completed events and only scrape ongoing events.
"""

import sys
import os
import re
import ssl
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
        # Use unverified SSL context for macOS where Python may lack system certs
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        # Create opener with no proxy handler and custom SSL context
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=ssl_ctx)
        )
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
    
    def process_match(self, match: dict, event_id: int):
        """Process a single match and save all player map stats"""
        match_url = match['url']
        full_url = f"{self.base_url}{match_url}"
        
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
            
            # Find all map stat sections
            game_sections = soup.find_all('div', class_='vm-stats-game')
            map_number = 0
            
            for section in game_sections:
                game_id = section.get('data-game-id', '')
                if game_id == 'all':
                    continue
                
                map_number += 1
                
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
                        
                        # Extract just the player IGN, not the team name
                        # The player name is typically in a div with class 'text-of'
                        name_div = player_link.find('div', class_='text-of')
                        if name_div:
                            player_name = name_div.get_text(strip=True)
                        else:
                            # Fallback: look for div with font-weight style
                            name_div = player_link.find('div', style=lambda x: x and 'font-weight' in str(x))
                            if name_div:
                                player_name = name_div.get_text(strip=True)
                            else:
                                # Last resort: take first part of text (before team name)
                                full_text = player_link.get_text(strip=True)
                                # Team names are often in CAPS or at the end
                                player_name = full_text.split()[0] if full_text else ''
                        
                        # Get stats from cells
                        stat_cells = row.find_all('td', class_='mod-stat')
                        
                        if len(stat_cells) >= 4:
                            # Column order: R, ACS, K, D, A, ...
                            kills = self._extract_stat_value(stat_cells[2])  # K column
                            deaths = self._extract_stat_value(stat_cells[3])  # D column
                            assists = self._extract_stat_value(stat_cells[4]) if len(stat_cells) > 4 else 0
                            
                            # Save to database
                            self.db.save_player_map_stat(
                                match_id=match_id,
                                player_name=player_name,
                                map_number=map_number,
                                kills=kills,
                                deaths=deaths,
                                assists=assists
                            )
                            self.stats['player_stats_saved'] += 1
            
            logger.info(f"    Saved {map_number} maps with player stats")
            
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


def main():
    print("\n" + "="*60)
    print("  VCT 2025 Database Population Script")
    print("="*60)
    print("\nThis script will populate the database with all 2025 VCT events.")
    print(f"Events to process: {len(VCT_2025_EVENTS)}")
    print("\nEstimated time: 5-10 minutes")
    print("\n" + "-"*60)
    
    response = input("Continue? (y/n): ").strip().lower()
    if response != 'y':
        print("Aborted.")
        return
    
    populator = DatabasePopulator()
    populator.populate_all_events()
    
    # Print final database stats
    print("\n" + "-"*60)
    print("Database Stats:")
    stats = populator.db.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == '__main__':
    main()
