# backend/theo_engine.py
"""
Markov-based Valorant map/series win probability engine.

Key design decisions:
- Phase 1 (rounds 1-12): each round probability uses the blend formula
    p_round = (team_a_rate_on_side + (1 - team_b_rate_on_opposite_side)) / 2
- Phase 2 (rounds 13-24): sides swap
- OT (round 25+): p_round = 0.5 (symmetric by design — no OT edge modelled)
- A map is won at first team to reach 13 rounds (regulation), then first to
  reach N+2 in OT (score parity after 24 rounds), but we model OT as 50/50.
- If a team/map/side is not in the rates file, fall back to the league average
  for that (map, side), and finally to the overall average.
"""

import json
import os
from functools import lru_cache
from typing import Optional

# --------------------------------------------------------------------------- #
# Default rates path
# --------------------------------------------------------------------------- #

_DEFAULT_RATES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', 'data', 'half_win_rates.json'
)

# --------------------------------------------------------------------------- #
# Markov state: (team_a_rounds_won, team_b_rounds_won)
# --------------------------------------------------------------------------- #

REGULATION_HALF = 12     # rounds per half in regulation
WIN_THRESHOLD = 13       # rounds needed to win in regulation
OT_WIN_MARGIN = 2        # OT: first to lead by this many after tie at 12-12


