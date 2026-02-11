"""
Compute P(Over) and P(Under) for betting props using statistical distributions.

Uses Poisson or Negative Binomial distributions for discrete counts (kills).
"""

import numpy as np
from typing import Dict, Tuple
from scipy import stats


def line_thresholds(line: float) -> Tuple[int, int]:
    """
    Convert a betting line to discrete thresholds.
    
    For a line of 18.5:
    - Under means X <= 18
    - Over means X >= 19
    
    Args:
        line: Betting line (e.g., 18.5)
        
    Returns:
        (under_max, over_min) tuple of integers
    """
    # Under: all values <= floor(line)
    under_max = int(np.floor(line))
    
    # Over: all values >= ceil(line)
    over_min = int(np.ceil(line))
    
    return under_max, over_min


def compute_prop_probabilities(dist_params: Dict, line: float) -> Dict:
    """
    Compute P(Over) and P(Under) for a given line using the player's distribution.
    
    Args:
        dist_params: Distribution parameters from model_params.py
        line: Betting line (e.g., 18.5 kills)
        
    Returns:
        Dictionary with:
            - p_over: Probability of Over
            - p_under: Probability of Under
            - under_max: Max value for Under
            - over_min: Min value for Over
            - method: 'poisson' or 'nbinom'
    """
    if dist_params.get('mu', 0) == 0:
        # No data or invalid params
        return {
            'p_over': 0.0,
            'p_under': 1.0,
            'under_max': int(np.floor(line)),
            'over_min': int(np.ceil(line)),
            'method': 'none',
            'error': 'Invalid distribution parameters'
        }
    
    under_max, over_min = line_thresholds(line)
    
    dist_type = dist_params.get('dist', 'poisson')
    
    if dist_type == 'poisson':
        return _poisson_probabilities(dist_params, line, under_max, over_min)
    elif dist_type == 'nbinom':
        return _nbinom_probabilities(dist_params, line, under_max, over_min)
    else:
        raise ValueError(f"Unknown distribution type: {dist_type}")


def _poisson_probabilities(dist_params: Dict, line: float, under_max: int, over_min: int) -> Dict:
    """Compute probabilities using Poisson distribution."""
    lam = dist_params.get('lambda', dist_params.get('mu', 0))
    
    if lam <= 0:
        return {
            'p_over': 0.0,
            'p_under': 1.0,
            'under_max': under_max,
            'over_min': over_min,
            'method': 'poisson',
            'error': 'Invalid lambda'
        }
    
    # P(X <= under_max) using Poisson CDF
    p_under = float(stats.poisson.cdf(under_max, lam))
    
    # P(X >= over_min) = 1 - P(X <= over_min - 1)
    p_over = 1.0 - float(stats.poisson.cdf(over_min - 1, lam))
    
    # Validate (should sum to ~1.0)
    if not np.isclose(p_under + p_over, 1.0, atol=0.01):
        # Numerical issue - normalize
        total = p_under + p_over
        if total > 0:
            p_under = p_under / total
            p_over = p_over / total
    
    return {
        'p_over': float(p_over),
        'p_under': float(p_under),
        'under_max': under_max,
        'over_min': over_min,
        'method': 'poisson',
        'lambda': lam
    }


def _nbinom_probabilities(dist_params: Dict, line: float, under_max: int, over_min: int) -> Dict:
    """Compute probabilities using Negative Binomial distribution."""
    k = dist_params.get('k', 1.0)
    p = dist_params.get('p', 0.5)
    
    if k <= 0 or p <= 0 or p >= 1:
        return {
            'p_over': 0.0,
            'p_under': 1.0,
            'under_max': under_max,
            'over_min': over_min,
            'method': 'nbinom',
            'error': 'Invalid NB parameters'
        }
    
    # SciPy's negative binomial uses (n, p) parameterization
    # n = k (number of successes), p = probability
    
    # P(X <= under_max) using NB CDF
    p_under = float(stats.nbinom.cdf(under_max, k, p))
    
    # P(X >= over_min) = 1 - P(X <= over_min - 1)
    p_over = 1.0 - float(stats.nbinom.cdf(over_min - 1, k, p))
    
    # Validate and normalize if needed
    if not np.isclose(p_under + p_over, 1.0, atol=0.01):
        total = p_under + p_over
        if total > 0:
            p_under = p_under / total
            p_over = p_over / total
    
    return {
        'p_over': float(p_over),
        'p_under': float(p_under),
        'under_max': under_max,
        'over_min': over_min,
        'method': 'nbinom',
        'k': k,
        'p': p
    }


