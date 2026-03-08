---
phase: 01-data-pipeline-embeddings
plan: 01
subsystem: ml
tags: [pytorch, sqlite, feature-engineering, temporal-split, embeddings]

requires:
  - phase: none
    provides: n/a
provides:
  - Feature extraction pipeline (backend/ml/features.py) producing per-player-per-map feature vectors
  - PyTorch Dataset with temporal train/test split (backend/ml/dataset.py)
  - Test infrastructure (pytest.ini, tests/conftest.py, test files)
affects: [01-02-embedding-model, 02-knn, 03-prediction-api]

tech-stack:
  added: [pytorch-2.10.0-cpu, pytest-9.0.2]
  patterns: [entity-embedding-dataset, temporal-split-by-event-id, rolling-causal-features, global-mean-imputation]

key-files:
  created: [backend/ml/__init__.py, backend/ml/features.py, backend/ml/dataset.py, tests/__init__.py, tests/conftest.py, tests/test_features.py, tests/test_dataset.py, pytest.ini]
  modified: []

key-decisions:
  - "PyTorch installed to C:/pylibs due to Windows long path limitation in default site-packages"
  - "Rolling window of 10 prior events for feature computation"
  - "Global mean imputation for sparse players (no NaN, no drops)"
  - "Index 0 reserved for unknown/unseen categoricals in all mappings"
  - "Normalization stats computed from training set only to prevent data leakage"

patterns-established:
  - "Temporal split: sort unique event_ids, split at 80% threshold"
  - "Causal rolling features: only use rows with event_id < current_event_id"
  - "Team name cleaning: regex strip at first year/VCT/Champions Tour keyword"
  - "Dataset returns dict with player_idx, map_idx, role_idx, continuous, target keys"

requirements-completed: [DATA-01, DATA-02, DATA-03]

duration: 8min
completed: 2026-03-08
---

# Phase 1 Plan 01: Feature Extraction & Dataset Summary

**SQLite feature extraction pipeline producing 41K+ player-map feature vectors with causal rolling stats, temporal train/test split, and PyTorch Dataset wrapper**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-08T07:46:11Z
- **Completed:** 2026-03-08T07:54:23Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments
- Feature extraction pipeline extracts 41,246 usable rows from SQLite with all required features
- Rolling features are strictly causal (only prior event data used), with global mean imputation for sparse players
- Temporal split produces 33,898 train / 7,348 test samples with zero overlap
- 15 tests all passing covering extraction, causality, NaN safety, normalization, and split correctness

## Task Commits

Each task was committed atomically:

1. **Task 0: Test scaffold and PyTorch install** - `a5a6da7` (test)
2. **Task 1: Feature extraction pipeline** - `d955bff` (feat)
3. **Task 2: PyTorch Dataset and temporal split** - `4f8ff4d` (feat)

## Files Created/Modified
- `backend/ml/__init__.py` - ML package init
- `backend/ml/features.py` - Feature extraction pipeline with rolling stats, opponent strength, agent roles
- `backend/ml/dataset.py` - PyTorch Dataset, temporal split, categorical encoding, normalization
- `tests/__init__.py` - Test package init
- `tests/conftest.py` - Shared fixtures (db_path, sample_raw_rows)
- `tests/test_features.py` - 7 tests for feature extraction pipeline
- `tests/test_dataset.py` - 8 tests for dataset and temporal split
- `pytest.ini` - Test discovery configuration

## Decisions Made
- PyTorch installed to C:/pylibs due to Windows long path limitation -- .pth file added to site-packages for auto-discovery
- Used session-scoped db_path fixture to avoid repeated database connections across test classes
- 80/20 temporal split puts events 101-114 in test (includes all 2026 data), events 73-100 in train
- Continuous features: 8 dimensions (7 rolling stats + opponent_win_rate)
- Agent roles include 'unknown' as 5th category for unmapped agents

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] PyTorch Windows long path installation failure**
- **Found during:** Task 0
- **Issue:** `pip install torch` failed with OSError due to Windows long path limitation in default site-packages directory
- **Fix:** Installed to C:/pylibs (shorter path) and added .pth file for auto-discovery
- **Files modified:** External (C:/pylibs/, site-packages/pylibs.pth)
- **Verification:** `python -c "import torch; print(torch.__version__)"` prints 2.10.0+cpu
- **Committed in:** N/A (external to repo)

**2. [Rule 1 - Bug] Fixed pytest fixture scope mismatch**
- **Found during:** Task 1
- **Issue:** class-scoped `feature_matrix` fixture depended on function-scoped `db_path` fixture, causing ScopeMismatch error
- **Fix:** Changed `db_path` to session scope in conftest.py
- **Files modified:** tests/conftest.py
- **Verification:** All tests pass
- **Committed in:** d955bff (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes necessary for test execution. No scope creep.

## Issues Encountered
- Total usable rows: 41,246 (slightly less than the estimated 45,456 due to additional NULL kills filtering)
- Roles count shows 6 (includes 'unknown' role) rather than expected 4, which is correct behavior for unmapped agents

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Feature pipeline and Dataset ready for embedding model training (Plan 02)
- Metadata dict provides all mappings needed for model initialization (n_players, n_maps, n_roles, n_continuous)
- Normalization stats stored for inference-time use

---
*Phase: 01-data-pipeline-embeddings*
*Completed: 2026-03-08*
