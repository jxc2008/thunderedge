#!/usr/bin/env python3
"""
Migrate database to add new columns for repopulation.
Adds: map_name, agent, acs, adr, kast, first_bloods to player_map_stats
"""

import sqlite3
import os
from config import Config

def migrate_database():
    db_path = Config.DATABASE_PATH
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    print("=" * 80)
    print("DATABASE MIGRATION - Adding New Columns")
    print("=" * 80)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get current columns
    cursor.execute("PRAGMA table_info(player_map_stats)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    print(f"\nExisting columns: {existing_columns}")
    
    # Columns to add
    new_columns = [
        ('map_name', 'TEXT'),
        ('agent', 'TEXT'),
        ('acs', 'INTEGER'),
        ('adr', 'INTEGER'),
        ('kast', 'REAL'),
        ('first_bloods', 'INTEGER')
    ]
    
    print("\nAdding new columns:")
    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            try:
                cursor.execute(f'ALTER TABLE player_map_stats ADD COLUMN {col_name} {col_type}')
                print(f"  [OK] Added {col_name} ({col_type})")
            except sqlite3.OperationalError as e:
                if 'duplicate column' in str(e).lower():
                    print(f"  - {col_name} already exists")
                else:
                    print(f"  [ERROR] Error adding {col_name}: {e}")
        else:
            print(f"  - {col_name} already exists")
    
    # Create match_pick_bans table if doesn't exist
    print("\nCreating match_pick_bans table:")
    try:
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
        print("  [OK] match_pick_bans table ready")
    except Exception as e:
        print(f"  [ERROR] Error: {e}")
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 80)
    print("MIGRATION COMPLETE")
    print("=" * 80)
    print("\nDatabase is ready for repopulation with:")
    print("  - Map names (Bind, Haven, etc.)")
    print("  - Agent per player per map")
    print("  - ACS, ADR, KAST stats")
    print("  - First bloods count")
    print("  - Pick/ban sequence per match")
    print("  - Map scores (already added)")

if __name__ == '__main__':
    migrate_database()
