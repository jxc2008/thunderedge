# Codebase Structure

**Analysis Date:** 2026-03-07

## Directory Layout

```
thunderedge/
├── api/                    # Vercel serverless entry point
├── app/                    # Next.js App Router pages
│   ├── _components/        # Page-specific sub-components
│   ├── challengers/        # /challengers route
│   ├── challengers-prizepicks/  # /challengers-prizepicks route
│   ├── moneylines/         # /moneylines route
│   ├── prizepicks/          # /prizepicks route
│   ├── team/               # /team (matchup) route
│   ├── globals.css          # Global CSS (Tailwind + custom)
│   ├── layout.tsx           # Root layout
│   ├── not-found.tsx        # 404 page
│   └── page.tsx             # Homepage (Kill Line analyzer)
├── backend/                # Flask API + analytics engine
├── components/             # Shared React components
├── data/                   # SQLite database files
├── docs/                   # Strategy specification docs
├── frontend/               # Legacy Flask-served HTML (superseded)
│   └── templates/          # Jinja2 HTML templates
├── lib/                    # Frontend utilities and types
│   ├── api.ts              # API_BASE URL helper
│   └── types/              # TypeScript type definitions
├── scraper/                # Web scrapers (VLR, rib.gg)
├── scripts/                # Database population & analytics scripts
├── config.py               # Centralized Python configuration
├── run.py                  # Flask dev server entry point
├── next.config.js          # Next.js config (API proxy rewrites)
├── package.json            # Node.js dependencies
├── requirements.txt        # Python dependencies
├── tsconfig.json           # TypeScript config
├── tailwind.config.js      # Tailwind CSS config
├── vercel.json             # Vercel deployment config
└── Procfile                # Heroku deployment config
```

## Directory Purposes

**`api/`:**
- Purpose: Vercel serverless function entry point
- Contains: `index.py` (imports and re-exports Flask `app` from `backend/api.py`)
- Key files: `api/index.py`

**`app/`:**
- Purpose: Next.js App Router pages - each subdirectory is a route
- Contains: `page.tsx` files for each route, `layout.tsx` for root HTML shell
- Key files:
  - `app/page.tsx` (653 lines) - Homepage, VCT player kill line analyzer
  - `app/team/page.tsx` (285 lines) - Team matchup page (input form + `MatchupPage` component)
  - `app/prizepicks/page.tsx` (915 lines) - PrizePicks analyzer with leaderboard, parlay builder
  - `app/challengers/page.tsx` (706 lines) - Challengers (tier 2) player analyzer
  - `app/challengers-prizepicks/page.tsx` (823 lines) - Challengers PrizePicks analyzer
  - `app/moneylines/page.tsx` (89 lines) - Moneyline strategy page (static demo data)
  - `app/layout.tsx` (31 lines) - Root layout with fonts, metadata, dark theme
  - `app/not-found.tsx` (17 lines) - 404 page

**`app/_components/`:**
- Purpose: Page-specific sub-components (not shared across pages)
- Contains: Components used only by specific pages
- Key files: `input-panel.tsx` (235 lines), `kpi-strip.tsx` (109 lines)

**`backend/`:**
- Purpose: Flask API server and all server-side analytics logic
- Contains: API routes, database access, statistical models, matchup adjustments
- Key files:
  - `backend/api.py` (2265 lines) - All Flask route definitions (~40 endpoints)
  - `backend/database.py` (2604 lines) - `Database` class with schema + all query methods
  - `backend/model_params.py` (288 lines) - Distribution parameter estimation (Poisson/NegBin)
  - `backend/prop_prob.py` (252 lines) - Over/under probability computation
  - `backend/matchup_adjust.py` (175 lines) - Kill projection adjustment based on team win probability
  - `backend/market_implied.py` (207 lines) - Market-implied parameter computation
  - `backend/odds_utils.py` (175 lines) - Odds conversion and EV calculations
  - `backend/calculator.py` (86 lines) - Basic kill line calculator

