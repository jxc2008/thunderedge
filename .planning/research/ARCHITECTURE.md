# Architecture Patterns

**Domain:** Esports analytics platform with ML kill prediction pipeline
**Researched:** 2026-03-07

## System Overview

The existing architecture is a straightforward Next.js frontend calling a Flask REST API backed by SQLite. The ML pipeline must integrate without disrupting the ~40 existing endpoints. The recommended approach: add ML as a **parallel analytics engine** alongside the existing scipy-based engine, with a shared Database layer and a model registry for trained artifacts.

```
                    Next.js (port 3000)
                         |
                    Flask API (port 5000)
                    /    |    \
            Existing   ML       Scrapers
            Analytics  Engine
            (scipy)    (PyTorch)
                \      /
              Database (SQLite)
                  |
            embeddings table (BLOB)
            model artifacts (filesystem)
```

### Why This Shape

1. **No separate ML service.** With ~540 match records and a local-only deployment, a microservice for ML inference is pure overhead. PyTorch loads into the same Flask process.
2. **Parallel engines, not replacement.** The existing Poisson/NegBinom engine works and ships today. The ML engine runs alongside it, and endpoints can return both predictions for comparison during development.
3. **SQLite stays.** Embeddings stored as BLOB columns in SQLite. At this data scale (~500 players, 32-64 dim vectors), SQLite handles k-NN brute-force search in <10ms. No vector database needed.

## Component Boundaries

| Component | Location | Responsibility | Depends On |
|-----------|----------|----------------|------------|
| **ML Training Pipeline** | `backend/ml/train.py` | Offline training: builds embeddings, fits quantile regression | `backend/database.py`, PyTorch |
| **Embedding Model** | `backend/ml/embeddings.py` | Player/map embedding definitions, forward pass | PyTorch |
| **Quantile Regression** | `backend/ml/quantile_regression.py` | From-scratch quantile regression (no sklearn) | numpy only (course requirement) |
| **k-NN Retrieval** | `backend/ml/knn.py` | From-scratch k-NN over embedding space (no sklearn) | numpy only (course requirement) |
| **Model Registry** | `backend/ml/registry.py` | Load/save model checkpoints, versioning | filesystem (`models/`) |
| **ML Inference** | `backend/ml/inference.py` | Prediction API: takes player+context, returns kill distribution | All ML modules |
| **Existing Analytics** | `backend/model_params.py` et al. | Poisson/NegBinom fitting (unchanged) | scipy, numpy |
| **Flask API** | `backend/api.py` | Routes, orchestrates both engines | All backend modules |
| **Database** | `backend/database.py` | SQLite access, now includes embedding storage | sqlite3 |
| **Frontend** | `app/`, `components/` | UI pages, redesigned component library | Flask API |

## Recommended Directory Structure

```
backend/
  ml/
    __init__.py
    embeddings.py       # Player + map embedding module (PyTorch nn.Module)
    quantile_regression.py  # From-scratch quantile loss + linear model
    knn.py              # From-scratch k-NN with cosine/euclidean distance
    inference.py        # Unified prediction interface
    registry.py         # Model save/load, version tracking
    train.py            # Training script (run offline)
    features.py         # Feature extraction from DB → tensors
  model_params.py       # Existing (unchanged)
  matchup_adjust.py     # Existing (unchanged)
  ...

models/                 # Git-ignored directory for trained artifacts
  player_embeddings/
    v1/
      model.pt          # PyTorch state dict
      config.json       # Hyperparams, training metadata
  quantile_regression/
    v1/
      weights.npz       # numpy arrays (from-scratch, no torch)
      config.json

scripts/
  train_embeddings.py   # CLI entry: trains embedding model
  train_quantile.py     # CLI entry: trains quantile regression
  evaluate_models.py    # Compare ML vs baseline predictions
```

## Data Flow

### Training Path (Offline)

