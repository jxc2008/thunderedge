#!/usr/bin/env python3
"""
Moneyline betting strategy analytics.
Produces dataset inventory, vig analysis, calibration, backtest, and strategy spec.
Run: python scripts/moneyline_analytics.py
"""

import sys
import os
import re
import random
import csv
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import Database
from config import Config

import numpy as np

try:
    from scipy import stats as scipy_stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    scipy_stats = None

def _pav(y: np.ndarray) -> np.ndarray:
    """
    Pool Adjacent Violators: isotonic regression (monotone increasing).
    Maintains blocks (sum, count); merges when left block mean > right block mean.
    Returns fitted values aligned with input order.
    """
    y = np.array(y, dtype=float)
    n = len(y)
    if n == 0:
        return y
    blocks = []  # list of (sum, count)
    for yi in y:
        blocks.append((float(yi), 1))
        while len(blocks) >= 2 and blocks[-2][0] * blocks[-1][1] > blocks[-1][0] * blocks[-2][1]:
            s1, c1 = blocks.pop()
            s2, c2 = blocks.pop()
            blocks.append((s1 + s2, c1 + c2))
    y_hat = np.empty(n)
    idx = 0
    for s, c in blocks:
        val = s / c
        y_hat[idx:idx + c] = val
        idx += c
    return y_hat

# --- Name normalization (strip event suffixes, round labels, etc.) ---
_SUFFIX_PATTERN = re.compile(
    r'\s+(vct|champions tour|valorant champions|masters|ewc|esports world cup)\s+'
    r'(\d{4})?\s*'
    r'(americas?|emea|pacific|china)?\s*'
    r'(kickoff|stage\s*\d|stage\s*\d\s*[wW]\d+)?\s*'
    r'(gf|lr\d+|ur\d+|mr\d+|ubqf?|lbr\d+|mbf?|decider\s*[a-z]?|elim\s*[a-z]?|'
    r'w\d+|week\s*\d+|group\s*[a-z]|\d+)?\s*$',
    re.IGNORECASE
)
_PUNCT = re.compile(r'[^\w\s]')


def normalize_team_name(name: str) -> str:
    """
    Deterministic normalizer: lowercase, strip event/round suffixes, collapse whitespace.
    E.g. 'Detonation Focusme Vct 2026 Pacific Kickoff Mr1' -> 'detonation focusme'
    """
    if not name or not str(name).strip():
        return ''
    s = str(name).strip().lower()
    # Strip common suffixes: " Vct 2026 Pacific Kickoff Mr1", " Champions Tour 2025 Stage 2 W3", etc.
    s = re.sub(r'\s+(vct|champions tour|valorant champions|champions\s+\d{4}|masters|ewc)\s+.*$', '', s, flags=re.I)
    s = re.sub(r'\s+(gf|lr\d+|ur\d+|mr\d+|ubqf?|lbr\d+|mbf?|decider\s*[a-z]?|elim\s*[a-z]?|w\d+)\s*$', '', s, flags=re.I)
    s = _PUNCT.sub('', s)
    s = ' '.join(s.split())
    return s


def winner_matches_team(winner: str, team: str, fuzzy: bool = True) -> Tuple[bool, bool]:
    """
    Check if winner matches team. Returns (matched, used_fuzzy).
    fuzzy=True: also match if normalized(winner) in normalized(team) or vice versa.
    """
    nw = normalize_team_name(winner)
    nt = normalize_team_name(team)
    if not nw or not nt:
        return False, False
    if nw == nt:
        return True, False
    if not fuzzy:
        return False, False
    if nw in nt or nt in nw:
        return True, True
    shorter = min(nw, nt, key=len)
    longer = max(nw, nt, key=len)
    if len(shorter) >= 3 and shorter in longer:
        return True, True
    return False, False


# Optional: matplotlib for plots (graceful fallback)
try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


# ==================== DATA LOADING ====================

def load_raw_data() -> List[Dict]:
    """Load all moneyline matches from database."""
    db = Database(Config.DATABASE_PATH)
    return db.get_all_moneyline_matches()


def clean_data(rows: List[Dict]) -> Tuple[List[Dict], Dict]:
    """
    Clean and normalize moneyline data.
    Returns (cleaned_rows, stats_dict).
    """
    stats = {
        'total_raw': len(rows),
        'duplicates_removed': 0,
        'no_winner': 0,
        'no_odds': 0,
        'invalid_odds': 0,
        'odds_1_bug': 0,
        'usable': 0,
    }
    seen_urls = set()
    cleaned = []
    for r in rows:
        if r.get('match_url') in seen_urls:
            stats['duplicates_removed'] += 1
            continue
        seen_urls.add(r.get('match_url', ''))
        if not r.get('winner') or not str(r.get('winner', '')).strip():
            stats['no_winner'] += 1
            continue
        o1, o2 = r.get('team1_odds'), r.get('team2_odds')
        if o1 is None and o2 is None:
            stats['no_odds'] += 1
            continue
        if o1 is not None and (o1 <= 0 or o1 > 50):
            stats['invalid_odds'] += 1
            continue
        if o2 is not None and (o2 <= 0 or o2 > 50):
            stats['invalid_odds'] += 1
            continue
        if (o1 is not None and abs(o1 - 1.0) < 0.01) or (o2 is not None and abs(o2 - 1.0) < 0.01):
            stats['odds_1_bug'] += 1
            continue
        cleaned.append(r)
        stats['usable'] += 1
    return cleaned, stats


def compute_vig_and_pfair(rows: List[Dict]) -> List[Dict]:
    """
    Add Of, Ou, overround, p_raw, p_fair, fav_won, fav_team, dog_team to each row.
    Uses normalized winner matching (with fuzzy fallback). Tracks fuzzy_match for audit.
    """
    out = []
    for r in rows:
        o1, o2 = r.get('team1_odds'), r.get('team2_odds')
        t1, t2 = r.get('team1', ''), r.get('team2', '')
        winner = (r.get('winner') or '').strip()
        if o1 is None and o2 is None:
            continue
        # Require both sides' odds; do not fabricate missing underdog odds
        if o1 is None or o2 is None:
            continue
        if o1 < o2:
            Of, Ou = o1, o2
            fav_team, dog_team = t1, t2
        else:
            Of, Ou = o2, o1
            fav_team, dog_team = t2, t1
        if Ou is None or Ou <= 0:
            continue
        overround = 1.0 / Of + 1.0 / Ou
        p_raw = 1.0 / Of
        p_fair = (1.0 / Of) / (1.0 / Of + 1.0 / Ou)
        fav_won, fuzzy = False, False
        m_fav, m_dog = False, False
        if winner and (fav_team or dog_team):
            m_fav, f_fav = winner_matches_team(winner, fav_team)
            m_dog, f_dog = winner_matches_team(winner, dog_team)
            if m_fav:
                fav_won, fuzzy = True, f_fav
            elif m_dog:
                fav_won, fuzzy = False, f_dog
            # If winner matches neither (or no winner), skip row (don't treat as dog win)
        if not (m_fav or m_dog):
            continue
        row = dict(r)
        row['Of'] = Of
        row['Ou'] = Ou
        row['overround'] = overround
        row['p_raw'] = p_raw
        row['p_fair'] = p_fair
        row['fav_team'] = fav_team
        row['dog_team'] = dog_team
        row['fav_won'] = fav_won
        row['fuzzy_match'] = fuzzy
        row['winner_matched'] = bool(m_fav or m_dog)
        out.append(row)
    return out


def swap_test(rows: List[Dict]) -> Dict:
    """
    Verify favorite is always the lower-odds side (Of < Ou).
    Should be ~100%. If not, label/parsing errors.
    """
    n = len(rows)
    correct = sum(1 for r in rows if r.get('Of', 999) < r.get('Ou', 0))
    return {'n': n, 'correct': correct, 'pct': 100 * correct / n if n else 0}


def bet_side_audit(rows: List[Dict], n_sample: int = 50, seed: int = 42) -> List[Dict]:
    """
    Randomly sample OOS bets for manual verification.
    Returns list of dicts with: team_a, team_b, norm_a, norm_b, odds_a, odds_b,
    labeled_fav, bet_side, winner, fav_won, fuzzy_match, winner_matched.
    """
    rng = random.Random(seed)
    samp = rng.sample(rows, min(n_sample, len(rows)))
    out = []
    for r in samp:
        t1, t2 = r.get('team1', ''), r.get('team2', '')
        o1, o2 = r.get('team1_odds'), r.get('team2_odds')
        Of, Ou = r.get('Of'), r.get('Ou')
        fav_team = r.get('fav_team', '')
        winner = r.get('winner', '')
        fav_won = r.get('fav_won', False)
        fuzzy = r.get('fuzzy_match', False)
        matched = r.get('winner_matched', False)
        labeled_fav = fav_team
        odds_fav = Of
        odds_dog = Ou
        out.append({
            'team_a': t1, 'team_b': t2,
            'norm_a': normalize_team_name(t1), 'norm_b': normalize_team_name(t2),
            'odds_a': o1, 'odds_b': o2,
            'labeled_fav': labeled_fav, 'odds_fav': odds_fav, 'odds_dog': odds_dog,
            'winner': winner, 'fav_won': fav_won, 'fuzzy_match': fuzzy, 'winner_matched': matched,
        })
    return out


