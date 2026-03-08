# Phase 1: Data Pipeline & Embeddings - Research

**Researched:** 2026-03-08
**Domain:** PyTorch embedding model, feature engineering from SQLite, temporal data splitting
**Confidence:** HIGH

## Summary

This phase builds a feature extraction pipeline from the existing SQLite database (61,736 player_map_stats rows, 45,456 with complete data) and trains a PyTorch embedding model to map player+map+context into 4-8 dimensional vectors. The training objective is kill prediction -- embeddings are a learned byproduct.

The data is well-structured for this task. The `player_map_stats` table contains all needed features (kills, deaths, assists, ACS, ADR, KAST, first_bloods, map_name, agent). Event IDs serve as a reliable chronological proxy since `match_date` is NULL. Key challenges: 16,280 rows have NULL map_name/agent/acs/adr/kast (from early scrapes without match_id linkage to events), 604 players have fewer than 5 map records, and team names in the `matches` table are polluted with event suffixes.

**Primary recommendation:** Use only the 45,456 complete rows (those with non-NULL map_name). Split by event_id threshold for train/test. Build a simple MLP (2-3 hidden layers) with entity embedding layers for player_name, map_name, and agent_role. Target: kills. Embedding dimension: start at 8, validate down to 4 if overfitting.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Use ALL available stats from player_map_stats: kills, deaths, assists, ACS, ADR, KAST, first_bloods
- Include contextual features: map_name (categorical), agent (categorical/role-grouped)
- Include opponent team strength as a feature -- derive from match/team data
- Apply recency weighting -- recent matches count more than older ones
- Primary task: predict kills -- embeddings are a byproduct
- Embedding layer activations become the player vectors for downstream k-NN and visualization
- Demo must show BOTH end-to-end prediction pipeline AND embedding space exploration
- Both qualitative sanity checks AND quantitative metrics required for validation

### Claude's Discretion
- Embedding granularity: whether embeddings are per-player, per-player+map, or hybrid
- Embedding dimensionality: 4-8 dims, pick based on validation metrics
- Agent role encoding: part of embedding vs separate categorical input
- Model architecture complexity: simple MLP (2-3 layers) recommended given 540 matches
- Feature aggregation strategy: rolling averages vs individual match samples vs hybrid
- Whether to produce a quick PCA scatter plot for manual validation
- Whether to compute statistical baseline (Poisson/NegBinom) in this phase or defer to Phase 5
- Embedding update strategy: full retrain vs incremental when new data arrives

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DATA-01 | Feature extraction pipeline produces per-player-per-map feature vectors from existing SQLite data (KPR, ADR, map win%, agent role, opponent strength) | 45,456 complete rows available; all stats present in player_map_stats; opponent strength derivable via team win rates from matches table; agent role mapping covers all 29 agents |
| DATA-02 | Temporal train/test splitting using event_id as chronological proxy (no data leakage) | 35 events with IDs 73-114; events are chronologically ordered; 2026 events start at ID 110; recommend split at event_id ~105 |
| DATA-03 | Feature normalization and missing value handling for sparse player histories | 604 players have <5 maps; 16,280 rows have NULL extended stats (filter these out); for sparse players, use global mean imputation for rolling stats |
| EMBED-01 | Player embedding model trained via PyTorch that maps player+map+context features into a low-dimensional vector space (4-8 dims) | PyTorch needs clean install (DLL issue on current system); MLP with entity embeddings is the right architecture for this data scale |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyTorch | 2.5.x (CPU) | Embedding model training | Locked decision; standard for entity embeddings |
| numpy | 1.26.2 | Feature vector computation | Already installed |
| scipy | 1.11.4 | Statistical utilities | Already installed |
| sqlite3 | stdlib | Data access | Already used throughout project |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.2 | Testing | Already installed; use for validation tests |
| matplotlib | any | PCA scatter plot | Optional -- only if producing embedding visualization |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyTorch | TensorFlow | PyTorch is locked decision; simpler for small models |
| Raw SQL queries | pandas | pandas adds dependency; raw SQL + numpy is lighter and matches existing patterns |

