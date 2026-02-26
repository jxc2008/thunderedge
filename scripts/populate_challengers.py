#!/usr/bin/env python3
"""
Populate database with Challengers (tier 2 / VCL) event data.
Uses same logic as populate_database.py but for Challengers leagues.
Run: python scripts/populate_challengers.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Reuse DatabasePopulator from populate_database
from scripts.populate_database import DatabasePopulator, VCT_2025_EVENTS

# Challengers 2025 events (completed) - major regional leagues
# URLs from VLR.gg tier=61 (VCL)
CHALLENGERS_2025_EVENTS = [
    # Americas
    {'url': '/event/2467/challengers-2025-north-america-ace-stage-3', 'name': 'Challengers 2025: North America ACE Stage 3', 'region': 'Americas', 'year': 2025},
    {'url': '/event/2396/challengers-2025-north-america-ace-stage-2', 'name': 'Challengers 2025: North America ACE Stage 2', 'region': 'Americas', 'year': 2025},
    {'url': '/event/2301/challengers-2025-north-america-ace-stage-1', 'name': 'Challengers 2025: North America ACE Stage 1', 'region': 'Americas', 'year': 2025},
    {'url': '/event/2454/challengers-2025-brazil-gamers-club-stage-2', 'name': 'Challengers 2025: Brazil Gamers Club Stage 2', 'region': 'Americas', 'year': 2025},
    {'url': '/event/2304/challengers-2025-brazil-gamers-club-stage-1', 'name': 'Challengers 2025: Brazil Gamers Club Stage 1', 'region': 'Americas', 'year': 2025},
    {'url': '/event/2457/challengers-2025-latam-north-ace-stage-2', 'name': 'Challengers 2025: LATAM North ACE Stage 2', 'region': 'Americas', 'year': 2025},
    {'url': '/event/2456/challengers-2025-latam-south-ace-stage-2', 'name': 'Challengers 2025: LATAM South ACE Stage 2', 'region': 'Americas', 'year': 2025},
    # EMEA
    {'url': '/event/2521/challengers-2025-emea-stage-3', 'name': 'Challengers 2025: EMEA Stage 3', 'region': 'EMEA', 'year': 2025},
    {'url': '/event/2523/challengers-2025-dach-evolution-stage-3', 'name': 'Challengers 2025: DACH Evolution Stage 3', 'region': 'EMEA', 'year': 2025},
    {'url': '/event/2542/challengers-2025-france-revolution-stage-3', 'name': 'Challengers 2025: France Revolution Stage 3', 'region': 'EMEA', 'year': 2025},
    {'url': '/event/2581/challengers-2025-spain-rising-finals', 'name': 'Challengers 2025: Spain Rising Finals', 'region': 'EMEA', 'year': 2025},
    {'url': '/event/2540/challengers-2025-north-east-samsung-odyssey-stage-3', 'name': 'Challengers 2025: NORTH//EAST Samsung Odyssey Stage 3', 'region': 'EMEA', 'year': 2025},
    {'url': '/event/2524/challengers-2025-t-rkiye-birlik-stage-3', 'name': 'Challengers 2025: Türkiye Birlik Stage 3', 'region': 'EMEA', 'year': 2025},
    # Pacific
    {'url': '/event/2559/challengers-2025-southeast-asia-stage-3', 'name': 'Challengers 2025: Southeast Asia Stage 3', 'region': 'Pacific', 'year': 2025},
    {'url': '/event/2311/challengers-2025-japan-stage-3', 'name': 'Challengers 2025: Japan Stage 3', 'region': 'Pacific', 'year': 2025},
    {'url': '/event/2547/challengers-2025-korea-wdg-stage-3', 'name': 'Challengers 2025: Korea WDG Stage 3', 'region': 'Pacific', 'year': 2025},
    {'url': '/event/2527/challengers-2025-south-asia-stage-3', 'name': 'Challengers 2025: South Asia Stage 3', 'region': 'Pacific', 'year': 2025},
    {'url': '/event/2497/challengers-2025-oceania-stage-2', 'name': 'Challengers 2025: Oceania Stage 2', 'region': 'Pacific', 'year': 2025},
]


def main():
    populator = DatabasePopulator()
    # Override save_vct_event to pass tier=2 for Challengers
    original_save = populator.db.save_vct_event
    def save_challengers_event(event_url, event_name, region=None, year=None, status='completed', tier=2):
        return original_save(event_url, event_name, region, year, status, tier=2)
    populator.db.save_vct_event = save_challengers_event

    print("=" * 60)
    print("POPULATING CHALLENGERS (TIER 2) EVENTS")
    print("=" * 60)
    populator.populate_all_events(events=CHALLENGERS_2025_EVENTS)
    print("\nChallengers population complete. Run the app and visit /challengers")


if __name__ == '__main__':
    main()
