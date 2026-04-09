# Kalshi VCT Eco/Anti-Eco Round Trading Strategy
## Research Memo — Skeptical Quant Review

**Date:** 2026-04-08  
**Status:** Pre-implementation feasibility assessment  
**Verdict preview:** Implementable with narrow conditions — but currently blocked by a data gap that must be closed first.

---

## Executive Summary

The hypothesis is interesting but the current repo cannot test it. The foundational data — round-by-round economy states — does not exist in the database despite a schema being present for it. The tables `match_round_data` and `match_map_halves` were designed exactly right but are empty. No scraping code populates them.

More importantly: even if the data existed, the strategy faces a structural market problem that is far more dangerous than any data gap. The signal (eco round → ~80% next-round win) operates at a different level of abstraction than the tradable contract (map/game winner). The repricing per round is often small, and the window to execute is ~30 seconds. That combination — thin repricing, narrow execution window, Kalshi spreads of 5–15 cents — is extremely hostile to this strategy in most scoreline contexts.

The strategy is not dead, but it is only viable in a narrow slice of high-leverage scorelines.

---

## Section 1: Repo & Data Audit

### Repository Structure

```
thunderedge/
├── data/valorant_stats.db         (2.7 MB SQLite - MAIN DATA)
├── backend/
│   ├── database.py                (82 KB - schema + queries)
│   ├── api.py                     (76 KB - Flask endpoints)
│   ├── model_params.py            (Poisson/NegBin distribution fitting)
│   ├── prop_prob.py               (P(over/under line) calculations)
│   ├── market_implied.py          (vig removal, market mean inference)
│   ├── odds_utils.py              (EV, ROI, Kelly)
│   └── matchup_adjust.py         (team-strength multiplier, calibrated)
├── scraper/
│   ├── vlr_scraper.py             (63 KB - VLR.gg web scraper)
│   └── [other scrapers]
└── scripts/
    ├── moneyline_analytics.py     (67 KB - backtesting framework)
    └── calibrate_matchup.py       (expanding-window calibration)
```

### Database Tables — Record Counts

| Table | Rows | Notes |
|-------|------|-------|
| player_map_stats | 21,740 | Core data — per-map player stats |
| player_event_stats | 1,498 | Aggregated per event |
| matches | 428 | Match metadata |
| vct_events | 12 | VCT 2025 (all 4 regions × 3 splits) |
| match_round_data | **0** | **EMPTY — critical for strategy** |
| match_map_halves | **0** | **EMPTY — critical for strategy** |
| moneyline_matches | 0 | Empty |
| team_event_stats | 0 | Empty |

### Data Coverage

- **Events:** VCT 2025 (Americas, EMEA, Pacific, China — Kickoff + Stage 1 + Stage 2)
- **Time range:** ~Jan–Nov 2025
- **Map instances:** ~2,174 (derived: 21,740 rows ÷ 10 players per map)
- **No odds data stored** — moneyline_matches is empty despite the schema existing

---

## Section 2: Column Availability Audit

### Required Columns for Strategy — Status

| Column | Required For | Available? | Source |
|--------|-------------|-----------|--------|
| match_id | Joining tables | ✓ Yes | matches.id |
| map_number | Map within series | ✓ Yes | player_map_stats.map_number |
| map_name | Map identity | ✓ Yes | player_map_stats.map_name |
| round_num | Round sequence | ✗ Missing | match_round_data (empty) |
| current_score_before_round | Game state | ✗ Missing | Not stored anywhere |
| team_name | Team identity | ✓ Yes (match-level) | matches.team1/team2 |
| side (attack/defense) | Eco context | ✗ Missing | Not scraped |
| round_winner | Round outcome | ✗ Missing | match_round_data (empty) |
| map_winner | Map outcome | ✓ Derivable | From map_score parse |
| match_winner | Match outcome | ✓ Derivable | From team1_maps/team2_maps |
| credits | Econ state | ✗ Missing | Not on VLR.gg |
| weapon_type (rifle/eco/etc) | Econ class | ✗ Missing | Not on VLR.gg |
| equipment_value | Econ score | ✗ Missing | Not on VLR.gg |
| armor | Econ detail | ✗ Missing | Not on VLR.gg |
| utility | Econ detail | ✗ Missing | Not on VLR.gg |
| ult_points | Ult advantage | ✗ Missing | Not on VLR.gg |
| team1_economy (pistol/eco/etc) | Econ class | ✓ Schema exists | match_round_data (empty) |
| team2_economy | Econ class | ✓ Schema exists | match_round_data (empty) |
| atk_rounds_won | Side performance | ✓ Schema exists | match_map_halves (empty) |
| def_rounds_won | Side performance | ✓ Schema exists | match_map_halves (empty) |
| map_score (final) | Derivable score | ✓ Yes | player_map_stats.map_score |
| Kalshi bid/ask | Market pricing | ✗ Missing | Not in repo at all |
| Kalshi contract price | Entry/exit | ✗ Missing | Not in repo at all |
| Round timestamp | Trade timing | ✗ Missing | Not in repo at all |