class TheoEngine:
    """
    Computes Valorant map and series win probabilities using half win-rate data.
    """

    def __init__(self, rates_path: str = _DEFAULT_RATES_PATH):
        rates_path = os.path.normpath(rates_path)
        with open(rates_path) as f:
            data = json.load(f)

        self._team_rates: dict = data.get('team_map_side', {})
        self._league_rates: dict = data.get('league_map_side', {})
        self._overall_avg: float = data.get('overall_avg', 0.5)

    # ---------------------------------------------------------------------- #
    # Rate lookups
    # ---------------------------------------------------------------------- #

    def _get_rate(self, team: str, map_name: str, side: str) -> float:
        """
        Look up P(win a single round) for (team, map, side).
        Fallback chain: team-specific → league map/side avg → overall avg.
        """
        key = f'{team}|{map_name}|{side}'
        entry = self._team_rates.get(key)
        if entry:
            return entry['rate']

        # League average for this map/side
        lg_key = f'{map_name}|{side}'
        lg = self._league_rates.get(lg_key)
        if lg:
            return lg['rate']

        return self._overall_avg

    # ---------------------------------------------------------------------- #
    # Single-round probability blend
    # ---------------------------------------------------------------------- #

    def _round_win_prob(
        self,
        team_a: str,
        team_b: str,
        map_name: str,
        team_a_side: str,   # 'atk' or 'def'
    ) -> float:
        """
        P(team_a wins a single round) given sides.

        Blend formula:
          team_a_rate  = team_a's win rate on their current side
          team_b_opp   = team_b's win rate on the opposite side
          p = (team_a_rate + (1 - team_b_opp)) / 2

        This averages: (team_a's offensive quality) and
                       (1 - team_b's defensive quality) to get a consensus
        round probability.
        """
        team_b_side = 'def' if team_a_side == 'atk' else 'atk'

        a_rate = self._get_rate(team_a, map_name, team_a_side)
        b_rate = self._get_rate(team_b, map_name, team_b_side)

        p = (a_rate + (1.0 - b_rate)) / 2.0
        # Clamp to (0.05, 0.95) to avoid degenerate distributions
        return max(0.05, min(0.95, p))

    # ---------------------------------------------------------------------- #
    # Markov map win probability (from score 0-0)
    # ---------------------------------------------------------------------- #

    def _build_markov_table(
        self,
        p1: float,   # P(team_a wins a round) in phase 1 (rounds 1-12)
        p2: float,   # P(team_a wins a round) in phase 2 (rounds 13-24)
        p_ot: float = 0.5,
    ) -> float:
        """
        Compute P(team_a wins map) using dynamic programming over
        (a_rounds_won, b_rounds_won) states.

        States: (a, b) where a = team_a rounds, b = team_b rounds.
        The map ends when a = 13 or b = 13 (regulation) or at OT resolution.
        We resolve OT analytically as a geometric series at p=0.5.
        """
        # dp[(a, b)] = P(reaching state (a, b))
        # Iterate in topological order (by total rounds played).
        # At total=24, the only non-terminal state is (12,12) — the OT entry.
        # We resolve it in one step with p_ot = 0.5 → sends prob to terminals
        # (13,12) [A wins] and (12,13) [B wins], both of which are handled as
        # terminal absorbers above.  No separate OT correction needed.
        dp = {(0, 0): 1.0}
        win_prob = 0.0

        max_total = WIN_THRESHOLD * 2  # iterate totals 0..25 (state 12-12 at total=24)
        for total in range(0, max_total):
            for a in range(max(0, total - (WIN_THRESHOLD - 1)),
                           min(total + 1, WIN_THRESHOLD)):
                b = total - a
                if b < 0 or b >= WIN_THRESHOLD:
                    continue

                prob = dp.get((a, b), 0.0)
                if prob < 1e-14:
                    continue

                # Determine current phase → round win probability
                if total < REGULATION_HALF:
                    p_win = p1
                elif total < REGULATION_HALF * 2:
                    p_win = p2
                else:
                    # OT: only (12,12) reaches here; resolved at p_ot = 0.5
                    p_win = p_ot

                # Team A wins this round
                new_a = a + 1
                if new_a == WIN_THRESHOLD:
                    win_prob += prob * p_win
                else:
                    dp[(new_a, b)] = dp.get((new_a, b), 0.0) + prob * p_win

                # Team B wins this round
                new_b = b + 1
                if new_b == WIN_THRESHOLD:
                    pass  # team_b wins, no contribution to win_prob
                else:
                    dp[(a, new_b)] = dp.get((a, new_b), 0.0) + prob * (1.0 - p_win)

        return win_prob

    # ---------------------------------------------------------------------- #
    # Public API
    # ---------------------------------------------------------------------- #

    def map_win_prob(
        self,
        team_a: str,
        team_b: str,
        map_name: str,
        team_a_starts: str = 'atk',
    ) -> float:
        """
        Returns P(team_a wins the map).

        Parameters
        ----------
        team_a, team_b : str
            Team abbreviations as stored in match_map_halves (e.g. 'SEN', 'G2').
        map_name : str
            Map name as stored (e.g. 'Ascent', 'Haven').
        team_a_starts : str
            'atk' if team_a starts on attack side, 'def' otherwise.
        """
        team_a_side_p1 = team_a_starts
        team_a_side_p2 = 'def' if team_a_starts == 'atk' else 'atk'  # sides swap

        p1 = self._round_win_prob(team_a, team_b, map_name, team_a_side_p1)
        p2 = self._round_win_prob(team_a, team_b, map_name, team_a_side_p2)

        return self._build_markov_table(p1, p2)

    def series_win_prob(
        self,
        team_a: str,
        team_b: str,
        map_pool: list,
        team_a_sides: dict,
    ) -> float:
        """
        Returns P(team_a wins a BO3 series).

        Parameters
        ----------
        map_pool : list[str]
            List of map names to be played (in order).  For BO3 this should
            have 2 or 3 entries.  If only 2 are provided the third is ignored.
        team_a_sides : dict[str, str]
            {map_name: 'atk'|'def'} — which side team_a starts on each map.
            Maps not present default to 'atk'.

        Returns P(team_a wins 2-0) + P(team_a wins 2-1) assuming independence.
        """
        if len(map_pool) < 2:
            raise ValueError('map_pool must have at least 2 maps for a BO3')

        probs = []
        for m in map_pool[:3]:
            side = team_a_sides.get(m, 'atk')
            probs.append(self.map_win_prob(team_a, team_b, m, side))

        p1, p2 = probs[0], probs[1]
        p3 = probs[2] if len(probs) >= 3 else 0.5  # if only 2 maps specified

        # P(2-0): win maps 1 and 2
        p_2_0 = p1 * p2

        # P(2-1): (win map1, lose map2, win map3) or (lose map1, win map2, win map3)
        p_2_1 = p1 * (1 - p2) * p3 + (1 - p1) * p2 * p3

        return p_2_0 + p_2_1

    def live_map_win_prob(
        self,
        team_a: str,
        team_b: str,
        map_name: str,
        t1_score: int,
        t2_score: int,
        team_a_starts: str = 'atk',
    ) -> float:
        """
        Returns P(team_a wins the map) given current score.

        Uses the same Markov model but starts from state (t1_score, t2_score)
        rather than (0, 0).  The current half is determined from total rounds played.
        """
        # Validate inputs
        if t1_score >= WIN_THRESHOLD or t2_score >= WIN_THRESHOLD:
            # Map already over
            return 1.0 if t1_score >= WIN_THRESHOLD else 0.0

        total_played = t1_score + t2_score

        # Determine starting sides for remaining rounds
        if total_played < REGULATION_HALF:
            # Still in phase 1
            current_side_a = team_a_starts
        elif total_played < REGULATION_HALF * 2:
            # Phase 2: sides swapped
            current_side_a = 'def' if team_a_starts == 'atk' else 'atk'
        else:
            # OT
            current_side_a = team_a_starts  # doesn't matter at p=0.5

        team_a_side_p2 = 'def' if team_a_starts == 'atk' else 'atk'

        team_a_side_p2 = 'def' if team_a_starts == 'atk' else 'atk'

        # Build Markov table from the current score state using topological order.
        dp = {(t1_score, t2_score): 1.0}
        win_prob = 0.0

        min_total = t1_score + t2_score
        max_total = WIN_THRESHOLD * 2  # state (12,12) reached at total=24

        for total in range(min_total, max_total):
            for a in range(max(t1_score, total - (WIN_THRESHOLD - 1)),
                           min(total + 1, WIN_THRESHOLD)):
                b = total - a
                if b < 0 or b >= WIN_THRESHOLD:
                    continue
                if a < t1_score or b < t2_score:
                    continue

                prob = dp.get((a, b), 0.0)
                if prob < 1e-14:
                    continue

                if total < REGULATION_HALF:
                    team_a_current_side = team_a_starts
                    p_win = self._round_win_prob(team_a, team_b, map_name, team_a_current_side)
                elif total < REGULATION_HALF * 2:
                    team_a_current_side = team_a_side_p2
                    p_win = self._round_win_prob(team_a, team_b, map_name, team_a_current_side)
                else:
                    p_win = 0.5  # OT: no edge

                new_a = a + 1
                if new_a == WIN_THRESHOLD:
                    win_prob += prob * p_win
                else:
                    dp[(new_a, b)] = dp.get((new_a, b), 0.0) + prob * p_win

                new_b = b + 1
                if new_b == WIN_THRESHOLD:
                    pass
                else:
                    dp[(a, new_b)] = dp.get((a, new_b), 0.0) + prob * (1.0 - p_win)

        return win_prob


