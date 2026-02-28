"""Matchup-aware probability adjustments for player kill props.

This module lets callers optionally pass team matchup odds (or a direct team
win probability), then applies a non-linear mean adjustment before computing
over/under probabilities.

Rationale:
- Team-strength effect: better teams support better individual output.
- Blowout-rounds effect: extreme mismatches often reduce total rounds, which
  lowers kill opportunity for both teams.

The combined adjustment is intentionally bounded and configurable.
"""

from __future__ import annotations

import math
from typing import Dict, Optional


def _odds_to_implied_prob(odds: float) -> float:
    """Convert decimal or American odds to implied probability.

    Heuristic:
    - abs(odds) >= 100 => American odds
    - otherwise => decimal odds (must be > 1)
    """
    if odds is None:
        raise ValueError("odds cannot be None")

    o = float(odds)

    # American odds
    if abs(o) >= 100:
        if o == 0:
            raise ValueError("American odds cannot be 0")
        if o < 0:
            return abs(o) / (abs(o) + 100)
        return 100 / (o + 100)

    # Decimal odds
    if o <= 1.0:
        raise ValueError("Decimal odds must be > 1.0")
    return 1.0 / o


def infer_team_win_probability(
    team_win_prob: Optional[float] = None,
    team_odds: Optional[float] = None,
    opp_odds: Optional[float] = None,
) -> Dict:
    """Infer vig-free team win probability from user inputs.

    Returns a dictionary with:
      - provided: bool
      - team_win_prob: float|None
      - method: description string
      - warning: optional warning text
    """
    if team_win_prob is not None:
        p = float(team_win_prob)
        if not (0 < p < 1):
            raise ValueError("team_win_prob must be between 0 and 1")
        return {
            'provided': True,
            'team_win_prob': p,
            'method': 'direct_team_win_prob'
        }

    if team_odds is None and opp_odds is None:
        return {'provided': False, 'team_win_prob': None, 'method': 'none'}

    if team_odds is None or opp_odds is None:
        raise ValueError("Provide both team_odds and opp_odds, or provide team_win_prob")

    p_team_raw = _odds_to_implied_prob(float(team_odds))
    p_opp_raw = _odds_to_implied_prob(float(opp_odds))
    total = p_team_raw + p_opp_raw
    if total <= 0:
        raise ValueError("Invalid odds, implied probability total <= 0")

    return {
        'provided': True,
        'team_win_prob': p_team_raw / total,  # vig-free normalization
        'method': 'vig_free_from_team_and_opp_odds',
        'raw_team_prob': p_team_raw,
        'raw_opp_prob': p_opp_raw,
        'overround': total
    }


def apply_matchup_adjustment(
    dist_params: Dict,
    team_win_prob: Optional[float],
    alpha_strength: float = 0.04,
    beta_mismatch: float = 0.04,
    gamma_mismatch: float = 4.0,
    min_multiplier: float = 0.72,
    max_multiplier: float = 1.28,
) -> Dict:
    """Apply matchup-aware non-linear mean adjustment to distribution params.

    Defaults calibrated from 3,753 historical player-map records (2024-2026 VCT).
    Calibration result: team win probability has near-zero effect on individual
    kill output beyond the player's historical baseline. alpha and beta are set
    to ~0.04 (effectively minimal adjustment). The mu_base alone is the best
    single predictor.

    multiplier = 1 + strength_term - mismatch_penalty
    where:
      strength_term = alpha_strength * tanh((p_win - 0.5)/0.22)
      mismatch_penalty = beta_mismatch * (|p_win-0.5|/0.5)^gamma_mismatch

    This makes extreme favorites/underdogs incur a rounds/opportunity penalty,
    instead of assuming linearly increasing output with win probability.
    """
    if team_win_prob is None:
        return {
            'dist_params': dict(dist_params),
            'applied': False,
            'reason': 'no_matchup_inputs'
        }

    p = float(team_win_prob)
    if not (0 < p < 1):
        raise ValueError("team_win_prob must be between 0 and 1")

    adjusted = dict(dist_params)
    mu_base = float(dist_params.get('mu', 0.0))
    var_base = float(dist_params.get('var', 0.0))

    # Offset from coinflip and normalized extremeness.
    d = p - 0.5
    ext = min(1.0, abs(d) / 0.5)

    strength_term = alpha_strength * math.tanh(d / 0.22)
    mismatch_penalty = beta_mismatch * (ext ** gamma_mismatch)

    multiplier = 1.0 + strength_term - mismatch_penalty
    multiplier = max(min_multiplier, min(max_multiplier, multiplier))

    mu_adj = max(0.01, mu_base * multiplier)
    adjusted['mu'] = mu_adj

    if adjusted.get('dist') == 'poisson':
        adjusted['lambda'] = mu_adj
    elif adjusted.get('dist') == 'nbinom':
        k = float(adjusted.get('k', 1.0))
        k = max(1e-6, k)
        adjusted['p'] = k / (k + mu_adj)

    # Track a softly adjusted variance for display/context.
    adjusted['var'] = max(0.0, var_base * (0.85 + 0.3 * ext))

    return {
        'dist_params': adjusted,
        'applied': True,
        'team_win_prob': p,
        'mu_base': mu_base,
        'mu_adjusted': mu_adj,
        'multiplier': multiplier,
        'components': {
            'strength_term': strength_term,
            'mismatch_penalty': mismatch_penalty,
            'extremeness': ext
        },
        'params': {
            'alpha_strength': alpha_strength,
            'beta_mismatch': beta_mismatch,
            'gamma_mismatch': gamma_mismatch,
            'min_multiplier': min_multiplier,
            'max_multiplier': max_multiplier
        }
    }

