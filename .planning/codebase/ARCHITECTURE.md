# Architecture

**Analysis Date:** 2026-03-07

## Pattern Overview

**Overall:** Client-Server with separate Next.js frontend (port 3000) and Flask backend (port 5000)

**Key Characteristics:**
- Next.js App Router serves all UI pages as client-side rendered (`'use client'`) React components
- Flask serves a REST JSON API at `/api/*` endpoints; Next.js proxies `/api/*` to Flask via `next.config.js` rewrites
- Some long-running endpoints (player analysis, edge analysis) bypass the Next.js proxy and call Flask directly from the browser using `API_BASE` (`http://localhost:5000`)
- SQLite is the sole data store (`data/valorant_stats.db`), accessed directly by the Flask backend via the `Database` class
- Web scrapers (VLR.gg, rib.gg) run in-process on the Flask server, triggered by API requests
- A legacy Flask-served HTML frontend exists in `frontend/templates/` (Jinja2 templates), superseded by the Next.js app but still wired up via Flask routes

## Layers

**Presentation (Next.js Frontend):**
- Purpose: Renders all user-facing pages; handles form inputs and displays analysis results
- Location: `app/`, `components/`, `lib/`
- Contains: Page components (`app/*/page.tsx`), reusable UI components (`components/*.tsx`), API helper (`lib/api.ts`), types (`lib/types/`)
- Depends on: Flask API via fetch calls
- Used by: Browser

**API Layer (Flask):**
- Purpose: Exposes REST endpoints for all analytics, orchestrates scraping and computation
- Location: `backend/api.py`
- Contains: All route definitions (~40 endpoints), request parsing, response formatting, global error handlers
- Depends on: `backend/database.py`, `backend/model_params.py`, `backend/prop_prob.py`, `backend/matchup_adjust.py`, `backend/market_implied.py`, `backend/odds_utils.py`, `scraper/*`
- Used by: Next.js frontend (via fetch)

**Data Access (Database):**
- Purpose: SQLite read/write operations, schema initialization, all query methods
- Location: `backend/database.py` (2604 lines, single `Database` class)
- Contains: Table creation/migration, CRUD for players, matches, events, stats; all team matchup query methods
- Depends on: SQLite3 stdlib
- Used by: `backend/api.py`, scrapers

**Analytics Engine:**
- Purpose: Statistical modeling for kill line predictions, edge analysis, matchup adjustments
- Location: `backend/model_params.py`, `backend/prop_prob.py`, `backend/matchup_adjust.py`, `backend/market_implied.py`, `backend/odds_utils.py`, `backend/calculator.py`
- Contains: Negative binomial / Poisson distribution fitting, over/under probability computation, matchup-adjusted kill projections, expected value calculations
- Depends on: `numpy`, `scipy`, `backend/database.py`
- Used by: `backend/api.py`

**Scraping Layer:**
- Purpose: Fetches live player/team data from external sites
- Location: `scraper/`
- Contains:
  - `scraper/vlr_scraper.py` (1481 lines) - VLR.gg scraper for VCT player data and team analysis
  - `scraper/rib_scraper.py` (897 lines) - rib.gg scraper for PrizePicks data (avoids VLR IP bans)
  - `scraper/team_scraper.py` (1222 lines) - Team-level data scraping
  - `scraper/player_processor.py` (356 lines) - Processes scraped player data into analysis results
  - `scraper/prizepicks_processor.py` (568 lines) - PrizePicks-specific processing (combo maps)
  - `scraper/prizepicks_api.py` (135 lines) - Fetches live PrizePicks projections
  - `scraper/vision_parser.py` (275 lines) - OCR/vision parsing for PrizePicks screenshots
  - `scraper/team_processor.py` (121 lines) - Team data processing
- Depends on: `requests`, `beautifulsoup4`, `backend/database.py`
- Used by: `backend/api.py`

**Configuration:**
- Purpose: Centralized settings
- Location: `config.py`
- Contains: Database path, scraping settings (headers, base URLs), betting thresholds, cache duration
- Depends on: Environment variables, `.env` file
- Used by: All backend modules

## Data Flow

**Player Kill Line Analysis:**
1. User enters player IGN + kill line on homepage (`app/page.tsx`)
2. Browser fetches `{API_BASE}/api/player/{ign}?line={line}` directly (bypasses Next.js proxy for timeout reasons)
3. Flask route in `backend/api.py` calls `VLRScraper.get_player_by_ign()` which scrapes VLR.gg live
4. Scraped data saved to SQLite via `Database.save_player_data()`
5. `PlayerProcessor.evaluate_betting_line()` computes KPR, over/under percentages, classification
6. If matchup odds provided, `compute_distribution_params()` + `apply_matchup_adjustment()` adjust probabilities
7. Optional second fetch to `/api/edge/{ign}` for Monte Carlo edge analysis
8. JSON response rendered by React components (`OverUnderDisplay`, `StatsGrid`, `RecommendationCard`, etc.)