**`components/`:**
- Purpose: Shared React UI components used across multiple pages
- Contains: Reusable display components (tables, charts, cards, navigation)
- Key files:
  - `components/matchup-page.tsx` (1623 lines) - Full matchup analysis display (largest component)
  - `components/moneyline-page.tsx` (638 lines) - Moneyline strategy display
  - `components/app-header.tsx` (392 lines) - Navigation header with dropdowns + sync button
  - `components/ux-patterns.tsx` (334 lines) - Shared UI primitives (EmptyState, etc.)
  - `components/team-page.tsx` (271 lines) - Single-team analysis display
  - `components/edge-section.tsx` (238 lines) - Monte Carlo edge analysis display
  - `components/data-table.tsx` (229 lines) - Generic sortable/filterable data table
  - `components/search-form.tsx` (224 lines) - Player search form component
  - `components/distribution-chart.tsx` (195 lines) - Kill distribution chart (recharts)
  - `components/event-card.tsx` (199 lines) - Event detail card
  - `components/recommendation-card.tsx` (144 lines) - Bet recommendation display
  - `components/over-under-display.tsx` (142 lines) - Over/under percentage bars
  - `components/stats-grid.tsx` (94 lines) - Grid of stat cards
  - `components/event-timeline.tsx` (76 lines) - Event timeline display
  - `components/collapsible-section.tsx` (64 lines) - Expandable content section
  - `components/matchup-box.tsx` (51 lines) - Matchup adjustment display
  - `components/kill-chips.tsx` (27 lines) - Kill count chip badges

**`data/`:**
- Purpose: SQLite database storage
- Contains: `valorant_stats.db` (primary), `thunderedge.db` (secondary/legacy)
- Generated: Yes (by scraper/populate scripts)
- Committed: Yes (checked into git)

**`docs/`:**
- Purpose: Strategy specification documents
- Contains: `CHALLENGERS_STRATEGY_PROMPT.md`, `CHALLENGERS_STRATEGY_SPEC.md`, `MONEYLINE_STRATEGY_SPEC.md`

**`frontend/`:**
- Purpose: Legacy Flask-served HTML templates (superseded by Next.js app)
- Contains: `templates/` directory with HTML files for each page
- Key files: `frontend/templates/index.html`, `frontend/templates/challengers.html`, etc.
- Note: Flask still routes to these for legacy HTML endpoints (`/`, `/challengers`, etc.) but the Next.js app is the primary frontend

**`lib/`:**
- Purpose: Frontend TypeScript utilities and type definitions
- Contains: API configuration, shared types
- Key files:
  - `lib/api.ts` (9 lines) - Exports `API_BASE` URL (uses `NEXT_PUBLIC_BACKEND_URL` or defaults to `http://localhost:5000`)
  - `lib/types/matchupAnalytics.ts` - TypeScript types for matchup analytics

**`scraper/`:**
- Purpose: Web scraping modules for VLR.gg and rib.gg
- Contains: Scraper classes, data processors, API clients
- Key files:
  - `scraper/vlr_scraper.py` (1481 lines) - VLR.gg HTML scraper (primary player data source)
  - `scraper/rib_scraper.py` (897 lines) - rib.gg scraper (PrizePicks, avoids VLR IP bans)
  - `scraper/team_scraper.py` (1222 lines) - Team-level data scraping
  - `scraper/player_processor.py` (356 lines) - Player data analysis (KPR, classification)
  - `scraper/prizepicks_processor.py` (568 lines) - PrizePicks combo-map processing
  - `scraper/prizepicks_api.py` (135 lines) - Fetches live PrizePicks projections
  - `scraper/vision_parser.py` (275 lines) - OCR parsing for PrizePicks screenshots
  - `scraper/team_processor.py` (121 lines) - Team data processing

**`scripts/`:**
- Purpose: Offline database population and analytics scripts
- Contains: Bulk scraping scripts, calibration scripts, validation scripts
- Key files:
  - `scripts/populate_database.py` - Bulk populate DB from VLR.gg events
  - `scripts/populate_challengers.py` - Populate Challengers (tier 2) data
  - `scripts/populate_moneyline.py` - Populate moneyline match data
  - `scripts/populate_atk_def.py` - Scrape attack/defense halftime splits from VLR.gg
  - `scripts/populate_round_data.py` - Populate round-level data
  - `scripts/repopulate_pick_bans.py` - Re-scrape pick/ban data
  - `scripts/calibrate_matchup.py` - Odds-based matchup calibration
  - `scripts/calibrate_matchup_results.py` - Results-based matchup calibration
  - `scripts/moneyline_analytics.py` - Moneyline strategy analysis
  - `scripts/validate_frontend.sh` - Frontend validation (uses `tsc --noEmit`)
  - `scripts/validate_backend.sh` - Backend validation
  - `scripts/validate_all.sh` - Full validation suite