### What Can Be Derived From Existing Data

From `map_score` (e.g., "13-10"), you can infer:
- Final score on the map
- Whether a team won the map
- Approximate total rounds played
- Rough game closeness

**What you cannot derive:** Any intermediate round state, economy per round, weapons used, or the sequence of who won which round.

### Critical Finding

> The tables `match_round_data` and `match_map_halves` were designed with exactly the right schema — round number, winning side, and economy class per team — but contain **zero rows**. No scraping code in the repo populates them. The strategy cannot be backtested without first building a round-level data pipeline.

---

## Section 3: Strategy Framing — The Right Hypothesis

### What the Strategy Is NOT

"Team X wins eco rounds at 80%, therefore bet on team X when they have an econ advantage."

This is wrong because:
1. The tradable contract is "team X wins the MAP," not "team X wins the next round"
2. Even if team X wins the round, the map contract reprices by only a few cents in most game states
3. You are absorbing spread + fees on both legs of a round trip that may yield 2–5 cents of fair-value movement

### The Correct Framing

The tradable hypothesis is:

> **The Kalshi map-winner contract is currently priced at P(map win | score state), but the true fair value is P(map win | score state, econ state). If the market ignores the econ state, there is a gap between current market price and fair value. We buy before the round, the round result moves fair value by δ, and we sell after. Net edge = δ − fees − spread.**

This requires three things to all be true simultaneously:

1. **The market misprices the econ state.** The current contract price does not fully reflect the econ advantage.
2. **The fair-value swing δ is large enough.** The repricing after the round resolves must exceed the round-trip cost.
3. **Execution is feasible.** You can identify the econ state, size up, and execute within the ~30-second buy phase.

### When δ Is Meaningfully Large

The round-to-round impact on map win probability is highest when:

- The score is close (e.g., 11-11, 12-12, 12-11)
- One team is at map point (12-X) and has the econ advantage
- The map is tied going to overtime
- A losing streak is occurring during a specific side

At 11-11 with team A at 80% to win the next round (clean eco for team B):
- If team A wins: P(map win for A) might move from ~55% → ~75% (δ ≈ +20 cents)
- If team A loses: P(map win for A) moves from ~55% → ~35% (δ ≈ −20 cents)

This is where the strategy might generate edge. At non-leverage scorelines (e.g., 10-4), the same eco situation produces δ of only 2–5 cents. After fees and spread, this is negative EV.

**Conclusion:** The strategy is only worth pursuing in high-leverage score states. A version that only trades near 12-X or 11-11 or OT has plausible math; a general "bet whenever there's an eco" version does not.

---

## Section 4: Feature Engineering Design

Even without current round-level data, here is the target feature set:

### Tier 1: Rules-Based Econ Classifier

Uses VLR.gg economy class labels (which DO appear on match pages and could be scraped):

```python
ECON_CLASSES = {
    'pistol':   0,   # Round 1 or round 13 — both teams equal
    'eco':      1,   # Full save, buying almost nothing (<$1000 team avg)
    'semi-eco': 2,   # Partial buy (~$1000-2000 team avg)
    'force':    3,   # Force buy (buying rifles/shotguns with partial armor)
    'full':     4,   # Full buy (rifles + armor + utility)
    'bonus':    5,   # Won last round with econ intact
}

# Matchup classification
def classify_round_matchup(team1_econ, team2_econ):
    if team1_econ == 'full' and team2_econ in ['eco', 'semi-eco']:
        return 'gun_advantage_t1'
    if team2_econ == 'full' and team1_econ in ['eco', 'semi-eco']:
        return 'gun_advantage_t2'
    if team1_econ in ['eco', 'semi-eco'] and team2_econ in ['eco', 'semi-eco']:
        return 'both_eco'
    if team1_econ == 'full' and team2_econ == 'force':
        return 'gun_vs_force_t1'
    return 'even'
```

