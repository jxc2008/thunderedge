# backend/calculator.py
"""
Advanced KPR calculation utilities.

Also contains blend_with_ml() which merges the Poisson/NB baseline with the
XGBoost ML signal (kill_mean_xgb + kill_over_xgb) trained by
scripts/train_kill_model.py.
"""
from typing import Dict, List, Optional
import statistics
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ML blending
# ---------------------------------------------------------------------------

def blend_with_ml(
    dist_params: Dict,
    db,
    player_name: str,
    map_name: Optional[str],
    line: float,
    ml_weight: float = 0.4,
    min_sample_size: int = 10,
) -> Dict:
    """
    Blend the Poisson/NB baseline distribution with the XGBoost ML signal.

    Only blends when the baseline has sufficient data (sample_size >=
    min_sample_size).  Falls back gracefully if models are not installed.

    Args:
        dist_params:     Output of get_player_distribution() / apply_matchup_adjustment().
                         Must contain 'mu' and 'sample_size'.
        db:              Database instance (passed through to ml_adjust).
        player_name:     Player IGN.
        map_name:        Map name, or None.
        line:            Betting line (e.g. 18.5).
        ml_weight:       Weight given to ML mu signal (default 0.4).
                         Baseline weight = 1 - ml_weight.
        min_sample_size: Only blend if sample_size >= this threshold.

    Returns:
        Updated dist_params dict (may be the original if blending is skipped).
        Adds keys:
            - ml_signal: dict with raw ML predictions, or None
            - ml_blended: bool — whether blending was applied
    """
    from backend.model_params import ml_adjust

    sample_size = dist_params.get('sample_size', 0)
    baseline_mu = float(dist_params.get('mu', 0.0))

    result = dict(dist_params)
    result['ml_signal'] = None
    result['ml_blended'] = False

    if sample_size < min_sample_size:
        logger.debug(
            f"ML blend skipped for {player_name}: sample_size={sample_size} < {min_sample_size}"
        )
        return result

    ml = ml_adjust(db, player_name, map_name, line)

    if ml is None:
        logger.debug(f"ML signal unavailable for {player_name} (models not loaded or insufficient data)")
        return result

    ml_mu = ml['ml_mu']
    final_mu = (1.0 - ml_weight) * baseline_mu + ml_weight * ml_mu
    final_mu = max(0.5, final_mu)

    logger.info(
        f"[ML blend] {player_name} | map={map_name or 'any'} | line={line} | "
        f"baseline_mu={baseline_mu:.2f}  ml_mu={ml_mu:.2f}  final_mu={final_mu:.2f} | "
        f"ml_p_over={ml['ml_p_over']:.3f}"
    )

    result['mu'] = final_mu
    if result.get('dist') == 'poisson':
        result['lambda'] = final_mu
    elif result.get('dist') == 'nbinom':
        k = float(result.get('k', 1.0))
        k = max(1e-6, k)
        result['p'] = k / (k + final_mu)

    result['ml_signal'] = {
        'ml_mu': ml_mu,
        'ml_p_over': ml['ml_p_over'],
        'ml_p_under': ml['ml_p_under'],
        'rolling_mean_5': ml.get('rolling_mean_5'),
        'rolling_mean_10': ml.get('rolling_mean_10'),
        'agent': ml.get('agent'),
        'ml_weight': ml_weight,
        'baseline_mu_pre_blend': baseline_mu,
        'final_mu_post_blend': final_mu,
    }
    result['ml_blended'] = True

    return result

class KPRCalculator:
    """Advanced KPR calculations and predictions"""
    
    @staticmethod
    def weighted_moving_average(values: List[float], weights: List[float] = None) -> float:
        """Calculate weighted moving average"""
        if not values:
            return 0.0
        
        if weights is None:
            # Default: more recent values have higher weight
            n = len(values)
            weights = [(i + 1) / sum(range(1, n + 1)) for i in range(n)]
        
        return sum(v * w for v, w in zip(values, weights))
    
    @staticmethod
    def exponential_smoothing(values: List[float], alpha: float = 0.3) -> float:
        """Calculate exponential smoothing prediction"""
        if not values:
            return 0.0
        
        result = values[0]
        for value in values[1:]:
            result = alpha * value + (1 - alpha) * result
        
        return result
    
    @staticmethod
    def calculate_consistency_score(values: List[float]) -> float:
        """Calculate consistency score (0-1, higher = more consistent)"""
        if len(values) < 2:
            return 1.0
        
        mean = statistics.mean(values)
        std = statistics.stdev(values)
        
        if mean == 0:
            return 0.0
        
        # Coefficient of variation (lower = more consistent)
        cv = std / mean
        
        # Convert to consistency score (inverse, capped at 1)
        return max(0, min(1, 1 - cv))
    
    @staticmethod
    def predict_kpr(events: List[Dict], method: str = 'weighted') -> float:
        """Predict KPR using specified method"""
        kpr_values = [e['kpr'] for e in events if e.get('kpr', 0) > 0]
        
        if not kpr_values:
            return 0.0
        
        if method == 'weighted':
            return KPRCalculator.weighted_moving_average(kpr_values)
        elif method == 'exponential':
            return KPRCalculator.exponential_smoothing(kpr_values)
        elif method == 'simple':
            return statistics.mean(kpr_values)
        else:
            return statistics.mean(kpr_values)
    
    @staticmethod
    def calculate_form_factor(events: List[Dict], recent_count: int = 3) -> float:
        """Calculate recent form factor (-1 to 1, positive = good form)"""
        kpr_values = [e['kpr'] for e in events if e.get('kpr', 0) > 0]
        
        if len(kpr_values) < recent_count + 1:
            return 0.0
        
        recent_avg = statistics.mean(kpr_values[-recent_count:])
        overall_avg = statistics.mean(kpr_values)
        
        if overall_avg == 0:
            return 0.0
        
        # Positive = performing above average recently
        return (recent_avg - overall_avg) / overall_avg