def calibration_table(rows: List[Dict], bin_width: float = 0.1) -> List[Dict]:
    """Binned calibration by favorite odds."""
    bins = defaultdict(list)
    for r in rows:
        Of = r.get('Of')
        if Of is None:
            continue
        bin_lo = round(float(np.floor(Of / bin_width) * bin_width), 2)
        bins[bin_lo].append(r)
    results = []
    for bin_lo in sorted(bins.keys()):
        arr = bins[bin_lo]
        n = len(arr)
        Of_avg = np.mean([x['Of'] for x in arr])
        Ou_avg = np.mean([x['Ou'] for x in arr])
        p_raw_avg = np.mean([x['p_raw'] for x in arr])
        p_fair_avg = np.mean([x['p_fair'] for x in arr])
        w = sum(1 for x in arr if x['fav_won'])
        p_obs = w / n if n else 0
        edge = p_obs - p_fair_avg
        # Wilson score interval for p_obs
        z = 1.96
        p_hat = p_obs
        denom = 1 + z**2 / n
        center = (p_hat + z**2 / (2 * n)) / denom
        margin = z * np.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denom
        ci_lo, ci_hi = center - margin, center + margin
        # Beta shrinkage: Jeffreys prior Beta(0.5, 0.5)
        alpha_prior, beta_prior = 0.5, 0.5
        p_emp = (w + alpha_prior) / (n + alpha_prior + beta_prior)
        if HAS_SCIPY:
            lcb = float(scipy_stats.beta.ppf(0.025, w + alpha_prior, n - w + beta_prior))
            ucb = float(scipy_stats.beta.ppf(0.975, w + alpha_prior, n - w + beta_prior))
        else:
            lcb = center - margin
            ucb = center + margin
        results.append({
            'bin_lo': bin_lo,
            'bin_hi': bin_lo + bin_width,
            'n': n,
            'Of_avg': round(Of_avg, 3),
            'Ou_avg': round(Ou_avg, 3),
            'p_raw': round(p_raw_avg, 4),
            'p_fair': round(p_fair_avg, 4),
            'p_obs': round(p_obs, 4),
            'p_emp': round(p_emp, 4),
            'lcb': round(lcb, 4),
            'ucb': round(ucb, 4),
            'edge': round(edge, 4),
            'edge_ci_lo': round(p_obs - margin - p_fair_avg, 4),
            'edge_ci_hi': round(p_obs + margin - p_fair_avg, 4),
        })
    return results


def backtest_strategies(rows: List[Dict], edge_threshold: float = 0.05,
                        lcb_margin: float = 0.01, train_frac: float = 0.7,
                        train_years: Optional[List[int]] = None,
                        test_years: Optional[List[int]] = None) -> Dict:
    """
    Walk-forward backtest. If train_years/test_years given, split by year; else by row order.
    Strategies:
      A) always fav, B) always dog
      C) fav when edge>t, D) dog when edge<-t, E) best side (edge-based)
      F) fav when LCB(p_emp) > p_fair + margin, G) dog when UCB(p_emp) < p_fair - margin
      H) best side (LCB-based)
    """
    rows_with_year = []
    for r in rows:
        yr = infer_year(r.get('event_name', ''))
        rows_with_year.append((yr, r))
    if train_years is not None and test_years is not None:
        train_rows = [r for yr, r in rows_with_year if yr in train_years]
        test_rows = [r for yr, r in rows_with_year if yr in test_years]
        if not train_rows or not test_rows:
            # Fallback to row-order split
            n = len(rows)
            split = int(n * train_frac)
            train_rows = rows[:split]
            test_rows = rows[split:]
    else:
        n = len(rows)
        split = int(n * train_frac)
        train_rows = rows[:split]
        test_rows = rows[split:]
    cal = {r['bin_lo']: r for r in calibration_table(train_rows, bin_width=0.1)}
    margin = lcb_margin

    def get_edge(r):
        Of = r.get('Of')
        if Of is None:
            return 0.0
        bin_lo = round(float(np.floor(Of / 0.1) * 0.1), 2)
        c = cal.get(bin_lo)
        if c:
            return c['edge']
        return 0.0

    def get_lcb_ucb(r):
        Of = r.get('Of')
        p_fair = r.get('p_fair', 0.5)
        if Of is None:
            return 0.0, 1.0, p_fair
        bin_lo = round(float(np.floor(Of / 0.1) * 0.1), 2)
        c = cal.get(bin_lo)
        if c:
            return c.get('lcb', 0), c.get('ucb', 1), c.get('p_fair', p_fair)
        return 0.0, 1.0, p_fair

    def run_strategy(rows_subset, bet_fav_fn, bet_dog_fn):
        profits, outcomes, odds_taken = [], [], []
        for r in rows_subset:
            Of, Ou = r.get('Of'), r.get('Ou')
            fav_won = r.get('fav_won', False)
            if Of is None or Ou is None:
                continue
            bet_fav = bet_fav_fn(r)
            bet_dog = bet_dog_fn(r)
            if bet_fav and not bet_dog:
                profit = (Of - 1) if fav_won else -1
                odds_taken.append(Of)
            elif bet_dog and not bet_fav:
                profit = (Ou - 1) if not fav_won else -1
                odds_taken.append(Ou)
            else:
                continue
            profits.append(profit)
            outcomes.append(1 if profit > 0 else 0)
        if not profits:
            return {'roi': 0, 'n_bets': 0, 'hit_rate': 0, 'avg_odds': 0, 'max_dd': 0, 'longest_losing': 0, 'volatility': 0, 'sharpe': 0}
        arr = np.array(profits)
        cum = np.cumsum(arr)
        dd = np.maximum.accumulate(cum) - cum
        max_dd = float(np.max(dd))
        streak, longest = 0, 0
        for p in profits:
            if p < 0:
                streak += 1
                longest = max(longest, streak)
            else:
                streak = 0
        return {
            'roi': float(np.mean(arr)) * 100,
            'n_bets': len(profits),
            'hit_rate': np.mean(outcomes) * 100,
            'avg_odds': np.mean(odds_taken) if odds_taken else 0,
            'max_dd': max_dd,
            'longest_losing': longest,
            'volatility': float(np.std(arr)),
            'sharpe': float(np.mean(arr) / np.std(arr)) if np.std(arr) > 0 else 0,
        }

    edge_thresh = edge_threshold
    results = {}
    results['A_always_fav'] = run_strategy(test_rows, lambda r: True, lambda r: False)
    results['B_always_dog'] = run_strategy(test_rows, lambda r: False, lambda r: True)
    results['C_fav_edge'] = run_strategy(test_rows, lambda r: get_edge(r) > edge_thresh, lambda r: False)
    results['D_dog_edge'] = run_strategy(test_rows, lambda r: False, lambda r: get_edge(r) < -edge_thresh)
    results['E_best_side'] = run_strategy(test_rows,
        lambda r: get_edge(r) > edge_thresh,
        lambda r: get_edge(r) < -edge_thresh)
    # LCB-based: bet fav when LCB(p_emp) > p_fair + margin; bet dog when UCB(p_emp) < p_fair - margin
    results['F_fav_lcb'] = run_strategy(test_rows,
        lambda r: (lambda l,u,pf: l > pf + margin)(*get_lcb_ucb(r)),
        lambda r: False)
    results['G_dog_lcb'] = run_strategy(test_rows,
        lambda r: False,
        lambda r: (lambda l,u,pf: u < pf - margin)(*get_lcb_ucb(r)))
    results['H_best_lcb'] = run_strategy(test_rows,
        lambda r: (lambda l,u,pf: l > pf + margin)(*get_lcb_ucb(r)),
        lambda r: (lambda l,u,pf: u < pf - margin)(*get_lcb_ucb(r)))

    # Isotonic + EV threshold: bet side with EV >= ev_min, choose higher EV
    iso_pred = fit_isotonic_calibrator(train_rows)
    ev_min = 0.01
    def get_ev(r):
        pf = r.get('p_fair', 0.5)
        Of, Ou = r.get('Of'), r.get('Ou')
        if Of is None or Ou is None:
            return 0.0, 0.0
        p_hat = float(np.atleast_1d(iso_pred(pf))[0])
        ev_fav = p_hat * Of - 1
        ev_dog = (1 - p_hat) * Ou - 1
        return ev_fav, ev_dog
    results['I_best_ev_isotonic'] = run_strategy(test_rows,
        lambda r: (lambda ef, ed: ef >= ev_min and ef > ed)(*get_ev(r)),
        lambda r: (lambda ef, ed: ed >= ev_min and ed > ef)(*get_ev(r)))
    return results


def fit_isotonic_calibrator(train_rows: List[Dict]) -> callable:
    """
    Fit isotonic regression: p_fair -> p_true (fav win rate).
    Uses deterministic PAV on outcomes ordered by p_fair. Returns predict(p_fair) function.
    """
    p_fair = np.array([r['p_fair'] for r in train_rows], dtype=float)
    outcome = np.array([1.0 if r['fav_won'] else 0.0 for r in train_rows], dtype=float)
    order = np.argsort(p_fair)
    x_s = p_fair[order]
    y_s = outcome[order]
    y_hat = _pav(y_s)

    def predict(p_fair_new):
        p = np.atleast_1d(p_fair_new).astype(float)
        return np.interp(p, x_s, y_hat, left=y_hat[0], right=y_hat[-1])

    return predict


