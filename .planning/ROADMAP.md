# Roadmap: ThunderEdge ML + UI Redesign

## Overview

ThunderEdge adds an ML prediction engine (player embeddings + quantile regression + k-NN) alongside the existing Poisson/NegBinom statistical engine, then redesigns the UI to surface ML results in a dark, data-dense aesthetic. ML work comes first (course rubric weight), followed by UI foundation, then ML-specific UI and validation displays. The two from-scratch algorithms (quantile regression, k-NN) are isolated in Phase 2 for grading clarity.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Data Pipeline & Embeddings** - Feature extraction, temporal splitting, and player embedding model training (completed 2026-03-08)
- [ ] **Phase 2: From-Scratch Algorithms** - Quantile regression (pinball loss) and k-NN similarity search, numpy-only
- [ ] **Phase 3: Inference Integration** - Wire trained models into Flask API with dual predictions and graceful degradation
- [ ] **Phase 4: UI Foundation & Navigation** - Dark design system, loading states, and unified navigation across all pages
- [ ] **Phase 5: ML Feature UI & Validation** - Embedding visualization, backtesting display, and data-dense tables with progressive disclosure

## Phase Details

### Phase 1: Data Pipeline & Embeddings
**Goal**: A trained player embedding model that maps player+map+context into a low-dimensional vector space, built on a leak-free data pipeline
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03, EMBED-01
**Success Criteria** (what must be TRUE):
  1. Running the feature extraction pipeline produces per-player-per-map feature vectors from SQLite data without manual intervention
  2. Train/test split uses event_id chronologically -- no future data leaks into training set
  3. Players with sparse histories get valid feature vectors (missing values handled, not dropped)
  4. A trained PyTorch embedding model exists that produces 4-8 dimensional vectors for any player+map combination
  5. Training loss converges and validation loss does not diverge (no gross overfitting)
**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md -- Feature extraction pipeline and temporal dataset (DATA-01, DATA-02, DATA-03)
- [ ] 01-02-PLAN.md -- Embedding model training and CLI (EMBED-01)

### Phase 2: From-Scratch Algorithms
**Goal**: Two from-scratch algorithm implementations (no sklearn) that consume embeddings to produce kill quantiles and similar-player lookups
**Depends on**: Phase 1
**Requirements**: EMBED-02, PRED-01, PRED-02
**Success Criteria** (what must be TRUE):
  1. Quantile regression predicts 10th/25th/50th/75th/90th percentile kill counts for a given player+map+opponent
  2. Quantile regression uses pinball loss implemented in numpy only -- no sklearn or library regression calls
  3. k-NN retrieves the most similar player-map matchups from the embedding space using cosine similarity in numpy only
  4. k-NN results make intuitive sense (similar roles on similar maps cluster together)
**Plans**: TBD

Plans:
- [ ] 02-01: TBD
- [ ] 02-02: TBD
- [ ] 02-03: TBD

### Phase 3: Inference Integration
**Goal**: ML predictions served alongside existing statistical predictions through the Flask API, with automatic fallback when ML data is unavailable
**Depends on**: Phase 2
**Requirements**: EMBED-03, PRED-03, PRED-04, PRED-05
**Success Criteria** (what must be TRUE):
  1. API endpoints return both `statistical` and `ml` prediction fields for kill projections
  2. Embedding vectors are stored in SQLite and retrievable via a dedicated API endpoint
  3. If no trained model exists or a player has insufficient data, API returns `ml: null` and statistical predictions still work
  4. Each ML prediction includes a feature importance breakdown showing top factors influencing the result
  5. ML inference completes in under 100ms per player (no user-perceptible lag)
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD
- [ ] 03-03: TBD

### Phase 4: UI Foundation & Navigation
**Goal**: A cohesive dark design system applied globally with unified navigation that connects all existing and new features
**Depends on**: Nothing (can parallel Phases 2-3, but must complete before Phase 5)
**Requirements**: UI-01, UI-02, UI-03, NAV-01, NAV-02
**Success Criteria** (what must be TRUE):
  1. All pages render with a dark color scheme -- no white/light pages remain
  2. Design tokens (colors, spacing, typography, radii) are defined as CSS variables and used consistently
  3. Every data-fetching view shows a skeleton/loading state while waiting for API responses
  4. A single navigation structure connects player analysis, team matchups, PrizePicks, and ML features
  5. Any feature is reachable within 2 clicks from the homepage
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD
- [ ] 04-03: TBD

### Phase 5: ML Feature UI & Validation
**Goal**: ML results displayed through interactive visualizations, data-dense tables, and a backtesting page that proves ML beats the statistical baseline
**Depends on**: Phase 3, Phase 4
**Requirements**: EMBED-04, VAL-01, VAL-02, TABLE-01, TABLE-02, TABLE-03
**Success Criteria** (what must be TRUE):
  1. An interactive 2D/3D scatter plot shows the player embedding space with hoverable player labels
  2. A backtesting page displays ML model accuracy vs Poisson/NegBinom baseline on held-out test data
  3. Calibration metrics show predicted vs actual kill quantiles (do predicted 25th percentiles actually occur ~25% of the time?)
  4. Data tables are sortable and filterable (not static HTML tables)
  5. Key pages show summary KPI cards first, with expandable detail views underneath (progressive disclosure)
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD
- [ ] 05-03: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5
Note: Phase 4 (UI) can begin in parallel with Phases 2-3 (ML) since it has no backend dependencies.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Pipeline & Embeddings | 2/2 | Complete   | 2026-03-08 |
| 2. From-Scratch Algorithms | 0/3 | Not started | - |
| 3. Inference Integration | 0/3 | Not started | - |
| 4. UI Foundation & Navigation | 0/3 | Not started | - |
| 5. ML Feature UI & Validation | 0/3 | Not started | - |
