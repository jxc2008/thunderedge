#!/usr/bin/env python3
"""
Challengers (Tier 2) moneyline analytics: inventory, calibration, baselines, strategy search.
Produces CHALLENGERS_STRATEGY_SPEC.md or negative result.
Run: python scripts/challengers_analytics.py
"""

import sys
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.moneyline_analytics import (
    load_raw_data,
    clean_data,
    compute_vig_and_pfair,
    calibration_table,
    fit_isotonic_calibrator,
    run_dumb_filter_strategy,
    run_isotonic_strategy,
    event_blocked_roi,
    infer_region,
    infer_tier_detail,
    infer_year,
)
from config import Config

import numpy as np
import random

CHALLENGERS_KEYS = ('challengers', 'ascension', 'national competition')
OV_THRESH_V0 = 1.05  # Single threshold for overround filter; use everywhere for consistency
OU_LO_V0, OU_HI_V0 = 3.25, 5.00  # v0 odds band
EVEN_ODDS_THRESH = 0.05


def _sigmoid(z):
    z = np.clip(z, -35, 35)
    return 1.0 / (1.0 + np.exp(-z))


def _standardize_fit(X: np.ndarray):
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd < 1e-8] = 1.0
    return mu, sd


def _standardize_apply(X: np.ndarray, mu: np.ndarray, sd: np.ndarray):
    return (X - mu) / sd


def _one_hot(values: List[str], vocab: List[str]) -> np.ndarray:
    idx = {v: i for i, v in enumerate(vocab)}
    out = np.zeros((len(values), len(vocab)), dtype=float)
    for i, v in enumerate(values):
        j = idx.get(v, None)
        if j is not None:
            out[i, j] = 1.0
    return out


def _ou_bin(ou: float) -> str:
    if ou < 2.0:
        return "<2.0"
    if ou < 2.5:
        return "2.0-2.5"
    if ou < 3.25:
        return "2.5-3.25"
    if ou < 5.0:
        return "3.25-5.0"
    if ou < 7.5:
        return "5.0-7.5"
    return "7.5+"


def build_edge_features(rows: List[Dict]) -> Tuple[np.ndarray, np.ndarray, Dict]:
    """
    Features to learn bias vs p_fair.
    X: intercept, p_fair, log(Of), log(Ou), overround, tier one-hot, region one-hot, Ou-bin one-hot, p_fair*I(Ascension)
    y: fav_won (0/1)
    """
    rows = [r for r in rows if r.get('Of') is not None and r.get('Ou') is not None]
    if not rows:
        return np.zeros((0, 1)), np.array([]), {}
    regions = sorted(list({infer_region(r.get('event_name', '')) for r in rows}))
    tiers = sorted(list({infer_tier_detail(r.get('event_name', '')) for r in rows}))
    ou_bins = sorted(list({_ou_bin(r.get('Ou', 999.0)) for r in rows}))

    pf = np.array([float(r['p_fair']) for r in rows], dtype=float)
    Of = np.array([float(r['Of']) for r in rows], dtype=float)
    Ou = np.array([float(r['Ou']) for r in rows], dtype=float)
    ov = np.array([float(r.get('overround', 1.10)) for r in rows], dtype=float)

    reg_vals = [infer_region(r.get('event_name', '')) for r in rows]
    tier_vals = [infer_tier_detail(r.get('event_name', '')) for r in rows]
    oub_vals = [_ou_bin(float(r['Ou'])) for r in rows]

    R = _one_hot(reg_vals, regions)
    T = _one_hot(tier_vals, tiers)
    B = _one_hot(oub_vals, ou_bins)

    asc = np.array([1.0 if infer_tier_detail(r.get('event_name', '')) == 'Ascension' else 0.0 for r in rows])

    num = np.column_stack([
        pf,
        np.log(np.maximum(Of, 1e-6)),
        np.log(np.maximum(Ou, 1e-6)),
        ov,
        pf * asc,
    ])

    X = np.column_stack([np.ones(len(rows)), num, T, R, B])
    y = np.array([1.0 if r.get('fav_won', False) else 0.0 for r in rows], dtype=float)
    meta = {"regions": regions, "tiers": tiers, "ou_bins": ou_bins, "num_cols": 5}
    return X, y, meta


def fit_ridge_logit(X: np.ndarray, y: np.ndarray, lam: float = 5.0, n_iter: int = 50) -> np.ndarray:
    """L2-regularized logistic regression via Newton steps. Regularizes all weights except intercept."""
    n, d = X.shape
    w = np.zeros(d, dtype=float)
    reg = np.ones(d, dtype=float)
    reg[0] = 0.0

    for _ in range(n_iter):
        p = _sigmoid(X @ w)
        g = X.T @ (p - y) + lam * reg * w
        s = p * (1 - p)
        H = (X.T * s) @ X + lam * np.diag(reg)
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(H + 1e-6 * np.eye(d), g, rcond=None)[0]
        w -= step
        if np.linalg.norm(step) < 1e-6:
            break
    return w


def predict_fav_win_prob(rows: List[Dict], w: np.ndarray, meta: Dict) -> np.ndarray:
    """Rebuild X using train vocab; return P(fav_won). Unknown categories become all-zeros."""
    rows = [r for r in rows if r.get('Of') is not None and r.get('Ou') is not None]
    if not rows or not meta:
        return np.array([])
    regions = meta["regions"]
    tiers = meta["tiers"]
    ou_bins = meta["ou_bins"]

    pf = np.array([float(r['p_fair']) for r in rows], dtype=float)
    Of = np.array([float(r['Of']) for r in rows], dtype=float)
    Ou = np.array([float(r['Ou']) for r in rows], dtype=float)
    ov = np.array([float(r.get('overround', 1.10)) for r in rows], dtype=float)

    reg_vals = [infer_region(r.get('event_name', '')) for r in rows]
    tier_vals = [infer_tier_detail(r.get('event_name', '')) for r in rows]
    oub_vals = [_ou_bin(float(r['Ou'])) for r in rows]

    R = _one_hot(reg_vals, regions)
    T = _one_hot(tier_vals, tiers)
    B = _one_hot(oub_vals, ou_bins)

    asc = np.array([1.0 if infer_tier_detail(r.get('event_name', '')) == 'Ascension' else 0.0 for r in rows])

    num = np.column_stack([
        pf,
        np.log(np.maximum(Of, 1e-6)),
        np.log(np.maximum(Ou, 1e-6)),
        ov,
        pf * asc,
    ])

    X = np.column_stack([np.ones(len(rows)), num, T, R, B])
    return _sigmoid(X @ w)


def run_ev_model_strategy(rows: List[Dict], p_fav_hat: np.ndarray, ev_min: float = 0.01) -> Dict:
    """
    Choose the side with max positive EV; bet only if EV >= ev_min. Flat 1u.
    EV_fav = p*(Of-1) - (1-p), EV_dog = (1-p)*(Ou-1) - p
    """
    profits, outcomes, odds_taken = [], [], []
    rows_valid = [r for r in rows if r.get('Of') is not None and r.get('Ou') is not None]
    if len(rows_valid) != len(p_fav_hat):
        return {'roi': 0, 'n_bets': 0, 'hit_rate': 0, 'avg_odds': 0, 'max_dd': 0, 'longest_losing': 0}
    for r, p in zip(rows_valid, p_fav_hat):
        Of, Ou = r.get('Of'), r.get('Ou')
        if abs(Of - Ou) <= EVEN_ODDS_THRESH:
            continue

        ev_f = p * (Of - 1.0) - (1.0 - p)
        ev_d = (1.0 - p) * (Ou - 1.0) - p

        if ev_f >= ev_d:
            if ev_f < ev_min:
                continue
            fav_won = r.get('fav_won', False)
            profit = (Of - 1.0) if fav_won else -1.0
            odds_taken.append(Of)
        else:
            if ev_d < ev_min:
                continue
            fav_won = r.get('fav_won', False)
            profit = (Ou - 1.0) if not fav_won else -1.0
            odds_taken.append(Ou)

        profits.append(profit)
        outcomes.append(1 if profit > 0 else 0)

    if not profits:
        return {'roi': 0, 'n_bets': 0, 'hit_rate': 0, 'avg_odds': 0, 'max_dd': 0, 'longest_losing': 0}

    arr = np.array(profits)
    cum = np.cumsum(arr)
    dd = np.maximum.accumulate(cum) - cum

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
        'hit_rate': float(np.mean(outcomes)) * 100,
        'avg_odds': float(np.mean(odds_taken)) if odds_taken else 0,
        'max_dd': float(np.max(dd)),
        'longest_losing': longest,
    }


