# Agent & Map Analysis - Now Available!

## Overview

The PrizePicks analysis now includes detailed breakdowns by **agent combinations** and **map combinations**, answering questions like:
- "How often does aspas hit his line on Jett vs Raze?"
- "Which map combinations does he perform best on?"

## Features Implemented

### 1. Database Methods

**`get_player_agent_aggregation(player_name)`**
- Returns stats per agent across all events
- Includes: matches played, maps played, total kills, K/D, avg ACS/ADR/KAST

**`get_player_map_aggregation(player_name)`**
- Returns stats per map across all events
- Includes: times played, total kills, K/D, avg ACS/ADR/KAST, avg kills per map

### 2. PrizePicks Processor Updates

**`_calculate_agent_hit_rates(match_results, kill_line)`**
- Analyzes hit rates for each agent combination (e.g., "Jett + Raze")
- Returns: combinations played, hits, hit rate %, avg kills

**`_calculate_map_hit_rates(match_results, kill_line)`**
- Analyzes hit rates for each map combination (e.g., "Bind + Haven")
- Returns: combinations played, hits, hit rate %, avg kills

### 3. API Response

The `/api/prizepicks/<player>` endpoint now returns:

```json
{
  "player_ign": "aspas",
  "hit_percentage": 65.5,
  "agent_analysis": [
    {
      "agent_combo": "Jett + Raze",
      "agents": ["Jett", "Raze"],
      "combinations": 5,
      "hits": 5,
      "hit_rate": 100.0,
      "avg_kills": 39.8
    },
    ...
  ],
  "map_analysis": [
    {
      "map_combo": "Bind + Lotus",
      "maps": ["Bind", "Lotus"],
      "combinations": 2,
      "hits": 1,
      "hit_rate": 50.0,
      "avg_kills": 38.0
    },
    ...
  ]
}
```

## Example Results (aspas)

### Overall
- **Hit Rate:** 65.5%
- **Total Combinations:** 55
- **Hits:** 36

### By Agent
| Agent Combo | Games | Hit Rate | Avg Kills |
|-------------|-------|----------|-----------|
| Jett + Raze | 5 | 100% | 39.8 |
| Jett + Neon | 4 | 100% | 40.0 |
| Jett + Jett | 6 | 66.7% | 34.0 |
| Raze + Raze | 3 | 33.3% | 31.7 |

### By Map
| Map Combo | Games | Hit Rate | Avg Kills |
|-----------|-------|----------|-----------|
| Lotus + Pearl | 2 | 100% | 36.0 |
| Haven + Pearl | 1 | 100% | 41.0 |
| Icebox + Sunset | 1 | 100% | 45.0 |
| Bind + Lotus | 2 | 50% | 38.0 |

## Insights

From aspas's data, we can see:
- ✅ **Best agent combo:** Jett + Raze (100% hit rate, 39.8 avg kills)
- ✅ **Best map combo:** Icebox + Sunset (100% hit rate, 45.0 avg kills)
- ⚠️ **Risky:** Raze + Raze (only 33.3% hit rate)
- ⚠️ **Avoid:** Lotus + Sunset (0% hit rate, 19.0 avg kills)

## Next Steps

To display this on the frontend:
1. Update `prizepicks.html` to show agent/map breakdown sections
2. Add filtering/sorting options
3. Create visualizations (charts showing hit rates by agent/map)
4. Add tooltips with detailed stats

The backend is **fully ready** - all data is being calculated and returned!