```
1. scripts/train_embeddings.py
   |
2. backend/ml/features.py
   - Queries player_map_stats from SQLite
   - Builds feature matrix: kills, deaths, assists, KPR, map_name, team, opponent
   - Encodes categoricals (map, agent) as integer indices
   |
3. backend/ml/embeddings.py
   - PyTorch nn.Embedding layers for player_id, map_id
   - Concatenated with numerical features
   - Trained to predict kill counts (MSE loss)
   - Learned embeddings capture player skill + map affinity
   |
4. backend/ml/quantile_regression.py
   - Takes embedding vectors + features as input
   - Pinball loss at quantiles [0.10, 0.25, 0.50, 0.75, 0.90]
   - Implemented from scratch: forward pass, gradient computation, training loop
   - Outputs: kill count at each quantile (confidence intervals)
   |
5. Save artifacts
   - model.pt → models/player_embeddings/v{N}/
   - weights.npz → models/quantile_regression/v{N}/
   - Embeddings written to SQLite: player_embeddings table (player_name, vector BLOB, updated_at)
```

### Inference Path (Live, in Flask process)

```
1. GET /api/player/{ign}?line=16.5
   |
2. Flask route (backend/api.py)
   - Existing flow: calls PlayerProcessor + model_params.py → Poisson/NegBinom result
   - NEW: also calls backend/ml/inference.py
   |
3. backend/ml/inference.py
   - Loads model from registry (cached in memory after first call)
   - Looks up player embedding from SQLite or computes on-the-fly
   - Runs quantile regression forward pass
   - Returns: {median_kills, q10, q25, q75, q90, over_prob, under_prob}
   |
4. Flask merges both predictions into response:
   {
     "statistical": { ... existing Poisson/NegBinom ... },
     "ml": { "median": 17.2, "q10": 12, "q90": 23, "over_prob": 0.58, ... },
     "recommended": "ml"  // or "statistical" based on confidence
   }
```

### Embedding Retrieval Path (k-NN)

```
1. GET /api/player/{ign}/similar?k=5
   |
2. Flask route
   |
3. backend/ml/knn.py
   - Loads all player embeddings from SQLite (small enough to fit in memory)
   - Computes cosine similarity to target player's embedding
   - Returns top-k similar players
   - FROM SCRATCH: no sklearn, just numpy dot products + argsort
   |
4. Response: [{player: "aspas", similarity: 0.94, role: "duelist"}, ...]
```

## Embedding Storage in SQLite

Use a dedicated table with BLOB columns. At 500 players x 64 dimensions x 4 bytes = 128KB total -- trivial for SQLite.

```sql
CREATE TABLE IF NOT EXISTS player_embeddings (
    player_name TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,        -- numpy float32 array as bytes
    embedding_dim INTEGER NOT NULL,  -- 32 or 64
    model_version TEXT NOT NULL,     -- "v1", "v2"
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS map_embeddings (
    map_name TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,
    embedding_dim INTEGER NOT NULL,
    model_version TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Write pattern** (in train.py):
```python
embedding_bytes = embedding_vector.numpy().astype(np.float32).tobytes()
db.execute("INSERT OR REPLACE INTO player_embeddings VALUES (?, ?, ?, ?, ?)",
           (player_name, embedding_bytes, dim, version, datetime.now()))
```

**Read pattern** (in inference.py / knn.py):
```python
row = db.execute("SELECT embedding, embedding_dim FROM player_embeddings WHERE player_name=?", (name,))
vector = np.frombuffer(row[0], dtype=np.float32)
```

## Model Loading Strategy

Load models lazily on first inference request, then cache in module-level globals. This avoids slowing Flask startup when ML models are not yet trained.

```python
# backend/ml/registry.py
_model_cache = {}

def get_model(model_type: str, version: str = "latest"):
    cache_key = f"{model_type}:{version}"
    if cache_key not in _model_cache:
        model_path = _resolve_path(model_type, version)
        if model_type == "embeddings":
            model = EmbeddingModel.load(model_path)
            model.eval()  # Set to inference mode
        elif model_type == "quantile":
            model = QuantileRegressor.load(model_path)
        _model_cache[cache_key] = model
    return _model_cache[cache_key]
