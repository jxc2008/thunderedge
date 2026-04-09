"""
Model parameter estimation from historical kill data.

Computes mean (μ) and variance, then selects appropriate distribution
(Poisson or Negative Binomial) based on dispersion.
"""

import numpy as np
from typing import List, Dict, Optional, Tuple
from backend.database import Database
from config import Config

# ---------------------------------------------------------------------------
# ML model cache (lazy-loaded on first call to ml_adjust)
# ---------------------------------------------------------------------------
_ml_models: Dict = {}


def _load_ml_models() -> bool:
    """
    Lazy-load the XGBoost models from the models/ directory.
    Returns True if both models loaded successfully, False otherwise.
    Populates the module-level _ml_models cache.
    """
    global _ml_models
    if _ml_models.get('loaded') is not None:
        return _ml_models.get('loaded', False)

    import os
    try:
        import joblib
    except ImportError:
        _ml_models['loaded'] = False
        return False

    # Resolve models/ directory relative to this file
    _backend_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(_backend_dir)
    _models_dir = os.path.join(_project_root, 'models')

    reg_path = os.path.join(_models_dir, 'kill_mean_xgb.pkl')
    cls_path = os.path.join(_models_dir, 'kill_over_xgb.pkl')

    if not os.path.exists(reg_path) or not os.path.exists(cls_path):
        _ml_models['loaded'] = False
        return False

    try:
        _ml_models['reg'] = joblib.load(reg_path)
        _ml_models['cls'] = joblib.load(cls_path)
        _ml_models['loaded'] = True
        return True
    except Exception:
        _ml_models['loaded'] = False
        return False


# Known agent role sets (mirrors train_kill_model.py)
_DUELIST_AGENTS = {'Jett', 'Neon', 'Raze', 'Reyna', 'Phoenix', 'Yoru', 'Iso'}
_INITIATOR_AGENTS = {'Skye', 'Sova', 'Breach', 'Kayo', 'Fade', 'Gekko'}
_CONTROLLER_AGENTS = {'Brimstone', 'Omen', 'Astra', 'Viper', 'Harbor', 'Clove'}
_SENTINEL_AGENTS = {'Cypher', 'Killjoy', 'Sage', 'Chamber', 'Deadlock', 'Vyse'}