### Tier 2: Numeric Econ Advantage Score

Without credits (not available on VLR.gg), approximate from econ class:

```python
ECON_VALUE_APPROX = {
    'pistol':   800,
    'eco':      500,
    'semi-eco': 2000,
    'force':    2800,
    'full':     4500,
    'bonus':    5200,
}

def econ_advantage_score(team1_econ, team2_econ):
    """Returns positive = team1 advantage, negative = team2 advantage"""
    v1 = ECON_VALUE_APPROX.get(team1_econ, 2500)
    v2 = ECON_VALUE_APPROX.get(team2_econ, 2500)
    return (v1 - v2) / 1000.0  # Normalized
```

### Tier 3: Full Feature Set (When Data Is Available)

```python
features = {
    # Game state
    'team1_score': int,          # Rounds won by team1 so far on this map
    'team2_score': int,          # Rounds won by team2 so far on this map
    'score_diff': int,           # team1_score - team2_score
    'rounds_remaining': int,     # Estimated rounds left in map
    'leverage': float,           # How much this round matters (see below)
    'is_map_point_t1': bool,     # team1 at 12 wins (1 away from map win)
    'is_map_point_t2': bool,
    'is_overtime': bool,         # Score >= 12-12
    
    # Econ state
    'econ_class_t1': str,        # pistol/eco/semi-eco/force/full/bonus
    'econ_class_t2': str,
    'econ_advantage': float,     # Tier-2 numeric score
    'prior_round_winner': int,   # 1=team1 won previous round, 2=team2, 0=round1
    
    # Side
    'team1_side': str,           # attack or defense
    'half': int,                 # 1 or 2 (or overtime half)
    
    # Map context
    'map_name': str,
    'round_number': int,
    
    # Team strength
    'team1_win_prob_pregame': float,  # From pregame odds or Elo
    'team2_win_prob_pregame': float,
    'team_strength_diff': float,
}

# Score leverage: how much does winning this round swing map win probability?
# Highest near 12-12 or 12-X situations, lowest when one team is far ahead.
def score_leverage(t1_score, t2_score):
    total = t1_score + t2_score
    min_to_win = 13  # standard; 14+ for OT
    dist_t1 = min_to_win - t1_score
    dist_t2 = min_to_win - t2_score
    # Leverage is high when both teams are close to winning
    return 1.0 / (dist_t1 * dist_t2 + 0.5)
```

---

## Section 5: Backtest Design

### 5A: Predictive Signal Test — P(next round win | econ state)

**Goal:** Establish empirical win rates by econ matchup type.

**Data needed:** `match_round_data` populated (currently empty).

**Pseudocode:**

```python
def test_round_win_signal(db):
    """
    For each round where team econ class is known:
    - Group by econ matchup type
    - Compute empirical P(round win | econ matchup)
    - Report with confidence intervals
    - Calibrate against prior round outcomes
    """
    rounds = db.query("""
        SELECT 
            mrd.match_id, mrd.map_number, mrd.round_num,
            mrd.team1_economy, mrd.team2_economy,
            mrd.winning_team_side,
            m.team1, m.team2
        FROM match_round_data mrd
        JOIN matches m ON m.id = mrd.match_id
    """)
    
    results = defaultdict(list)
    for r in rounds:
        matchup = classify_round_matchup(r.team1_economy, r.team2_economy)
        results[matchup].append(1 if r.winning_team_side == 1 else 0)
    
    for matchup, outcomes in results.items():
        n = len(outcomes)
        win_rate = np.mean(outcomes)
        ci_low, ci_high = wilson_confidence_interval(sum(outcomes), n)
        print(f"{matchup}: {win_rate:.3f} [{ci_low:.3f}, {ci_high:.3f}] (n={n})")
```

