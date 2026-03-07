# Codebase Concerns

**Analysis Date:** 2026-03-07

## Tech Debt

**Monolithic Frontend Components (High):**
- Issue: Several page components are excessively large single-file components with no decomposition
- Files: `components/matchup-page.tsx` (1623 lines), `app/prizepicks/page.tsx` (915 lines), `app/challengers-prizepicks/page.tsx` (823 lines), `app/challengers/page.tsx` (706 lines), `app/page.tsx` (653 lines)
- Impact: Hard to maintain, review, or test individual sections. Merge conflicts likely when multiple features touch same file.
- Fix approach: Extract logical sections (e.g., ParlayBuilder, MapProbability, PlayerKillProjections) into separate components under `app/_components/` or `components/`.

**Monolithic Backend Files (High):**
- Issue: `backend/api.py` (2265 lines) contains all 37+ API routes in a single file. `backend/database.py` (2604 lines) contains all database methods in a single class.
- Files: `backend/api.py`, `backend/database.py`
- Impact: Difficult to navigate, high risk of merge conflicts, no separation of concerns between feature domains.
- Fix approach: Split `api.py` into route blueprints by domain (player, matchup, prizepicks, scraper). Split `database.py` into mixin classes or separate modules by domain.

**Legacy Frontend Remains (Medium):**
- Issue: Old Flask-served HTML templates still exist alongside the Next.js app, and Flask routes still serve them
- Files: `frontend/templates/index.html`, `frontend/templates/challengers.html`, `frontend/templates/prizepicks.html`, `frontend/templates/team.html`, `frontend/templates/moneylines.html`, `frontend/templates/edge.html`, `frontend/templates/challengers-prizepicks.html`, `frontend/app.py`
- Impact: Confusion about which frontend is authoritative. Flask routes at lines 131-143 of `backend/api.py` serve legacy HTML.
- Fix approach: Remove legacy frontend templates and Flask HTML-serving routes once Next.js frontend is fully validated.

**Debug/Utility Scripts at Project Root (Low):**
- Issue: One-off debug and test scripts scattered at project root
- Files: `check_boaster.py`, `check_repopulation_status.py`, `repopulate.py`, `repopulate_americas_emea.py`, `test_team_route.py`, `test_team_scraper.py`
- Impact: Clutters root directory. Not part of any test framework. Likely stale.
- Fix approach: Remove or move to a `scripts/debug/` directory.

**Dirty Team Names in Database (Medium):**
- Issue: Team names in `matches.team1/team2` are polluted with event name suffixes (e.g., "Nrg Vct 2025 Americas Stage 2 Lbf" instead of "Nrg Esports"). Requires runtime cleanup via `Database._clean_team_name()`.
- Files: `backend/database.py` (line 1400, `_clean_team_name`), scraper output
- Impact: Every query that displays team names must remember to clean them. Inconsistent matching across the codebase.
- Fix approach: Clean team names at scrape/insert time rather than at read time.

**NULL match_date Column (Medium):**
- Issue: `matches.match_date` is NULL for all rows. The codebase uses `event_id` as a chronological proxy instead.
- Files: `backend/database.py` (schema at line 66)
- Impact: Cannot sort or filter matches by actual date. Temporal queries are unreliable.
- Fix approach: Backfill match dates from scraped data (VLR match pages contain dates).

## Security Considerations

**CORS Wide Open (Medium):**
- Risk: `CORS(app)` with no origin restrictions allows any domain to call the API
- Files: `backend/api.py` (line 34)
- Current mitigation: None. App is currently localhost-only.
- Recommendations: If deployed publicly, restrict CORS origins to the Next.js frontend domain.

**Debug Mode in Production Entry Points (Medium):**
- Risk: `app.run(debug=True)` is hardcoded in both entry points, which exposes the Werkzeug debugger (interactive Python console) if deployed without gunicorn
- Files: `backend/api.py` (line 2265), `run.py` (line 38), `frontend/app.py` (line 19)
- Current mitigation: Production should use gunicorn (listed in requirements.txt) which ignores `debug=True`.
- Recommendations: Use `debug=os.getenv('FLASK_DEBUG', False)` or remove `debug=True` from `__main__` blocks.

**No API Authentication (Medium):**
- Risk: All API endpoints are publicly accessible with no auth. Scraper trigger endpoints (`/api/sync/trigger`) can be invoked by anyone.
- Files: `backend/api.py` (all routes)
- Current mitigation: Localhost-only deployment.
- Recommendations: Add API key or session auth before any public deployment.

