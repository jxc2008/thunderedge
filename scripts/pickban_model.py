"""
scripts/pickban_model.py

Pick/ban prediction model for VCT BO3 matches.

Predicts the map pool distribution before the veto is announced, enabling
pre-match theo computation as soon as a match is scheduled.

Algorithm:
  1. Load pick/ban history from DB with recency weighting
       current stage = 1.0, previous stage = 0.5, older = excluded
  2. Build per-team weighted tendency tables (ban/pick frequency per map)
  3. For each veto step, blend tendency prior with win-rate score:
       alpha(n) = 0.4 * (1 - exp(-n/3))    <- near-capped at n=4 matches
       score = alpha * tendency + (1-alpha) * win_rate_score
  4. Monte Carlo veto simulation -> P(map pool) distribution
  5. E[theo] = sum over pools of P(pool) * series_theo_no_sides(pool)

Usage (CLI):
    python scripts/pickban_model.py SEN NRG --ask 55 --verbose
    python scripts/pickban_model.py "Sentinels" "NRG Esports" --ask 55

Usage (library):
    from scripts.pickban_model import PickBanModel
    model = PickBanModel(db_path, rates_path)
    result = model.predict('SEN', 'NRG', kalshi_yes_ask=55)
"""

import argparse
import logging
import math
import os
import random
import re
import sqlite3
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

# Resolve paths relative to this file so imports work regardless of cwd
_SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
_WORKTREE_ROOT = os.path.dirname(_SCRIPT_DIR)
_MAIN_REPO    = os.path.normpath(os.path.join(_WORKTREE_ROOT, '..', '..', 'thunderedge'))

sys.path.insert(0, _WORKTREE_ROOT)

from backend.theo_engine import TheoEngine
from backend.team_names import normalise

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

# Current VCT 2026 active map pool (7 maps)
VCT_2026_MAP_POOL = ['Abyss', 'Bind', 'Breeze', 'Corrode', 'Haven', 'Lotus', 'Pearl', 'Split']

# Standard BO3 veto order: (actor_index, action)
# actor_index: 0 = team_a, 1 = team_b
VETO_ORDER = [
    (0, 'ban'),
    (1, 'ban'),
    (0, 'pick'),
    (1, 'pick'),
    (0, 'ban'),
    (1, 'ban'),
    # remaining map = decider
]

# Softmax temperature — controls how deterministic each veto step is.
# Lower: team almost always picks top-scored map.
# Higher: more random, reflects model uncertainty.
SOFTMAX_TEMP = 1.2

N_SIMULATIONS = 10_000

_STAGE_ORDER = {'Kickoff': 0, 'Stage 1': 1, 'Stage 2': 2, 'Stage 3': 3}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _extract_round_key(event_name: str) -> tuple:
    """Return (year, stage_order) for recency sorting."""
    m = re.match(r'VCT (\d{4}).*?(Kickoff|Stage\s+\d+)', event_name or '', re.IGNORECASE)
    if m:
        year  = int(m.group(1))
        stage = re.sub(r'Stage\s+', 'Stage ', m.group(2).strip())
        return (year, _STAGE_ORDER.get(stage, -1))
    return (0, -1)


def _clean_team(raw: str) -> str:
    """
    Strip event suffix from team2 field.

    DB stores team2 as '{team_name} Champions Tour/Vct {year} ...' due to
    a scraping quirk — extract just the team name prefix.

    Examples:
      'Edward Gaming Vct 2026 China Kickoff Lbf' -> 'Edward Gaming'
      'Cloud9 Champions Tour 2025 Americas Kickoff Ur1' -> 'Cloud9'
    """
    m = re.match(r'^(.*?)\s+(?:Champions Tour|Vct)\s+\d{4}', raw, re.IGNORECASE)
    return m.group(1).strip() if m else raw.strip()


def _softmax(scores: List[float], temp: float = SOFTMAX_TEMP) -> List[float]:
    """Softmax with temperature scaling."""
    scaled  = [s / temp for s in scores]
    max_s   = max(scaled)
    exp_s   = [math.exp(s - max_s) for s in scaled]
    total   = sum(exp_s)
    return [e / total for e in exp_s]


def _alpha(n: float) -> float:
    """Tendency weight: concave curve, near-capped at n≈4."""
    return 0.4 * (1.0 - math.exp(-n / 3.0))


# --------------------------------------------------------------------------- #
# PickBanModel
# --------------------------------------------------------------------------- #