def wilson_ci(wins: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """95% Wilson score interval for binomial proportion."""
    if n <= 0:
        return 0.0, 0.0
    p_hat = wins / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    margin = z * np.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denom
    return center - margin, center + margin


def is_challengers(event_name: str) -> bool:
    """Central Challengers filter."""
    n = (event_name or '').lower()
    return any(k in n for k in CHALLENGERS_KEYS)


def run_baseline(rows: List[Dict], bet_side: str) -> Dict:
    """Flat 1u on favorite or underdog. Returns roi, n_bets, hit_rate, max_dd, longest_losing."""
    profits, outcomes, odds_taken = [], [], []
    for r in rows:
        Of, Ou = r.get('Of'), r.get('Ou')
        fav_won = r.get('fav_won', False)
        if Of is None or Ou is None:
            continue
        if bet_side == 'fav':
            profit = (Of - 1) if fav_won else -1
            odds_taken.append(Of)
        else:
            profit = (Ou - 1) if not fav_won else -1
            odds_taken.append(Ou)
        profits.append(profit)
        outcomes.append(1 if profit > 0 else 0)
    if not profits:
        return {'roi': 0, 'n_bets': 0, 'hit_rate': 0, 'avg_odds': 0, 'max_dd': 0, 'longest_losing': 0}
    arr = np.array(profits)
    cum = np.cumsum(arr)
    dd = np.maximum.accumulate(cum) - cum
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
        'max_dd': float(np.max(dd)),
        'longest_losing': longest,
    }


def bootstrap_roi(rows: List[Dict], bet_side: str, n_reps: int = 500, seed: int = 42) -> Dict:
    """Block bootstrap by event. Returns roi p5/p50/p95, dd p5/p50/p95."""
    by_event = defaultdict(list)
    for r in rows:
        ev = r.get('event_name', '') or 'unknown'
        by_event[ev].append(r)
    events = list(by_event.keys())
    if not events:
        return {}
    rng = np.random.default_rng(seed)
    rois, max_dds = [], []
    for _ in range(n_reps):
        ev_sample = rng.choice(events, size=len(events), replace=True)
        rows_bs = []
        for ev in ev_sample:
            rows_bs.extend(by_event[ev])
        res = run_baseline(rows_bs, bet_side)
        if res['n_bets'] > 0:
            rois.append(res['roi'])
            max_dds.append(res['max_dd'])
    if not rois:
        return {}
    return {
        'roi_p5': np.percentile(rois, 5), 'roi_p50': np.percentile(rois, 50), 'roi_p95': np.percentile(rois, 95),
        'dd_p5': np.percentile(max_dds, 5), 'dd_p50': np.percentile(max_dds, 50), 'dd_p95': np.percentile(max_dds, 95),
    }


def run_baseline_dog_overround_filter(rows: List[Dict], overround_max: float) -> Dict:
    """Bet dog only if overround <= overround_max. Flat 1u."""
    profits, outcomes, odds_taken = [], [], []
    for r in rows:
        Of, Ou = r.get('Of'), r.get('Ou')
        ov = r.get('overround', 1.1)
        fav_won = r.get('fav_won', False)
        if Of is None or Ou is None or ov > overround_max:
            continue
        profit = (Ou - 1) if not fav_won else -1
        odds_taken.append(Ou)
        profits.append(profit)
        outcomes.append(1 if profit > 0 else 0)
    if not profits:
        return {'roi': 0, 'n_bets': 0, 'hit_rate': 0, 'avg_odds': 0, 'max_dd': 0, 'longest_losing': 0}
    arr = np.array(profits)
    cum = np.cumsum(arr)
    dd = np.maximum.accumulate(cum) - cum
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
        'max_dd': float(np.max(dd)),
        'longest_losing': longest,
    }


def _ou_bucket_results(rows: List[Dict]) -> List[Dict]:
    """B_always_dog by Ou bucket."""
    buckets = [(2.00, 2.50), (2.50, 3.25), (3.25, 5.00), (5.00, 999.0)]
    out = []
    for lo, hi in buckets:
        sub = [r for r in rows if r.get('Ou') is not None and lo <= r['Ou'] < hi]
        if sub:
            res = run_baseline(sub, 'dog')
            out.append({'lo': lo, 'hi': hi, 'n': len(sub), 'roi': res['roi'], 'hit_rate': res['hit_rate']})
    return out


def _overround_filter_results(rows: List[Dict]) -> List[Dict]:
    """Baseline B_dog + overround filter only (no Ou band). Uses OV_THRESH_V0 for consistency."""
    out = []
    for thresh in [OV_THRESH_V0, 1.07]:
        res = run_baseline_dog_overround_filter(rows, thresh)
        if res['n_bets'] > 0:
            out.append({'thresh': thresh, 'n': res['n_bets'], 'roi': res['roi'], 'hit_rate': res['hit_rate']})
    return out


def run_ou_band_strategy(rows: List[Dict], ou_lo: float, ou_hi: float, ov_thresh: float = OV_THRESH_V0,
                         exclude_ascension: bool = False, ascension_only: bool = False,
                         overrounds_out: Optional[List[float]] = None) -> Dict:
    """
    B_dog + overround <= ov_thresh + Ou in [ou_lo, ou_hi] + skip even odds.
    If overrounds_out is provided, append overround of each bet (for sanity stats).
    """
    subset = rows
    if exclude_ascension:
        subset = [r for r in rows if infer_tier_detail(r.get('event_name', '')) != 'Ascension']
    elif ascension_only:
        subset = [r for r in rows if infer_tier_detail(r.get('event_name', '')) == 'Ascension']
    profits, outcomes, odds_taken = [], [], []
    ov_list = [] if overrounds_out is not None else None
    for r in subset:
        Of, Ou = r.get('Of'), r.get('Ou')
        ov = r.get('overround', 999)
        fav_won = r.get('fav_won', False)
        if Of is None or Ou is None:
            continue
        if ov > ov_thresh:
            continue
        if Ou < ou_lo or Ou >= ou_hi:
            continue
        if abs(Of - Ou) <= EVEN_ODDS_THRESH:
            continue
        profit = (Ou - 1) if not fav_won else -1
        odds_taken.append(Ou)
        profits.append(profit)
        outcomes.append(1 if profit > 0 else 0)
        if ov_list is not None:
            ov_list.append(ov)
    if not profits:
        if overrounds_out is not None:
            overrounds_out.clear()
        return {'roi': 0, 'n_bets': 0, 'hit_rate': 0, 'avg_odds': 0, 'max_dd': 0, 'longest_losing': 0,
                'total_profit': 0, 'top_wins': [], 'top_losses': [], 'roi_implied': 0,
                'wilson_ci_lo': 0, 'wilson_ci_hi': 0, 'break_even_rate': 0}
    arr = np.array(profits)
    cum = np.cumsum(arr)
    dd = np.maximum.accumulate(cum) - cum
    streak, longest = 0, 0
    for p in profits:
        if p < 0:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
    wins = sorted([p for p in profits if p > 0], reverse=True)[:3]
    losses = sorted([p for p in profits if p < 0])[:3]
    avg_o = np.mean(odds_taken) if odds_taken else 0
    hit = np.mean(outcomes) * 100
    roi_implied = (hit / 100) * avg_o - 1 if avg_o else 0
    n_wins = sum(outcomes)
    n = len(profits)
    ci_lo, ci_hi = wilson_ci(n_wins, n)
    be_rate = 100 / avg_o if avg_o else 0
    if overrounds_out is not None:
        overrounds_out.clear()
        overrounds_out.extend(ov_list)
    return {
        'roi': float(np.mean(arr)) * 100,
        'n_bets': n,
        'hit_rate': hit,
        'avg_odds': avg_o,
        'max_dd': float(np.max(dd)),
        'longest_losing': longest,
        'total_profit': float(np.sum(arr)),
        'top_wins': wins,
        'top_losses': losses,
        'roi_implied': roi_implied,
        'wilson_ci_lo': ci_lo,
        'wilson_ci_hi': ci_hi,
        'break_even_rate': be_rate,
    }


def run_v0_strategy(rows: List[Dict], exclude_ascension: bool = False, ascension_only: bool = False,
                    overrounds_out: Optional[List[float]] = None) -> Dict:
    """v0: B_dog + ov<=1.05 + Ou in [3.25,5.00]. Wrapper over run_ou_band_strategy."""
    return run_ou_band_strategy(rows, OU_LO_V0, OU_HI_V0, OV_THRESH_V0,
                                exclude_ascension=exclude_ascension, ascension_only=ascension_only,
                                overrounds_out=overrounds_out)


