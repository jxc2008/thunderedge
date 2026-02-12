# scraper/prizepicks_processor.py
from typing import Dict, List, Tuple
import itertools
from scraper.player_processor import PlayerProcessor

class PrizePicksProcessor(PlayerProcessor):
    """
    Processor for PrizePicks lines that combine kills across maps.
    
    combo_maps=2 (Bo3): Maps 1+2 combined. For 3-map matches: (1,2), (1,3), (2,3).
    combo_maps=3 (Bo5): Maps 1+2+3 combined. For 4-map matches: (1,2,3), (1,2,4), etc.
    """
    
    def __init__(self, kill_line: float = 30.5, combo_maps: int = 2):
        """
        Initialize processor with PrizePicks kill line.
        
        Args:
            kill_line: The combined kill line (e.g., 30.5 for 2 maps, 45.5 for 3 maps)
            combo_maps: 2 for Bo3 (Maps 1+2), 3 for Bo5 (Maps 1+2+3)
        """
        super().__init__(kill_line=kill_line)
        self.combo_maps = max(2, min(3, int(combo_maps)))
    
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
            all_kills = match_data.get('map_kills', [])
            all_scores = match_data.get('map_scores', [])
            # Exclude 0-kill maps (unplayed) - keep parallel indices
            filtered = [(k, s) for k, s in zip(all_kills, all_scores) if k is not None and k > 0]
            map_kills = [p[0] for p in filtered]
            map_scores = [p[1] for p in filtered]
            
            if len(map_kills) < self.combo_maps:
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
            
            # For PrizePicks, we analyze the first n maps (2 or 3)
            n = min(self.combo_maps, len(map_kills))
            if n >= self.combo_maps:
                combined_kills = sum(map_kills[:n])
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

    def _calculate_outcome_stats(self, match_results: List[Dict], kill_line: float) -> Dict:
        """
        Calculate OVER/UNDER rates by map outcome composition.
        For 2-map: both_wins (WW), split (WL/LW), both_losses (LL)
        For 3-map: all_wins (WWW), two_wins (WWL/WLW/LWW), one_win (WLL/LWL/LLW), all_losses (LLL)
        """
        n = self.combo_maps
        if n == 2:
            buckets = {
                'both_wins': {'label': 'Both Maps Won (W+W)', 'over': 0, 'under': 0, 'total': 0},
                'split': {'label': 'One Win, One Loss (W+L)', 'over': 0, 'under': 0, 'total': 0},
                'both_losses': {'label': 'Both Maps Lost (L+L)', 'over': 0, 'under': 0, 'total': 0}
            }
        else:
            buckets = {
                'all_wins': {'label': 'All 3 Maps Won (W+W+W)', 'over': 0, 'under': 0, 'total': 0},
                'two_wins': {'label': 'Two Wins, One Loss (2W+1L)', 'over': 0, 'under': 0, 'total': 0},
                'one_win': {'label': 'One Win, Two Losses (1W+2L)', 'over': 0, 'under': 0, 'total': 0},
                'all_losses': {'label': 'All 3 Maps Lost (L+L+L)', 'over': 0, 'under': 0, 'total': 0}
            }

        for match in match_results:
            map_scores = match.get('map_scores', [])
            combinations = match.get('combinations', [])

            if not map_scores or not combinations:
                continue

            map_outcomes = []
            for score in map_scores:
                is_win, _ = self._parse_map_score(score)
                map_outcomes.append(is_win)

            for combo in combinations:
                maps = combo.get('maps', [])
                if len(maps) != n:
                    continue

                indices = [m - 1 for m in maps]
                if any(i < 0 or i >= len(map_outcomes) for i in indices):
                    continue

                outcomes = [map_outcomes[i] for i in indices]
                if any(o is None for o in outcomes):
                    continue

                wins = sum(1 for o in outcomes if o)
                if n == 2:
                    if wins == 2:
                        bucket_key = 'both_wins'
                    elif wins == 1:
                        bucket_key = 'split'
                    else:
                        bucket_key = 'both_losses'
                else:
                    if wins == 3:
                        bucket_key = 'all_wins'
                    elif wins == 2:
                        bucket_key = 'two_wins'
                    elif wins == 1:
                        bucket_key = 'one_win'
                    else:
                        bucket_key = 'all_losses'

                result_key = 'over' if combo.get('hit', False) else 'under'
                buckets[bucket_key][result_key] += 1
                buckets[bucket_key]['total'] += 1

        for bucket in buckets.values():
            if bucket['total'] > 0:
                bucket['over_pct'] = round((bucket['over'] / bucket['total']) * 100, 1)
                bucket['under_pct'] = round((bucket['under'] / bucket['total']) * 100, 1)
            else:
                bucket['over_pct'] = 0
                bucket['under_pct'] = 0

        return {
            **buckets,
            'total_combinations': sum(b['total'] for b in buckets.values()),
            'combo_maps': n
        }
    
    def classify_line(self, rounds_needed: float) -> tuple:
        """
        Classify the betting line based on rounds needed.
        Thresholds scaled for combo_maps: 2-map uses 38-50, 3-map uses 57-75 (1.5x).
        """
        # Bo5 (3 maps): scale thresholds by 1.5 since we need ~1.5x more rounds
        scale = 1.5 if self.combo_maps == 3 else 1.0
        t = lambda x: x * scale  # threshold helper
        if rounds_needed < t(38):
            return ("SEVERELY UNDERPRICED", "STRONG OVER")
        elif rounds_needed < t(40):
            return ("MODERATELY UNDERPRICED", "OVER")
        elif rounds_needed < t(41):
            return ("SLIGHTLY UNDERPRICED", "LEAN OVER")
        elif rounds_needed < t(47):
            return ("WELL PRICED", "NO EDGE")
        elif rounds_needed < t(48):
            return ("SLIGHTLY OVERPRICED", "LEAN UNDER")
        elif rounds_needed < t(50):
            return ("MODERATELY OVERPRICED", "UNDER")
        else:
            return ("SEVERELY OVERPRICED", "STRONG UNDER")
    
    def process_match_combinations(self, match_map_kills: List[int]) -> List[Dict]:
        """
        Process a match's map kills into combinations.
        Excludes 0-kill maps (unplayed) from all calculations.
        
        For Bo5 (combo_maps=3): 2-map matches are scaled by 1.5 to estimate 3-map equivalent,
        so they contribute to the distribution instead of being discarded.
        
        Returns:
            List of combination results based on combo_maps.
        """
        match_map_kills = [k for k in match_map_kills if k is not None and k > 0]
        num_maps = len(match_map_kills)
        n = self.combo_maps  # 2 or 3
        
        if num_maps < 2:
            return []
        
        combinations = []
        
        # Bo5 mode: scale 2-map matches by 1.5 to estimate 3-map equivalent
        if n == 3 and num_maps == 2:
            raw_kills = match_map_kills[0] + match_map_kills[1]
            scaled_kills = round(raw_kills * 1.5)  # 2 maps -> 3 maps: scale by 1.5
            combinations.append({
                'maps': [1, 2],
                'combined_kills': scaled_kills,
                'hit': scaled_kills > self.kill_line,
                'map1_kills': match_map_kills[0],
                'map2_kills': match_map_kills[1],
                'scaled': True,
                'raw_kills': raw_kills,
            })
            return combinations
        
        if num_maps < n:
            return []
        
        for indices in itertools.combinations(range(num_maps), n):
            map_indices = [i + 1 for i in indices]  # 1-indexed for display
            combined_kills = sum(match_map_kills[i] for i in indices)
            combo = {
                'maps': map_indices,
                'combined_kills': combined_kills,
                'hit': combined_kills > self.kill_line,
            }
            for j, idx in enumerate(indices):
                combo[f'map{j+1}_kills'] = match_map_kills[idx]
            combinations.append(combo)
        
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
        outcome_stats = self._calculate_outcome_stats(match_results, self.kill_line)
        
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
            'two_map_outcome_stats': outcome_stats,  # WW/WL/LL or WWW/2W1L/1W2L/LLL
            'combo_maps': self.combo_maps,
            'total_combinations': total_combinations,
            'hit_count': hit_count,
            'miss_count': miss_count,
            'hit_percentage': round(hit_percentage, 1),
            'miss_percentage': round(miss_percentage, 1)
        }
    
    def _calculate_agent_hit_rates(self, match_results: List[Dict], kill_line: float) -> List[Dict]:
        """Calculate hit rates broken down by agent combinations (uses combo_maps)"""
        agent_stats = {}
        n = self.combo_maps
        
        for match in match_results:
            agents = match.get('agents', [])
            combinations = match.get('combinations', [])
            
            for combo in combinations:
                if len(combo.get('maps', [])) != n:
                    continue
                maps_indices = [m - 1 for m in combo['maps']]
                if any(i < 0 or i >= len(agents) for i in maps_indices):
                    continue
                agent_combo = tuple(sorted([agents[i] for i in maps_indices if i < len(agents)]))
                if len(agent_combo) != n:
                    continue
                if agent_combo not in agent_stats:
                    agent_stats[agent_combo] = {'agents': list(agent_combo), 'combinations': 0, 'hits': 0, 'total_kills': 0}
                agent_stats[agent_combo]['combinations'] += 1
                agent_stats[agent_combo]['total_kills'] += combo['combined_kills']
                if combo.get('hit'):
                    agent_stats[agent_combo]['hits'] += 1
        
        agent_analysis = []
        for agent_tuple, stats in agent_stats.items():
            agent_analysis.append({
                'agent_combo': ' + '.join(stats['agents']),
                'agents': stats['agents'],
                'combinations': stats['combinations'],
                'hits': stats['hits'],
                'hit_rate': round((stats['hits'] / stats['combinations'] * 100), 1) if stats['combinations'] > 0 else 0,
                'avg_kills': round(stats['total_kills'] / stats['combinations'], 1) if stats['combinations'] > 0 else 0
            })
        agent_analysis.sort(key=lambda x: x['combinations'], reverse=True)
        return agent_analysis
    
    def _calculate_map_hit_rates(self, match_results: List[Dict], kill_line: float) -> List[Dict]:
        """Calculate hit rates broken down by map combinations (uses combo_maps)"""
        map_stats = {}
        n = self.combo_maps
        
        for match in match_results:
            map_names = match.get('map_names', [])
            combinations = match.get('combinations', [])
            
            for combo in combinations:
                if len(combo.get('maps', [])) != n:
                    continue
                maps_indices = [m - 1 for m in combo['maps']]
                if any(i < 0 or i >= len(map_names) for i in maps_indices):
                    continue
                map_combo = tuple(sorted([map_names[i] for i in maps_indices if i < len(map_names)]))
                if len(map_combo) != n:
                    continue
                if map_combo not in map_stats:
                    map_stats[map_combo] = {'maps': list(map_combo), 'combinations': 0, 'hits': 0, 'total_kills': 0}
                map_stats[map_combo]['combinations'] += 1
                map_stats[map_combo]['total_kills'] += combo['combined_kills']
                if combo.get('hit'):
                    map_stats[map_combo]['hits'] += 1
        
        map_analysis = []
        for map_tuple, stats in map_stats.items():
            map_analysis.append({
                'map_combo': ' + '.join(stats['maps']),
                'maps': stats['maps'],
                'combinations': stats['combinations'],
                'hits': stats['hits'],
                'hit_rate': round((stats['hits'] / stats['combinations'] * 100), 1) if stats['combinations'] > 0 else 0,
                'avg_kills': round(stats['total_kills'] / stats['combinations'], 1) if stats['combinations'] > 0 else 0
            })
        map_analysis.sort(key=lambda x: x['combinations'], reverse=True)
        return map_analysis
