# Team Statistics Calculation Explanation

## 1. Fights Per Round Calculation

### Formula
```
Fights Per Round = (Total Kills + Total Deaths) / Total Rounds
```

### How it's calculated:

**Step 1: For each match in an event:**
- The system scrapes each map played in the match
- For each map, it finds the team's stat table (by matching roster players)
- It sums up kills and deaths from **all 5 players** on the roster for that map

**Step 2: Accumulate across all maps:**
- `map_kills` = sum of kills from all 5 players in that map
- `map_deaths` = sum of deaths from all 5 players in that map
- `map_rounds` = number of rounds played in that map

**Step 3: Accumulate across all matches:**
- `total_kills` = sum of all `map_kills` from all maps in all matches
- `total_deaths` = sum of all `map_deaths` from all maps in all matches
- `total_rounds` = sum of all `map_rounds` from all maps in all matches

**Step 4: Calculate fights per round:**
- `fights_per_round = (total_kills + total_deaths) / total_rounds`

### Example for Sentinels (VCT 2026: Americas Kickoff):
Based on the test output:
- Total Kills: 472
- Total Deaths: 486
- Total Rounds: 141
- **Fights Per Round = (472 + 486) / 141 = 958 / 141 = 6.794**

### Code Location:
- Kills/deaths accumulation: `scraper/team_scraper.py` lines 605-635 (per player per map)
- Map totals: lines 673-675 (accumulate per map)
- Match totals: lines 925-927 (accumulate per match)
- Final calculation: line 982 (fights_per_round formula)

---

## 2. Pick/Ban Percentage Calculation

### Formula
```
Percentage = (Count of times map was picked/banned / Total matches) × 100
```

### How it's calculated:

**Step 1: For each match:**
- The system extracts pick/ban data from the match page
- It identifies which maps the team banned first, banned second, picked first, and picked second
- This is stored as counts: `{'first_ban': {'Bind': 1}, 'second_ban': {'Haven': 2}, ...}`

**Step 2: Accumulate counts across all matches:**
- For each action type (first_ban, second_ban, first_pick, second_pick)
- Count how many times each map appears
- Example: If Sentinels banned "Bind" as their first ban in 3 matches, `first_ban['Bind'] = 3`

**Step 3: Calculate percentages:**
- For each map in each action type: `percentage = (count / total_matches) × 100`
- Round to 2 decimal places

### Example for Sentinels (VCT 2026: Americas Kickoff):
Based on the test output:
- Total Matches: 4
- First Ban counts: `{'Bind': 1, 'Breeze': 1, 'Abyss': 1}`
- First Pick counts: `{'Split': 2, 'Pearl': 1}`

**First Ban Percentages:**
- Bind: (1 / 4) × 100 = **25.00%**
- Breeze: (1 / 4) × 100 = **25.00%**
- Abyss: (1 / 4) × 100 = **25.00%**

**First Pick Percentages:**
- Split: (2 / 4) × 100 = **50.00%**
- Pearl: (1 / 4) × 100 = **25.00%**

### Code Location:
- Pick/ban extraction: `scraper/team_scraper.py` lines 162-382 (`get_match_pick_bans`)
- Count accumulation: lines 935-949 (track counts per match)
- Percentage calculation: `scraper/team_processor.py` lines 81-121 (`_calculate_pick_ban_rates`)

---

## Important Notes:

1. **Fights Per Round is NOT the sum of individual KPRs and DPRs**
   - It's calculated from the **raw totals** (sum of all kills + sum of all deaths) divided by total rounds
   - This gives the team's combined engagement rate per round

2. **Pick/Ban percentages are based on matches, not maps**
   - Each match contributes one pick/ban action per category (first_ban, second_ban, etc.)
   - If a team plays 4 matches, the percentages are out of 4 (100% total across all maps)

3. **Roster matching**
   - The system matches roster players to identify which stat table belongs to the team
   - It uses flexible matching (exact match or substring match) to handle name variations
   - Only maps where at least 2 roster players are found are counted