class PickBanModel:
    """
    Predicts map pool probabilities for a VCT BO3 before the veto.

    Args:
        db_path:    Path to valorant_stats.db.
        rates_path: Path to half_win_rates.json.
        map_pool:   Override the active map pool list (default: VCT_2026_MAP_POOL).
    """

    def __init__(
        self,
        db_path: str   = os.path.join(_MAIN_REPO, 'data', 'valorant_stats.db'),
        rates_path: str = os.path.join(_WORKTREE_ROOT, 'data', 'half_win_rates.json'),
        map_pool: Optional[List[str]] = None,
    ):
        self.theo      = TheoEngine(rates_path)
        self._db_path  = db_path
        self._map_pool = map_pool or VCT_2026_MAP_POOL
        self._cache: Optional[dict] = None   # tendency cache

    # ------------------------------------------------------------------ #
    # Tendency table
    # ------------------------------------------------------------------ #

    def _load(self) -> dict:
        """
        Build per-team weighted tendency tables from match_pick_bans.

        Returns dict keyed by normalised team abbreviation:
          {
            'n':     effective_appearances (float),
            'alpha': tendency weight,
            'ban':   {map_name: weighted_count},
            'pick':  {map_name: weighted_count},
          }
        """
        conn = sqlite3.connect(self._db_path)
        cur  = conn.cursor()

        # Build event round weights
        cur.execute('SELECT id, event_name FROM vct_events')
        event_rounds = {eid: _extract_round_key(ename) for eid, ename in cur.fetchall()}
        ranked       = sorted(set(event_rounds.values()), reverse=True)
        round_weights = {
            rk: (1.0 if i == 0 else (0.5 if i == 1 else 0.0))
            for i, rk in enumerate(ranked)
        }

        def _w(event_id: int) -> float:
            return round_weights.get(event_rounds.get(event_id, (0, -1)), 0.0)

        cur.execute('''
            SELECT m.team1, m.team2, m.event_id,
                   pb.first_ban, pb.second_ban,
                   pb.first_pick, pb.second_pick
            FROM match_pick_bans pb
            JOIN matches m ON m.id = pb.match_id
            WHERE pb.first_ban IS NOT NULL
        ''')
        rows = cur.fetchall()
        conn.close()

        n    = defaultdict(float)
        ban  = defaultdict(lambda: defaultdict(float))
        pick = defaultdict(lambda: defaultdict(float))

        for raw1, raw2, event_id, fb, sb, fp, sp in rows:
            w = _w(event_id)
            if w == 0.0:
                continue

            t1 = normalise(_clean_team(raw1))
            t2 = normalise(_clean_team(raw2))

            n[t1] += w
            n[t2] += w

            # Standard VCT veto: T1 first_ban, T2 second_ban,
            #                    T1 first_pick, T2 second_pick
            if fb: ban[t1][fb]   += w
            if sb: ban[t2][sb]   += w
            if fp: pick[t1][fp]  += w
            if sp: pick[t2][sp]  += w

        return {
            team: {
                'n':     round(eff_n, 2),
                'alpha': round(_alpha(eff_n), 4),
                'ban':   dict(ban[team]),
                'pick':  dict(pick[team]),
            }
            for team, eff_n in n.items()
        }

    def tendencies(self) -> dict:
        """Return cached tendency tables (lazy-loaded)."""
        if self._cache is None:
            self._cache = self._load()
        return self._cache

    def invalidate_cache(self) -> None:
        """Force reload of tendency tables on next call."""
        self._cache = None

    # ------------------------------------------------------------------ #
    # Score computation
    # ------------------------------------------------------------------ #

    def _win_rate_score(self, team: str, opp: str, map_name: str, action: str) -> float:
        """
        Win-rate based score for ban or pick.

        ban:  opp_winrate - team_winrate  (ban maps where opp is strong / you're weak)
        pick: team_winrate - opp_winrate  (pick your strong maps)

        Win rate = average of atk + def rates.
        """
        def _avg(t: str) -> float:
            rates  = self.theo._team_rates
            league = self.theo._league_rates
            atk = rates.get(f'{t}|{map_name}|atk',
                            league.get(f'{map_name}|atk', {'rate': 0.5}))['rate']
            def_ = rates.get(f'{t}|{map_name}|def',
                             league.get(f'{map_name}|def', {'rate': 0.5}))['rate']
            return (atk + def_) / 2.0

        team_r = _avg(team)
        opp_r  = _avg(opp)
        return (opp_r - team_r) if action == 'ban' else (team_r - opp_r)

    def _score(self, team: str, opp: str, map_name: str, action: str) -> float:
        """Blend tendency prior with win-rate score."""
        wr_score  = self._win_rate_score(team, opp, map_name, action)
        data      = self.tendencies().get(team)

        if not data or data['n'] < 1.0:
            return wr_score

        a    = data['alpha']
        eff  = data['n']
        freq = data['ban'] if action == 'ban' else data['pick']
        tendency = freq.get(map_name, 0.0) / eff   # normalised frequency [0, 1]

        return a * tendency + (1.0 - a) * wr_score

    # ------------------------------------------------------------------ #
    # Veto simulation
    # ------------------------------------------------------------------ #

    def simulate_veto(
        self,
        team_a: str,
        team_b: str,
        n_sims: int = N_SIMULATIONS,
    ) -> Dict[Tuple[str, str, str], float]:
        """
        Monte Carlo simulation of the BO3 veto.

        Returns:
            {(pick_1, pick_2, decider): probability}
            Sorted descending by probability.
        """
        teams   = [team_a, team_b]
        pool    = list(self._map_pool)
        counts: Dict[Tuple[str, str, str], int] = defaultdict(int)

        for _ in range(n_sims):
            available = list(pool)
            picks: List[str] = []

            for actor_idx, action in VETO_ORDER:
                actor = teams[actor_idx]
                opp   = teams[1 - actor_idx]

                scores = [self._score(actor, opp, m, action) for m in available]
                probs  = _softmax(scores)

                # Weighted random sample
                r, cumulative = random.random(), 0.0
                chosen = available[-1]
                for i, p in enumerate(probs):
                    cumulative += p
                    if r <= cumulative:
                        chosen = available[i]
                        break

                if action == 'pick':
                    picks.append(chosen)
                available.remove(chosen)

            decider = available[0]
            counts[(picks[0], picks[1], decider)] += 1

        total = n_sims
        return dict(
            sorted(
                {k: v / total for k, v in counts.items()}.items(),
                key=lambda x: -x[1],
            )
        )

    # ------------------------------------------------------------------ #
    # Expected theo
    # ------------------------------------------------------------------ #

    def predict(
        self,
        team_a: str,
        team_b: str,
        kalshi_yes_ask: int,
        n_sims: int = N_SIMULATIONS,
        top_n: int = 10,
    ) -> dict:
        """
        Predict map pool distribution and compute expected pre-veto theo.

        Args:
            team_a:          Team A abbreviation (Kalshi YES side).
            team_b:          Team B abbreviation.
            kalshi_yes_ask:  Current Kalshi YES ask price in cents.
            n_sims:          Monte Carlo sample count.
            top_n:           Number of top map pools to include in output.

        Returns:
            {
                'expected_theo':      float,
                'model_confidence':   'HIGH'|'MED'|'LOW',
                'data_weight':        float,
                'top_pools':          [{maps, prob, theo, data_w}, ...],
                'team_a_data':        {n, alpha},
                'team_b_data':        {n, alpha},
            }
        """
        distribution = self.simulate_veto(team_a, team_b, n_sims)

        expected_theo = 0.0
        expected_dw   = 0.0
        top_pools     = []

        for maps, prob in distribution.items():
            theo, data_w, _ = self.theo.series_theo_no_sides(
                team_a, team_b, list(maps), kalshi_yes_ask
            )
            expected_theo += prob * theo
            expected_dw   += prob * data_w
            top_pools.append({
                'maps':   maps,
                'prob':   round(prob, 4),
                'theo':   round(theo, 4),
                'data_w': round(data_w, 3),
            })

        top_pools = sorted(top_pools, key=lambda x: -x['prob'])[:top_n]

        conf = ('HIGH' if expected_dw >= 0.8
                else ('MED' if expected_dw >= 0.4 else 'LOW'))

        td = self.tendencies()
        return {
            'expected_theo':    round(expected_theo, 4),
            'model_confidence': conf,
            'data_weight':      round(expected_dw, 3),
            'top_pools':        top_pools,
            'team_a_data':      {k: td.get(team_a, {}).get(k, 0) for k in ('n', 'alpha')},
            'team_b_data':      {k: td.get(team_b, {}).get(k, 0) for k in ('n', 'alpha')},
        }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(
        description='Pick/ban prediction model — VCT BO3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('team_a', help='Team A (Kalshi YES side) — name or abbreviation')
    parser.add_argument('team_b', help='Team B — name or abbreviation')
    parser.add_argument('--ask',   type=int, default=50, metavar='CENTS',
                        help='Kalshi YES ask price in cents (default: 50)')
    parser.add_argument('--db',    default=None, metavar='PATH',
                        help='Path to valorant_stats.db')
    parser.add_argument('--rates', default=None, metavar='PATH',
                        help='Path to half_win_rates.json')
    parser.add_argument('--maps',  nargs='+', metavar='MAP',
                        help='Override map pool (default: VCT 2026 pool)')
    parser.add_argument('--sims',  type=int, default=N_SIMULATIONS,
                        help=f'Monte Carlo iterations (default: {N_SIMULATIONS})')
    parser.add_argument('--top',   type=int, default=8,
                        help='Top N map pools to show (default: 8)')
    parser.add_argument('--tendencies', action='store_true',
                        help='Print raw tendency tables for both teams')
    parser.add_argument('--json', action='store_true',
                        help='Output result as JSON (for API consumption)')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format='%(levelname)s  %(message)s',
    )

    db_path    = args.db    or os.path.join(_MAIN_REPO, 'data', 'valorant_stats.db')
    rates_path = args.rates or os.path.join(_WORKTREE_ROOT, 'data', 'half_win_rates.json')

    model  = PickBanModel(db_path=db_path, rates_path=rates_path, map_pool=args.maps)
    team_a = normalise(args.team_a)
    team_b = normalise(args.team_b)

    if args.json:
        import json as _json
        result = model.predict(team_a, team_b, args.ask, n_sims=args.sims, top_n=args.top)
        # Make top_pools serialisable (tuples → lists)
        for p in result['top_pools']:
            p['maps'] = list(p['maps'])
        print(_json.dumps(result))
        return

    if args.tendencies:
        td = model.tendencies()
        for t in (team_a, team_b):
            d = td.get(t)
            if not d:
                print(f'{t}: no pick/ban data')
                continue
            print(f'\n{t}  n={d["n"]}  alpha={d["alpha"]}')
            ban_sorted  = sorted(d['ban'].items(),  key=lambda x: -x[1])
            pick_sorted = sorted(d['pick'].items(), key=lambda x: -x[1])
            print(f'  Bans:  { {m: round(c/d["n"]*100) for m, c in ban_sorted} }')
            print(f'  Picks: { {m: round(c/d["n"]*100) for m, c in pick_sorted} }')

    result = model.predict(team_a, team_b, args.ask, n_sims=args.sims, top_n=args.top)

    print(f'\nPick/Ban Prediction: {team_a} vs {team_b}')
    print(f'Kalshi YES ask:      {args.ask}c')
    print(f'Expected theo:       {result["expected_theo"]:.3f}  ({result["expected_theo"]*100:.1f}c)')
    print(f'Confidence:          {result["model_confidence"]}  (data_w={result["data_weight"]:.3f})')

    ta, tb = result['team_a_data'], result['team_b_data']
    print(f'  {team_a}: n={ta["n"]}, alpha={ta["alpha"]}')
    print(f'  {team_b}: n={tb["n"]}, alpha={tb["alpha"]}')

    print(f'\nTop predicted map pools (of {len(result["top_pools"])} shown):')
    print(f'  {"Prob":>6}  {"Pick 1":<12} {"Pick 2":<12} {"Decider":<12}  Theo   dw')
    print(f'  {"":->6}  {"":->12} {"":->12} {"":->12}  {"":->5}  {"":->4}')
    for p in result['top_pools']:
        m1, m2, dec = p['maps']
        print(f'  {p["prob"]*100:5.1f}%  {m1:<12} {m2:<12} {dec:<12}  '
              f'{p["theo"]:.3f}  {p["data_w"]:.2f}')

    edge = result['expected_theo'] - args.ask / 100.0
    arrow = '>>' if abs(edge) >= 0.05 else ('>' if abs(edge) >= 0.02 else '~')
    side  = 'BUY YES' if edge > 0 else 'BUY NO'
    print(f'\nEdge vs ask: {edge:+.3f} ({edge*100:+.1f}c)  {arrow}  {side}')


if __name__ == '__main__':
    main()
