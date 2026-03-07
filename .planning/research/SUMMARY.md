# Project Research Summary

**Project:** ThunderEdge - Valorant Esports Analytics
**Domain:** Esports betting analytics with ML pipeline + UI/UX redesign
**Researched:** 2026-03-07
**Confidence:** HIGH

## Executive Summary

ThunderEdge is a brownfield Valorant esports analytics platform that already has a working prediction engine (Poisson/NegBinom), ~40 Flask API endpoints, and a functional Next.js frontend. The project adds two things: (1) an ML pipeline with player/map embeddings and quantile regression for kill predictions, and (2) a dark, data-dense UI redesign. Both serve a dual purpose -- improving the product and satisfying a PyTorch course final project (CSCI-UA 473) that requires at least one from-scratch algorithm implementation.

The recommended approach is to build the ML pipeline first, then redesign the UI to display ML results. The ML engine runs alongside the existing statistical engine in the same Flask process -- no separate service, no GPU, no vector database. Embeddings are stored as BLOBs in SQLite. Quantile regression and k-NN are implemented from scratch (numpy only, no sklearn) in isolated modules that are easy to grade. The UI redesign applies a dark design system to existing components rather than rewriting them, with component extraction only where needed for ML feature integration.

The dominant risk is small-dataset overfitting (540 matches, ~80 unique players). Keep embedding dimensions at 4-8, use strict temporal train/test splits (by event_id since match_date is NULL), and validate that k-NN neighbors make intuitive sense. The secondary risk is UI scope creep consuming ML time -- the course rubric weights algorithm implementation (10%) and working demo (10%) heavily, so a polished UI with weak predictions scores poorly. Time-box UI work.

## Key Findings

### Recommended Stack

The existing stack (Next.js 15 / Flask 3 / SQLite) stays unchanged. New additions are minimal and targeted.

**Core technologies:**
- **PyTorch 2.6 (CPU-only)**: Model training and inference -- course requirement, good for custom loss functions. Load in Flask process, ~sub-ms inference.
- **Recharts + shadcn/ui charts (existing)**: All standard visualizations -- already installed and integrated. No replacement needed.
- **react-plotly.js (gl3d partial bundle)**: 3D embedding space scatter plot only -- lazy-loaded to manage ~1MB bundle size. The single use case that Recharts cannot handle.
- **TanStack Table v8**: Data-dense sortable/filterable tables -- shadcn DataTable wraps it natively. Already the standard pairing.
- **scikit-learn (PCA/UMAP only)**: Dimensionality reduction for visualization preprocessing on backend. k-NN and quantile regression must NOT use sklearn.

**What not to use:** TorchServe (overkill), FAISS/vector DBs (200 vectors -- brute force is <1ms), ONNX Runtime (negligible speedup on tiny model), AG Grid (commercial license), any ORM (existing raw queries work fine).

### Expected Features

**Must have (table stakes):**
- Kill predictions with confidence intervals (quantile regression at 10th/25th/50th/75th/90th)
- Model accuracy metrics and backtesting display (prove ML beats Poisson/NegBinom baseline)
- Similar player lookups via k-NN in embedding space (from-scratch, satisfies course requirement)
- Dark theme with consistent design system (Bloomberg/DraftKings aesthetic)
- Loading states and skeleton screens (ML endpoints will be slower than existing ones)
- Feature importance / explainability (top 3-5 factors per prediction -- builds trust)

**Should have (differentiators):**
- Player embedding space visualization (interactive 2D/3D scatter -- the "wow" demo feature)
- Map-conditional kill predictions (leverages existing map probability data)
- Mispricing confidence scoring (quantile width + edge magnitude)
- KPI strip / dashboard header (Bloomberg-style at-a-glance metrics)
- Progressive disclosure (summary > charts > raw tables drill-down)

**Defer (v2+):**
- Agent composition counterfactuals (requires more data than available)
- Parlay correlation matrix (advanced, not needed for demo)
- Command palette, keyboard shortcuts (nice-to-have polish)
- Sparkline mini-charts in tables (low priority polish)

### Architecture Approach

The ML engine runs as a parallel analytics engine alongside the existing scipy-based engine, sharing the Database layer. Training is offline via CLI scripts; inference is in-process in Flask with lazy model loading and caching. Endpoints return both statistical and ML predictions (`"statistical": {...}, "ml": {...}`) enabling graceful degradation (if no model trained, `"ml": null`) and A/B comparison during development.

**Major components:**
1. **ML Training Pipeline** (`backend/ml/train.py`, `features.py`, `embeddings.py`) -- offline training: feature extraction from SQLite, embedding model definition, training scripts
2. **From-Scratch Algorithms** (`backend/ml/quantile_regression.py`, `knn.py`) -- isolated numpy-only modules for quantile regression (pinball loss) and k-NN (cosine similarity), cleanly gradeable
3. **ML Inference** (`backend/ml/inference.py`, `registry.py`) -- unified prediction interface with lazy model loading, caching, and `torch.inference_mode()` for performance
4. **Frontend Design System** (`app/globals.css`, `components/ui/`) -- dark theme CSS variables, extended shadcn/ui components, component decomposition of matchup-page.tsx
5. **Embedding Storage** (SQLite `player_embeddings` table with BLOB columns) -- 128KB total at 500 players x 64 dims, trivial for SQLite

