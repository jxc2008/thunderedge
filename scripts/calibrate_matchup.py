#!/usr/bin/env python3
"""
Calibrate matchup adjustment constants (alpha_strength, beta_mismatch, gamma_mismatch)
from historical player kill data joined with team betting odds.

Methodology:
  1. Join player_map_stats → matches → moneyline_matches (via match_url)
     + player_event_stats (for team assignment)
  2. Build per-player expanding-window baseline μ (leave-future-out)
  3. Optimize α, β, γ via Poisson maximum-likelihood on a 70% train split
  4. Evaluate and compare against no-adjustment and current-defaults baselines
  5. Optionally update backend/matchup_adjust.py with the optimized values

Run:
    python scripts/calibrate_matchup.py
"""

import sys
import os
import sqlite3
import re
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from scipy import stats as scipy_stats
from scipy.optimize import minimize

from backend.matchup_adjust import apply_matchup_adjustment, infer_team_win_probability
from backend.model_params import compute_distribution_params, compute_weighted_mean
from config import Config

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIN_PRIOR_MAPS = 10          # min maps before a row for a reliable rolling μ
CURRENT_DEFAULTS = (0.22, 0.18, 1.8)
BOUNDS = [(0.0, 0.60), (0.0, 0.50), (0.5, 4.0)]
TRAIN_SPLIT_FRACTION = 0.70
LOW_CONFIDENCE_THRESHOLD = 200   # warn if calibration set is below this


# ---------------------------------------------------------------------------
# Name normalization (mirrors moneyline_analytics.py)
# ---------------------------------------------------------------------------
_PUNCT = re.compile(r'[^\w\s]')

def normalize_team_name(name: str) -> str:
    if not name or not str(name).strip():
        return ''
    s = str(name).strip().lower()
    s = re.sub(r'\s+(vct|champions tour|valorant champions|champions\s+\d{4}|masters|ewc)\s+.*$', '', s, flags=re.I)
    s = re.sub(r'\s+(gf|lr\d+|ur\d+|mr\d+|ubqf?|lbr\d+|mbf?|decider\s*[a-z]?|elim\s*[a-z]?|w\d+)\s*$', '', s, flags=re.I)
    s = _PUNCT.sub('', s)
    s = ' '.join(s.split())
    return s


