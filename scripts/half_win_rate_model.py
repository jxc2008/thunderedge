# scripts/half_win_rate_model.py
"""
Compute per-(team, map, side) win rates from match_map_halves and write
to data/half_win_rates.json.

Event-based recency weighting:
  - The two most recent events (by latest match date) are included.
  - Current event rounds are weighted 1.0; previous event rounds 0.5.
  - Older events are excluded entirely.
  - New maps that only exist in the current event have no prior data and
    fall back to the current-event league average for that map/side.

Wilson score confidence intervals are used to smooth small samples.
If a team has fewer than MIN_ROUNDS *effective* rounds on a given
(map, side), the model falls back to the league-average rate for that
(map, side).
"""

import json
import math
import os
import re
import sqlite3
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

MIN_ROUNDS = 15          # fall back to league average below this threshold (effective rounds)
WILSON_Z = 1.645         # 90% confidence interval (one-tailed)
CURRENT_EVENT_WEIGHT = 1.0
PREV_EVENT_WEIGHT    = 0.5

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

_STAGE_ORDER = {'Kickoff': 0, 'Stage 1': 1, 'Stage 2': 2, 'Stage 3': 3}


def _extract_round_key(event_name: str) -> tuple:
    """
    Extract a (year, stage_order) sort key from an event name.

    VCT season order within a year: Kickoff(0) → Stage 1(1) → Stage 2(2)
    Higher stage_order = later in the season = more recent data.

    Examples:
      'VCT 2026: Americas Stage 1'  → (2026, 1)
      'VCT 2026: EMEA Kickoff'      → (2026, 0)
      'VCT 2025: Pacific Stage 2'   → (2025, 2)
    """
    m = re.match(r'VCT (\d{4}).*?(Kickoff|Stage\s+\d+)', event_name)
    if m:
        year = int(m.group(1))
        stage = m.group(2).strip()
        order = _STAGE_ORDER.get(stage, -1)
        return (year, order)
    return (0, -1)  # fallback: sorts last


def _round_label(key: tuple) -> str:
    year, order = key
    stage = {v: k for k, v in _STAGE_ORDER.items()}.get(order, str(order))
    return f'{year}|{stage}'


def detect_event_weights(conn: sqlite3.Connection) -> Dict[int, float]:
    """
    Auto-detect the two most recent event rounds and assign weights.

    VCT runs 4 concurrent regional events per stage (Americas/EMEA/Pacific/China).
    We group these into 'rounds' (e.g. '2026|Kickoff', '2025|Stage 2') so all
    regions of the same stage share the same weight tier.

    Round ranking: by MAX(e.id) within the round (higher id = newer), using
    e.id as a proxy for recency when match_date is NULL.

    Weights: current round = 1.0, previous round = 0.5, older = excluded.
    Only rounds that have at least one event with scraped halves data are included.

    Returns: {event_id: weight}
    """
    cur = conn.cursor()

    # Fetch events that have scraped halves data
    cur.execute('''
        SELECT DISTINCT e.id, e.event_name
        FROM vct_events e
        JOIN matches m ON m.event_id = e.id
        JOIN match_map_halves h ON h.match_id = m.id
    ''')
    events = cur.fetchall()

    if not events:
        return {}

    # Group by (year, stage_order) round key
    from collections import defaultdict as _dd
    round_to_ids: Dict[tuple, list] = _dd(list)
    for eid, ename in events:
        rk = _extract_round_key(ename)
        round_to_ids[rk].append(eid)

    # Rank rounds by (year DESC, stage_order DESC) — most recent season stage first
    ranked_rounds = sorted(round_to_ids.keys(), reverse=True)

    weights: Dict[int, float] = {}
    for rank, rk in enumerate(ranked_rounds):
        if rank == 0:
            w = CURRENT_EVENT_WEIGHT
            print(f'  Round detected as CURRENT ({_round_label(rk)}):')
        elif rank == 1:
            w = PREV_EVENT_WEIGHT
            print(f'  Round detected as PREVIOUS ({_round_label(rk)}):')
        else:
            w = 0.0
        for eid in round_to_ids[rk]:
            weights[eid] = w

    # Log which rounds were selected
    cur.execute(
        'SELECT id, event_name FROM vct_events WHERE id IN ({})'.format(
            ','.join('?' * len(weights))
        ),
        list(weights.keys()),
    )
    for eid, ename in sorted(cur.fetchall(), key=lambda r: weights[r[0]], reverse=True):
        w = weights[eid]
        if w > 0:
            label = 'CURRENT' if w == CURRENT_EVENT_WEIGHT else 'PREVIOUS'
            print(f'  [{label} weight={w}] {ename} (id={eid})')

    return weights