**Installation:**
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install matplotlib  # optional, for PCA visualization
```

Note: PyTorch CPU-only is ~200MB vs ~2GB for CUDA. GPU is explicitly out of scope per REQUIREMENTS.md.

## Architecture Patterns

### Recommended Project Structure
```
backend/
  ml/
    __init__.py
    features.py        # Feature extraction pipeline (DATA-01, DATA-03)
    dataset.py         # PyTorch Dataset + temporal splitting (DATA-02)
    embedding_model.py # Model definition (EMBED-01)
    train.py           # Training loop + validation
models/
    player_embeddings.pt  # Saved model weights
    training_meta.json    # Training metadata (split info, loss curves)
scripts/
    train_embeddings.py   # CLI entry point for training
tests/
    test_features.py      # Feature pipeline tests
    test_dataset.py       # Dataset + split tests
    test_model.py         # Model training tests
```

### Pattern 1: Entity Embedding MLP
**What:** Categorical variables (player_name, map_name, agent_role) get learned embedding layers; continuous features (KPR, ADR, etc.) pass through directly. All concatenated and fed through MLP to predict kills.
**When to use:** When you have a mix of categorical and continuous features with a regression target.
**Example:**
```python
import torch
import torch.nn as nn

class PlayerEmbeddingModel(nn.Module):
    def __init__(self, n_players, n_maps, n_roles, n_continuous, embed_dim=8):
        super().__init__()
        self.player_embed = nn.Embedding(n_players, embed_dim)
        self.map_embed = nn.Embedding(n_maps, 4)
        self.role_embed = nn.Embedding(n_roles, 3)

        total_in = embed_dim + 4 + 3 + n_continuous
        self.mlp = nn.Sequential(
            nn.Linear(total_in, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(32, 1)  # predict kills
        )

    def forward(self, player_id, map_id, role_id, continuous_features):
        p = self.player_embed(player_id)
        m = self.map_embed(map_id)
        r = self.role_embed(role_id)
        x = torch.cat([p, m, r, continuous_features], dim=1)
        return self.mlp(x)

    def get_player_embedding(self, player_id):
        """Extract learned embedding vector for downstream use."""
        return self.player_embed(player_id).detach()
```

### Pattern 2: Temporal Train/Test Split
**What:** Split data by event_id threshold, not random sampling, to prevent data leakage.
**When to use:** Always for this project -- match_date is NULL, event_id is the chronological proxy.
**Example:**
```python
def temporal_split(event_ids, split_ratio=0.8):
    """Split by event_id chronologically."""
    sorted_events = sorted(set(event_ids))
    split_idx = int(len(sorted_events) * split_ratio)
    train_events = set(sorted_events[:split_idx])
    test_events = set(sorted_events[split_idx:])
    return train_events, test_events
```

### Pattern 3: Feature Extraction with Recency Weighting
**What:** For each training sample, compute rolling statistics (e.g., last-N-games KPR, ADR) using only data from prior events.
**When to use:** Locked decision -- recency weighting required.
**Example:**
```python
def compute_rolling_features(player_name, current_event_id, all_player_data, window=10):
    """Compute rolling stats using only data from events BEFORE current_event_id."""
    prior = [row for row in all_player_data
             if row['event_id'] < current_event_id]
    prior.sort(key=lambda x: x['event_id'], reverse=True)
    recent = prior[:window]
    if not recent:
        return None  # handled as sparse player
    return {
        'avg_kills': np.mean([r['kills'] for r in recent]),
        'avg_deaths': np.mean([r['deaths'] for r in recent]),
        # ... etc
    }
```

### Anti-Patterns to Avoid
- **Using future data in features:** Computing rolling stats that include the current match or future matches. The feature extraction must be strictly causal -- only use data from events with lower event_id.
- **Embedding dimension too large:** With ~2,246 players but only ~45K rows, embedding dims above 8 risk overfitting. Start at 8, reduce if validation loss diverges.
- **Dropping sparse players entirely:** 604 players have <5 maps. These should get valid embeddings (via learned embedding + imputed features), not be dropped.
- **Using 16K NULL rows:** Rows where map_name/agent/acs/adr/kast are NULL lack the features needed. Filter these out at extraction time.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Gradient descent | Custom optimizer | `torch.optim.Adam` | Numerically tested, handles learning rate scheduling |
| Embedding lookup | Manual weight matrix indexing | `nn.Embedding` | Handles padding_idx, sparse gradients, initialization |
| Data batching | Custom batch iteration | `torch.utils.data.DataLoader` | Handles shuffling, parallel loading, pin_memory |
| Feature normalization | Manual z-score | Compute mean/std from training set, apply as transform | Must use TRAINING set stats only (leak prevention) |

**Key insight:** PyTorch's DataLoader + Dataset pattern handles the entire training loop boilerplate. The only custom code needed is the model architecture, feature extraction SQL, and the temporal split logic.

## Common Pitfalls

### Pitfall 1: Data Leakage Through Normalization
**What goes wrong:** Computing feature mean/std on the entire dataset (including test set), then normalizing.
**Why it happens:** Easy to accidentally include test data when computing statistics.
**How to avoid:** Compute normalization stats ONLY from training set rows. Store these stats alongside the model for inference-time normalization.
**Warning signs:** Suspiciously good test performance. Test loss lower than training loss.

### Pitfall 2: Team Name Pollution in Opponent Strength
**What goes wrong:** Team names in `matches.team1/team2` include event suffixes (e.g., "Nrg Vct 2025 Americas Stage 2 Lbf"). Comparing these raw strings fails to match anything.
**Why it happens:** Scraper bug stores event context in team name field.
**How to avoid:** Use `Database._clean_team_name()` on all team names from matches table before any comparison. Cross-reference with `players.team` for canonical names.
**Warning signs:** Opponent strength features all returning 0 or NaN.

### Pitfall 3: Player Name Case Sensitivity
**What goes wrong:** Player names have inconsistent casing across tables.
**Why it happens:** Different scraper runs use different capitalization.
**How to avoid:** Always use `LOWER()` in SQL comparisons. Use lowercase keys in player-to-index mappings.
**Warning signs:** Same player appearing twice in embedding space with different vectors.

### Pitfall 4: Map Score Direction Ambiguity
**What goes wrong:** The `map_score` field "13-8" means team1 got 13 rounds -- but for a player on team2, they lost. Without knowing which team the player is on, you cannot compute team win/loss or round differential.
**Why it happens:** `player_map_stats` does not directly store which team the player belongs to.
**How to avoid:** Join with `players.team` to determine the player's team, then compare with `matches.team1/team2` (after cleaning) to determine if the player's team is team1 or team2, then parse map_score accordingly.
**Warning signs:** Win rate features showing ~50% for all players regardless of team strength.

### Pitfall 5: PyTorch DLL Load Failure on Windows
**What goes wrong:** `ImportError: DLL load failed while importing _C` when importing torch.
**Why it happens:** PyTorch was installed for wrong Python version or missing Visual C++ redistributable.
**How to avoid:** Install CPU-only PyTorch via official index URL: `pip install torch --index-url https://download.pytorch.org/whl/cpu`. Ensure Python 3.12 compatibility.
**Warning signs:** Import error on `from torch._C import *`.

### Pitfall 6: Sparse Player Cold Start
**What goes wrong:** Players with 1-4 historical maps produce unreliable rolling features, but their embedding still needs to be learnable.
**Why it happens:** 604 out of 2,246 players have <5 map records.
**How to avoid:** For rolling features, impute with global means when fewer than N prior records exist. The embedding layer itself handles cold start naturally -- it initializes randomly and learns from whatever data exists. Flag samples from sparse players with a "sparse" indicator feature.
**Warning signs:** NaN in feature vectors causing NaN loss during training.

## Code Examples

### Querying Feature Data from SQLite
```python
# Reuse existing Database class pattern
import sqlite3
from config import Config

def extract_all_player_map_features(db_path: str) -> list[dict]:
    """Extract all complete player-map records with event context."""
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pms.player_name, pms.map_name, pms.agent,
               pms.kills, pms.deaths, pms.assists,
               pms.acs, pms.adr, pms.kast, pms.first_bloods,
               pms.map_score, pms.match_id, pms.map_number,
               m.event_id, m.team1, m.team2,
               p.team as player_team
        FROM player_map_stats pms
        JOIN matches m ON pms.match_id = m.id
        LEFT JOIN players p ON LOWER(pms.player_name) = LOWER(p.ign)
        WHERE pms.map_name IS NOT NULL
          AND pms.kills IS NOT NULL
        ORDER BY m.event_id ASC
    ''')
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows
```

### Agent Role Mapping
```python
AGENT_ROLES = {
    'Jett': 'duelist', 'Raze': 'duelist', 'Reyna': 'duelist',
    'Phoenix': 'duelist', 'Yoru': 'duelist', 'Neon': 'duelist',
    'Iso': 'duelist', 'Waylay': 'duelist',
    'Sova': 'initiator', 'Breach': 'initiator', 'Skye': 'initiator',
    'Kayo': 'initiator', 'Fade': 'initiator', 'Gekko': 'initiator',
    'Tejo': 'initiator',
    'Brimstone': 'controller', 'Omen': 'controller', 'Astra': 'controller',
    'Viper': 'controller', 'Harbor': 'controller', 'Clove': 'controller',
    'Sage': 'sentinel', 'Cypher': 'sentinel', 'Killjoy': 'sentinel',
    'Chamber': 'sentinel', 'Deadlock': 'sentinel', 'Vyse': 'sentinel',
    'Veto': 'sentinel',
}
# All 29 agents in DB are covered. 'Unknown' maps to a special index.
```

### Opponent Strength Feature
```python
import re

def clean_team_name(raw: str) -> str:
    """Strip event-name pollution. Mirrors Database._clean_team_name()."""
    if not raw:
        return raw
    m = re.search(r'\s+(?:20\d{2}|vct\b|champions?\s+tour\b|challengers?\b)',
                  raw, flags=re.IGNORECASE)
    return raw[:m.start()].strip() if m else raw.strip()

def compute_opponent_win_rate(player_team: str, team1: str, team2: str,
                              team_records: dict) -> float:
    """Derive opponent strength from team win records."""
    t1_clean = clean_team_name(team1)
    t2_clean = clean_team_name(team2)

    # Determine opponent
    if player_team and t1_clean.lower() in player_team.lower():
        opponent = t2_clean
    elif player_team and t2_clean.lower() in player_team.lower():
        opponent = t1_clean
    else:
        return 0.5  # fallback: unknown opponent strength

    record = team_records.get(opponent.lower(), None)
    if record and record['total'] > 0:
        return record['wins'] / record['total']
    return 0.5  # unknown team defaults to average
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| One-hot encoding for categoricals | Entity embeddings (nn.Embedding) | ~2016 (Guo & Berkhahn) | Learns relationships between categories; essential for high-cardinality features like player_name |
| Random train/test split | Temporal split | Standard in time-series ML | Prevents data leakage from future information |
| Fixed feature vectors | Learned embeddings | Standard in modern ML | Captures latent player characteristics beyond raw stats |

**Deprecated/outdated:**
- Using sklearn's LabelEncoder + one-hot for categorical features with >100 categories is outdated for neural networks. Entity embeddings are strictly better.
- PyTorch < 2.0: `torch.compile()` available in 2.0+ but unnecessary for this tiny model.

## Data Profile

Key statistics for planning:

| Metric | Value |
|--------|-------|
| Total player_map_stats rows | 61,736 |
| Usable rows (non-NULL map_name) | 45,456 |
| 2026 rows (all complete) | 3,430 |
| Distinct players | 2,246 |
| Players with <5 maps | 604 (27%) |
| Players with 50+ maps | 360 (16%) |
| Distinct maps | 12 (excluding 'TBD') |
| Distinct agents | 29 (including 'Unknown') |
| Agent roles | 4 (duelist, initiator, controller, sentinel) |
| Events | 35 (IDs 73-114) |
| Avg kills per map | 14.5 |
| Kill range | 0-42 |

## Open Questions

1. **Player-team mapping completeness**
   - What we know: `players.team` has 138 rows with canonical team names; `player_map_stats` has 2,246 distinct players
   - What's unclear: Many players in player_map_stats may not have entries in the players table (especially Challengers players)
   - Recommendation: Use LEFT JOIN; when player_team is NULL, set opponent_strength to 0.5 (average). This is acceptable -- the model learns from the embedding that this player's opponent data is unknown.

2. **Optimal train/test split point**
   - What we know: Events 73-114, with 2026 starting at 110. Most data (1,577 matches) is 2025.
   - What's unclear: Exact right split ratio for this dataset
   - Recommendation: Use ~80/20 split by event count. Split around event_id ~105 puts Challengers Stage 3 + all 2026 in test. Alternatively, put just 2026 events (110-114) as test -- gives a "predict the future" validation which is the actual use case.

3. **Feature aggregation strategy (Claude's discretion)**
   - Option A: Individual match samples -- each row in player_map_stats is one training sample. Rolling stats computed from prior events are additional features.
   - Option B: Aggregated features per player+map -- average stats across recent matches, one feature vector per player+map combo.
   - Recommendation: Option A (individual samples). It gives 45K training samples instead of ~5K aggregated ones, and the model can learn from match-level variance. Rolling stats serve as "prior form" features alongside the individual sample.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none -- see Wave 0 |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | Feature extraction produces per-player-per-map vectors | unit | `python -m pytest tests/test_features.py -x` | No -- Wave 0 |
| DATA-02 | Temporal split uses event_id, no future data in training set | unit | `python -m pytest tests/test_dataset.py::test_temporal_split -x` | No -- Wave 0 |
| DATA-03 | Sparse players get valid feature vectors (no NaN, no drops) | unit | `python -m pytest tests/test_features.py::test_sparse_players -x` | No -- Wave 0 |
| EMBED-01 | Trained model produces 4-8 dim vectors for any player+map | integration | `python -m pytest tests/test_model.py::test_embedding_output -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/__init__.py` -- empty init for test package
- [ ] `tests/test_features.py` -- covers DATA-01, DATA-03
- [ ] `tests/test_dataset.py` -- covers DATA-02
- [ ] `tests/test_model.py` -- covers EMBED-01
- [ ] `tests/conftest.py` -- shared fixtures (test DB path, sample data)
- [ ] `pytest.ini` or `pyproject.toml` [tool.pytest] section -- configure test discovery
- [ ] Framework install: PyTorch CPU -- `pip install torch --index-url https://download.pytorch.org/whl/cpu`

## Sources

### Primary (HIGH confidence)
- Direct SQLite database inspection -- schema, row counts, NULL distribution, data ranges
- Existing codebase inspection -- `backend/model_params.py`, `backend/database.py`, `config.py`
- Project CONTEXT.md, REQUIREMENTS.md, STATE.md -- locked decisions and constraints

### Secondary (MEDIUM confidence)
- PyTorch entity embedding patterns -- well-established technique (Guo & Berkhahn 2016, widely adopted)
- Agent role categorization -- verified all 29 DB agents map to 4 roles with no gaps

### Tertiary (LOW confidence)
- PyTorch 2.5.x CPU wheel compatibility with Python 3.12 on Windows -- the existing torch install has DLL issues; needs clean reinstall

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- PyTorch is locked, numpy/scipy already installed, data schema fully inspected
- Architecture: HIGH -- Entity embedding MLP is the established approach for this data profile; data scale well-understood
- Pitfalls: HIGH -- Identified from direct database inspection (NULL rows, team name pollution, case sensitivity confirmed in data)
- Data profile: HIGH -- All statistics computed directly from the database

**Research date:** 2026-03-08
**Valid until:** 2026-04-08 (stable -- no fast-moving dependencies)