def teams_match(a: str, b: str) -> bool:
    na, nb = normalize_team_name(a), normalize_team_name(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


# ---------------------------------------------------------------------------
# Step 1: Build raw calibration rows from DB
# ---------------------------------------------------------------------------
def build_raw_rows(db_path: str) -> list:
    """
    Returns (rows, team_lookup).

    rows: list of dicts with player_name, kills, match_url, event_id,
          match_team1, match_team2, team1_odds, team2_odds.

    team_lookup: dict of player_name_lower -> team (full name, from players table).
    Uses players.team (full names like 'Cloud9', 'Sentinels') so it can be
    substring-matched against matches.team1/team2 which also use full names.
    Falls back to player_event_stats.team for players not in the players table.
    """
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT
                pms.player_name,
                pms.kills,
                pms.map_name,
                m.match_url,
                m.event_id,
                m.team1  AS match_team1,
                m.team2  AS match_team2,
                mm.team1_odds,
                mm.team2_odds
            FROM player_map_stats pms
            JOIN matches m            ON pms.match_id = m.id
            JOIN moneyline_matches mm  ON m.match_url = mm.match_url
            WHERE pms.kills > 0
              AND mm.team1_odds IS NOT NULL
              AND mm.team2_odds IS NOT NULL
              AND mm.team1_odds > 1.0
              AND mm.team2_odds > 1.0
            ORDER BY m.event_id, pms.player_name
        """)
        cols = ['player_name', 'kills', 'map_name', 'match_url', 'event_id',
                'match_team1', 'match_team2', 'team1_odds', 'team2_odds']
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

        # Primary: players table (full team names — best for substring matching)
        cursor.execute("SELECT LOWER(ign), team FROM players WHERE team IS NOT NULL AND team != ''")
        team_lookup = {row[0]: row[1] for row in cursor.fetchall()}

        # Fallback: player_event_stats (abbreviated, but useful if not in players table)
        cursor.execute("SELECT LOWER(player_name), team FROM player_event_stats WHERE team IS NOT NULL AND team != ''")
        for pname, team in cursor.fetchall():
            if pname not in team_lookup:
                team_lookup[pname] = team

        return rows, team_lookup
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Step 2: Assign team win probability to each row
# ---------------------------------------------------------------------------
def assign_team_win_prob(rows: list, team_lookup: dict) -> tuple:
    """
    Returns (clean_rows, stats_dict).
    clean_rows: rows with 'team_win_prob' added (direction-aware).
    team_lookup: player_name_lower -> full team name (from players table).
    Drops rows where team assignment cannot be determined.
    """
    clean = []
    stats = {
        'total_input': len(rows),
        'dropped_no_odds': 0,
        'dropped_no_team': 0,
        'dropped_team_mismatch': 0,
        'kept': 0,
    }

    for r in rows:
        o1, o2 = r['team1_odds'], r['team2_odds']
        if not o1 or not o2 or o1 <= 1.0 or o2 <= 1.0:
            stats['dropped_no_odds'] += 1
            continue

        # Get player team from flat lookup (player_name -> team)
        player_team = team_lookup.get(r['player_name'].lower())
        if not player_team:
            stats['dropped_no_team'] += 1
            continue

        # Match player team against match teams
        if teams_match(player_team, r['match_team1']):
            t_odds, opp_odds = o1, o2
        elif teams_match(player_team, r['match_team2']):
            t_odds, opp_odds = o2, o1
        else:
            stats['dropped_team_mismatch'] += 1
            continue

        # Compute vig-free probability
        try:
            info = infer_team_win_probability(team_odds=t_odds, opp_odds=opp_odds)
            p_win = info['team_win_prob']
        except Exception:
            stats['dropped_team_mismatch'] += 1
            continue

        row = dict(r)
        row['team_win_prob'] = p_win
        row['player_team'] = player_team
        clean.append(row)
        stats['kept'] += 1

    return clean, stats


# ---------------------------------------------------------------------------
# Step 2b: Load full kill history for all players from the whole DB
# ---------------------------------------------------------------------------
def load_full_kill_history(db_path: str) -> dict:
    """
    Returns dict: player_name_lower -> sorted list of (event_id, kills).
    Uses ALL player_map_stats rows (not just those with odds), so the rolling
    baseline has the maximum possible historical context.
    """
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT LOWER(pms.player_name), m.event_id, pms.kills
            FROM player_map_stats pms
            JOIN matches m ON pms.match_id = m.id
            WHERE pms.kills > 0
            ORDER BY m.event_id
        """)
        history = defaultdict(list)
        for pname, event_id, kills in cursor.fetchall():
            history[pname].append((event_id or 0, kills))
        return dict(history)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Step 3: Rolling baseline μ (expanding window, leave-future-out)
# ---------------------------------------------------------------------------
def build_rolling_baselines(rows: list, full_history: dict) -> tuple:
    """
    For each calibration row, compute mu_base from ALL kills the player had
    in events strictly before this row's event_id, drawn from the full DB
    history (not just calibration-set rows).

    This gives far more context than limiting to calibration-set rows alone:
    a player with 50 career maps but only 8 with odds data was previously
    dropped; now they get a baseline from all 50.

    Rows where the player has fewer than MIN_PRIOR_MAPS total prior maps
    are still dropped (baseline would be unreliable).
    """
    result = []
    dropped = 0

    for r in rows:
        pname = r['player_name'].lower()
        eid = r.get('event_id') or 0

        # All kills from events strictly before this row's event
        prior = [k for ev, k in full_history.get(pname, []) if ev < eid]

        if len(prior) < MIN_PRIOR_MAPS:
            dropped += 1
            continue

        params = compute_distribution_params(prior)
        if params.get('mu', 0) <= 0 or 'error' in params:
            dropped += 1
            continue

        row = dict(r)
        row['mu_base'] = params['mu']
        row['var_base'] = params.get('var', params['mu'])
        row['dist'] = params['dist']
        row['prior_n'] = len(prior)
        result.append(row)

    return result, dropped


# ---------------------------------------------------------------------------
# Step 4: Train/test split by date
# ---------------------------------------------------------------------------
def train_test_split(rows: list, fraction: float = TRAIN_SPLIT_FRACTION) -> tuple:
    """Split on event_id (chronological proxy). Returns (train, test, split_event_id)."""
    sorted_rows = sorted(rows, key=lambda x: x.get('event_id') or 0)
    split_idx = int(len(sorted_rows) * fraction)
    split_idx = max(1, min(split_idx, len(sorted_rows) - 1))
    split_event_id = sorted_rows[split_idx]['event_id']
    train = [r for r in sorted_rows if (r.get('event_id') or 0) < split_event_id]
    test  = [r for r in sorted_rows if (r.get('event_id') or 0) >= split_event_id]
    return train, test, split_event_id