```

## Integration with Existing Endpoints

### Strategy: Augment, Don't Replace

Existing endpoints return the same data they always have. ML predictions are added as an additional field. This means:

- No breaking changes to the frontend during development
- Frontend can progressively adopt ML predictions
- A/B comparison between statistical and ML predictions is built-in

### Endpoint Changes

| Endpoint | Current | With ML |
|----------|---------|---------|
| `GET /api/player/{ign}` | Returns Poisson/NegBinom params | Adds `ml_prediction` field with quantile estimates |
| `GET /api/matchup/player-kills` | Per-player kill distributions | Adds ML-based distributions alongside |
| `GET /api/matchup/mispricing` | Compares projected kills to lines | Uses ML median + quantiles for sharper edge detection |
| `GET /api/player/{ign}/similar` | **NEW** | k-NN similar players from embedding space |
| `GET /api/embeddings/visualization` | **NEW** | PCA/t-SNE reduced embeddings for scatter plot |
| `GET /api/models/status` | **NEW** | Which models are trained, versions, last training date |

### Graceful Degradation

If no ML model is trained yet, endpoints return `"ml_prediction": null` and the frontend shows only statistical predictions. This is critical for incremental development.

```python
# In api.py route handler
try:
    ml_pred = ml_inference.predict_kills(player_name, context)
except (FileNotFoundError, ModelNotTrainedError):
    ml_pred = None

response = {
    "statistical": statistical_result,
    "ml": ml_pred
}
```

## Frontend Architecture for Redesign

### Current Problems
- `matchup-page.tsx` is 1600+ lines (monolith component)
- No shared design system beyond raw shadcn/ui primitives
- No state management -- each page is isolated
- Pages duplicate fetching logic

### Recommended Component Architecture

```
app/
  _components/              # Shared layout components
    nav-sidebar.tsx         # Persistent navigation
    page-shell.tsx          # Common page wrapper (header, padding, loading states)
    theme-provider.tsx      # Dark theme context

  (dashboard)/              # Route group for main views
    layout.tsx              # Dashboard layout with sidebar
    page.tsx                # Home/overview
    player/
      [ign]/
        page.tsx            # Player detail page
    team/
      page.tsx              # Team matchup page
    prizepicks/
      page.tsx

components/
  ui/                       # Base design system (extended shadcn/ui)
    card.tsx
    data-table.tsx
    stat-block.tsx          # Reusable stat display (value + label + trend)
    confidence-bar.tsx      # Visual confidence indicator
    distribution-chart.tsx  # Kill distribution visualization
    embedding-scatter.tsx   # 2D embedding space visualization

  matchup/                  # Matchup page broken into sub-components
    matchup-overview.tsx
    matchup-map-scores.tsx
    matchup-pick-ban.tsx
    matchup-player-kills.tsx
    matchup-mispricing.tsx
    matchup-parlay.tsx

  player/                   # Player analysis sub-components
    player-stats.tsx
    player-similar.tsx      # k-NN similar players card
    player-prediction.tsx   # ML vs statistical prediction comparison

  shared/
    prediction-comparison.tsx  # Side-by-side ML vs statistical
    quantile-display.tsx       # Shows Q10-Q90 confidence band
