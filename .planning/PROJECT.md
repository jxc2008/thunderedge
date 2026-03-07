# ThunderEdge

## What This Is

A Valorant esports analytics platform that helps bettors determine if player kill lines are over- or underpriced. It scrapes player and team data from rib.gg and vlr.gg, fits statistical models to predict kill distributions, and surfaces mispricing opportunities. The Next.js frontend displays player analysis, team matchups, PrizePicks projections, and a parlay builder backed by a Flask/SQLite API.

## Core Value

Accurate kill line predictions that demonstrably beat naive statistical baselines — the one thing that makes ThunderEdge worth using over gut feel or generic stat sites.

## Requirements

### Validated

- ✓ Player kill line analysis with over/under probabilities — existing
- ✓ Team matchup page with projected map scores, pick/ban, agent comps — existing
- ✓ PrizePicks integration with combo-map projections — existing
- ✓ Parlay builder with correlated leg handling — existing
- ✓ Map probability estimation from pick/ban tendencies — existing
- ✓ Mispricing alerts comparing projected kills to market lines — existing
- ✓ Attack/defense win rate breakdowns per map — existing
- ✓ Player data scraping from rib.gg and vlr.gg — existing
- ✓ Moneyline and challengers league data pages — existing

### Active

- [ ] ML-powered kill predictions replacing Poisson/NegBinom with embeddings + regression
- [ ] Quantile regression (from scratch) for kill count confidence intervals
- [ ] Player/map embedding space with k-NN retrieval (from scratch) for similar-player lookups
- [ ] Full UI/UX redesign — dark, data-dense aesthetic (Bloomberg/DraftKings style)
- [ ] Improved navigation and information architecture across all pages
- [ ] Progressive data disclosure — reduce clutter while keeping data density when needed
- [ ] Dimensionality reduction visualization of player embedding space

### Out of Scope

- Mobile app — web-first, responsive is sufficient
- Real-time odds streaming — current manual input is fine for now
- User accounts / auth — public tool, no login needed
- Deployment to production — local development is the target

## Context

- **Existing analytics engine**: Uses scipy/numpy for Poisson and Negative Binomial distribution fitting on historical kill counts. Matchup adjustment applies alpha/beta/gamma constants calibrated from betting odds (near-zero signal found) and results-based calibration (genuine signal at +4.1% NLL improvement).
- **Data**: SQLite database with player_map_stats, matches, match_pick_bans, match_map_halves tables. ~540 halftime records, 1150 pick/ban rows, all filtered to year=2026. match_date is NULL for all rows — event_id used as chronological proxy.
- **ML course context**: CSCI-UA 473 (NYU, Prof. Kyunghyun Cho, Spring 2026) covers embeddings, PCA, dimensionality reduction, clustering, classification, regression, quantile regression, cross-modal retrieval. Final project requires at least one algorithm implemented from scratch (no libraries). Course uses PyTorch. Project may be submitted as final project if team agrees.
- **Course rubric priorities**: Algorithm implementation (10%) — must be from scratch and explainable. Application quality (10%) — real dataset, clear UI/UX, technical ambition beyond lecture demos. Working demo (10%) — must run end-to-end.
- **Current UI state**: Functional but visually unpolished. Navigation is fragmented (separate pages for player analysis, team matchups, PrizePicks). Matchup page alone is 1600+ lines. Uses shadcn/ui (Radix) components with Tailwind but lacks cohesive design system.

## Constraints

- **Tech stack**: Must keep Next.js + Flask + SQLite architecture (too much existing code to rewrite)
- **ML framework**: PyTorch preferred (aligns with course requirements)
- **From-scratch requirement**: Quantile regression and k-NN must be implemented without sklearn/library calls
- **Data volume**: Limited to ~540 match records and ~1150 pick/ban rows for 2026 — ML models must handle small datasets gracefully
- **Build issue**: `npm run build` fails on `/challengers` and `/moneylines` prerender — pre-existing, use `tsc --noEmit` for validation

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Embeddings + quantile regression approach | Covers multiple course topics (Weeks 2-4, 6, 9), provides both similarity search and probabilistic predictions | — Pending |
| Dark, data-dense UI aesthetic | Matches target user (serious bettors), aligns with DraftKings/Bloomberg reference points | — Pending |
| PyTorch for ML components | Course requirement, good ecosystem for custom implementations | — Pending |
| Two from-scratch algorithms (quantile reg + k-NN) | Maximizes rubric score, both are explainable and directly useful | — Pending |

---
*Last updated: 2026-03-07 after initialization*
