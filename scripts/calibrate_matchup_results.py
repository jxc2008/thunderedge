#!/usr/bin/env python3
"""
Calibrate matchup adjustment constants using actual map results (map scores)
rather than pre-match betting odds.

Instead of team_win_prob from odds, we use:
    round_share = player_rounds / total_rounds

e.g. winning 13-7 → round_share = 13/20 = 0.65
     losing   7-13 → round_share =  7/20 = 0.35

This is the ACTUAL outcome, not a prediction, giving us a much larger dataset
(~37k rows with scores vs ~5k with odds) and a direct causal signal.

The same apply_matchup_adjustment() formula is used; round_share replaces
team_win_prob as input. Constants fit here represent the true post-hoc
relationship between match outcome and individual kills.

Run:
    python scripts/calibrate_matchup_results.py
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

from backend.matchup_adjust import apply_matchup_adjustment
from backend.model_params import compute_distribution_params
from config import Config

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIN_PRIOR_MAPS      = 10
CURRENT_DEFAULTS    = (0.04, 0.04, 4.0)   # calibrated from odds run
BOUNDS              = [(0.0, 0.80), (0.0, 0.60), (0.5, 5.0)]
TRAIN_SPLIT_FRACTION = 0.70
_PUNCT = re.compile(r'[^\w\s]')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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


def parse_score(map_score: str):
    """
    Parse "A-B" → (A, B) as ints.
    Returns None if unparseable.
    map_score is stored as "team1_rounds-team2_rounds".
    """
    if not map_score:
        return None
    parts = map_score.strip().split('-')
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Step 1: Build result rows from DB
# ---------------------------------------------------------------------------
def build_result_rows(db_path: str) -> tuple:
    """
    Returns (rows, team_lookup).
    rows: all player_map_stats rows that have a parseable map_score,
          joined with matches for team info.
    team_lookup: player_name_lower -> full team name.
    """
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT
                pms.player_name,
                pms.kills,
                pms.map_name,
                pms.map_score,
                m.event_id,
                m.team1  AS match_team1,
                m.team2  AS match_team2
            FROM player_map_stats pms
            JOIN matches m ON pms.match_id = m.id
            WHERE pms.kills > 0
              AND pms.map_score IS NOT NULL
            ORDER BY m.event_id, pms.player_name
        """)
        cols = ['player_name', 'kills', 'map_name', 'map_score',
                'event_id', 'match_team1', 'match_team2']
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

        # Team lookup: players table (full names) + fallback to player_event_stats
        cursor.execute("SELECT LOWER(ign), team FROM players WHERE team IS NOT NULL AND team != ''")
        team_lookup = {r[0]: r[1] for r in cursor.fetchall()}
        cursor.execute("SELECT LOWER(player_name), team FROM player_event_stats WHERE team IS NOT NULL AND team != ''")
        for pname, team in cursor.fetchall():
            if pname not in team_lookup:
                team_lookup[pname] = team

        return rows, team_lookup
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Step 2: Parse scores and assign round_share
# ---------------------------------------------------------------------------
def assign_round_share(rows: list, team_lookup: dict) -> tuple:
    """
    For each row:
      - Parse map_score → (team1_rounds, team2_rounds)
      - Match player's team against match_team1/match_team2
      - Compute round_share = player_rounds / total_rounds
      - Compute: total_rounds, won (bool), win_margin

    Returns (clean_rows, stats).
    """
    clean = []
    stats = {
        'total_input': len(rows),
        'dropped_bad_score': 0,
        'dropped_no_team': 0,
        'dropped_team_mismatch': 0,
        'kept': 0,
    }

    for r in rows:
        score = parse_score(r['map_score'])
        if score is None:
            stats['dropped_bad_score'] += 1
            continue

        t1_rounds, t2_rounds = score
        total_rounds = t1_rounds + t2_rounds
        if total_rounds <= 0:
            stats['dropped_bad_score'] += 1
            continue

        player_team = team_lookup.get(r['player_name'].lower())
        if not player_team:
            stats['dropped_no_team'] += 1
            continue

        if teams_match(player_team, r['match_team1']):
            player_rounds = t1_rounds
            opp_rounds    = t2_rounds
        elif teams_match(player_team, r['match_team2']):
            player_rounds = t2_rounds
            opp_rounds    = t1_rounds
        else:
            stats['dropped_team_mismatch'] += 1
            continue

        row = dict(r)
        row['player_rounds'] = player_rounds
        row['opp_rounds']    = opp_rounds
        row['total_rounds']  = total_rounds
        row['won']           = player_rounds > opp_rounds
        row['win_margin']    = player_rounds - opp_rounds
        # Clamp to (0.001, 0.999) — apply_matchup_adjustment requires 0 < p < 1
        raw_share = player_rounds / total_rounds
        row['round_share']   = max(0.001, min(0.999, raw_share))
        row['player_team']   = player_team
        clean.append(row)
        stats['kept'] += 1

    return clean, stats


