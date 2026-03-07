# Coding Conventions

**Analysis Date:** 2026-03-07

## Naming Patterns

**Files (TypeScript/React):**
- Components use kebab-case: `matchup-page.tsx`, `data-table.tsx`, `app-header.tsx`
- Page routes use Next.js App Router convention: `app/{route}/page.tsx`
- Co-located page components use underscore-prefixed directory: `app/_components/input-panel.tsx`
- Shared components live in root `components/` directory
- Lib/utility files use kebab-case: `lib/api.ts`
- Type definition files use camelCase: `lib/types/matchupAnalytics.ts`

**Files (Python):**
- snake_case throughout: `api.py`, `database.py`, `model_params.py`, `matchup_adjust.py`
- Scraper files named by source: `rib_scraper.py`, `vlr_scraper.py`, `team_scraper.py`
- Scripts are verb-noun: `populate_database.py`, `calibrate_matchup.py`, `populate_atk_def.py`
- Test scripts (ad-hoc) prefixed with `test_`: `test_team_route.py`, `test_team_scraper.py`

**Functions (TypeScript):**
- React components: PascalCase function declarations (`function OverviewSection(...)`, `export function DataTable(...)`)
- Helper functions: camelCase (`classificationToType`, `handleAnalyze`, `handleSync`)
- Event handlers: `handle` prefix (`handleKey`, `handleSync`, `handleToggleMobile`)
- Boolean derivations: `is` or `can` prefix (`isActive`, `canAnalyze`)

**Functions (Python):**
- Public methods: snake_case (`get_team_overview`, `compute_distribution_params`)
- Private/internal: underscore prefix (`_sanitize_floats`, `_parse_matchup_inputs`, `_odds_to_implied_prob`)
- Flask routes: snake_case matching endpoint purpose (`get_player_analysis`, `batch_analysis`)

**Variables (TypeScript):**
- camelCase for local state: `team1Odds`, `isLoading`, `syncState`
- UPPER_SNAKE for constants: `T1_COLOR`, `T2_COLOR`, `NAV_DROPDOWNS`, `PAGE_BADGES`
- React state hooks: `[value, setValue]` pattern

**Variables (Python):**
- snake_case: `kill_line`, `team_win_prob`, `db_path`
- Module-level constants: UPPER_SNAKE (`_RETRY_BACKOFFS`, `VCT_2026_KICKOFF_EVENTS`)
- Class constants: UPPER_SNAKE (`BASE_URL`, `DATABASE_PATH`)

**Types (TypeScript):**
- Interfaces: PascalCase with descriptive names (`MatchupData`, `TeamOverview`, `PlayerKillStats`)
- Exported from component file where primarily used (`components/matchup-page.tsx` exports 30+ interfaces)
- Re-exported via type registry: `lib/types/matchupAnalytics.ts`
- Type unions: literal string unions (`'BET_OVER' | 'BET_UNDER' | 'NO_BET'`, `'asc' | 'desc' | null`)

**Types (Python):**
- Type hints from `typing` module: `Dict`, `List`, `Optional` (not using modern `dict`, `list` syntax)
- Used on function signatures in backend modules: `backend/model_params.py`, `backend/matchup_adjust.py`
- Not consistently applied across all files (scrapers have less typing)

## Code Style

**Formatting (TypeScript):**
- 2-space indentation
- Single quotes for strings
- No semicolons (omitted consistently)
- No ESLint config file present; `package.json` has `"lint": "eslint ."` script but no `.eslintrc`
- No Prettier config file present
- JSX uses self-closing tags where applicable
- Template literals for string interpolation in fetch URLs

**Formatting (Python):**
- 4-space indentation (PEP 8 standard)
- Single quotes for strings (consistently)
- f-strings for string formatting: `f"Error processing player {ign}: {e}"`
- Multi-line SQL uses triple-quoted strings with consistent indentation
- No linter/formatter config files (no `pyproject.toml`, `setup.cfg`, or `ruff.toml`)

## Import Organization

**TypeScript import order:**
1. `'use client'` directive (always first line in client components)
2. React hooks: `import { useState, useEffect, useRef } from 'react'`
3. Next.js imports: `import Link from 'next/link'`
4. Third-party icons: `import { Loader2, AlertCircle } from 'lucide-react'`
5. Radix UI primitives: `import * as Tabs from '@radix-ui/react-tabs'`
6. Local components via path alias: `import { AppHeader } from '@/components/app-header'`
7. Local utilities: `import { API_BASE } from '@/lib/api'`

**Path Aliases:**
- `@/*` maps to project root (configured in `tsconfig.json` and `next.config.js`)
- Used consistently: `@/components/...`, `@/lib/...`

