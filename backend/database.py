# backend/database.py
import sqlite3
import json
from collections import Counter
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
        
        # Match map halves: attack/defense round breakdown per team per map
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS match_map_halves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                map_number INTEGER NOT NULL,
                map_name TEXT,
                team_name TEXT NOT NULL,
                atk_rounds_won INTEGER DEFAULT 0,
                def_rounds_won INTEGER DEFAULT 0,
                total_rounds INTEGER DEFAULT 0,
                UNIQUE(match_id, map_number, team_name)
            )
        ''')

        # Create indexes for faster lookups
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_player_name ON player_map_stats(player_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_match_event ON matches(event_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_status ON vct_events(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_leaderboard_snapshot ON leaderboard_entries(snapshot_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_snapshots_created ON leaderboard_snapshots(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_player_combo_name ON player_combo_cache(player_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_map_halves_match ON match_map_halves(match_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_map_halves_team ON match_map_halves(team_name)')

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
    
    def get_player_agent_aggregation(self, player_name: str, tier: Optional[int] = None, kill_line: Optional[float] = None) -> List[Dict]:
        """Get aggregated stats per agent. tier: 1=VCT, 2=Challengers, None=all. kill_line for over/under counts."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        over_under = ''
        if kill_line is not None:
            over_under = ''',
                        SUM(CASE WHEN pms.kills > ? THEN 1 ELSE 0 END) as over_count,
                        SUM(CASE WHEN pms.kills <= ? THEN 1 ELSE 0 END) as under_count'''
        
        try:
            if tier is not None:
                sql = '''
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
                        SUM(pms.first_bloods) as total_first_bloods''' + over_under + '''
                    FROM player_map_stats pms
                    JOIN matches m ON pms.match_id = m.id
                    JOIN vct_events ve ON m.event_id = ve.id
                    WHERE LOWER(pms.player_name) = LOWER(?) AND pms.agent IS NOT NULL AND pms.kills > 0 AND ve.tier = ?
                    GROUP BY pms.agent
                    ORDER BY maps_played DESC
                '''
                params = (player_name, tier) if kill_line is None else (kill_line, kill_line, player_name, tier)
            else:
                sql = '''
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
                        SUM(pms.first_bloods) as total_first_bloods''' + over_under + '''
                    FROM player_map_stats pms
                    WHERE LOWER(pms.player_name) = LOWER(?) AND pms.agent IS NOT NULL AND pms.kills > 0
                    GROUP BY pms.agent
                    ORDER BY maps_played DESC
                '''
                params = (player_name,) if kill_line is None else (kill_line, kill_line, player_name)
            
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            agents = []
            has_over_under = kill_line is not None
            for row in rows:
                maps_played = row[2]
                total_kills = row[3]
                avg_kills = round(total_kills / maps_played, 1) if maps_played > 0 else 0
                over_count = row[10] if has_over_under and len(row) > 10 else None
                under_count = row[11] if has_over_under and len(row) > 11 else None
                over_pct = round(over_count / maps_played * 100, 1) if over_count is not None and maps_played > 0 else None
                
                agent_dict = {
                    'agent': row[0],
                    'matches_played': row[1],
                    'maps_played': maps_played,
                    'maps': maps_played,
                    'total_kills': total_kills,
                    'total_deaths': row[4],
                    'total_assists': row[5],
                    'avg_acs': round(row[6], 1) if row[6] else 0,
                    'avg_adr': round(row[7], 1) if row[7] else 0,
                    'avg_kast': round(row[8], 1) if row[8] else 0,
                    'total_first_bloods': row[9],
                    'kd_ratio': round(row[3] / row[4], 2) if row[4] > 0 else 0,
                    'avg_kills': avg_kills,
                    'over_count': over_count,
                    'under_count': under_count,
                    'over_pct': over_pct,
                }
                agents.append(agent_dict)
            
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

    # ==================== Team Matchup ====================

    def _normalize_team(self, team_name: str) -> str:
        """Return LIKE pattern for flexible team name matching."""
        return f'%{team_name.strip()}%'

    @staticmethod
    def _clean_team_name(raw: str) -> str:
        """Strip event-name pollution from a stored team name.

        The scraper sometimes stores team names with the event context appended,
        e.g. 'Nrg Vct 2025 Americas Stage 2 Lbf' instead of 'Nrg Esports'.
        We strip everything from the first year-digit or known event keyword.
        """
        import re
        if not raw:
            return raw
        # Truncate at first occurrence of a 4-digit year or event keyword
        m = re.search(
            r'\s+(?:20\d{2}|vct\b|champions?\s+tour\b|challengers?\b)',
            raw,
            flags=re.IGNORECASE,
        )
        return raw[:m.start()].strip() if m else raw.strip()

    def get_team_overview(self, team_name: str, year: int = 2026) -> Dict:
        """Aggregate team stats derived from player_map_stats + matches + players."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        pat = self._normalize_team(team_name)
        try:
            cursor.execute('''
                SELECT pms.match_id, pms.map_number, pms.kills, pms.deaths,
                       pms.map_score, ve.event_name, ve.id as event_id, p.team
                FROM player_map_stats pms
                JOIN matches m ON pms.match_id = m.id
                JOIN players p ON LOWER(pms.player_name) = LOWER(p.ign)
                JOIN vct_events ve ON m.event_id = ve.id
                WHERE LOWER(p.team) LIKE LOWER(?)
                  AND pms.kills > 0
                  AND ve.year = ?
                ORDER BY ve.id DESC
            ''', (pat, year))
            rows = cursor.fetchall()

            resolved_name = team_name
            # Per-event accumulators: {event_id: {event_name, kills, deaths, maps set, matches set, round_map dict}}
            event_data: Dict[int, Dict] = {}
            # Track rounds per unique (match_id, map_number) globally to avoid overcounting
            global_round_map: Dict[tuple, int] = {}

            for (match_id, map_number, kills, deaths, map_score, event_name, event_id, team) in rows:
                if not resolved_name or resolved_name == team_name:
                    resolved_name = team

                if event_id not in event_data:
                    event_data[event_id] = {
                        'event_name': event_name,
                        'kills': 0,
                        'deaths': 0,
                        'maps': set(),
                        'matches': set(),
                        'round_map': {},
                    }
                ed = event_data[event_id]
                ed['kills'] += kills or 0
                ed['deaths'] += deaths or 0
                ed['maps'].add((match_id, map_number))
                ed['matches'].add(match_id)

                map_key = (match_id, map_number)
                if map_key not in ed['round_map'] and map_score and '-' in map_score:
                    parts = map_score.split('-')
                    if len(parts) == 2:
                        try:
                            ed['round_map'][map_key] = int(parts[0]) + int(parts[1])
                        except ValueError:
                            pass

                # Global round tracking
                if map_key not in global_round_map and map_score and '-' in map_score:
                    parts = map_score.split('-')
                    if len(parts) == 2:
                        try:
                            global_round_map[map_key] = int(parts[0]) + int(parts[1])
                        except ValueError:
                            pass

            total_kills = total_deaths = 0
            total_maps_set: set = set()
            total_matches_set: set = set()
            events = []
            for event_id in sorted(event_data.keys(), reverse=True):
                ed = event_data[event_id]
                e_kills = ed['kills']
                e_deaths = ed['deaths']
                e_rounds = sum(ed['round_map'].values())
                e_maps = len(ed['maps'])
                e_matches = len(ed['matches'])
                total_kills += e_kills
                total_deaths += e_deaths
                total_maps_set.update(ed['maps'])
                total_matches_set.update(ed['matches'])
                events.append({
                    'event_name': ed['event_name'],
                    'event_id': event_id,
                    'fights_per_round': None,
                    'kills': e_kills,
                    'deaths': e_deaths,
                    'rounds': e_rounds,
                    'matches_played': e_matches,
                    'maps_played': e_maps,
                })

            total_rounds = sum(global_round_map.values())
            total_maps = len(total_maps_set)
            total_matches = len(total_matches_set)
            overall_kd = round(total_kills / total_deaths, 2) if total_deaths > 0 else None
            avg_rounds_per_map = round(total_rounds / total_maps, 1) if total_maps > 0 else None

            return {
                'resolved_name': resolved_name,
                'total_kills': total_kills,
                'total_deaths': total_deaths,
                'total_rounds': total_rounds,
                'total_matches': total_matches,
                'total_maps': total_maps,
                'avg_rounds_per_map': avg_rounds_per_map,
                'overall_kd': overall_kd,
                'overall_fpr': None,
                'events': events,
            }
        except Exception as e:
            logger.error(f"Error getting team overview for {team_name}: {e}")
            return {}
        finally:
            conn.close()

    def get_team_pick_ban_stats(self, team_name: str, year: int = 2026) -> Dict:
        """Aggregate map pick/ban rates from match_pick_bans for matches the team played."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        pat = self._normalize_team(team_name)
        try:
            cursor.execute('''
                SELECT mpb.first_ban, mpb.second_ban, mpb.first_pick, mpb.second_pick
                FROM match_pick_bans mpb
                JOIN matches m ON mpb.match_id = m.id
                JOIN vct_events ve ON m.event_id = ve.id
                WHERE (LOWER(m.team1) LIKE LOWER(?) OR LOWER(m.team2) LIKE LOWER(?))
                  AND ve.year = ?
            ''', (pat, pat, year))
            rows = cursor.fetchall()
            total = len(rows)
            counts: Dict[str, Dict] = {
                'first_ban': {}, 'second_ban': {},
                'first_pick': {}, 'second_pick': {},
            }
            for (fb, sb, fp, sp) in rows:
                for key, val in [('first_ban', fb), ('second_ban', sb), ('first_pick', fp), ('second_pick', sp)]:
                    if val:
                        counts[key][val] = counts[key].get(val, 0) + 1
            result: Dict = {'total_matches': total}
            for action in counts:
                result[action] = sorted(
                    [{'map': m, 'rate': round(c / total, 3) if total else 0}
                     for m, c in counts[action].items()],
                    key=lambda x: -x['rate']
                )[:5]
            return result
        except Exception as e:
            logger.error(f"Error getting team pick/ban stats for {team_name}: {e}")
            return {}
        finally:
            conn.close()

    def get_team_map_records(self, team_name: str, year: int = 2026) -> List[Dict]:
        """Per-map win/loss record and avg rounds for a team."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        pat = self._normalize_team(team_name)
        try:
            cursor.execute('''
                SELECT m.id, m.team1, m.team2, pms.map_name, MIN(pms.map_score) as map_score
                FROM player_map_stats pms
                JOIN matches m ON pms.match_id = m.id
                JOIN vct_events ve ON m.event_id = ve.id
                WHERE (LOWER(m.team1) LIKE LOWER(?) OR LOWER(m.team2) LIKE LOWER(?))
                  AND pms.map_score IS NOT NULL AND pms.map_score LIKE '%-%'
                  AND pms.kills > 0 AND pms.map_name IS NOT NULL
                  AND ve.year = ?
                GROUP BY m.id, pms.map_number, pms.map_name
            ''', (pat, pat, year))
            rows = cursor.fetchall()
            map_stats: Dict[str, Dict] = {}
            tname_lower = team_name.lower()
            for (match_id, team1, team2, map_name, map_score) in rows:
                if not map_score or '-' not in map_score:
                    continue
                parts = map_score.split('-')
                if len(parts) != 2:
                    continue
                try:
                    t1_rounds = int(parts[0])
                    t2_rounds = int(parts[1])
                except ValueError:
                    continue
                is_team1 = tname_lower in (team1 or '').lower()
                is_team2 = tname_lower in (team2 or '').lower()
                if not is_team1 and not is_team2:
                    continue
                team_rounds = t1_rounds if is_team1 else t2_rounds
                opp_rounds = t2_rounds if is_team1 else t1_rounds
                total_rounds = t1_rounds + t2_rounds
                won = team_rounds > opp_rounds
                if map_name not in map_stats:
                    map_stats[map_name] = {'map': map_name, 'wins': 0, 'losses': 0,
                                           'team_rounds': 0, 'opp_rounds': 0,
                                           'total_rounds': 0, 'played': 0}
                map_stats[map_name]['wins'] += 1 if won else 0
                map_stats[map_name]['losses'] += 0 if won else 1
                map_stats[map_name]['team_rounds'] += team_rounds
                map_stats[map_name]['opp_rounds'] += opp_rounds
                map_stats[map_name]['total_rounds'] += total_rounds
                map_stats[map_name]['played'] += 1
            result = []
            for ms in map_stats.values():
                played = ms['played']
                result.append({
                    'map': ms['map'],
                    'wins': ms['wins'],
                    'losses': ms['losses'],
                    'played': played,
                    'win_rate': round(100 * ms['wins'] / played, 1) if played > 0 else 0,
                    'avg_team_rounds': round(ms['team_rounds'] / played, 1) if played > 0 else 0,
                    'avg_opp_rounds': round(ms['opp_rounds'] / played, 1) if played > 0 else 0,
                    'avg_total_rounds': round(ms['total_rounds'] / played, 1) if played > 0 else 0,
                })
            return sorted(result, key=lambda x: -x['played'])
        except Exception as e:
            logger.error(f"Error getting team map records for {team_name}: {e}")
            return []
        finally:
            conn.close()

    def get_team_recent_matches(self, team_name: str, limit: int = 15, year: int = 2026) -> List[Dict]:
        """Recent matches for a team ordered by newest first."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        pat = self._normalize_team(team_name)
        tname_lower = team_name.lower()
        try:
            cursor.execute('''
                SELECT m.id, m.match_url, m.team1, m.team2, ve.event_name,
                       mn.winner, mn.team1_maps, mn.team2_maps
                FROM matches m
                JOIN vct_events ve ON m.event_id = ve.id
                LEFT JOIN moneyline_matches mn ON m.match_url = mn.match_url
                WHERE (LOWER(m.team1) LIKE LOWER(?) OR LOWER(m.team2) LIKE LOWER(?))
                  AND ve.year = ?
                ORDER BY m.id DESC
                LIMIT ?
            ''', (pat, pat, year, limit))
            rows = cursor.fetchall()
            results = []
            for (mid, url, t1, t2, event_name, winner, t1_maps, t2_maps) in rows:
                is_team1 = tname_lower in (t1 or '').lower()
                raw_opp = t2 if is_team1 else t1
                opponent = self._clean_team_name(raw_opp or '')
                team_maps = (t1_maps or 0) if is_team1 else (t2_maps or 0)
                opp_maps = (t2_maps or 0) if is_team1 else (t1_maps or 0)
                won = None
                if winner:
                    won = tname_lower in (winner or '').lower()
                results.append({
                    'match_id': mid,
                    'match_url': url,
                    'opponent': opponent,
                    'event_name': event_name,
                    'result': 'W' if won is True else ('L' if won is False else None),
                    'score': f'{team_maps}-{opp_maps}' if (t1_maps is not None and t2_maps is not None) else None,
                })
            return results
        except Exception as e:
            logger.error(f"Error getting recent matches for {team_name}: {e}")
            return []
        finally:
            conn.close()

    def get_team_comps_per_map(self, team_name: str, year: int = 2026) -> Dict[str, List[Dict]]:
        """Full 5-agent compositions per map for a team.

        Primary: joins players.team for team assignment.
        Fallback: uses row-insertion order (pms.id) to split 10 players into team1/team2
                  when the players table lacks enough coverage for this team.
        """
        from collections import Counter as _Counter
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        pat = self._normalize_team(team_name)
        tname_lower = team_name.lower()

        def _build_result(map_plays: Dict) -> Dict[str, List[Dict]]:
            map_comp_counts: Dict[str, _Counter] = {}
            for (match_id, map_number, map_name), agents in map_plays.items():
                if len(agents) < 4:
                    continue
                comp = tuple(sorted(agents))
                if map_name not in map_comp_counts:
                    map_comp_counts[map_name] = _Counter()
                map_comp_counts[map_name][comp] += 1
            out: Dict[str, List[Dict]] = {}
            for map_name, comp_counter in sorted(map_comp_counts.items()):
                total = sum(comp_counter.values())
                out[map_name] = [
                    {'agents': list(comp), 'count': cnt, 'pct': round(cnt / total * 100, 1)}
                    for comp, cnt in comp_counter.most_common()
                ]
            return out

        try:
            # ── Primary: players.team join ──────────────────────────────────
            cursor.execute('''
                SELECT pms.match_id, pms.map_number, pms.map_name, pms.agent
                FROM player_map_stats pms
                JOIN matches m ON pms.match_id = m.id
                JOIN vct_events ve ON m.event_id = ve.id
                JOIN players p ON LOWER(pms.player_name) = LOWER(p.ign)
                WHERE LOWER(p.team) LIKE LOWER(?)
                  AND pms.agent IS NOT NULL AND pms.map_name IS NOT NULL AND pms.kills > 0
                  AND ve.year = ?
            ''', (pat, year))
            rows = cursor.fetchall()

            map_plays: Dict[tuple, List[str]] = {}
            for (match_id, map_number, map_name, agent) in rows:
                key = (match_id, map_number, map_name)
                map_plays.setdefault(key, []).append(agent)

            # Count valid maps (>= 4 agents found via players table)
            valid_maps = sum(1 for agents in map_plays.values() if len(agents) >= 4)

            if valid_maps >= 3:
                return _build_result(map_plays)

            # ── Fallback: row-insertion order split ─────────────────────────
            # For each match, the populate script inserted team1's players first
            # (lower pms.id) then team2's players. Split accordingly.
            cursor.execute('''
                SELECT pms.id, pms.match_id, pms.map_number, pms.map_name,
                       pms.agent, m.team1, m.team2
                FROM player_map_stats pms
                JOIN matches m ON pms.match_id = m.id
                JOIN vct_events ve ON m.event_id = ve.id
                WHERE (LOWER(m.team1) LIKE LOWER(?) OR LOWER(m.team2) LIKE LOWER(?))
                  AND pms.agent IS NOT NULL AND pms.map_name IS NOT NULL AND pms.kills > 0
                  AND ve.year = ?
                ORDER BY pms.match_id, pms.map_number, pms.id
            ''', (pat, pat, year))
            fb_rows = cursor.fetchall()

            # Group by (match_id, map_number) preserving insertion order
            from collections import defaultdict as _dd
            grp: Dict = _dd(lambda: {'map_name': None, 'team1': None, 'team2': None, 'agents': []})
            for (row_id, match_id, map_number, map_name, agent, t1, t2) in fb_rows:
                key = (match_id, map_number)
                grp[key]['map_name'] = map_name
                grp[key]['team1'] = t1
                grp[key]['team2'] = t2
                grp[key]['agents'].append(agent)

            fb_plays: Dict[tuple, List[str]] = {}
            for (match_id, map_number), info in grp.items():
                agents_all = info['agents']
                n = len(agents_all)
                if n < 8:
                    continue
                is_team1 = tname_lower in (info['team1'] or '').lower()
                half = n // 2
                team_agents = agents_all[:half] if is_team1 else agents_all[half:]
                fb_plays[(match_id, map_number, info['map_name'])] = team_agents

            return _build_result(fb_plays)

        except Exception as e:
            logger.error(f"Error getting team comps for {team_name}: {e}")
            return {}
        finally:
            conn.close()

    def get_head_to_head(self, team1_name: str, team2_name: str, year: int = 2026) -> List[Dict]:
        """All matches between two teams."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        p1 = self._normalize_team(team1_name)
        p2 = self._normalize_team(team2_name)
        try:
            cursor.execute('''
                SELECT m.id, m.match_url, m.team1, m.team2, ve.event_name,
                       mn.winner, mn.team1_maps, mn.team2_maps
                FROM matches m
                JOIN vct_events ve ON m.event_id = ve.id
                LEFT JOIN moneyline_matches mn ON m.match_url = mn.match_url
                WHERE ((LOWER(m.team1) LIKE LOWER(?) AND LOWER(m.team2) LIKE LOWER(?))
                   OR  (LOWER(m.team1) LIKE LOWER(?) AND LOWER(m.team2) LIKE LOWER(?)))
                  AND ve.year = ?
                ORDER BY m.id DESC
            ''', (p1, p2, p2, p1, year))
            rows = cursor.fetchall()
            results = []
            for (mid, url, t1, t2, event_name, winner, t1_maps, t2_maps) in rows:
                results.append({
                    'match_id': mid,
                    'match_url': url,
                    'team1': self._clean_team_name(t1 or ''),
                    'team2': self._clean_team_name(t2 or ''),
                    'event_name': event_name,
                    'winner': self._clean_team_name(winner or '') if winner else None,
                    'team1_maps': t1_maps,
                    'team2_maps': t2_maps,
                })
            return results
        except Exception as e:
            logger.error(f"Error getting H2H for {team1_name} vs {team2_name}: {e}")
            return []
        finally:
            conn.close()

    def get_team_fights_per_round(self, team_name: str, year: int = 2026) -> Dict[str, Dict]:
        """Per-map fights-per-round stats for a team.

        For each map the team has played, computes kills, deaths, rounds,
        fights_per_round, kills_per_round, deaths_per_round, and sample_maps.
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        pat = self._normalize_team(team_name)
        tname_lower = team_name.lower()

        def _aggregate(rows) -> Dict[str, Dict]:
            # rows: (match_id, map_number, map_name, kills, deaths, map_score)
            # Accumulate per-map totals; deduplicate rounds by (match_id, map_number)
            map_data: Dict[str, Dict] = {}
            for (match_id, map_number, map_name, kills, deaths, map_score) in rows:
                if not map_name:
                    continue
                if map_name not in map_data:
                    map_data[map_name] = {'kills': 0, 'deaths': 0, 'round_map': {}, 'map_keys': set()}
                md = map_data[map_name]
                md['kills'] += kills or 0
                md['deaths'] += deaths or 0
                md['map_keys'].add((match_id, map_number))
                rkey = (match_id, map_number)
                if rkey not in md['round_map'] and map_score and '-' in map_score:
                    parts = map_score.split('-')
                    if len(parts) == 2:
                        try:
                            md['round_map'][rkey] = int(parts[0]) + int(parts[1])
                        except ValueError:
                            pass
            result: Dict[str, Dict] = {}
            for map_name, md in map_data.items():
                total_rounds = sum(md['round_map'].values())
                sample_maps = len(md['map_keys'])
                k = md['kills']
                d = md['deaths']
                result[map_name] = {
                    'kills': k,
                    'deaths': d,
                    'rounds': total_rounds,
                    'fights_per_round': round((k + d) / total_rounds, 3) if total_rounds > 0 else None,
                    'kills_per_round': round(k / total_rounds, 3) if total_rounds > 0 else None,
                    'deaths_per_round': round(d / total_rounds, 3) if total_rounds > 0 else None,
                    'sample_maps': sample_maps,
                }
            return result

        try:
            # Primary: players.team join
            cursor.execute('''
                SELECT pms.match_id, pms.map_number, pms.map_name,
                       pms.kills, pms.deaths, pms.map_score
                FROM player_map_stats pms
                JOIN matches m ON pms.match_id = m.id
                JOIN vct_events ve ON m.event_id = ve.id
                JOIN players p ON LOWER(pms.player_name) = LOWER(p.ign)
                WHERE LOWER(p.team) LIKE LOWER(?)
                  AND pms.kills > 0 AND pms.map_name IS NOT NULL
                  AND ve.year = ?
            ''', (pat, year))
            rows = cursor.fetchall()

            result = _aggregate(rows)
            valid_maps = sum(1 for v in result.values() if v['sample_maps'] >= 1)

            if valid_maps >= 3:
                return result

            # Fallback: matches.team1/team2 LIKE match
            cursor.execute('''
                SELECT pms.id, pms.match_id, pms.map_number, pms.map_name,
                       pms.kills, pms.deaths, pms.map_score, m.team1, m.team2
                FROM player_map_stats pms
                JOIN matches m ON pms.match_id = m.id
                JOIN vct_events ve ON m.event_id = ve.id
                WHERE (LOWER(m.team1) LIKE LOWER(?) OR LOWER(m.team2) LIKE LOWER(?))
                  AND pms.kills > 0 AND pms.map_name IS NOT NULL
                  AND ve.year = ?
                ORDER BY pms.match_id, pms.map_number, pms.id
            ''', (pat, pat, year))
            fb_rows = cursor.fetchall()

            # Split players into team1/team2 by insertion order
            from collections import defaultdict as _dd
            grp: Dict = _dd(lambda: {'rows': [], 'team1': None, 'team2': None})
            for (row_id, match_id, map_number, map_name, kills, deaths, map_score, t1, t2) in fb_rows:
                key = (match_id, map_number)
                grp[key]['rows'].append((row_id, map_name, kills, deaths, map_score))
                grp[key]['team1'] = t1
                grp[key]['team2'] = t2

            filtered_rows = []
            for (match_id, map_number), info in grp.items():
                all_rows = info['rows']
                n = len(all_rows)
                if n < 8:
                    continue
                is_team1 = tname_lower in (info['team1'] or '').lower()
                half = n // 2
                team_rows = all_rows[:half] if is_team1 else all_rows[half:]
                for (_, map_name, kills, deaths, map_score) in team_rows:
                    filtered_rows.append((match_id, map_number, map_name, kills, deaths, map_score))

            return _aggregate(filtered_rows)
        except Exception as e:
            logger.error(f"Error getting team fights per round for {team_name}: {e}")
            return {}
        finally:
            conn.close()

    def get_team_per_map_kd(self, team_name: str, year: int = 2026) -> Dict[str, Dict]:
        """Per-map K/D breakdown for a team.

        Returns kills, deaths, assists, kd, rounds, sample_maps, is_low_sample per map.
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        pat = self._normalize_team(team_name)
        tname_lower = team_name.lower()

        def _aggregate(rows) -> Dict[str, Dict]:
            # rows: (match_id, map_number, map_name, kills, deaths, assists, map_score)
            map_data: Dict[str, Dict] = {}
            for (match_id, map_number, map_name, kills, deaths, assists, map_score) in rows:
                if not map_name:
                    continue
                if map_name not in map_data:
                    map_data[map_name] = {'kills': 0, 'deaths': 0, 'assists': 0,
                                          'round_map': {}, 'map_keys': set()}
                md = map_data[map_name]
                md['kills'] += kills or 0
                md['deaths'] += deaths or 0
                md['assists'] += assists or 0
                md['map_keys'].add((match_id, map_number))
                rkey = (match_id, map_number)
                if rkey not in md['round_map'] and map_score and '-' in map_score:
                    parts = map_score.split('-')
                    if len(parts) == 2:
                        try:
                            md['round_map'][rkey] = int(parts[0]) + int(parts[1])
                        except ValueError:
                            pass
            result: Dict[str, Dict] = {}
            for map_name, md in map_data.items():
                total_rounds = sum(md['round_map'].values())
                sample_maps = len(md['map_keys'])
                k = md['kills']
                d = md['deaths']
                a = md['assists']
                result[map_name] = {
                    'kills': k,
                    'deaths': d,
                    'assists': a,
                    'kd': round(k / d, 2) if d > 0 else None,
                    'rounds': total_rounds,
                    'sample_maps': sample_maps,
                    'is_low_sample': sample_maps < 5,
                }
            return result

        try:
            # Primary: players.team join
            cursor.execute('''
                SELECT pms.match_id, pms.map_number, pms.map_name,
                       pms.kills, pms.deaths, pms.assists, pms.map_score
                FROM player_map_stats pms
                JOIN matches m ON pms.match_id = m.id
                JOIN vct_events ve ON m.event_id = ve.id
                JOIN players p ON LOWER(pms.player_name) = LOWER(p.ign)
                WHERE LOWER(p.team) LIKE LOWER(?)
                  AND pms.kills > 0 AND pms.map_name IS NOT NULL
                  AND ve.year = ?
            ''', (pat, year))
            rows = cursor.fetchall()

            result = _aggregate(rows)
            valid_maps = sum(1 for v in result.values() if v['sample_maps'] >= 1)

            if valid_maps >= 3:
                return result

            # Fallback: matches.team1/team2 LIKE match
            cursor.execute('''
                SELECT pms.id, pms.match_id, pms.map_number, pms.map_name,
                       pms.kills, pms.deaths, pms.assists, pms.map_score,
                       m.team1, m.team2
                FROM player_map_stats pms
                JOIN matches m ON pms.match_id = m.id
                JOIN vct_events ve ON m.event_id = ve.id
                WHERE (LOWER(m.team1) LIKE LOWER(?) OR LOWER(m.team2) LIKE LOWER(?))
                  AND pms.kills > 0 AND pms.map_name IS NOT NULL
                  AND ve.year = ?
                ORDER BY pms.match_id, pms.map_number, pms.id
            ''', (pat, pat, year))
            fb_rows = cursor.fetchall()

            from collections import defaultdict as _dd
            grp: Dict = _dd(lambda: {'rows': [], 'team1': None, 'team2': None})
            for (row_id, match_id, map_number, map_name, kills, deaths, assists, map_score, t1, t2) in fb_rows:
                key = (match_id, map_number)
                grp[key]['rows'].append((row_id, map_name, kills, deaths, assists, map_score))
                grp[key]['team1'] = t1
                grp[key]['team2'] = t2

            filtered_rows = []
            for (match_id, map_number), info in grp.items():
                all_rows = info['rows']
                n = len(all_rows)
                if n < 8:
                    continue
                is_team1 = tname_lower in (info['team1'] or '').lower()
                half = n // 2
                team_rows = all_rows[:half] if is_team1 else all_rows[half:]
                for (_, map_name, kills, deaths, assists, map_score) in team_rows:
                    filtered_rows.append((match_id, map_number, map_name, kills, deaths, assists, map_score))

            return _aggregate(filtered_rows)
        except Exception as e:
            logger.error(f"Error getting team per-map K/D for {team_name}: {e}")
            return {}
        finally:
            conn.close()

    def get_projected_map_score(self, team1_name: str, team2_name: str, year: int = 2026) -> Dict[str, Dict]:
        """Project likely score margin per map between two teams.

        Uses each team's avg rounds scored/conceded from get_team_map_records
        to project winner, score, and confidence for each shared map.
        """
        t1_records = self.get_team_map_records(team1_name, year=year)
        t2_records = self.get_team_map_records(team2_name, year=year)

        # Index by map name
        t1_by_map = {r['map']: r for r in t1_records}
        t2_by_map = {r['map']: r for r in t2_records}

        shared_maps = set(t1_by_map.keys()) & set(t2_by_map.keys())
        result: Dict[str, Dict] = {}

        for map_name in sorted(shared_maps):
            t1 = t1_by_map[map_name]
            t2 = t2_by_map[map_name]

            # Project rounds: average of team's offense vs opponent's defense
            # team1 projected = avg of (t1 avg scored, t2 avg conceded)
            t1_proj = (t1['avg_team_rounds'] + t2['avg_opp_rounds']) / 2
            t2_proj = (t2['avg_team_rounds'] + t1['avg_opp_rounds']) / 2

            # Determine winner and build projected score
            if t1_proj >= t2_proj:
                winner = 'team1'
                # Scale to a realistic Valorant score (winner gets 13)
                if t2_proj > 0:
                    ratio = t1_proj / t2_proj
                    loser_rounds = max(0, min(12, round(13 / ratio)))
                else:
                    loser_rounds = 0
                score_str = f"13-{loser_rounds}"
            else:
                winner = 'team2'
                if t1_proj > 0:
                    ratio = t2_proj / t1_proj
                    loser_rounds = max(0, min(12, round(13 / ratio)))
                else:
                    loser_rounds = 0
                score_str = f"{loser_rounds}-13"

            # Confidence: based on sample size and win-rate margin
            sample1 = t1['played']
            sample2 = t2['played']
            min_sample = min(sample1, sample2)
            total_sample = sample1 + sample2
            # Sample size factor: ramps from 0 to 1, saturates around 10+ maps each
            sample_factor = min(1.0, min_sample / 10.0)
            # Win rate margin factor
            wr1 = t1.get('win_rate', 50) / 100.0
            wr2 = t2.get('win_rate', 50) / 100.0
            margin = abs(wr1 - wr2)
            margin_factor = min(1.0, margin * 2)  # 50% margin -> 1.0
            confidence = round(0.5 * sample_factor + 0.5 * margin_factor, 2)

            result[map_name] = {
                'projectedWinner': winner,
                'projectedScore': score_str,
                'confidence': confidence,
                'team1AvgRounds': t1['avg_team_rounds'],
                'team2AvgRounds': t2['avg_team_rounds'],
                'sampleMaps1': sample1,
                'sampleMaps2': sample2,
            }

        return result

    def save_match_map_halves(self, match_id: int, map_number: int, map_name: str,
                              team_name: str, atk_rounds: int, def_rounds: int):
        """Save attack/defense round data for a team on a specific map."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            total = atk_rounds + def_rounds
            cursor.execute('''
                INSERT OR REPLACE INTO match_map_halves
                (match_id, map_number, map_name, team_name, atk_rounds_won, def_rounds_won, total_rounds)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (match_id, map_number, map_name, team_name, atk_rounds, def_rounds, total))
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving match_map_halves: {e}")
            conn.rollback()
        finally:
            conn.close()

    def get_team_atk_def_rates(self, team_name: str, year: int = 2026) -> Dict[str, Dict]:
        """Attack/defense win rates per map for a team.

        Returns {map_name: {atk_win_rate, def_win_rate, atk_rounds_won, def_rounds_won,
                             total_rounds, sample_maps}}
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        pat = self._normalize_team(team_name)
        try:
            cursor.execute('''
                SELECT mmh.map_name,
                       SUM(mmh.atk_rounds_won) as total_atk_won,
                       SUM(mmh.def_rounds_won) as total_def_won,
                       SUM(mmh.total_rounds) as total_rounds,
                       COUNT(*) as sample_maps
                FROM match_map_halves mmh
                JOIN matches m ON mmh.match_id = m.id
                JOIN vct_events ve ON m.event_id = ve.id
                WHERE LOWER(mmh.team_name) LIKE LOWER(?)
                  AND ve.year = ?
                  AND mmh.map_name IS NOT NULL
                GROUP BY mmh.map_name
                ORDER BY sample_maps DESC
            ''', (pat, year))
            rows = cursor.fetchall()

            result = {}
            for (map_name, atk_won, def_won, total_rounds, sample_maps) in rows:
                if not map_name or map_name == 'Unknown':
                    continue
                # In standard Valorant: 12 rounds per regulation half (atk then def, then swap).
                # total_atk_rounds_played = total_rounds - def_won  (opponent's def rounds = our atk rounds played)
                # But simpler: atk_win_rate = atk_rounds_won / (atk_rounds_won + opp_def_rounds_won)
                # Since we only have this team's data, use total_rounds / 2 as approximate rounds per side.
                # More precisely: atk_rate = atk_won / total across all maps.
                total_side = atk_won + def_won  # = total rounds won by this team
                atk_rate = atk_won / (total_side) if total_side > 0 else 0.5
                def_rate = def_won / (total_side) if total_side > 0 else 0.5
                result[map_name] = {
                    'atk_win_rate': round(atk_rate, 3),
                    'def_win_rate': round(def_rate, 3),
                    'atk_rounds_won': atk_won,
                    'def_rounds_won': def_won,
                    'total_rounds': total_rounds,
                    'sample_maps': sample_maps,
                }
            return result
        except Exception as e:
            logger.error(f"Error getting atk/def rates for {team_name}: {e}")
            return {}
        finally:
            conn.close()

    def get_team_matchup_data(self, team_name: str) -> Dict:
        """Master method: all matchup data for one team."""
        return {
            'overview': self.get_team_overview(team_name),
            'pick_ban': self.get_team_pick_ban_stats(team_name),
            'map_records': self.get_team_map_records(team_name),
            'recent_matches': self.get_team_recent_matches(team_name),
            'comps_per_map': self.get_team_comps_per_map(team_name),
            'fights_per_round': self.get_team_fights_per_round(team_name),
            'per_map_kd': self.get_team_per_map_kd(team_name),
        }

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
