"""
Odds conversion utilities for sports betting analysis.

Converts American odds to probabilities, removes vig, and calculates expected value.
"""

def american_to_implied_prob(odds: float) -> float:
    """
    Convert American odds to implied probability.
    
    Args:
        odds: American odds (e.g., -110, +150)
        
    Returns:
        Implied probability as a decimal (0-1)
        
    Examples:
        >>> american_to_implied_prob(-110)
        0.5238
        >>> american_to_implied_prob(+150)
        0.4000
    """
    if odds == 0:
        raise ValueError("Odds cannot be zero")
    
    if odds < 0:
        # Favorite: p = |odds| / (|odds| + 100)
        prob = abs(odds) / (abs(odds) + 100)
    else:
        # Underdog: p = 100 / (odds + 100)
        prob = 100 / (odds + 100)
    
    # Clamp to valid probability range (handle tiny numerical errors)
    return max(0.0, min(1.0, prob))


def vig_free_probs(over_odds: float, under_odds: float) -> tuple[float, float]:
    """
    Remove vig (bookmaker margin) from odds to get fair probabilities.
    
    The sum of implied probabilities typically exceeds 1.0 (the vig).
    This normalizes them to sum to exactly 1.0.
    
    Args:
        over_odds: American odds for Over
        under_odds: American odds for Under
        
    Returns:
        (p_over_vigfree, p_under_vigfree) tuple
        
    Example:
        >>> vig_free_probs(-110, -110)
        (0.5, 0.5)  # Fair odds after removing vig
    """
    p_over_raw = american_to_implied_prob(over_odds)
    p_under_raw = american_to_implied_prob(under_odds)
    
    total = p_over_raw + p_under_raw
    
    if total == 0:
        raise ValueError("Total probability cannot be zero")
    
    # Normalize to sum to 1.0
    p_over_vigfree = p_over_raw / total
    p_under_vigfree = p_under_raw / total
    
    return p_over_vigfree, p_under_vigfree


def american_to_decimal(odds: float) -> float:
    """
    Convert American odds to decimal odds (for payout calculation).
    
    Args:
        odds: American odds
        
    Returns:
        Decimal odds (e.g., 1.91, 2.50)
        
    Examples:
        >>> american_to_decimal(-110)
        1.909
        >>> american_to_decimal(+150)
        2.500
    """
    if odds < 0:
        return 1 + (100 / abs(odds))
    else:
        return 1 + (odds / 100)


def expected_value_per_1(p_win: float, odds: float) -> float:
    """
    Calculate expected value (EV) per $1 wagered.
    
    EV represents the average profit/loss per bet if repeated many times.
    Positive EV = profitable long-term, Negative EV = unprofitable.
    
    Args:
        p_win: Probability of winning (0-1)
        odds: American odds
        
    Returns:
        Expected net profit per $1 stake
        
    Examples:
        >>> expected_value_per_1(0.55, -110)  # 55% win rate at -110
        0.045  # Profit $0.045 per $1 bet (4.5% ROI)
        
        >>> expected_value_per_1(0.45, -110)  # 45% win rate at -110
        -0.046  # Lose $0.046 per $1 bet
    """
    decimal_odds = american_to_decimal(odds)
    
    # EV = (p_win * profit_if_win) - (p_lose * loss_if_lose)
    # profit_if_win = decimal_odds - 1 (net profit on $1)
    # loss_if_lose = 1 (you lose your $1 stake)
    
    ev = (p_win * (decimal_odds - 1)) - ((1 - p_win) * 1)
    
    return ev


def calculate_vig_percentage(over_odds: float, under_odds: float) -> float:
    """
    Calculate the bookmaker's vig (margin/juice) as a percentage.
    
    Args:
        over_odds: American odds for Over
        under_odds: American odds for Under
        
    Returns:
        Vig percentage (e.g., 4.76 for standard -110/-110)
    """
    p_over = american_to_implied_prob(over_odds)
    p_under = american_to_implied_prob(under_odds)
    
    # Vig = how much the total exceeds 100%
    vig = ((p_over + p_under) - 1.0) * 100
    
    return max(0.0, vig)


# Quick tests when run directly
if __name__ == '__main__':
    print("=== Odds Utilities Test ===\n")
    
    # Test 1: Standard -110/-110 (typical American odds)
    print("Test 1: Standard -110/-110")
    p_over = american_to_implied_prob(-110)
    p_under = american_to_implied_prob(-110)
    print(f"  Raw probabilities: Over={p_over:.4f}, Under={p_under:.4f}")
    print(f"  Sum (with vig): {p_over + p_under:.4f}")
    
    p_over_vf, p_under_vf = vig_free_probs(-110, -110)
    print(f"  Vig-free: Over={p_over_vf:.4f}, Under={p_under_vf:.4f}")
    print(f"  Vig percentage: {calculate_vig_percentage(-110, -110):.2f}%\n")
    
    # Test 2: EV calculation
    print("Test 2: EV Calculation")
    print(f"  Model says 55% chance of Over at -110:")
    ev = expected_value_per_1(0.55, -110)
    print(f"  EV = ${ev:.4f} per $1 bet ({ev*100:.2f}% ROI)")
    
    print(f"\n  Model says 45% chance of Over at -110:")
    ev = expected_value_per_1(0.45, -110)
    print(f"  EV = ${ev:.4f} per $1 bet ({ev*100:.2f}% ROI)")
    
    # Test 3: Underdog odds
    print("\nTest 3: Underdog +150")
    p = american_to_implied_prob(+150)
    decimal = american_to_decimal(+150)
    print(f"  Implied prob: {p:.4f} ({p*100:.1f}%)")
    print(f"  Decimal odds: {decimal:.3f}")
    print(f"  If you win: profit ${decimal-1:.2f} on $1 bet")