**Python import order:**
1. Standard library: `import os`, `import json`, `import logging`
2. Third-party: `from flask import Flask, request, jsonify`
3. `sys.path.insert(0, ...)` hack for parent directory imports (used in `backend/api.py` and root scripts)
4. Local modules: `from backend.database import Database`, `from config import Config`

## Error Handling

**TypeScript patterns:**
- try/catch around fetch calls with error state: `setError(json.error ?? 'Unknown error')`
- Supplemental/non-critical fetches wrapped in separate try/catch that silently continues
- Null coalescing for display: `value ?? '---'`
- Pattern in `app/team/page.tsx` lines 56-103: primary fetch sets error, supplemental fetches are non-critical

**Python patterns:**
- Flask global error handlers catch all unhandled exceptions and return JSON (never HTML):
  ```python
  @app.errorhandler(Exception)
  def _handle_exception(e):
      logger.error(f"Unhandled exception: {e}", exc_info=True)
      return _json_error_response(str(e) or type(e).__name__)
  ```
- Per-endpoint try/except returning `jsonify({'error': str(e)}), 500`
- Database methods use try/finally for connection cleanup: `conn.close()` in `finally` block
- NaN/Infinity sanitization: custom `_SafeJSONProvider` in `backend/api.py` replaces with `null`

## Logging

**Python:**
- Framework: Python `logging` module
- Setup: `logging.basicConfig(level=logging.INFO)` in `backend/api.py`
- Logger per module: `logger = logging.getLogger(__name__)`
- Request logging via Flask middleware: `@app.before_request` / `@app.after_request`
- Also uses `print()` for request logging alongside `logger.info()`
- Log levels used: `logger.info()`, `logger.error()`, `logger.debug()` (debug in scrapers)

**TypeScript:**
- No logging framework; uses `console.log` implicitly (no explicit logging calls observed in components)
- Errors displayed to user via React state (`setError(...)`)

## Comments

**TypeScript:**
- Section dividers using Unicode box-drawing: `/* --- Types ---- */`, `/* --- Constants --- */`, `/* --- Small helpers --- */`
- Inline comments for non-obvious logic
- JSDoc-style comment on `lib/api.ts` explaining purpose
- No TSDoc on component props (interfaces are self-documenting)

**Python:**
- Module-level docstrings explaining purpose (every backend module has one)
- Function docstrings with Args/Returns sections in `backend/model_params.py`
- Inline comments for SQL migrations and business logic
- Section dividers: `# ==================== Challengers (Tier 2) API ====================`
- TODO/FIXME comments present in scraper code

## Function Design

**React components:**
- Large monolithic components: `matchup-page.tsx` is 1623 lines with many sub-components defined in the same file
- Sub-components are file-private functions (not exported): `SectionLabel`, `Card`, `TeamBadge`, `StatRow`
- Props defined via interfaces directly above the component
- State managed with `useState` hooks; no external state management (no Redux, Zustand, etc.)
- Data fetching done in page-level components via `fetch()` in event handlers, not `useEffect`

**Python classes:**
- `Database` class: single monolithic class (2604 lines) with all DB operations
- Methods open/close their own connections (no connection pooling or context managers)
- `Config` class: static configuration, no instantiation needed
- Scraper classes: one per data source, initialized with database reference

## Module Design

**Exports (TypeScript):**
- Named exports only (no default exports except page components)
- Page components: `export default function PageName()`
- Shared components: `export function ComponentName()`
- Interfaces exported alongside their primary component
- Type re-export barrel file: `lib/types/matchupAnalytics.ts`

**Exports (Python):**
- No `__all__` definitions
- Classes and functions imported directly by name
- `__init__.py` files exist but are empty

## Inline Styling

**Dominant pattern: inline `style` objects over Tailwind for precise values:**
- Colors specified as raw hex/rgba: `style={{ color: '#F0E040' }}`
- Layout properties mixed between `className` (Tailwind) and `style` (inline)
- Tailwind used for: spacing, flexbox, responsive breakpoints, transitions
- Inline styles used for: colors, borders, backgrounds, font sizes, letter spacing
- No CSS modules or styled-components
- Global CSS in `app/globals.css` defines design tokens as CSS custom properties

## TypeScript Configuration

**Strict mode: OFF** (`"strict": false` in `tsconfig.json`)
- `skipLibCheck: true`
- `noEmit: true` (Next.js handles compilation)
- Module resolution: `"node"` (not `"bundler"`)
- Target: ES2017

---

*Convention analysis: 2026-03-07*
