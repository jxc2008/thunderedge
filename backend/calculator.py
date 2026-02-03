# backend/calculator.py
"""
Advanced KPR calculation utilities
"""
from typing import Dict, List
import statistics

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
