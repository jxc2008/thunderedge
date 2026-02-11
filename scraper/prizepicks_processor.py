# scraper/prizepicks_processor.py
from typing import Dict, List, Tuple
import itertools
from scraper.player_processor import PlayerProcessor

class PrizePicksProcessor(PlayerProcessor):
    """
    Processor for PrizePicks lines that combine kills from maps 1 AND 2.
    For 2-map matches: combines kills from both maps
    For 3-map matches: shows all combinations of 2 maps (3 choose 2 = 3 combinations)
    """
    
    def __init__(self, kill_line: float = 30.5):
        """
        Initialize processor with PrizePicks kill line.
        
        Args:
            kill_line: The combined kill line for maps 1 AND 2 (e.g., 30.5 kills)
        """
        super().__init__(kill_line=kill_line)
    
    def _determine_match_outcome(self, map_scores: List[str]) -> Tuple[bool, int]:
        """
        Determine if the match was won and the match margin (2-0 or 2-1).
        
        Returns:
            (is_win, match_score_margin) where margin is 0, 1, or 2 map differential
        """
        if not map_scores or len(map_scores) < 2:
            return None, None
        
        wins = 0
        losses = 0
        
        for score in map_scores:
            is_win, _ = self._parse_map_score(score)
            if is_win is None:
                continue
            if is_win:
                wins += 1
            else:
                losses += 1
        
        # Determine overall match outcome
        if wins + losses == 0:
            return None, None
        
        is_match_win = wins > losses
        margin = abs(wins - losses)
        
        return is_match_win, margin
    
    def _calculate_prizepicks_margin_stats(self, match_combinations: List[Dict], kill_line: float) -> Dict:
        """
        Calculate win/loss margin statistics for PrizePicks matches.
        For matches: 2-0 = blowout, 2-1 = close
        """
        stats = {
            'wins': {'close': {'over': 0, 'under': 0}, 'blowout': {'over': 0, 'under': 0}},
            'losses': {'close': {'over': 0, 'under': 0}, 'blowout': {'over': 0, 'under': 0}},
            'total_wins': 0,
            'total_losses': 0,
            'total_matches': 0
        }
        
        for match_data in match_combinations:
            map_scores = match_data.get('map_scores', [])
            map_kills = match_data.get('map_kills', [])
            
            if len(map_kills) < 2:
                continue
            
            # Determine match outcome
            is_match_win, match_margin = self._determine_match_outcome(map_scores)
            
            if is_match_win is None or match_margin is None:
                continue
            
            # Classify margin: 2-0 = blowout, 2-1 = close
            if match_margin >= 2:
                margin_type = 'blowout'  # 2-0 or 3-0
            else:
                margin_type = 'close'  # 2-1 or 3-1
            
            # For PrizePicks, we analyze the first 2 maps combination
            # (most common scenario for 2-map matches)
            if len(map_kills) >= 2:
                combined_kills = map_kills[0] + map_kills[1]
                is_over = combined_kills > kill_line
                result_key = 'over' if is_over else 'under'
                
                stats['total_matches'] += 1
                
                if is_match_win:
                    stats['total_wins'] += 1
                    stats['wins'][margin_type][result_key] += 1
                else:
                    stats['total_losses'] += 1
                    stats['losses'][margin_type][result_key] += 1
        
        # Calculate percentages
        result = {
            'wins': {},
            'losses': {},
            'total_wins': stats['total_wins'],
            'total_losses': stats['total_losses'],
            'total_matches': stats['total_matches']
        }
        
        # Calculate win percentages
        if stats['total_wins'] > 0:
            result['wins_over_pct'] = round(100 * sum(stats['wins'][m]['over'] for m in ['close', 'blowout']) / stats['total_wins'], 1)
            result['wins_under_pct'] = round(100 * sum(stats['wins'][m]['under'] for m in ['close', 'blowout']) / stats['total_wins'], 1)
        else:
            result['wins_over_pct'] = 0
            result['wins_under_pct'] = 0
        
        # Calculate loss percentages
        if stats['total_losses'] > 0:
            result['losses_over_pct'] = round(100 * sum(stats['losses'][m]['over'] for m in ['close', 'blowout']) / stats['total_losses'], 1)
            result['losses_under_pct'] = round(100 * sum(stats['losses'][m]['under'] for m in ['close', 'blowout']) / stats['total_losses'], 1)
        else:
            result['losses_over_pct'] = 0
            result['losses_under_pct'] = 0
        
        # Calculate margin breakdowns for wins
        for margin_type in ['close', 'blowout']:
            total = stats['wins'][margin_type]['over'] + stats['wins'][margin_type]['under']
            if total > 0:
                result['wins'][margin_type] = {
                    'over': stats['wins'][margin_type]['over'],
                    'under': stats['wins'][margin_type]['under'],
                    'total': total,
                    'over_pct': round(100 * stats['wins'][margin_type]['over'] / total, 1),
                    'under_pct': round(100 * stats['wins'][margin_type]['under'] / total, 1)
                }
            else:
                result['wins'][margin_type] = {
                    'over': 0,
                    'under': 0,
                    'total': 0,
                    'over_pct': 0,
                    'under_pct': 0
                }
        
        # Calculate margin breakdowns for losses
        for margin_type in ['close', 'blowout']:
            total = stats['losses'][margin_type]['over'] + stats['losses'][margin_type]['under']
            if total > 0:
                result['losses'][margin_type] = {
                    'over': stats['losses'][margin_type]['over'],
                    'under': stats['losses'][margin_type]['under'],
                    'total': total,
                    'over_pct': round(100 * stats['losses'][margin_type]['over'] / total, 1),
                    'under_pct': round(100 * stats['losses'][margin_type]['under'] / total, 1)
                }
            else:
                result['losses'][margin_type] = {
                    'over': 0,
                    'under': 0,
                    'total': 0,
                    'over_pct': 0,
                    'under_pct': 0
                }
        
        return result
    
    def classify_line(self, rounds_needed: float) -> tuple:
        """
        Classify the betting line based on rounds needed for 2-map combinations.
        
        Classification thresholds (doubled for 2 maps):
        - < 38 rounds: Severely underpriced (easy to hit over)
        - 38-40 rounds: Moderately underpriced
        - 40-41 rounds: Slightly underpriced
        - 41-47 rounds: Well priced (fair value)
        - 47-48 rounds: Slightly overpriced
        - 48-50 rounds: Moderately overpriced
        - > 50 rounds: Severely overpriced
        
        Args:
            rounds_needed: Expected rounds needed to hit the kill line
            
        Returns:
            Tuple of (classification, recommendation)
        """
        if rounds_needed < 38:
            return ("SEVERELY UNDERPRICED", "STRONG OVER")
        elif rounds_needed < 40:
            return ("MODERATELY UNDERPRICED", "OVER")
        elif rounds_needed < 41:
            return ("SLIGHTLY UNDERPRICED", "LEAN OVER")
        elif rounds_needed < 47:
            return ("WELL PRICED", "NO EDGE")
        elif rounds_needed < 48:
            return ("SLIGHTLY OVERPRICED", "LEAN UNDER")
        elif rounds_needed < 50:
            return ("MODERATELY OVERPRICED", "UNDER")
        else:
            return ("SEVERELY OVERPRICED", "STRONG UNDER")
    
    def process_match_combinations(self, match_map_kills: List[int]) -> List[Dict]:
        """
        Process a match's map kills into combinations.
        
        Args:
            match_map_kills: List of kills per map in order [map1_kills, map2_kills, ...]
            
        Returns:
            List of combination results:
            - For 2 maps: [{'maps': [1, 2], 'combined_kills': total, 'hit': bool}]
            - For 3 maps: [{'maps': [1, 2], ...}, {'maps': [1, 3], ...}, {'maps': [2, 3], ...}]
        """
        num_maps = len(match_map_kills)
        
        if num_maps < 2:
            return []  # Need at least 2 maps for PrizePicks
        
        combinations = []
        
        if num_maps == 2:
            # Simple case: combine maps 1 and 2
            combined_kills = match_map_kills[0] + match_map_kills[1]
            combinations.append({
                'maps': [1, 2],
                'combined_kills': combined_kills,
                'hit': combined_kills > self.kill_line,
                'map1_kills': match_map_kills[0],
                'map2_kills': match_map_kills[1]
            })
        elif num_maps >= 3:
            # 3 choose 2: all combinations of 2 maps
            # Combinations: (1,2), (1,3), (2,3)
            for i, j in itertools.combinations(range(num_maps), 2):
                map1_idx = i + 1  # 1-indexed for display
                map2_idx = j + 1
                combined_kills = match_map_kills[i] + match_map_kills[j]
                combinations.append({
                    'maps': [map1_idx, map2_idx],
                    'combined_kills': combined_kills,
                    'hit': combined_kills > self.kill_line,
                    'map1_kills': match_map_kills[i],
                    'map2_kills': match_map_kills[j]
                })
        
        return combinations
    
    def evaluate_prizepicks_line(self, player_data: Dict) -> Dict:
        """
        Evaluate PrizePicks line vs player's historical performance.
        
        Args:
            player_data: Player data with match-level map kills structure
            
        Returns:
            Analysis dictionary with PrizePicks-specific metrics
        """
        # Get events for KPR calculation
        events = player_data.get('events', [])
        kpr_data = self.calculate_weighted_kpr(events)
        
        if not kpr_data:
            return {'error': 'Insufficient data - no valid KPR values found from VCT events'}
        
        total_kpr = kpr_data['total_kpr']
        weighted_kpr = kpr_data['weighted_kpr']
        
        # Calculate rounds needed using weighted KPR
        rounds_needed = self.calculate_rounds_needed(weighted_kpr)
        
        # Classification based on rounds needed
        classification, recommendation = self.classify_line(rounds_needed)
        
        # Process match combinations and group by event
        match_combinations = player_data.get('match_combinations', [])
        events_data = player_data.get('events', [])
        
        # Calculate hit/miss statistics
        total_combinations = 0
        hit_count = 0
        miss_count = 0
        
        # Group matches by event name
        matches_by_event = {}
        
        for match_data in match_combinations:
            match_num_maps = match_data.get('num_maps', 0)
            match_map_kills = match_data.get('map_kills', [])
            event_name = match_data.get('event_name', 'Unknown Event')
            
            if match_num_maps < 2:
                continue
            
            combinations = self.process_match_combinations(match_map_kills)
            
            match_hits = sum(1 for c in combinations if c['hit'])
            match_misses = sum(1 for c in combinations if not c['hit'])
            
            total_combinations += len(combinations)
            hit_count += match_hits
            miss_count += match_misses
            
            # Add to event group
            if event_name not in matches_by_event:
                matches_by_event[event_name] = []
            
            matches_by_event[event_name].append({
                'match_url': match_data.get('match_url', ''),
                'event_name': event_name,
                'num_maps': match_num_maps,
                'map_kills': match_map_kills,
                'map_scores': match_data.get('map_scores', []),
                'map_names': match_data.get('map_names', []),
                'agents': match_data.get('agents', []),
                'combinations': combinations,
                'hits': match_hits,
                'misses': match_misses,
                'total_combinations': len(combinations)
            })
        
        # Create event sections in reverse chronological order
        # Event order: 2026 Kickoff, 2025 Stage 2, 2025 Stage 1, 2025 Kickoff
        event_priority = {
            '2026': 4,
            '2025 Stage 2': 3,
            '2025 Stage 1': 2,
            '2025 Kickoff': 1
        }
        
        def get_event_priority(event_name):
            if '2026' in event_name:
                return 4
            elif 'Stage 2' in event_name and '2025' in event_name:
                return 3
            elif 'Stage 1' in event_name and '2025' in event_name:
                return 2
            elif 'Kickoff' in event_name and '2025' in event_name:
                return 1
            else:
                return 0
        
        # Create event sections
        event_sections = []
        for event_name, matches in matches_by_event.items():
            event_sections.append({
                'event_name': event_name,
                'matches': matches,
                'total_matches': len(matches),
                'priority': get_event_priority(event_name)
            })
        
        # Sort by priority (highest first = most recent)
        event_sections.sort(key=lambda x: x['priority'], reverse=True)
        
        # Flatten back to match_results for backward compatibility
        match_results = []
        for section in event_sections:
            match_results.extend(section['matches'])
        
        # Calculate percentages
        hit_percentage = (hit_count / total_combinations * 100) if total_combinations > 0 else 0
        miss_percentage = (miss_count / total_combinations * 100) if total_combinations > 0 else 0
        
        # Determine confidence
        if hit_percentage >= 70:
            confidence = "HIGH (Strong Hit)"
        elif hit_percentage >= 55:
            confidence = "MEDIUM (Lean Hit)"
        elif hit_percentage >= 45:
            confidence = "LOW (Coin Flip)"
        elif hit_percentage >= 30:
            confidence = "MEDIUM (Lean Miss)"
        else:
            confidence = "HIGH (Strong Miss)"
        
        # Calculate agent and map hit rates
        agent_analysis = self._calculate_agent_hit_rates(match_results, self.kill_line)
        map_analysis = self._calculate_map_hit_rates(match_results, self.kill_line)
        
        # Calculate win/loss margin statistics
        margin_stats = self._calculate_prizepicks_margin_stats(match_combinations, self.kill_line)
        
        return {
            'player_ign': player_data.get('ign'),
            'team': player_data.get('team', 'Unknown'),
            'kill_line': self.kill_line,
            'total_kpr': round(total_kpr, 3),
            'weighted_kpr': round(weighted_kpr, 3),
            'total_rounds': kpr_data['total_rounds'],
            'rounds_needed': round(rounds_needed, 2),
            'classification': classification,
            'recommendation': recommendation,
            'confidence': confidence,
            'events_analyzed': kpr_data['events_used'],
            'match_results': match_results,
            'event_sections': event_sections,  # Add grouped view
            'agent_analysis': agent_analysis,  # Agent-specific hit rates
            'map_analysis': map_analysis,       # Map-specific hit rates
            'margin_stats': margin_stats,       # Win/loss margin statistics
            'total_combinations': total_combinations,
            'hit_count': hit_count,
            'miss_count': miss_count,
            'hit_percentage': round(hit_percentage, 1),
            'miss_percentage': round(miss_percentage, 1)
        }
    
    def _calculate_agent_hit_rates(self, match_results: List[Dict], kill_line: float) -> List[Dict]:
        """Calculate hit rates broken down by agent combinations"""
        agent_stats = {}
        
        for match in match_results:
            agents = match.get('agents', [])
            map_kills = match.get('map_kills', [])
            
            # For 2-map combinations
            if len(map_kills) >= 2 and len(agents) >= 2:
                # Combination of first two maps
                combined_kills = map_kills[0] + map_kills[1]
                hit = combined_kills > kill_line
                
                # Track agent pair (sorted so "Jett + Raze" is same as "Raze + Jett")
                agent_pair = tuple(sorted([agents[0], agents[1]]))
                if agent_pair not in agent_stats:
                    agent_stats[agent_pair] = {
                        'agents': list(agent_pair),
                        'combinations': 0,
                        'hits': 0,
                        'total_kills': 0
                    }
                
                agent_stats[agent_pair]['combinations'] += 1
                agent_stats[agent_pair]['total_kills'] += combined_kills
                if hit:
                    agent_stats[agent_pair]['hits'] += 1
        
        # Convert to list and calculate rates
        agent_analysis = []
        for agent_pair, stats in agent_stats.items():
            agent_analysis.append({
                'agent_combo': ' + '.join(stats['agents']),
                'agents': stats['agents'],
                'combinations': stats['combinations'],
                'hits': stats['hits'],
                'hit_rate': round((stats['hits'] / stats['combinations'] * 100), 1) if stats['combinations'] > 0 else 0,
                'avg_kills': round(stats['total_kills'] / stats['combinations'], 1) if stats['combinations'] > 0 else 0
            })
        
        # Sort by combinations (most common first)
        agent_analysis.sort(key=lambda x: x['combinations'], reverse=True)
        return agent_analysis
    
    def _calculate_map_hit_rates(self, match_results: List[Dict], kill_line: float) -> List[Dict]:
        """Calculate hit rates broken down by map combinations"""
        map_stats = {}
        
        for match in match_results:
            map_names = match.get('map_names', [])
            map_kills = match.get('map_kills', [])
            
            # For 2-map combinations
            if len(map_kills) >= 2 and len(map_names) >= 2:
                # Combination of first two maps
                combined_kills = map_kills[0] + map_kills[1]
                hit = combined_kills > kill_line
                
                # Track map pair (sorted so "Bind + Haven" is same as "Haven + Bind")
                map_pair = tuple(sorted([map_names[0], map_names[1]]))
                if map_pair not in map_stats:
                    map_stats[map_pair] = {
                        'maps': list(map_pair),
                        'combinations': 0,
                        'hits': 0,
                        'total_kills': 0
                    }
                
                map_stats[map_pair]['combinations'] += 1
                map_stats[map_pair]['total_kills'] += combined_kills
                if hit:
                    map_stats[map_pair]['hits'] += 1
        
        # Convert to list and calculate rates
        map_analysis = []
        for map_pair, stats in map_stats.items():
            map_analysis.append({
                'map_combo': ' + '.join(stats['maps']),
                'maps': stats['maps'],
                'combinations': stats['combinations'],
                'hits': stats['hits'],
                'hit_rate': round((stats['hits'] / stats['combinations'] * 100), 1) if stats['combinations'] > 0 else 0,
                'avg_kills': round(stats['total_kills'] / stats['combinations'], 1) if stats['combinations'] > 0 else 0
            })
        
        # Sort by combinations (most common first)
        map_analysis.sort(key=lambda x: x['combinations'], reverse=True)
        return map_analysis
