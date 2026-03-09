---
status: testing
phase: 01-data-pipeline-embeddings
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md]
started: 2026-03-08T08:10:00Z
updated: 2026-03-08T08:10:00Z
---

## Current Test

number: 1
name: All Tests Pass
expected: |
  Run `python -m pytest tests/ -v` from the project root.
  All 22 tests should pass (7 in test_features.py, 8 in test_dataset.py, 7 in test_model.py).
  No errors, no warnings about missing dependencies.
awaiting: user response

## Tests

### 1. All Tests Pass
expected: Run `python -m pytest tests/ -v` from project root. All 22 tests pass across test_features.py, test_dataset.py, and test_model.py. No import errors or missing dependencies.
result: [pending]

### 2. Feature Extraction from Database
expected: Run `python -c "from backend.ml.features import extract_features; rows = extract_features('data/valorant_stats.db'); print(f'{len(rows)} rows, {len(rows[0])} columns')"`. Should print ~41,246 rows with the expected column count. No errors.
result: [pending]

### 3. Training CLI Runs End-to-End
expected: Run `python scripts/train_embeddings.py --epochs 5 --patience 3`. Training starts, prints epoch losses, completes without error. Creates model file in models/ directory.
result: [pending]

### 4. Model Artifacts Saved to Disk
expected: After training, `models/` directory contains a `.pt` file (model weights) and `training_meta.json` (metadata with n_players, n_maps, embedding dims, etc.).
result: [pending]

### 5. Model Loads for Inference
expected: Run `python -c "from backend.ml.train import load_model; model, meta = load_model('models/'); print(f'Loaded: {meta[\"n_players\"]} players, embedding dim {meta[\"player_emb_dim\"]}')"`. Model loads without error, metadata shows expected values (~1827 players, 8-dim embeddings).
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0

## Gaps

[none yet]