**Expected result (prior from literature):** Full-buy vs Eco: ~80% win rate. But n will be critical — with 2,174 map instances × ~3–5 eco rounds per map ≈ 6,500–10,000 eco round observations. That's enough for decent estimates by category.

### 5B: Contract-Impact Test — Fair Value Swing

**Goal:** Estimate the Kalshi map-contract repricing caused by a round result.

**Method:** Model P(map win | score state X-Y) using historical outcomes.

```python
def build_score_state_model(db):
    """
    For each (team1_score, team2_score, side) combination,
    estimate P(map win for team1) from historical data.
    This is independent of round-level econ data.
    """
    # We CAN derive this from existing data!
    # map_score contains FINAL score. We need intermediate states.
    # Unfortunately, we only have final scores — not intermediate states.
    # We cannot reconstruct the round sequence from the final score alone.
    
    # What we CAN do: use the final score distribution to estimate
    # P(map win | current score) via a Markov model calibrated to observed outcomes.
    
    maps = db.query("""
        SELECT DISTINCT match_id, map_number, map_score,
               team1, team2
        FROM player_map_stats
    """)
    
    # Parse final scores and build calibration set
    score_outcomes = []
    for m in maps:
        score_parts = m.map_score.split('-')
        t1_final = int(score_parts[0])
        t2_final = int(score_parts[1])
        winner = 1 if t1_final > t2_final else 2
        score_outcomes.append({'t1_final': t1_final, 't2_final': t2_final, 'winner': winner})
    
    return score_outcomes


def estimate_map_win_prob_from_score(t1_score, t2_score, side='unknown'):
    """
    Given current score, estimate P(map win for team1).
    Uses a logistic regression or lookup table on historical data.
    
    LIMITATION: This requires round-by-round score data to calibrate properly.
    With only final scores, we must use a Markov model assumption.
    """
    # Markov approximation: each team wins each remaining round with equal probability p
    # P(map win) = sum over all paths where team1 reaches 13 (or OT threshold) first
    # This is conservative — doesn't account for momentum, eco cycles, side advantage
    pass
```

**Key insight:** You CAN build a crude score-state model using a Markov chain + historical win rates even without round-level data. But it won't capture eco-state heterogeneity, which is the entire point of the strategy.

### 5C: Heterogeneity Analysis

```python
def analyze_heterogeneity(rounds_df):
    """
    Break down round win rates by:
    - Scoreline category (early: 0-5 rounds each, mid: 6-10, late: 11+)
    - Close vs blowout map (final score within 3 = close)
    - Side (attack vs defense)
    - Map name
    - Team strength gap (proxied by pregame odds if available)
    - Econ type
    """
    categories = {
        'early': rounds_df[rounds_df['total_rounds_played'] < 12],
        'mid': rounds_df[(rounds_df['total_rounds_played'] >= 12) & 
                         (rounds_df['total_rounds_played'] < 20)],
        'late': rounds_df[rounds_df['total_rounds_played'] >= 20],
        'map_point_t1': rounds_df[rounds_df['t1_score'] == 12],
        'map_point_t2': rounds_df[rounds_df['t2_score'] == 12],
        'overtime': rounds_df[rounds_df['is_overtime']],
    }
    
    for name, subset in categories.items():
        if len(subset) == 0:
            continue
        eco_rounds = subset[subset['econ_matchup'].str.contains('gun_advantage')]
        print_win_rate_table(name, eco_rounds)
```

---

## Section 6: Backtest Quality Standards

### Requirements Checklist

| Requirement | Status | Action Needed |
|------------|--------|--------------|
| No data leakage | N/A (no model yet) | Use time-based train/test splits when building |
| Out-of-sample testing | N/A | Hold out 2025 Stage 2 for final eval |
| Time-based splits | N/A | Split by event: train on Kickoff + Stage 1, test on Stage 2 |
| Calibration diagnostics | N/A | Implement reliability diagrams + Brier score |
| Confidence intervals | ✗ | Add Wilson CI to all win rate estimates |
| No look-ahead | N/A | All features must be computable from data available before round start |

### Time-Based Split Recommendation

