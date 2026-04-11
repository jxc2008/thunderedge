"""
backend/theo_engine.py

Pre-match Markov series-winner theo engine.

Theo calculation:
  1. For each map in the pool, compute per-round win probabilities from
     half_win_rates.json (per team/map/side historical rates).
  2. Run a Markov DP over (a_score, b_score) states to get P(team_a wins map).
  3. Chain map probs into a BO3 series win probability.
  4. Adjust using market odds as a prior:
       final_theo = market_p + (model_series_p - 0.5)
     The market captures overall skill gap; the model captures map-specific edge.
  5. When data is thin, weight the map adjustment down toward 0 (trust market).

Fallback chain for rate lookups:
  team-specific rate → league map/side average → overall average
"""

import json
import math
import os
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

_DEFAULT_RATES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', 'data', 'half_win_rates.json'
)

REGULATION_HALF = 12
WIN_THRESHOLD   = 13
MIN_ROUNDS_FULL_WEIGHT = 15   # effective rounds for full data confidence


# --------------------------------------------------------------------------- #
# TheoEngine
# --------------------------------------------------------------------------- #

class TheoEngine:
    """
    Computes pre-match series win probabilities for Valorant BO3 markets.

    Args:
        rates_path: Path to half_win_rates.json produced by half_win_rate_model.py.
    """

    def __init__(self, rates_path: str = _DEFAULT_RATES_PATH):
        rates_path = os.path.normpath(rates_path)
        if not os.path.exists(rates_path):
            raise FileNotFoundError(
                f'half_win_rates.json not found at {rates_path}. '
                'Run scripts/half_win_rate_model.py first.'
            )
        with open(rates_path) as f:
            data = json.load(f)

        self._team_rates: dict  = data.get('team_map_side', {})
        self._league_rates: dict = data.get('league_map_side', {})
        self._overall_avg: float = data.get('overall_avg', 0.5)

    # ---------------------------------------------------------------------- #
    # Rate lookups
    # ---------------------------------------------------------------------- #

    def _get_rate(self, team: str, map_name: str, side: str) -> float:
        """P(team wins a single round) on this map/side. Three-tier fallback."""
        entry = self._team_rates.get(f'{team}|{map_name}|{side}')
        if entry:
            return entry['rate']
        lg = self._league_rates.get(f'{map_name}|{side}')
        if lg:
            return lg['rate']
        return self._overall_avg

    def _data_weight(self, team_a: str, team_b: str, map_name: str) -> float:
        """
        Confidence weight [0, 1] for a (team_a, team_b, map) combination.

        1.0 means both teams have at least MIN_ROUNDS_FULL_WEIGHT effective
        rounds on this map across both sides.  Below that we linearly shrink
        toward 0, which causes the market-odds adjustment to shrink toward 0
        (i.e. just use the market price as-is).
        """
        total = 0.0
        count = 0
        for team in (team_a, team_b):
            for side in ('atk', 'def'):
                entry = self._team_rates.get(f'{team}|{map_name}|{side}')
                if entry:
                    total += entry.get('total', 0)
                    count += 1
        if count == 0:
            return 0.0
        avg_rounds = total / count
        return min(1.0, avg_rounds / MIN_ROUNDS_FULL_WEIGHT)

    # ---------------------------------------------------------------------- #
    # Single-round probability
    # ---------------------------------------------------------------------- #

    def _round_win_prob(
        self,
        team_a: str,
        team_b: str,
        map_name: str,
        team_a_side: str,
    ) -> float:
        """
        P(team_a wins one round) given current sides.

        Blend: (team_a's rate on their side + team_b's weakness on opposite side) / 2
        """
        team_b_side = 'def' if team_a_side == 'atk' else 'atk'
        a_rate = self._get_rate(team_a, map_name, team_a_side)
        b_rate = self._get_rate(team_b, map_name, team_b_side)
        p = (a_rate + (1.0 - b_rate)) / 2.0
        return max(0.05, min(0.95, p))

    # ---------------------------------------------------------------------- #
    # Markov map win probability
    # ---------------------------------------------------------------------- #

    def _markov_map_win(self, p1: float, p2: float) -> float:
        """
        P(team_a wins map) via DP over (a_score, b_score) states.

        p1: P(team_a wins round) in phase 1 (rounds 1-12)
        p2: P(team_a wins round) in phase 2 (rounds 13-24)
        OT (12-12) resolved at 0.5.
        """
        dp = {(0, 0): 1.0}
        win_prob = 0.0

        for total in range(WIN_THRESHOLD * 2):
            for a in range(max(0, total - (WIN_THRESHOLD - 1)),
                           min(total + 1, WIN_THRESHOLD)):
                b = total - a
                if b < 0 or b >= WIN_THRESHOLD:
                    continue
                prob = dp.get((a, b), 0.0)
                if prob < 1e-14:
                    continue

                if total < REGULATION_HALF:
                    p = p1
                elif total < REGULATION_HALF * 2:
                    p = p2
                else:
                    p = 0.5  # OT

                new_a = a + 1
                if new_a == WIN_THRESHOLD:
                    win_prob += prob * p
                else:
                    dp[(new_a, b)] = dp.get((new_a, b), 0.0) + prob * p

                new_b = b + 1
                if new_b < WIN_THRESHOLD:
                    dp[(a, new_b)] = dp.get((a, new_b), 0.0) + prob * (1.0 - p)

        return win_prob

    def map_win_prob(
        self,
        team_a: str,
        team_b: str,
        map_name: str,
        team_a_starts: str = 'atk',
    ) -> float:
        """P(team_a wins this map) from score 0-0."""
        p1 = self._round_win_prob(team_a, team_b, map_name, team_a_starts)
        p2_side = 'def' if team_a_starts == 'atk' else 'atk'
        p2 = self._round_win_prob(team_a, team_b, map_name, p2_side)
        return self._markov_map_win(p1, p2)

    # ---------------------------------------------------------------------- #
    # Series win probability (model only, no market adjustment)
    # ---------------------------------------------------------------------- #

    def model_series_prob(
        self,
        team_a: str,
        team_b: str,
        map_pool: List[str],
        team_a_sides: Dict[str, str],
    ) -> float:
        """
        P(team_a wins BO3 series) using only the Markov map model.

        map_pool:     list of map names in play order (2 or 3 maps)
        team_a_sides: {map_name: 'atk'|'def'} — team_a's starting side.
                      Maps not listed default to 'atk'.
        """
        if len(map_pool) < 2:
            raise ValueError('map_pool must have at least 2 maps')

        probs = []
        for m in map_pool[:3]:
            side = team_a_sides.get(m, 'atk')
            probs.append(self.map_win_prob(team_a, team_b, m, side))

        p1, p2 = probs[0], probs[1]
        p3 = probs[2] if len(probs) >= 3 else 0.5

        p_2_0 = p1 * p2
        p_2_1 = p1 * (1 - p2) * p3 + (1 - p1) * p2 * p3
        return p_2_0 + p_2_1

    # ---------------------------------------------------------------------- #
    # Final theo with market-odds adjustment
    # ---------------------------------------------------------------------- #

    def series_theo(
        self,
        team_a: str,
        team_b: str,
        map_pool: List[str],
        team_a_sides: Dict[str, str],
        kalshi_yes_ask: int,
    ) -> Tuple[float, float, str]:
        """
        Compute final theo for team_a winning the series.

        Formula:
            market_p   = kalshi_yes_ask / 100
            model_p    = Markov series win prob
            map_delta  = model_p - 0.5   (model's edge vs coin flip)
            data_w     = confidence weight in [0, 1] based on sample size
            final_theo = market_p + data_w * map_delta

        When data_w = 1.0: full model adjustment applied on top of market price.
        When data_w = 0.0: no adjustment, final_theo = market_p (pure market).

        Returns:
            (final_theo, data_weight, confidence_label)
        """
        market_p   = kalshi_yes_ask / 100.0
        model_p    = self.model_series_prob(team_a, team_b, map_pool, team_a_sides)
        map_delta  = model_p - 0.5

        # Average data weight across all maps in pool
        weights = [self._data_weight(team_a, team_b, m) for m in map_pool[:3]]
        data_w = sum(weights) / len(weights)

        final_theo = market_p + data_w * map_delta
        final_theo = max(0.03, min(0.97, final_theo))

        if data_w >= 0.8:
            conf = 'HIGH'
        elif data_w >= 0.4:
            conf = 'MED'
        else:
            conf = 'LOW'

        return final_theo, data_w, conf

    # ---------------------------------------------------------------------- #
    # Side-agnostic variant (when sides are unknown)
    # ---------------------------------------------------------------------- #

    def series_theo_no_sides(
        self,
        team_a: str,
        team_b: str,
        map_pool: List[str],
        kalshi_yes_ask: int,
    ) -> Tuple[float, float, str]:
        """
        Same as series_theo but averages over both possible starting sides
        for each map.  Use when pick/ban sides haven't been announced yet.
        """
        averaged_sides: Dict[str, str] = {}
        # We'll pass 'avg' as a sentinel — map_win_prob handles it by averaging
        # atk-first and def-first results.
        atk_sides = {m: 'atk' for m in map_pool}
        def_sides = {m: 'def' for m in map_pool}

        p_atk = self.model_series_prob(team_a, team_b, map_pool, atk_sides)
        p_def = self.model_series_prob(team_a, team_b, map_pool, def_sides)
        model_p = (p_atk + p_def) / 2.0

        market_p  = kalshi_yes_ask / 100.0
        map_delta = model_p - 0.5
        weights   = [self._data_weight(team_a, team_b, m) for m in map_pool[:3]]
        data_w    = sum(weights) / len(weights)

        final_theo = max(0.03, min(0.97, market_p + data_w * map_delta))
        conf = 'HIGH' if data_w >= 0.8 else ('MED' if data_w >= 0.4 else 'LOW')
        return final_theo, data_w, conf