# ---------------------------------------------------------------------------
# Step 3: Full kill history + rolling baseline
# ---------------------------------------------------------------------------
def load_full_kill_history(db_path: str) -> dict:
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


def build_rolling_baselines(rows: list, full_history: dict) -> tuple:
    result = []
    dropped = 0
    for r in rows:
        pname = r['player_name'].lower()
        eid = r.get('event_id') or 0
        prior = [k for ev, k in full_history.get(pname, []) if ev < eid]
        if len(prior) < MIN_PRIOR_MAPS:
            dropped += 1
            continue
        params = compute_distribution_params(prior)
        if params.get('mu', 0) <= 0 or 'error' in params:
            dropped += 1
            continue
        row = dict(r)
        row['mu_base']  = params['mu']
        row['var_base'] = params.get('var', params['mu'])
        row['dist']     = params['dist']
        row['prior_n']  = len(prior)
        result.append(row)
    return result, dropped


# ---------------------------------------------------------------------------
# Step 4: Train/test split
# ---------------------------------------------------------------------------
def train_test_split(rows: list, fraction: float = TRAIN_SPLIT_FRACTION) -> tuple:
    sorted_rows = sorted(rows, key=lambda x: x.get('event_id') or 0)
    split_idx = int(len(sorted_rows) * fraction)
    split_idx = max(1, min(split_idx, len(sorted_rows) - 1))
    split_eid = sorted_rows[split_idx]['event_id']
    train = [r for r in sorted_rows if (r.get('event_id') or 0) < split_eid]
    test  = [r for r in sorted_rows if (r.get('event_id') or 0) >= split_eid]
    return train, test, split_eid


# ---------------------------------------------------------------------------
# Step 5: Objectives
# ---------------------------------------------------------------------------
def neg_log_likelihood(params, records: list) -> float:
    alpha, beta, gamma = float(params[0]), float(params[1]), float(params[2])
    ll = 0.0
    for r in records:
        result = apply_matchup_adjustment(
            {'mu': r['mu_base'], 'var': r['var_base'], 'dist': r['dist']},
            team_win_prob=r['round_share'],
            alpha_strength=alpha,
            beta_mismatch=beta,
            gamma_mismatch=gamma,
        )
        mu_adj = max(0.01, result['dist_params']['mu'])
        ll += float(scipy_stats.poisson.logpmf(int(r['kills']), mu=mu_adj))
    return -ll


def compute_rmse(params, records: list) -> float:
    alpha, beta, gamma = float(params[0]), float(params[1]), float(params[2])
    errors = []
    for r in records:
        result = apply_matchup_adjustment(
            {'mu': r['mu_base'], 'var': r['var_base'], 'dist': r['dist']},
            team_win_prob=r['round_share'],
            alpha_strength=alpha,
            beta_mismatch=beta,
            gamma_mismatch=gamma,
        )
        mu_adj = max(0.01, result['dist_params']['mu'])
        errors.append((r['kills'] - mu_adj) ** 2)
    return float(np.sqrt(np.mean(errors))) if errors else float('inf')


def no_adj_nll(records: list) -> float:
    return -sum(float(scipy_stats.poisson.logpmf(int(r['kills']), mu=max(0.01, r['mu_base'])))
                for r in records)


def no_adj_rmse(records: list) -> float:
    errors = [(r['kills'] - max(0.01, r['mu_base'])) ** 2 for r in records]
    return float(np.sqrt(np.mean(errors))) if errors else float('inf')


