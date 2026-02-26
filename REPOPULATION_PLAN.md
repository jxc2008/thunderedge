# Database Repopulation Plan

## Current Data Structure
- Player map stats: kills, deaths, assists per map
- Match info: URL, event, teams, date
- Event stats: KPR, rounds, rating, ACS, ADR

## New Data to Add

### 1. Map Scores ✓ (Column already added)
**Table:** `player_map_stats.map_score`
- **Format:** "13-6", "16-14", "11-13"
- **Source:** VLR match page header per map
- **Status:** Schema updated, needs scraping logic

### 2. Pick/Ban Sequence (Adapt from team_scraper.py)
**New Table:** `match_pick_bans`
```sql
CREATE TABLE match_pick_bans (
    id INTEGER PRIMARY KEY,
    match_id INTEGER,
    map_number INTEGER,  -- Which map in the series (1, 2, 3)
    first_ban TEXT,      -- e.g., "Bind"
    second_ban TEXT,     -- e.g., "Haven"
    first_pick TEXT,     -- e.g., "Split"
    second_pick TEXT,    -- e.g., "Pearl"
    decider TEXT,        -- The remaining map
    FOREIGN KEY (match_id) REFERENCES matches (id)
)
```
- **Source:** VLR match page pick/ban text (already implemented in team_scraper.py line 155-395)
- **Reuse:** `get_match_pick_bans()` method

### 3. Agent Data Per Player ✓ (Confirmed extractable)
**New Table:** `player_agent_stats`
```sql
CREATE TABLE player_agent_stats (
    id INTEGER PRIMARY KEY,
    match_id INTEGER,
    player_name TEXT,
    map_number INTEGER,
    agent TEXT,          -- e.g., "jett", "viper", "killjoy"
    kills INTEGER,
    deaths INTEGER,
    assists INTEGER,
    acs INTEGER,
    adr INTEGER,
    kast REAL,
    first_bloods INTEGER,
    FOREIGN KEY (match_id) REFERENCES matches (id),
    UNIQUE(match_id, player_name, map_number)
)
```
- **Source:** VLR match page - `<img class='mod-agent' alt='jett'>`
- **Status:** Confirmed extractable (tested successfully)

### 4. Additional Per-Map Data (Recommended)
**Add to** `player_map_stats`:
- `map_name TEXT` -- e.g., "Bind", "Haven", "Split"
- `acs INTEGER` -- Average Combat Score
- `adr INTEGER` -- Average Damage per Round
- `kast REAL` -- Kill, Assist, Survive, Trade %
- `first_bloods INTEGER` -- First blood count
- `clutches INTEGER` -- Clutches won (if available)

### 5. Match Result Data (Recommended)
**Add to** `matches`:
- `winner TEXT` -- Team that won the match
- `score TEXT` -- Match score (e.g., "2-1", "2-0")

## Suggested Scraping Strategy

### Phase 1: Update Schema
1. Add new tables (match_pick_bans, player_agent_stats)
2. Add new columns to existing tables
3. Create indexes for performance

### Phase 2: Update Scraper
1. Modify `_get_match_map_kills_and_scores()` to extract:
   - Map scores ✓ (already done)
   - Map names
   - Agent per player
   - Additional stats (ACS, ADR, KAST, etc.)
2. Add pick/ban extraction to player match scraping (reuse team_scraper logic)
3. Update `save_player_data()` to store all new fields

### Phase 3: Repopulate
1. Clear old partial data (or add columns gracefully)
2. Run repopulation script for all 4 regions (Americas, EMEA, Pacific, China)
3. Verify data completeness

## Questions Before Proceeding

1. **Agent stats aggregation:** Do you want cumulative stats per agent across all events? (e.g., "aspas on Jett: 500 kills across 20 maps")

2. **Map scores for analysis:** How will you use map scores? Close games (13-11) vs blowouts (13-3) might affect player performance.

3. **Pick/ban utility:** For player analysis (not just team), do you want to see which maps players perform best on when their team picks vs gets picked into?

4. **Additional stats priority:** Which stats are most important?
   - ACS/ADR (damage output)
   - KAST% (consistency)
   - First bloods (aggression)
   - Clutches (1vX situations)

5. **Performance considerations:** Scraping all this data will be slower. Should we:
   - Add progress indicators?
   - Scrape in batches?
   - Run overnight?

Let me know your preferences and I'll implement the complete solution!