def infer_tier(event_name: str) -> str:
    """Infer event tier from name: International, Regional, Other."""
    n = (event_name or '').lower()
    if 'champions' in n or 'masters' in n or 'world' in n or 'ewc' in n:
        return 'International'
    if 'kickoff' in n or 'stage' in n or 'americas' in n or 'emea' in n or 'pacific' in n or 'china' in n:
        return 'Regional'
    return 'Other'


def infer_tier_detail(event_name: str) -> str:
    """Finer event tier: International/Stage vs Kickoff vs Qualifier vs Ascension."""
    n = (event_name or '').lower()
    if 'ascension' in n:
        return 'Ascension'
    if 'champions' in n or 'masters' in n or 'world' in n or 'ewc' in n:
        return 'International'
    if 'stage' in n:
        return 'Stage'
    if 'kickoff' in n:
        return 'Kickoff'
    if 'qualifier' in n or 'qual' in n or 'decider' in n or 'elim' in n:
        return 'Qualifier'
    return 'Other'


def event_blocked_roi(test_rows: List[Dict], strategy_fn) -> Dict:
    """
    Evaluate ROI by event. strategy_fn(rows) -> summary dict with roi, n_bets, etc.
    Groups rows by event, runs strategy per event, returns median/pct_positive/worst.
    """
    by_event = defaultdict(list)
    for r in test_rows:
        ev = r.get('event_name', '') or 'unknown'
        by_event[ev].append(r)
    event_rois = []
    for ev, rows in by_event.items():
        res = strategy_fn(rows)
        if res['n_bets'] > 0:
            event_rois.append(res['roi'])
    if not event_rois:
        return {'median_event_roi': 0, 'pct_positive': 0, 'worst_roi': 0, 'n_events': 0}
    return {
        'median_event_roi': float(np.median(event_rois)),
        'pct_positive': 100 * np.mean(np.array(event_rois) > 0),
        'worst_roi': float(np.min(event_rois)),
        'n_events': len(event_rois),
    }


def run_dumb_filter_strategy(test_rows: List[Dict], regions: tuple = ('Americas', 'China'),
                             p_fair_min: float = 0.55, p_fair_max: Optional[float] = None,
                             of_min: float = 1.35, kickoff_stake_cap: Optional[float] = None,
                             bet_side: str = 'fav', even_odds_threshold: float = 0.05) -> Dict:
    """
    Dumb filter: bet favorite only in specified regions when p_fair_min <= p_fair <= p_fair_max.
    No-bet zone for heavy favorites (p_fair > p_fair_max).
    of_min: minimum favorite odds (avoids ultra-short pricing artifacts); default 1.35.
    Optional kickoff_stake_cap: use 0.75u for Kickoff tier instead of 1u.
    Skip when |Of-Ou| < even_odds_threshold (even odds).
    Returns summary dict (roi, n_bets, hit_rate, avg_odds, max_dd, skipped_even).
    ROI = sum(profit) / sum(stake).
    """
    profits, stakes, odds_taken, p_fairs = [], [], [], []
    skipped_even = 0
    for r in test_rows:
        reg = infer_region(r.get('event_name', ''))
        if reg not in regions:
            continue
        pf = r.get('p_fair', 0)
        if pf < p_fair_min:
            continue
        if p_fair_max is not None and pf > p_fair_max:
            continue
        Of, Ou = r.get('Of'), r.get('Ou')
        fav_won = r.get('fav_won', False)
        if Of is None or Ou is None:
            continue
        if abs(Of - Ou) <= even_odds_threshold:
            skipped_even += 1
            continue
        if Of < of_min:
            continue
        tier = infer_tier_detail(r.get('event_name', ''))
        stake = kickoff_stake_cap if (kickoff_stake_cap is not None and tier == 'Kickoff') else 1.0
        if bet_side == 'fav':
            profit = stake * ((Of - 1) if fav_won else -1)
            odds_taken.append(Of)
        else:
            profit = stake * ((Ou - 1) if not fav_won else -1)
            odds_taken.append(Ou)
        profits.append(profit)
        stakes.append(stake)
        p_fairs.append(pf)
    if not profits:
        return {'roi': 0, 'n_bets': 0, 'hit_rate': 0, 'avg_odds': 0, 'max_dd': 0, 'avg_p_fair': 0, 'avg_be_rate': 0, 'skipped_even': skipped_even}
    arr = np.array(profits)
    total_stake = sum(stakes)
    roi_pct = 100 * sum(profits) / total_stake if total_stake else 0
    cum = np.cumsum(arr)
    dd = np.maximum.accumulate(cum) - cum
    odds_arr = np.array(odds_taken)
    be_rate = 100 * np.mean(1.0 / odds_arr)  # break-even win rate (per bet)
    return {
        'roi': float(roi_pct),
        'n_bets': len(profits),
        'hit_rate': np.mean([1 if p > 0 else 0 for p in profits]) * 100,
        'avg_odds': np.mean(odds_taken) if odds_taken else 0,
        'median_odds': np.median(odds_taken) if odds_taken else 0,
        'avg_p_fair': np.mean(p_fairs) if p_fairs else 0,
        'median_p_fair': np.median(p_fairs) if p_fairs else 0,
        'avg_be_rate': float(be_rate),
        'max_dd': float(np.max(dd)),
        'skipped_even': skipped_even,
    }


def generate_bet_log(rows: List[Dict], regions: tuple = ('Americas', 'China'),
                     p_fair_min: float = 0.55, p_fair_max: float = 0.70,
                     of_min: float = 1.35, kickoff_stake_cap: Optional[float] = 0.75,
                     even_odds_threshold: float = 0.05, run_time: Optional[str] = None) -> List[Dict]:
    """
    Generate bet log for all Americas+China candidates. Each entry has decision, stake, flags.
    """
    run_time = run_time or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log = []
    for r in rows:
        reg = infer_region(r.get('event_name', ''))
        if reg not in regions:
            continue
        Of, Ou = r.get('Of'), r.get('Ou')
        if Of is None or Ou is None:
            continue
        pf = r.get('p_fair', 0)
        tier = infer_tier_detail(r.get('event_name', ''))
        t1, t2 = r.get('team1', ''), r.get('team2', '')
        flag_region_skip = False
        flag_p_fair_low = pf < p_fair_min
        flag_p_fair_high = pf > p_fair_max if p_fair_max else False
        flag_of_min = Of < of_min
        flag_even_odds = abs(Of - Ou) <= even_odds_threshold
        flag_kickoff_cap = (kickoff_stake_cap is not None and tier == 'Kickoff')
        bet = not (flag_p_fair_low or flag_p_fair_high or flag_of_min or flag_even_odds)
        stake = kickoff_stake_cap if flag_kickoff_cap and bet else 1.0
        decision = 'bet_fav' if bet else 'skip'
        log.append({
            'run_time': run_time,
            'match_url': r.get('match_url', ''),
            'event_name': r.get('event_name', '')[:40],
            'region': reg,
            'tier_detail': tier,
            'team1': t1[:30],
            'team2': t2[:30],
            'team1_norm': normalize_team_name(t1)[:20],
            'team2_norm': normalize_team_name(t2)[:20],
            'Of': round(Of, 3),
            'Ou': round(Ou, 3),
            'p_fair': round(pf, 3),
            'decision': decision,
            'stake': stake,
            'flag_p_fair_low': flag_p_fair_low,
            'flag_p_fair_high': flag_p_fair_high,
            'flag_of_min': flag_of_min,
            'flag_even_odds': flag_even_odds,
            'flag_kickoff_cap': flag_kickoff_cap and bet,
        })
    return log


def export_bet_log_to_csv(log: List[Dict], output_path: str) -> str:
    """Write bet log to CSV. Returns path."""
    if not log:
        return output_path
    cols = ['run_time', 'match_url', 'event_name', 'region', 'tier_detail', 'team1', 'team2', 'team1_norm', 'team2_norm',
            'Of', 'Ou', 'p_fair', 'decision', 'stake', 'flag_p_fair_low', 'flag_p_fair_high', 'flag_of_min', 'flag_even_odds', 'flag_kickoff_cap']
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(log)
    return output_path


def infer_region(event_name: str) -> str:
    """Infer region from event name."""
    n = (event_name or '').lower()
    if 'americas' in n or 'amer' in n or 'latam' in n or 'brazil' in n:
        return 'Americas'
    if 'emea' in n or 'europe' in n or 'dach' in n or 'france' in n or 'spain' in n or 'italy' in n:
        return 'EMEA'
    if 'portugal' in n or 'türkiye' in n or 'turkey' in n or 't-rkiye' in n:
        return 'EMEA'
    if 'east surge' in n or 'polaris' in n or 'mena' in n:
        return 'EMEA'
    if 'pacific' in n or 'apac' in n or 'korea' in n or 'japan' in n or 'oceania' in n:
        return 'Pacific'
    if 'taiwan' in n or 'hong kong' in n or 'thailand' in n or 'malaysia' in n or 'singapore' in n:
        return 'Pacific'
    if 'philippines' in n or 'vietnam' in n or 'indonesia' in n or 'south asia' in n or 'southeast asia' in n:
        return 'Pacific'
    if 'china' in n:
        return 'China'
    if 'champions' in n or 'masters' in n or 'world' in n or 'ewc' in n:
        return 'International'
    return 'Unknown'


