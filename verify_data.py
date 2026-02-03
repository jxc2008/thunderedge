import sys, sqlite3
sys.path.insert(0, '.')
from config import Config

conn = sqlite3.connect(Config.DATABASE_PATH)
c = conn.cursor()

player = 'udotan'

# Check map stats for udotan
print(f"{'='*60}")
print(f"MAP STATS FOR {player.upper()} (AFTER FIX):")
print(f"{'='*60}")

c.execute("""
    SELECT ve.event_name, COUNT(*) as maps, SUM(pms.kills) as total_kills
    FROM player_map_stats pms
    JOIN matches m ON pms.match_id = m.id
    JOIN vct_events ve ON m.event_id = ve.id
    WHERE LOWER(pms.player_name) = LOWER(?)
    GROUP BY ve.event_name
    ORDER BY ve.event_name
""", (player,))
total = 0
for r in c.fetchall():
    print(f"  {r[0]}: {r[1]} maps, {r[2]} total kills")
    total += r[1]
print(f"\n  TOTAL: {total} maps")

# Also check aspas and f0rsaken
for p in ['aspas', 'f0rsaken']:
    print(f"\n{'='*60}")
    print(f"MAP STATS FOR {p.upper()}:")
    print(f"{'='*60}")
    
    c.execute("""
        SELECT ve.event_name, COUNT(*) as maps
        FROM player_map_stats pms
        JOIN matches m ON pms.match_id = m.id
        JOIN vct_events ve ON m.event_id = ve.id
        WHERE LOWER(pms.player_name) = LOWER(?)
        GROUP BY ve.event_name
        ORDER BY ve.event_name
    """, (p,))
    total = 0
    for r in c.fetchall():
        print(f"  {r[0]}: {r[1]} maps")
        total += r[1]
    print(f"\n  TOTAL: {total} maps")

conn.close()
