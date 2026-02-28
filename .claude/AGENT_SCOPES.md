# Agent Scope Definitions

Each agent owns specific files. Never touch files outside your scope unless the ticket explicitly says so.

---

## frontend

**Owns:**
- `app/**` — all Next.js pages (App Router)
- `components/**` — all React components
- `lib/**` — frontend utilities (api.ts, etc.)
- `public/**` — static assets
- `styles/**` — global CSS
- `next.config.js`, `tailwind.config.*`, `postcss.config.*`

**Must not touch:**
- `backend/` (any Python file)
- `scraper/`
- `scripts/`
- `data/`
- `config.py`

**Validation command (must pass before done):**
```
bash scripts/validate_frontend.sh
```

---

## backend

**Owns:**
- `backend/api.py` — Flask routes
- `backend/model_params.py` — distribution fitting
- `backend/prop_prob.py` — probability calculations
- `backend/matchup_adjust.py` — matchup adjustment
- `backend/odds_utils.py` — odds math
- `backend/market_implied.py` — market inference
- `backend/calculator.py` — KPR/weighted averages

**Must not touch:**
- `backend/database.py` (owned by data agent)
- `app/`, `components/`, `lib/` (owned by frontend)
- `scraper/` (owned by data agent)

**Validation command (must pass before done):**
```
bash scripts/validate_backend.sh
```

---

## data

**Owns:**
- `backend/database.py` — all DB schema and query methods
- `scraper/**` — all scrapers and processors
- `scripts/**` — populate and calibration scripts
- `config.py` — configuration constants
- `data/` — SQLite DB file (never commit the .db file itself)

**Must not touch:**
- `backend/api.py` (owned by backend agent — except when data contract changes require it, coordinate first)
- `app/`, `components/`, `lib/` (owned by frontend)

**Validation command (must pass before done):**
```
bash scripts/validate_backend.sh
```

---

## Shared rules (all agents)

1. **One task at a time.** Never start a second ticket before the first is validated and reported done.
2. **If a test fails or you're uncertain, STOP.** Write a clear TODO comment and report the blocker — do not guess.
3. **No drive-by refactors.** Only change what the ticket explicitly asks for.
4. **No architecture changes** (changing DB schema columns, renaming API endpoints, changing response shapes) without explicit instruction.
5. **Always run your validation script before reporting done.**
6. **Commits must be self-contained.** One logical change per commit.