## Key File Locations

**Entry Points:**
- `run.py`: Flask development server (`python run.py` -> port 5000)
- `api/index.py`: Vercel serverless entry (imports Flask app)
- `app/layout.tsx`: Next.js root layout
- `app/page.tsx`: Next.js homepage

**Configuration:**
- `config.py`: Python backend config (DB path, scraping settings, thresholds)
- `next.config.js`: Next.js config (API proxy rewrites, webpack alias)
- `tsconfig.json`: TypeScript config (path alias `@/*` -> `./*`)
- `tailwind.config.js`: Tailwind CSS config
- `postcss.config.mjs`: PostCSS config
- `vercel.json`: Vercel deployment (Python serverless)
- `Procfile`: Heroku deployment
- `.env`: Environment variables (exists, not read for security)

**Core Logic:**
- `backend/api.py`: All API endpoint definitions
- `backend/database.py`: All database operations
- `backend/model_params.py`: Statistical distribution fitting
- `backend/matchup_adjust.py`: Kill projection adjustments
- `components/matchup-page.tsx`: Team matchup UI (largest React component)

**Testing:**
- `scripts/validate_frontend.sh`: TypeScript compilation check
- `scripts/validate_backend.sh`: Backend validation
- `test_team_route.py`: Manual team route test
- `test_team_scraper.py`: Manual team scraper test

## Naming Conventions

**Files:**
- Python: `snake_case.py` (e.g., `vlr_scraper.py`, `model_params.py`)
- React components: `kebab-case.tsx` (e.g., `matchup-page.tsx`, `app-header.tsx`)
- Next.js pages: `page.tsx` inside route directories (e.g., `app/team/page.tsx`)

**Directories:**
- Python packages: `snake_case` (e.g., `backend/`, `scraper/`)
- Next.js routes: `kebab-case` (e.g., `challengers-prizepicks/`)
- Special Next.js: `_components/` prefix for non-route directories inside `app/`

**Exports:**
- React components: Named exports with PascalCase (e.g., `export function MatchupPage()`)
- Python classes: PascalCase (e.g., `Database`, `VLRScraper`, `PlayerProcessor`)

## Where to Add New Code

**New API Endpoint:**
- Add route in `backend/api.py` following existing pattern: `@app.route('/api/new-endpoint')` with try/except wrapper
- Add database query method in `backend/database.py` if needed
- Follow JSON response pattern: `jsonify({'success': True, ...})` or `jsonify({'error': msg}), status_code`

**New Frontend Page:**
- Create directory `app/{route-name}/page.tsx` with `'use client'` directive
- Import `AppHeader` from `@/components/app-header` for consistent navigation
- Add navigation link in `components/app-header.tsx` (either `NAV_DROPDOWNS` or `NAV_DIRECT` arrays)

**New Shared Component:**
- Place in `components/{component-name}.tsx`
- Use named export with PascalCase function name
- Export TypeScript interfaces for props
- Import in pages via `@/components/{component-name}`

**New Page-Specific Component:**
- Place in `app/_components/{component-name}.tsx`
- Only used by components within `app/` directory

**New Scraper:**
- Place in `scraper/{source_name}_scraper.py`
- Accept `Database` instance in constructor
- Use user-agent rotation and retry backoff patterns from existing scrapers

**New Analytics Module:**
- Place in `backend/{module_name}.py`
- Import and use in `backend/api.py`

**New Population Script:**
- Place in `scripts/populate_{data_type}.py`
- Follow existing pattern: import `Database`, `Config`, iterate over data and call `db.save_*()` methods

**New TypeScript Types:**
- Place in `lib/types/{domain}.ts`

## Special Directories

**`.next/`:**
- Purpose: Next.js build output and cache
- Generated: Yes
- Committed: No (in `.gitignore`)

**`data/`:**
- Purpose: SQLite database files
- Generated: Yes (by populate scripts)
- Committed: Yes

**`frontend/templates/`:**
- Purpose: Legacy Jinja2 HTML templates served by Flask
- Generated: No
- Committed: Yes
- Note: Superseded by Next.js app but still served by Flask routes

**`node_modules/`:**
- Purpose: Node.js dependencies
- Generated: Yes
- Committed: No

**`__pycache__/`:**
- Purpose: Python bytecode cache
- Generated: Yes
- Committed: No

---

*Structure analysis: 2026-03-07*