def load_halves(db_path: str,
                event_weights: Dict[int, float] = None) -> List[dict]:
    """
    Return rows from match_map_halves with a 'weight' field attached.

    If event_weights is None, it is auto-detected from the DB (two most
    recent events). Rows belonging to excluded events (weight=0) are
    dropped.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if event_weights is None:
        print('Auto-detecting event weights...')
        event_weights = detect_event_weights(conn)

    cur = conn.cursor()
    cur.execute('''
        SELECT h.match_id, h.map_number, h.map_name, h.team_name,
               h.atk_rounds_won, h.def_rounds_won, h.total_rounds,
               m.event_id
        FROM match_map_halves h
        JOIN matches m ON m.id = h.match_id
        WHERE h.map_name IS NOT NULL AND h.map_name != ""
    ''')
    raw = cur.fetchall()
    conn.close()

    rows = []
    for r in raw:
        eid = r['event_id']
        w = event_weights.get(eid, 0.0)
        if w == 0.0:
            continue
        rows.append({
            'match_id':      r['match_id'],
            'map_number':    r['map_number'],
            'map_name':      r['map_name'],
            'team_name':     r['team_name'],
            'atk_rounds_won': r['atk_rounds_won'],
            'def_rounds_won': r['def_rounds_won'],
            'total_rounds':  r['total_rounds'],
            'event_id':      eid,
            'weight':        w,
        })
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
        team     = row['team_name']
        map_name = row['map_name']
        total    = row['total_rounds']
        w        = row.get('weight', 1.0)   # recency weight (1.0 current, 0.5 prev event)

        # Each team plays ~half the rounds on attack, half on defense.
        # atk_total ≈ total // 2 is a robust estimate (±1 for OT).
        atk_total = max(1, total // 2)
        def_total = max(1, total - atk_total)

        # Weighted accumulation: treat w*rounds as effective sample size.
        team_stats[(team, map_name, 'atk')][0] += w * row['atk_rounds_won']
        team_stats[(team, map_name, 'atk')][1] += w * atk_total
        team_stats[(team, map_name, 'def')][0] += w * row['def_rounds_won']
        team_stats[(team, map_name, 'def')][1] += w * def_total

        # League averages use the same weighting so current-event maps
        # don't get polluted by old-meta data for the fallback either.
        league_stats[(map_name, 'atk')][0] += w * row['atk_rounds_won']
        league_stats[(map_name, 'atk')][1] += w * atk_total
        league_stats[(map_name, 'def')][0] += w * row['def_rounds_won']
        league_stats[(map_name, 'def')][1] += w * def_total

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

    # Track which maps are present — useful for detecting new maps with no prior data
    maps_in_data = sorted({k.split('|')[1] for k in team_rates})

    return {
        'team_map_side': team_rates,
        'league_map_side': league_rates,
        'overall_avg': round(overall_avg, 6),
        'min_rounds_threshold': MIN_ROUNDS,
        'maps_in_data': maps_in_data,
        'event_weights': {
            'current': CURRENT_EVENT_WEIGHT,
            'previous': PREV_EVENT_WEIGHT,
            'note': 'Effective sample sizes are weighted; current event counts fully, previous event at 0.5x',
        },
    }


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main(db_path: str, output_path: str):
    print(f'Loading data from {db_path}...')
    rows = load_halves(db_path)   # auto-detects the two most recent events
    print(f'  {len(rows)} weighted rows loaded from match_map_halves')

    if not rows:
        print('ERROR: No data found in match_map_halves. Run halves_scraper.py first.')
        sys.exit(1)

    print('Computing win rates...')
    result = compute_rates(rows)

    n_teams = len(set(k.split('|')[0] for k in result['team_map_side']))
    n_maps = len(set(k.split('|')[1] for k in result['team_map_side']))
    n_fallback = sum(1 for v in result['team_map_side'].values() if v['used_fallback'])

    print(f'  Teams: {n_teams}, Maps: {n_maps}')
    print(f'  Maps in data: {", ".join(result["maps_in_data"])}')
    print(f'  Team-map-side entries: {len(result["team_map_side"])}')
    print(f'  Entries using fallback (eff. n < {MIN_ROUNDS}): {n_fallback}')
    print(f'  Overall avg rate: {result["overall_avg"]:.4f}')
    print(f'  Weighting: current event={CURRENT_EVENT_WEIGHT}x, previous event={PREV_EVENT_WEIGHT}x')

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
