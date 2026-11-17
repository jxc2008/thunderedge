#!/usr/bin/env python3
"""
Populate moneyline_matches with VCT 2024+ match data (odds + results).
Scrapes Thunderpick pre-match odds and match results from VLR.gg.
Run: python scripts/populate_moneyline.py

Events: Champions Tour 2024 through VCT 2026 (regional + international).
"""

import sys
import os
import re
import time
import logging
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import Database
from scraper.vlr_scraper import VLRScraper
from scripts.populate_database import DatabasePopulator, VCT_2025_EVENTS
from config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# VCT 2024+ events (Champions Tour 2024 start) - regional + international
# URLs from VLR.gg - tier 60 (VCT)
MONEYLINE_EVENTS = [
    # VCT 2024 (Champions Tour 2024)
    {'url': '/event/1923/champions-tour-2024-americas-kickoff', 'name': 'Champions Tour 2024: Americas Kickoff', 'year': 2024},
    {'url': '/event/1924/champions-tour-2024-pacific-kickoff', 'name': 'Champions Tour 2024: Pacific Kickoff', 'year': 2024},
    {'url': '/event/1925/champions-tour-2024-emea-kickoff', 'name': 'Champions Tour 2024: EMEA Kickoff', 'year': 2024},
    {'url': '/event/1926/champions-tour-2024-china-kickoff', 'name': 'Champions Tour 2024: China Kickoff', 'year': 2024},
    {'url': '/event/2095/champions-tour-2024-americas-stage-2', 'name': 'Champions Tour 2024: Americas Stage 2', 'year': 2024},
    {'url': '/event/2094/champions-tour-2024-emea-stage-2', 'name': 'Champions Tour 2024: EMEA Stage 2', 'year': 2024},
    {'url': '/event/2005/champions-tour-2024-pacific-stage-2', 'name': 'Champions Tour 2024: Pacific Stage 2', 'year': 2024},
    {'url': '/event/2096/champions-tour-2024-china-stage-2', 'name': 'Champions Tour 2024: China Stage 2', 'year': 2024},
    {'url': '/event/1921/champions-tour-2024-masters-madrid', 'name': 'Masters Madrid', 'year': 2024},
    {'url': '/event/2097/valorant-champions-2024', 'name': 'Valorant Champions 2024', 'year': 2024},
    # Challengers 2024 (tier 2 - ALL events from VLR.gg/vcl-2024)
    # Americas
    {'url': '/event/1954/challengers-league-2024-north-america-qualifiers', 'name': 'Challengers League 2024 North America: Qualifiers', 'year': 2024},
    {'url': '/event/1971/challengers-league-2024-north-america-stage-1', 'name': 'Challengers League 2024 North America: Stage 1', 'year': 2024},
    {'url': '/event/2071/challengers-league-2024-north-america-stage-2', 'name': 'Challengers League 2024 North America: Stage 2', 'year': 2024},
    {'url': '/event/2150/challengers-league-2024-north-america-stage-3', 'name': 'Challengers League 2024 North America: Stage 3', 'year': 2024},
    {'url': '/event/2135/champions-tour-2024-americas-ascension', 'name': 'Champions Tour 2024 Americas: Ascension', 'year': 2024},
    {'url': '/event/1898/challengers-league-2024-latam-north-ace-split-1', 'name': 'Challengers League 2024 LATAM North ACE: Split 1', 'year': 2024},
    {'url': '/event/2079/challengers-league-2024-latam-north-ace-split-2', 'name': 'Challengers League 2024 LATAM North ACE: Split 2', 'year': 2024},
    {'url': '/event/2220/challengers-league-2024-latam-north-ace-split-3', 'name': 'Challengers League 2024 LATAM North ACE: Split 3', 'year': 2024},
    {'url': '/event/1950/challengers-league-2024-latam-south-ace-split-1', 'name': 'Challengers League 2024 LATAM South ACE: Split 1', 'year': 2024},
    {'url': '/event/2078/challengers-league-2024-latam-south-ace-split-2', 'name': 'Challengers League 2024 LATAM South ACE: Split 2', 'year': 2024},
    {'url': '/event/2221/challengers-league-2024-latam-south-ace-split-3', 'name': 'Challengers League 2024 LATAM South ACE: Split 3', 'year': 2024},
    {'url': '/event/2126/challengers-league-2024-latam-regional-playoffs', 'name': 'Challengers League 2024 LATAM: Regional Playoffs', 'year': 2024},
    {'url': '/event/1949/gamers-club-challengers-league-2024-brazil-split-1', 'name': 'Gamers Club Challengers League 2024 Brazil: Split 1', 'year': 2024},
    {'url': '/event/2089/gamers-club-challengers-league-2024-brazil-split-2', 'name': 'Gamers Club Challengers League 2024 Brazil: Split 2', 'year': 2024},
    {'url': '/event/2200/gamers-club-challengers-league-2024-brazil-split-3', 'name': 'Gamers Club Challengers League 2024 Brazil: Split 3', 'year': 2024},
    # EMEA
    {'url': '/event/2143/champions-tour-2024-emea-ascension', 'name': 'Champions Tour 2024 EMEA: Ascension', 'year': 2024},
    {'url': '/event/1948/challengers-league-2024-dach-evolution-split-1', 'name': 'Challengers League 2024 DACH Evolution: Split 1', 'year': 2024},
    {'url': '/event/2072/challengers-league-2024-dach-evolution-split-2', 'name': 'Challengers League 2024 DACH Evolution: Split 2', 'year': 2024},
    {'url': '/event/1942/challengers-league-2024-france-revolution-split-1', 'name': 'Challengers League 2024 France: Revolution Split 1', 'year': 2024},
    {'url': '/event/2060/challengers-league-2024-france-revolution-split-2', 'name': 'Challengers League 2024 France: Revolution Split 2', 'year': 2024},
    {'url': '/event/1939/challengers-league-2024-spain-rising-split-1', 'name': 'Challengers League 2024 Spain Rising: Split 1', 'year': 2024},
    {'url': '/event/2067/challengers-league-2024-spain-rising-split-2', 'name': 'Challengers League 2024 Spain Rising: Split 2', 'year': 2024},
    {'url': '/event/2194/challengers-2024-spain-rising-consolidation', 'name': 'Challengers 2024 Spain Rising: Consolidation', 'year': 2024},
    {'url': '/event/1947/challengers-league-2024-italy-rinascimento-split-1', 'name': 'Challengers League 2024 Italy Rinascimento: Split 1', 'year': 2024},
    {'url': '/event/2082/challengers-league-2024-italy-rinascimento-split-2', 'name': 'Challengers League 2024 Italy Rinascimento: Split 2', 'year': 2024},
    {'url': '/event/1945/challengers-league-2024-portugal-tempest-split-1', 'name': 'Challengers League 2024 Portugal Tempest: Split 1', 'year': 2024},
    {'url': '/event/2092/challengers-league-2024-portugal-tempest-split-2', 'name': 'Challengers League 2024 Portugal Tempest: Split 2', 'year': 2024},
    {'url': '/event/1893/challengers-league-2024-t-rkiye-birlik-split-1', 'name': 'Challengers League 2024 Türkiye Birlik: Split 1', 'year': 2024},
    {'url': '/event/2085/challengers-league-2024-t-rkiye-birlik-split-2', 'name': 'Challengers League 2024 Türkiye Birlik: Split 2', 'year': 2024},
    {'url': '/event/1932/challengers-league-2024-east-surge-split-1', 'name': 'Challengers League 2024 East Surge: Split 1', 'year': 2024},
    {'url': '/event/2077/challengers-league-2024-east-surge-split-2', 'name': 'Challengers League 2024 East Surge: Split 2', 'year': 2024},
    {'url': '/event/1943/challengers-league-2024-northern-europe-polaris-split-1', 'name': 'Challengers League 2024 Northern Europe: Polaris Split 1', 'year': 2024},
    {'url': '/event/2065/challengers-league-2024-north-polaris-split-2', 'name': 'Challengers League 2024 North: Polaris Split 2', 'year': 2024},
    {'url': '/event/2240/challengers-league-2024-north-polaris-eclipse', 'name': 'Challengers League 2024 North: Polaris ECLIPSE', 'year': 2024},
    {'url': '/event/1944/challengers-league-2024-mena-resilience-split-1', 'name': 'Challengers League 2024 MENA Resilience: Split 1', 'year': 2024},
    {'url': '/event/2062/challengers-league-2024-mena-resilience-split-2', 'name': 'Challengers League 2024 MENA Resilience: Split 2', 'year': 2024},
    {'url': '/event/2161/challengers-league-2024-mena-resilience-split-2-promotion', 'name': 'Challengers League 2024 MENA Resilience: Split 2 Promotion', 'year': 2024},
    {'url': '/event/2144/challengers-league-2024-mena-regional-playoffs', 'name': 'Challengers League 2024 MENA: Regional Playoffs', 'year': 2024},
    # Pacific
    {'url': '/event/2146/champions-tour-2024-pacific-ascension', 'name': 'Champions Tour 2024 Pacific: Ascension', 'year': 2024},
    {'url': '/event/1958/wdg-challengers-league-2024-korea-split-1', 'name': 'WDG Challengers League 2024 Korea: Split 1', 'year': 2024},
    {'url': '/event/2055/wdg-challengers-league-2024-korea-split-2', 'name': 'WDG Challengers League 2024 Korea: Split 2', 'year': 2024},
    {'url': '/event/2168/wdg-challengers-league-2024-korea-split-3', 'name': 'WDG Challengers League 2024 Korea: Split 3', 'year': 2024},
    {'url': '/event/1962/challengers-league-2024-japan-split-1', 'name': 'Challengers League 2024 Japan: Split 1', 'year': 2024},
    {'url': '/event/2049/challengers-league-2024-japan-split-2', 'name': 'Challengers League 2024 Japan: Split 2', 'year': 2024},
    {'url': '/event/2173/challengers-league-2024-japan-split-3', 'name': 'Challengers League 2024 Japan: Split 3', 'year': 2024},
    {'url': '/event/1986/challengers-league-oceania-stage-1', 'name': 'Challengers League Oceania: Stage 1', 'year': 2024},
    {'url': '/event/2059/challengers-league-2024-oceania-stage-2', 'name': 'Challengers League 2024 Oceania: Stage 2', 'year': 2024},
    {'url': '/event/2157/challengers-league-2024-oceania-stage-3', 'name': 'Challengers League 2024 Oceania: Stage 3', 'year': 2024},
    {'url': '/event/1955/challengers-league-2024-taiwan-hong-kong-split-1', 'name': 'Challengers League 2024 Taiwan/Hong Kong: Split 1', 'year': 2024},
    {'url': '/event/2070/challengers-league-2024-taiwan-hong-kong-split-2', 'name': 'Challengers League 2024 Taiwan/Hong Kong: Split 2', 'year': 2024},
    {'url': '/event/1960/afreecatv-challengers-league-2024-thailand-split-1', 'name': 'AfreecaTV Challengers League 2024 Thailand: Split 1', 'year': 2024},
    {'url': '/event/2075/soop-challengers-league-2024-thailand-split-2', 'name': 'SOOP Challengers League 2024 Thailand: Split 2', 'year': 2024},
    {'url': '/event/2076/challengers-league-2024-thailand-ascension-qualifier-series', 'name': 'Challengers League 2024 Thailand: Ascension Qualifier Series', 'year': 2024},
    {'url': '/event/1956/challengers-league-2024-malaysia-singapore-split-1', 'name': 'Challengers League 2024 Malaysia/Singapore: Split 1', 'year': 2024},
    {'url': '/event/2056/challengers-league-2024-malaysia-singapore-split-2', 'name': 'Challengers League 2024 Malaysia/Singapore: Split 2', 'year': 2024},
    {'url': '/event/1964/challengers-league-2024-philippines-split-1', 'name': 'Challengers League 2024 Philippines: Split 1', 'year': 2024},
    {'url': '/event/2083/challengers-league-2024-philippines-split-2', 'name': 'Challengers League 2024 Philippines: Split 2', 'year': 2024},
    {'url': '/event/1974/challengers-league-2024-vietnam-split-1', 'name': 'Challengers League 2024 Vietnam: Split 1', 'year': 2024},
    {'url': '/event/2084/challengers-league-2024-vietnam-split-2', 'name': 'Challengers League 2024 Vietnam: Split 2', 'year': 2024},
    {'url': '/event/1952/challengers-league-2024-indonesia-split-1', 'name': 'Challengers League 2024 Indonesia: Split 1', 'year': 2024},
    {'url': '/event/2069/challengers-league-2024-indonesia-split-2', 'name': 'Challengers League 2024 Indonesia: Split 2', 'year': 2024},
    {'url': '/event/1966/omen-challengers-league-2024-south-asia-split-1', 'name': 'OMEN Challengers League 2024 South Asia: Split 1', 'year': 2024},
    {'url': '/event/2073/challengers-league-2024-south-asia-split-2', 'name': 'Challengers League 2024 South Asia: Split 2', 'year': 2024},
    {'url': '/event/2155/challengers-league-2024-south-asia-split-3', 'name': 'Challengers League 2024 South Asia: Split 3', 'year': 2024},
    {'url': '/event/2223/challengers-league-2024-southeast-asia', 'name': 'Challengers League 2024 Southeast Asia', 'year': 2024},
    # China
    {'url': '/event/2149/champions-tour-2024-china-ascension', 'name': 'Champions Tour 2024 China: Ascension', 'year': 2024},
    {'url': '/event/2131/valorant-china-national-competition-season-2', 'name': 'VALORANT China National Competition: Season 2', 'year': 2024},
    # VCT 2025
    *VCT_2025_EVENTS,
    {'url': '/event/2543/masters-toronto-2025', 'name': 'Masters Toronto 2025', 'year': 2025},
    {'url': '/event/2544/esports-world-cup-2025', 'name': 'Esports World Cup 2025', 'year': 2025},
    {'url': '/event/2545/valorant-champions-2025', 'name': 'Valorant Champions 2025', 'year': 2025},
    # VCT 2026
    {'url': '/event/2682/vct-2026-americas-kickoff', 'name': 'VCT 2026: Americas Kickoff', 'year': 2026},
    {'url': '/event/2683/vct-2026-pacific-kickoff', 'name': 'VCT 2026: Pacific Kickoff', 'year': 2026},
    {'url': '/event/2684/vct-2026-emea-kickoff', 'name': 'VCT 2026: EMEA Kickoff', 'year': 2026},
    {'url': '/event/2685/vct-2026-china-kickoff', 'name': 'VCT 2026: China Kickoff', 'year': 2026},
]


