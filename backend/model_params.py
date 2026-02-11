"""
Model parameter estimation from historical kill data.

Computes mean (μ) and variance, then selects appropriate distribution
(Poisson or Negative Binomial) based on dispersion.
"""

import numpy as np
from typing import List, Dict, Optional
from backend.database import Database
from config import Config


def extract_kill_samples(
    db: Database,
    player_name: str,
    context: Optional[Dict] = None
) -> List[int]:
    """
    Extract kill samples from database with optional filtering.
    
    Args:
        db: Database instance
        player_name: Player IGN
        context: Optional filters:
            - map_name: Filter to specific map (e.g., 'Bind')
            - last_n: Only use last N maps
            - event_ids: List of specific event IDs
            
    Returns:
        List of kill counts (integers)
    """
    import sqlite3
    
    if context is None:
        context = {}
    
    conn = sqlite3.connect(db.db_path, timeout=30.0)
    cursor = conn.cursor()
    
    try:
        # Build query with optional filters
        query = """
            SELECT pms.kills, m.id as match_id, pms.map_name
            FROM player_map_stats pms
            JOIN matches m ON pms.match_id = m.id
            WHERE LOWER(pms.player_name) = LOWER(?)
        """
        params = [player_name]
        
        # Optional: filter by map
        if context.get('map_name'):
            query += " AND LOWER(pms.map_name) = LOWER(?)"
            params.append(context['map_name'])
        
        # Optional: filter by event IDs
        if context.get('event_ids'):
            placeholders = ','.join('?' * len(context['event_ids']))
            query += f" AND m.event_id IN ({placeholders})"
            params.extend(context['event_ids'])
        
        query += " ORDER BY m.id DESC"
        
        # Optional: limit to last N
        if context.get('last_n'):
            query += " LIMIT ?"
            params.append(context['last_n'])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        kills = [row[0] for row in rows if row[0] is not None]
        
        return kills
        
    finally:
        conn.close()


def compute_weighted_mean(samples: List[int], decay: float = 0.05) -> float:
    """
    Compute weighted mean with exponential decay (more recent = higher weight).
    
    Args:
        samples: List of values (most recent first)
        decay: Decay rate (higher = more weight on recent)
        
    Returns:
        Weighted mean
    """
    if not samples:
        return 0.0
    
    n = len(samples)
    weights = np.exp(-decay * np.arange(n))
    weights = weights / weights.sum()
    
    return float(np.average(samples, weights=weights))


