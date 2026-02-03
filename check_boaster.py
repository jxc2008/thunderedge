#!/usr/bin/env python3
"""Check database for boaster's data"""
from backend.database import Database
from config import Config

db = Database(Config.DATABASE_PATH)

# Check boaster's events
print("=== Checking boaster's cached events ===")
events = db.get_player_all_event_stats('boaster')
print(f"Found {len(events)} events for boaster")
for e in events[:10]:
    print(f"  {e['event_name']} - {e['rounds_played']} rounds - URL: {e['event_url']}")

# Check map kills for each event
print("\n=== Checking map kills per event ===")
for e in events[:5]:
    event_db = db.get_vct_event(e['event_url'])
    if event_db:
        map_kills = db.get_player_map_kills_for_event('boaster', event_db['id'])
        print(f"  {e['event_name']}: {len(map_kills)} maps")
        if len(map_kills) > 0:
            print(f"    Sample kills: {map_kills[:5]}")
    else:
        print(f"  {e['event_name']}: Event not found in vct_events table")

# Check all EMEA events in database
print("\n=== Checking EMEA events in database ===")
import sqlite3
conn = sqlite3.connect(Config.DATABASE_PATH, timeout=30.0)
cursor = conn.cursor()
cursor.execute("SELECT event_name, event_url, region FROM vct_events WHERE region = 'EMEA' ORDER BY id")
emea_events = cursor.fetchall()
print(f"Found {len(emea_events)} EMEA events")
for event in emea_events:
    print(f"  {event[0]} - {event[1]}")

# Check player_map_stats for boaster
print("\n=== Checking player_map_stats for boaster ===")
cursor.execute("SELECT DISTINCT player_name FROM player_map_stats WHERE LOWER(player_name) LIKE '%boaster%'")
players = cursor.fetchall()
print(f"Found players matching 'boaster': {[p[0] for p in players]}")

# Check if boaster has any map stats
cursor.execute("""
    SELECT COUNT(*) 
    FROM player_map_stats pms
    JOIN matches m ON pms.match_id = m.id
    JOIN vct_events ve ON m.event_id = ve.id
    WHERE LOWER(pms.player_name) LIKE '%boaster%' AND ve.region = 'EMEA'
""")
count = cursor.fetchone()[0]
print(f"Total EMEA map stats for boaster: {count}")

# Check total map stats for EMEA events
cursor.execute("""
    SELECT COUNT(*) 
    FROM player_map_stats pms
    JOIN matches m ON pms.match_id = m.id
    JOIN vct_events ve ON m.event_id = ve.id
    WHERE ve.region = 'EMEA'
""")
total_emea = cursor.fetchone()[0]
print(f"Total EMEA map stats (all players): {total_emea}")

# Check Americas
cursor.execute("""
    SELECT COUNT(*) 
    FROM player_map_stats pms
    JOIN matches m ON pms.match_id = m.id
    JOIN vct_events ve ON m.event_id = ve.id
    WHERE ve.region = 'Americas'
""")
total_americas = cursor.fetchone()[0]
print(f"Total Americas map stats (all players): {total_americas}")

# Check Pacific
cursor.execute("""
    SELECT COUNT(*) 
    FROM player_map_stats pms
    JOIN matches m ON pms.match_id = m.id
    JOIN vct_events ve ON m.event_id = ve.id
    WHERE ve.region = 'Pacific'
""")
total_pacific = cursor.fetchone()[0]
print(f"Total Pacific map stats (all players): {total_pacific}")

# Check matches per region
cursor.execute("""
    SELECT ve.region, COUNT(DISTINCT m.id) as match_count
    FROM matches m
    JOIN vct_events ve ON m.event_id = ve.id
    GROUP BY ve.region
""")
matches_by_region = cursor.fetchall()
print(f"\nMatches by region:")
for region, count in matches_by_region:
    print(f"  {region}: {count} matches")

# Check player_event_stats for boaster
print("\n=== Checking player_event_stats for boaster ===")
cursor.execute("""
    SELECT pes.*, ve.event_name, ve.region
    FROM player_event_stats pes
    JOIN vct_events ve ON pes.event_id = ve.id
    WHERE LOWER(pes.player_name) = 'boaster'
    ORDER BY pes.rounds_played DESC
""")
player_events = cursor.fetchall()
print(f"Found {len(player_events)} player_event_stats entries for boaster")
for pe in player_events[:5]:
    print(f"  {pe[8]} ({pe[9]}): {pe[5]} rounds, KPR: {pe[4]}")

# Check matches for EMEA events
print("\n=== Checking matches for EMEA events ===")
cursor.execute("""
    SELECT ve.event_name, COUNT(m.id) as match_count
    FROM vct_events ve
    LEFT JOIN matches m ON ve.id = m.event_id
    WHERE ve.region = 'EMEA'
    GROUP BY ve.id, ve.event_name
""")
emea_matches = cursor.fetchall()
for event_name, count in emea_matches:
    print(f"  {event_name}: {count} matches")

# Check matches for Americas events
print("\n=== Checking matches for Americas events ===")
cursor.execute("""
    SELECT ve.event_name, COUNT(m.id) as match_count
    FROM vct_events ve
    LEFT JOIN matches m ON ve.id = m.event_id
    WHERE ve.region = 'Americas'
    GROUP BY ve.id, ve.event_name
""")
americas_matches = cursor.fetchall()
for event_name, count in americas_matches:
    print(f"  {event_name}: {count} matches")

conn.close()
