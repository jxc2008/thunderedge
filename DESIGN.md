# In-Match Eco-Round Strategy — Design Document

## Overview

Runs continuously during a live match. Monitors round-by-round economy states
scraped from VLR.gg. When one team is on a full buy and the other is on eco,
fires a short-duration bet on the map winner market — because the gun team wins
~82% of eco rounds, this creates a reliable short-term edge.

---

## Core Insight

Not all rounds are equal. The economy cycle creates predictable win probability
spikes:

```
Pistol round (1, 13)     : ~50/50 — no economic advantage
Gun round (pistol winner): ~65-70% for gun team
Eco round (pistol loser) : ~18% for eco team  (GUN_WIN_RATE = 0.822)
Semi-buy                 : ~35-45% depending on equipment delta
Full buy vs full buy     : back to team skill baseline
```

After a team wins the pistol, the next 1-3 rounds are highly predictable
regardless of team skill — the gun team almost always wins. This is the window
to exploit.

---

## Economy Classification

Based on total team credits at round start (from `match_round_data`):

| Label | Credits | Implication |
|---|---|---|
| full | ≥ 20,000 | Rifles + armor + util |
| semi-buy | 10,000–19,999 | Mix of rifles/smgs |
| semi-eco | 5,000–9,999 | Pistols + some util |
| eco | < 5,000 | Pistols only |

**Signal fires when:** one team is `full` and the other is `eco` or `semi-eco`.

---

## Round Win Probability Model

Two-layer probability:

### Layer 1: Economy advantage
Base probability from economy matchup:

| Situation | P(gun team wins round) |
|---|---|
| full vs eco | 0.822 (empirical backtest) |
| full vs semi-eco | ~0.65 (estimated) |
| full vs semi-buy | ~0.55 |
| full vs full | back to skill model |

### Layer 2: Skill adjustment
Even on eco rounds, team skill matters at the margins.
Blend economy probability with team's historical round win rate:

```
p_round = (1 - SKILL_ALPHA) * economy_prob  +  SKILL_ALPHA * team_skill_rate
```

Suggested `SKILL_ALPHA = 0.15` — economy dominates but skill nudges the number.

### Layer 3: Map score context
If one team leads 10-2, their win probability is already very high regardless
of eco. The map score provides a prior that prevents over-betting on stale edges.

Use `live_map_win_prob(t1_score, t2_score)` from TheoEngine as the baseline,
then update it with the round eco signal:

```
updated_map_prob = bayesian_update(
    prior=live_map_win_prob,
    likelihood_ratio=eco_round_lr,   # how much this round shifts things
)
```

---

## Signal Detection Pipeline

```
Poll VLR.gg live match page (every ~10s)
    ↓
Parse current round number + economy values for both teams
    ↓
Classify economy state (full / semi-buy / semi-eco / eco)
    ↓
Is this a pistol round? (round 1 or 13) → skip (50/50, no edge)
Is round > 24? → skip (OT — both teams reset to full buy, no eco edge)
    ↓
Is economy gap large enough? (full vs eco/semi-eco)
    ↓
Compute gun team's win probability for THIS round
    ↓
Convert round win prob → map win prob delta
    ↓
Compare to current Kalshi map winner market price
    ↓
Edge > threshold? → fire order
```

---

## Map Win Probability Update

A single round win doesn't directly translate to a map win — you need to
propagate it through the remaining rounds. Use the live Markov model:

1. Get current score `(t1_score, t2_score)` and current side
2. Temporarily override `p_round` for THIS round with the eco probability
3. For all subsequent rounds, use normal skill-based probabilities
4. Run DP from current state with the overridden first-round probability

This gives the true map win probability update from the eco signal.

---

## Bet Structure

- Market: **map winner** (shorter duration, resolves within ~45 min)
- Entry: passive limit buy at `updated_map_prob - SPREAD` (don't take spread)
- Exit: let it expire naturally when map ends OR close early if map score makes
  position obvious (e.g. up 12-3, sell to lock in profit)
- Position cap: max 1 open position per map at a time
- No OT bets — both teams reset to full buy, eco edge disappears

---

## Economy Parsing

VLR.gg live match page structure:
- Economy data visible in the "Economy" tab per round
- Fields: team1_economy, team2_economy (total credits)
- Round number: parsed from round indicator

Current `match_round_data` table schema already stores this.
Live scraper needs to read the live version, not historical.

---

## Calibration Data

From `match_round_data` backtest (712 rows):
- `GUN_WIN_RATE = 0.822` — gun team wins 82.2% of eco rounds
- This is hardcoded and should not be changed without re-running the backtest
- Sample is Americas only — may differ slightly by region/meta

---

## Timing

```
Round starts → economy visible on VLR.gg
  ↓ ~5-10s scrape lag
Economy parsed → signal computed → order sent
  ↓ ~1-2s API call
Order on book
  ↓ ~20-30s
Round resolves → position profitable or not
```

Total window: ~40 seconds from round start to resolution.
Must post limit (not market) order — taker spread makes market orders unprofitable.

---

## Files

| File | Purpose |
|---|---|
| `scraper/live_score_poller.py` | Polls VLR.gg, parses economy + score |
| `scraper/kalshi_client.py` | Kalshi API wrapper |
| `scraper/kalshi_order_manager.py` | Position tracking + order execution |
| `backend/theo_engine.py` | `live_map_win_prob()` for score-adjusted probs |

---

## Open Questions

- **Semi-buy probability**: 0.65 and 0.55 are estimates. Need to run backtest
  on `match_round_data` to get empirical values for semi-buy and semi-eco matchups.
- **Regional meta differences**: Gun win rate may vary by region (EMEA vs Americas).
  Current 0.822 is Americas-only. Needs validation on EMEA/Pacific data.
- **Pistol round value**: Pistol is 50/50 but the winner gets 2-3 effectively free
  rounds. Could bet on the 2-3 rounds AFTER the pistol rather than the pistol itself.
  Higher EV but requires more precise timing.
- **Kalshi map winner market liquidity**: Series winner has more volume.
  Map winner markets may be thin — need to check typical order book depth
  before assuming fills are available at reasonable prices.