**No Input Validation on Query Parameters (Low):**
- Risk: Query parameters like `line`, `combo_maps`, `over_odds`, `under_odds` are cast directly with `float()` / `int()` inside try/except blocks. While SQL injection is prevented by parameterized queries, malformed inputs only produce generic 500 errors.
- Files: `backend/api.py` (lines 151, 244, 289-291, 367-368, 417-421, 515-517)
- Current mitigation: Global exception handler returns JSON error responses (line 71).
- Recommendations: Add explicit validation with meaningful error messages before processing.

**Subprocess Execution in API (Low):**
- Risk: The sync endpoint runs Python scripts via `subprocess.run()`. Script paths are hardcoded (not user-controlled), so injection risk is minimal.
- Files: `backend/api.py` (line 2212)
- Current mitigation: Script paths are constructed from constants, not user input.
- Recommendations: No immediate action needed.

## Performance Bottlenecks

**New SQLite Connection Per Query (High):**
- Problem: Every database method opens a new `sqlite3.connect()`, executes one query, then closes the connection. No connection pooling or reuse.
- Files: `backend/database.py` (pattern repeats ~60 times, e.g., lines 348, 374, 406, 434, 462, 484, 513, 546, 627, 654, 676)
- Cause: Each method follows the pattern: `conn = sqlite3.connect(self.db_path, timeout=30.0)` ... `finally: conn.close()`
- Improvement path: Use a connection pool (e.g., `sqlite3` with a thread-local connection) or context manager that reuses connections within a request.

**Matchup Endpoint Makes Multiple Sequential DB Calls (Medium):**
- Problem: The `/api/matchup` endpoint (line 813 of `backend/api.py`) calls 10+ database methods sequentially for each team, each opening its own connection.
- Files: `backend/api.py` (matchup route), `backend/database.py` (all `get_team_*` methods)
- Cause: No batching or single-query approach for aggregated team data.
- Improvement path: Combine related queries or pass a shared connection through the request lifecycle.

**No Server-Side Caching for Computed Results (Medium):**
- Problem: Expensive computations like distribution fitting (`compute_distribution_params`) and matchup projections are recalculated on every request.
- Files: `backend/api.py`, `backend/model_params.py`
- Cause: No in-memory cache (e.g., `@lru_cache`, Redis, or TTL dict) for computed results.
- Improvement path: Cache team stats and distribution params with a TTL matching `Config.CACHE_DURATION` (6 hours).

**Browser Caching Explicitly Disabled (Low):**
- Problem: `Cache-Control: no-cache, no-store, must-revalidate` headers are set on several endpoints, forcing the browser to re-fetch on every visit.
- Files: `backend/api.py` (lines 798-799, 855)
- Cause: Intentional to ensure fresh data during development.
- Improvement path: Add short-lived cache headers (e.g., 5 minutes) for read-only endpoints in production.

## Fragile Areas

**Scraper HTML Parsing (High):**
- Files: `scraper/vlr_scraper.py` (1481 lines), `scraper/rib_scraper.py` (897 lines), `scraper/team_scraper.py` (1222 lines)
- Why fragile: Scrapes VLR.gg and rib.gg HTML with BeautifulSoup CSS selectors. Any site redesign breaks data ingestion silently.
- Safe modification: Test against cached HTML snapshots before deploying changes.
- Test coverage: Zero automated tests. 7 bare `except:` clauses silently swallow errors across these files (`scraper/player_processor.py:37`, `scraper/team_scraper.py:402`, `scripts/populate_database.py:400,488,495`, `scraper/vlr_scraper.py:972,979`).

**Broad Exception Handling (Medium):**
- Files: `backend/database.py` (55+ `except Exception as e` blocks), `backend/api.py` (30+ `except Exception as e` blocks)
- Why fragile: Every database method catches `Exception` broadly and returns empty results (`None`, `[]`, `{}`). This masks bugs — a schema mismatch or logic error silently returns "no data" instead of failing visibly.
- Safe modification: Narrow exception types. Let unexpected errors propagate to the global handler.
- Test coverage: None.

**Team Name Matching (Medium):**
- Files: `backend/database.py` (line 1395, `_normalize_team`)
- Why fragile: Uses SQL `LIKE '%team_name%'` for team matching. This can match unintended teams (e.g., "G2" matches "G2 Esports" but also any team containing "G2").
- Safe modification: Use exact match after normalization, or maintain a team alias lookup table.
- Test coverage: None.

