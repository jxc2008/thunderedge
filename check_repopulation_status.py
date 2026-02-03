#!/usr/bin/env python3
"""Check repopulation status"""
from backend.database import Database
from config import Config
import sqlite3

db = Database(Config.DATABASE_PATH)
conn = sqlite3.connect(Config.DATABASE_PATH, timeout=30.0)
cursor = conn.cursor()

print("=== Repopulation Status ===")
print()

# Check Americas/EMEA events
cursor.execute("""
    SELECT ve.event_name, ve.region, COUNT(DISTINCT m.id) as matches, COUNT(pms.id) as map_stats
    FROM vct_events ve
    LEFT JOIN matches m ON ve.id = m.event_id
    LEFT JOIN player_map_stats pms ON m.id = pms.match_id
    WHERE ve.region IN ('Americas', 'EMEA')
    GROUP BY ve.id, ve.event_name, ve.region
    ORDER BY ve.id
""")

print("Americas/EMEA Events:")
print(f"{'Event':<40} {'Region':<10} {'Matches':<10} {'Map Stats':<12}")
print("-" * 75)
for row in cursor.fetchall():
    event_name, region, matches, map_stats = row
    print(f"{event_name:<40} {region:<10} {matches:<10} {map_stats:<12}")

print()
print("=== Totals ===")
cursor.execute("""
    SELECT ve.region, COUNT(DISTINCT m.id) as matches, COUNT(pms.id) as map_stats
    FROM vct_events ve
    LEFT JOIN matches m ON ve.id = m.event_id
    LEFT JOIN player_map_stats pms ON m.id = pms.match_id
    WHERE ve.region IN ('Americas', 'EMEA')
    GROUP BY ve.region
""")
for row in cursor.fetchall():
    region, matches, map_stats = row
    print(f"{region}: {matches} matches, {map_stats} map stats")

conn.close()