def ml_adjust(
    db: Database,
    player_name: str,
    map_name: Optional[str],
    line: float,
) -> Optional[Dict]:
    """
    Query the ML models to get an alternative kill mean and P(over) estimate.

    Uses the player's recent stats from the DB to build a feature vector that
    matches the training feature set from scripts/train_kill_model.py.

    Args:
        db:          Database instance (read-only)
        player_name: Player IGN
        map_name:    Map name (e.g. 'Bind'), or None for map-agnostic
        line:        Betting line (e.g. 18.5)

    Returns:
        Dict with keys 'ml_mu' and 'ml_p_over', or None if models not available
        or player has insufficient data for inference.
    """
    if not _load_ml_models():
        return None

    import sqlite3

    reg_bundle = _ml_models['reg']
    cls_bundle = _ml_models['cls']
    reg_model = reg_bundle['model']
    cls_model = cls_bundle['model']
    feature_names = reg_bundle['feature_names']

    # ------------------------------------------------------------------
    # Fetch recent player stats from DB (last 10 maps for rolling means)
    # ------------------------------------------------------------------
    try:
        conn = sqlite3.connect(db.db_path, timeout=30)
        cursor = conn.cursor()

        # Recent maps for this player (up to last 10), ordered newest first
        cursor.execute("""
            SELECT
                pms.kills, pms.deaths, pms.assists, pms.acs, pms.adr,
                pms.kast, pms.first_bloods, pms.agent, pms.map_name,
                pms.map_score, pms.match_id
            FROM player_map_stats pms
            WHERE LOWER(pms.player_name) = LOWER(?)
            ORDER BY pms.match_id DESC
            LIMIT 15
        """, (player_name,))
        rows = cursor.fetchall()
        conn.close()
    except Exception:
        return None

    if len(rows) < 3:
        return None

    # Most recent row is the "current" context
    most_recent = rows[0]
    (kills_r, deaths_r, assists_r, acs_r, adr_r,
     kast_r, fb_r, agent_r, map_r, map_score_r, match_id_r) = most_recent

    # Rolling means (shift by 1 — exclude most recent for production inference)
    recent_kills = [r[0] for r in rows[1:] if r[0] is not None]
    rolling5 = float(np.mean(recent_kills[:5])) if recent_kills else float(kills_r or 0)
    rolling10 = float(np.mean(recent_kills[:10])) if recent_kills else float(kills_r or 0)

    # Player-map average on the target map (excluding most recent)
    if map_name:
        map_kills_hist = [r[0] for r in rows[1:] if r[0] is not None and
                          r[8] and r[8].lower() == map_name.lower()]
    else:
        map_kills_hist = recent_kills
    player_map_avg = float(np.mean(map_kills_hist)) if map_kills_hist else rolling10

    # Parse map_score for win/loss and kills_per_round
    def _parse_score(s):
        if not s or not isinstance(s, str):
            return None, None, None
        parts = s.split('-')
        if len(parts) != 2:
            return None, None, None
        try:
            a, b = int(parts[0]), int(parts[1])
            return a, b, a + b
        except (ValueError, TypeError):
            return None, None, None

    a, b, rc = _parse_score(map_score_r)
    is_win = 1.0 if (a is not None and a > b) else (0.0 if a is not None else 0.5)
    kills_per_round = float(kills_r) / rc if (rc and rc > 0 and kills_r is not None) else rolling5 / 24.0

    # Opponent strength proxy: use average across recent maps
    opp_deaths_vals = []
    for row in rows[:5]:
        _, d, _, _, _, _, _, _, _, ms, _ = row
        aa, bb, rrc = _parse_score(ms)
        if rrc and rrc > 0 and d is not None:
            opp_deaths_vals.append(d / rrc)
    opponent_deaths_pr = float(np.mean(opp_deaths_vals)) if opp_deaths_vals else 0.65

    # Agent encoding
    agent_clean = (agent_r or 'Unknown').strip()
    agent_is_duelist = float(agent_clean in _DUELIST_AGENTS)
    agent_is_initiator = float(agent_clean in _INITIATOR_AGENTS)
    agent_is_controller = float(agent_clean in _CONTROLLER_AGENTS)
    agent_is_sentinel = float(agent_clean in _SENTINEL_AGENTS)

    # ------------------------------------------------------------------
    # Build feature vector matching training feature_names
    # ------------------------------------------------------------------
    feat_vals = {
        'acs': float(acs_r or 0),
        'adr': float(adr_r or 0),
        'kast': float(kast_r or 0),
        'first_bloods': float(fb_r or 0),
        'kills_per_round': kills_per_round,
        'rolling_mean_5': rolling5,
        'rolling_mean_10': rolling10,
        'player_map_avg': player_map_avg,
        'is_win': is_win,
        'opponent_deaths_pr': opponent_deaths_pr,
        'agent_is_duelist': agent_is_duelist,
        'agent_is_initiator': agent_is_initiator,
        'agent_is_controller': agent_is_controller,
        'agent_is_sentinel': agent_is_sentinel,
    }

    # One-hot agent columns (agent_jett, agent_neon, etc.)
    agent_col = f"agent_{agent_clean.lower().replace(' ', '_')}"
    map_col = f"map_{(map_name or '').lower().replace(' ', '_')}" if map_name else None

    # Build the full feature vector in the exact order of feature_names
    x = []
    for fname in feature_names:
        if fname in feat_vals:
            x.append(feat_vals[fname])
        elif fname == agent_col:
            x.append(1.0)
        elif fname == map_col:
            x.append(1.0)
        elif fname.startswith('agent_') or fname.startswith('map_'):
            x.append(0.0)
        else:
            x.append(0.0)

    X = np.array(x, dtype=float).reshape(1, -1)

    # ------------------------------------------------------------------
    # Predict
    # ------------------------------------------------------------------
    try:
        ml_mu = float(reg_model.predict(X)[0])
        ml_mu = max(0.5, ml_mu)  # clamp to sensible floor

        # Classifier expects features + line appended
        X_cls = np.column_stack([X, [[line]]])
        ml_p_over = float(cls_model.predict_proba(X_cls)[0][1])
        ml_p_over = float(np.clip(ml_p_over, 0.01, 0.99))

        return {
            'ml_mu': ml_mu,
            'ml_p_over': ml_p_over,
            'ml_p_under': 1.0 - ml_p_over,
            'agent': agent_clean,
            'rolling_mean_5': rolling5,
            'rolling_mean_10': rolling10,
        }
    except Exception:
        return None


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
            WHERE LOWER(pms.player_name) = LOWER(?) AND pms.kills > 0
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
        
        kills = [row[0] for row in rows if row[0] is not None and row[0] > 0]
        
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
