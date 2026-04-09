# scripts/validate_theo.py
"""
Validate the TheoEngine against historical match outcomes.

For each map in match_map_halves:
  1. Look up the actual map outcome from player_map_stats (map_score = 'X-Y').
  2. Compute P(team1 wins map) using TheoEngine.
  3. Compare predicted probability to actual outcome.
  4. Report Brier score and log loss vs. naive 0.5 baseline.

The team identity problem:
  - match_map_halves stores team abbreviations (e.g. 'SEN', 'G2') scraped from VLR.
  - player_map_stats stores map_score as 'team1_score-team2_score' (team1 = left team in slug).
  - matches.match_url encodes the slug: /{vlr_id}/{team1slug}-vs-{team2slug}-{event}
  - We determine which halves team is 'team1' by checking which abbreviation corresponds
    to the first team in the URL slug.

We skip maps where team identity cannot be resolved.
"""

import json
import math
import os
import re
import sqlite3
import sys
from typing import Optional

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)

DB_PATH = os.path.join(project_root, 'data', 'valorant_stats.db')
RATES_PATH = os.path.join(project_root, 'data', 'half_win_rates.json')

# --------------------------------------------------------------------------- #
# Team slug → abbreviation mapping
# Built from observed VLR economy page scrapes (abbreviation is from the page itself)
# --------------------------------------------------------------------------- #

_SLUG_TO_ABBR = {
    'evil-geniuses': 'EG',
    'loud': 'LOUD',
    'mibr': 'MIBR',
    '100-thieves': '100T',
    '2game-esports': '2G',
    'furia': 'FUR',
    'nrg-esports': 'NRG',
    'cloud9': 'C9',
    'kr-esports': 'KR',
    'sentinels': 'SEN',
    'leviat-n': 'LEV',
    'g2-esports': 'G2',
    # EMEA
    'team-liquid': 'TL',
    'koi': 'KOI',
    'karmine-corp': 'KC',
    'natus-vincere': 'NAVI',
    'bbl-esports': 'BBL',
    'giantx': 'GX',
    'apeks': 'APX',
    'gentle-mates': 'GM',
    'fut-esports': 'FUT',
    'team-vitality': 'VIT',
    'fnatic': 'FNC',
    'team-heretics': 'TH',
    # Pacific
    'paper-rex': 'PRX',
    'drx': 'DRX',
    'talon-esports': 'TLN',
    'bleed-esports': 'BLEED',
    'nongshim-redforce': 'NS',
    'geng': 'GEN',
    'rex-regum-qeon': 'RRQ',
    'boom-esports': 'BOOM',
    'global-esports': 'GE',
    'team-secret': 'TS',
    'zeta-division': 'ZETA',
}

# Also try the inverse: normalise abbreviations found on the page.
# Some teams appear as e.g. 'KR\ufffd' due to encoding; normalise them.
_ABBR_NORMALISE = {
    'KR\ufffd': 'KR',
    'KR?': 'KR',
}


def _normalise_abbr(abbr: str) -> str:
    return _ABBR_NORMALISE.get(abbr, abbr)


def _slug_from_url(match_url: str) -> Optional[tuple]:
    """
    Extract (team1_slug, team2_slug) from a match URL like:
      /427991/evil-geniuses-vs-loud-champions-tour-2025-americas-kickoff-ur1
    Returns None if parsing fails.
    """
    m = re.match(r'/\d+/(.+)', match_url)
    if not m:
        return None
    slug = m.group(1)
    # Split on -vs-
    parts = slug.split('-vs-', 1)
    if len(parts) < 2:
        return None
    team1_slug = parts[0]

    # team2 slug is the start of parts[1] up to where the event name begins.
    # We identify the team2 slug by matching against known slugs.
    remaining = parts[1]
    best_match = None
    best_len = 0
    for known_slug in _SLUG_TO_ABBR:
        if remaining.startswith(known_slug):
            if len(known_slug) > best_len:
                best_len = len(known_slug)
                best_match = known_slug

    # Fallback: take everything up to the first word that looks like an event keyword
    if best_match is None:
        event_keywords = ['champions', 'vct', 'masters', 'lock', 'kickoff', 'stage',
                          'emea', 'americas', 'pacific', 'china']
        words = remaining.split('-')
        slug_words = []
        for w in words:
            if w.lower() in event_keywords:
                break
            slug_words.append(w)
        if slug_words:
            best_match = '-'.join(slug_words)

    return (team1_slug, best_match) if best_match else None


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #

