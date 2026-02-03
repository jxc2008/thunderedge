# scraper/player_processor.py
from typing import Dict, List
import statistics
import re
from datetime import datetime

class PlayerProcessor:
    def __init__(self, kill_line: float = 15.5):
        """
        Initialize processor with kill line from sportsbook.
        
        Args:
            kill_line: The over/under kill line from the sportsbook (e.g., 15.5 kills)
        """
        self.kill_line = kill_line
        
    def _is_most_recent_event(self, event_name: str) -> bool:
        """
        Check if an event is the most recent (2026 Kickoff).
        This identifies the event that should get 1.5x weight.
        """
        if not event_name:
            return False
        # Check for 2026 Kickoff pattern
        return '2026' in event_name and 'kickoff' in event_name.lower()
    
    def calculate_weighted_kpr(self, events: List[Dict]) -> Dict:
        """
        Calculate both total KPR (weighted by rounds) and weighted KPR (1.5x for most recent event).
        
        Total KPR Formula: (KPR1 * rounds1 + KPR2 * rounds2) / (rounds1 + rounds2)
        Weighted KPR Formula: (KPR1 * rounds1 * weight1 + KPR2 * rounds2 * weight2) / (rounds1 * weight1 + rounds2 * weight2)
        where most recent event gets 1.5x weight
        """
        if not events:
            return {}
        
        valid_events = [e for e in events if e.get('kpr', 0) > 0 and e.get('rounds_played', 0) > 0]
        
        if not valid_events:
            return {}
        
        # Calculate Total KPR (weighted by rounds, no special weighting)
        total_weighted_kpr = sum(e['kpr'] * e['rounds_played'] for e in valid_events)
        total_rounds = sum(e['rounds_played'] for e in valid_events)
        total_kpr = total_weighted_kpr / total_rounds if total_rounds > 0 else 0
        
        # Calculate Weighted KPR (1.5x weight for most recent event)
        # Find the most recent event (2026 Kickoff)
        weighted_numerator = 0
        weighted_denominator = 0
        
        for e in valid_events:
            event_name = e.get('event_name', '')
            is_recent = self._is_most_recent_event(event_name)
            weight = 1.5 if is_recent else 1.0
            
            weighted_numerator += e['kpr'] * e['rounds_played'] * weight
            weighted_denominator += e['rounds_played'] * weight
        
        weighted_kpr = weighted_numerator / weighted_denominator if weighted_denominator > 0 else 0
        
        event_kprs = [e['kpr'] for e in valid_events]
        
        return {
            'total_kpr': total_kpr,  # Renamed from weighted_kpr
            'weighted_kpr': weighted_kpr,  # New: 1.5x weight for most recent event
            'total_rounds': total_rounds,
            'events_used': len(valid_events),
            'individual_kprs': event_kprs,
            'min_kpr': min(event_kprs),
            'max_kpr': max(event_kprs),
            'event_details': [
                {
                    'event_name': self._clean_event_name(e.get('event_name', 'Unknown')),
                    'kpr': e['kpr'],
                    'rounds': e['rounds_played'],
                    'rating': e.get('rating', 0),
                    'acs': e.get('acs', 0),
                    'map_kills': e.get('map_kills', []),
                    'event_over': e.get('event_over', 0),
                    'event_under': e.get('event_under', 0),
                    'event_maps': e.get('event_maps', 0),
                    'cached': e.get('cached', False),
                    'is_recent': self._is_most_recent_event(e.get('event_name', ''))
                }
                for e in valid_events
            ]
        }
    
    def _clean_event_name(self, event_name: str) -> str:
        """Clean up event name by removing extra formatting"""
        cleaned = re.sub(r'\s+', ' ', event_name)
        
        vct_match = re.search(r'(VCT\s*\d{4}[:\s]+[A-Za-z]+\s+(?:Stage\s+\d|Kickoff))', cleaned, re.IGNORECASE)
        if vct_match:
            return vct_match.group(1).strip()
        
        ct_match = re.search(r'(Champions\s+Tour\s*\d{4}[:\s]+[A-Za-z]+\s+(?:Stage\s+\d|Kickoff|League))', cleaned, re.IGNORECASE)
        if ct_match:
            return ct_match.group(1).strip()
        
        cleaned = re.sub(r'(Stage\s+\d|Kickoff).*$', r'\1', cleaned)
        return cleaned.strip()[:50]
    
    def calculate_rounds_needed(self, kpr: float) -> float:
        """
        Calculate the expected number of rounds needed to reach the kill line.
        
        Formula: Rounds Needed = Kill Line / KPR
        """
        if kpr <= 0:
            return float('inf')
        return self.kill_line / kpr
    
    def classify_line(self, rounds_needed: float) -> tuple:
        """
        Classify the betting line based on rounds needed.
        
        Classification thresholds:
        - < 19 rounds: Severely underpriced (easy to hit over)
        - 19-20 rounds: Moderately underpriced
        - 20-20.5 rounds: Slightly underpriced
        - 20.5-23.5 rounds: Well priced (fair value)
        - 23.5-24 rounds: Slightly overpriced
        - 24-25 rounds: Moderately overpriced
        - 25+ rounds: Severely overpriced (hard to hit over)
        """
        if rounds_needed < 19:
            return ("SEVERELY UNDERPRICED", "STRONG OVER")
        elif rounds_needed < 20:
            return ("MODERATELY UNDERPRICED", "OVER")
        elif rounds_needed < 20.5:
            return ("SLIGHTLY UNDERPRICED", "LEAN OVER")
        elif rounds_needed < 23.5:
            return ("WELL PRICED", "NO EDGE")
        elif rounds_needed < 24:
            return ("SLIGHTLY OVERPRICED", "LEAN UNDER")
        elif rounds_needed < 25:
            return ("MODERATELY OVERPRICED", "UNDER")
        else:
            return ("SEVERELY OVERPRICED", "STRONG UNDER")
    
    def evaluate_betting_line(self, player_data: Dict) -> Dict:
        """
        Evaluate betting line vs player's KPR and historical over/under.
        
        Uses weighted KPR from the player's VCT events plus actual map-by-map
        kill data to calculate historical over/under percentage.
        """
        events = player_data.get('events', [])
        kpr_data = self.calculate_weighted_kpr(events)
        
        if not kpr_data:
            return {'error': 'Insufficient data - no valid KPR values found from VCT events'}
        
        total_kpr = kpr_data['total_kpr']
        weighted_kpr = kpr_data['weighted_kpr']
        
        # Calculate rounds needed using weighted KPR (the new 1.5x weighted version)
        rounds_needed = self.calculate_rounds_needed(weighted_kpr)
        
        # Classification based on rounds needed
        classification, recommendation = self.classify_line(rounds_needed)
        
        # Get over/under stats from player_data (calculated from map kills)
        all_map_kills = player_data.get('all_map_kills', [])
        over_count = player_data.get('over_count', 0)
        under_count = player_data.get('under_count', 0)
        total_maps = player_data.get('total_maps', 0)
        over_percentage = player_data.get('over_percentage', 0)
        under_percentage = player_data.get('under_percentage', 0)
        
        # Determine confidence based on over/under percentage
        if over_percentage >= 70:
            confidence = "HIGH (Strong Over)"
        elif over_percentage >= 55:
            confidence = "MEDIUM (Lean Over)"
        elif over_percentage >= 45:
            confidence = "LOW (Coin Flip)"
        elif over_percentage >= 30:
            confidence = "MEDIUM (Lean Under)"
        else:
            confidence = "HIGH (Strong Under)"
        
        return {
            'player_ign': player_data.get('ign'),
            'team': player_data.get('team', 'Unknown'),
            'kill_line': self.kill_line,
            'total_kpr': round(total_kpr, 3),  # Total KPR (weighted by rounds)
            'weighted_kpr': round(weighted_kpr, 3),  # Weighted KPR (1.5x for most recent event)
            'total_rounds': kpr_data['total_rounds'],
            'rounds_needed': round(rounds_needed, 2),
            'classification': classification,
            'recommendation': recommendation,
            'confidence': confidence,
            'events_analyzed': kpr_data['events_used'],
            'event_details': kpr_data['event_details'],
            'kpr_range': round(kpr_data['max_kpr'] - kpr_data['min_kpr'], 3),
            # New over/under stats
            'all_map_kills': all_map_kills,
            'over_count': over_count,
            'under_count': under_count,
            'total_maps': total_maps,
            'over_percentage': over_percentage,
            'under_percentage': under_percentage
        }