```
Training:    VCT 2025 Kickoff (Jan–Feb 2025)
Validation:  VCT 2025 Stage 1 (Mar–May 2025)
Test:        VCT 2025 Stage 2 (Jul–Sep 2025) — hold out until model is frozen
```

---

## Section 7: Tradability / Implementation Analysis

### Contract Type Mismatch

This is the most important structural problem.

Kalshi VCT markets are binary: "Will [team] win this map/match?" priced 0–100 cents.

The signal is round-level. The contract is map-level. The relationship between them is:

```
Current contract price = P(map win | current score state, current game context)

After round result:
New contract price = P(map win | new score state)

Edge = [P(new price) − P(old price)] − [bid/ask spread + fees + slippage]
```

For this to be positive EV:
- `|P(new) - P(old)|` must be large (high-leverage scoreline)
- The market must not have already priced in the econ state (market underreaction required)
- You must be able to execute at or near fair value

### Round-Trip Cost Structure

| Cost Component | Estimated Range | Notes |
|----------------|----------------|-------|
| Bid/ask spread (entry) | 3–10 cents | Kalshi VCT markets are illiquid |
| Bid/ask spread (exit) | 3–10 cents | May widen after round result |
| Kalshi fee | ~2% of payout | Applied to winning side |
| Slippage (market order) | 1–5 cents | Depends on order book depth |
| **Total round-trip cost** | **~10–25 cents** | Conservative estimate |

### Minimum Required δ

For break-even, the fair-value swing must exceed ~15–25 cents (conservative to aggressive estimate). This means the strategy is only viable when:

| Score State | Fair Value Swing (Gun Advantage Round) | Viable? |
|------------|----------------------------------------|---------|
| 0-0 (pistol) | ~2-5 cents | No |
| 5-5 (mid map) | ~5-10 cents | No |
| 10-8 | ~8-15 cents | Borderline |
| 12-11 | ~20-35 cents | Maybe |
| 12-12 (OT) | ~25-40 cents | Possible |
| 12-X (map point) | ~15-30 cents | Possible |

### Latency Window

- Buy phase: 30 seconds before round start
- You need to: detect econ state from stream → calculate → send order → get fill
- Realistic automated pipeline: 5–15 seconds
- This leaves 15–25 seconds of execution window
- Problem: Kalshi order books are thin. Large orders move the price. Small orders may not move it enough to matter.

### Market Liquidity Reality

Kalshi VCT markets are NOT like stock markets. For a $1,000 position:
- The order book depth may only be $200–500 at the best price
- You may move the market just by entering
- Exit liquidity after a round result may be even thinner (everyone knows what happened)
- Queue position matters — if you're not first, you're paying a worse price

### Fill Probability and Queue Position

In thin markets, limit orders near mid often don't fill before the round starts. Market orders guarantee fill but guarantee bad prices. This is a genuine execution challenge with no clean solution at small scale.

---

## Section 8: Realistic Trading Simulation Framework

