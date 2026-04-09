# scripts/half_win_rate_model.py
"""
Compute per-(team, map, side) win rates from match_map_halves and write
to data/half_win_rates.json.

Wilson score confidence intervals are used to smooth small samples.
If a team has fewer than MIN_ROUNDS rounds on a given (map, side), the
model falls back to the league-average rate for that (map, side).
"""

import json
import math
import os
import sqlite3
import sys
from collections import defaultdict
from typing import Dict, Tuple

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

MIN_ROUNDS = 15          # fall back to league average below this threshold
WILSON_Z = 1.645         # 90% confidence interval (one-tailed)

# --------------------------------------------------------------------------- #
# Wilson score lower bound
# --------------------------------------------------------------------------- #

def wilson_lower(wins: int, n: int, z: float = WILSON_Z) -> float:
    """
    Return the lower bound of the Wilson score confidence interval.
    Used as a conservative (shrunk-toward-0) estimate when n is small.
    """
    if n == 0:
        return 0.0
    p_hat = wins / n
    denom = 1 + z * z / n
    centre = p_hat + z * z / (2 * n)
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n))
    return (centre - margin) / denom


def wilson_point(wins: int, n: int, z: float = WILSON_Z) -> float:
    """
    Return the Wilson score mid-point (raw proportion, Wilson-smoothed).
    We use the centre of the interval as the point estimate, which adds
    a Laplace-style prior.
    """
    if n == 0:
        return 0.5
    p_hat = wins / n
    denom = 1 + z * z / n
    centre = (p_hat + z * z / (2 * n)) / denom
    return centre


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #

