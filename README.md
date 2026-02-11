# ThunderEdge – Valorant Betting Analytics

A comprehensive web application that analyzes Valorant player and team statistics from [VLR.gg](https://www.vlr.gg) to evaluate betting lines for kills, KPR (Kills Per Round), and PrizePicks-style combined-map props.

## Features

| Feature | Description |
|--------|-------------|
| **Player Kill Analysis** | Per-map kill lines with over/under evaluation, win/loss breakdown, and margin classification (close/regular/blowout) |
| **PrizePicks Analysis** | Combined kills for maps 1+2 (or any 2-map combo in 3-map matches) with match outcome context (2-0 vs 2-1) |
| **Team Analysis** | Fights per round, pick/ban percentages, and team-level stats from VCT events |
| **Agent & Map Stats** | Per-agent and per-map aggregations (ACS, ADR, KAST, first bloods) |
| **Database Caching** | SQLite cache of 12 VCT 2025 events (~428 matches, 21k+ map stats) for fast lookups |

## Project Structure

```
thunderedge/
├── backend/
│   ├── api.py              # Flask REST API & routes
│   ├── calculator.py        # KPR calculations (weighted avg, exponential smoothing)
│   └── database.py         # SQLite schema & queries
├── scraper/
│   ├── vlr_scraper.py      # VLR.gg web scraper
│   ├── player_processor.py # Player kill line analysis
│   ├── prizepicks_processor.py  # PrizePicks combined-map analysis
│   ├── team_scraper.py     # Team event scraper
│   └── team_processor.py   # Team stats processing
├── frontend/
│   ├── app.py              # Alternative entry (port 5001)
│   └── templates/
│       ├── index.html      # Player analysis UI
│       ├── prizepicks.html # PrizePicks analysis UI
│       └── team.html       # Team analysis UI
├── scripts/
│   └── populate_database.py  # Database population script
├── data/                   # SQLite database (valorant_stats.db)
├── config.py               # Configuration
├── run.py                  # Main entry point
├── repopulate.py           # Quick repopulate (no confirmation)
├── migrate_database.py     # Schema migration for new columns
└── requirements.txt
```

## Installation

### 1. Clone and install

```bash
git clone https://github.com/jxc2008/thunderedge.git
cd thunderedge
pip install -r requirements.txt
```

### 2. Populate the database (recommended)

Populate the cache with all 12 VCT 2025 events (~10–15 min):

```bash
python repopulate.py
```

For interactive mode with confirmation:

```bash
python scripts/populate_database.py
```

To repopulate only Americas & EMEA:

```bash
python repopulate_americas_emea.py
```

### 3. Run the application

```bash
python run.py
```

Open http://localhost:5000

## API Endpoints

### Player Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/player/<IGN>` | Player kill analysis. Query: `?line=15.5` (default kill line) |
| POST | `/api/batch` | Batch player analysis. Body: `{"players": ["TenZ", "aspas"], "line": 15.5}` |

### PrizePicks Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/prizepicks/<IGN>` | Combined kills for maps 1+2. Query: `?line=30.5` (default) |

### Team Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/team/<team_name>` | Team stats (fights/round, pick/bans). Query: `?region=Americas` |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/stats` | Database stats (events, matches, map stats) |
| GET | `/api/cache/status` | Cache status and cached events |

### Web Pages

| Route | Description |
|-------|-------------|
| `/` | Player analysis page |
| `/prizepicks` | PrizePicks analysis page |
| `/team` | Team analysis page |

## How It Works

### Data flow

1. **Scraping** – VLR.gg is scraped for player stats, matches, and team data.
2. **Caching** – Completed VCT events are stored in SQLite. Ongoing events are scraped live.
3. **Processing** – Processors (Player, PrizePicks, Team) compute aggregations and evaluate lines.
4. **Output** – API returns predictions, over/under breakdowns, and classifications.

### Player kill analysis

- **Per-map kills** – Each map is evaluated against the kill line (e.g., 15.5).
- **Margin classification**:
  - **Close**: 2–3 round margin
  - **Regular**: 4–6 round margin
  - **Blowout**: 7+ round margin
- **Win/loss breakdown** – Over/under rates by match outcome and margin.

### PrizePicks analysis

- **Combined kills** – Sum of kills from maps 1 and 2 (or 2-map combos in 3-map matches).
- **Match outcome** – 2-0 (blowout) vs 2-1 (close).
- **Win/loss context** – Over/under rates by match result and margin.

### Database schema (key tables)

- **vct_events** – Event metadata (name, region, status).
- **matches** – Match URLs, teams, event.
- **player_map_stats** – Per-map stats (kills, deaths, assists, ACS, ADR, KAST, agent, map_name).
- **match_pick_bans** – Pick/ban sequence per match.
- **player_event_stats** – Aggregate KPR, rounds, rating per player per event.

## Configuration

In `config.py`:

- `DEFAULT_KILL_LINE` – Default per-map kill line (15.5).
- `DATABASE_PATH` – Override via `DATABASE_PATH` env var.
- `ROUNDS_THRESHOLDS` – Rounds-based classification thresholds.

## Deployment

- **Heroku**: See `DEPLOYMENT.md` and `Procfile`.
- **Vercel**: See `VERCEL_DEPLOYMENT.md` and `vercel.json`.

## Documentation

- `CALCULATION_EXPLANATION.md` – Team fights/round and pick/ban logic.
- `GITHUB_SETUP.md` – GitHub setup notes.

## Important Notes

### Web scraping

- Respect VLR.gg robots.txt and terms of service.
- Built-in delays and caching reduce request volume.
- Proxy env vars are disabled to avoid request issues on some systems.

### Disclaimer

- For educational and prototyping only.
- Not financial or betting advice.
- Check local laws related to sports betting data.

## License

MIT License