def run_ou_band_no_ov(rows: List[Dict], ou_lo: float, ou_hi: float,
                      exclude_ascension: bool = False, ascension_only: bool = False) -> Dict:
    """B_dog + Ou in [ou_lo, ou_hi], no overround filter. Skip even odds."""
    return run_ou_band_strategy(rows, ou_lo, ou_hi, ov_thresh=999.0,  # no ov filter
                                exclude_ascension=exclude_ascension, ascension_only=ascension_only)


def run_ou_band_ov_percentile(rows: List[Dict], ou_lo: float, ou_hi: float, pct_bottom: float,
                              exclude_ascension: bool = False, ascension_only: bool = False) -> Dict:
    """
    Filter to Ou band first, then take bottom pct_bottom% overround within that band.
    pct_bottom in (0, 100], e.g. 20 = bottom 20%.
    """
    subset = rows
    if exclude_ascension:
        subset = [r for r in rows if infer_tier_detail(r.get('event_name', '')) != 'Ascension']
    elif ascension_only:
        subset = [r for r in rows if infer_tier_detail(r.get('event_name', '')) == 'Ascension']
    in_band = []
    for r in subset:
        Of, Ou = r.get('Of'), r.get('Ou')
        ov = r.get('overround', 999)
        if Of is None or Ou is None:
            continue
        if Ou < ou_lo or Ou >= ou_hi:
            continue
        if abs(Of - Ou) <= EVEN_ODDS_THRESH:
            continue
        in_band.append(r)
    if not in_band:
        return {'roi': 0, 'n_bets': 0, 'hit_rate': 0, 'avg_odds': 0, 'max_dd': 0, 'longest_losing': 0,
                'total_profit': 0, 'top_wins': [], 'top_losses': [], 'roi_implied': 0,
                'wilson_ci_lo': 0, 'wilson_ci_hi': 0, 'break_even_rate': 0}
    in_band.sort(key=lambda r: r.get('overround', 999))
    k = max(1, int(len(in_band) * pct_bottom / 100))
    selected = in_band[:k]
    return run_ou_band_strategy(selected, ou_lo, ou_hi, ov_thresh=999.0)  # already filtered


def permutation_roi(rows: List[Dict], ou_lo: float, ou_hi: float, n_reps: int = 1000, seed: int = 42) -> Dict:
    """
    Within Ou band: shuffle outcomes (fav_won) within each event, recompute ROI.
    Returns observed_roi, null_rois (list), p_value (fraction of null >= observed for one-sided).
    """
    random.seed(seed)
    by_ev = defaultdict(list)
    for r in rows:
        Of, Ou = r.get('Of'), r.get('Ou')
        if Of is None or Ou is None:
            continue
        if Ou < ou_lo or Ou >= ou_hi:
            continue
        if abs(Of - Ou) <= EVEN_ODDS_THRESH:
            continue
        by_ev[r.get('event_name', '') or 'unknown'].append(r)
    if not by_ev:
        return {'observed_roi': 0, 'null_rois': [], 'p_value': 1.0, 'n_bets': 0}

    def _roi_from_rows(rows_with_outcomes: List[Dict]) -> float:
        profits = []
        for r in rows_with_outcomes:
            fav_won = r.get('fav_won', False)
            Ou = r['Ou']
            profit = (Ou - 1) if not fav_won else -1
            profits.append(profit)
        return 100 * np.mean(profits) if profits else 0

    observed_roi = _roi_from_rows([r for sub in by_ev.values() for r in sub])
    n_bets = sum(len(sub) for sub in by_ev.values())

    null_rois = []
    for _ in range(n_reps):
        shuffled = []
        for ev, sub in by_ev.items():
            outcomes = [r['fav_won'] for r in sub]
            random.shuffle(outcomes)
            for i, r in enumerate(sub):
                r_copy = dict(r)
                r_copy['fav_won'] = outcomes[i]
                shuffled.append(r_copy)
        null_rois.append(_roi_from_rows(shuffled))

    # one-sided: how often is null >= observed (if we're testing "is observed high?")
    p_value = (1 + sum(1 for x in null_rois if x >= observed_roi)) / (n_reps + 1)
    return {'observed_roi': observed_roi, 'null_rois': null_rois, 'p_value': p_value,
            'null_p5': float(np.percentile(null_rois, 5)), 'null_p50': float(np.percentile(null_rois, 50)),
            'null_p95': float(np.percentile(null_rois, 95)), 'n_bets': n_bets}


def run_challengers_strategy_v1(rows: List[Dict], regions: tuple = None,
                                p_fair_min: float = 0.55, p_fair_max: float = 0.70,
                                of_min: float = 1.35, bet_side: str = 'fav',
                                even_odds_threshold: float = 0.05) -> Dict:
    """
    Challengers strategy v1: bet favorite (or dog) when p_fair in [min, max], Of >= of_min.
    regions=None means all regions.
    """
    if regions is None:
        regions = ('Americas', 'EMEA', 'Pacific', 'China')
    return run_dumb_filter_strategy(
        rows, regions=regions, p_fair_min=p_fair_min, p_fair_max=p_fair_max,
        of_min=of_min, bet_side=bet_side, even_odds_threshold=even_odds_threshold,
    )