```python
class EcoRoundTradingSimulator:
    """
    Simulates PnL of the eco-round Kalshi strategy.
    
    Assumptions:
    - Entry at fair value + half-spread (limit order)
    - Exit at new fair value - half-spread (limit order) or market order
    - Partial fill probability modeled
    - Kalshi fee of 2% on winning trades
    """
    
    def __init__(
        self,
        spread_entry: float = 0.05,     # 5-cent spread at entry
        spread_exit: float = 0.07,      # 7-cent spread at exit (wider post-round)
        kalshi_fee_pct: float = 0.02,   # 2% Kalshi fee on payout
        fill_prob_limit: float = 0.65,  # Probability a limit order fills
        slippage_market: float = 0.03,  # Additional slippage if using market order
        min_delta_threshold: float = 0.15,  # Don't trade if expected swing < 15 cents
        max_position_usd: float = 200,      # Max USD per trade
        bankroll: float = 2000,             # Total bankroll
    ):
        self.spread_entry = spread_entry
        self.spread_exit = spread_exit
        self.kalshi_fee_pct = kalshi_fee_pct
        self.fill_prob_limit = fill_prob_limit
        self.slippage_market = slippage_market
        self.min_delta_threshold = min_delta_threshold
        self.max_position_usd = max_position_usd
        self.bankroll = bankroll
    
    def simulate_trade(
        self,
        pre_round_fair_value: float,    # Our estimate of fair P(map win) before round
        market_price_before: float,     # Actual Kalshi price before round
        post_round_fair_value_win: float,  # Fair value if favored team wins round
        post_round_fair_value_lose: float, # Fair value if favored team loses round
        p_round_win: float,             # Our P(favored team wins this round)
        use_market_order: bool = False,
    ) -> dict:
        
        # Decision gate: is there enough expected swing?
        expected_post_round_fv = (
            p_round_win * post_round_fair_value_win +
            (1 - p_round_win) * post_round_fair_value_lose
        )
        expected_delta = expected_post_round_fv - pre_round_fair_value
        
        if abs(expected_delta) < self.min_delta_threshold:
            return {'trade': False, 'reason': 'below_delta_threshold', 'pnl': 0}
        
        # Determine direction
        direction = 1 if expected_delta > 0 else -1  # 1=buy, -1=sell
        
        # Entry cost
        if use_market_order:
            entry_price = market_price_before + direction * (self.spread_entry/2 + self.slippage_market)
            fill_prob = 1.0
        else:
            entry_price = market_price_before + direction * (self.spread_entry / 2)
            fill_prob = self.fill_prob_limit
        
        # Position sizing (Kelly-inspired, simplified)
        edge_per_dollar = abs(expected_delta) - self.spread_entry/2 - self.spread_exit/2
        kelly_fraction = edge_per_dollar / 1.0  # Simplified
        position_usd = min(self.max_position_usd, kelly_fraction * self.bankroll * 0.25)
        contracts = position_usd  # 1 contract = $1 on Kalshi
        
        # Simulate round outcome
        round_win = np.random.random() < p_round_win
        
        # Post-round exit
        if round_win:
            true_post_fv = post_round_fair_value_win
        else:
            true_post_fv = post_round_fair_value_lose
        
        exit_price = true_post_fv - direction * (self.spread_exit / 2)
        
        # PnL calculation
        gross_pnl = direction * (exit_price - entry_price) * contracts
        fee = self.kalshi_fee_pct * max(0, gross_pnl)
        net_pnl = (gross_pnl - fee) * fill_prob  # Weighted by fill probability
        
        return {
            'trade': True,
            'direction': 'buy' if direction == 1 else 'sell',
            'entry_price': entry_price,
            'exit_price': exit_price,
            'contracts': contracts,
            'round_win': round_win,
            'gross_pnl': gross_pnl,
            'fee': fee,
            'net_pnl': net_pnl,
            'fill_prob': fill_prob,
            'expected_delta': expected_delta,
            'actual_delta': true_post_fv - pre_round_fair_value,
        }
    
    def run_simulation(self, rounds: list, n_simulations: int = 1000) -> dict:
        """
        Monte Carlo simulation over a set of round opportunities.
        
        rounds: list of dicts with pre_round_fair_value, market_price_before, etc.
        """
        all_pnls = []
        
        for sim in range(n_simulations):
            sim_pnl = 0
            trades = 0
            for r in rounds:
                result = self.simulate_trade(**r)
                sim_pnl += result['net_pnl']
                if result['trade']:
                    trades += 1
            all_pnls.append(sim_pnl)
        
        return {
            'mean_pnl': np.mean(all_pnls),
            'median_pnl': np.median(all_pnls),
            'std_pnl': np.std(all_pnls),
            'sharpe': np.mean(all_pnls) / (np.std(all_pnls) + 1e-9),
            'win_rate': np.mean([p > 0 for p in all_pnls]),
            'pnl_5th_pct': np.percentile(all_pnls, 5),
            'pnl_95th_pct': np.percentile(all_pnls, 95),
        }


# Example calibration scenarios (requires actual data to populate)
ILLUSTRATIVE_SCENARIOS = [
    # High-leverage: 12-11 score, clean eco for team1
    {
        'pre_round_fair_value': 0.58,
        'market_price_before': 0.55,      # Market underpricing by 3 cents
        'post_round_fair_value_win': 0.78,
        'post_round_fair_value_lose': 0.38,
        'p_round_win': 0.80,              # Full buy vs eco
        'scenario': '12-11, clean anti-eco'
    },
    # Mid-map: 8-6 score, gun advantage
    {
        'pre_round_fair_value': 0.60,
        'market_price_before': 0.58,      # Market underpricing by 2 cents
        'post_round_fair_value_win': 0.67,
        'post_round_fair_value_lose': 0.50,
        'p_round_win': 0.80,
        'scenario': '8-6, gun advantage'
    },
    # Early map: 2-1 score, pistol follow-up
    {
        'pre_round_fair_value': 0.52,
        'market_price_before': 0.51,      # Market barely mispriced
        'post_round_fair_value_win': 0.56,
        'post_round_fair_value_lose': 0.47,
        'p_round_win': 0.65,
        'scenario': '2-1, early eco'
    },
]
```

