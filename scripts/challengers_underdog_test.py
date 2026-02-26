#!/usr/bin/env python3
"""
Test hypothesis: Underdogs are underpriced in Challengers (tier 2) due to higher volatility.
Compares underdog performance in Challengers vs Tier 1 (VCT) matches.
Run: python scripts/challengers_underdog_test.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.moneyline_analytics import (
    load_raw_data,
    clean_data,
    compute_vig_and_pfair,
)


def is_challengers(event_name: str) -> bool:
    """True if event is Challengers (tier 2)."""
    n = (event_name or '').lower()
    return 'challengers' in n or 'ascension' in n or 'national competition' in n


def run_underdog_test(rows: list) -> dict:
    """
    For each row: dog_won, p_dog_fair (implied underdog prob), Ou.
    Returns aggregate stats for underdog betting.
    """
    dog_wins = []
    p_dog_fair_list = []
    profits = []
    for r in rows:
        Of, Ou = r.get('Of'), r.get('Ou')
        fav_won = r.get('fav_won', False)
        if Of is None or Ou is None or Ou <= 0:
            continue
        p_dog_fair = (1.0 / Ou) / (1.0 / Of + 1.0 / Ou)
        dog_won = not fav_won
        dog_wins.append(1 if dog_won else 0)
        p_dog_fair_list.append(p_dog_fair)
        # Profit from 1u on underdog: Ou - 1 if dog wins, else -1
        profit = (Ou - 1) if dog_won else -1
        profits.append(profit)
    n = len(dog_wins)
    if n == 0:
        return {'n': 0}
    return {
        'n': n,
        'dog_win_rate': sum(dog_wins) / n,
        'mean_implied_dog_prob': sum(p_dog_fair_list) / n,
        'roi_pct': 100 * sum(profits) / n,
        'total_profit': sum(profits),
        'dog_wins': sum(dog_wins),
    }


def main():
    rows = load_raw_data()
    cleaned, stats = clean_data(rows)
    enriched = compute_vig_and_pfair(cleaned)

    challengers = [r for r in enriched if is_challengers(r.get('event_name', ''))]
    tier1 = [r for r in enriched if not is_challengers(r.get('event_name', ''))]

    res_ch = run_underdog_test(challengers)
    res_t1 = run_underdog_test(tier1)

    print("=" * 70)
    print("CHALLENGERS UNDERDOG HYPOTHESIS TEST")
    print("Hypothesis: Underdogs underpriced in Challengers (more volatile, mispriced)")
    print("=" * 70)
    print()
    print("CHALLENGERS (tier 2):")
    if res_ch['n'] > 0:
        print(f"  n = {res_ch['n']}")
        print(f"  Underdog win rate:     {100*res_ch['dog_win_rate']:.1f}%")
        print(f"  Mean implied dog prob: {100*res_ch['mean_implied_dog_prob']:.1f}%")
        print(f"  ROI (1u flat on dog):  {res_ch['roi_pct']:.1f}%")
        print(f"  Total profit (1u/bet): {res_ch['total_profit']:.1f}u")
        diff = res_ch['dog_win_rate'] - res_ch['mean_implied_dog_prob']
        print(f"  Win rate - implied:    {100*diff:+.1f}pp (positive = underdogs underpriced)")
    else:
        print("  No Challengers data with usable odds.")
    print()
    print("TIER 1 (VCT regional + International):")
    if res_t1['n'] > 0:
        print(f"  n = {res_t1['n']}")
        print(f"  Underdog win rate:     {100*res_t1['dog_win_rate']:.1f}%")
        print(f"  Mean implied dog prob: {100*res_t1['mean_implied_dog_prob']:.1f}%")
        print(f"  ROI (1u flat on dog):  {res_t1['roi_pct']:.1f}%")
        print(f"  Total profit (1u/bet): {res_t1['total_profit']:.1f}u")
        diff_t1 = res_t1['dog_win_rate'] - res_t1['mean_implied_dog_prob']
        print(f"  Win rate - implied:   {100*diff_t1:+.1f}pp")
    else:
        print("  No Tier 1 data.")
    print()
    print("COMPARISON:")
    if res_ch['n'] > 0 and res_t1['n'] > 0:
        roi_diff = res_ch['roi_pct'] - res_t1['roi_pct']
        print(f"  Challengers underdog ROI vs Tier 1: {roi_diff:+.1f}pp")
        if res_ch['dog_win_rate'] > res_ch['mean_implied_dog_prob']:
            print("  -> Challengers: Underdogs appear underpriced (win rate > implied prob)")
        else:
            print("  -> Challengers: Underdogs do NOT appear underpriced in this sample")
    print()
    print("DATA COVERAGE:")
    events_ch = set(r.get('event_name') for r in challengers)
    for e in sorted(events_ch):
        c = sum(1 for r in challengers if r.get('event_name') == e)
        print(f"  {e}: {c} matches")
    print()
    print("NOTE: Americas Challengers (NA Stage 1, Stage 2, Americas Ascension) populated.")
    print("      EMEA, Pacific, China Ascension added to populate_moneyline - run populate for more regions.")


if __name__ == '__main__':
    main()