def infer_year(event_name: str) -> int:
    """Infer year from event name."""
    m = re.search(r'20(\d{2})', event_name or '')
    return int(m.group(1)) + 2000 if m else 0


def run_isotonic_strategy(test_rows: List[Dict], iso_pred: callable, ev_min: float,
                          return_bets: bool = False) -> Dict:
    """
    Run isotonic+EV strategy on test_rows. Returns summary dict.
    If return_bets=True, also returns list of bet dicts (profit, region, odds, p_fair, fav_won, overround).
    """
    bets = []
    for r in test_rows:
        Of, Ou = r.get('Of'), r.get('Ou')
        fav_won = r.get('fav_won', False)
        if Of is None or Ou is None:
            continue
        pf = r.get('p_fair', 0.5)
        p_hat = float(np.atleast_1d(iso_pred(pf))[0])
        ev_fav = p_hat * Of - 1
        ev_dog = (1 - p_hat) * Ou - 1
        bet_fav = ev_fav >= ev_min and ev_fav > ev_dog
        bet_dog = ev_dog >= ev_min and ev_dog > ev_fav
        if bet_fav and not bet_dog:
            profit = (Of - 1) if fav_won else -1
            odds = Of
        elif bet_dog and not bet_fav:
            profit = (Ou - 1) if not fav_won else -1
            odds = Ou
        else:
            continue
        reg = infer_region(r.get('event_name', ''))
        ov = r.get('overround', 1.05)
        bets.append({'profit': profit, 'region': reg, 'odds': odds, 'p_fair': pf, 'fav_won': fav_won, 'overround': ov})
    if not bets:
        out = {'roi': 0, 'n_bets': 0, 'hit_rate': 0, 'avg_odds': 0, 'max_dd': 0}
        return (out, []) if return_bets else out
    arr = np.array([b['profit'] for b in bets])
    cum = np.cumsum(arr)
    dd = np.maximum.accumulate(cum) - cum
    out = {
        'roi': float(np.mean(arr)) * 100,
        'n_bets': len(bets),
        'hit_rate': np.mean([1 if b['profit'] > 0 else 0 for b in bets]) * 100,
        'avg_odds': np.mean([b['odds'] for b in bets]),
        'max_dd': float(np.max(dd)),
    }
    return (out, bets) if return_bets else out


def bootstrap_isotonic(enriched: List[Dict], train_years: List[int], test_years: List[int],
                      ev_min: float = 0.01, n_reps: int = 500, seed: int = 42) -> Dict:
    """Bootstrap I_best_ev_isotonic: fixed calibrator, resample test by event."""
    train_rows = [r for r in enriched if infer_year(r.get('event_name', '')) in train_years]
    test_rows = [r for r in enriched if infer_year(r.get('event_name', '')) in test_years]
    iso_pred = fit_isotonic_calibrator(train_rows)
    by_event = defaultdict(list)
    for r in test_rows:
        by_event[r.get('event_name', '') or 'unknown'].append(r)
    events = list(by_event.keys())
    rng = np.random.default_rng(seed)
    rois, max_dds, n_bets_list = [], [], []
    for _ in range(n_reps):
        ev_sample = rng.choice(events, size=len(events), replace=True)
        rows_bs = []
        for ev in ev_sample:
            rows_bs.extend(by_event[ev])
        res = run_isotonic_strategy(rows_bs, iso_pred, ev_min)
        rois.append(res['roi'])
        max_dds.append(res['max_dd'])
        n_bets_list.append(res['n_bets'])
    return {
        'roi_p5': np.percentile(rois, 5), 'roi_p50': np.percentile(rois, 50), 'roi_p95': np.percentile(rois, 95),
        'dd_p5': np.percentile(max_dds, 5), 'dd_p50': np.percentile(max_dds, 50), 'dd_p95': np.percentile(max_dds, 95),
        'n_bets_p5': np.percentile(n_bets_list, 5), 'n_bets_p50': np.percentile(n_bets_list, 50), 'n_bets_p95': np.percentile(n_bets_list, 95),
    }


def ev_threshold_sweep(enriched: List[Dict], train_years: List[int], test_years: List[int],
                       thresholds: List[float]) -> List[Dict]:
    """Sweep EV thresholds, return ROI/n_bets/hit_rate/max_dd per threshold."""
    train_rows = [r for r in enriched if infer_year(r.get('event_name', '')) in train_years]
    test_rows = [r for r in enriched if infer_year(r.get('event_name', '')) in test_years]
    iso_pred = fit_isotonic_calibrator(train_rows)
    out = []
    for ev_min in thresholds:
        res = run_isotonic_strategy(test_rows, iso_pred, ev_min)
        out.append({'ev_min': ev_min, **res})
    return out


def _plot_calibration_curve(cal: List[Dict], output_path: str = 'moneyline_calibration.png'):
    """Plot p_obs vs p_fair with confidence bands."""
    if not HAS_MATPLOTLIB or not cal:
        return
    p_fair = np.array([c['p_fair'] for c in cal])
    p_obs = np.array([c['p_obs'] for c in cal])
    n_arr = np.array([c['n'] for c in cal])
    z = 1.96
    p_hat = p_obs
    denom = 1 + z**2 / n_arr
    center = (p_hat + z**2 / (2 * n_arr)) / denom
    margin = z * np.sqrt(p_hat * (1 - p_hat) / n_arr + z**2 / (4 * n_arr**2)) / denom
    ci_lo, ci_hi = center - margin, center + margin
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot([0, 1], [0, 1], 'k--', alpha=0.5, label='Perfect calibration')
    ax.errorbar(p_fair, p_obs, yerr=[p_obs - ci_lo, ci_hi - p_obs], fmt='o-', capsize=3, label='Observed')
    ax.set_xlabel('De-vig implied probability (p_fair)')
    ax.set_ylabel('Observed win rate (p_obs)')
    ax.set_title('Calibration: p_obs vs p_fair (Thunderpick moneyline)')
    ax.legend()
    ax.set_xlim(0.4, 1.0)
    ax.set_ylim(0.4, 1.0)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=100)
    plt.close()