# ---------------------------------------------------------------------------
# Step 5: Objective — Poisson negative log-likelihood
# ---------------------------------------------------------------------------
def neg_log_likelihood(params, records: list) -> float:
    alpha, beta, gamma = float(params[0]), float(params[1]), float(params[2])
    ll = 0.0
    for r in records:
        result = apply_matchup_adjustment(
            {'mu': r['mu_base'], 'var': r['var_base'], 'dist': r['dist']},
            team_win_prob=r['team_win_prob'],
            alpha_strength=alpha,
            beta_mismatch=beta,
            gamma_mismatch=gamma,
        )
        mu_adj = max(0.01, result['dist_params']['mu'])
        ll += float(scipy_stats.poisson.logpmf(int(r['kills']), mu=mu_adj))
    return -ll


def rmse(params, records: list) -> float:
    alpha, beta, gamma = float(params[0]), float(params[1]), float(params[2])
    errors = []
    for r in records:
        result = apply_matchup_adjustment(
            {'mu': r['mu_base'], 'var': r['var_base'], 'dist': r['dist']},
            team_win_prob=r['team_win_prob'],
            alpha_strength=alpha,
            beta_mismatch=beta,
            gamma_mismatch=gamma,
        )
        mu_adj = max(0.01, result['dist_params']['mu'])
        errors.append((r['kills'] - mu_adj) ** 2)
    return float(np.sqrt(np.mean(errors))) if errors else float('inf')


def no_adj_nll(records: list) -> float:
    ll = 0.0
    for r in records:
        mu = max(0.01, r['mu_base'])
        ll += float(scipy_stats.poisson.logpmf(int(r['kills']), mu=mu))
    return -ll


def no_adj_rmse(records: list) -> float:
    errors = [(r['kills'] - max(0.01, r['mu_base'])) ** 2 for r in records]
    return float(np.sqrt(np.mean(errors))) if errors else float('inf')


