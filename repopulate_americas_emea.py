#!/usr/bin/env python3
"""Repopulate Americas and EMEA events only"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scripts.populate_database import DatabasePopulator, VCT_2025_EVENTS
from config import Config

# Filter to only Americas and EMEA events
americas_emea_events = [
    e for e in VCT_2025_EVENTS 
    if e['region'] in ['Americas', 'EMEA']
]

print(f"Repopulating {len(americas_emea_events)} Americas/EMEA events...")
print("Events to process:")
for e in americas_emea_events:
    print(f"  - {e['name']} ({e['region']})")

populator = DatabasePopulator()
populator.populate_all_events(americas_emea_events)

print("\n=== Population Complete ===")
print(f"Events processed: {populator.stats['events_processed']}")
print(f"Matches processed: {populator.stats['matches_processed']}")
print(f"Player stats saved: {populator.stats['player_stats_saved']}")
print(f"Errors: {populator.stats['errors']}")
