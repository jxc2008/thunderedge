# Phase 1: Data Pipeline & Embeddings - Context

**Gathered:** 2026-03-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a feature extraction pipeline from the existing SQLite database and train a PyTorch player embedding model. The pipeline must use temporal splitting (event_id as chronological proxy) to prevent data leakage. Output: trained embedding model that maps player+map+context into a low-dimensional vector space.

</domain>

<decisions>
## Implementation Decisions

### Feature Composition
- Use ALL available stats from player_map_stats: kills, deaths, assists, ACS, ADR, KAST, first_bloods
- Include contextual features: map_name (categorical), agent (categorical/role-grouped)
- Include opponent team strength as a feature — derive from match/team data (e.g., opponent win rate or ELO-like rating)
- Apply recency weighting — recent matches count more than older ones (exponential decay or rolling window)

### Training Objective
- Primary task: predict kills — embeddings are a byproduct of learning to predict kill counts
- The embedding layer's activations become the player vectors used downstream for k-NN and visualization
- Demo story: show BOTH the end-to-end prediction pipeline AND embedding space exploration equally

### Validation Criteria
- Both qualitative sanity checks AND quantitative metrics required:
  - Sanity: duelists should cluster together, similar KPR players should be near each other in embedding space, embedding distances should correlate with stat similarity
  - Quantitative: held-out validation loss must converge, no gross divergence between train/test loss

### Claude's Discretion
- Embedding granularity: whether embeddings are per-player, per-player+map, or hybrid
- Embedding dimensionality: 4-8 dims, pick based on validation metrics
- Agent role encoding: part of embedding vs separate categorical input
- Model architecture complexity: simple MLP (2-3 layers) recommended given 540 matches, but Claude decides
- Feature aggregation strategy: rolling averages vs individual match samples vs hybrid
- Whether to produce a quick PCA scatter plot for manual validation
- Whether to compute statistical baseline (Poisson/NegBinom) in this phase or defer to Phase 5
- Embedding update strategy: full retrain vs incremental when new data arrives

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/model_params.py`: `extract_kill_samples()` already queries player_map_stats with map/event filters — can be extended for feature extraction
- `backend/database.py`: `get_player_map_kills_with_scores_for_event()` returns kills + map scores per player — useful for building feature vectors
- `backend/database.py`: `get_team_overview()`, `get_team_map_records()` provide opponent strength data
- `backend/matchup_adjust.py`: Existing matchup adjustment constants (alpha, beta, gamma) calibrated from real data

### Established Patterns
- Database access via `Database` class singleton, instantiated with `Config.DATABASE_PATH`
- All queries use parameter binding, WAL journal mode for concurrency
- Python snake_case throughout backend, type hints from `typing` module
- Scripts for data population live in `scripts/` directory (e.g., `populate_database.py`)

### Integration Points
- `player_map_stats` table: primary data source (kills, deaths, assists, acs, adr, kast, first_bloods, map_name, agent, match_id)
- `matches` table: links to event_id (chronological proxy since match_date is NULL), team1/team2 names
- `match_map_halves` table: 540 rows of halftime round splits (atk/def data)
- `match_pick_bans` table: 1150 rows for map context
- Trained model and embeddings should be storable/loadable from a path relative to project root (e.g., `models/` or `data/`)

</code_context>

<specifics>
## Specific Ideas

- Training objective "predict kills" was chosen because it creates embeddings that encode kill-relevant information — directly useful for the downstream quantile regression in Phase 2
- Course demo should tell a story: raw data -> features -> embeddings -> predictions, with a detour into "here's how the embedding space looks"
- The from-scratch algorithms (Phase 2) consume these embeddings, so the vector quality directly affects the course grade

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-data-pipeline-embeddings*
*Context gathered: 2026-03-08*