# ---------------------------------------------------------------------------
# Descriptive analysis
# ---------------------------------------------------------------------------
def print_descriptive(records: list) -> None:
    """
    Show how kills relate to round_share and total_rounds.
    """
    print("\n  --- By result (won vs lost) ---")
    won  = [r for r in records if r['won']]
    lost = [r for r in records if not r['won']]
    def _row(label, subset):
        if not subset: return
        kills = [r['kills'] for r in subset]
        mu    = [r['mu_base'] for r in subset]
        ratio = np.mean(kills) / np.mean(mu) if np.mean(mu) > 0 else 1.0
        print(f"    {label:<12}  n={len(subset):>5}  mean_kills={np.mean(kills):>5.2f}  "
              f"mu_base={np.mean(mu):>5.2f}  kill/mu={ratio:.3f}")
    _row('Won map', won)
    _row('Lost map', lost)

    print("\n  --- By win margin (margin = player_rounds - opp_rounds) ---")
    margin_bins = [
        ('Blowout loss', lambda r: r['win_margin'] <= -7),
        ('Moderate loss', lambda r: -6 <= r['win_margin'] <= -3),
        ('Close loss',   lambda r: r['win_margin'] in (-1, -2)),
        ('Close win',    lambda r: r['win_margin'] in (1, 2)),
        ('Moderate win', lambda r: 3 <= r['win_margin'] <= 6),
        ('Blowout win',  lambda r: r['win_margin'] >= 7),
    ]
    for label, filt in margin_bins:
        subset = [r for r in records if filt(r)]
        if subset:
            kills = [r['kills'] for r in subset]
            mu    = [r['mu_base'] for r in subset]
            ratio = np.mean(kills) / np.mean(mu) if np.mean(mu) > 0 else 1.0
            print(f"    {label:<16}  n={len(subset):>5}  mean_kills={np.mean(kills):>5.2f}  "
                  f"mu_base={np.mean(mu):>5.2f}  kill/mu={ratio:.3f}")

    print("\n  --- By total rounds played ---")
    round_bins = [
        ('<=17 rds (3-2 blowout)', lambda r: r['total_rounds'] <= 17),
        ('18-21 rds',              lambda r: 18 <= r['total_rounds'] <= 21),
        ('22-25 rds (close game)', lambda r: 22 <= r['total_rounds'] <= 25),
        ('26+ rds (OT)',           lambda r: r['total_rounds'] >= 26),
    ]
    for label, filt in round_bins:
        subset = [r for r in records if filt(r)]
        if subset:
            kills     = [r['kills'] for r in subset]
            mu        = [r['mu_base'] for r in subset]
            tot_rds   = [r['total_rounds'] for r in subset]
            ratio     = np.mean(kills) / np.mean(mu) if np.mean(mu) > 0 else 1.0
            print(f"    {label:<26}  n={len(subset):>5}  mean_kills={np.mean(kills):>5.2f}  "
                  f"mu_base={np.mean(mu):>5.2f}  kill/mu={ratio:.3f}  "
                  f"avg_rounds={np.mean(tot_rds):.1f}")


def print_calibration_bins(records: list, params: tuple) -> None:
    alpha, beta, gamma = params
    bins = [(0.0, 0.40), (0.40, 0.50), (0.50, 0.60), (0.60, 0.75), (0.75, 1.01)]
    labels = ['<40% (big loss)', '40-50% (slight loss)', '50-60% (slight win)', '60-75% (clear win)', '>75% (blowout win)']
    header = f"  {'round_share bin':<24} {'n':>5} {'actual':>8} {'mu_base':>8} {'mu_adj':>8} {'bias_base':>10} {'bias_adj':>9}"
    print(header)
    print('  ' + '-' * (len(header) - 2))
    for (lo, hi), label in zip(bins, labels):
        subset = [r for r in records if lo <= r['round_share'] < hi]
        if not subset:
            continue
        actual  = np.mean([r['kills'] for r in subset])
        mu_base = np.mean([r['mu_base'] for r in subset])
        adj_mus = []
        for r in subset:
            res = apply_matchup_adjustment(
                {'mu': r['mu_base'], 'var': r['var_base'], 'dist': r['dist']},
                team_win_prob=r['round_share'],
                alpha_strength=alpha, beta_mismatch=beta, gamma_mismatch=gamma,
            )
            adj_mus.append(max(0.01, res['dist_params']['mu']))
        mu_adj     = np.mean(adj_mus)
        bias_base  = mu_base - actual
        bias_adj   = mu_adj  - actual
        print(f"  {label:<24} {len(subset):>5} {actual:>8.2f} {mu_base:>8.2f} {mu_adj:>8.2f} {bias_base:>+10.2f} {bias_adj:>+9.2f}")