# --------------------------------------------------------------------------- #
# Quick smoke test when run directly
# --------------------------------------------------------------------------- #

if __name__ == '__main__':
    import sys

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    rates_path = os.path.join(project_root, 'data', 'half_win_rates.json')

    if not os.path.exists(rates_path):
        print(f'ERROR: {rates_path} not found. Run scripts/half_win_rate_model.py first.')
        sys.exit(1)

    engine = TheoEngine(rates_path)

    print('=== TheoEngine Smoke Test ===')

    # Map win probability
    p = engine.map_win_prob('SEN', 'G2', 'Haven', team_a_starts='atk')
    print(f'SEN vs G2 on Haven (SEN starts atk): {p:.4f}')

    p = engine.map_win_prob('G2', 'SEN', 'Ascent', team_a_starts='def')
    print(f'G2 vs SEN on Ascent (G2 starts def):  {p:.4f}')

    # Series win probability
    p_series = engine.series_win_prob(
        'SEN', 'G2',
        map_pool=['Haven', 'Ascent', 'Pearl'],
        team_a_sides={'Haven': 'atk', 'Ascent': 'def', 'Pearl': 'atk'},
    )
    print(f'SEN vs G2 BO3 (Haven/Ascent/Pearl):    {p_series:.4f}')

    # Live map win probability
    p_live = engine.live_map_win_prob('SEN', 'G2', 'Haven', 9, 3, 'atk')
    print(f'SEN vs G2 Haven, SEN leads 9-3:         {p_live:.4f}')

    p_live2 = engine.live_map_win_prob('SEN', 'G2', 'Haven', 3, 9, 'atk')
    print(f'SEN vs G2 Haven, SEN trails 3-9:        {p_live2:.4f}')

    # Symmetry check: swapping teams at 0-0 should give ~1-p
    p_fwd = engine.map_win_prob('SEN', 'G2', 'Lotus', 'atk')
    p_rev = engine.map_win_prob('G2', 'SEN', 'Lotus', 'def')
    print(f'Symmetry check SEN/G2 Lotus: fwd={p_fwd:.4f}, rev={p_rev:.4f}, sum={p_fwd+p_rev:.4f}')