def load_halves(db_path: str) -> list:
    """
    Return all rows from match_map_halves as list of dicts.
    Only rows with a valid map_name are included.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('''
        SELECT match_id, map_number, map_name, team_name,
               atk_rounds_won, def_rounds_won, total_rounds
        FROM match_map_halves
        WHERE map_name IS NOT NULL AND map_name != ""
    ''')
    cols = ['match_id', 'map_number', 'map_name', 'team_name',
            'atk_rounds_won', 'def_rounds_won', 'total_rounds']
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows


# --------------------------------------------------------------------------- #
# Rate computation
# --------------------------------------------------------------------------- #

def compute_rates(rows: list) -> dict:
    """
    Compute win rates for each (team, map, side) combination.

    Returns a nested dict:
        {
          'team_map_side': {
            '<team>|<map>|atk': {'wins': int, 'total': int, 'rate': float},
            ...
          },
          'league_map_side': {
            '<map>|atk': {'wins': int, 'total': int, 'rate': float},
            ...
          }
        }

    Side 'atk' = T side (attacker), 'def' = CT side (defender).
    The 'total' for each side is the total number of rounds that team played
    on that side on that map (across all matches), not just the map total.
    """

    # ------------------------------------------------------------------ #
    # Aggregate raw win counts
    # ------------------------------------------------------------------ #

    # team_stats[(team, map, side)] = [wins, total_rounds_on_that_side]
    team_stats: Dict[Tuple[str, str, str], list] = defaultdict(lambda: [0, 0])
    # league_stats[(map, side)] = [wins, total_rounds]
    league_stats: Dict[Tuple[str, str], list] = defaultdict(lambda: [0, 0])

    for row in rows:
        team = row['team_name']
        map_name = row['map_name']
        total = row['total_rounds']

        # atk_rounds_won / total_atk_rounds
        # In a standard map (24 rounds), each team plays 12 atk and 12 def.
        # OT adds extra rounds. We only know total rounds and how many each
        # team won on attack vs defence.
        #
        # To get the denominator for each side we use:
        #   total_atk_rounds ≈ ceil(total / 2)  (team played atk in first half + OT)
        #   total_def_rounds ≈ floor(total / 2)
        # But more precisely: in regulation (24 rds) each side = 12.
        # In OT (25+), alternating pistols, so each OT pair = 2 rounds per side.
        # Simplest robust estimate: atk_total = def_total = total // 2 for regulation,
        # which equals wins_atk_team1 + wins_atk_team2 = total rounds.
        #
        # Actually: atk_rounds_won_t1 + def_rounds_won_t2 = total (t2 def = t1 rounds lost on atk)
        # So: atk_total_t1 = atk_wins_t1 + def_wins_t2  <- but we don't join rows here easily.
        #
        # Simplest correct derivation per-row:
        #   atk_total = atk_rounds_won + (total_rounds - atk_rounds_won - def_rounds_won)
        #             = total_rounds - def_rounds_won
        # Because: total = atk_won + def_won + (rounds opponent won on those sides too)
        # Nope - let's think again:
        #   total_rounds = rounds played on map
        #   atk_rounds_won = rounds this team won when playing attack
        #   def_rounds_won = rounds this team won when playing defense
        #   atk_rounds_won + def_rounds_won = total rounds won by this team
        #   total_rounds = total rounds won by both teams
        #
        # How many rounds did this team PLAY on attack? = rounds 1-12 = 12 (regulation)
        # + OT rounds on attack side.
        # We don't directly have this from the data, but we know:
        #   atk_rounds_played = rounds where this team was on attack side
        #   def_rounds_played = rounds where this team was on defense side
        #   atk_rounds_played + def_rounds_played = total_rounds
        #
        # In regulation: atk_rounds_played = 12 for all maps.
        # After halftime swap: they play 12 on the other side.
        # In OT: pairs of 2 rounds, so atk_rounds_played += n_ot_rounds / 2
        #
        # Approximation: atk_rounds_played ≈ total_rounds / 2 (±1 for odd OT rounds)
        # This is robust enough for win rate computation.
        atk_total = max(1, total // 2)
        def_total = max(1, total - atk_total)

        team_stats[(team, map_name, 'atk')][0] += row['atk_rounds_won']
        team_stats[(team, map_name, 'atk')][1] += atk_total
        team_stats[(team, map_name, 'def')][0] += row['def_rounds_won']
        team_stats[(team, map_name, 'def')][1] += def_total

        league_stats[(map_name, 'atk')][0] += row['atk_rounds_won']
        league_stats[(map_name, 'atk')][1] += atk_total
        league_stats[(map_name, 'def')][0] += row['def_rounds_won']
        league_stats[(map_name, 'def')][1] += def_total

    # ------------------------------------------------------------------ #
    # Build league averages (used as fallback)
    # ------------------------------------------------------------------ #

    league_rates = {}
    for (map_name, side), (wins, total) in league_stats.items():
        rate = wilson_point(wins, total) if total > 0 else 0.5
        league_rates[f'{map_name}|{side}'] = {
            'wins': wins,
            'total': total,
            'rate': round(rate, 6),
        }

    # Overall league average (across all maps/sides) as final fallback
    all_wins = sum(v[0] for v in league_stats.values())
    all_total = sum(v[1] for v in league_stats.values())
    overall_avg = wilson_point(all_wins, all_total) if all_total > 0 else 0.5

    # ------------------------------------------------------------------ #
    # Build per-team rates with fallback logic
    # ------------------------------------------------------------------ #

    team_rates = {}
    for (team, map_name, side), (wins, total) in team_stats.items():
        key = f'{team}|{map_name}|{side}'
        league_key = f'{map_name}|{side}'

        if total >= MIN_ROUNDS:
            rate = wilson_point(wins, total)
            used_fallback = False
        else:
            # Fall back to league average for this map/side
            lg = league_rates.get(league_key)
            rate = lg['rate'] if lg else overall_avg
            used_fallback = True

        team_rates[key] = {
            'wins': wins,
            'total': total,
            'rate': round(rate, 6),
            'used_fallback': used_fallback,
        }

    return {
        'team_map_side': team_rates,
        'league_map_side': league_rates,
        'overall_avg': round(overall_avg, 6),
        'min_rounds_threshold': MIN_ROUNDS,
    }


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main(db_path: str, output_path: str):
    print(f'Loading data from {db_path}...')
    rows = load_halves(db_path)
    print(f'  {len(rows)} rows loaded from match_map_halves')

    if not rows:
        print('ERROR: No data found in match_map_halves. Run halves_scraper.py first.')
        sys.exit(1)

    print('Computing win rates...')
    result = compute_rates(rows)

    n_teams = len(set(k.split('|')[0] for k in result['team_map_side']))
    n_maps = len(set(k.split('|')[1] for k in result['team_map_side']))
    n_fallback = sum(1 for v in result['team_map_side'].values() if v['used_fallback'])

    print(f'  Teams: {n_teams}, Maps: {n_maps}')
    print(f'  Team-map-side entries: {len(result["team_map_side"])}')
    print(f'  Entries using fallback (n < {MIN_ROUNDS}): {n_fallback}')
    print(f'  Overall avg rate: {result["overall_avg"]:.4f}')

    print('\nLeague averages by map/side:')
    for key in sorted(result['league_map_side']):
        v = result['league_map_side'][key]
        print(f'  {key:20s}: rate={v["rate"]:.4f}  ({v["wins"]}/{v["total"]} rounds)')

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f'\nSaved to {output_path}')


if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    db_path = os.path.join(project_root, 'data', 'valorant_stats.db')
    output_path = os.path.join(project_root, 'data', 'half_win_rates.json')

    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    if len(sys.argv) > 2:
        output_path = sys.argv[2]

    main(db_path, output_path)