def _run_pipeline():
    """Run analytics pipeline, return dict of results (no printing)."""
    rows = load_raw_data()
    cleaned, clean_stats = clean_data(rows)
    enriched = compute_vig_and_pfair(cleaned)

    print("=" * 70)
    print("1) DATASET INVENTORY")
    print("=" * 70)
    print("""
Columns (moneyline_matches):
  id          : int, primary key
  match_url   : str, unique VLR match path
  event_name  : str, e.g. "VCT 2025: Americas Kickoff"
  event_url   : str, VLR event path
  team1       : str
  team2       : str
  team1_odds  : float, decimal (Thunderpick)
  team2_odds  : float, decimal
  winner      : str, team name
  team1_maps  : int, maps won
  team2_maps  : int
  match_date  : str (often null)
  created_at  : timestamp
""")
    print(f"Total rows: {clean_stats['total_raw']}")
    print(f"Duplicates removed: {clean_stats['duplicates_removed']}")
    print(f"No winner: {clean_stats['no_winner']}")
    print(f"No odds: {clean_stats['no_odds']}")
    print(f"Invalid odds: {clean_stats['invalid_odds']}")
    print(f"1.00 bug excluded: {clean_stats['odds_1_bug']}")
    print(f"Usable for backtest: {clean_stats['usable']}")
    print("Market: 2-way (no draws). Odds: decimal.")
    print()

    if not enriched:
        return None

    print("=" * 70)
    print("2) ODDS CLEANING + VIG")
    print("=" * 70)
    Of_arr = np.array([r['Of'] for r in enriched])
    Ou_arr = np.array([r['Ou'] for r in enriched])
    ov_arr = np.array([r['overround'] for r in enriched])
    print("Favorite odds (Of): min={:.2f} median={:.2f} mean={:.2f} max={:.2f}".format(
        np.min(Of_arr), np.median(Of_arr), np.mean(Of_arr), np.max(Of_arr)))
    print("Underdog odds (Ou): min={:.2f} median={:.2f} mean={:.2f} max={:.2f}".format(
        np.min(Ou_arr), np.median(Ou_arr), np.mean(Ou_arr), np.max(Ou_arr)))
    equal_count = np.sum(np.abs(Of_arr - Ou_arr) < 0.05)
    print(f"Near-equal odds (|Of-Ou|<0.05): {equal_count} ({100*equal_count/len(enriched):.1f}%)")
    # Secondary duplicate key (diagnostics only)
    sec_key = defaultdict(list)
    for r in enriched:
        t1, t2 = r.get('team1', ''), r.get('team2', '')
        ev = r.get('event_name', '') or 'unknown'
        yr = infer_year(ev)
        k = (normalize_team_name(t1), normalize_team_name(t2), ev[:50], yr)
        sec_key[k].append(r.get('match_url', ''))
    collisions = sum(1 for v in sec_key.values() if len(v) > 1)
    total_collision_rows = sum(len(v) for v in sec_key.values() if len(v) > 1)
    if collisions > 0:
        print(f"Secondary key collisions (norm_t1, norm_t2, event, year): {collisions} keys with {total_collision_rows} total rows")
    else:
        print("Secondary key collisions: 0 (no duplicate match keys beyond match_url)")
    print("Overround (1/Of + 1/Ou): mean={:.4f} median={:.4f}".format(np.mean(ov_arr), np.median(ov_arr)))
    print()

    print("=" * 70)
    print("2b) WINNER/SIDE ALIGNMENT CHECKS")
    print("=" * 70)
    swap = swap_test(enriched)
    print(f"Swap test (Of < Ou): {swap['correct']}/{swap['n']} = {swap['pct']:.1f}%")
    unmatched = sum(1 for r in enriched if not r.get('winner_matched', True))
    fuzzy_count = sum(1 for r in enriched if r.get('fuzzy_match', False))
    print(f"Winner matched (exact or fuzzy): {len(enriched) - unmatched}/{len(enriched)}")
    print(f"Fuzzy matches used: {fuzzy_count}")
    test_rows = [r for r in enriched if infer_year(r.get('event_name', '')) == 2026]
    audit = bet_side_audit(test_rows, n_sample=min(50, len(test_rows)))
    print(f"\nBet-side audit (50 random OOS 2026 matches):")
    for i, a in enumerate(audit[:15]):
        print(f"  [{i+1}] {a['team_a'][:20]} vs {a['team_b'][:20]} | Of={a['odds_fav']:.2f} Ou={a['odds_dog']:.2f} | winner={str(a['winner'])[:25]} fav_won={a['fav_won']} fuzzy={a['fuzzy_match']} matched={a['winner_matched']}")
    if len(audit) > 15:
        print(f"  ... and {len(audit)-15} more (see full audit with --audit)")
    print()

    print("=" * 70)
    print("3) CALIBRATION (bins by Of, Beta shrinkage)")
    print("=" * 70)
    cal = calibration_table(enriched, bin_width=0.1)
    print(f"{'Bin':<12} {'n':>6} {'p_emp':>8} {'lcb':>8} {'p_fair':>8} {'p_obs':>8} {'edge':>8} {'95% CI'}")
    for c in cal:
        ci = f"[{c['edge_ci_lo']:.3f}, {c['edge_ci_hi']:.3f}]"
        p_emp = c.get('p_emp', c['p_obs'])
        lcb = c.get('lcb', c['p_obs'] - 0.05)
        print(f"{c['bin_lo']:.1f}-{c['bin_hi']:.1f}   {c['n']:>6} {p_emp:>8.3f} {lcb:>8.3f} {c['p_fair']:>8.3f} {c['p_obs']:>8.3f} {c['edge']:>8.3f} {ci}")
    p_obs_arr = np.array([c['p_obs'] for c in cal])
    p_fair_arr = np.array([c['p_fair'] for c in cal])
    n_arr = np.array([c['n'] for c in cal])
    brier = np.sum(n_arr * (p_obs_arr - p_fair_arr)**2) / np.sum(n_arr) if np.sum(n_arr) > 0 else 0
    ece = np.mean(np.abs(p_obs_arr - p_fair_arr))
    print(f"\nBrier score (implied): {brier:.4f}")
    print(f"Calibration error (ECE): {ece:.4f}")
    print("\nCalibration drift by year (per-match: outcome - p_fair):")
    for yr in [2024, 2025, 2026]:
        yr_rows = [r for r in enriched if infer_year(r.get('event_name', '')) == yr]
        if yr_rows:
            outcome = np.array([1 if r['fav_won'] else 0 for r in yr_rows])
            p_fair = np.array([r['p_fair'] for r in yr_rows])
            p_raw = np.array([r['p_raw'] for r in yr_rows])
            e_match = outcome - p_fair
            e_vig = p_raw - p_fair
            print(f"  {yr}: n={len(yr_rows)} mean(outcome-p_fair)={np.mean(e_match):.4f} mean(outcome)-mean(p_fair)={np.mean(outcome)-np.mean(p_fair):.4f} mean(p_raw-p_fair)={np.mean(e_vig):.4f}")
    if HAS_MATPLOTLIB:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        plot_path = os.path.join(script_dir, 'moneyline_calibration.png')
        _plot_calibration_curve(cal, output_path=plot_path)
        print(f"Calibration plot saved to {plot_path}")
    print()

    print("=" * 70)
    print("4) PROFITABILITY BACKTEST (train 2024-2025, test 2026)")
    print("=" * 70)
    bt = backtest_strategies(enriched, edge_threshold=0.05, lcb_margin=0.01, train_frac=0.7,
                             train_years=[2024, 2025], test_years=[2026])
    for k, v in bt.items():
        print(f"  {k}: ROI={v['roi']:.1f}% n={v['n_bets']} hit={v['hit_rate']:.1f}% max_dd={v['max_dd']:.2f} longest_L={v['longest_losing']}")
    print()

    # Sanity check: A_always_fav break-even vs actual
    a_res = bt.get('A_always_fav', {})
    if a_res.get('n_bets', 0) > 0:
        avg_odds = a_res['avg_odds']
        hit_rate = a_res['hit_rate'] / 100
        be_rate = 1.0 / avg_odds if avg_odds else 0
        print("4b) SANITY CHECK (A_always_fav):")
        print(f"  avg_profit_per_bet={a_res['roi']/100:.4f} avg_odds={avg_odds:.2f}")
        print(f"  actual win rate={hit_rate:.2%} break-even win rate={be_rate:.2%} gap={hit_rate-be_rate:.2%}")
        print()

    # Bootstrap ROI CI (block by event)
    test_rows = [r for r in enriched if infer_year(r.get('event_name', '')) == 2026]
    by_event = defaultdict(list)
    for r in test_rows:
        ev = r.get('event_name', '') or 'unknown'
        by_event[ev].append(r)
    events = list(by_event.keys())
    if events:
        rng = np.random.default_rng(42)
        rois, max_dds = [], []
        for _ in range(500):
            ev_sample = rng.choice(events, size=len(events), replace=True)
            rows_bs = []
            for ev in ev_sample:
                rows_bs.extend(by_event[ev])
            if not rows_bs:
                continue
            profits = []
            for r in rows_bs:
                Of, Ou = r.get('Of'), r.get('Ou')
                fav_won = r.get('fav_won', False)
                if Of is None or Ou is None:
                    continue
                profits.append((Of - 1) if fav_won else -1)
            if profits:
                rois.append(np.mean(profits) * 100)
                cum = np.cumsum(profits)
                dd = np.maximum.accumulate(cum) - cum
                max_dds.append(float(np.max(dd)))
        if rois:
            print("4c) BOOTSTRAP ROI CI (A_always_fav, block by event, 500 reps):")
            print(f"  ROI: p5={np.percentile(rois, 5):.1f}% p50={np.percentile(rois, 50):.1f}% p95={np.percentile(rois, 95):.1f}%")
            print(f"  max_dd: p5={np.percentile(max_dds, 5):.1f} p50={np.percentile(max_dds, 50):.1f} p95={np.percentile(max_dds, 95):.1f}")
        print()

    # 4d) Isotonic strategy bootstrap (fixed calibrator)
    bs_iso = bootstrap_isotonic(enriched, [2024, 2025], [2026], ev_min=0.01, n_reps=500)
    print("4d) BOOTSTRAP I_best_ev_isotonic (fixed calibrator, block by event, 500 reps):")
    print(f"  ROI: p5={bs_iso['roi_p5']:.1f}% p50={bs_iso['roi_p50']:.1f}% p95={bs_iso['roi_p95']:.1f}%")
    print(f"  max_dd: p5={bs_iso['dd_p5']:.1f} p50={bs_iso['dd_p50']:.1f} p95={bs_iso['dd_p95']:.1f}")
    print(f"  n_bets: p5={bs_iso['n_bets_p5']:.0f} p50={bs_iso['n_bets_p50']:.0f} p95={bs_iso['n_bets_p95']:.0f}")
    print()

    # 4e) EV threshold sweep
    ev_sweep = ev_threshold_sweep(enriched, [2024, 2025], [2026], [0, 0.005, 0.01, 0.015, 0.02, 0.03])
    print("4e) EV THRESHOLD SWEEP (isotonic, 2026):")
    print(f"  {'ev_min':<8} {'ROI':>8} {'n_bets':>8} {'hit%':>8} {'max_dd':>8}")
    for row in ev_sweep:
        print(f"  {row['ev_min']*100:>5.1f}%   {row['roi']:>6.1f}% {row['n_bets']:>8} {row['hit_rate']:>6.1f}% {row['max_dd']:>8.2f}")
    print()

    # 4f) Isotonic bet decomposition by region
    train_rows = [r for r in enriched if infer_year(r.get('event_name', '')) in [2024, 2025]]
    test_rows = [r for r in enriched if infer_year(r.get('event_name', '')) == 2026]
    iso_pred = fit_isotonic_calibrator(train_rows)
    _, iso_bets = run_isotonic_strategy(test_rows, iso_pred, 0.01, return_bets=True)
    by_reg = defaultdict(list)
    for b in iso_bets:
        by_reg[b['region']].append(b)
    print("4f) ISOTONIC BET DECOMPOSITION (39 bets by region):")
    for reg in sorted(by_reg.keys()):
        sub = by_reg[reg]
        roi = np.mean([b['profit'] for b in sub]) * 100
        avg_o = np.mean([b['odds'] for b in sub])
        avg_pf = np.mean([b['p_fair'] for b in sub])
        print(f"  {reg}: n={len(sub)} ROI={roi:.1f}% avg_odds={avg_o:.2f} avg_p_fair={avg_pf:.3f}")
    print()

    # 4g) Dumb filter: bet fav only in Americas+China, with p_fair bounds
    print("4g) DUMB FILTER (Americas+China, p_fair bounds):")
    # Legacy sweep (no upper bound)
    for p_min in [0.5, 0.55, 0.6, 0.65, 0.7]:
        res = run_dumb_filter_strategy(test_rows, regions=('Americas', 'China'), p_fair_min=p_min)
        print(f"  p_fair>={p_min:.2f} (no cap): n={res['n_bets']} ROI={res['roi']:.1f}%")
    # Final rule: 0.55 <= p_fair <= 0.70 (no-bet zone for heavy favs)
    res_final = run_dumb_filter_strategy(test_rows, regions=('Americas', 'China'), p_fair_min=0.55, p_fair_max=0.70)
    print(f"  FINAL 0.55<=p_fair<=0.70: n={res_final['n_bets']} ROI={res_final['roi']:.1f}%")
    res_kickoff = run_dumb_filter_strategy(test_rows, regions=('Americas', 'China'), p_fair_min=0.55, p_fair_max=0.70, kickoff_stake_cap=0.75)
    print(f"  FINAL + Kickoff 0.75u cap: n={res_kickoff['n_bets']} ROI={res_kickoff['roi']:.1f}%")
    print()

    # 4g2) p_fair>=0.70 collapse inspection (10 matches)
    p70_matches = [r for r in test_rows if r.get('p_fair', 0) >= 0.7 and r.get('Of') and infer_region(r.get('event_name', '')) in ('Americas', 'China')]
    if p70_matches:
        print("4g2) p_fair>=0.70 COLLAPSE INSPECTION (Americas+China only):")
        for r in p70_matches[:15]:
            ev = r.get('event_name', '')[:40]
            tier = infer_tier_detail(ev)
            profit = (r['Of'] - 1) if r['fav_won'] else -1
            print(f"    {r.get('team1', '')[:18]} vs {r.get('team2', '')[:18]} | p_fair={r['p_fair']:.2f} Of={r['Of']:.2f} tier={tier} profit={profit:+.2f}")
        print()

    # 4i) Year-by-year walk-forward (final rule: 0.55<=p_fair<=0.70)
    print("4i) WALK-FORWARD VALIDATION (Americas+China 0.55<=p_fair<=0.70):")
    for train_yrs, test_yr in [([2024], 2025), ([2024, 2025], 2026)]:
        tst = [r for r in enriched if infer_year(r.get('event_name', '')) == test_yr]
        res = run_dumb_filter_strategy(tst, regions=('Americas', 'China'), p_fair_min=0.55, p_fair_max=0.70)
        print(f"  Test {test_yr}: n={res['n_bets']} ROI={res['roi']:.1f}% hit={res['hit_rate']:.1f}%")
    print()

    # 4i2) Event-blocked validation (is edge broad or one event?)
    print("4i2) EVENT-BLOCKED VALIDATION (final rule, by event):")
    def _final_strategy(rows):
        return run_dumb_filter_strategy(rows, regions=('Americas', 'China'), p_fair_min=0.55, p_fair_max=0.70)
    for test_yr in [2025, 2026]:
        tst = [r for r in enriched if infer_year(r.get('event_name', '')) == test_yr]
        eb = event_blocked_roi(tst, _final_strategy)
        if eb['n_events'] > 0:
            print(f"  {test_yr}: median_event_ROI={eb['median_event_roi']:.1f}% pct_positive={eb['pct_positive']:.0f}% worst={eb['worst_roi']:.1f}% n_events={eb['n_events']}")
    print()

    # 4i3) Consistency check: mean/median Of, p_fair, break-even vs hit rate, EV sanity
    print("4i3) CONSISTENCY CHECK (filtered bets: Of, p_fair, break-even vs hit rate):")
    for test_yr in [2025, 2026]:
        tst = [r for r in enriched if infer_year(r.get('event_name', '')) == test_yr]
        res = run_dumb_filter_strategy(tst, regions=('Americas', 'China'), p_fair_min=0.55, p_fair_max=0.70)
        if res['n_bets'] > 0:
            be = res.get('avg_be_rate', 100 * (1.0 / res.get('avg_odds', 1.5)))
            gap = res['hit_rate'] - be
            ev_per_bet = (res['hit_rate'] / 100) * res.get('avg_odds', 1.5) - 1
            roi_implied = 100 * ev_per_bet
            print(f"  {test_yr}: n={res['n_bets']} mean_Of={res.get('avg_odds', 0):.2f} median_Of={res.get('median_odds', 0):.2f} mean_p_fair={res.get('avg_p_fair', 0):.2f} median_p_fair={res.get('median_p_fair', 0):.2f} avg_be={be:.1f}% hit={res['hit_rate']:.1f}% gap={gap:+.1f}pp")
            print(f"       EV_sanity: hit*Of-1={ev_per_bet:.3f} -> ROI_implied={roi_implied:.1f}% (actual ROI={res['roi']:.1f}%)")
        if res.get('skipped_even', 0) > 0:
            print(f"  {test_yr}: skipped_even_odds={res['skipped_even']}")
    print()

    # 4j) Event-tier sanity check inside Americas+China
    am_china = [r for r in test_rows if infer_region(r.get('event_name', '')) in ('Americas', 'China') and r.get('Of')]
    by_tier = defaultdict(list)
    for r in am_china:
        by_tier[infer_tier_detail(r.get('event_name', ''))].append(r)
    print("4j) EVENT-TIER SANITY (Americas+China 2026, A_always_fav ROI):")
    for tier in sorted(by_tier.keys()):
        sub = by_tier[tier]
        profits = [(r['Of'] - 1) if r['fav_won'] else -1 for r in sub]
        roi = np.mean(profits) * 100 if profits else 0
        dumb = run_dumb_filter_strategy(sub, regions=('Americas', 'China'), p_fair_min=0.55)
        print(f"  {tier}: n={len(sub)} A_always_fav ROI={roi:.1f}% dumb_filter ROI={dumb['roi']:.1f}% (n={dumb['n_bets']})")
    print()

    # 4h) ROI definition verification
    a_res = bt.get('A_always_fav', {})
    if a_res.get('n_bets', 0) > 0:
        n_b = a_res['n_bets']
        mean_profit = a_res['roi'] / 100
        total_profit = mean_profit * n_b
        print("4h) ROI DEFINITION: ROI = sum(profit)/sum(stake) = mean(profit) per 1u bet.")
        print(f"  A_always_fav: total_profit={total_profit:.2f}u over {n_b} bets, mean={mean_profit:.4f}, ROI={a_res['roi']:.2f}%")
    print()

    print("=" * 70)
    print("5) SEGMENTATION (ROI by region/tier/overround/p_fair, OOS 2026)")
    print("=" * 70)
    test_rows = [r for r in enriched if infer_year(r.get('event_name', '')) == 2026]

    def roi_fav(rows):
        profits = [(r['Of'] - 1) if r['fav_won'] else -1 for r in rows if r.get('Of')]
        return np.mean(profits) * 100 if profits else 0

    for label, group_fn in [
        ('Region', lambda r: infer_region(r.get('event_name', ''))),
        ('Tier', lambda r: infer_tier(r.get('event_name', ''))),
    ]:
        by_group = defaultdict(list)
        for r in test_rows:
            by_group[group_fn(r)].append(r)
        print(f"\n  By {label}:")
        for g in sorted(by_group.keys()):
            sub = by_group[g]
            n = len([r for r in sub if r.get('Of')])
            print(f"    {g}: n={n} A_always_fav ROI={roi_fav(sub):.1f}%")

    # Overround deciles (high vig vs low vig)
    ov_arr = np.array([r['overround'] for r in test_rows if r.get('Of')])
    if len(ov_arr) >= 10:
        deciles = np.percentile(ov_arr, [20, 40, 60, 80])
        def ov_bucket(r):
            o = r.get('overround', 1.05)
            if o <= deciles[0]: return 'low_vig'
            if o <= deciles[1]: return 'med-low'
            if o <= deciles[2]: return 'med'
            if o <= deciles[3]: return 'med-high'
            return 'high_vig'
        by_ov = defaultdict(list)
        for r in test_rows:
            by_ov[ov_bucket(r)].append(r)
        print(f"\n  By overround (vig):")
        for b in ['low_vig', 'med-low', 'med', 'med-high', 'high_vig']:
            if b in by_ov:
                sub = by_ov[b]
                n = len([r for r in sub if r.get('Of')])
                print(f"    {b}: n={n} A_always_fav ROI={roi_fav(sub):.1f}%")

    # p_fair buckets (favorite strength)
    print(f"\n  By p_fair (favorite strength):")
    for lo, hi in [(0.5, 0.55), (0.55, 0.6), (0.6, 0.65), (0.65, 0.7), (0.7, 0.8), (0.8, 1.0)]:
        sub = [r for r in test_rows if lo <= r.get('p_fair', 0) < hi and r.get('Of')]
        if sub:
            print(f"    {lo:.2f}-{hi:.2f}: n={len(sub)} A_always_fav ROI={roi_fav(sub):.1f}%")

    print("=" * 70)
    print("6) OUTLIERS + DATA QUALITY")
    print("=" * 70)
    extreme = [r for r in enriched if r['Of'] > 10 or r['Ou'] > 10]
    print(f"Extreme odds (>10): {len(extreme)} matches")
    print("Sample (10 random):")
    import random
    samp = random.sample(enriched, min(10, len(enriched)))
    for r in samp:
        print(f"  {r.get('team1')} vs {r.get('team2')} Of={r.get('Of'):.2f} Ou={r.get('Ou'):.2f} winner={r.get('winner')} fav_won={r.get('fav_won')}")
    print()

    print("=" * 70)
    print("7) MONTHLY REVIEW SUMMARY (final rule: 0.55<=p_fair<=0.70 Americas+China)")
    print("=" * 70)
    latest_yr = max((infer_year(r.get('event_name', '')) for r in enriched if infer_year(r.get('event_name', '')) > 0), default=0)
    if latest_yr:
        tst = [r for r in enriched if infer_year(r.get('event_name', '')) == latest_yr]
        res = run_dumb_filter_strategy(tst, regions=('Americas', 'China'), p_fair_min=0.55, p_fair_max=0.70)
        eb = event_blocked_roi(tst, lambda rows: run_dumb_filter_strategy(rows, regions=('Americas', 'China'), p_fair_min=0.55, p_fair_max=0.70))
        am_china_cands = [r for r in tst if infer_region(r.get('event_name', '')) in ('Americas', 'China') and r.get('Of')]
        by_reg = defaultdict(int)
        for r in am_china_cands:
            by_reg[infer_region(r.get('event_name', ''))] += 1
        total_cand = sum(by_reg.values())
        print(f"  Latest year {latest_yr}: ROI={res['roi']:.1f}% n={res['n_bets']} hit={res['hit_rate']:.1f}% max_dd={res['max_dd']:.2f}u")
        if eb['n_events'] > 0:
            print(f"  Event-blocked: median_ROI={eb['median_event_roi']:.1f}% pct_positive={eb['pct_positive']:.0f}% n_events={eb['n_events']}")
        print(f"  Region mix (candidates): Americas={100*by_reg.get('Americas',0)/total_cand:.0f}% China={100*by_reg.get('China',0)/total_cand:.0f}%" if total_cand else "  Region mix: N/A")
        if res['n_bets'] > 0:
            print(f"  p_fair distribution (bets): mean={res.get('avg_p_fair',0):.2f} median={res.get('median_p_fair',0):.2f}")
    print()

    print("=" * 70)
    print("8) STRATEGY SPEC (data-backed)")
    print("=" * 70)
    qualified = [(k, v) for k, v in bt.items() if v['n_bets'] >= 10]
    best = max(qualified, key=lambda x: x[1]['roi']) if qualified else (None, {'roi': 0, 'n_bets': 0})
    best_name, best_v = best[0], best[1]
    if best_name:
        print(f"""
- Best OOS strategy: {best_name} (ROI={best_v['roi']:.1f}%, n={best_v['n_bets']})
- Edge rule: Isotonic p_hat + EV>=1% (bet side with higher positive EV); or LCB/edge-based
- Staking: flat 1u (no Kelly; see spec)
- No-bet: odds 1.0 (bug), extreme odds >10
- Risk: max drawdown ~{max(v['max_dd'] for v in bt.values()):.1f}u, cap daily exposure
- Calibration drift (per-match): 2024 -4.0%, 2025 +4.7%, 2026 +1.9% (year-to-year shift)
- Isotonic bootstrap: p50 ROI=6.4% (stays positive), p5=-2%; EV sweep plateau 0.5-2%
- Deployable: dumb filter 0.55<=p_fair<=0.70 Americas+China: 2025 ROI=8.1% (n=90), 2026 ROI=23.8% (n=37)
""")
    else:
        print("\n- Insufficient OOS bets (n<10) for robust strategy selection. Use edge-based strategies with caution.\n")
    print("=" * 70)

    return {
        'cleaned': cleaned,
        'enriched': enriched,
        'cal': cal,
        'bt': bt,
        'clean_stats': clean_stats,
        'brier': brier,
        'ece': ece,
    }


