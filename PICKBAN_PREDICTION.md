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
| VLR.gg | `matches` | team1, team2, match_id |
| Half-win-rate model | `match_map_halves` | team_name, map_name, atk/def win rates |

**Minimum viable data threshold:**
- ≥ 15 veto appearances per team before team-specific tendencies are used
- Below threshold: fall back to league-average veto tendencies

---

## Model

### Step 1: Win-rate scores

For each (team, map, opponent) triple:

```
ban_score(team, map, opp)  = opp_winrate(map)  - team_winrate(map)   # team bans their disadvantage vs opp
pick_score(team, map, opp) = team_winrate(map) - opp_winrate(map)    # team picks their advantage over opp
```

### Step 2: Tendency prior

From `match_pick_bans`, compute per-team historical frequencies:
```
P(team bans map X)  = count(team banned X) / count(team vetos)
P(team picks map X) = count(team picked X) / count(team picks)
```

### Step 3: Blend

```
final_ban_score(team, map, opp)  = α * tendency_prior + (1-α) * ban_score
final_pick_score(team, map, opp) = α * tendency_prior + (1-α) * pick_score
```

`α` shrinks toward 0 as sample size grows — trust data over prior.
Suggested starting α = 0.4, decaying to 0.1 at 50+ appearances.

### Step 4: Simulate veto

Standard BO3 veto order: ban → ban → pick → pick → ban → ban → decider
Each step: the acting team selects the available map with highest score.

Output: probability distribution over (map1, map2, map3) combinations.

### Step 5: Expected theo

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
Match announced → compute expected theo immediately → trade
                ↓
         pick/ban completes → update theo with actual maps → adjust position if needed
```

Two-stage approach:
1. Enter position early based on predicted map pool (smaller size, wider edge threshold)
2. After pick/ban confirmed: re-evaluate, add size if theo confirms or exit if maps were wrong

---

## Data Threshold for Automation

| Condition | Action |
|---|---|
| Team has < 15 veto appearances | Manual only — flag for human review |
| Team has 15-40 appearances | Semi-auto — compute predicted theo, require human confirmation |
| Both teams have > 40 appearances | Fully automated — enter position pre-veto |

---

## When to Build

- **Now**: infrastructure exists, data is thin (~20-30 vetos per team in 2025 data)
- **Target**: after VCT 2026 Stage 1 completes — should have 40-60 vetos per major team
- **Trigger**: when `SELECT COUNT(*) FROM match_pick_bans WHERE match_id IN
  (SELECT id FROM matches WHERE event_id IN <2026 events>)` exceeds 200

---

## Files (when built)

| File | Purpose |
|---|---|
| `scripts/pickban_model.py` | Compute tendency tables + veto simulator |
| `data/pickban_tendencies.json` | Per-team ban/pick frequency tables |
| `backend/theo_engine.py` | Add `expected_series_theo()` method using predicted map pool |