### Expected PnL Per Trade (Illustrative)

| Scenario | Expected δ | After Costs | Verdict |
|----------|-----------|-------------|---------|
| 12-11 clean anti-eco | ~18 cents | ~+5 cents | Marginal positive |
| 12-12 OT eco | ~22 cents | ~+8 cents | Possible edge |
| 8-6 gun advantage | ~8 cents | ~-7 cents | Negative EV |
| Early eco (2-1) | ~3 cents | ~-17 cents | Strongly negative |

> **Critical assumption:** These numbers require the market to underreact by 2–5 cents relative to fair value. If the market already prices the econ state correctly, δ_exploitable = 0 and all trades are negative EV after costs.

---

## Section 9: Simpler/Better Variants

If the base strategy doesn't survive scrutiny, these are the better-narrowed versions:

### Variant A: High-Leverage Only (Recommended)

Trade ONLY when:
- Score is within 2 rounds of map conclusion (e.g., 11-11, 12-X, 12-12 OT)
- Econ advantage is clean (full buy vs confirmed eco, not force-vs-force)
- Market price is at least 3–4 cents from our fair-value estimate

**Why:** This maximizes δ and filters out the large volume of rounds where the econ signal is real but the contract repricing is economically negligible.

### Variant B: Predict Contract Movement, Not Round Winner

Instead of predicting "who wins the round," predict "how much will the contract reprice." This is a better-aligned objective.

```python
target = post_round_contract_price - pre_round_contract_price
```

A regression model on this target filters out high-round-win-rate but low-δ situations automatically.

### Variant C: Multi-Round Hold

Instead of exiting after every round, hold through an eco cycle (typically 1–3 rounds). The compounding effect of econ advantage can produce larger price moves than single-round trades, and reduces transaction costs.

**Risk:** Hold through a round if you misidentified the eco state.

### Variant D: Map-Point Specialist

Only trade at 12-X (team on map point). The expected δ is consistently large here (a lost map-point round is very painful), and the econ state is often known (the team at 11 often has to force-buy to avoid losing).

### Variant E: No-Trade Filter (Strong Recommendation)

Regardless of which variant you use, implement hard no-trade filters:
- Don't trade when contract price is already >75 or <25 cents (not enough to win/lose)
- Don't trade when estimated fill probability < 50% (no liquidity)
- Don't trade when the market has moved >5 cents since last check (something changed you don't know about)
- Don't trade in pistol rounds (both teams equal, no econ signal)

---

## Section 10: Final Verdict

### Verdict: **Implementable with narrow conditions — but currently NOT testable**

### Reasoning

**The strategy is not dead** because:
- The underlying Valorant mechanic is real — full buy vs eco does produce ~80% round win rates
- High-leverage scorelines DO produce meaningful contract repricing (~15–25 cents)
- If markets underreact to pre-round econ state, there is a structural inefficiency to exploit
- The schema in this repo was already designed for this data

**The strategy is currently NOT testable** because:
- `match_round_data` and `match_map_halves` are empty — zero rows
- No code in the repo populates them
- Without round-level data, the backtest cannot be run
- Without knowing what Kalshi prices were at round-start, market underreaction cannot be measured

**The strategy would be marginal even with data** because:
- Kalshi VCT liquidity is thin — spreads of 5–15 cents are realistic
- The strategy only generates positive EV in maybe 20–30% of eco rounds (the high-leverage ones)
- The execution window is 30 seconds — tight for automated detection + order routing
- Even correct predictions produce δ < 10 cents in most game states — not enough after costs