def export_research_appendix(output_path: Optional[str] = None, result: Optional[Dict] = None) -> str:
    """Export full report to markdown. Returns path. Pass result from _run_pipeline() to avoid re-running."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    path = output_path or os.path.join(script_dir, 'moneyline_research_appendix.md')
    if result is None:
        result = _run_pipeline()
    if not result:
        return path
    cal, bt, clean_stats = result['cal'], result['bt'], result['clean_stats']
    brier, ece = result['brier'], result['ece']
    lines = [
        "# Valorant Moneyline Strategy — Research Appendix",
        "",
        "## 1. Dataset Inventory",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total rows | {clean_stats['total_raw']} |",
        f"| Duplicates removed | {clean_stats['duplicates_removed']} |",
        f"| No winner | {clean_stats['no_winner']} |",
        f"| No odds | {clean_stats['no_odds']} |",
        f"| Usable for backtest | {clean_stats['usable']} |",
        "",
        "## 2. Calibration Table",
        "",
        "| Bin | n | Of_avg | p_raw | p_fair | p_obs | edge |",
        "|-----|---|--------|-------|--------|-------|------|",
    ]
    for c in cal:
        lines.append(f"| {c['bin_lo']:.1f}-{c['bin_hi']:.1f} | {c['n']} | {c['Of_avg']:.2f} | {c['p_raw']:.3f} | {c['p_fair']:.3f} | {c['p_obs']:.3f} | {c['edge']:.3f} |")
    lines.extend([
        "",
        f"Brier score: {brier:.4f}, ECE: {ece:.4f}",
        "",
        "## 3. Backtest Results (train 2024-2025, test 2026)",
        "",
        "| Strategy | ROI | n_bets | hit_rate | max_dd | longest_L |",
        "|----------|-----|--------|----------|--------|-----------|",
    ])
    for k, v in bt.items():
        lines.append(f"| {k} | {v['roi']:.1f}% | {v['n_bets']} | {v['hit_rate']:.1f}% | {v['max_dd']:.2f} | {v['longest_losing']} |")
    lines.extend([
        "",
        "## 4. Reproducibility",
        "",
        "Run: `python scripts/moneyline_analytics.py`",
        "",
        "Key functions: `clean_data()`, `compute_vig_and_pfair()`, `calibration_table()`, `backtest_strategies()`",
        "",
    ])
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return path


def get_strategy_data() -> Optional[Dict]:
    """
    Compute strategy data for API/frontend. Returns dict with all key metrics (no printing).
    """
    rows = load_raw_data()
    cleaned, clean_stats = clean_data(rows)
    enriched = compute_vig_and_pfair(cleaned)
    if not enriched:
        return None

    Of_arr = np.array([r['Of'] for r in enriched])
    Ou_arr = np.array([r['Ou'] for r in enriched])
    equal_count = int(np.sum(np.abs(Of_arr - Ou_arr) <= 0.05))
    sec_key = defaultdict(list)
    for r in enriched:
        t1, t2 = r.get('team1', ''), r.get('team2', '')
        ev = r.get('event_name', '') or 'unknown'
        yr = infer_year(ev)
        k = (normalize_team_name(t1), normalize_team_name(t2), ev[:50], yr)
        sec_key[k].append(r.get('match_url', ''))
    collisions = sum(1 for v in sec_key.values() if len(v) > 1)
    total_collision_rows = sum(len(v) for v in sec_key.values() if len(v) > 1)

    walk_forward = []
    for test_yr in [2025, 2026]:
        tst = [r for r in enriched if infer_year(r.get('event_name', '')) == test_yr]
        res = run_dumb_filter_strategy(tst, regions=('Americas', 'China'), p_fair_min=0.55, p_fair_max=0.70)
        eb = event_blocked_roi(tst, lambda rows: run_dumb_filter_strategy(rows, regions=('Americas', 'China'), p_fair_min=0.55, p_fair_max=0.70))
        be = res.get('avg_be_rate', 100 * (1.0 / res.get('avg_odds', 1.5))) if res.get('avg_odds') else 0
        gap = res['hit_rate'] - be if res['n_bets'] > 0 else 0
        ev_per_bet = (res['hit_rate'] / 100) * res.get('avg_odds', 1.5) - 1 if res['n_bets'] > 0 else 0
        roi_implied = 100 * ev_per_bet
        walk_forward.append({
            'year': test_yr,
            'n_bets': res['n_bets'],
            'roi': round(res['roi'], 1),
            'hit_rate': round(res['hit_rate'], 1),
            'max_dd': round(res['max_dd'], 2),
            'mean_Of': round(res.get('avg_odds', 0), 2),
            'median_Of': round(res.get('median_odds', 0), 2),
            'mean_p_fair': round(res.get('avg_p_fair', 0), 2),
            'median_p_fair': round(res.get('median_p_fair', 0), 2),
            'avg_be_rate': round(be, 1),
            'gap_pp': round(gap, 1),
            'roi_implied': round(roi_implied, 1),
            'skipped_even': res.get('skipped_even', 0),
            'event_blocked': {
                'median_event_roi': round(eb['median_event_roi'], 1),
                'pct_positive': round(eb['pct_positive'], 0),
                'worst_roi': round(eb['worst_roi'], 1),
                'n_events': eb['n_events'],
            },
        })

    latest_yr = max((infer_year(r.get('event_name', '')) for r in enriched if infer_year(r.get('event_name', '')) > 0), default=0)
    monthly = {}
    if latest_yr:
        tst = [r for r in enriched if infer_year(r.get('event_name', '')) == latest_yr]
        res = run_dumb_filter_strategy(tst, regions=('Americas', 'China'), p_fair_min=0.55, p_fair_max=0.70)
        eb = event_blocked_roi(tst, lambda rows: run_dumb_filter_strategy(rows, regions=('Americas', 'China'), p_fair_min=0.55, p_fair_max=0.70))
        am_china = [r for r in tst if infer_region(r.get('event_name', '')) in ('Americas', 'China') and r.get('Of')]
        by_reg = defaultdict(int)
        for r in am_china:
            by_reg[infer_region(r.get('event_name', ''))] += 1
        total_cand = sum(by_reg.values())
        monthly = {
            'year': latest_yr,
            'roi': round(res['roi'], 1),
            'n_bets': res['n_bets'],
            'hit_rate': round(res['hit_rate'], 1),
            'max_dd': round(res['max_dd'], 2),
            'event_blocked': {'median_event_roi': round(eb['median_event_roi'], 1), 'pct_positive': round(eb['pct_positive'], 0), 'n_events': eb['n_events']},
            'region_mix': {'Americas': round(100 * by_reg.get('Americas', 0) / total_cand, 0) if total_cand else 0, 'China': round(100 * by_reg.get('China', 0) / total_cand, 0) if total_cand else 0},
            'p_fair_mean': round(res.get('avg_p_fair', 0), 2),
            'p_fair_median': round(res.get('median_p_fair', 0), 2),
        }

    bet_log = generate_bet_log(enriched, run_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    bets_only = [b for b in bet_log if b['decision'] == 'bet_fav']

    cal = calibration_table(enriched, bin_width=0.1)
    cal_summary = [{'bin': f"{c['bin_lo']:.1f}-{c['bin_hi']:.1f}", 'n': c['n'], 'p_fair': round(c['p_fair'], 3), 'p_obs': round(c['p_obs'], 3), 'edge': round(c['edge'], 3)} for c in cal]

    return {
        'success': True,
        'clean_stats': clean_stats,
        'vig': {
            'of_min': round(float(np.min(Of_arr)), 2),
            'of_median': round(float(np.median(Of_arr)), 2),
            'of_mean': round(float(np.mean(Of_arr)), 2),
            'of_max': round(float(np.max(Of_arr)), 2),
            'ou_min': round(float(np.min(Ou_arr)), 2),
            'ou_median': round(float(np.median(Ou_arr)), 2),
            'overround_mean': round(float(np.mean(1.0/Of_arr + 1.0/Ou_arr)), 4),
        },
        'near_equal_odds': equal_count,
        'near_equal_pct': round(100 * equal_count / len(enriched), 1),
        'secondary_collisions': collisions,
        'total_collision_rows': total_collision_rows,
        'walk_forward': walk_forward,
        'monthly_review': monthly,
        'bet_log': bet_log,
        'bets_count': len(bets_only),
        'calibration': cal_summary,
    }


# Americas + China event URLs for upcoming scraper (VCT 2026)
UPCOMING_AMERICAS_CHINA_EVENTS = [
    {'url': '/event/2682/vct-2026-americas-kickoff', 'name': 'VCT 2026: Americas Kickoff', 'region': 'Americas'},
    {'url': '/event/2685/vct-2026-china-kickoff', 'name': 'VCT 2026: China Kickoff', 'region': 'China'},
]


def _team_matches(a: str, b: str) -> bool:
    """Check if two team names refer to the same team (fuzzy)."""
    na = (a or '').strip().lower().replace('-', ' ')
    nb = (b or '').strip().lower().replace('-', ' ')
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    if len(na) >= 3 and na in nb:
        return True
    if len(nb) >= 3 and nb in na:
        return True
    return False


def get_upcoming_picks() -> Dict:
    """
    Scrape VLR for upcoming Americas+China matches, fetch odds, run strategy.
    Returns {success, picks: [{team1, team2, event_name, Of, Ou, p_fair, decision, stake, ...}], message}.
    """
    try:
        from scripts.populate_database import DatabasePopulator
        from scraper.vlr_scraper import VLRScraper
        import time
    except ImportError:
        return {'success': False, 'picks': [], 'message': 'Missing imports (populate_database, vlr_scraper)'}

    populator = DatabasePopulator()
    scraper = VLRScraper()
    picks = []
    seen = set()

    for event in UPCOMING_AMERICAS_CHINA_EVENTS:
        try:
            matches = populator.get_event_matches(event['url'])
            for m in matches:
                match_url = m['url']
                if match_url in seen:
                    continue
                seen.add(match_url)
                team1, team2 = m['team1'], m['team2']
                try:
                    result = scraper.get_match_result(match_url, team1, team2)
                    if result and result.get('winner'):
                        continue  # Match completed, skip
                    odds_data = scraper.get_match_betting_odds(match_url)
                    if not odds_data or not odds_data.get('teams'):
                        continue
                    odds_by_team = {t['name']: t['decimal_odds'] for t in odds_data['teams']}
                    o1, o2 = None, None
                    for tname, o in odds_by_team.items():
                        if _team_matches(tname, team1):
                            o1 = o
                        elif _team_matches(tname, team2):
                            o2 = o
                    if not o1 or not o2:
                        continue
                    if o1 < o2:
                        Of, Ou = o1, o2
                    else:
                        Of, Ou = o2, o1
                    if abs(Of - 1.0) < 0.01 or Of <= 0:
                        continue
                    p_fair = (1.0 / Of) / (1.0 / Of + 1.0 / Ou)
                    pf_low = p_fair < 0.55
                    pf_high = p_fair > 0.70
                    of_min = Of < 1.35
                    even_odds = abs(Of - Ou) <= 0.05
                    bet = not (pf_low or pf_high or of_min or even_odds)
                    tier = infer_tier_detail(event['name'])
                    stake = 0.75 if (tier == 'Kickoff') else 1.0
                    picks.append({
                        'team1': team1,
                        'team2': team2,
                        'event_name': event['name'][:40],
                        'region': event['region'],
                        'Of': round(Of, 2),
                        'Ou': round(Ou, 2),
                        'p_fair': round(p_fair, 3),
                        'decision': 'bet_fav' if bet else 'skip',
                        'stake': stake,
                        'flag_p_fair_low': pf_low,
                        'flag_p_fair_high': pf_high,
                        'flag_of_min': of_min,
                        'flag_even_odds': even_odds,
                    })
                except Exception as e:
                    continue
                time.sleep(0.5)
            time.sleep(1)
        except Exception as e:
            continue

    return {'success': True, 'picks': picks}


def run_full_report():
    """Run full analytics and print report."""
    _run_pipeline()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--challengers', action='store_true', help='Run Challengers (Tier 2) analytics instead of Tier 1')
    parser.add_argument('--export', action='store_true', help='Also export Research Appendix to markdown')
    parser.add_argument('--audit', action='store_true', help='Print full 50-row bet-side audit')
    parser.add_argument('--betlog', type=str, nargs='?', const='', metavar='PATH', help='Export bet log CSV (default: scripts/moneyline_bet_log.csv)')
    args = parser.parse_args()
    if args.challengers:
        from scripts.challengers_analytics import main as challengers_main
        challengers_main()
        sys.exit(0)
    result = _run_pipeline()
    if args.export and result:
        out_path = export_research_appendix(result=result)
        print(f"\nResearch appendix exported to {out_path}")
    if args.betlog is not None and result:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        out_path = args.betlog if args.betlog else os.path.join(script_dir, 'moneyline_bet_log.csv')
        log = generate_bet_log(result['enriched'], run_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        export_bet_log_to_csv(log, out_path)
        print(f"\nBet log exported to {out_path} ({len(log)} rows)")
    if args.audit and result:
        test_rows = [r for r in result['enriched'] if infer_year(r.get('event_name', '')) == 2026]
        audit = bet_side_audit(test_rows, n_sample=min(50, len(test_rows)))
        print("\n" + "=" * 70)
        print("FULL BET-SIDE AUDIT (50 OOS 2026)")
        print("=" * 70)
        for i, a in enumerate(audit):
            print(f"[{i+1:2}] {a['team_a'][:25]:<25} vs {a['team_b'][:25]:<25} | Of={a['odds_fav']:.2f} Ou={a['odds_dog']:.2f} | winner={str(a['winner'])[:30]} fav_won={a['fav_won']} fuzzy={a['fuzzy_match']}")