```

### State Management

Add a lightweight data fetching layer rather than a full state management library:

- **SWR or React Query** for data fetching with caching and revalidation
- Keep page-level state in `useState` for form inputs
- No global store needed -- pages are independent views

Use **SWR** because it is lighter weight, already common in Next.js projects, and the app has simple fetching patterns (no mutations, no optimistic updates).

## Patterns to Follow

### Pattern 1: Dual Prediction Response
**What:** Every kill prediction endpoint returns both statistical and ML results.
**When:** Any endpoint that currently returns kill estimates.
**Why:** Enables A/B comparison, graceful degradation, incremental adoption.

### Pattern 2: Offline Training, Online Inference
**What:** Training runs as a CLI script, not through the API. Inference loads cached models.
**When:** Always. Never train models during a request.
**Why:** Training on 500+ records with PyTorch takes seconds to minutes. Request timeouts are 30s. Keep them separate.

### Pattern 3: Embedding Storage as BLOB
**What:** Store embeddings as numpy float32 bytes in SQLite BLOB columns.
**When:** After training completes, and during k-NN retrieval.
**Why:** At this data scale, SQLite BLOB is simpler and faster than any vector database. The entire embedding table fits in memory.

### Pattern 4: From-Scratch Module Isolation
**What:** Quantile regression and k-NN implementations live in standalone files with zero sklearn/torch dependencies (numpy only).
**When:** Course requirement -- these two algorithms must be explainable and library-free.
**Why:** Clean separation makes it obvious to the grader what is from scratch vs library-assisted.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Separate ML Microservice
**What:** Running PyTorch inference in a separate process/container.
**Why bad:** Doubles deployment complexity for zero benefit at this scale. Inter-process communication adds latency. Local-only app does not need service isolation.
**Instead:** Load PyTorch model in the Flask process. Lazy-load on first inference call.

### Anti-Pattern 2: Training via API Endpoint
**What:** `POST /api/train` that kicks off model training.
**Why bad:** Training can take minutes, far exceeding request timeouts. Ties up the Flask worker. Hard to report progress.
**Instead:** Training is a CLI script (`scripts/train_embeddings.py`). The API only serves inference.

### Anti-Pattern 3: Replacing Statistical Engine Immediately
**What:** Deleting the Poisson/NegBinom code and using only ML predictions.
**Why bad:** ML model may underperform on small data. Loses the working baseline. No way to compare.
**Instead:** Run both in parallel. Let the frontend show both. Decide later which to emphasize.

### Anti-Pattern 4: Vector Database for 500 Embeddings
**What:** Adding Pinecone, Chroma, or Faiss for k-NN search.
**Why bad:** Massive dependency for a brute-force search that takes <1ms in numpy. Also violates the from-scratch course requirement for k-NN.
**Instead:** Store in SQLite, load into numpy array, compute distances with `np.dot`.

## Build Order (Dependencies)

This ordering is critical -- each step depends on the ones before it.

```
Phase 1: ML Foundation
  1. backend/ml/features.py        -- Feature extraction (needs DB, no ML yet)
  2. backend/ml/embeddings.py      -- Embedding model definition (PyTorch)
  3. scripts/train_embeddings.py   -- Training script
  4. Embedding storage in SQLite   -- Schema + read/write helpers

Phase 2: From-Scratch Algorithms
  5. backend/ml/quantile_regression.py  -- Needs embeddings as input
  6. backend/ml/knn.py                  -- Needs stored embeddings
  7. scripts/train_quantile.py          -- Training script

Phase 3: Inference Integration
  8. backend/ml/registry.py        -- Model loading/caching
  9. backend/ml/inference.py        -- Unified prediction interface
  10. API endpoint changes          -- Augment existing routes

Phase 4: Frontend (can partially overlap with Phase 2-3)
  11. Design system + theme         -- Before any page work
  12. Component decomposition       -- Break matchup-page.tsx into pieces
  13. ML-specific UI components     -- Embedding scatter, quantile display
  14. Integration                   -- Wire new components to augmented API
```

**Key dependency:** Steps 5-6 cannot start until step 4 is done (embeddings must exist before quantile regression or k-NN can use them). Steps 8-10 cannot start until at least one model is trained. Frontend redesign (11-12) can start in parallel with ML work (1-7).

## Scalability Considerations

| Concern | Current (500 players) | At 5K players | At 50K players |
|---------|----------------------|---------------|----------------|
| Embedding storage | ~128KB in SQLite | ~1.3MB, still trivial | ~13MB, consider sqlite-vec extension |
| k-NN search | <1ms brute force | ~5ms brute force | Consider approximate NN (but likely still fine) |
| Model loading | <100ms | Same (model size doesn't scale with data) | Same |
| Training time | ~10 seconds | ~1 minute | ~10 minutes, consider batching |
| SQLite concurrency | Fine (WAL mode) | Fine | Might need connection pooling |

At current and foreseeable scale, none of these are concerns. SQLite + in-process PyTorch handles everything.

## Sources

- [PyTorch Flask Deployment Tutorial (official)](https://docs.pytorch.org/tutorials/intermediate/flask_rest_api_tutorial.html) -- Confidence: HIGH
- [tinyvector: SQLite + PyTorch embedding DB](https://github.com/0hq/tinyvector) -- Validates SQLite BLOB approach for small-scale embeddings
- [Building a Vector Database on SQLite, Numpy and KNNs](https://www.linkedin.com/pulse/building-vector-database-sqlite-numpy-knns-david-okpare) -- Pattern reference for BLOB storage + brute-force k-NN
- [sqlite-vec extension](https://github.com/sqliteai/sqlite-vector) -- Future option if scale demands it (not needed now)

---

*Architecture analysis: 2026-03-07*