**The path to live testing requires:**
1. Populate `match_round_data` from VLR.gg (schema already designed)
2. Obtain historical Kalshi prices for VCT contracts
3. Validate that market underreaction actually occurs
4. Prove round-trip cost structure is viable at target scorelines

---

## Top 5 Reasons This Strategy Could Fail (Even If Signal Is Real)

1. **The market already prices econ state.** Kalshi bettors watching the same stream can see the buy phase. If professional bettors react instantly to the econ state, the "underreaction" vanishes before you can trade it. The efficient market hypothesis applies more strongly to publicly visible information.

2. **Spread and fees eat the entire δ.** At 8-6 or earlier in the map, the fair-value swing from an eco round is only 5–10 cents. With 10–20 cents in round-trip costs, every such trade is negative EV by construction. The strategy only works in leverage situations that may represent <20% of all eco rounds.

3. **Fill probability in thin markets is crippling.** Limit orders at or near fair value may not fill in the 30-second buy window. Market orders guarantee fills but at bad prices. There is no clean solution — you're in a low-liquidity environment with a hard time constraint.

4. **Econ detection latency.** Real-time econ state detection requires either: (a) stream parsing with vision APIs (expensive, slow, error-prone), or (b) a dedicated match data feed. VLR.gg does not provide a real-time API. You may learn the econ state 15–20 seconds into the 30-second window, leaving very little time.

5. **Sample size will be too small for significance.** High-leverage eco rounds (score 11-11, 12-X with confirmed full-vs-eco) occur maybe 5–10 times per map in close games, and not all maps go to high-leverage states. In a tournament with 50 maps, you might get 50–100 qualifying trades per season. That is not enough to distinguish genuine edge from variance.

---

## Top 5 Pre-Deployment Validation Requirements

1. **Prove the market underreacts.** Collect 500+ historical eco rounds with contemporaneous Kalshi prices. Show that the time-series of Kalshi contract prices does NOT fully reflect econ state before the round starts. Quantify the gap and its consistency.

2. **Validate the cost model.** Actually measure Kalshi bid/ask spreads during live VCT matches. Confirm that round-trip costs are within the range assumed in the simulation. This requires accessing Kalshi's API or scraping the order book in real time.

3. **Run the full pipeline end-to-end in paper trading.** Build the complete automated system: stream parsing → econ detection → fair-value calculation → order routing → exit. Run it paper-trading for an entire tournament split before committing real money. Measure actual fill rates, latency, and execution quality.

4. **Establish minimum sample for statistical significance.** With a claimed edge of 5–8 cents per qualifying trade and round-trip cost variance of ±15–20 cents, you need roughly 400–600 qualifying trades to distinguish edge from variance at 95% confidence. This may take multiple tournament seasons.

5. **Build a no-eco-state-required baseline.** Before attributing PnL to the econ signal, prove that a naive strategy (e.g., just trading the score state) does NOT also make money. If the score-state alone is sufficient, the econ detection complexity is unnecessary.

---

## Immediate Action Plan

### Step 1 (Unblocks everything): Populate round-level data
```bash
# The schema exists. Write the scraper.
# VLR.gg match pages show round-by-round economy stats.
# Target tables: match_round_data, match_map_halves
# Estimated work: 2–3 days to write + run on existing 428 matches
```

### Step 2: Build score-state Markov model (can do NOW with existing data)
```python
# Use final map scores to calibrate P(map win | current score X-Y)
# This is achievable from player_map_stats alone
# See pseudo-code in Section 5B
```

### Step 3: Obtain Kalshi historical data
```bash
# Kalshi has an API. Historical trade data is publicly available.
# Need: contract prices, timestamps for VCT 2025 maps
# This is the second biggest blocker after round-level data
```

### Step 4: Define the narrow version precisely
```python
# Only trade when ALL conditions are met:
# - Score is within 2 rounds of map conclusion OR in overtime
# - Econ matchup is clean full-buy vs confirmed eco
# - Market price deviates from our fair value by >= 4 cents
# - Fill probability estimate >= 60%
# - Contract price is between 20 and 80 cents (not already decided)
```

---

*Prepared by: Claude Code (skeptical quant mode)*  
*Repository: thunderedge*  
*Data snapshot: 2026-04-08*