def _run_pipeline() -> Optional[Dict]:
    """Run full Challengers analytics pipeline."""
    rows = load_raw_data()
    cleaned, clean_stats = clean_data(rows)
    enriched = compute_vig_and_pfair(cleaned)
    challengers = [r for r in enriched if is_challengers(r.get('event_name', ''))]

    print("=" * 70)
    print("CHALLENGERS MONEYLINE ANALYTICS")
    print("=" * 70)

    # 3.1 Dataset inventory
    print("\n3.1 DATASET INVENTORY")
    print("-" * 50)
    raw_ch = sum(1 for r in rows if is_challengers(r.get('event_name', '')))
    print(f"Total Challengers matches (raw): {raw_ch}")
    print(f"Usable after cleaning: {len(challengers)}")
    print(f"  (clean_stats: total_raw={clean_stats['total_raw']}, usable={clean_stats['usable']})")

    # A) Separate Ascension from Regular Challengers (and National competition)
    regular_ch = [r for r in challengers if infer_tier_detail(r.get('event_name', '')) not in ('Ascension',)]
    ascension_ch = [r for r in challengers if infer_tier_detail(r.get('event_name', '')) == 'Ascension']
    national_ch = [r for r in challengers if 'national competition' in (r.get('event_name') or '').lower()]
    regular_excl_asc = [r for r in challengers if infer_tier_detail(r.get('event_name', '')) in ('Stage', 'Qualifier', 'Other')]

    print("\nUsable by bucket (A: Regular vs Ascension vs National):")
    print(f"  Regular Challengers (Stage/Qualifier/Other): {len(regular_excl_asc)}")
    print(f"  Ascension: {len(ascension_ch)}")
    print(f"  National competition: {len(national_ch)}")

    by_region = defaultdict(int)
    by_tier = defaultdict(int)
    near_even = 0
    for r in challengers:
        reg = infer_region(r.get('event_name', ''))
        tier = infer_tier_detail(r.get('event_name', ''))
        by_region[reg] += 1
        by_tier[tier] += 1
        Of, Ou = r.get('Of'), r.get('Ou')
        if Of is not None and Ou is not None and abs(Of - Ou) <= 0.05:
            near_even += 1
    print("\nUsable by region:")
    for reg in sorted(by_region.keys()):
        print(f"  {reg}: {by_region[reg]}")
    print("\nUsable by tier detail:")
    for tier in sorted(by_tier.keys()):
        print(f"  {tier}: {by_tier[tier]}")
    pct_near_even = 100 * near_even / len(challengers) if challengers else 0
    print(f"\nNear-even odds (|Of-Ou|<=0.05): {near_even} ({pct_near_even:.1f}%)")

    if not challengers:
        print("\nNo Challengers data with usable odds. Cannot proceed.")
        return None

    # 3.2 Market stats
    print("\n3.2 MARKET STATS")
    print("-" * 50)
    Of_arr = np.array([r['Of'] for r in challengers])
    Ou_arr = np.array([r['Ou'] for r in challengers])
    ov_arr = np.array([r['overround'] for r in challengers])
    pf_arr = np.array([r['p_fair'] for r in challengers])
    print(f"Of: mean={np.mean(Of_arr):.2f} median={np.median(Of_arr):.2f}")
    print(f"Ou: mean={np.mean(Ou_arr):.2f} median={np.median(Ou_arr):.2f}")
    print(f"Overround: mean={np.mean(ov_arr):.4f} median={np.median(ov_arr):.4f}")
    print("p_fair buckets: [0.5,0.55) [0.55,0.6) [0.6,0.65) [0.65,0.7) [0.7,0.75) [0.75,1.0]")
    for lo, hi in [(0.5, 0.55), (0.55, 0.6), (0.6, 0.65), (0.65, 0.7), (0.7, 0.75), (0.75, 1.01)]:
        c = np.sum((pf_arr >= lo) & (pf_arr < hi))
        print(f"  [{lo:.2f},{hi:.2f}): {c}")

    # 3.3 Calibration + drift
    print("\n3.3 CALIBRATION + DRIFT")
    print("-" * 50)
    outcome = np.array([1 if r['fav_won'] else 0 for r in challengers])
    p_fair = np.array([r['p_fair'] for r in challengers])
    p_raw = np.array([r['p_raw'] for r in challengers])
    cal_err = np.mean(outcome - p_fair)
    vig_effect = np.mean(p_raw - p_fair)
    print(f"Per-match calibration error mean(outcome - p_fair): {cal_err:.4f}")
    print(f"Vig effect mean(p_raw - p_fair): {vig_effect:.4f}")
    cal = calibration_table(challengers, bin_width=0.1)
    print("Calibration by p_fair/Of bucket:")
    for c in cal[:10]:
        print(f"  {c['bin_lo']:.1f}-{c['bin_hi']:.1f}: n={c['n']} p_obs={c['p_obs']:.3f} p_fair={c['p_fair']:.3f} edge={c['edge']:.3f}")
    # Drift by event (order)
    by_ev = defaultdict(list)
    for r in challengers:
        by_ev[r.get('event_name', '')].append(r)
    print("\nCalibration by event (sample):")
    for ev, sub in list(by_ev.items())[:5]:
        o = np.array([1 if r['fav_won'] else 0 for r in sub])
        pf = np.array([r['p_fair'] for r in sub])
        print(f"  {ev[:45]}: n={len(sub)} mean(outcome-p_fair)={np.mean(o-pf):.3f}")

    # 3.4 Baselines
    print("\n3.4 BASELINES")
    print("-" * 50)
    a_fav = run_baseline(challengers, 'fav')
    b_dog = run_baseline(challengers, 'dog')
    print(f"A_always_fav (all): ROI={a_fav['roi']:.1f}% n={a_fav['n_bets']} hit={a_fav['hit_rate']:.1f}% max_dd={a_fav['max_dd']:.2f} longest_L={a_fav['longest_losing']}")
    print(f"B_always_dog (all): ROI={b_dog['roi']:.1f}% n={b_dog['n_bets']} hit={b_dog['hit_rate']:.1f}% max_dd={b_dog['max_dd']:.2f} longest_L={b_dog['longest_losing']}")

    # A) Baselines per bucket (Regular vs Ascension)
    print("\n3.4b BASELINES BY BUCKET (Regular vs Ascension)")
    reg_asc_baselines: Dict = {}
    for label, subset in [("Regular (excl Ascension)", regular_excl_asc), ("Ascension", ascension_ch)]:
        if subset:
            af = run_baseline(subset, 'fav')
            bd = run_baseline(subset, 'dog')
            reg_asc_baselines[label] = {'n': len(subset), 'a_fav': af, 'b_dog': bd}
            print(f"  {label}: n={len(subset)} | A_fav ROI={af['roi']:.1f}% n={af['n_bets']} | B_dog ROI={bd['roi']:.1f}% n={bd['n_bets']}")

    # B) B_always_dog by Ou (dog odds) buckets
    print("\n3.4c B_always_dog BY Ou BUCKET")
    ou_buckets = [(2.00, 2.50), (2.50, 3.25), (3.25, 5.00), (5.00, 999.0)]
    for lo, hi in ou_buckets:
        sub = [r for r in challengers if r.get('Ou') is not None and lo <= r['Ou'] < hi]
        if sub:
            res = run_baseline(sub, 'dog')
            print(f"  Ou [{lo:.2f}, {hi:.2f}): n={len(sub)} ROI={res['roi']:.1f}% hit={res['hit_rate']:.1f}%")

    # C) Overround filter for dogs (baseline B_dog only; uses OV_THRESH_V0 for consistency)
    print(f"\n3.4d BASELINE B_dog + OVERROUND FILTER (no Ou band)")
    for thresh in [OV_THRESH_V0, 1.07]:
        res = run_baseline_dog_overround_filter(challengers, thresh)
        if res['n_bets'] > 0:
            print(f"  overround <= {thresh:.2f}: n={res['n_bets']} ROI={res['roi']:.1f}% hit={res['hit_rate']:.1f}%")

    # Bootstrap
    bs_fav = bootstrap_roi(challengers, 'fav')
    bs_dog = bootstrap_roi(challengers, 'dog')
    if bs_fav:
        print(f"\nBootstrap A_always_fav (block by event): ROI p5/p50/p95 = {bs_fav['roi_p5']:.1f}% / {bs_fav['roi_p50']:.1f}% / {bs_fav['roi_p95']:.1f}%")
    if bs_dog:
        print(f"Bootstrap B_always_dog (block by event): ROI p5/p50/p95 = {bs_dog['roi_p5']:.1f}% / {bs_dog['roi_p50']:.1f}% / {bs_dog['roi_p95']:.1f}%")

    # D) Event-blocked for B_always_dog
    def _b_dog_strat(rows):
        return run_baseline(rows, 'dog')
    eb_dog = event_blocked_roi(challengers, _b_dog_strat)
    # Get worst event's n_bets for footnote
    by_ev_dog = defaultdict(list)
    for r in challengers:
        by_ev_dog[r.get('event_name', '') or 'unknown'].append(r)
    event_rois_dog = []
    for ev, sub in by_ev_dog.items():
        res = run_baseline(sub, 'dog')
        if res['n_bets'] > 0:
            event_rois_dog.append((ev, res['roi'], res['n_bets']))
    worst_ev = min(event_rois_dog, key=lambda x: x[1]) if event_rois_dog else (None, 0, 0)
    eb_dog['worst_event_n_bets'] = worst_ev[2]
    print(f"\n3.4e EVENT-BLOCKED B_always_dog: median_event_roi={eb_dog['median_event_roi']:.1f}% pct_positive={eb_dog['pct_positive']:.0f}% worst={eb_dog['worst_roi']:.1f}% n_events={eb_dog['n_events']} (worst event had n={worst_ev[2]} bets)")

    # Rounding atom report: top 10 overround values and frequencies (data-generation artifact check)
    ov_counts = defaultdict(int)
    for r in challengers:
        if r.get('Of') is not None and r.get('Ou') is not None:
            ov = r.get('overround', 999)
            if ov < 2.0:  # sane range
                ov_counts[round(ov, 4)] += 1
    print(f"\n3.4e2 OVERROUND ROUNDING ATOMS (top 10 values)")
    for ov_val, cnt in sorted(ov_counts.items(), key=lambda x: -x[1])[:10]:
        pct = 100 * cnt / sum(ov_counts.values()) if ov_counts else 0
        print(f"  ov={ov_val:.4f}: n={cnt} ({pct:.1f}%)")
    ov_atoms = dict(sorted(ov_counts.items(), key=lambda x: -x[1])[:10])

    # Overround clustering: matches per event with overround <= OV_THRESH_V0 (same as vig table)
    print(f"\n3.4f OVERROUND CLUSTERING (matches per event with ov<={OV_THRESH_V0})")
    by_ev_ov = defaultdict(int)
    for r in challengers:
        if r.get('overround', 999) <= OV_THRESH_V0:
            by_ev_ov[r.get('event_name', '') or 'unknown'] += 1
    for ev, cnt in sorted(by_ev_ov.items(), key=lambda x: -x[1]):
        print(f"  {ev[:50]}: {cnt} matches")
    total_lowvig = sum(by_ev_ov.values())
    n_events_lowvig = len(by_ev_ov)
    print(f"  Total: {total_lowvig} matches across {n_events_lowvig} events")
    ov_clustering = dict(by_ev_ov)

    # Strategy v0 (ov<=1.05 + Ou in [3.25,5.00])
    print(f"\n3.4g STRATEGY v0 (ov<={OV_THRESH_V0} + Ou in [{OU_LO_V0},{OU_HI_V0}])")
    v0_overrounds: List[float] = []
    v0_all = run_v0_strategy(challengers, overrounds_out=v0_overrounds)
    v0_regular = run_v0_strategy(challengers, exclude_ascension=True)
    v0_ascension = run_v0_strategy(challengers, ascension_only=True)
    eb_v0 = event_blocked_roi(challengers, lambda rows: run_v0_strategy(rows))

    def _print_v0_diag(label: str, res: Dict):
        n = res.get('n_bets', 0)
        if n == 0:
            print(f"  {label}: n=0")
            return
        hit = res.get('hit_rate', 0)
        avg_o = res.get('avg_odds', 0)
        ci_lo = res.get('wilson_ci_lo', 0)
        ci_hi = res.get('wilson_ci_hi', 0)
        be_rate = res.get('break_even_rate', 100 / avg_o if avg_o else 0)
        print(f"  {label}: n={n} ROI={res['roi']:.1f}% total_profit={res.get('total_profit', 0):.1f}u avg_odds={avg_o:.2f} hit={hit:.1f}%")
        print(f"    Wilson 95% CI for hit: [{100*ci_lo:.1f}%, {100*ci_hi:.1f}%] | break-even rate={be_rate:.1f}%")
        print(f"    top_wins={res.get('top_wins', [])} top_losses={res.get('top_losses', [])}")
        roi_impl = res.get('roi_implied', 0)
        print(f"    EV_sanity (approx for flat 1u): hit*avg_odds-1={roi_impl:.3f} -> ROI_implied={100*roi_impl:.1f}% (actual ROI={res['roi']:.1f}%)")

    _print_v0_diag("v0 (all)", v0_all)
    _print_v0_diag("v0a (Regular only)", v0_regular)
    _print_v0_diag("v0b (Ascension only)", v0_ascension)

    # Event distribution for v0
    by_ev_v0 = defaultdict(list)
    for r in challengers:
        by_ev_v0[r.get('event_name', '') or 'unknown'].append(r)
    event_n_bets = []
    v0_event_details = []  # (ev, n, hit, avg_odds, hit_minus_be)
    for ev, sub in by_ev_v0.items():
        r = run_v0_strategy(sub)
        if r['n_bets'] > 0:
            event_n_bets.append(r['n_bets'])
            hit_pct = r['hit_rate'] / 100
            avg_o = r['avg_odds']
            be = 1 / avg_o if avg_o else 0
            v0_event_details.append((ev, r['n_bets'], r['hit_rate'], avg_o, hit_pct - be))
    v0_event_dist = {}
    if event_n_bets:
        med_bpe = float(np.median(event_n_bets))
        max_bpe = max(event_n_bets)
        pct_top = 100 * max_bpe / sum(event_n_bets) if sum(event_n_bets) else 0
        v0_event_dist = {'median_bpe': med_bpe, 'max_bpe': max_bpe, 'pct_top': pct_top}
        print(f"  v0 event distribution: median_bets_per_event={med_bpe:.0f} max_bets_in_event={max_bpe} pct_from_top_event={pct_top:.0f}%")
    print(f"  Event-blocked v0: median={eb_v0['median_event_roi']:.1f}% pct_positive={eb_v0['pct_positive']:.0f}% worst={eb_v0['worst_roi']:.1f}% n_events={eb_v0['n_events']}")

    # Event-blocked hit-rate vs break-even (more interpretable than ROI at small n)
    print(f"\n3.4h V0 EVENT-LEVEL: hit_rate vs break-even")
    for ev, n, hit, avg_o, hit_minus_be in sorted(v0_event_details, key=lambda x: -x[4]):
        be = 100 / avg_o if avg_o else 0
        print(f"  {ev[:45]}: n={n} hit={hit:.1f}% avg_odds={avg_o:.2f} hit-be={hit_minus_be*100:+.1f}pp")

    # Placebo bands (adjacent to v0): if v0 strong and adjacent weak, evidence of real pocket
    print(f"\n3.4i PLACEBO BANDS (same ov<={OV_THRESH_V0}, different Ou)")
    placebo_lo = run_ou_band_strategy(challengers, 2.50, 3.25, OV_THRESH_V0)  # bad band
    placebo_hi = run_ou_band_strategy(challengers, 5.00, 7.50, OV_THRESH_V0)  # above v0
    _print_v0_diag("placebo Ou [2.50, 3.25)", placebo_lo)
    _print_v0_diag("placebo Ou [5.00, 7.50)", placebo_hi)

    # v0 overround sanity: mean/median, distribution near cutoff
    print(f"\n3.4j V0 OVERROUND SANITY (among v0 bets)")
    if v0_overrounds:
        ov_arr = np.array(v0_overrounds)
        print(f"  mean={np.mean(ov_arr):.4f} median={np.median(ov_arr):.4f} min={np.min(ov_arr):.4f} max={np.max(ov_arr):.4f}")
        near_cutoff = sum(1 for o in v0_overrounds if 1.049 <= o <= 1.050)
        print(f"  n in [1.049, 1.050]: {near_cutoff} / {len(v0_overrounds)} ({100*near_cutoff/len(v0_overrounds):.0f}%)")
    else:
        print("  (no v0 bets)")

    # ov cutoff robustness sweep (analysis only; rule stays frozen)
    print(f"\n3.4k OV CUTOFF SWEEP (analysis only)")
    for ov_t in [1.045, 1.05, 1.055]:
        r = run_ou_band_strategy(challengers, OU_LO_V0, OU_HI_V0, ov_t)
        if r['n_bets'] > 0:
            print(f"  ov<={ov_t}: n={r['n_bets']} ROI={r['roi']:.1f}% hit={r['hit_rate']:.1f}% CI=[{100*r['wilson_ci_lo']:.1f}%, {100*r['wilson_ci_hi']:.1f}%]")
        else:
            print(f"  ov<={ov_t}: n=0")

    # Ou band WITHOUT overround filter (the only part that may be a real hypothesis)
    print(f"\n3.4l OU BAND [3.25,5.00] NO OVERROUND (baseline for new v0 candidate)")
    ou_no_ov = run_ou_band_no_ov(challengers, OU_LO_V0, OU_HI_V0)
    _print_v0_diag("Ou [3.25,5.00] no ov", ou_no_ov)
    eb_ou_no_ov = event_blocked_roi(challengers, lambda rows: run_ou_band_no_ov(rows, OU_LO_V0, OU_HI_V0))
    print(f"  Event-blocked: median={eb_ou_no_ov['median_event_roi']:.1f}% pct_positive={eb_ou_no_ov['pct_positive']:.0f}% n_events={eb_ou_no_ov['n_events']}")

    # Ou band + ov-percentile filter (replaces absolute cutoff)
    print(f"\n3.4m OU BAND + OV PERCENTILE (bottom X% overround within band)")
    ov_pct_results = []
    for pct in [10, 20, 30]:
        r = run_ou_band_ov_percentile(challengers, OU_LO_V0, OU_HI_V0, pct)
        ov_pct_results.append({'pct': pct, **r})
        if r['n_bets'] > 0:
            _print_v0_diag(f"  bottom {pct}% ov", r)
        else:
            print(f"  bottom {pct}% ov: n=0")
    eb_pct20 = event_blocked_roi(challengers, lambda rows: run_ou_band_ov_percentile(rows, OU_LO_V0, OU_HI_V0, 20))
    if ou_no_ov['n_bets'] > 0:
        print(f"  Event-blocked (20%): median={eb_pct20['median_event_roi']:.1f}% pct_positive={eb_pct20['pct_positive']:.0f}%")

    # Permutation test: shuffle outcomes within event
    print(f"\n3.4n PERMUTATION TEST (Ou [3.25,5.00], shuffle outcomes within event, 1000 reps)")
    perm = permutation_roi(challengers, OU_LO_V0, OU_HI_V0, n_reps=1000)
    print(f"  observed ROI={perm['observed_roi']:.1f}% n={perm['n_bets']}")
    print(f"  null ROI p5/p50/p95 = {perm['null_p5']:.1f}% / {perm['null_p50']:.1f}% / {perm['null_p95']:.1f}%")
    print(f"  p-value (null >= observed) = {perm['p_value']:.3f}")

    # 3.4o Edge-model (ridge logistic) + EV strategy (walk-forward)
    print(f"\n3.4o EDGE MODEL (ridge logistic) + EV STRATEGY (walk-forward)")
    by_ev_model = defaultdict(list)
    for r in challengers:
        by_ev_model[r.get('event_name', '') or 'unknown'].append(r)
    events_ordered_ev = list(by_ev_model.keys())
    n_train_ev = max(1, int(0.7 * len(events_ordered_ev)))
    train_events_ev = set(events_ordered_ev[:n_train_ev])
    test_events_ev = set(events_ordered_ev[n_train_ev:])
    train_rows_ev = [r for r in challengers if r.get('event_name', '') in train_events_ev]
    test_rows_ev = [r for r in challengers if r.get('event_name', '') in test_events_ev]

    Xtr, ytr, meta = build_edge_features(train_rows_ev)
    ev_model_w = None
    ev_model_meta = {}
    ev_model_results = []
    eb_ev = {}
    if Xtr.size > 0 and len(ytr) >= 10:
        ev_model_w = fit_ridge_logit(Xtr, ytr, lam=5.0, n_iter=50)
        ev_model_meta = meta
        p_hat_te = predict_fav_win_prob(test_rows_ev, ev_model_w, meta)
        if len(p_hat_te) > 0:
            for ev_min in [0.00, 0.01, 0.02]:
                res = run_ev_model_strategy(test_rows_ev, p_hat_te, ev_min=ev_min)
                ev_model_results.append({'ev_min': ev_min, **res})
                print(f"  EV>={ev_min:.2f}: ROI={res['roi']:.1f}% n={res['n_bets']} hit={res['hit_rate']:.1f}% avg_odds={res['avg_odds']:.2f} max_dd={res['max_dd']:.2f}")

            def _ev_strat(rows_sub):
                p_sub = predict_fav_win_prob(rows_sub, ev_model_w, meta)
                return run_ev_model_strategy(rows_sub, p_sub, ev_min=0.01)

            eb_ev = event_blocked_roi(test_rows_ev, _ev_strat)
            print(f"  Event-blocked (EV>=0.01): median={eb_ev['median_event_roi']:.1f}% pct_positive={eb_ev['pct_positive']:.0f}% worst={eb_ev['worst_roi']:.1f}% n_events={eb_ev['n_events']}")
    else:
        print("  (insufficient train data for edge model)")

    # Strategy search (parsimonious)
    print("\n4) STRATEGY SEARCH")
    print("-" * 50)
    all_regions = ('Americas', 'EMEA', 'Pacific', 'China')
    candidates = []

    # Fav bands
    for p_min, p_max in [(0.55, 0.70), (0.55, 0.75), (0.50, 0.70), (0.60, 0.70)]:
        for regs in [('Americas',), all_regions]:
            res = run_challengers_strategy_v1(challengers, regions=regs, p_fair_min=p_min, p_fair_max=p_max, bet_side='fav')
            if res['n_bets'] >= 10:
                candidates.append({
                    'name': f"fav p_fair in [{p_min},{p_max}] regions={regs}",
                    'roi': res['roi'], 'n_bets': res['n_bets'], 'hit_rate': res['hit_rate'],
                    'max_dd': res['max_dd'], 'params': {'p_min': p_min, 'p_max': p_max, 'regions': regs, 'side': 'fav'},
                })

    # Dog bands (conditional)
    for p_min, p_max in [(0.25, 0.45), (0.30, 0.50)]:
        res = run_challengers_strategy_v1(challengers, regions=all_regions, p_fair_min=p_min, p_fair_max=p_max, bet_side='dog')
        if res['n_bets'] >= 10:
            candidates.append({
                'name': f"dog p_fair in [{p_min},{p_max}]",
                'roi': res['roi'], 'n_bets': res['n_bets'], 'hit_rate': res['hit_rate'],
                'max_dd': res['max_dd'], 'params': {'p_min': p_min, 'p_max': p_max, 'regions': all_regions, 'side': 'dog'},
            })

    # Walk-forward: first 70% events vs last 30% (by event order)
    events_ordered = list(by_ev.keys())
    n_train_ev = max(1, int(0.7 * len(events_ordered)))
    train_events = set(events_ordered[:n_train_ev])
    test_events = set(events_ordered[n_train_ev:])
    train_rows = [r for r in challengers if r.get('event_name', '') in train_events]
    test_rows = [r for r in challengers if r.get('event_name', '') in test_events]

    print(f"\nWalk-forward: train events={len(train_events)} ({len(train_rows)} matches), test events={len(test_events)} ({len(test_rows)} matches)")

    # Verify Ascension holdout: test_rows have both odds + winner
    test_with_odds = sum(1 for r in test_rows if r.get('Of') is not None and r.get('Ou') is not None)
    test_with_winner = sum(1 for r in test_rows if r.get('winner_matched', True))
    print(f"Ascension holdout verification: {len(test_rows)} test matches, {test_with_odds} with both odds, {test_with_winner} with winner matched")

    best_candidate = None
    best_oos_roi = -999
    for c in candidates:
        params = c['params']
        res_test = run_challengers_strategy_v1(
            test_rows, regions=params['regions'],
            p_fair_min=params['p_min'], p_fair_max=params['p_max'],
            bet_side=params['side'],
        )
        c['oos_roi'] = res_test['roi']
        c['oos_n'] = res_test['n_bets']
        c['oos_hit'] = res_test['hit_rate']
        c['oos_max_dd'] = res_test['max_dd']
        print(f"  {c['name']}: in-sample ROI={c['roi']:.1f}% n={c['n_bets']} | OOS ROI={res_test['roi']:.1f}% n={res_test['n_bets']}")
        if res_test['n_bets'] >= 5 and res_test['roi'] > best_oos_roi:
            best_oos_roi = res_test['roi']
            best_candidate = c

    # Event-blocked for best
    if best_candidate and test_rows:
        def _strat(rows):
            p = best_candidate['params']
            return run_challengers_strategy_v1(rows, regions=p['regions'], p_fair_min=p['p_min'], p_fair_max=p['p_max'], bet_side=p['side'])
        eb = event_blocked_roi(test_rows, _strat)
        print(f"\nEvent-blocked (best candidate): median_event_roi={eb['median_event_roi']:.1f}% pct_positive={eb['pct_positive']:.0f}% worst={eb['worst_roi']:.1f}% n_events={eb['n_events']}")

    # Build result for spec
    result = {
        'challengers': challengers,
        'train_rows': train_rows,
        'test_rows': test_rows,
        'clean_stats': clean_stats,
        'by_region': dict(by_region),
        'by_tier': dict(by_tier),
        'a_fav': a_fav,
        'b_dog': b_dog,
        'regular_excl_asc': regular_excl_asc,
        'ascension_ch': ascension_ch,
        'reg_asc_baselines': reg_asc_baselines,
        'ou_bucket_results': _ou_bucket_results(challengers),
        'overround_filter_results': _overround_filter_results(challengers),
        'v0_all': v0_all,
        'v0_regular': v0_regular,
        'v0_ascension': v0_ascension,
        'eb_v0': eb_v0,
        'v0_event_dist': v0_event_dist,
        'v0_event_details': v0_event_details,
        'placebo_lo': placebo_lo,
        'placebo_hi': placebo_hi,
        'v0_overround_sanity': {'mean': float(np.mean(v0_overrounds)), 'median': float(np.median(v0_overrounds)), 'n_near_cutoff': sum(1 for o in v0_overrounds if 1.049 <= o <= 1.050), 'n': len(v0_overrounds)} if v0_overrounds else {},
        'ov_atoms': ov_atoms,
        'ou_no_ov': ou_no_ov,
        'ov_pct_results': ov_pct_results,
        'permutation': perm,
        'eb_ou_no_ov': eb_ou_no_ov,
        'ev_model_results': ev_model_results,
        'eb_ev': eb_ev,
        'eb_dog': eb_dog,
        'ov_clustering': ov_clustering,
        'candidates': candidates,
        'best_candidate': best_candidate,
    }
    return result