# ---------------------------------------------------------------------------
# Step 6: Calibration bin table
# ---------------------------------------------------------------------------
def calibration_bin_table(records: list, params: tuple) -> None:
    alpha, beta, gamma = params
    bins = [(0.0, 0.40), (0.40, 0.50), (0.50, 0.60), (0.60, 0.75), (0.75, 1.01)]
    bin_labels = ['<40%', '40-50%', '50-60%', '60-75%', '>75%']

    header = f"{'P(win) bin':<12} {'n':>5} {'mean kills':>11} {'mu_base':>8} {'mu_adj':>8} {'bias_base':>10} {'bias_adj':>9}"
    print(header)
    print('-' * len(header))

    for (lo, hi), label in zip(bins, bin_labels):
        subset = [r for r in records if lo <= r['team_win_prob'] < hi]
        if not subset:
            print(f"  {label:<10} {'–':>5}")
            continue

        actual   = np.mean([r['kills'] for r in subset])
        mu_base  = np.mean([r['mu_base'] for r in subset])

        adj_mus = []
        for r in subset:
            res = apply_matchup_adjustment(
                {'mu': r['mu_base'], 'var': r['var_base'], 'dist': r['dist']},
                team_win_prob=r['team_win_prob'],
                alpha_strength=alpha, beta_mismatch=beta, gamma_mismatch=gamma,
            )
            adj_mus.append(max(0.01, res['dist_params']['mu']))
        mu_adj = np.mean(adj_mus)

        bias_base = mu_base - actual
        bias_adj  = mu_adj  - actual

        print(f"  {label:<10} {len(subset):>5} {actual:>11.2f} {mu_base:>8.2f} {mu_adj:>8.2f} {bias_base:>+10.2f} {bias_adj:>+9.2f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    db_path = Config.DATABASE_PATH
    print("=" * 70)
    print("  MATCHUP ADJUSTMENT CALIBRATION")
    print("=" * 70)

    # --- Step 1: Build raw rows ---
    print("\n[1] Loading data from database...")
    raw_rows, team_lookup = build_raw_rows(db_path)
    print(f"    Raw rows (player-maps with odds): {len(raw_rows):,}")
    print(f"    Team assignment entries:          {len(team_lookup):,}")

    # --- Step 2: Assign team win prob ---
    print("\n[2] Assigning team win probabilities...")
    rows_with_prob, stats = assign_team_win_prob(raw_rows, team_lookup)
    print(f"    Input rows:              {stats['total_input']:>6,}")
    print(f"    Dropped (bad odds):      {stats['dropped_no_odds']:>6,}")
    print(f"    Dropped (no team):       {stats['dropped_no_team']:>6,}")
    print(f"    Dropped (team mismatch): {stats['dropped_team_mismatch']:>6,}")
    print(f"    Kept:                    {stats['kept']:>6,}")

    if stats['kept'] == 0:
        print("\n[!] No rows survive the join — cannot calibrate.")
        print("    Likely cause: match_url values differ between 'matches' and")
        print("    'moneyline_matches' tables. Check scraper URL formats.")
        return

    # Diagnostic: show sample of team mismatches
    if stats['dropped_team_mismatch'] > 100:
        print("\n    [diag] High team mismatch count. Sampling up to 5 mismatched rows:")
        mismatch_count = 0
        for r in raw_rows[:2000]:
            key = (r['event_id'], r['player_name'].lower())
            pt = team_lookup.get(key)
            if not pt:
                continue
            if not teams_match(pt, r['match_team1']) and not teams_match(pt, r['match_team2']):
                print(f"      player='{r['player_name']}'  player_team='{pt}'  match1='{r['match_team1']}'  match2='{r['match_team2']}'")
                mismatch_count += 1
                if mismatch_count >= 5:
                    break
        if mismatch_count == 0:
            print("      (could not find examples in first 2000 rows)")

    if stats['kept'] < LOW_CONFIDENCE_THRESHOLD:
        print(f"\n[!] WARNING: Only {stats['kept']} rows. Results may be unreliable.")

    # --- Step 2b: Load full kill history ---
    print("\n[2b] Loading full kill history (all DB maps, not just odds-linked)...")
    full_history = load_full_kill_history(db_path)
    total_career_maps = sum(len(v) for v in full_history.values())
    print(f"    Players with history:  {len(full_history):,}")
    print(f"    Total career map-rows: {total_career_maps:,}")

    # --- Step 3: Rolling baselines ---
    print("\n[3] Computing rolling baselines (full-history, leave-future-out)...")
    calib_rows, dropped_baseline = build_rolling_baselines(rows_with_prob, full_history)
    print(f"    Rows dropped (< {MIN_PRIOR_MAPS} prior maps): {dropped_baseline:,}")
    print(f"    Final calibration rows: {len(calib_rows):,}")
    if calib_rows:
        avg_prior = sum(r['prior_n'] for r in calib_rows) / len(calib_rows)
        print(f"    Avg prior maps per row: {avg_prior:.1f}")

    if len(calib_rows) < 50:
        print("\n[!] Too few rows for reliable calibration. Aborting.")
        return

    # --- Step 4: Train/test split ---
    print("\n[4] Splitting train/test (by event_id as time proxy)...")
    try:
        train, test, split_eid = train_test_split(calib_rows)
    except ValueError as e:
        print(f"    [!] {e}")
        return
    print(f"    Split event_id: {split_eid}")
    print(f"    Train: {len(train):,}  |  Test: {len(test):,}")

    if len(test) < 20:
        print("\n[!] Test set too small (<20). Using full dataset for evaluation only.")
        test = calib_rows

    # --- Step 5: Optimize on train ---
    print("\n[5] Optimizing on train set...")
    print(f"    Bounds: alpha=[0,0.6]  beta=[0,0.5]  gamma=[0.5,4.0]")

    iter_count = [0]
    def callback(xk):
        iter_count[0] += 1
        if iter_count[0] % 20 == 0:
            print(f"    iter {iter_count[0]:>4}: alpha={xk[0]:.4f}  beta={xk[1]:.4f}  gamma={xk[2]:.4f}  NLL={neg_log_likelihood(xk, train):.2f}")

    # Start 1: from current defaults
    res1 = minimize(
        fun=neg_log_likelihood,
        x0=list(CURRENT_DEFAULTS),
        args=(train,),
        method='L-BFGS-B',
        bounds=BOUNDS,
        callback=callback,
        options={'maxiter': 500, 'ftol': 1e-9},
    )
    # Start 2: from zero (tests whether any adjustment helps at all)
    res2 = minimize(
        fun=neg_log_likelihood,
        x0=[0.01, 0.01, 1.0],
        args=(train,),
        method='L-BFGS-B',
        bounds=BOUNDS,
        options={'maxiter': 500, 'ftol': 1e-9},
    )

    # Pick whichever start converged to lower NLL on train
    best_res = res1 if res1.fun <= res2.fun else res2
    opt_params = tuple(best_res.x)

    print(f"\n    Optimized: alpha={opt_params[0]:.4f}  beta={opt_params[1]:.4f}  gamma={opt_params[2]:.4f}")
    print(f"    Converged: {best_res.success}  |  message: {best_res.message}")

    # --- Step 6: Evaluation ---
    print("\n[6] Evaluation on TEST set")
    print("-" * 70)

    nll_none    = no_adj_nll(test)
    nll_current = neg_log_likelihood(CURRENT_DEFAULTS, test)
    nll_opt     = neg_log_likelihood(opt_params, test)

    rmse_none    = no_adj_rmse(test)
    rmse_current = rmse(CURRENT_DEFAULTS, test)
    rmse_opt     = rmse(opt_params, test)

    print(f"\n  {'Model':<35} {'NLL':>10} {'RMSE':>8}")
    print(f"  {'-'*35} {'-'*10} {'-'*8}")
    print(f"  {'No adjustment (mu_base only)':<35} {nll_none:>10.2f} {rmse_none:>8.4f}")
    print(f"  {'Current defaults (a=0.22 b=0.18 g=1.8)':<35} {nll_current:>10.2f} {rmse_current:>8.4f}")
    print(f"  {'Optimized':<35} {nll_opt:>10.2f} {rmse_opt:>8.4f}")

    delta_nll  = nll_none - nll_opt
    delta_pct  = 100.0 * delta_nll / abs(nll_none) if nll_none != 0 else 0.0
    print(f"\n  NLL improvement vs. no-adjustment: {delta_nll:+.2f}  ({delta_pct:+.2f}%)")

    if delta_nll < 0:
        print("  [!] Optimized params are WORSE than no adjustment on test set.")
        print("      Consider: data may be insufficient, or team strength has no")
        print("      detectable effect on individual kills in this dataset.")

    # --- Calibration bin table ---
    print("\n[7] Calibration bins (test set, optimized params)")
    print("    bias = predicted - actual  (negative = under-predicting)")
    print()
    calibration_bin_table(test, opt_params)

    print("\n    (Same table with current defaults for comparison)")
    print()
    calibration_bin_table(test, CURRENT_DEFAULTS)

    # --- Step 7: Offer to update defaults ---
    print("\n" + "=" * 70)
    print(f"  Optimized parameters:")
    print(f"    alpha_strength = {opt_params[0]:.4f}")
    print(f"    beta_mismatch  = {opt_params[1]:.4f}")
    print(f"    gamma_mismatch = {opt_params[2]:.4f}")
    print("=" * 70)

    answer = input("\nUpdate backend/matchup_adjust.py defaults with optimized values? [y/N]: ").strip().lower()
    if answer == 'y':
        _update_matchup_adjust(opt_params)
    else:
        print("  Defaults NOT updated.")


def _update_matchup_adjust(params: tuple) -> None:
    alpha, beta, gamma = params
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'backend', 'matchup_adjust.py')
    with open(path, 'r') as f:
        src = f.read()

    src = re.sub(
        r'(alpha_strength\s*:\s*float\s*=\s*)[\d.]+',
        lambda m: m.group(1) + f'{alpha:.4f}',
        src
    )
    src = re.sub(
        r'(beta_mismatch\s*:\s*float\s*=\s*)[\d.]+',
        lambda m: m.group(1) + f'{beta:.4f}',
        src
    )
    src = re.sub(
        r'(gamma_mismatch\s*:\s*float\s*=\s*)[\d.]+',
        lambda m: m.group(1) + f'{gamma:.4f}',
        src
    )

    with open(path, 'w') as f:
        f.write(src)

    print(f"  [OK] Updated {path}")
    print(f"       alpha_strength = {alpha:.4f}")
    print(f"       beta_mismatch  = {beta:.4f}")
    print(f"       gamma_mismatch = {gamma:.4f}")


if __name__ == '__main__':
    main()
