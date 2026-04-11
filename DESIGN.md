# Pre-Match TheoEngine — Design Document

## Overview

Fires once per match after pick/ban completes (~5 minutes before map 1 start).
Computes a theoretical series win probability, compares it to Kalshi's market price,
and posts passive limit orders if the edge is large enough.

---

## Inputs

| Input | Source | Notes |
|---|---|---|
| Team A, Team B | VLR.gg pick/ban page | Scraped post-ban |
| Map pool (2-3 maps) | VLR.gg pick/ban page | In play order |
| Starting sides per map | VLR.gg pick/ban page | Which team starts atk/def |
| `half_win_rates.json` | Half-win-rate model | Per-(team, map, side) win rates |
| Kalshi series winner market | Kalshi API | Current ask/bid + last price |

---

## Theo Calculation — Step by Step

### Step 1: Per-map round win probability

For each map in the pool, for each half:

```
p_round = (team_a_rate_on_side + (1 - team_b_rate_on_opposite_side)) / 2
```

- `team_a_rate_on_side`: team A's historical win rate on attack/defense for this map
- `team_b_rate_on_opposite_side`: team B's win rate on the other side
- Averaging these two perspectives gives a consensus round probability
- Fallback chain: team-specific → league average for (map, side) → overall average

This gives two probabilities per map:
- `p1`: P(team A wins a round) in rounds 1–12 (starting sides)
- `p2`: P(team A wins a round) in rounds 13–24 (sides swapped)

### Step 2: Markov map win probability

Dynamic programming over `(a_score, b_score)` states.
Map ends when either team reaches 13 rounds.
OT (12-12) resolved at 50/50 — no economic edge modeled in OT.

Output: `P(team A wins this map)`

### Step 3: Market-odds adjustment

The per-map rates are historical averages against the full field.
They don't capture the specific matchup strength gap.
The Kalshi market implicitly prices this in.

```
market_p     = kalshi_yes_ask / 100          # market's series win prob for team A
naive_map_p  = markov_result_at_50_50        # what model gives when both teams are equal
model_map_p  = markov_result_with_real_rates # what model gives with actual rates
map_delta    = model_map_p - naive_map_p     # how much our maps shift prob vs a coin flip

final_theo   = market_p + map_delta
```

This uses the market as the baseline (accounts for overall skill gap) and the
map model to adjust up or down depending on which team has the map advantage.

Clamp `final_theo` to [0.05, 0.95].

### Step 4: Series win probability

For a BO3 with maps M1, M2, M3:

```
P(2-0) = p(M1) * p(M2)
P(2-1) = p(M1) * (1-p(M2)) * p(M3)  +  (1-p(M1)) * p(M2) * p(M3)
P(series) = P(2-0) + P(2-1)
```

Map independence is assumed.

---

## Edge Detection

```
edge = final_theo - (kalshi_yes_ask / 100)
```

Only trade if `abs(edge) > MIN_EDGE` (suggested: 0.05 = 5 cents).

| edge > 0 | Buy YES (market underpricing team A) |
| edge < 0 | Buy NO / Sell YES (market overpricing team A) |

---

## Order Execution

- Post passive limit orders (do not take liquidity)
- Bid at `theo - SPREAD/2`, ask at `theo + SPREAD/2` (suggested spread: 4 cents)
- Size: fixed fractional Kelly or flat unit size (configurable)
- Cancel unfilled orders if match starts (avoid getting filled at stale price)

---

## Confidence Tiers

Based on how much data backs the team-map rates:

| Tier | Condition | Action |
|---|---|---|
| HIGH | Both teams have ≥15 effective rounds on all maps in pool | Full size |
| MED | At least one team has data on each map | Half size |
| LOW | Significant fallback to league average | Skip or minimal size |

---

## Trigger Logic

1. Poll VLR.gg match page every 30s starting 30 min before scheduled match time
2. Detect pick/ban completion: all maps listed + starting sides visible
3. Run TheoEngine
4. Post orders
5. Set cancellation timer for match start

---

## Fallbacks

- Team name not in `half_win_rates.json` → use league average for that (map, side)
- Map not in `half_win_rates.json` → use overall league average
- Kalshi market not found → abort, do not trade
- Pick/ban not parseable → abort, log warning

---

## Files

| File | Purpose |
|---|---|
| `backend/theo_engine.py` | Markov model + market adjustment |
| `backend/market_maker.py` | Edge detection + order sizing + execution |
| `scraper/pickban_watcher.py` | Poll VLR.gg for pick/ban completion |
| `run_market_maker.py` | Entry point — wires all pieces together |
| `data/half_win_rates.json` | Shared from half-win-rate branch |

---

## Open Questions

- How to handle maps with zero data for one or both teams (new team, new map)?
  Currently falls back to league average — acceptable for now.
- Should we model pick/ban tendencies to predict maps before they're announced?
  We have `match_pick_bans` data (856 rows). Future optimization.
- Kelly fraction sizing vs flat unit — needs backtest to determine which is safer
  given the small sample of Kalshi fills at acceptable odds.
