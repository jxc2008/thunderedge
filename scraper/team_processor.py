# scraper/team_processor.py
from typing import Dict, List
import logging
import re

logger = logging.getLogger(__name__)

class TeamProcessor:
    def __init__(self):
        """Initialize team processor"""
        pass
    
    def process_team_data(self, team_data: Dict) -> Dict:
        """
        Process raw team data and calculate statistics.
        
        Returns formatted data with:
        - Fights per round per event
        - Pick/ban rates per event
        """
        if 'error' in team_data:
            return team_data
        
        processed_events = []
        
        for event in team_data.get('events', []):
            matches_played = event.get('matches_played', 0)
            if matches_played == 0 and 'matches' in event:
                matches_played = len(event['matches'])
            
            processed_event = {
                'event_name': event['event_name'],
                'event_url': event['event_url'],
                'region': event['region'],
                'roster': event['roster'],
                'fights_per_round': round(event.get('fights_per_round', 0), 3),
                'total_kills': event.get('total_kills', 0),
                'total_deaths': event.get('total_deaths', 0),
                'total_rounds': event.get('total_rounds', 0),
                'matches_played': matches_played,
                'pick_ban_rates': self._calculate_pick_ban_rates(event.get('pick_bans', {}), matches_played),
                'cached': event.get('cached', False)
            }
            
            processed_events.append(processed_event)
        
        return {
            'team_name': team_data['team_name'],
            'team_url': team_data['team_url'],
            'roster': team_data['roster'],
            'events': processed_events
        }
    
    def _clean_map_name(self, map_name: str) -> str:
        """Clean map name by removing timestamps and extra text"""
        if not map_name:
            return ""
        
        # Remove timestamps (e.g., "51:04", "1:02:13")
        cleaned = re.sub(r'\d+:\d+(:\d+)?', '', map_name)
        # Remove PICK/BAN keywords
        cleaned = re.sub(r'PICK|BAN', '', cleaned, flags=re.IGNORECASE)
        # Remove extra whitespace
        cleaned = cleaned.strip()
        
        # Validate against known Valorant maps
        valorant_maps = ['Bind', 'Haven', 'Split', 'Ascent', 'Icebox', 'Breeze', 'Fracture', 
                        'Pearl', 'Lotus', 'Sunset', 'Abyss', 'Corrode']
        
        # Try to match cleaned name to a valid map
        for valid_map in valorant_maps:
            if valid_map.lower() in cleaned.lower() or cleaned.lower() in valid_map.lower():
                return valid_map
        
        # If no match, return cleaned (capitalize first letter)
        if cleaned:
            return cleaned.capitalize()
        
        return map_name
    
    def _calculate_pick_ban_rates(self, pick_bans: Dict, total_matches: int) -> Dict:
        """
        Calculate pick/ban rates as percentages.
        
        Returns:
        {
            'first_ban': {map_name: percentage},
            'second_ban': {map_name: percentage},
            'first_pick': {map_name: percentage},
            'second_pick': {map_name: percentage}
        }
        """
        if total_matches == 0:
            return {
                'first_ban': {},
                'second_ban': {},
                'first_pick': {},
                'second_pick': {}
            }
        
        rates = {
            'first_ban': {},
            'second_ban': {},
            'first_pick': {},
            'second_pick': {}
        }
        
        for action_type in ['first_ban', 'second_ban', 'first_pick', 'second_pick']:
            action_counts = pick_bans.get(action_type, {})
            # Clean map names and aggregate counts
            cleaned_counts = {}
            for map_name, count in action_counts.items():
                cleaned_name = self._clean_map_name(map_name)
                if cleaned_name:
                    cleaned_counts[cleaned_name] = cleaned_counts.get(cleaned_name, 0) + count
            
            # Calculate percentages
            for map_name, count in cleaned_counts.items():
                rates[action_type][map_name] = round((count / total_matches) * 100, 2)
        
        return rates