def generate_pmf(dist_params: Dict, x_range: Tuple[int, int]) -> Dict:
    """
    Generate probability mass function (PMF) for visualization.
    
    Args:
        dist_params: Distribution parameters
        x_range: (min, max) range for x-axis
        
    Returns:
        Dictionary with:
            - x: array of kill values
            - pmf: array of probabilities
            - method: distribution type
    """
    x_min, x_max = x_range
    x = np.arange(x_min, x_max + 1)
    
    dist_type = dist_params.get('dist', 'poisson')
    
    if dist_type == 'poisson':
        lam = dist_params.get('lambda', dist_params.get('mu', 0))
        if lam > 0:
            pmf = stats.poisson.pmf(x, lam)
        else:
            pmf = np.zeros_like(x, dtype=float)
    
    elif dist_type == 'nbinom':
        k = dist_params.get('k', 1.0)
        p = dist_params.get('p', 0.5)
        if k > 0 and 0 < p < 1:
            pmf = stats.nbinom.pmf(x, k, p)
        else:
            pmf = np.zeros_like(x, dtype=float)
    
    else:
        pmf = np.zeros_like(x, dtype=float)
    
    return {
        'x': x.tolist(),
        'pmf': pmf.tolist(),
        'method': dist_type
    }


# Quick test when run directly
if __name__ == '__main__':
    from backend.database import Database
    from backend.model_params import get_player_distribution
    from config import Config
    
    print("=== Prop Probability Test ===\n")
    
    db = Database(Config.DATABASE_PATH)
    
    # Get a player's distribution
    test_player = 'yay'
    line = 18.5
    
    print(f"Player: {test_player}")
    print(f"Line: {line} kills")
    print("=" * 50)
    
    # Get distribution params
    dist_params = get_player_distribution(db, test_player, context={'last_n': 50})
    
    if 'error' not in dist_params:
        print(f"\nModel Distribution: {dist_params['dist'].upper()}")
        print(f"Mean: {dist_params['mu']:.2f}")
        print(f"Sample size: {dist_params['sample_size']}")
        
        # Compute probabilities
        probs = compute_prop_probabilities(dist_params, line)
        
        print(f"\nProbabilities:")
        print(f"  P(Under {line}) = {probs['p_under']:.2%}")
        print(f"  P(Over {line}) = {probs['p_over']:.2%}")
        print(f"  Sum: {probs['p_under'] + probs['p_over']:.4f}")
        
        print(f"\nThresholds:")
        print(f"  Under: X <= {probs['under_max']}")
        print(f"  Over: X >= {probs['over_min']}")
        
        # Test a few different lines
        print(f"\nTesting different lines:")
        for test_line in [15.5, 18.5, 21.5]:
            probs = compute_prop_probabilities(dist_params, test_line)
            print(f"  Line {test_line}: Over={probs['p_over']:.2%}, Under={probs['p_under']:.2%}")
        
        # Generate PMF for plotting
        mu = dist_params['mu']
        x_min = max(0, int(mu - 15))
        x_max = int(mu + 15)
        
        pmf_data = generate_pmf(dist_params, (x_min, x_max))
        print(f"\nPMF generated for x in [{x_min}, {x_max}]")
        print(f"PMF sum (should ≈ 1.0): {sum(pmf_data['pmf']):.4f}")
    
    else:
        print(f"Error: {dist_params['error']}")
