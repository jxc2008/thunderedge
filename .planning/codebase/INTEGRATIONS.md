# External Integrations

**Analysis Date:** 2026-03-07

## APIs & External Services

**Web Scraping (Data Ingestion):**
- **VLR.gg** - Valorant esports match data, team stats, pick/ban data
  - Client: `requests` + `beautifulsoup4` (HTML scraping)
  - Implementation: `scraper/vlr_scraper.py`
  - Rate limiting: User-Agent rotation, retry backoffs (10s-120s)
  - Auth: None (public pages)
  - Also used by: `scripts/populate_atk_def.py` for attack/defense round splits

- **rib.gg** - Player statistics (primary data source, VLR.gg IP-banned for player data)
  - Client: `requests` + `beautifulsoup4` (HTML scraping)
  - Implementation: `scraper/rib_scraper.py`
  - URL patterns: `/events/{slug}/{id}`, `/series/{slug}/{id}`
  - Auth: None (public pages)
  - Lookup priority: cache table > DB match data > live scrape

- **PrizePicks API** - Real-time Valorant player kill lines
  - Endpoint: `https://api.prizepicks.com/projections`
  - League ID: 159 (Valorant)
  - Client: `requests` (JSON API)
  - Implementation: `scraper/prizepicks_api.py`
  - Auth: None (public API, browser User-Agent spoofing)

**AI/ML:**
- **Google Gemini** - Vision API for PrizePicks screenshot parsing
  - Model: `gemini-2.0-flash-lite` (free tier: 15 RPM, 1000 RPD)
  - SDK: `google-generativeai` Python package
  - Implementation: `scraper/vision_parser.py`
  - Auth: `GOOGLE_API_KEY` or `GEMINI_API_KEY` environment variable
  - In-memory cache (image MD5 hash) to avoid duplicate API calls

**Analytics:**
- **Vercel Analytics** - Frontend web analytics
  - SDK: `@vercel/analytics` 1.3.1
  - Implementation: Imported in Next.js app

## Data Storage

**Database:**
- SQLite 3
  - Path: `data/valorant_stats.db` (configurable via `DATABASE_PATH` env var)
  - Client: Python `sqlite3` stdlib (no ORM)
  - Implementation: `backend/database.py` - `Database` class with direct SQL queries
  - Journal mode: WAL (for concurrency and OneDrive compatibility)
  - Connection timeout: 30 seconds
  - Key tables: `players`, `vct_events`, `player_map_stats`, `player_event_stats`, `matches`, `match_pick_bans`, `match_map_halves`, `team_event_stats`, `team_pick_bans`
  - Secondary DB: `data/thunderedge.db` (present but purpose unclear)

**File Storage:**
- Local filesystem only
- No cloud storage integration

**Caching:**
- In-memory caches within Python processes (e.g., vision parser image cache)
- No external cache service (no Redis, Memcached)
- `Config.CACHE_DURATION = 6 hours` defined in `config.py`

## Authentication & Identity

**Auth Provider:**
- None - No user authentication system
- Application is a local analytics tool, no login required

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry, Datadog, etc.)
- Flask global error handlers return JSON error responses (`backend/api.py`)

**Logs:**
- Python `logging` stdlib at INFO level (`backend/api.py`, scrapers)
- No structured logging or log aggregation
- Console output only

## CI/CD & Deployment

**Hosting:**
- Local development (primary use case)
- Vercel Analytics SDK suggests potential Vercel deployment for frontend

**CI Pipeline:**
- No CI/CD configuration detected (no `.github/workflows/`, no `Dockerfile`)
- Validation scripts in `scripts/`: `validate_all.sh`, `validate_backend.sh`, `validate_data.sh`, `validate_frontend.sh`

## Environment Configuration

**Required env vars:**
- `GOOGLE_API_KEY` or `GEMINI_API_KEY` - For PrizePicks screenshot parsing via Gemini (optional; only needed for vision feature)

**Optional env vars:**
- `BACKEND_URL` - Flask backend URL for Next.js proxy (default: `http://localhost:5000`)
- `NEXT_PUBLIC_BACKEND_URL` - Client-side direct backend URL (default: `http://localhost:5000`)
- `DATABASE_PATH` - Override SQLite database file location (default: `data/valorant_stats.db`)

**Secrets location:**
- `.env` file in project root (gitignored)
- Loaded via `python-dotenv` in `config.py`

## Frontend-Backend Communication

**API Proxy:**
- Next.js rewrites `/api/*` to Flask backend (`next.config.js`)
- Client-side code uses `API_BASE` from `lib/api.ts` for direct Flask calls (bypasses Next.js 30s proxy timeout for long-running endpoints)
- All API responses are JSON; Flask sanitizes `Infinity`/`NaN` to `null` via custom JSON provider

**Endpoints:**
- Flask serves ~37 API routes under `/api/`
- Key endpoint groups: `/api/matchup`, `/api/matchup/player-kills`, `/api/matchup/map-probs`, `/api/matchup/mispricing`
- CORS enabled globally via `flask-cors`

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## Data Population Scripts

**Database population (run manually):**
- `scripts/populate_database.py` - Main data population from scrapers
- `scripts/populate_atk_def.py` - Attack/defense round splits from VLR.gg
- `scripts/populate_moneyline.py` - Moneyline odds data
- `scripts/populate_round_data.py` - Round-level data
- `scripts/populate_challengers.py` - Challengers tier data
- `scripts/repopulate_pick_bans.py` - Pick/ban data refresh
- `scripts/scrape_challengers.py` - Challengers event scraping

---

*Integration audit: 2026-03-07*
