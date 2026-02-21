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
        
        # VCT Events table (tier 1=VCT, tier 2=Challengers)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vct_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_url TEXT UNIQUE NOT NULL,
                event_name TEXT NOT NULL,
                region TEXT,
                year INTEGER,
                status TEXT DEFAULT 'completed',
                last_scraped TIMESTAMP,
                total_matches INTEGER DEFAULT 0,
                tier INTEGER DEFAULT 1
            )
        ''')
        # Migration: add tier column if missing
        cursor.execute("PRAGMA table_info(vct_events)")
        cols = {row[1] for row in cursor.fetchall()}
        if 'tier' not in cols:
            cursor.execute('ALTER TABLE vct_events ADD COLUMN tier INTEGER DEFAULT 1')
            cursor.execute('UPDATE vct_events SET tier = 1 WHERE tier IS NULL')
        
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
        
        # Moneyline: match odds + result for strategy analysis (VCT 2024+)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS moneyline_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_url TEXT UNIQUE NOT NULL,
                event_name TEXT,
                event_url TEXT,
                team1 TEXT NOT NULL,
                team2 TEXT NOT NULL,
                team1_odds REAL,
                team2_odds REAL,
                winner TEXT,
                team1_maps INTEGER DEFAULT 0,
                team2_maps INTEGER DEFAULT 0,
                match_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        
        # Leaderboard snapshots (daily leaderboards from API or image upload)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS leaderboard_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source TEXT NOT NULL,
                parsed_count INTEGER DEFAULT 0,
                ranked_count INTEGER DEFAULT 0
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS leaderboard_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                rank INTEGER NOT NULL,
                player_name TEXT NOT NULL,
                vlr_ign TEXT,
                team TEXT,
                line REAL NOT NULL,
                best_side TEXT NOT NULL,
                p_hit REAL NOT NULL,
                p_over REAL NOT NULL,
                p_under REAL NOT NULL,
                sample_size INTEGER NOT NULL,
                mu REAL,
                FOREIGN KEY (snapshot_id) REFERENCES leaderboard_snapshots (id)
            )
        ''')
        # Player combo cache: store 2-map or 3-map combo samples per player
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_combo_cache (
                player_name TEXT NOT NULL,
                combo_maps INTEGER NOT NULL DEFAULT 2,
                combo_samples TEXT NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (player_name, combo_maps)
            )
        ''')
        # Challengers combo cache (tier 2)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_combo_cache_challengers (
                player_name TEXT NOT NULL,
                combo_maps INTEGER NOT NULL DEFAULT 2,
                combo_samples TEXT NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (player_name, combo_maps)
            )
        ''')
        # Migration: if old table has no combo_maps column, migrate
        cursor.execute("PRAGMA table_info(player_combo_cache)")
        cols = [row[1] for row in cursor.fetchall()]
        if 'combo_maps' not in cols and cols:
            cursor.execute('''
                CREATE TABLE player_combo_cache_new (
                    player_name TEXT NOT NULL,
                    combo_maps INTEGER NOT NULL DEFAULT 2,
                    combo_samples TEXT NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (player_name, combo_maps)
                )
            ''')
            cursor.execute('''
                INSERT INTO player_combo_cache_new (player_name, combo_maps, combo_samples, last_updated)
                SELECT player_name, 2, combo_samples, last_updated FROM player_combo_cache
            ''')
            cursor.execute('DROP TABLE player_combo_cache')
            cursor.execute('ALTER TABLE player_combo_cache_new RENAME TO player_combo_cache')
        # Player data cache: store full player_data (team, ign, match_combinations) to avoid VLR scrape
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_data_cache (
                player_name TEXT PRIMARY KEY,
                ign TEXT,
                team TEXT,
                match_combinations TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Challengers player data cache (tier 2)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_data_cache_challengers (
                player_name TEXT PRIMARY KEY,
                ign TEXT,
                team TEXT,
                match_combinations TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # VLR player URL cache: maps player name -> VLR profile path (avoids repeat /search hits)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vlr_player_url_cache (
                player_name TEXT PRIMARY KEY,
                vlr_url TEXT NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indexes for faster lookups
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_player_name ON player_map_stats(player_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_match_event ON matches(event_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_status ON vct_events(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_leaderboard_snapshot ON leaderboard_entries(snapshot_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_snapshots_created ON leaderboard_snapshots(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_player_combo_name ON player_combo_cache(player_name)')
        
        conn.commit()
        conn.close()
    
    # ==================== VCT Events ====================
    
    def save_vct_event(self, event_url: str, event_name: str, region: str = None, 
                       year: int = None, status: str = 'completed', tier: int = 1) -> int:
        """Save or update a VCT event. tier: 1=VCT, 2=Challengers."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO vct_events 
                (event_url, event_name, region, year, status, last_scraped, tier)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (event_url, event_name, region, year, status, datetime.now().isoformat(), tier))
            
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
    
    def save_moneyline_match(self, match_url: str, event_name: str, event_url: str,
                             team1: str, team2: str, team1_odds: float = None, team2_odds: float = None,
                             winner: str = None, team1_maps: int = 0, team2_maps: int = 0,
                             match_date: str = None) -> Optional[int]:
        """Save or update a moneyline match record"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO moneyline_matches 
                (match_url, event_name, event_url, team1, team2, team1_odds, team2_odds, 
                 winner, team1_maps, team2_maps, match_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(match_url) DO UPDATE SET
                    event_name=excluded.event_name, event_url=excluded.event_url,
                    team1=excluded.team1, team2=excluded.team2,
                    team1_odds=excluded.team1_odds, team2_odds=excluded.team2_odds,
                    winner=excluded.winner, team1_maps=excluded.team1_maps,
                    team2_maps=excluded.team2_maps, match_date=excluded.match_date
            ''', (match_url, event_name, event_url, team1, team2, team1_odds, team2_odds,
                  winner, team1_maps, team2_maps, match_date))
            conn.commit()
            cursor.execute('SELECT id FROM moneyline_matches WHERE match_url = ?', (match_url,))
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.error(f"Error saving moneyline match: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def get_moneyline_stats(self) -> Dict:
        """
        Compute moneyline strategy stats from historical data.
        Categories: heavy_favorite (<1.5), moderate_favorite (1.5-1.86), even (1.86-1.86).
        Returns win rates and sample sizes per category.
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT team1, team2, team1_odds, team2_odds, winner
                FROM moneyline_matches
                WHERE winner IS NOT NULL AND winner != ''
                  AND (team1_odds IS NOT NULL OR team2_odds IS NOT NULL)
            ''')
            rows = cursor.fetchall()
            
            heavy_fav_wins, heavy_fav_total = 0, 0
            mod_fav_wins, mod_fav_total = 0, 0
            even_wins, even_total = 0, 0
            
            for team1, team2, o1, o2, winner in rows:
                fav_odds = None
                fav_team = None
                underdog_odds = None
                if o1 is not None and o2 is not None:
                    if o1 < o2:
                        fav_odds, fav_team = o1, team1
                        underdog_odds = o2
                    else:
                        fav_odds, fav_team = o2, team2
                        underdog_odds = o1
                elif o1 is not None:
                    fav_odds, fav_team = o1, team1
                    underdog_odds = 1.0 / (1.0 / 1.05 - 1.0 / o1) if o1 > 1 else None
                elif o2 is not None:
                    fav_odds, fav_team = o2, team2
                    underdog_odds = 1.0 / (1.0 / 1.05 - 1.0 / o2) if o2 > 1 else None
                
                if fav_odds is None or fav_team is None:
                    continue
                
                fav_won = (winner and winner.lower() == fav_team.lower())
                
                if fav_odds < 1.5:
                    heavy_fav_total += 1
                    if fav_won:
                        heavy_fav_wins += 1
                elif fav_odds <= 1.86 and (underdog_odds is None or underdog_odds >= 1.86):
                    mod_fav_total += 1
                    if fav_won:
                        mod_fav_wins += 1
                elif underdog_odds is not None and 1.75 <= fav_odds <= 2.0 and 1.75 <= underdog_odds <= 2.0:
                    even_total += 1
                    if fav_won:
                        even_wins += 1
            
            total = heavy_fav_total + mod_fav_total + even_total
            return {
                'total_matches': total,
                'heavy_favorite': {
                    'wins': heavy_fav_wins,
                    'total': heavy_fav_total,
                    'win_rate_pct': round(100 * heavy_fav_wins / heavy_fav_total, 1) if heavy_fav_total else 0,
                    'description': 'Favorite odds < 1.50 (implied >66%)'
                },
                'moderate_favorite': {
                    'wins': mod_fav_wins,
                    'total': mod_fav_total,
                    'win_rate_pct': round(100 * mod_fav_wins / mod_fav_total, 1) if mod_fav_total else 0,
                    'description': 'Favorite odds 1.50-1.86 (implied 54-66%)'
                },
                'even_matchup': {
                    'wins': even_wins,
                    'total': even_total,
                    'win_rate_pct': round(100 * even_wins / even_total, 1) if even_total else 0,
                    'description': 'Both teams ~1.86 (coin flip, vig-adjusted)'
                }
            }
        except Exception as e:
            logger.error(f"Error getting moneyline stats: {e}")
            return {}
        finally:
            conn.close()
    
    def get_all_moneyline_matches(self) -> List[Dict]:
        """Export all moneyline matches for analytics (calibration, backtest)."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT id, match_url, event_name, event_url, team1, team2,
                       team1_odds, team2_odds, winner, team1_maps, team2_maps, match_date, created_at
                FROM moneyline_matches
                ORDER BY created_at, id
            ''')
            cols = ['id', 'match_url', 'event_name', 'event_url', 'team1', 'team2',
                    'team1_odds', 'team2_odds', 'winner', 'team1_maps', 'team2_maps',
                    'match_date', 'created_at']
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting moneyline matches: {e}")
            return []
        finally:
            conn.close()
    
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
                WHERE LOWER(pms.player_name) = LOWER(?) AND m.event_id = ? AND pms.kills > 0
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
                WHERE LOWER(pms.player_name) = LOWER(?) AND m.event_id = ? AND pms.kills > 0
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
                WHERE LOWER(pms.player_name) = LOWER(?) AND m.event_id = ? AND pms.kills > 0
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
                WHERE LOWER(pms.player_name) = LOWER(?) AND ve.status = 'completed' AND pms.kills > 0
                ORDER BY ve.year DESC, m.id, pms.map_number
            ''', (player_name,))
            
            results = {}
            for row in cursor.fetchall():
                event_url = row[0]
                event_name = row[1]
                kills = row[2]
                if kills is None or kills <= 0:
                    continue
                if event_url not in results:
                    results[event_url] = {'event_name': event_name, 'kills': []}
                results[event_url]['kills'].append(kills)
            
            return results
            
        except Exception as e:
            logger.error(f"Error getting player cached kills: {e}")
            return {}
        finally:
            conn.close()
    
    def get_player_agent_aggregation(self, player_name: str, tier: Optional[int] = None) -> List[Dict]:
        """Get aggregated stats per agent. tier: 1=VCT, 2=Challengers, None=all."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            if tier is not None:
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
                    JOIN matches m ON pms.match_id = m.id
                    JOIN vct_events ve ON m.event_id = ve.id
                    WHERE LOWER(pms.player_name) = LOWER(?) AND pms.agent IS NOT NULL AND pms.kills > 0 AND ve.tier = ?
                    GROUP BY pms.agent
                    ORDER BY maps_played DESC
                ''', (player_name, tier))
            else:
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
                    WHERE LOWER(pms.player_name) = LOWER(?) AND pms.agent IS NOT NULL AND pms.kills > 0
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
    
    def get_player_map_aggregation(self, player_name: str, tier: Optional[int] = None) -> List[Dict]:
        """Get aggregated stats per map. tier: 1=VCT, 2=Challengers, None=all."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            if tier is not None:
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
                    JOIN matches m ON pms.match_id = m.id
                    JOIN vct_events ve ON m.event_id = ve.id
                    WHERE LOWER(pms.player_name) = LOWER(?) AND pms.map_name IS NOT NULL AND pms.kills > 0 AND ve.tier = ?
                    GROUP BY pms.map_name
                    ORDER BY times_played DESC
                ''', (player_name, tier))
            else:
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
                    WHERE LOWER(pms.player_name) = LOWER(?) AND pms.map_name IS NOT NULL AND pms.kills > 0
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
    
    def get_player_all_event_stats(self, player_name: str, tier: Optional[int] = None) -> List[Dict]:
        """Get all cached event stats for a player. tier: 1=VCT, 2=Challengers, None=all."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            if tier is not None:
                cursor.execute('''
                    SELECT pes.*, ve.event_url, ve.event_name, ve.status
                    FROM player_event_stats pes
                    JOIN vct_events ve ON pes.event_id = ve.id
                    WHERE LOWER(pes.player_name) = LOWER(?) AND ve.status = 'completed' AND ve.tier = ?
                    ORDER BY pes.rounds_played DESC, ve.id DESC
                ''', (player_name, tier))
            else:
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

    # ==================== Leaderboard & Player Combo Cache ====================

    CACHE_TTL_DAYS = 7  # Re-scrape player if cache older than this

    def get_cached_combo_samples(self, player_name: str, combo_maps: int = 2) -> Optional[List[int]]:
        """Get cached combo samples for a player if not stale. combo_maps: 2 or 3."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT combo_samples, last_updated FROM player_combo_cache
                WHERE LOWER(player_name) = LOWER(?) AND combo_maps = ?
            ''', (player_name, combo_maps))
            row = cursor.fetchone()
            if not row:
                return None
            samples_json, last_updated = row[0], row[1]
            if last_updated:
                try:
                    from datetime import datetime, timedelta
                    last = datetime.fromisoformat(last_updated.replace('Z', '').split('+')[0].split('.')[0])
                    if (datetime.now() - last).days > self.CACHE_TTL_DAYS:
                        return None
                except Exception:
                    pass
            return json.loads(samples_json) if samples_json else None
        except Exception as e:
            logger.error(f"Error getting combo cache: {e}")
            return None
        finally:
            conn.close()

    def save_combo_cache(self, player_name: str, combo_samples: List[int], combo_maps: int = 2) -> None:
        """Save or update combo samples for a player. combo_maps: 2 or 3."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO player_combo_cache (player_name, combo_maps, combo_samples, last_updated)
                VALUES (?, ?, ?, datetime('now'))
            ''', (player_name.lower(), combo_maps, json.dumps(combo_samples)))
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving combo cache: {e}")
            conn.rollback()
        finally:
            conn.close()

    def get_cached_player_data(self, player_name: str) -> Optional[Dict]:
        """Get cached player_data (ign, team, match_combinations) if not stale."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT ign, team, match_combinations, last_updated FROM player_data_cache
                WHERE LOWER(player_name) = LOWER(?)
            ''', (player_name,))
            row = cursor.fetchone()
            if not row:
                return None
            ign, team, mc_json, last_updated = row[0], row[1], row[2], row[3]
            if last_updated:
                try:
                    from datetime import datetime
                    last = datetime.fromisoformat(last_updated.replace('Z', '').split('+')[0].split('.')[0])
                    if (datetime.now() - last).days > self.CACHE_TTL_DAYS:
                        return None
                except Exception:
                    pass
            return {
                'ign': ign or player_name,
                'team': team or 'Unknown',
                'match_combinations': json.loads(mc_json) if mc_json else []
            }
        except Exception as e:
            logger.error(f"Error getting player data cache: {e}")
            return None
        finally:
            conn.close()

    def save_player_data_cache(self, player_name: str, player_data: Dict) -> None:
        """Save player_data (ign, team, match_combinations) to cache."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            mc = player_data.get('match_combinations', [])
            cursor.execute('''
                INSERT OR REPLACE INTO player_data_cache (player_name, ign, team, match_combinations, last_updated)
                VALUES (?, ?, ?, ?, datetime('now'))
            ''', (player_name.lower(), player_data.get('ign'), player_data.get('team', 'Unknown'), json.dumps(mc)))
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving player data cache: {e}")
            conn.rollback()
        finally:
            conn.close()

    def get_cached_player_data_challengers(self, player_name: str) -> Optional[Dict]:
        """Get cached Challengers player_data if not stale."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT ign, team, match_combinations, last_updated FROM player_data_cache_challengers
                WHERE LOWER(player_name) = LOWER(?)
            ''', (player_name,))
            row = cursor.fetchone()
            if not row:
                return None
            ign, team, mc_json, last_updated = row[0], row[1], row[2], row[3]
            if last_updated:
                try:
                    from datetime import datetime
                    last = datetime.fromisoformat(last_updated.replace('Z', '').split('+')[0].split('.')[0])
                    if (datetime.now() - last).days > self.CACHE_TTL_DAYS:
                        return None
                except Exception:
                    pass
            return {
                'ign': ign or player_name,
                'team': team or 'Unknown',
                'match_combinations': json.loads(mc_json) if mc_json else []
            }
        except Exception as e:
            logger.error(f"Error getting Challengers player data cache: {e}")
            return None
        finally:
            conn.close()

    def save_player_data_cache_challengers(self, player_name: str, player_data: Dict) -> None:
        """Save Challengers player_data to cache."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            mc = player_data.get('match_combinations', [])
            cursor.execute('''
                INSERT OR REPLACE INTO player_data_cache_challengers (player_name, ign, team, match_combinations, last_updated)
                VALUES (?, ?, ?, ?, datetime('now'))
            ''', (player_name.lower(), player_data.get('ign'), player_data.get('team', 'Unknown'), json.dumps(mc)))
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving Challengers player data cache: {e}")
            conn.rollback()
        finally:
            conn.close()

    def get_cached_combo_samples_challengers(self, player_name: str, combo_maps: int = 2) -> Optional[List[int]]:
        """Get cached Challengers combo samples if not stale."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT combo_samples, last_updated FROM player_combo_cache_challengers
                WHERE LOWER(player_name) = LOWER(?) AND combo_maps = ?
            ''', (player_name, combo_maps))
            row = cursor.fetchone()
            if not row:
                return None
            samples_json, last_updated = row[0], row[1]
            if last_updated:
                try:
                    from datetime import datetime, timedelta
                    last = datetime.fromisoformat(last_updated.replace('Z', '').split('+')[0].split('.')[0])
                    if (datetime.now() - last).days > self.CACHE_TTL_DAYS:
                        return None
                except Exception:
                    pass
            return json.loads(samples_json) if samples_json else None
        except Exception as e:
            logger.error(f"Error getting Challengers combo cache: {e}")
            return None
        finally:
            conn.close()

    def save_combo_cache_challengers(self, player_name: str, combo_samples: List[int], combo_maps: int = 2) -> None:
        """Save Challengers combo samples to cache."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO player_combo_cache_challengers (player_name, combo_maps, combo_samples, last_updated)
                VALUES (?, ?, ?, datetime('now'))
            ''', (player_name.lower(), combo_maps, json.dumps(combo_samples)))
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving Challengers combo cache: {e}")
            conn.rollback()
        finally:
            conn.close()

    def get_vlr_player_url(self, player_name: str) -> Optional[str]:
        """Return cached VLR profile path for a player, or None if not cached."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT vlr_url FROM vlr_player_url_cache WHERE LOWER(player_name) = LOWER(?)',
                (player_name,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.error(f"Error getting VLR player URL cache: {e}")
            return None
        finally:
            conn.close()

    def save_vlr_player_url(self, player_name: str, vlr_url: str) -> None:
        """Persist a player_name → VLR profile path mapping so future lookups skip /search."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO vlr_player_url_cache (player_name, vlr_url, last_updated)
                VALUES (LOWER(?), ?, datetime('now'))
            ''', (player_name, vlr_url))
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving VLR player URL cache: {e}")
            conn.rollback()
        finally:
            conn.close()

    def clear_prizepicks_cache(self, challengers_only: bool = False) -> Dict[str, int]:
        """Clear PrizePicks player/combo caches so fresh 2026 data is fetched.
        challengers_only: if True, only clear Challengers caches; else clear both VCT and Challengers."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        counts = {}
        try:
            if not challengers_only:
                cursor.execute('DELETE FROM player_data_cache')
                counts['player_data'] = cursor.rowcount
                cursor.execute('DELETE FROM player_combo_cache')
                counts['player_combo'] = cursor.rowcount
            cursor.execute('DELETE FROM player_data_cache_challengers')
            counts['player_data_challengers'] = cursor.rowcount
            cursor.execute('DELETE FROM player_combo_cache_challengers')
            counts['player_combo_challengers'] = cursor.rowcount
            conn.commit()
        except Exception as e:
            logger.error(f"Error clearing PrizePicks cache: {e}")
            conn.rollback()
        finally:
            conn.close()
        return counts

    def save_leaderboard_snapshot(self, source: str, results: List[Dict], parsed_count: int = 0) -> Optional[int]:
        """Save a leaderboard snapshot. Returns snapshot_id."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO leaderboard_snapshots (source, parsed_count, ranked_count)
                VALUES (?, ?, ?)
            ''', (source, parsed_count, len(results)))
            snapshot_id = cursor.lastrowid
            for r in results:
                cursor.execute('''
                    INSERT INTO leaderboard_entries (snapshot_id, rank, player_name, vlr_ign, team, line, best_side, p_hit, p_over, p_under, sample_size, mu)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (snapshot_id, r['rank'], r['player_name'], r.get('vlr_ign'), r.get('team'), r['line'], r['best_side'], r['p_hit'], r['p_over'], r['p_under'], r['sample_size'], r.get('mu')))
            conn.commit()
            return snapshot_id
        except Exception as e:
            logger.error(f"Error saving leaderboard snapshot: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def get_leaderboard_snapshots(self, limit: int = 50) -> List[Dict]:
        """List recent leaderboard snapshots."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT id, created_at, source, parsed_count, ranked_count
                FROM leaderboard_snapshots
                ORDER BY created_at DESC
                LIMIT ?
            ''', (limit,))
            return [{'id': r[0], 'created_at': r[1], 'source': r[2], 'parsed_count': r[3], 'ranked_count': r[4]} for r in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting snapshots: {e}")
            return []
        finally:
            conn.close()

    def get_leaderboard_snapshot(self, snapshot_id: int) -> Optional[Dict]:
        """Get full leaderboard by snapshot ID."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id, created_at, source, parsed_count, ranked_count FROM leaderboard_snapshots WHERE id = ?', (snapshot_id,))
            row = cursor.fetchone()
            if not row:
                return None
            meta = {'id': row[0], 'created_at': row[1], 'source': row[2], 'parsed_count': row[3], 'ranked_count': row[4]}
            cursor.execute('''
                SELECT rank, player_name, vlr_ign, team, line, best_side, p_hit, p_over, p_under, sample_size, mu
                FROM leaderboard_entries WHERE snapshot_id = ? ORDER BY rank
            ''', (snapshot_id,))
            meta['leaderboard'] = [{
                'rank': r[0], 'player_name': r[1], 'vlr_ign': r[2], 'team': r[3], 'line': r[4],
                'best_side': r[5], 'p_hit': r[6], 'p_over': r[7], 'p_under': r[8], 'sample_size': r[9], 'mu': r[10]
            } for r in cursor.fetchall()]
            return meta
        except Exception as e:
            logger.error(f"Error getting snapshot: {e}")
            return None
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
            
            cursor.execute("SELECT COUNT(*) FROM leaderboard_snapshots")
            leaderboard_snapshots = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM player_combo_cache")
            player_combo_cached = cursor.fetchone()[0]
            
            return {
                'players_tracked': player_count,
                'vct_events': event_count,
                'completed_events': completed_events,
                'matches_cached': match_count,
                'map_stats_cached': map_stats_count,
                'leaderboard_snapshots': leaderboard_snapshots,
                'players_combo_cached': player_combo_cached
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}
        finally:
            conn.close()
