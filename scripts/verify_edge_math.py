#!/usr/bin/env python3
"""
Verification script for mathematical edge analysis.

Tests the full pipeline with real cached data.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import Database
from backend.model_params import get_player_distribution
from backend.prop_prob import compute_prop_probabilities
from backend.market_implied import compute_market_parameters
from backend.odds_utils import expected_value_per_1, vig_free_probs
from config import Config


def verify_player_analysis(player_name: str, line: float, over_odds: float, under_odds: float):
    """Run full analysis and print results."""
    
    print("\n" + "=" * 70)
    print(f"  Edge Analysis: {player_name}")
    print("=" * 70)
    
    db = Database(Config.DATABASE_PATH)
    
    # Step 1: Get distribution
    print(f"\n[1] Extracting historical kill data...")
    dist_params = get_player_distribution(db, player_name, context={'last_n': 50})
    
    if 'error' in dist_params:
        print(f"    [X] Error: {dist_params['error']}")
        return
    
    print(f"    [OK] Found {dist_params['sample_size']} maps")
    print(f"    [OK] Distribution: {dist_params['dist'].upper()}")
    print(f"    [OK] Mean (mu): {dist_params['mu']:.2f} kills")
    print(f"    [OK] Variance: {dist_params['var']:.2f}")
    print(f"    [OK] Confidence: {dist_params['confidence']}")
    
    if dist_params['sample_size'] > 0:
        print(f"    [OK] Recent kill counts: {dist_params['samples'][:10]}")
    
    # Step 2: Model probabilities
    print(f"\n[2] Computing model probabilities for line {line}...")
    model_probs = compute_prop_probabilities(dist_params, line)
    
    print(f"    [OK] P(Over {line}): {model_probs['p_over']:.2%}")
    print(f"    [OK] P(Under {line}): {model_probs['p_under']:.2%}")
    print(f"    [OK] Method: {model_probs['method']}")
    
    # Step 3: Market parameters
    print(f"\n[3] Computing market-implied parameters...")
    print(f"    Odds: Over {over_odds:+.0f}, Under {under_odds:+.0f}")
    
    market_params = compute_market_parameters(
        line=line,
        over_odds=over_odds,
        under_odds=under_odds,
        model_dist_type=dist_params['dist'],
        model_dispersion=dist_params.get('k', None)
    )
    
    print(f"    [OK] Vig: {market_params['vig_percentage']:.2f}%")
    print(f"    [OK] P(Over) vig-free: {market_params['p_over_vigfree']:.2%}")
    print(f"    [OK] P(Under) vig-free: {market_params['p_under_vigfree']:.2%}")
    print(f"    [OK] Market-implied mean: {market_params['mu_market']:.2f} kills")
    
    # Step 4: Edge computation
    print(f"\n[4] Computing edge...")
    
    prob_edge_over = model_probs['p_over'] - market_params['p_over_vigfree']
    prob_edge_under = model_probs['p_under'] - market_params['p_under_vigfree']
    
    ev_over = expected_value_per_1(model_probs['p_over'], over_odds)
    ev_under = expected_value_per_1(model_probs['p_under'], under_odds)
    
    print(f"\n    OVER Analysis:")
    print(f"      Model P(Over):   {model_probs['p_over']:.2%}")
    print(f"      Market P(Over):  {market_params['p_over_vigfree']:.2%}")
    print(f"      Prob Edge:       {prob_edge_over:+.2%}")
    print(f"      EV per $1:       ${ev_over:+.4f}")
    print(f"      ROI:             {ev_over*100:+.2f}%")
    
    print(f"\n    UNDER Analysis:")
    print(f"      Model P(Under):  {model_probs['p_under']:.2%}")
    print(f"      Market P(Under): {market_params['p_under_vigfree']:.2%}")
    print(f"      Prob Edge:       {prob_edge_under:+.2%}")
    print(f"      EV per $1:       ${ev_under:+.4f}")
    print(f"      ROI:             {ev_under*100:+.2f}%")
    
    # Step 5: Recommendation
    print(f"\n[5] Recommendation:")
    
    if ev_over > 0 and ev_over > ev_under:
        print(f"    >>> BET OVER <<<")
        print(f"       Expected ROI: {ev_over*100:+.2f}%")
        print(f"       On $100 bet over 100 trials: ${ev_over*100*100:+,.2f} profit")
    elif ev_under > 0 and ev_under > ev_over:
        print(f"    >>> BET UNDER <<<")
        print(f"       Expected ROI: {ev_under*100:+.2f}%")
        print(f"       On $100 bet over 100 trials: ${ev_under*100*100:+,.2f} profit")
    else:
        print(f"    [X] NO BET (Negative EV on both sides)")
        print(f"       Best side: {'OVER' if ev_over > ev_under else 'UNDER'}")
        print(f"       But still negative: {max(ev_over, ev_under)*100:+.2f}% ROI")
    
    # Step 6: Interpretation
    print(f"\n[6] Interpretation:")
    
    mean_diff = dist_params['mu'] - market_params['mu_market']
    
    if abs(mean_diff) < 0.5:
        print(f"    Your model and market agree (both ~{dist_params['mu']:.1f} kills)")
    elif mean_diff > 0:
        print(f"    Your model is MORE bullish than market")
        print(f"    (You: {dist_params['mu']:.1f} vs Market: {market_params['mu_market']:.1f})")
        print(f"    => OVER has better value")
    else:
        print(f"    Your model is LESS bullish than market")
        print(f"    (You: {dist_params['mu']:.1f} vs Market: {market_params['mu_market']:.1f})")
        print(f"    => UNDER has better value")
    
    print("\n" + "=" * 70 + "\n")


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("  MATHEMATICAL EDGE ANALYSIS VERIFICATION")
    print("=" * 70)
    
    # Test with a few scenarios
    test_cases = [
        {
            'player': 'yay',
            'line': 18.5,
            'over_odds': -110,
            'under_odds': -110,
        },
        {
            'player': 'tenz',
            'line': 20.5,
            'over_odds': -120,
            'under_odds': +100,
        },
    ]
    
    for i, test in enumerate(test_cases, 1):
        verify_player_analysis(
            player_name=test['player'],
            line=test['line'],
            over_odds=test['over_odds'],
            under_odds=test['under_odds']
        )
        
        if i < len(test_cases):
            input("Press Enter to continue to next test case...")
    
    print("\n[OK] Verification complete!")
    print("\nIf the above looks reasonable:")
    print("  - Probabilities sum to ~1.0")
    print("  - EV makes sense (positive = good bet)")
    print("  - Recommendations align with edge")
    print("\nThen the backend is working correctly!")