def load_validation_data(db_path: str) -> list:
    """
    Returns a list of dicts, one per (match_id, map_number) combination where:
      - match_map_halves data exists (for both teams)
      - player_map_stats has a map_score for that match/map
      - We can identify which team is team1 vs team2

    Each dict:
      {match_id, map_number, map_name,
       team1_abbr, team2_abbr,   # abbreviations from halves data
       team1_score, team2_score, # from map_score
       team1_wins}               # bool: True if team1 won the map
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. Get all maps with halves data (need both teams per map)
    cur.execute('''
        SELECT match_id, map_number, map_name,
               GROUP_CONCAT(team_name) as teams,
               SUM(atk_rounds_won) as total_atk,
               SUM(def_rounds_won) as total_def
        FROM match_map_halves
        WHERE map_name IS NOT NULL
        GROUP BY match_id, map_number
        HAVING COUNT(DISTINCT team_name) = 2
    ''')
    halves_maps = {}
    for row in cur.fetchall():
        match_id, map_num, map_name, teams, total_atk, total_def = row
        halves_maps[(match_id, map_num)] = {
            'map_name': map_name,
            'teams': set(teams.split(',')),
        }

    # 2. Get per-team halves data
    cur.execute('''
        SELECT match_id, map_number, team_name, atk_rounds_won, def_rounds_won, total_rounds
        FROM match_map_halves
        WHERE map_name IS NOT NULL
    ''')
    team_halves = {}
    for row in cur.fetchall():
        match_id, map_num, team_name, atk_won, def_won, total = row
        team_halves[(match_id, map_num, team_name)] = {
            'atk_rounds_won': atk_won,
            'def_rounds_won': def_won,
            'total_rounds': total,
        }

    # 3. Get map scores from player_map_stats (one row per player; take distinct per match/map)
    cur.execute('''
        SELECT DISTINCT match_id, map_number, map_score
        FROM player_map_stats
        WHERE map_score IS NOT NULL AND map_score != ''
    ''')
    map_scores = {}
    for match_id, map_num, score_str in cur.fetchall():
        map_scores[(match_id, map_num)] = score_str

    # 4. Get match URLs to extract team slugs
    cur.execute('SELECT id, match_url FROM matches')
    match_urls = {row[0]: row[1] for row in cur.fetchall()}

    conn.close()

    # 5. Build validation records
    records = []
    skipped = 0

    for (match_id, map_num), map_info in halves_maps.items():
        map_name = map_info['map_name']
        teams = list(map_info['teams'])

        # Get score
        score_str = map_scores.get((match_id, map_num))
        if not score_str:
            skipped += 1
            continue

        m = re.match(r'^(\d+)-(\d+)$', score_str.strip())
        if not m:
            skipped += 1
            continue
        score_left, score_right = int(m.group(1)), int(m.group(2))

        # Determine which abbreviation = team1 (left team in score)
        match_url = match_urls.get(match_id, '')
        slugs = _slug_from_url(match_url)
        if not slugs:
            skipped += 1
            continue
        team1_slug, team2_slug = slugs

        team1_abbr_from_slug = _SLUG_TO_ABBR.get(team1_slug)
        team2_abbr_from_slug = _SLUG_TO_ABBR.get(team2_slug)

        # Normalise team abbreviations from halves data
        teams_norm = [_normalise_abbr(t) for t in teams]

        # Try to assign team1/team2 based on slug lookup
        if team1_abbr_from_slug and team2_abbr_from_slug:
            if team1_abbr_from_slug in teams_norm and team2_abbr_from_slug in teams_norm:
                team1_abbr = team1_abbr_from_slug
                team2_abbr = team2_abbr_from_slug
            else:
                skipped += 1
                continue
        else:
            # Fall back: can't determine ordering; skip
            skipped += 1
            continue

        # Map team abbr back to original (un-normalised) form for DB lookup
        def _orig_abbr(abbr):
            # Find the original (possibly un-normalised) key in teams
            for t in teams:
                if _normalise_abbr(t) == abbr:
                    return t
            return abbr

        t1_orig = _orig_abbr(team1_abbr)
        t2_orig = _orig_abbr(team2_abbr)

        # Validate that we have halves data for both
        if (match_id, map_num, t1_orig) not in team_halves:
            skipped += 1
            continue
        if (match_id, map_num, t2_orig) not in team_halves:
            skipped += 1
            continue

        team1_wins = score_left > score_right

        records.append({
            'match_id': match_id,
            'map_number': map_num,
            'map_name': map_name,
            'team1_abbr': team1_abbr,   # normalised
            'team2_abbr': team2_abbr,   # normalised
            't1_orig': t1_orig,          # as in halves table
            't2_orig': t2_orig,
            'team1_score': score_left,
            'team2_score': score_right,
            'team1_wins': team1_wins,
        })

    print(f'Loaded {len(records)} validation samples ({skipped} skipped due to missing data)')
    return records


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

def brier_score(probs: list, outcomes: list) -> float:
    """Mean squared error between predicted probabilities and binary outcomes."""
    n = len(probs)
    return sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / n


def log_loss(probs: list, outcomes: list, eps: float = 1e-7) -> float:
    """Cross-entropy loss."""
    n = len(probs)
    total = 0.0
    for p, o in zip(probs, outcomes):
        p_clamp = max(eps, min(1 - eps, p))
        total += o * math.log(p_clamp) + (1 - o) * math.log(1 - p_clamp)
    return -total / n


def calibration_buckets(probs: list, outcomes: list, n_buckets: int = 5) -> list:
    """
    Return calibration data: list of (bucket_centre, mean_pred, mean_actual, count).
    """
    bucket_size = 1.0 / n_buckets
    buckets = [[] for _ in range(n_buckets)]
    for p, o in zip(probs, outcomes):
        idx = min(int(p / bucket_size), n_buckets - 1)
        buckets[idx].append((p, o))

    result = []
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        centre = (i + 0.5) * bucket_size
        mean_pred = sum(b[0] for b in bucket) / len(bucket)
        mean_actual = sum(b[1] for b in bucket) / len(bucket)
        result.append((centre, mean_pred, mean_actual, len(bucket)))
    return result


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    print('Loading rates...')
    if not os.path.exists(RATES_PATH):
        print(f'ERROR: {RATES_PATH} not found. Run scripts/half_win_rate_model.py first.')
        sys.exit(1)

    sys.path.insert(0, project_root)
    from backend.theo_engine import TheoEngine
    engine = TheoEngine(RATES_PATH)

    print('Loading validation data...')
    records = load_validation_data(DB_PATH)

    if not records:
        print('No validation samples found.')
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Compute predictions
    # ------------------------------------------------------------------ #
    theo_probs = []
    actuals = []
    baseline_probs = []
    skipped_pred = 0

    per_map_results = {}  # map_name -> [(pred, actual)]

    for rec in records:
        try:
            # We don't know which side each team started on, so we average
            # P(team1 wins | team1 starts atk) and P(team1 wins | team1 starts def)
            # This is a reasonable approach when side info isn't available.
            p_atk = engine.map_win_prob(
                rec['t1_orig'], rec['t2_orig'], rec['map_name'], 'atk'
            )
            p_def = engine.map_win_prob(
                rec['t1_orig'], rec['t2_orig'], rec['map_name'], 'def'
            )
            p = (p_atk + p_def) / 2.0
        except Exception as e:
            skipped_pred += 1
            continue

        outcome = 1.0 if rec['team1_wins'] else 0.0
        theo_probs.append(p)
        actuals.append(outcome)
        baseline_probs.append(0.5)

        key = rec['map_name']
        if key not in per_map_results:
            per_map_results[key] = []
        per_map_results[key].append((p, outcome))

    n = len(theo_probs)
    print(f'\nEvaluating on {n} map predictions ({skipped_pred} skipped due to prediction error)\n')

    if n == 0:
        print('No predictions could be computed.')
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Overall metrics
    # ------------------------------------------------------------------ #
    theo_bs = brier_score(theo_probs, actuals)
    base_bs = brier_score(baseline_probs, actuals)
    theo_ll = log_loss(theo_probs, actuals)
    base_ll = log_loss(baseline_probs, actuals)

    print('=' * 60)
    print(f'  Theo engine  Brier score: {theo_bs:.4f}  vs  baseline (0.5/0.5): {base_bs:.4f}')
    print(f'  Theo engine  Log loss:    {theo_ll:.4f}  vs  baseline:            {base_ll:.4f}')
    bs_improvement = (base_bs - theo_bs) / base_bs * 100
    print(f'  Brier score improvement over baseline: {bs_improvement:+.1f}%')
    print('=' * 60)

    # ------------------------------------------------------------------ #
    # Per-map breakdown
    # ------------------------------------------------------------------ #
    print('\nPer-map Brier score:')
    for map_name in sorted(per_map_results):
        preds, acts = zip(*per_map_results[map_name])
        bs = brier_score(list(preds), list(acts))
        n_map = len(preds)
        print(f'  {map_name:12s}: Brier={bs:.4f}  (n={n_map})')

    # ------------------------------------------------------------------ #
    # Calibration
    # ------------------------------------------------------------------ #
    print('\nCalibration (predicted prob vs actual win rate):')
    print(f'  {"Bucket":>8}  {"Mean Pred":>10}  {"Actual WR":>10}  {"Count":>6}')
    cal = calibration_buckets(theo_probs, actuals, n_buckets=5)
    for centre, mean_pred, mean_actual, count in cal:
        diff = mean_actual - mean_pred
        print(f'  {centre:>8.2f}  {mean_pred:>10.4f}  {mean_actual:>10.4f}  {count:>6}  (diff={diff:+.4f})')

    # ------------------------------------------------------------------ #
    # Sample predictions
    # ------------------------------------------------------------------ #
    print('\nSample predictions (first 10):')
    print(f'  {"Match":>7}  {"Map":>5}  {"Map Name":>12}  {"T1":>6}  {"T2":>6}  '
          f'{"Score":>8}  {"Pred":>6}  {"Outcome":>7}')
    for rec, p in zip(records[:10], theo_probs[:10]):
        outcome_str = 'T1 WIN' if rec['team1_wins'] else 'T2 WIN'
        score_str = f"{rec['team1_score']}-{rec['team2_score']}"
        print(f'  {rec["match_id"]:>7}  {rec["map_number"]:>5}  {rec["map_name"]:>12}  '
              f'{rec["t1_orig"]:>6}  {rec["t2_orig"]:>6}  '
              f'{score_str:>8}  {p:>6.3f}  {outcome_str:>7}')


if __name__ == '__main__':
    main()