# ---------------------------------------------------------------------------
# Update matchup_adjust.py
# ---------------------------------------------------------------------------
def _update_matchup_adjust(params: tuple) -> None:
    alpha, beta, gamma = params
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'backend', 'matchup_adjust.py')
    with open(path, 'r') as f:
        src = f.read()
    src = re.sub(r'(alpha_strength\s*:\s*float\s*=\s*)[\d.]+',
                 lambda m: m.group(1) + f'{alpha:.4f}', src)
    src = re.sub(r'(beta_mismatch\s*:\s*float\s*=\s*)[\d.]+',
                 lambda m: m.group(1) + f'{beta:.4f}', src)
    src = re.sub(r'(gamma_mismatch\s*:\s*float\s*=\s*)[\d.]+',
                 lambda m: m.group(1) + f'{gamma:.4f}', src)
    with open(path, 'w') as f:
        f.write(src)
    print(f"  [OK] Updated {path}")
    print(f"       alpha_strength = {alpha:.4f}")
    print(f"       beta_mismatch  = {beta:.4f}")
    print(f"       gamma_mismatch = {gamma:.4f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    db_path = Config.DATABASE_PATH
    print("=" * 70)
    print("  MATCHUP CALIBRATION — RESULT-BASED (MAP SCORES)")
    print("=" * 70)

    # --- Step 1 ---
    print("\n[1] Loading map score data...")
    raw_rows, team_lookup = build_result_rows(db_path)
    print(f"    Rows with map_score:    {len(raw_rows):,}")
    print(f"    Players in team lookup: {len(team_lookup):,}")

    # --- Step 2 ---
    print("\n[2] Parsing scores and assigning round_share...")
    rows_with_share, stats = assign_round_share(raw_rows, team_lookup)
    print(f"    Input rows:              {stats['total_input']:>7,}")
    print(f"    Dropped (bad score):     {stats['dropped_bad_score']:>7,}")
    print(f"    Dropped (no team):       {stats['dropped_no_team']:>7,}")
    print(f"    Dropped (team mismatch): {stats['dropped_team_mismatch']:>7,}")
    print(f"    Kept:                    {stats['kept']:>7,}")

    if stats['kept'] == 0:
        print("\n[!] No rows kept — check team name matching.")
        return

    # Quick sanity check: distribution of round_share
    shares = [r['round_share'] for r in rows_with_share]
    won_pct = 100 * sum(1 for r in rows_with_share if r['won']) / len(rows_with_share)
    print(f"    round_share range:  [{min(shares):.3f}, {max(shares):.3f}]  mean={np.mean(shares):.3f}")
    print(f"    Won maps:           {won_pct:.1f}%  (expect ~50%)")

    # --- Step 3 ---
    print("\n[3] Loading full kill history...")
    full_history = load_full_kill_history(db_path)
    print(f"    Total career map-rows: {sum(len(v) for v in full_history.values()):,}")

    print("\n[4] Building rolling baselines (leave-future-out)...")
    calib_rows, dropped = build_rolling_baselines(rows_with_share, full_history)
    print(f"    Dropped (< {MIN_PRIOR_MAPS} prior maps): {dropped:,}")
    print(f"    Final calibration rows: {len(calib_rows):,}")
    if calib_rows:
        print(f"    Avg prior maps per row: {np.mean([r['prior_n'] for r in calib_rows]):.1f}")

    if len(calib_rows) < 100:
        print("\n[!] Too few rows. Aborting.")
        return

    # --- Descriptive analysis (full calibration set) ---
    print("\n[5] DESCRIPTIVE ANALYSIS (full calibration set)")
    print("-" * 70)
    print_descriptive(calib_rows)

    # --- Step 5: Train/test split ---
    print("\n[6] Train/test split (by event_id)...")
    train, test, split_eid = train_test_split(calib_rows)
    print(f"    Split event_id: {split_eid}  |  Train: {len(train):,}  Test: {len(test):,}")

    # --- Step 6: Optimize ---
    print("\n[7] Optimizing on train set...")
    print(f"    Bounds: alpha=[0,0.8]  beta=[0,0.6]  gamma=[0.5,5.0]")

    iter_count = [0]
    def callback(xk):
        iter_count[0] += 1
        if iter_count[0] % 30 == 0:
            print(f"    iter {iter_count[0]:>4}: alpha={xk[0]:.4f}  beta={xk[1]:.4f}  "
                  f"gamma={xk[2]:.4f}  NLL={neg_log_likelihood(xk, train):.2f}")

    res1 = minimize(neg_log_likelihood, x0=list(CURRENT_DEFAULTS), args=(train,),
                    method='L-BFGS-B', bounds=BOUNDS, callback=callback,
                    options={'maxiter': 500, 'ftol': 1e-9})
    res2 = minimize(neg_log_likelihood, x0=[0.3, 0.1, 2.0], args=(train,),
                    method='L-BFGS-B', bounds=BOUNDS,
                    options={'maxiter': 500, 'ftol': 1e-9})
    res3 = minimize(neg_log_likelihood, x0=[0.01, 0.01, 1.0], args=(train,),
                    method='L-BFGS-B', bounds=BOUNDS,
                    options={'maxiter': 500, 'ftol': 1e-9})

    best = min([res1, res2, res3], key=lambda r: r.fun)
    opt_params = tuple(best.x)
    print(f"\n    Optimized: alpha={opt_params[0]:.4f}  beta={opt_params[1]:.4f}  gamma={opt_params[2]:.4f}")
    print(f"    Converged: {best.success}  |  {best.message}")

    # --- Step 7: Evaluation ---
    print("\n[8] Evaluation on TEST set")
    print("-" * 70)

    nll_none    = no_adj_nll(test)
    nll_current = neg_log_likelihood(CURRENT_DEFAULTS, test)
    nll_opt     = neg_log_likelihood(opt_params, test)
    rmse_none    = no_adj_rmse(test)
    rmse_current = compute_rmse(CURRENT_DEFAULTS, test)
    rmse_opt     = compute_rmse(opt_params, test)

    print(f"\n  {'Model':<38} {'NLL':>10} {'RMSE':>8}")
    print(f"  {'-'*38} {'-'*10} {'-'*8}")
    print(f"  {'No adjustment (mu_base only)':<38} {nll_none:>10.2f} {rmse_none:>8.4f}")
    print(f"  {'Current defaults (a=0.04 b=0.04 g=4.0)':<38} {nll_current:>10.2f} {rmse_current:>8.4f}")
    print(f"  {'Result-optimized':<38} {nll_opt:>10.2f} {rmse_opt:>8.4f}")

    delta     = nll_none - nll_opt
    delta_pct = 100.0 * delta / abs(nll_none) if nll_none != 0 else 0.0
    print(f"\n  NLL improvement vs. no-adjustment: {delta:+.2f}  ({delta_pct:+.3f}%)")

    if delta > 0:
        print("  [OK] Result-optimized params improve on pure mu_base.")
    else:
        print("  [!] Still no improvement — results don't predict kills beyond baseline.")

    # --- Calibration bins ---
    print("\n[9] Calibration bins (test set, optimized params)")
    print_calibration_bins(test, opt_params)

    # --- Final summary ---
    print("\n" + "=" * 70)
    print("  Result-calibrated parameters:")
    print(f"    alpha_strength = {opt_params[0]:.4f}  (strength effect: winners > losers)")
    print(f"    beta_mismatch  = {opt_params[1]:.4f}  (blowout penalty: fewer rounds = fewer kills)")
    print(f"    gamma_mismatch = {opt_params[2]:.4f}  (nonlinearity of penalty)")
    print("=" * 70)
    print()
    print("  NOTE: These constants are calibrated from ACTUAL match results.")
    print("  In production, team_win_prob (from pre-match odds) is used as input.")
    print("  The odds-based input is a noisier proxy than actual round_share,")
    print("  so pre-match predictions will see smaller real-world gains.")

    answer = input("\nUpdate backend/matchup_adjust.py with result-calibrated values? [y/N]: ").strip().lower()
    if answer == 'y':
        _update_matchup_adjust(opt_params)
    else:
        print("  Defaults NOT updated.")


if __name__ == '__main__':
    main()
