# Requirements: ThunderEdge

**Defined:** 2026-03-07
**Core Value:** Accurate kill line predictions that demonstrably beat naive statistical baselines

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### ML Data Pipeline

- [x] **DATA-01**: Feature extraction pipeline produces per-player-per-map feature vectors from existing SQLite data (KPR, ADR, map win%, agent role, opponent strength)
- [x] **DATA-02**: Temporal train/test splitting using event_id as chronological proxy (no data leakage)
- [x] **DATA-03**: Feature normalization and missing value handling for sparse player histories

### Player Embeddings

- [ ] **EMBED-01**: Player embedding model trained via PyTorch that maps player+map+context features into a low-dimensional vector space (4-8 dims)
- [ ] **EMBED-02**: k-NN similarity search (implemented from scratch, no sklearn) over player embeddings to find historically similar player-map matchups
- [ ] **EMBED-03**: Embedding vectors stored in SQLite and retrievable via API endpoint
- [ ] **EMBED-04**: Interactive 2D/3D scatter visualization of player embedding space using PCA/UMAP projection

### Kill Prediction

- [ ] **PRED-01**: Quantile regression model (implemented from scratch — pinball loss, no sklearn) predicting 10th/25th/50th/75th/90th percentile kill counts
- [ ] **PRED-02**: Model uses player embeddings + contextual features (map, opponent, recent form) as inputs
- [ ] **PRED-03**: Predictions served via Flask API alongside existing statistical model (dual prediction: ml + statistical fields)
- [ ] **PRED-04**: Graceful degradation — falls back to Poisson/NegBinom if ML model fails or lacks data for a player
- [ ] **PRED-05**: Feature importance display showing which inputs most influence each prediction

### Model Validation

- [ ] **VAL-01**: Backtesting results page showing ML model accuracy vs statistical baseline on held-out test data
- [ ] **VAL-02**: Calibration metrics displayed (predicted vs actual kill quantiles)

### Dark Theme & Design System

- [ ] **UI-01**: Dark color scheme applied globally via CSS variables — consistent across all pages
- [ ] **UI-02**: Design tokens defined (colors, spacing, typography, border radii) for cohesive aesthetic
- [ ] **UI-03**: Loading states and skeleton screens for all data-fetching views

### Navigation & Information Architecture

- [ ] **NAV-01**: Unified navigation structure connecting player analysis, team matchups, PrizePicks, and new ML features
- [ ] **NAV-02**: Clear page hierarchy — users can reach any feature within 2 clicks from homepage

### Data Display

- [ ] **TABLE-01**: Sortable, filterable data tables (TanStack Table + shadcn DataTable) replacing current static tables
- [ ] **TABLE-02**: Progressive disclosure — summary cards with key metrics first, expandable detail views underneath
- [ ] **TABLE-03**: KPI strip / at-a-glance metrics on key pages (player analysis, team matchup)

## v2 Requirements

Deferred to future work. Tracked but not in current roadmap.

### Advanced ML

- **ADV-01**: Ensemble predictions combining multiple model types
- **ADV-02**: Real-time model retraining as new match data is scraped
- **ADV-03**: Cross-modal retrieval (text descriptions to player embeddings)

### Advanced UI

- **ADV-04**: Animated transitions between views (Framer Motion)
- **ADV-05**: Mobile-optimized responsive layouts
- **ADV-06**: User-customizable dashboard layouts

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time odds streaming | Complexity + no API access; manual input sufficient |
| User accounts / auth | Public tool, no login needed |
| Production deployment | Local development is the target for now |
| Automated betting integration | Legal/ethical concerns, out of project scope |
| GPU inference | Model is far too small; CPU inference is sub-millisecond |
| Separate ML microservice | Overkill at this scale; in-process Flask inference is correct |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Complete |
| DATA-02 | Phase 1 | Complete |
| DATA-03 | Phase 1 | Complete |
| EMBED-01 | Phase 1 | Pending |
| EMBED-02 | Phase 2 | Pending |
| EMBED-03 | Phase 3 | Pending |
| EMBED-04 | Phase 5 | Pending |
| PRED-01 | Phase 2 | Pending |
| PRED-02 | Phase 2 | Pending |
| PRED-03 | Phase 3 | Pending |
| PRED-04 | Phase 3 | Pending |
| PRED-05 | Phase 3 | Pending |
| VAL-01 | Phase 5 | Pending |
| VAL-02 | Phase 5 | Pending |
| UI-01 | Phase 4 | Pending |
| UI-02 | Phase 4 | Pending |
| UI-03 | Phase 4 | Pending |
| NAV-01 | Phase 4 | Pending |
| NAV-02 | Phase 4 | Pending |
| TABLE-01 | Phase 5 | Pending |
| TABLE-02 | Phase 5 | Pending |
| TABLE-03 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 22 total
- Mapped to phases: 22
- Unmapped: 0

---
*Requirements defined: 2026-03-07*
*Last updated: 2026-03-07 after roadmap creation*