### Critical Pitfalls

1. **Temporal data leakage in train/test split** -- match_date is NULL; must split by event_id strictly. Random splits leak future information and produce fake accuracy. Validate by comparing walk-forward results to random-split results.
2. **Overfitting embeddings on 540 matches** -- standard embedding dims (32-64) are too large. Keep at 4-8 dimensions for players. Monitor train vs validation loss divergence and sanity-check k-NN neighbors.
3. **Quantile regression loss function bugs** -- pinball loss is easy to implement wrong. Use vectorized `max(tau * e, (tau-1) * e)`, avoid batch normalization, train quantiles jointly to prevent crossing, and run calibration checks post-training.
4. **Mixing market odds into training features** -- existing calibration showed moneyline odds have near-zero signal for kill counts. Exclude all odds from model inputs; use them only as evaluation targets for mispricing detection.
5. **UI redesign scope creep** -- course rubric weights algorithm implementation + working demo at 20%. If >50% of project time is spent on UI without a working ML pipeline, the project is in danger. Time-box UI, implement ML first.

## Implications for Roadmap

### Phase 1: Data Pipeline and ML Foundation
**Rationale:** Everything downstream depends on clean data splitting and feature extraction. Temporal leakage (the #1 pitfall) must be prevented at the foundation level.
**Delivers:** Feature extraction pipeline, temporal train/val/test splitting infrastructure, embedding model training, embedding storage in SQLite.
**Addresses:** Player/map embeddings (P0), temporal leakage prevention, data normalization.
**Avoids:** Temporal leakage (Pitfall 1), overfitting (Pitfall 2 -- embedding dim decision made here), odds contamination (Pitfall 4).

### Phase 2: From-Scratch Algorithms
**Rationale:** Course rubric requires from-scratch implementations. These depend on trained embeddings from Phase 1. Completing these early de-risks the most grade-critical deliverable.
**Delivers:** Quantile regression with pinball loss (numpy-only), k-NN similarity search (numpy-only), calibration validation, model evaluation vs Poisson/NegBinom baseline.
**Uses:** PyTorch embeddings as input features, numpy for from-scratch implementations.
**Implements:** Quantile regression module, k-NN retrieval module.
**Avoids:** Quantile loss bugs (Pitfall 3), un-normalized k-NN (Performance Trap 2).

### Phase 3: Inference Integration
**Rationale:** With trained models and from-scratch algorithms complete, wire them into the Flask API. This phase connects ML to the existing product without breaking existing endpoints.
**Delivers:** Augmented API endpoints returning dual predictions, model registry with lazy loading, graceful degradation when models are not trained, prediction caching.
**Uses:** Flask (existing), PyTorch inference_mode, model registry pattern.
**Implements:** ML inference layer, endpoint augmentation (statistical + ML side-by-side).
**Avoids:** PyTorch latency in Flask (Tech Debt 1), model-database coupling (Tech Debt 2), silent failure propagation (Tech Debt 3).

### Phase 4: UI Foundation and Dark Theme
**Rationale:** With ML API endpoints delivering data, the frontend needs a design system to display it. Design system must come before any page-level work to avoid inconsistency.
**Delivers:** Dark theme CSS variables, design tokens, extended shadcn/ui components (stat-block, confidence-bar, quantile-display), loading states/skeletons, KPI strip component.
**Addresses:** Dark theme (P0), design system (P0), loading states (P1), KPI strip (P1).
**Avoids:** Data density without hierarchy (UX Pitfall 1), scope creep (Pitfall 5 -- apply system to existing components, don't rewrite).

### Phase 5: ML Feature UI and Integration
**Rationale:** Now that both the ML API and the design system exist, build the ML-specific UI components and wire them to the augmented endpoints.
**Delivers:** Kill prediction confidence intervals display, similar player cards (k-NN), model accuracy/backtesting page, embedding space visualization (Plotly 3D scatter), enhanced mispricing with confidence scoring.
**Addresses:** Confidence intervals (P1), similar player lookup UI (P1), backtesting display (P1), embedding visualization (P2), mispricing confidence (P2).
**Avoids:** Confidence intervals that users cannot interpret (UX Pitfall 3 -- translate to betting language).

### Phase 6: Polish and Demo Prep
**Rationale:** Final pass for progressive disclosure, navigation overhaul, matchup page component extraction, and demo scripting. Only after all features are working.
**Delivers:** Navigation redesign, progressive disclosure (3-level drill-down), matchup-page.tsx decomposition (only extracting ML-related sections), demo walkthrough script.
**Addresses:** Navigation overhaul (P0), progressive disclosure (P2), map-conditional predictions UI (P2).
**Avoids:** Redesigning for new users while breaking existing workflow (UX Pitfall 2), monolithic refactoring scope creep.

### Phase Ordering Rationale

- **ML before UI** because the course rubric weights algorithm implementation and working demo at 20% combined. A pretty UI with broken predictions fails the project.
- **Embeddings before quantile regression and k-NN** because both from-scratch algorithms consume embeddings as input. This is a hard dependency.
- **Design system before page-level UI** because applying dark theme piecemeal creates visual inconsistency that requires rework.
- **Inference integration as a separate phase** (not merged with training) because it requires different patterns (caching, graceful degradation, batching) and different testing (latency, error handling).
- **Frontend design system can overlap with Phases 2-3** since it has no backend dependencies. The roadmapper should allow parallelism here.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1 (Data Pipeline):** Needs research into optimal embedding dimensions for small datasets. The 4-8 dim recommendation is a starting point but may need experimentation.
- **Phase 2 (From-Scratch Algorithms):** Quantile regression implementation has documented gotchas (optimizer choice, batch norm interaction, quantile crossing). Review referenced McCaffrey blog post and unit test the loss function before training.

Phases with standard patterns (skip research-phase):
- **Phase 3 (Inference Integration):** Flask + PyTorch serving is well-documented (official PyTorch tutorial). Lazy loading + inference_mode is a standard pattern.
- **Phase 4 (UI Foundation):** shadcn/ui dark theme + Tailwind CSS variables is a standard, well-documented approach. No research needed.
- **Phase 5 (ML Feature UI):** Recharts + Plotly are well-documented. The main question is UX (how to display quantiles), which is a design decision not a research question.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Existing stack stays. New additions (PyTorch, Plotly, TanStack Table) are well-established with official docs. CPU-only PyTorch is the clear choice at this scale. |
| Features | HIGH | Feature landscape is well-mapped. Table stakes vs differentiators are clear. Anti-features correctly identified. Course rubric constraints narrow the feature set. |
| Architecture | HIGH | In-process Flask + PyTorch is validated by official PyTorch tutorial. SQLite BLOB storage for embeddings is validated by tinyvector and community patterns. No exotic patterns needed. |
| Pitfalls | HIGH | Domain-specific pitfalls (temporal leakage, small-dataset overfitting, quantile loss bugs) are well-documented in ML/sports-betting literature. Phase-specific warnings are actionable. |

**Overall confidence:** HIGH

### Gaps to Address

- **Optimal embedding dimension:** Research recommends 4-8 but this needs empirical validation on the actual dataset. Run a hyperparameter sweep during Phase 1.
- **Quantile calibration baseline:** No existing benchmark for "good" calibration on Valorant kill counts. Must establish a baseline by checking Poisson/NegBinom calibration first, then comparing ML model against it.
- **matchup-page.tsx decomposition scope:** The 1600-line monolith needs partial extraction for ML features, but how much to extract is a judgment call. Risk of over-refactoring vs under-refactoring. Decide during Phase 6 planning.
- **SWR vs React Query:** Architecture recommends SWR for data fetching. This is a minor decision but should be validated against actual fetching patterns (particularly parallel requests on the matchup page).
- **Pre-existing build failure:** `npm run build` fails on `/challengers` and `/moneylines` prerender. This blocks deployment but not development. Should be tracked but not addressed in this roadmap unless deployment becomes a goal.

## Sources

### Primary (HIGH confidence)
- [PyTorch Flask REST API Tutorial](https://docs.pytorch.org/tutorials/intermediate/flask_rest_api_tutorial.html) -- model serving pattern
- [PyTorch Releases](https://github.com/pytorch/pytorch/releases) -- version 2.6.x confirmation
- [shadcn/ui Chart docs](https://ui.shadcn.com/docs/components/radix/chart) -- Recharts integration
- [shadcn/ui Data Table docs](https://ui.shadcn.com/docs/components/radix/data-table) -- TanStack Table integration
- [TanStack Table](https://tanstack.com/table/latest) -- v8.21.x headless table

### Secondary (MEDIUM confidence)
- [Quantile Regression with PyTorch (McCaffrey, Feb 2025)](https://jamesmccaffreyblog.com/2025/02/28/quantile-regression-using-a-pytorch-neural-network-with-a-quantile-loss-function/) -- pinball loss implementation patterns
- [NBA2Vec: Player embeddings](https://arxiv.org/pdf/2302.13386) -- embedding architecture for sports analytics
- [Information Leakage in Backtesting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3836631) -- temporal leakage prevention
- [Building a Vector Database on SQLite](https://www.linkedin.com/pulse/building-vector-database-sqlite-numpy-knns-david-okpare) -- BLOB storage + brute-force k-NN pattern
- [Bloomberg Terminal color accessibility](https://www.bloomberg.com/ux/2021/10/14/designing-the-terminal-for-color-accessibility/) -- dark theme design reference
- [UI Density](https://mattstromawn.com/writing/ui-density/) -- density vs. clutter design principles

### Tertiary (LOW confidence)
- [Valorant player prediction with Random Forest](https://ijrm.net/index.php/ijrm/article/view/39) -- limited applicability (different model type, different target variable)
- [Framer Motion](https://www.framer.com/motion/) -- optional animation library, low priority

---
*Research completed: 2026-03-07*
*Ready for roadmap: yes*
