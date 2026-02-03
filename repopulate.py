# Quick repopulate script - no confirmation
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scripts.populate_database import DatabasePopulator, VCT_2025_EVENTS

print(f"Populating {len(VCT_2025_EVENTS)} events...")
populator = DatabasePopulator()
populator.populate_all_events()

# Print stats
stats = populator.db.get_stats()
print("\nFinal stats:")
for key, value in stats.items():
    print(f"  {key}: {value}")
