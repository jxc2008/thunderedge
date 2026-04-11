# Pick/Ban Prediction Model — Design Document

## Overview

Predict the map pool before pick/ban is announced, so the pre-match theo can
be computed as soon as a match is scheduled rather than waiting 5 minutes for
the veto to complete. Wider trading window, more time to get filled.

---

## Data Required

| Source | Table | Fields needed |
|---|---|---|
| VLR.gg | `match_pick_bans` | first_ban, second_ban, first_pick, second_pick, decider, match_id |
| VLR.gg | `matches` | team1, team2, event_id, match_id |
| VLR.gg | `vct_events` | id, event_name, year (for stage ordering) |
| Half-win-rate model | `match_map_halves` | team_name, map_name, atk/def win rates |

---

## Data Philosophy

No minimum match threshold. The model runs as long as a team has appeared in
at least one pick/ban. With thin data the tendency prior is simply down-weighted
and the win-rate score dominates — the output is still a valid probability
distribution, just with wider uncertainty.

---

## Recency Weighting

VCT teams adapt their map pools between stages. Use event-round weighting to
emphasise recent data:

| Stage | Weight |
|---|---|
| Current stage (e.g. Stage 1) | 1.0 |
| Previous stage (e.g. Kickoff) | 0.5 |
| Older (e.g. prior year) | 0.0 (excluded) |

```
weighted_ban_count(team, map) = Σ w(match) * I(team banned map in match)
effective_appearances(team)   = Σ w(match) for all matches involving team
```

Same `_extract_round_key()` logic from `half_win_rate_model.py`.

---

## Model

### Step 1: Win-rate scores (quantitative baseline)

For each (team, map, opponent) triple:

```
ban_score(team, map, opp)  = opp_winrate(map)  - team_winrate(map)
pick_score(team, map, opp) = team_winrate(map) - opp_winrate(map)
```

Win rates come from `half_win_rates.json` (already recency-weighted).

### Step 2: Tendency prior (qualitative, scales with data)

From `match_pick_bans`, compute weighted per-team frequencies:
```
P(team bans map X)  = weighted_ban_count(team, X)  / effective_appearances(team)
P(team picks map X) = weighted_pick_count(team, X) / effective_appearances(team)
```

### Step 3: Blend

```
α(n) = min(0.4, n / 20)        # n = effective_appearances

final_ban_score  = α * tendency_prior + (1-α) * win_rate_score
final_pick_score = α * tendency_prior + (1-α) * win_rate_score
```

α scales continuously with data — no hard cutoffs:

| Effective appearances | α (tendency weight) |
|---|---|
| 1 | 0.05 |
| 5 | 0.25 |
| 8+ | 0.40 (cap) |

α is capped at 0.4 regardless of sample size because VCT teams change map
pools between stages and no frequency table should fully override the math.
Teams with only 1-2 matches still get a prediction; tendency just contributes
less.

### Step 4: Manual override

A per-team annotation dict can hard-set known tendencies that data hasn't
captured yet (e.g. team just overhauled their map pool mid-season):
```python
MANUAL_OVERRIDES = {
    'SEN': {'always_ban': 'Lotus'},
    'NRG': {'never_pick': 'Abyss'},
}
```
Applied after Step 3.

### Step 5: Simulate veto

Standard BO3 veto order: ban → ban → pick → pick → ban → ban → decider
Each step: the acting team selects the available map with the highest score.

Output: probability distribution over (map1, map2, map3) combinations.

### Step 6: Expected theo

```
E[theo] = Σ P(map_pool) * series_theo(team_a, team_b, map_pool)
```

This gives a pre-veto expected series win probability.

---

## Integration with Market Maker

**Current flow:**
```
Match announced → wait for pick/ban (~5 min window) → compute theo → trade
```

**With pick/ban prediction:**
```
Match announced → compute E[theo] immediately → enter small position
                ↓
         pick/ban confirmed → update theo with actual maps → adjust size
```

Two-stage approach:
1. Enter early based on predicted map pool — smaller size, wider edge threshold (8+ cents)
2. After pick/ban: re-evaluate with exact maps, add to position or exit if maps diverged

---

## When to Build

- **Now viable**: any team with ≥ 1 match in `match_pick_bans` gets a prediction
- **Practical trigger**: at least one match of current-stage pick/ban data for both teams
- **Auto-check**: `auto_update.py` reports effective appearances per team every run

---

## Files (when built)

| File | Purpose |
|---|---|
| `scripts/pickban_model.py` | Compute weighted tendency tables + veto simulator |
| `data/pickban_tendencies.json` | Per-team weighted ban/pick frequency tables |
| `backend/theo_engine.py` | Add `expected_series_theo()` using predicted map pool |