**Team Matchup Analysis:**
1. User enters two team names + optional odds on matchup page (`app/team/page.tsx`)
2. Browser fetches `/api/matchup?team1=X&team2=Y` (via Next.js proxy)
3. Flask calls `Database.get_team_matchup_data()` which aggregates: overview, pick/ban, map records, recent matches, comps, fights per round, K/D, atk/def rates, projected scores
4. Three parallel secondary fetches: `/api/matchup/player-kills`, `/api/matchup/map-probs`, `/api/matchup/mispricing`
5. `MatchupPage` component (`components/matchup-page.tsx`, 1623 lines) renders all sections

**PrizePicks Analysis:**
1. User enters player IGN on PrizePicks page (`app/prizepicks/page.tsx`)
2. Browser fetches `/api/prizepicks/{ign}?line={line}&combo_maps={n}`
3. Flask uses `RibScraper` (rib.gg) instead of VLR to avoid IP bans
4. `PrizePicksProcessor` computes combo-map kill projections
5. Leaderboard feature uses `/api/prizepicks/leaderboard` with optional image upload for OCR parsing

**State Management:**
- No global state management library (no Redux, Zustand, etc.)
- Each page uses local `useState` hooks for form inputs, loading state, results, and errors
- No client-side caching or shared state between pages
- Backend caches scraped data in SQLite tables (`player_data_cache`, `combo_cache`)

## Key Abstractions

**Database (singleton pattern):**
- Purpose: All SQLite operations through a single class
- Examples: `backend/database.py` - instantiated once in `backend/api.py` as `db = Database(Config.DATABASE_PATH)`
- Pattern: Methods return plain dicts/lists; raw SQL queries with parameter binding; WAL journal mode for concurrency

**Scrapers (class-based):**
- Purpose: Encapsulate HTTP scraping logic per data source
- Examples: `scraper/vlr_scraper.py` (`VLRScraper`), `scraper/rib_scraper.py` (`RibScraper`), `scraper/team_scraper.py` (`TeamScraper`)
- Pattern: Accept `Database` instance in constructor; user-agent rotation; retry with exponential backoff; BeautifulSoup HTML parsing

**Processors (class-based):**
- Purpose: Transform scraped data into analytics results
- Examples: `scraper/player_processor.py` (`PlayerProcessor`), `scraper/prizepicks_processor.py` (`PrizePicksProcessor`)
- Pattern: Accept `kill_line` in constructor; main method is `evaluate_betting_line(player_data)`

**Reusable UI Components:**
- Purpose: Shared visual building blocks across pages
- Examples: `components/stats-grid.tsx`, `components/data-table.tsx`, `components/collapsible-section.tsx`, `components/over-under-display.tsx`
- Pattern: Props-driven, stateless display components; inline styles + Tailwind CSS classes

## Entry Points

**Next.js Frontend:**
- Location: `app/layout.tsx` (root layout), `app/page.tsx` (homepage)
- Triggers: Browser navigation
- Responsibilities: Renders all pages via App Router file-based routing

**Flask Backend:**
- Location: `run.py` (development server), `api/index.py` (Vercel serverless entry)
- Triggers: `python run.py` starts Flask on port 5000; Vercel uses `api/index.py`
- Responsibilities: Imports `backend/api.app` Flask application

**Population Scripts (offline):**
- Location: `scripts/populate_database.py`, `scripts/populate_challengers.py`, `scripts/populate_moneyline.py`, `scripts/populate_atk_def.py`, `scripts/populate_round_data.py`
- Triggers: Manual CLI execution
- Responsibilities: Bulk-scrape and populate the SQLite database

## Error Handling

**Strategy:** Global Flask error handlers catch all exceptions and return JSON error responses

**Patterns:**
- `backend/api.py` registers `@app.errorhandler(Exception)` and `@app.errorhandler(500)` that return `{'error': message}` JSON
- `_json_error_response()` uses `json.dumps` directly (not Flask's JSON pipeline) to avoid double-failure
- `_SafeJSONProvider` replaces `float('inf')` and `float('nan')` with `null` to prevent browser JSON.parse errors
- Individual route handlers wrap logic in try/except and return `jsonify({'error': str(e)}), 500`
- Frontend pages display errors via inline error banners using local `error` state
- Scrapers use retry with backoff (`_RETRY_BACKOFFS`) for transient HTTP failures

## Cross-Cutting Concerns

**Logging:** Python `logging` module; Flask request/response logging via `@app.before_request` / `@app.after_request` middleware in `backend/api.py`

**Validation:** Minimal - Flask routes check for required query params and return 400; no schema validation library; frontend relies on HTML input types

**Authentication:** None - all endpoints are public, no auth layer

**CORS:** Enabled globally via `flask_cors.CORS(app)` in `backend/api.py`

**Caching:** SQLite-based caching of scraped player data (`player_data_cache` table); `Config.CACHE_DURATION = 6 hours`; no HTTP caching (responses include `Cache-Control: no-cache`)

---

*Architecture analysis: 2026-03-07*
