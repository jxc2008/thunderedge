#!/usr/bin/env python
"""Test script to debug team scraper"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper.team_scraper import TeamScraper
from backend.database import Database
from config import Config
import logging

# Set up logging to see all output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

db = Database(Config.DATABASE_PATH)
ts = TeamScraper(database=db)

print("=" * 80)
print("Testing team scraper for Sentinels")
print("=" * 80)

result = ts.get_team_events_data('Sentinels', region='Americas')

print(f"\nResult keys: {result.keys()}")
print(f"Events found: {len(result.get('events', []))}")

if result.get('events'):
    for i, event in enumerate(result.get('events', [])):
        print(f"\nEvent {i+1}: {event.get('event_name')}")
        print(f"  Fights per round: {event.get('fights_per_round')}")
        print(f"  Total kills: {event.get('total_kills')}")
        print(f"  Total deaths: {event.get('total_deaths')}")
        print(f"  Total rounds: {event.get('total_rounds')}")
        print(f"  Matches played: {event.get('matches_played')}")
        print(f"  Pick/bans: {event.get('pick_bans')}")
else:
    print("\nNo events found!")
    if 'error' in result:
        print(f"Error: {result['error']}")
