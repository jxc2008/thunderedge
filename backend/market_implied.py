"""
Infer market-implied distribution parameters from betting odds.

Given a line and vig-free probability, reverse-engineer what mean (μ)
the market is implying.
"""

import numpy as np
from typing import Dict, Optional
from scipy import stats
from backend.odds_utils import vig_free_probs
from backend.prop_prob import line_thresholds


def market_implied_mean_discrete(
    line: float,
    p_under_vigfree: float,
    dist_type: str = 'poisson',
    model_dispersion: Optional[float] = None
) -> Dict:
    """
    Infer the market-implied mean via discrete CDF matching.
    
    Find μ such that P(X <= floor(line)) ≈ p_under_vigfree
    
    Args:
        line: Betting line (e.g., 18.5)
        p_under_vigfree: Vig-free probability of Under
        dist_type: 'poisson' or 'nbinom'
        model_dispersion: If nbinom, use this k value (optional)
        
    Returns:
        Dictionary with:
            - mu_market: Implied mean
            - method: Distribution type used
            - iterations: Number of search iterations
    """
    under_max, over_min = line_thresholds(line)
    
    # Binary search for μ
    mu_low = 0.0
    mu_high = max(60.0, line * 3)  # Reasonable upper bound
    
    max_iterations = 50
    tolerance = 0.001
    
    for iteration in range(max_iterations):
        mu_mid = (mu_low + mu_high) / 2
        
        if dist_type == 'poisson':
            # P(X <= under_max) with Poisson(μ)
            if mu_mid <= 0:
                p_model = 1.0
            else:
                p_model = float(stats.poisson.cdf(under_max, mu_mid))
        
        elif dist_type == 'nbinom':
            # Use model's dispersion or estimate from market
            if model_dispersion is None:
                # Heuristic: assume moderate overdispersion
                k = max(1.0, mu_mid / 2)
            else:
                k = model_dispersion
            
            # NB parameters
            p_param = k / (k + mu_mid) if mu_mid > 0 else 0.5
            
            if mu_mid <= 0 or k <= 0 or p_param >= 1:
                p_model = 1.0
            else:
                p_model = float(stats.nbinom.cdf(under_max, k, p_param))
        
        else:
            raise ValueError(f"Unknown dist_type: {dist_type}")
        
        # Check convergence
        error = p_model - p_under_vigfree
        
        if abs(error) < tolerance:
            return {
                'mu_market': mu_mid,
                'method': dist_type,
                'iterations': iteration + 1,
                'p_under_check': p_model
            }
        
        # Adjust search bounds
        if p_model > p_under_vigfree:
            # Model probability too high → mean too low
            mu_low = mu_mid
        else:
            # Model probability too low → mean too high
            mu_high = mu_mid
    
    # Didn't converge - return best estimate
    return {
        'mu_market': (mu_low + mu_high) / 2,
        'method': dist_type,
        'iterations': max_iterations,
        'converged': False,
        'p_under_check': p_model
    }


def compute_market_parameters(
    line: float,
    over_odds: float,
    under_odds: float,
    model_dist_type: str = 'poisson',
    model_dispersion: Optional[float] = None
) -> Dict:
    """
    Compute full market-implied parameters from odds.
    
    Args:
        line: Betting line
        over_odds: American odds for Over
        under_odds: American odds for Under
        model_dist_type: Distribution type to use for inversion
        model_dispersion: Dispersion parameter (for nbinom)
        
    Returns:
        Dictionary with market parameters and vig info
    """
    # Compute vig-free probabilities
    p_over_vf, p_under_vf = vig_free_probs(over_odds, under_odds)
    
    # Compute vig percentage
    from backend.odds_utils import calculate_vig_percentage
    vig_pct = calculate_vig_percentage(over_odds, under_odds)
    
    # Infer market mean
    market_mean_result = market_implied_mean_discrete(
        line=line,
        p_under_vigfree=p_under_vf,
        dist_type=model_dist_type,
        model_dispersion=model_dispersion
    )
    
    return {
        'p_over_vigfree': p_over_vf,
        'p_under_vigfree': p_under_vf,
        'vig_percentage': vig_pct,
        'mu_market': market_mean_result['mu_market'],
        'dist_type': model_dist_type,
        'inversion_method': market_mean_result['method'],
        'converged': market_mean_result.get('converged', True)
    }


# Quick test when run directly
if __name__ == '__main__':
    print("=== Market Implied Parameters Test ===\n")
    
    # Test case 1: Standard -110/-110 at line 18.5
    print("Test 1: Line 18.5, both sides -110")
    print("=" * 50)
    
    market_params = compute_market_parameters(
        line=18.5,
        over_odds=-110,
        under_odds=-110,
        model_dist_type='poisson'
    )
    
    print(f"Vig-free probabilities:")
    print(f"  P(Over): {market_params['p_over_vigfree']:.4f}")
    print(f"  P(Under): {market_params['p_under_vigfree']:.4f}")
    print(f"  Vig: {market_params['vig_percentage']:.2f}%")
    
    print(f"\nMarket-implied mean: {market_params['mu_market']:.2f} kills")
    print(f"Method: {market_params['inversion_method']}")
    print(f"Converged: {market_params.get('converged', True)}")
    
    # Test case 2: Skewed odds (Over favorite)
    print("\n\nTest 2: Line 18.5, Over -150, Under +130")
    print("=" * 50)
    
    market_params2 = compute_market_parameters(
        line=18.5,
        over_odds=-150,
        under_odds=+130,
        model_dist_type='poisson'
    )
    
    print(f"Vig-free probabilities:")
    print(f"  P(Over): {market_params2['p_over_vigfree']:.4f}")
    print(f"  P(Under): {market_params2['p_under_vigfree']:.4f}")
    print(f"  Vig: {market_params2['vig_percentage']:.2f}%")
    
    print(f"\nMarket-implied mean: {market_params2['mu_market']:.2f} kills")
    print("(Higher than previous because Over is favored)")
    
    # Test case 3: Using Negative Binomial
    print("\n\nTest 3: Same odds, but using NB distribution")
    print("=" * 50)
    
    market_params3 = compute_market_parameters(
        line=18.5,
        over_odds=-110,
        under_odds=-110,
        model_dist_type='nbinom',
        model_dispersion=15.0  # moderate overdispersion
    )
    
    print(f"Market-implied mean (NB): {market_params3['mu_market']:.2f} kills")
    print(f"Compare to Poisson: {market_params['mu_market']:.2f} kills")
