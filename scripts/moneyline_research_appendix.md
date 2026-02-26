# Valorant Moneyline Strategy — Research Appendix

## 1. Dataset Inventory

| Metric | Value |
|--------|-------|
| Total rows | 1005 |
| Duplicates removed | 0 |
| No winner | 12 |
| No odds | 326 |
| Usable for backtest | 667 |

## 2. Calibration Table

| Bin | n | Of_avg | p_raw | p_fair | p_obs | edge |
|-----|---|--------|-------|--------|-------|------|
| 1.0-1.1 | 33 | 1.06 | 0.946 | 0.901 | 0.939 | 0.038 |
| 1.1-1.2 | 68 | 1.14 | 0.876 | 0.835 | 0.750 | -0.085 |
| 1.2-1.3 | 79 | 1.25 | 0.799 | 0.761 | 0.797 | 0.036 |
| 1.3-1.4 | 102 | 1.36 | 0.737 | 0.702 | 0.706 | 0.004 |
| 1.4-1.5 | 97 | 1.47 | 0.683 | 0.650 | 0.629 | -0.022 |
| 1.5-1.6 | 83 | 1.55 | 0.644 | 0.614 | 0.602 | -0.011 |
| 1.6-1.7 | 79 | 1.64 | 0.610 | 0.581 | 0.595 | 0.014 |
| 1.7-1.8 | 78 | 1.75 | 0.571 | 0.543 | 0.449 | -0.095 |
| 1.8-1.9 | 48 | 1.86 | 0.538 | 0.512 | 0.458 | -0.054 |

Brier score: 0.0023, ECE: 0.0399

## 3. Backtest Results (train 2024-2025, test 2026)

| Strategy | ROI | n_bets | hit_rate | max_dd | longest_L |
|----------|-----|--------|----------|--------|-----------|
| A_always_fav | -7.2% | 117 | 62.4% | 11.89 | 4 |
| B_always_dog | -8.3% | 117 | 37.6% | 13.51 | 6 |
| C_fav_edge | 0.0% | 0 | 0.0% | 0.00 | 0 |
| D_dog_edge | -0.7% | 23 | 47.8% | 3.00 | 3 |
| E_best_side | -0.7% | 23 | 47.8% | 3.00 | 3 |

## 4. Reproducibility

Run: `python scripts/moneyline_analytics.py`

Key functions: `clean_data()`, `compute_vig_and_pfair()`, `calibration_table()`, `backtest_strategies()`
