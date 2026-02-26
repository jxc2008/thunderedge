# Valorant Pre-Match Moneyline Strategy v1 — Deployable Spec

**Last updated:** Based on OOS 2025–2026 backtest.  
**Data:** Thunderpick decimal odds from VLR.gg, VCT 2024–2026.

---

## Executive Summary

- **No global edge** — Across all regions, pre-match ML is close to efficient (break-even check confirms).
- **Conditional regional edge** — Americas + China show positive ROI; EMEA/Pacific are negative.
- **Simple filter ≈ isotonic model** — The isotonic strategy mostly acts as a smoother version of "bet favorites in Americas/China when 0.55 ≤ p_fair ≤ 0.70."
- **Deploy as conditional strategy** with tight exposure controls and continual monitoring.

---

## Strategy v1: Market-Select Favorites (Final)

### Quick Reference

| Rule | Value |
|------|-------|
| **Universe** | Americas + China only |
| **Bet side** | Favorite |
| **Entry** | 0.55 ≤ p_fair ≤ 0.70, Of ≥ 1.35 |
| **Stake** | 1u flat (Kickoff stake cap (optional): 0.75u) |
| **Caps** | 3u/day, 2u/event, 1u/team/day |
| **Avoid** | p_fair > 0.70 (heavy favorites); **skip** |
| **Kill switch** | Pause if ROI(last 50) < -3% or drawdown > 10u |
| **Review cadence** | Monthly (re-run walk-forward + event-level breakdown) |

### Universe Filter

Only consider matches where:

- **Region ∈ {Americas, China}**
- Odds valid (no 1.00 bug, two-way market)
- `p_fair` computed via de-vig: `p_fair = (1/Of) / (1/Of + 1/Ou)`

**Favorite definition:** the side with **lower decimal odds** (`Of = min(odds_a, odds_b)`). If odds are equal (rare), treat as even and **skip**.

**Region source:** use the dataset's `region` field (or inferred from event). If inference fails, **skip** (don't guess).

### Bet Selection Rule

**Bet favorite** when **0.55 ≤ p_fair ≤ 0.70** and **Of ≥ 1.35**.

- **No-bet zone for heavy favorites:** If p_fair > 0.70, **skip**. (Optional probes are discouraged; Kickoff heavy favorites showed overpricing.)

### Kickoff-Specific Risk Modifier (Optional)

Since 2026 Americas+China is all Kickoff and heavy-fav overpricing was found there:

- If tier == **Kickoff**: cap stake to **0.75u** (or 0.5u)
- If tier != Kickoff: normal 1u

### Staking

- **Flat 1u per bet** (or 0.5u if ultra-conservative)
- Optional Kickoff cap: 0.75u for Kickoff tier

### Exposure Caps

| Cap | Limit |
|-----|-------|
| Max per day (or event-day) | 3u |
| Max per single event | 2u |
| Max per team per day | 1u |

**Event definition:** use the dataset's `event_name` (or the canonical tournament identifier). If multiple stages share a parent event, treat each stage as its own event only if `event_name` distinguishes it.

### Kill Switch / Monitoring

Track rolling performance on live bets:

- **Pause** if either:
  - ROI(last 50 bets) < **-3%**
  - Drawdown > **10u**
- **ROI(last 50)** = mean profit per 1u of stake over the last 50 bets.
- **Drawdown** = peak-to-trough cumulative profit in units.
- After pausing, resume only after re-running walk-forward on the latest data and confirming the rule remains positive in the most recent test window.

### Rolling Review (Critical)

- **Recompute p_fair and rerun walk-forward monthly** (or per stage).
- Re-evaluate whether Americas+China remain positive.
- If the last 100 bets ROI goes negative beyond a threshold, pause.
- Even if the rule doesn't use training, monitoring does.
- **Don't make rule changes based on fewer than 30 bets** in the most recent month/stage unless there is a clear data quality issue.

### Practical Deployment Rules

- **Line movement (optional):** If the odds you would bet change by more than **Δ = 0.07** (example: 1.60→1.53 or 1.67), **skip** or recompute `p_fair` using updated odds before betting.
- **No parlay rule:** Keep bets independent; your edge is small and variance compounds badly.

---

## Strategy v1b: Isotonic Confirmation (Alternative)

Same universe filter (Americas + China). Use isotonic calibrator trained on 2024–2025:

- Compute `p_hat = isotonic(p_fair)`
- Compute `EV_fav = p_hat * Of - 1`
- **Bet favorite** if `EV_fav ≥ 0.015` (1.5%)

Deploy v1 first; v1b only if you want model-assisted selection.

---

## OOS Validation Summary

| Test | Rule (0.55≤p_fair≤0.70) | n | ROI |
|------|------------------------|---|-----|
| 2025 | Americas+China | 90 | 8.1% |
| 2026 | Americas+China | 37 | 23.8% |

**Walk-forward:** Rule is positive in both 2025 and 2026 — supports stability.

**Event-blocked (by event ROI):**

| Year | median_event_ROI | % events positive | worst_event_ROI | n_events |
|------|------------------|-------------------|-----------------|----------|
| 2025 | 10.6% | 83% | -23.3% | 6 |
| 2026 | 27.4% | 100% | 12.4% | 2 |

Edge is broad in 2025 (83% of events positive); 2026 has only 2 events so noisier.

---

## What to Avoid

- **EMEA / Pacific** — Negative ROI in sample; no need to force action.
- **p_fair > 0.70** — Heavy favorites; all 10 bets in sample were Kickoff with 4 upsets. **Skip**.
- **Kelly sizing** — Not enough evidence yet; use flat stakes.

---

## What Could Invalidate This

Include this list so the document stays honest:

- **Region composition changes** — e.g., more elite matches, fewer qualifiers
- **Thunderpick pricing improves** — or liquidity increases
- **Team-name matching changes** — or VLR formatting changes
- **Kickoff-specific dynamics** — new rosters, uncertainty; may fade later in the season

---

## Reproducibility

```bash
python scripts/moneyline_analytics.py
```

**Canonical v1 strategy call:**

```python
run_dumb_filter_strategy(
    test_rows,
    regions=('Americas', 'China'),
    p_fair_min=0.55,
    p_fair_max=0.70,
    of_min=1.35,
    kickoff_stake_cap=0.75  # optional
)
```

Key functions: `run_dumb_filter_strategy()`, `event_blocked_roi()`, `fit_isotonic_calibrator()`, `run_isotonic_strategy()`.

---

## Disclaimer

For educational and prototyping only. Not financial or betting advice. Check local laws related to sports betting.
