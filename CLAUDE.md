# CLAUDE.md — Thunderedge

Valorant esports betting analytics platform. Python backend + Next.js 14 frontend. Four parallel development tracks, each in its own git worktree off a feature branch.

---

## Repo Layout

```
C:\Users\josep\OneDrive\Desktop\Thunderedge\
  thunderedge/          ← main repo (branch: main)
  worktrees/
    kill-line-ml/       ← branch: feature/kill-line-ml
    eco-round-strategy/ ← branch: feature/eco-round-strategy
    half-win-rate/      ← branch: feature/half-win-rate
    market-maker/       ← branch: feature/market-maker
```

Scripts in feature worktrees must be run from the **Thunderedge/ parent**, not from thunderedge/:
```bash
python worktrees/half-win-rate/scraper/halves_scraper.py --limit 500
```

---

## Active Development Tracks

| Track | Branch | Entry Point | Status |
|---|---|---|---|
| Kill-line predictor | feature/kill-line-ml | `calculator.py` | Active |
| Eco-round Kalshi bot | feature/eco-round-strategy | `live_score_poller.py` | Active |
| Half-win-rate model | feature/half-win-rate | `half_win_rate_model.py` | Active |
| Market maker | feature/market-maker | `run_market_maker.py` | Active |

---

## Backend Files (thunderedge/backend/)

| File | Purpose |
|---|---|
| `api.py` | Flask API endpoints |
| `calculator.py` | Kill-line pipeline orchestrator |
| `database.py` | SQLite ORM + all table schemas |
| `model_params.py` | Poisson/NB params + `ml_adjust()` XGBoost blend |
| `prop_prob.py` | CDF → P(Over)/P(Under) |
| `matchup_adjust.py` | Matchup multiplier on kill mean |
| `market_implied.py` | Reverse-engineer μ from market odds |
| `odds_utils.py` | American/decimal/vig conversions |
| `theo_engine.py` | *(feature/market-maker)* Markov map-win theo |
| `market_maker.py` | *(feature/market-maker)* Quoting engine |

---

## Database — `data/valorant_stats.db` (SQLite, WAL mode)

### Tables

**`vct_events`** — id, event_url, event_name, region, year, status, tier (1=VCT, 2=Challengers)

**`matches`** — id, match_url UNIQUE, event_id, team1, team2, match_date, maps_played

**`player_map_stats`** — id, match_id, player_name, map_number, map_name, agent, kills, deaths, assists, acs, adr, kast, first_bloods, map_score
- UNIQUE(match_id, player_name, map_number)
- **21,740 rows** — all VCT 2025 + partial 2026

**`player_event_stats`** — id, event_id, player_name, team, kpr, rounds_played, rating, acs, adr, kills, deaths (1,498 rows)

**`match_map_halves`** — id, match_id, map_number, map_name, team_name, atk_rounds_won, def_rounds_won, total_rounds
- **324 rows**, Americas 2025 only so far
- Core table for half-win-rate model

**`match_round_data`** — id, match_id, map_number, round_num, winning_team_side, team1_economy, team2_economy
- **712 rows** — used by eco-round backtest

**`match_pick_bans`** — id, match_id, first_ban, second_ban, first_pick, second_pick, decider (856 rows)

**`moneyline_matches`** — match_url, event_name, team1, team2, team1_odds, team2_odds, winner, team1_maps, team2_maps (**currently empty**)

**`player_data_cache`** — player_name PK, ign, team, match_combinations (JSON), last_updated
- **71 rows** — 2026 Kickoff kill data from rib.gg
- JSON format: `[{match_url, event_name, map_kills, map_scores, num_maps}]`

**`leaderboard_snapshots` / `leaderboard_entries`** — PrizePicks leaderboard with p_over, p_under, mu, sample_size

**`analysis_results`** — cached kill-line analysis per player