def _normalize_team(name: str) -> str:
    """Normalize team name for matching (e.g. '100 Thieves' vs '100t')"""
    if not name:
        return ''
    n = name.strip().lower()
    # Common aliases
    aliases = {'100t': '100 thieves', '100 thieves': '100 thieves', 'c9': 'cloud9', 'cloud9': 'cloud9',
               'nrg': 'nrg', 'g2': 'g2 esports', 'g2 esports': 'g2 esports', 'mibr': 'mibr'}
    return aliases.get(n, n)


def _team_matches(a: str, b: str) -> bool:
    """Exact (alias-normalized) team-name match.

    The old substring rule matched "furia" inside the contaminated
    "furia champions tour 2024 amer" and "g2" inside unrelated names.
    """
    return bool(a and b) and _normalize_team(a) == _normalize_team(b)


# Overround assumed when only one side's price is observed (VLR post-match pages show only
# the winner's price). Rows imputed this way are FLAGGED (team{1,2}_odds_imputed) and must be
# excluded from, or sensitivity-tested in, any calibration analysis. Wayback pre-match
# snapshots show the real Thunderpick overround differs (see research/REPORT.md).
IMPUTE_OVERROUND = 1.05


def _is_international(event_name: str) -> bool:
    """True if event is International (Masters, Champions, EWC)."""
    n = (event_name or '').lower()
    if 'masters madrid' in n or 'masters toronto' in n:
        return True
    if 'valorant champions' in n and 'ascension' not in n:
        return True
    if 'esports world cup' in n or 'ewc' in n:
        return True
    return False