def compute_distribution_params(samples: List[int]) -> Dict:
    """
    Compute distribution parameters from kill samples.
    
    Automatically selects between Poisson and Negative Binomial
    based on variance-to-mean ratio (dispersion).
    
    Args:
        samples: List of kill counts
        
    Returns:
        Dictionary with:
            - dist: 'poisson' or 'nbinom'
            - mu: mean
            - var: variance
            - lambda: Poisson rate (if Poisson)
            - k, p: NB params (if NB)
            - sample_size: number of samples
            - confidence: 'LOW', 'MED', or 'HIGH'
    """
    if not samples or len(samples) < 3:
        # Not enough data - return conservative defaults
        return {
            'dist': 'poisson',
            'mu': 0.0,
            'var': 0.0,
            'lambda': 0.0,
            'sample_size': len(samples) if samples else 0,
            'confidence': 'LOW',
            'note': 'Insufficient sample size'
        }
    
    # Compute statistics with recency weighting
    mu = compute_weighted_mean(samples, decay=0.05)
    
    # Also compute unweighted variance (mixing weighted mean with unweighted variance
    # is a pragmatic choice - feel free to adjust)
    var = float(np.var(samples, ddof=1))
    
    sample_size = len(samples)
    
    # Determine confidence based on sample size
    if sample_size < 10:
        confidence = 'LOW'
    elif sample_size < 25:
        confidence = 'MED'
    else:
        confidence = 'HIGH'
    
    # Clamp mean to non-negative
    mu = max(0.0, mu)
    
    # Decide distribution based on dispersion
    # Rule: if variance ≈ mean → Poisson, if variance >> mean → Negative Binomial
    
    if var <= mu * 1.2:  # Poisson-like (variance close to mean)
        return {
            'dist': 'poisson',
            'mu': mu,
            'var': var,
            'lambda': mu,  # Poisson rate parameter
            'sample_size': sample_size,
            'confidence': confidence
        }
    else:  # Overdispersed → Negative Binomial
        # Negative Binomial parameterization:
        # mean = μ
        # var = μ + μ²/k
        # Solve for k: k = μ² / (var - μ)
        
        if var <= mu:
            # Edge case: variance not actually greater than mean
            # Fall back to Poisson
            return {
                'dist': 'poisson',
                'mu': mu,
                'var': var,
                'lambda': mu,
                'sample_size': sample_size,
                'confidence': confidence,
                'note': 'Variance <= mean, using Poisson'
            }
        
        k = (mu ** 2) / (var - mu)
        p = k / (k + mu)
        
        # Validate parameters
        if k <= 0 or p <= 0 or p >= 1:
            # Invalid NB params - fall back to Poisson
            return {
                'dist': 'poisson',
                'mu': mu,
                'var': var,
                'lambda': mu,
                'sample_size': sample_size,
                'confidence': confidence,
                'note': 'Invalid NB params, using Poisson'
            }
        
        return {
            'dist': 'nbinom',
            'mu': mu,
            'var': var,
            'k': k,  # Dispersion parameter
            'p': p,  # Probability parameter
            'sample_size': sample_size,
            'confidence': confidence
        }


def get_player_distribution(
    db: Database,
    player_name: str,
    context: Optional[Dict] = None
) -> Dict:
    """
    Main function: Get distribution parameters for a player.
    
    Args:
        db: Database instance
        player_name: Player IGN
        context: Optional filters (map, last_n, etc.)
        
    Returns:
        Distribution parameters dict
    """
    # Extract samples
    samples = extract_kill_samples(db, player_name, context)
    
    if not samples:
        return {
            'dist': 'poisson',
            'mu': 0.0,
            'var': 0.0,
            'lambda': 0.0,
            'sample_size': 0,
            'confidence': 'LOW',
            'error': 'No data found for player'
        }
    
    # Compute distribution params
    params = compute_distribution_params(samples)
    
    # Add raw samples for debugging/visualization
    params['samples'] = samples
    
    return params


# Quick test when run directly
if __name__ == '__main__':
    from backend.database import Database
    from config import Config
    
    print("=== Model Parameters Test ===\n")
    
    db = Database(Config.DATABASE_PATH)
    
    # Test with a real player
    test_player = 'yay'
    
    print(f"Testing with player: {test_player}")
    print("=" * 50)
    
    # Get distribution
    params = get_player_distribution(db, test_player, context={'last_n': 50})
    
    if 'error' not in params:
        print(f"\nDistribution: {params['dist'].upper()}")
        print(f"Sample size: {params['sample_size']}")
        print(f"Confidence: {params['confidence']}")
        print(f"Mean (μ): {params['mu']:.2f} kills")
        print(f"Variance: {params['var']:.2f}")
        
        if params['dist'] == 'poisson':
            print(f"Lambda (rate): {params['lambda']:.2f}")
        else:
            print(f"k (dispersion): {params['k']:.2f}")
            print(f"p (probability): {params['p']:.4f}")
        
        print(f"\nLast 10 kill counts: {params['samples'][:10]}")
        
        # Show variance-to-mean ratio
        ratio = params['var'] / params['mu'] if params['mu'] > 0 else 0
        print(f"\nVariance/Mean ratio: {ratio:.2f}")
        print(f"  (If ≈1 → Poisson, if >>1 → Negative Binomial)")
    else:
        print(f"Error: {params['error']}")
