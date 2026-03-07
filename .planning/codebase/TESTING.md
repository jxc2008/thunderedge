# Testing Patterns

**Analysis Date:** 2026-03-07

## Test Framework

**Runner:** None configured.

No test framework is installed or configured for either the frontend or backend:
- No `jest`, `vitest`, `mocha`, `pytest`, or `unittest` in dependencies
- No `jest.config.*`, `vitest.config.*`, `pytest.ini`, or `pyproject.toml` test configs
- No `.github/` CI/CD pipeline directory exists
- `package.json` has no test script (only `dev`, `build`, `start`, `lint`)

## Existing Test Files

**Ad-hoc test scripts (not automated, no assertions):**

- `test_team_route.py` -- Manual Flask test-client check for `/team` route. Prints status code and response snippet. No assertions, no test runner.
- `test_team_scraper.py` -- Manual script that instantiates `TeamScraper` and prints results for "Sentinels". No assertions.
- `test_output.txt` -- Captured output file from a manual test run.

**Verification/debug scripts in root:**

- `verify_data.py` -- Data verification script (checks database contents)
- `check_boaster.py` -- Player-specific data check
- `check_repopulation_status.py` -- Checks scraper repopulation status

**Calibration scripts (quasi-tests):**

- `scripts/calibrate_matchup.py` -- Odds-based model calibration with NLL metrics
- `scripts/calibrate_matchup_results.py` -- Results-based calibration with improvement metrics
- `scripts/verify_edge_math.py` -- Verifies edge calculation mathematics

These scripts validate correctness by printing results for human review, not by running automated assertions.

## Frontend Validation

**Script:** `scripts/validate_frontend.sh`

```bash
# Run TypeScript typecheck
npx tsc --noEmit

# Attempt Next.js compile (informational only)
npx next build --no-lint 2>&1 | grep -E "Compil|error TS|SyntaxError|TypeError" | head -20
```

This is the only automated quality gate. It checks TypeScript compilation but does not run any tests. The full `next build` is known to fail on prerender of `/challengers` and `/moneylines` (pre-existing issue), so only `tsc --noEmit` is considered authoritative.

**Run command:**
```bash
bash scripts/validate_frontend.sh
```

## Test Coverage

**Coverage: 0% -- No automated tests exist.**

There is no test coverage tooling configured (no `c8`, `istanbul`, `coverage.py`, or equivalent).

## Test Types Present

**Unit Tests:** None.
**Integration Tests:** None.
**E2E Tests:** None.
**Snapshot Tests:** None.

## CI/CD Pipeline

**None configured.**

- No `.github/workflows/` directory
- No `Jenkinsfile`, `Dockerfile` for CI, or `.circleci/` config
- `Procfile` exists (Heroku-style deployment) but contains no test steps
- `vercel.json` exists for Vercel deployment but has no build-time test hooks

## Test Coverage Gaps

**Critical untested areas:**

1. **Backend API endpoints (`backend/api.py`, 2265 lines):**
   - 37+ API routes with no endpoint tests
   - Complex query parameter parsing and validation
   - JSON serialization edge cases (NaN/Infinity handling)
   - Error response format consistency

2. **Database layer (`backend/database.py`, 2604 lines):**
   - All SQL queries and aggregations untested
   - Migration logic (ALTER TABLE operations) untested
   - Data integrity assumptions (e.g., `_clean_team_name()`)

3. **Statistical models (`backend/model_params.py`, `backend/matchup_adjust.py`):**
   - Poisson/Negative Binomial distribution fitting
   - Matchup adjustment formula (alpha/beta/gamma constants)
   - Probability computations that directly affect betting recommendations

4. **React components (`components/matchup-page.tsx`, 1623 lines):**
   - No component rendering tests
   - No user interaction tests
   - Complex conditional rendering logic untested

5. **Scrapers (`scraper/rib_scraper.py`, `scraper/vlr_scraper.py`):**
   - HTML parsing fragile to upstream changes
   - No mock-based tests for scraper logic

## How to Run Tests

**There are no tests to run.** The closest equivalents:

```bash
# TypeScript compilation check (frontend)
npx tsc --noEmit

# Full frontend validation script
bash scripts/validate_frontend.sh

# Manual Python test scripts (require running backend)
python test_team_route.py
python test_team_scraper.py

# Manual calibration verification
python scripts/verify_edge_math.py
```

## Recommendations for Adding Tests

**If adding a test framework, follow these patterns based on the existing stack:**

**Frontend (recommended: Vitest + React Testing Library):**
- Install: `vitest`, `@testing-library/react`, `jsdom`
- Co-locate tests: `components/matchup-page.test.tsx`
- Priority targets: `components/data-table.tsx` (pure logic), `lib/api.ts`

**Backend (recommended: pytest):**
- Install: `pytest`, `pytest-cov`
- Test directory: `tests/` at project root
- Naming: `tests/test_api.py`, `tests/test_database.py`
- Priority targets: `backend/model_params.py` (mathematical correctness), `backend/matchup_adjust.py` (probability calculations)
- Use Flask test client (`app.test_client()`) for API tests, following the pattern already shown in `test_team_route.py`

---

*Testing analysis: 2026-03-07*