def _is_challengers(event_name: str) -> bool:
    """True if event is Challengers (tier 2)."""
    n = (event_name or '').lower()
    return 'challengers' in n or 'ascension' in n or 'national competition' in n


def main():
    parser = argparse.ArgumentParser(description='Populate moneyline_matches from VLR.gg')
    parser.add_argument('--skip-international', action='store_true',
                        help='Skip International events (Masters, Champions, EWC)')
    parser.add_argument('--challengers-only', action='store_true',
                        help='ONLY populate Challengers events - skip Tier 1 (regional VCT)')
    args = parser.parse_args()

    events = MONEYLINE_EVENTS
    if args.challengers_only:
        events = [e for e in MONEYLINE_EVENTS if _is_challengers(e['name'])]
        logger.info(f"Challengers only - processing {len(events)} Challengers events")
    elif args.skip_international:
        events = [e for e in MONEYLINE_EVENTS if not _is_international(e['name'])]
        logger.info(f"Skipping International - processing {len(events)} events")
    else:
        logger.info(f"Processing all {len(events)} events")

    db = Database(Config.DATABASE_PATH)
    scraper = VLRScraper()
    populator = DatabasePopulator()
    
    stats = {'events': 0, 'matches': 0, 'with_odds': 0, 'with_result': 0, 'saved': 0, 'errors': 0}
    
    logger.info("=" * 60)
    logger.info("MONEYLINE POPULATION - VCT 2024+ matches with Thunderpick odds")
    logger.info("=" * 60)
    
    for event in events:
        event_url = event['url']
        event_name = event['name']
        logger.info(f"\nProcessing: {event_name}")
        
        try:
            matches = populator.get_event_matches(event_url)
            if not matches:
                logger.warning(f"  No matches found for {event_name}")
                continue
            stats['events'] += 1
            
            for m in matches:
                match_url = m['url']
                team1, team2 = m['team1'], m['team2']
                stats['matches'] += 1
                
                try:
                    result = scraper.get_match_result(match_url, team1, team2)
                    odds_data = scraper.get_match_betting_odds(match_url)
                    
                    winner = None
                    t1_maps, t2_maps = 0, 0
                    if result:
                        winner = result['winner']
                        t1_maps, t2_maps = result['team1_maps'], result['team2_maps']
                        stats['with_result'] += 1
                    
                    team1_odds, team2_odds = None, None
                    team1_imputed = team2_imputed = 0
                    if odds_data and odds_data.get('teams'):
                        for t in odds_data['teams']:
                            if _team_matches(t['name'], team1):
                                team1_odds = t['decimal_odds']
                            elif _team_matches(t['name'], team2):
                                team2_odds = t['decimal_odds']
                        if team1_odds or team2_odds:
                            stats['with_odds'] += 1
                        if team1_odds and not team2_odds:
                            team2_odds = round(1.0 / (IMPUTE_OVERROUND - 1.0 / team1_odds), 2)
                            team2_imputed = 1
                        elif team2_odds and not team1_odds:
                            team1_odds = round(1.0 / (IMPUTE_OVERROUND - 1.0 / team2_odds), 2)
                            team1_imputed = 1

                    # VLR bug: 1.00 odds are invalid (implied 100% - never real pre-match). Skip.
                    if (team1_odds is not None and abs(team1_odds - 1.0) < 0.01) or \
                       (team2_odds is not None and abs(team2_odds - 1.0) < 0.01):
                        logger.debug(f"  Skipping {team1} vs {team2}: invalid 1.00 odds (VLR bug)")
                        continue
                    
                    db.save_moneyline_match(
                        match_url=match_url,
                        event_name=event_name,
                        event_url=event_url,
                        team1=team1,
                        team2=team2,
                        team1_odds=team1_odds,
                        team2_odds=team2_odds,
                        winner=winner,
                        team1_maps=t1_maps,
                        team2_maps=t2_maps,
                        team1_odds_imputed=team1_imputed,
                        team2_odds_imputed=team2_imputed,
                        imputed_overround=IMPUTE_OVERROUND if (team1_imputed or team2_imputed) else None,
                    )
                    stats['saved'] += 1
                    if odds_data or result:
                        logger.info(f"  {team1} vs {team2}: odds {team1_odds}/{team2_odds}, winner={winner}")
                    
                except Exception as e:
                    logger.warning(f"  Error processing {match_url}: {e}")
                    stats['errors'] += 1
                
                time.sleep(0.5)
            
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error processing event {event_name}: {e}")
            stats['errors'] += 1
    
    logger.info("\n" + "=" * 60)
    logger.info("MONEYLINE POPULATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Events: {stats['events']}, Matches: {stats['matches']}")
    logger.info(f"With odds: {stats['with_odds']}, With result: {stats['with_result']}")
    logger.info(f"Saved: {stats['saved']}, Errors: {stats['errors']}")
    
    stats_data = db.get_moneyline_stats()
    if stats_data.get('total_matches'):
        logger.info("\n--- Strategy Stats ---")
        for k in ['heavy_favorite', 'moderate_favorite', 'even_matchup']:
            v = stats_data.get(k, {})
            logger.info(f"  {k}: {v.get('wins', 0)}/{v.get('total', 0)} = {v.get('win_rate_pct', 0)}%")


if __name__ == '__main__':
    main()