## Scaling Limits

**SQLite Single-Writer (Medium):**
- Current capacity: Single concurrent writer, multiple readers (WAL mode enabled)
- Limit: Cannot handle multiple simultaneous write operations (e.g., concurrent scraper runs + API writes)
- Scaling path: Migrate to PostgreSQL if concurrent writes become necessary.

**In-Process Scraping (Medium):**
- Current capacity: Scrapers run in the Flask process or via subprocess
- Limit: Long-running scrape operations block the API thread or consume subprocess resources
- Scaling path: Move scraping to a background task queue (Celery, RQ).

## Dependencies at Risk

**Pinned Python Dependencies (Low):**
- Risk: `requirements.txt` pins exact versions (e.g., `flask==3.0.0`, `numpy==1.26.2`, `scipy==1.11.4`) from late 2023. These may have known CVEs.
- Impact: Security patches not applied automatically.
- Migration plan: Use version ranges (e.g., `flask>=3.0,<4.0`) or update pins periodically.

**Scraping Target Dependency (High):**
- Risk: Entire data pipeline depends on VLR.gg and rib.gg remaining scrapable. No API contracts or fallback sources.
- Impact: If either site blocks scraping, adds anti-bot measures, or changes HTML structure, all data ingestion stops.
- Migration plan: Cache scraped data aggressively. Consider official APIs if available.

## Test Coverage Gaps

**Zero Automated Tests (Critical):**
- What's not tested: The entire codebase has no test files, no test framework configured, no CI pipeline.
- Files: No `*.test.*` or `*.spec.*` files exist anywhere. `test_team_scraper.py` and `test_team_route.py` at root are ad-hoc manual scripts, not framework tests.
- Risk: Any change can silently break functionality. Regressions are discovered only through manual testing.
- Priority: Critical. At minimum, add unit tests for `backend/database.py` query methods, `backend/model_params.py` distribution fitting, and `backend/matchup_adjust.py` adjustment calculations.

## Build/Deployment Concerns

**Next.js Build Failure (High):**
- Problem: `npm run build` fails on prerender of `/challengers` and `/moneylines` pages with `e[o] is not a function` webpack runtime error.
- Files: `app/challengers/page.tsx`, `components/moneyline-page.tsx`
- Trigger: Pre-existing issue. Occurs during static generation.
- Workaround: TypeScript typecheck (`npx tsc --noEmit`) passes. Dev server works. Production build requires fixing the prerender issue or marking pages as `force-dynamic`.

**No CI/CD Pipeline (Medium):**
- Problem: No GitHub Actions, no automated linting, no automated tests, no deployment automation.
- Files: No `.github/workflows/` directory exists.
- Impact: Relies entirely on manual deployment and manual validation.
- Fix approach: Add basic CI with TypeScript check, Python lint, and (once created) test execution.

**Dual Frontend Serving (Low):**
- Problem: Flask serves legacy HTML templates while Next.js runs on port 3000. Both can serve the same conceptual pages.
- Files: `backend/api.py` (lines 131-143), `frontend/templates/`, `app/` (Next.js pages)
- Impact: Unclear which frontend a user should use. Legacy templates may show stale UI.
- Fix approach: Remove Flask HTML-serving routes and legacy templates.

## Data Integrity Issues

**No Foreign Key Enforcement (Medium):**
- Problem: SQLite foreign keys are not enforced by default (`PRAGMA foreign_keys` not set). Schema uses no `FOREIGN KEY` constraints.
- Files: `backend/database.py` (schema definition, lines 19-340)
- Impact: Orphaned rows possible (e.g., `player_map_stats` referencing deleted players).
- Fix approach: Add `PRAGMA foreign_keys = ON` and define foreign key constraints in schema.

**Silent Data Loss on Scraper Errors (Medium):**
- Problem: Bare `except:` clauses in scraper code silently swallow all exceptions, including data corruption or partial writes.
- Files: `scraper/player_processor.py:37`, `scraper/team_scraper.py:402`, `scripts/populate_database.py:400,488,495`, `scraper/vlr_scraper.py:972,979`
- Impact: Partial or corrupt data saved without any error indication.
- Fix approach: Replace bare `except:` with specific exception types. Log errors even when continuing.

---

*Concerns audit: 2026-03-07*