### Write behavior
All DB writes use `INSERT OR REPLACE`. `populate_database.py` has per-match checkpoint — skips matches already in `player_map_stats`.

---

## Data Coverage

- **VCT 2025**: All 12 events (4 regions × Kickoff/Stage1/Stage2) — fully scraped
- **VCT 2026 Kickoff**: Americas/EMEA/Pacific kill data in `player_data_cache`; match stats NOT in main tables yet
- **VCT 2026 Stage 1**: Ongoing — China/EMEA/Pacific live; Americas starts 2026-04-10
- **Maps**: Abyss, Ascent, Bind, Corrode (new 2026), Fracture, Haven, Icebox, Lotus, Pearl, Split, Sunset

---

## Key Run Commands

```bash
# Populate 2026 match data (choose option 3)
python scripts/populate_database.py

# Scrape atk/def half scores (run from Thunderedge/ parent)
python worktrees/half-win-rate/scraper/halves_scraper.py --limit 500

# Recompute half win rates (after halves_scraper)
python worktrees/half-win-rate/scripts/half_win_rate_model.py

# Train kill XGBoost model
python worktrees/kill-line-ml/scripts/train_kill_model.py

# Validate half-win-rate theo (Brier score)
python worktrees/half-win-rate/scripts/validate_theo.py

# Live eco-round signal detection
python worktrees/eco-round-strategy/scraper/live_score_poller.py --probe
python worktrees/eco-round-strategy/scraper/live_score_poller.py --match {slug}
python worktrees/eco-round-strategy/scraper/live_score_poller.py --test  # simulation

# Market maker (always dry-run first)
python worktrees/market-maker/run_market_maker.py --dry-run --verbose
```

---

## Domain Constants & Gotchas

### Economy thresholds (match_round_data)
| Label | Credits |
|---|---|
| full | ≥ 20,000 |
| semi-buy | 10,000–19,999 |
| semi-eco | 5,000–9,999 |
| eco | < 5,000 |

### Critical rules
- **No OT modeling**. Rounds > 24 are excluded everywhere — both teams reset to full buy each OT pair, no eco edge.
- `GUN_WIN_RATE = 0.822` — gun team wins 82.2% of eco rounds (empirical from backtest). Hardcoded constant, do not tune without re-running backtest.
- **Half-win-rate event weighting**: current event = 1.0, previous = 0.5, older = excluded. Auto-detected by latest match date per team.
- **Recency over history**: current event data always overrides older data in all models.

### Scraping behavior
- VLR.gg: 1–1.5s between requests, 30s backoff on HTTP 429
- Live match detection: `div.ml.mod-live`
- bo3.gg API: `GET api.bo3.gg/api/v1/matches/{slug}` — slug format `{t1}-vs-{t2}-{DD}-{MM}-{YYYY}`. **Filter params are broken; use slug endpoint only.**

### Kill-line pipeline
- Distribution blend: Poisson/Negative Binomial + XGBoost via `ml_adjust()` in `model_params.py`
- Serialized models: `models/kill_mean_xgb.pkl`, `models/kill_over_xgb.pkl`
- P(Over)/P(Under) computed via CDF in `prop_prob.py`

### Kalshi API
- **Auth**: RSA PKCS1v15/SHA-256. Key ID and private key path in `.env` (gitignored). **Never hardcode credentials.**
- `.env` vars: `KALSHI_KEY_ID`, `KALSHI_PRIVATE_KEY_PATH`
- Private key file: `valorant (1).txt` (gitignored)
- API version: v2

---

## Stack

- Python 3.11, Flask, SQLite (WAL mode)
- XGBoost (kill predictor)
- Next.js 14 (frontend — `app/` pages, `components/`)
- Kalshi REST API v2

---

## Preferences

- Terse responses, no trailing summaries
- Checkpoint systems over full re-scrapes
- Feature branches developed in parallel via git worktrees — don't merge feature work into main prematurely
- Regulation rounds only (1–24) in all models
