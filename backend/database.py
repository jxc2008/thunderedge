# backend/database.py
import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional
import logging
import os

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        # Ensure the directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database with required tables"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        # Use WAL mode for better concurrency and OneDrive compatibility
        conn.execute('PRAGMA journal_mode=WAL;')
        cursor = conn.cursor()
        
        # Players table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ign TEXT UNIQUE NOT NULL,
                team TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP
            )
        ''')
        
        # VCT Events table (the event itself, not player-specific)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vct_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_url TEXT UNIQUE NOT NULL,
                event_name TEXT NOT NULL,
                region TEXT,
                year INTEGER,
                status TEXT DEFAULT 'completed',
                last_scraped TIMESTAMP,
                total_matches INTEGER DEFAULT 0
            )
        ''')
        
        # Matches table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_url TEXT UNIQUE NOT NULL,
                event_id INTEGER,
                team1 TEXT,
                team2 TEXT,
                match_date TEXT,
                maps_played INTEGER DEFAULT 0,
                FOREIGN KEY (event_id) REFERENCES vct_events (id)
            )
        ''')
        
        # Player map stats - per-map performance for each player
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_map_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER,
                player_name TEXT NOT NULL,
                map_number INTEGER,
                map_name TEXT,
                agent TEXT,
                kills INTEGER,
                deaths INTEGER,
                assists INTEGER,
                acs INTEGER,
                adr INTEGER,
                kast REAL,
                first_bloods INTEGER,
                map_score TEXT,
                FOREIGN KEY (match_id) REFERENCES matches (id),
                UNIQUE(match_id, player_name, map_number)
            )
        ''')
        
        # Match pick/bans
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS match_pick_bans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER,
                first_ban TEXT,
                second_ban TEXT,
                first_pick TEXT,
                second_pick TEXT,
                decider TEXT,
                FOREIGN KEY (match_id) REFERENCES matches (id),
                UNIQUE(match_id)
            )
        ''')
        
        # Player event stats (aggregate KPR, rounds, etc. per event)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_event_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER,
                player_name TEXT NOT NULL,
                team TEXT,
                kpr REAL,
                rounds_played INTEGER,
                rating REAL,
                acs REAL,
                adr REAL,
                kills INTEGER,
                deaths INTEGER,
                FOREIGN KEY (event_id) REFERENCES vct_events (id),
                UNIQUE(event_id, player_name)
            )
        ''')
        
        # Team event stats (fights per round, etc. per event)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_event_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER,
                team_name TEXT NOT NULL,
                fights_per_round REAL,
                total_kills INTEGER,
                total_deaths INTEGER,
                total_rounds INTEGER,
                matches_played INTEGER,
                FOREIGN KEY (event_id) REFERENCES vct_events (id),
                UNIQUE(event_id, team_name)
            )
        ''')
        
        # Team pick/bans (per match)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_pick_bans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER,
                team_name TEXT NOT NULL,
                first_ban TEXT,
                second_ban TEXT,
                first_pick TEXT,
                second_pick TEXT,
                FOREIGN KEY (match_id) REFERENCES matches (id)
            )
        ''')
        
        # Analysis results table (for caching)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analysis_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                analysis_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                betting_line REAL,
                predicted_kpr REAL,
                classification TEXT,
                confidence TEXT,
                raw_data TEXT,
                FOREIGN KEY (player_id) REFERENCES players (id)
            )
        ''')
        
        # Create indexes for faster lookups
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_player_name ON player_map_stats(player_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_match_event ON matches(event_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_status ON vct_events(status)')
        
        conn.commit()
        conn.close()
    
    # ==================== VCT Events ====================
    
    def save_vct_event(self, event_url: str, event_name: str, region: str = None, 
                       year: int = None, status: str = 'completed') -> int:
        """Save or update a VCT event"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO vct_events 
                (event_url, event_name, region, year, status, last_scraped)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (event_url, event_name, region, year, status, datetime.now().isoformat()))
            
            conn.commit()
            
            # Get the event ID
            cursor.execute('SELECT id FROM vct_events WHERE event_url = ?', (event_url,))
            result = cursor.fetchone()
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Error saving VCT event: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def get_vct_event(self, event_url: str) -> Optional[Dict]:
        """Get a VCT event by URL"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT * FROM vct_events WHERE event_url = ?', (event_url,))
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': row[0],
                    'event_url': row[1],
                    'event_name': row[2],
                    'region': row[3],
                    'year': row[4],
                    'status': row[5],
                    'last_scraped': row[6],
                    'total_matches': row[7]
                }
        except Exception as e:
            logger.error(f"Error getting VCT event: {e}")
        finally:
            conn.close()
        
        return None
    
    def is_event_completed(self, event_url: str) -> bool:
        """Check if an event is marked as completed"""
        event = self.get_vct_event(event_url)
        return event is not None and event.get('status') == 'completed'
    
    def get_completed_events(self) -> List[Dict]:
        """Get all completed events"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM vct_events WHERE status = 'completed'")
            rows = cursor.fetchall()
            
            return [{
                'id': row[0],
                'event_url': row[1],
                'event_name': row[2],
                'region': row[3],
                'year': row[4],
                'status': row[5],
                'last_scraped': row[6],
                'total_matches': row[7]
            } for row in rows]
        except Exception as e:
            logger.error(f"Error getting completed events: {e}")
            return []
        finally:
            conn.close()
    
    # ==================== Matches ====================
    
    def save_match(self, match_url: str, event_id: int, team1: str, team2: str, 
                   match_date: str = None, maps_played: int = 0) -> int:
        """Save or update a match"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO matches 
                (match_url, event_id, team1, team2, match_date, maps_played)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (match_url, event_id, team1, team2, match_date, maps_played))
            
            conn.commit()
            
            cursor.execute('SELECT id FROM matches WHERE match_url = ?', (match_url,))
            result = cursor.fetchone()
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Error saving match: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def save_match_pick_bans(self, match_id: int, first_ban: str = None, second_ban: str = None,
                             first_pick: str = None, second_pick: str = None, decider: str = None):
        """Save match pick/ban sequence"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO match_pick_bans 
                (match_id, first_ban, second_ban, first_pick, second_pick, decider)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (match_id, first_ban, second_ban, first_pick, second_pick, decider))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error saving match pick/bans: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def get_match(self, match_url: str) -> Optional[Dict]:
        """Get a match by URL"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT * FROM matches WHERE match_url = ?', (match_url,))
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': row[0],
                    'match_url': row[1],
                    'event_id': row[2],
                    'team1': row[3],
                    'team2': row[4],
                    'match_date': row[5],
                    'maps_played': row[6]
                }
        except Exception as e:
            logger.error(f"Error getting match: {e}")
        finally:
            conn.close()
        
        return None
    
    # ==================== Player Map Stats ====================
    
    def save_player_map_stat(self, match_id: int, player_name: str, map_number: int,
                             kills: int, deaths: int = 0, assists: int = 0,
                             map_name: str = None, agent: str = None,
                             acs: int = 0, adr: int = 0, kast: float = 0.0,
                             first_bloods: int = 0, map_score: str = None):
        """Save comprehensive per-map stats for a player"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO player_map_stats 
                (match_id, player_name, map_number, kills, deaths, assists, 
                 map_name, agent, acs, adr, kast, first_bloods, map_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (match_id, player_name.lower(), map_number, kills, deaths, assists,
                  map_name, agent, acs, adr, kast, first_bloods, map_score))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error saving player map stat: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def get_player_map_kills_for_event(self, player_name: str, event_id: int) -> List[int]:
        """Get all map kills for a player in a specific event"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT pms.kills
                FROM player_map_stats pms
                JOIN matches m ON pms.match_id = m.id
                WHERE LOWER(pms.player_name) = LOWER(?) AND m.event_id = ?
                ORDER BY m.id, pms.map_number
            ''', (player_name, event_id))
            
            return [row[0] for row in cursor.fetchall()]
            
        except Exception as e:
            logger.error(f"Error getting player map kills: {e}")
            return []
        finally:
            conn.close()
    
    def get_player_map_kills_with_scores_for_event(self, player_name: str, event_id: int) -> List[Dict]:
        """Get map kills with scores for win/loss analysis"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT pms.kills, pms.map_score
                FROM player_map_stats pms
                JOIN matches m ON pms.match_id = m.id
                WHERE LOWER(pms.player_name) = LOWER(?) AND m.event_id = ?
                ORDER BY m.id, pms.map_number
            ''', (player_name, event_id))
            
            return [{'kills': row[0], 'map_score': row[1]} for row in cursor.fetchall()]
            
        except Exception as e:
            logger.error(f"Error getting player map kills with scores: {e}")
            return []
        finally:
            conn.close()
    
    def get_player_match_data_for_event(self, player_name: str, event_id: int) -> List[Dict]:
        """Get comprehensive match-level data (grouped by match) for a player in a specific event"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT m.match_url, e.event_name, pms.map_number, pms.kills, pms.map_score,
                       pms.map_name, pms.agent, pms.acs, pms.adr, pms.kast, pms.first_bloods
                FROM player_map_stats pms
                JOIN matches m ON pms.match_id = m.id
                JOIN vct_events e ON m.event_id = e.id
                WHERE LOWER(pms.player_name) = LOWER(?) AND m.event_id = ?
                ORDER BY m.id, pms.map_number
            ''', (player_name, event_id))
            
            rows = cursor.fetchall()
            
            # Group by match
            matches = {}
            for match_url, event_name, map_number, kills, map_score, map_name, agent, acs, adr, kast, first_bloods in rows:
                if match_url not in matches:
                    matches[match_url] = {
                        'match_url': match_url,
                        'event_name': event_name,
                        'map_kills': [],
                        'map_scores': [],
                        'map_names': [],
                        'agents': [],
                        'acs_list': [],
                        'adr_list': [],
                        'kast_list': [],
                        'first_bloods_list': []
                    }
                matches[match_url]['map_kills'].append(kills)
                matches[match_url]['map_scores'].append(map_score if map_score else 'N/A')
                matches[match_url]['map_names'].append(map_name if map_name else 'Unknown')
                matches[match_url]['agents'].append(agent if agent else 'Unknown')
                matches[match_url]['acs_list'].append(acs if acs else 0)
                matches[match_url]['adr_list'].append(adr if adr else 0)
                matches[match_url]['kast_list'].append(kast if kast else 0.0)
                matches[match_url]['first_bloods_list'].append(first_bloods if first_bloods else 0)
            
            # Convert to list and set num_maps based on actual map count
            match_list = []
            for match in matches.values():
                if len(match['map_kills']) >= 2:
                    match['num_maps'] = len(match['map_kills'])
                    match_list.append(match)
            
            return match_list
            
        except Exception as e:
            logger.error(f"Error getting player match data: {e}")
            return []
        finally:
            conn.close()
    
    def get_player_all_cached_kills(self, player_name: str) -> Dict[str, List[int]]:
        """Get all cached map kills for a player, organized by event"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT ve.event_url, ve.event_name, pms.kills
                FROM player_map_stats pms
                JOIN matches m ON pms.match_id = m.id
                JOIN vct_events ve ON m.event_id = ve.id
                WHERE LOWER(pms.player_name) = LOWER(?) AND ve.status = 'completed'
                ORDER BY ve.year DESC, m.id, pms.map_number
            ''', (player_name,))
            
            results = {}
            for row in cursor.fetchall():
                event_url = row[0]
                event_name = row[1]
                kills = row[2]
                
                if event_url not in results:
                    results[event_url] = {'event_name': event_name, 'kills': []}
                results[event_url]['kills'].append(kills)
            
            return results
            
        except Exception as e:
            logger.error(f"Error getting player cached kills: {e}")
            return {}
        finally:
            conn.close()
    
    def get_player_agent_aggregation(self, player_name: str) -> List[Dict]:
        """Get aggregated stats per agent for a player across all events"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT 
                    pms.agent,
                    COUNT(DISTINCT pms.match_id) as matches_played,
                    COUNT(*) as maps_played,
                    SUM(pms.kills) as total_kills,
                    SUM(pms.deaths) as total_deaths,
                    SUM(pms.assists) as total_assists,
                    AVG(pms.acs) as avg_acs,
                    AVG(pms.adr) as avg_adr,
                    AVG(pms.kast) as avg_kast,
                    SUM(pms.first_bloods) as total_first_bloods
                FROM player_map_stats pms
                WHERE LOWER(pms.player_name) = LOWER(?) AND pms.agent IS NOT NULL
                GROUP BY pms.agent
                ORDER BY maps_played DESC
            ''', (player_name,))
            
            rows = cursor.fetchall()
            
            agents = []
            for row in rows:
                agents.append({
                    'agent': row[0],
                    'matches_played': row[1],
                    'maps_played': row[2],
                    'total_kills': row[3],
                    'total_deaths': row[4],
                    'total_assists': row[5],
                    'avg_acs': round(row[6], 1) if row[6] else 0,
                    'avg_adr': round(row[7], 1) if row[7] else 0,
                    'avg_kast': round(row[8], 1) if row[8] else 0,
                    'total_first_bloods': row[9],
                    'kd_ratio': round(row[3] / row[4], 2) if row[4] > 0 else 0
                })
            
            return agents
            
        except Exception as e:
            logger.error(f"Error getting agent aggregation: {e}")
            return []
        finally:
            conn.close()
    
    def get_player_map_aggregation(self, player_name: str) -> List[Dict]:
        """Get aggregated stats per map for a player across all events"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT 
                    pms.map_name,
                    COUNT(DISTINCT pms.match_id) as matches_played,
                    COUNT(*) as times_played,
                    SUM(pms.kills) as total_kills,
                    SUM(pms.deaths) as total_deaths,
                    SUM(pms.assists) as total_assists,
                    AVG(pms.acs) as avg_acs,
                    AVG(pms.adr) as avg_adr,
                    AVG(pms.kast) as avg_kast,
                    SUM(pms.first_bloods) as total_first_bloods
                FROM player_map_stats pms
                WHERE LOWER(pms.player_name) = LOWER(?) AND pms.map_name IS NOT NULL
                GROUP BY pms.map_name
                ORDER BY times_played DESC
            ''', (player_name,))
            
            rows = cursor.fetchall()
            
            maps = []
            for row in rows:
                maps.append({
                    'map_name': row[0],
                    'matches_played': row[1],
                    'times_played': row[2],
                    'total_kills': row[3],
                    'total_deaths': row[4],
                    'total_assists': row[5],
                    'avg_acs': round(row[6], 1) if row[6] else 0,
                    'avg_adr': round(row[7], 1) if row[7] else 0,
                    'avg_kast': round(row[8], 1) if row[8] else 0,
                    'total_first_bloods': row[9],
                    'kd_ratio': round(row[3] / row[4], 2) if row[4] > 0 else 0,
                    'avg_kills_per_map': round(row[3] / row[2], 1) if row[2] > 0 else 0
                })
            
            return maps
            
        except Exception as e:
            logger.error(f"Error getting map aggregation: {e}")
            return []
        finally:
            conn.close()
    
    # ==================== Player Event Stats ====================
    
    def save_player_event_stats(self, event_id: int, player_name: str, team: str,
                                kpr: float, rounds_played: int, rating: float = 0,
                                acs: float = 0, adr: float = 0, kills: int = 0, deaths: int = 0):
        """Save player's aggregate stats for an event"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO player_event_stats 
                (event_id, player_name, team, kpr, rounds_played, rating, acs, adr, kills, deaths)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (event_id, player_name.lower(), team, kpr, rounds_played, rating, acs, adr, kills, deaths))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error saving player event stats: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def get_player_event_stats(self, player_name: str, event_id: int) -> Optional[Dict]:
        """Get player's aggregate stats for an event"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT * FROM player_event_stats 
                WHERE LOWER(player_name) = LOWER(?) AND event_id = ?
            ''', (player_name, event_id))
            
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'event_id': row[1],
                    'player_name': row[2],
                    'team': row[3],
                    'kpr': row[4],
                    'rounds_played': row[5],
                    'rating': row[6],
                    'acs': row[7],
                    'adr': row[8],
                    'kills': row[9],
                    'deaths': row[10]
                }
        except Exception as e:
            logger.error(f"Error getting player event stats: {e}")
        finally:
            conn.close()
        
        return None
    
    def get_player_all_event_stats(self, player_name: str) -> List[Dict]:
        """Get all cached event stats for a player"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            # Order by rounds_played DESC, then event_id DESC (higher ID = more recent event)
            # This ensures we get the player's main regional events, not guest appearances
            cursor.execute('''
                SELECT pes.*, ve.event_url, ve.event_name, ve.status
                FROM player_event_stats pes
                JOIN vct_events ve ON pes.event_id = ve.id
                WHERE LOWER(pes.player_name) = LOWER(?) AND ve.status = 'completed'
                ORDER BY pes.rounds_played DESC, ve.id DESC
            ''', (player_name,))
            
            return [{
                'id': row[0],
                'event_id': row[1],
                'player_name': row[2],
                'team': row[3],
                'kpr': row[4],
                'rounds_played': row[5],
                'rating': row[6],
                'acs': row[7],
                'adr': row[8],
                'kills': row[9],
                'deaths': row[10],
                'event_url': row[11],
                'event_name': row[12],
                'status': row[13]
            } for row in cursor.fetchall()]
            
        except Exception as e:
            logger.error(f"Error getting player all event stats: {e}")
            return []
        finally:
            conn.close()
    
    # ==================== Legacy Methods ====================
    
    def save_player_data(self, player_data: Dict) -> int:
        """Save player data to database (legacy method)"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO players (ign, team, last_updated)
                VALUES (?, ?, ?)
            ''', (
                player_data['ign'],
                player_data.get('team', 'Unknown'),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            player_id = cursor.lastrowid
            return player_id
            
        except Exception as e:
            logger.error(f"Error saving player data: {e}")
            conn.rollback()
            return None
            
        finally:
            conn.close()
    
    def get_stats(self) -> Dict:
        """Get database statistics"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT COUNT(*) FROM players')
            player_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM vct_events')
            event_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM matches')
            match_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM player_map_stats')
            map_stats_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM vct_events WHERE status = 'completed'")
            completed_events = cursor.fetchone()[0]
            
            return {
                'players_tracked': player_count,
                'vct_events': event_count,
                'completed_events': completed_events,
                'matches_cached': match_count,
                'map_stats_cached': map_stats_count
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}
        finally:
            conn.close()