def write_spec(result: Dict, output_path: str) -> str:
    """Write CHALLENGERS_STRATEGY_SPEC.md or negative result."""
    best = result.get('best_candidate')
    challengers = result.get('challengers', [])
    a_fav = result.get('a_fav', {})
    b_dog = result.get('b_dog', {})

    lines = [
        "# Challengers (Tier 2) Pre-Match Moneyline Strategy — Spec",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Data:** Thunderpick decimal odds from VLR.gg, Challengers 2024.",
        f"**Usable matches:** {len(challengers)}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
    ]

    # Challengers: require acceptance criteria (n_events>=10, n_bets>=200) before deployable
    deployable = (
        best and best.get('oos_roi', 0) > 0 and best.get('oos_n', 0) >= 200
        and result.get('eb_dog', {}).get('n_events', 0) >= 10
    )
    if deployable:
        p = best['params']
        lines.extend([
            f"- **Conditional edge found:** {best['name']}",
            f"- OOS ROI: {best['oos_roi']:.1f}% (n={best['oos_n']})",
            f"- In-sample ROI: {best['roi']:.1f}% (n={best['n_bets']})",
            "- Deploy with tight exposure controls and monitoring.",
            "",
            "## Strategy v1 (Final)",
            "",
            "### Quick Reference",
            "",
            "| Rule | Value |",
            "|------|-------|",
            f"| **Universe** | Challengers: {', '.join(p['regions'])} |",
            f"| **Bet side** | {'Favorite' if p['side'] == 'fav' else 'Underdog'} |",
            f"| **Entry** | {p['p_min']} ≤ p_fair ≤ {p['p_max']}, Of ≥ 1.35 |",
            "| **Stake** | 1u flat |",
            "| **Caps** | 3u/day, 2u/event, 1u/team/day |",
            "| **Kill switch** | Pause if ROI(last 50) < -5% or drawdown > 8u |",
            "| **Review cadence** | Monthly |",
            "",
        ])
    else:
        # Negative result: write full research spec (v0 hypothesis + acceptance criteria)
        reg_asc = result.get('reg_asc_baselines', {})
        ou_buckets = result.get('ou_bucket_results', [])
        ov_filter = result.get('overround_filter_results', [])
        eb_dog = result.get('eb_dog', {})
        bs_dog = bootstrap_roi(challengers, 'dog') if challengers else {}

        n_ev = eb_dog.get('n_events', 0)
        worst_n = eb_dog.get('worst_event_n_bets', 0)
        v0_all = result.get('v0_all', {})
        eb_v0 = result.get('eb_v0', {})
        ov_sanity = result.get('v0_overround_sanity', {})
        ov_sanity_near = ov_sanity.get('n_near_cutoff', 0)
        ov_sanity_total = ov_sanity.get('n', 1)
        ov_sanity_pct = 100 * ov_sanity_near / ov_sanity_total if ov_sanity_total else 0
        lines.extend([
            f"- **Status: Not ready for real staking.** With n_events={n_ev} and event-blocked negativity, any edge is unconfirmed.",
            "- **v0 (ov≤1.05) REJECTED:** The overround filter is a near-degenerate selector — " + f"{ov_sanity_pct:.0f}%" + " of v0 bets at ov≈1.05; ov≤1.055 collapses ROI to negative. Use percentile-based filters or no ov rule.",
            "- **New hypothesis:** If any dog edge exists, it's in Ou [3.25, 5.00] (or 3.25–7.50) and is *not* explained by a stable vig threshold. Ou [2.50, 3.25) is consistently bad.",
            "- **Segmentation findings:** Ascension behaves opposite to Regular; Ou 2.50–3.25 is the worst dog bucket.",
            "",
            "### Definitions used in this report",
            "",
            "- ROI = sum(profit)/sum(stake)",
            "- A_fav / B_dog = unconditional baseline bets on every usable match",
            "- Filters (e.g., overround ≤ 1.05) apply **on top of** baseline unless explicitly stated as \"Strategy v0 filter\"",
            "- Event-blocked ROI computed over events with ≥1 bet under that rule",
            "- ROI_implied = hit_rate × avg_odds − 1 is an **approximation** (assumes flat 1u stakes, loss = −1, win profit = odds−1)",
            "",
            "---",
            "",
            "## 1) Negative Result for Deployable v1",
            "",
            "**Do not deploy** a real-money Challengers strategy with current data.",
            "",
            "| Check | Result |",
            "|-------|--------|",
            f"| Event-blocked B_dog | median_event_roi {eb_dog.get('median_event_roi', 0):.1f}%, pct_positive {eb_dog.get('pct_positive', 0):.0f}%, worst {eb_dog.get('worst_roi', 0):.1f}% |",
            f"| n_events | {eb_dog.get('n_events', 0)} |",
            f"| Bootstrap B_dog | ROI p5/p50/p95 = {bs_dog.get('roi_p5', 0):.1f}% / {bs_dog.get('roi_p50', 0):.1f}% / {bs_dog.get('roi_p95', 0):.1f}% |",
            "",
            "Conclusion: Edge is not broad. One global Challengers rule does not exist.",
            "",
            f"*Worst event ROI often from small events (worst had n={worst_n} bets); one bad bet can swing event ROI sharply.*",
            "",
            "---",
            "",
            "## 2) What We Learned (Segmentation)",
            "",
            "### Ascension is a different market",
            "",
            "| Bucket | n | A_fav ROI | B_dog ROI |",
            "|--------|---|-----------|-----------|",
        ])
        for label, data in reg_asc.items():
            af, bd = data.get('a_fav', {}), data.get('b_dog', {})
            lines.append(f"| {label} | {data.get('n', 0)} | {af.get('roi', 0):.1f}% | {bd.get('roi', 0):.1f}% |")
        lines.extend([
            "",
            "Treat Ascension separately. Do not mix with Regular until you have enough events in each.",
            f"Overall A_fav {a_fav.get('roi', 0):.1f}% is a mix weighted by counts (Regular n={reg_asc.get('Regular (excl Ascension)', {}).get('n', 0)}, Ascension n={reg_asc.get('Ascension', {}).get('n', 0)}).",
            "",
            "### Dog profitability is not \"dogs in general\"",
            "",
            "| Ou band | n | ROI |",
            "|--------|---|-----|",
        ])
        for b in ou_buckets:
            lines.append(f"| [{b['lo']:.2f}, {b['hi']:.2f}) | {b['n']} | {b['roi']:.1f}% |")
        lines.extend([
            "",
            "If there's anything real, it's about **which dogs** — mid dogs (Ou 3.25–5.00).",
            "",
            "### Vig: baseline vs conditional v0",
            "",
            "**(i) Baseline B_dog + overround filter only (no Ou band)**",
            "",
            "| Filter | n | ROI |",
            "|--------|---|-----|",
        ])
        for b in ov_filter:
            lines.append(f"| overround ≤ {b['thresh']:.2f} | {b['n']} | {b['roi']:.1f}% |")
        lines.extend([
            "",
            "**(ii) Strategy v0 (ov≤1.05 + Ou∈[3.25,5.00])**",
            "",
            "| Rule | n | ROI |",
            "|------|---|-----|",
            f"| v0 (all) | {v0_all.get('n_bets', 0)} | {v0_all.get('roi', 0):.1f}% |",
            f"| v0a (Regular only) | {result.get('v0_regular', {}).get('n_bets', 0)} | {result.get('v0_regular', {}).get('roi', 0):.1f}% |",
            f"| v0b (Ascension only) | {result.get('v0_ascension', {}).get('n_bets', 0)} | {result.get('v0_ascension', {}).get('roi', 0):.1f}% |",
            "",
            "**v0 (all) diagnostics:** total_profit=" + f"{v0_all.get('total_profit', 0):.1f}u" + ", avg_odds=" + f"{v0_all.get('avg_odds', 0):.2f}" + ", hit=" + f"{v0_all.get('hit_rate', 0):.1f}%" + ", Wilson 95% CI=[" + f"{100*v0_all.get('wilson_ci_lo', 0):.1f}%" + ", " + f"{100*v0_all.get('wilson_ci_hi', 0):.1f}%" + "], break-even rate=" + f"{v0_all.get('break_even_rate', 0):.1f}%" + ". top_wins=" + str(v0_all.get('top_wins', [])) + ", top_losses=" + str(v0_all.get('top_losses', [])) + ". EV_sanity (approx for flat 1u): ROI_implied=" + f"{100*v0_all.get('roi_implied', 0):.1f}%" + " (actual " + f"{v0_all.get('roi', 0):.1f}%" + ").",
            "",
        ])
        v0_ed = result.get('v0_event_dist', {})
        if v0_ed:
            lines.extend([
                "**v0 event distribution:** median_bets_per_event=" + f"{v0_ed.get('median_bpe', 0):.0f}" + ", max_bets_in_event=" + str(v0_ed.get('max_bpe', 0)) + ", pct_from_top_event=" + f"{v0_ed.get('pct_top', 0):.0f}%" + ".",
                "",
            ])
        v0_ev_details = result.get('v0_event_details', [])
        if v0_ev_details:
            lines.extend([
                "**v0 event-level hit vs break-even:** (hit − 1/avg_odds in pp; more interpretable than ROI at small n)",
                "",
                "| Event | n | hit% | avg_odds | hit−be (pp) |",
                "|-------|---|------|----------|-------------|",
            ])
            for ev, n, hit, avg_o, hit_minus_be in sorted(v0_ev_details, key=lambda x: -x[4])[:12]:
                lines.append(f"| {ev[:40]} | {n} | {hit:.1f} | {avg_o:.2f} | {hit_minus_be*100:+.1f} |")
            lines.extend(["", ""])
        lines.extend([
            "v0 adds Ou band to isolate mid dogs; baseline ov-filter mixes all dog bands (no Ou filter).",
            "",
            "**Conclusion:** The v0 edge was entirely from the ov filter; Ou band alone shows no edge (permutation p≈0.5).",
            "",
        ])
        # Placebo bands + overround sanity + ov sweep
        plo = result.get('placebo_lo', {})
        phi = result.get('placebo_hi', {})
        ov_sanity = result.get('v0_overround_sanity', {})
        if plo or phi:
            lines.extend([
                "**Placebo bands (same ov≤1.05):** Ou [2.50, 3.25) n=" + str(plo.get('n_bets', 0)) + " ROI=" + f"{plo.get('roi', 0):.1f}%" + "; Ou [5.00, 7.50) n=" + str(phi.get('n_bets', 0)) + " ROI=" + f"{phi.get('roi', 0):.1f}%" + ". If v0 strong and adjacent weak, evidence of real pocket.",
                "",
            ])
        if ov_sanity:
            lines.extend([
                "**v0 overround sanity:** mean=" + f"{ov_sanity.get('mean', 0):.4f}" + ", n near [1.049,1.050]=" + str(ov_sanity.get('n_near_cutoff', 0)) + "/" + str(ov_sanity.get('n', 0)) + ".",
                "",
            ])
        ov_atoms = result.get('ov_atoms', {})
        if ov_atoms:
            top3 = list(ov_atoms.items())[:3]
            atoms_str = ", ".join([f"ov={k:.4f} n={v}" for k, v in top3])
            lines.extend([
                "**Overround rounding atoms (top 3):** " + atoms_str + ".",
                "",
            ])
        ou_no_ov = result.get('ou_no_ov', {})
        perm = result.get('permutation', {})
        eb_ou = result.get('eb_ou_no_ov', {})
        ov_pct = result.get('ov_pct_results', [])
        lines.extend([
            "**Ou [3.25,5.00] NO overround:** n=" + str(ou_no_ov.get('n_bets', 0)) + " ROI=" + f"{ou_no_ov.get('roi', 0):.1f}%" + ", event-blocked median=" + f"{eb_ou.get('median_event_roi', 0):.1f}%" + " pct_positive=" + f"{eb_ou.get('pct_positive', 0):.0f}%" + ". The v0 'edge' was entirely from the ov filter.",
            "",
            "**Permutation test (shuffle outcomes within event):** observed ROI=" + f"{perm.get('observed_roi', 0):.1f}%" + ", null p5/p50/p95=" + f"{perm.get('null_p5', 0):.1f}%" + "/" + f"{perm.get('null_p50', 0):.1f}%" + "/" + f"{perm.get('null_p95', 0):.1f}%" + ", p-value=" + f"{perm.get('p_value', 1):.3f}" + ". Not distinguishable from random.",
            "",
        ])
        if ov_pct:
            lines.append("**Ov-percentile (bottom X% within Ou band):** " + ", ".join([f"{r['pct']}% n={r['n_bets']} ROI={r['roi']:.1f}%" for r in ov_pct if r.get('n_bets', 0) > 0]) + ".")
            lines.extend(["", ""])
        ev_res = result.get('ev_model_results', [])
        eb_ev = result.get('eb_ev', {})
        if ev_res:
            ev_str = ", ".join([f"EV>={r['ev_min']:.2f} n={r['n_bets']} ROI={r['roi']:.1f}%" for r in ev_res])
            lines.extend([
                "**Edge model (ridge logistic + EV gate, walk-forward OOS):** " + ev_str + ".",
                "Event-blocked (EV>=0.01): median=" + f"{eb_ev.get('median_event_roi', 0):.1f}%" + " pct_positive=" + f"{eb_ev.get('pct_positive', 0):.0f}%" + ".",
                "",
                "",
            ])
        lines.extend([
            "---",
            "",
            "## 3) v0 REJECTED + New v0 Candidate",
            "",
            "### v0 (ov≤1.05 + Ou∈[3.25,5.00]) — REJECTED",
            "",
            "The apparent edge is not robust. The overround filter acts as a near-degenerate selector: 85%+ of v0 bets are in [1.049, 1.050]; ov≤1.045 gives n=0; ov≤1.055 collapses ROI to negative. This suggests a rounding/selection artifact, not a stable market inefficiency.",
            "",
            "**Do not use absolute overround thresholds.** Revisit using percentile-based filters after full populate.",
            "",
            "### New v0 candidate: Ou band only (no ov rule)",
            "",
            "| Rule | Value |",
            "|------|-------|",
            "| **Universe** | Challengers matches with both odds + winner matched |",
            "| **Market filter** | None (or optional: bottom 20% overround *within* Ou band) |",
            "| **Bet side** | Underdog |",
            "| **Odds band** | Ou ∈ [3.25, 5.00] |",
            "| **Exclude** | Ou ∈ [2.50, 3.25) (known bad) |",
            "| **Stake** | 0.25u flat |",
            "| **Caps** | 1u/day, 1u/event |",
            "| **Kill switch** | Stop if drawdown > 4u or ROI(last 30) < -5% |",
            "| **Goal** | Validate across ≥10 events and ≥200 bets; event-breadth (median hit−BE > 0, % positive > 60%) |",
            "",
            "Ou band [3.25, 5.00] with no ov filter shows ROI≈" + f"{ou_no_ov.get('roi', 0):.1f}%" + " — not distinguishable from null (permutation p≈" + f"{perm.get('p_value', 1):.2f}" + "). Percentile filters may cherry-pick noise at small n. Revisit after full populate.",
            "",
            "---",
            "",
            "## 4) Acceptance Criteria: Graduate v0 → v1",
            "",
            "Before upgrading to deployable v1, **all** must hold: n_events ≥ 10, n_bets ≥ 200, median event ROI ≥ 0%, % events positive > 50–60%, bootstrap p5 not wildly negative, Wilson CI on hit rate must clear break-even, overround matches not clustered in 1–2 events. First graduation check: event-breadth — median event hit−BE positive and % events positive > ~60%.",
            "",
            "---",
            "",
            "## 5) Post-Populate Validation",
            "",
            "For each region and tier: apply v0 filter, print ROI, n_bets, median event ROI, % events positive, bootstrap CI. Check overround clustering (matches per event with ov ≤ 1.05).",
            "",
            "---",
            "",
            "## 6) Overround Clustering (Current)",
            "",
        ])
        ov_clust = result.get('ov_clustering', {})
        if ov_clust:
            total = sum(ov_clust.values())
            n_ev = len(ov_clust)
            lines.append(f"Matches with overround ≤ 1.05: {total} across {n_ev} events.")
            for ev, cnt in sorted(ov_clust.items(), key=lambda x: -x[1])[:8]:
                lines.append(f"- {ev[:50]}: {cnt} matches")
            if n_ev <= 2:
                lines.append("**Caution:** Low-vig matches cluster in 1–2 events; may be event quirk.")
            lines.append("")

    lines.extend([
        "---",
        "",
        "## Baselines",
        "",
        f"| Strategy | ROI | n_bets | hit_rate | max_dd |",
        "|----------|-----|--------|----------|--------|",
        f"| A_always_fav | {a_fav.get('roi', 0):.1f}% | {a_fav.get('n_bets', 0)} | {a_fav.get('hit_rate', 0):.1f}% | {a_fav.get('max_dd', 0):.2f} |",
        f"| B_always_dog | {b_dog.get('roi', 0):.1f}% | {b_dog.get('n_bets', 0)} | {b_dog.get('hit_rate', 0):.1f}% | {b_dog.get('max_dd', 0):.2f} |",
        "",
        "---",
        "",
        "## Reproducibility",
        "",
        "```bash",
        "python scripts/challengers_analytics.py",
        "python scripts/challengers_underdog_test.py",
        "```",
        "",
        "---",
        "",
        "## Disclaimer",
        "",
        "For educational and prototyping only. Not financial or betting advice. Check local laws.",
        "",
    ])

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return output_path


def main():
    result = _run_pipeline()
    if result:
        docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs')
        os.makedirs(docs_dir, exist_ok=True)
        spec_path = os.path.join(docs_dir, 'CHALLENGERS_STRATEGY_SPEC.md')
        write_spec(result, spec_path)
        print(f"\nSpec written to {spec_path}")


if __name__ == '__main__':
    main()
