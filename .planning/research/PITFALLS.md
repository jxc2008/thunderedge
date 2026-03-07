# Domain Pitfalls

**Domain:** Esports analytics platform with ML-powered kill predictions (small dataset, from-scratch algorithms, UI redesign)
**Researched:** 2026-03-07
**Confidence:** HIGH (domain-specific, verified against codebase state and published research)

---

## Critical Pitfalls

Mistakes that cause rewrites, invalidate results, or waste entire phases of work.

### Pitfall 1: Temporal Data Leakage in Train/Test Split

**What goes wrong:** The model sees future match data during training and reports excellent accuracy that evaporates on real predictions. With ~540 matches using `event_id` as a chronological proxy (since `match_date` is NULL), a naive random split will leak future information into training.

**Why it happens:** Random train/test splits are the default in tutorials and introductory ML code. Sports/esports data is inherently temporal -- a player's form, meta shifts, roster changes, and map pool updates all evolve over time. A random split lets the model "see" how a player performed in Week 12 when predicting Week 8.

**Consequences:** Model appears to have predictive power that does not exist. Kill line predictions look accurate in backtesting but fail on live matches. The entire value proposition of ThunderEdge collapses -- you cannot tell if the model is better than the existing Poisson/NegBinom baseline.

**Prevention:**
- Use strict temporal splitting: train on events 1..N, validate on N+1..M, test on M+1..end
- Implement walk-forward validation: train on expanding windows, always predict forward
- Since `match_date` is NULL, sort by `event_id` (already used as chronological proxy) and split by event_id thresholds
- All feature engineering must produce lagged variables only -- never include stats from the match being predicted

**Detection:** If the model's test accuracy is dramatically better than the Poisson/NegBinom baseline (>10% improvement), suspect leakage before celebrating. Compare walk-forward results to random-split results; large gaps indicate leakage.

**Phase mapping:** Must be addressed at the very start of the ML phase, before any model training begins. The data splitting infrastructure is foundational.

---

### Pitfall 2: Overfitting Embeddings on 540 Matches

**What goes wrong:** Player and map embeddings memorize the training set instead of learning generalizable representations. With ~540 matches and roughly 50-80 unique players per year, the embedding space becomes a lookup table rather than a learned similarity space.

**Why it happens:** Standard embedding dimensions (32, 64, 128) are designed for datasets with thousands to millions of samples. The rule of thumb is at least 5 training examples per dimension. With ~540 matches, even 32-dimensional embeddings push the boundaries. The curse of dimensionality means that in high-dimensional space, all points become roughly equidistant, making k-NN retrieval meaningless.

**Consequences:** k-NN similarity search returns arbitrary "similar" players because distances are not meaningful. Embedding visualization (PCA/t-SNE) shows random scatter instead of meaningful clusters. The model degrades rather than improves predictions compared to the current statistical approach.

**Prevention:**
- Keep embedding dimensions very low: 4-8 dimensions for players, 2-4 for maps. This is not a "nice to have" -- it is a hard constraint given the data volume.
- Use aggressive regularization: weight decay (L2), dropout on embedding layers, early stopping based on validation loss (not training loss)
- Consider tying/sharing embeddings where possible (e.g., map embeddings shared across attack/defense contexts)
- Monitor embedding norms during training -- exploding norms indicate memorization
- Validate that k-NN retrieval returns sensible results (e.g., entry fraggers are similar to other entry fraggers, not random)

**Detection:** Plot train vs. validation loss curves. If training loss drops steadily while validation loss plateaus or rises after a few epochs, the model is overfitting. Also check: do k-NN neighbors make intuitive sense? If "aspas" is most similar to a random tier-2 controller, something is wrong.

**Phase mapping:** Core ML implementation phase. Embedding dimension must be decided before training begins.

---

### Pitfall 3: Quantile Regression Loss Function Implementation Bugs

**What goes wrong:** The pinball (quantile) loss function is implemented incorrectly, producing confidence intervals that are either too narrow (overconfident) or too wide (useless). Subtle bugs in the loss function can produce models that appear to train successfully but output nonsensical quantiles.

**Why it happens:** The quantile loss function has a piecewise structure that is easy to get wrong. The naive approach uses if/else branching per sample, which is both slow and error-prone. The correct vectorized implementation computes `max(tau * residual, (tau - 1) * residual)` element-wise. Additionally:
- Boundary quantiles (tau near 0 or 1) create large regions of zero loss, causing optimizer instability
- Batch normalization can cause severe underfitting when combined with quantile loss
- Weight initialization + optimizer choice interactions can produce wildly different results (SGD may work where Adam fails, or vice versa)
- Quantile crossing: the 25th percentile prediction can exceed the 75th percentile prediction if quantiles are trained independently

**Consequences:** Kill line confidence intervals are miscalibrated. Users see "80% confidence" intervals that contain the actual result only 40% of the time (or 99% of the time). This directly undermines the betting value proposition.

**Prevention:**
- Implement the loss function as: `loss = torch.max(tau * (y - y_hat), (tau - 1) * (y - y_hat))` -- no branching
- Test the loss function in isolation with known inputs before integrating into the model
- Avoid batch normalization in quantile regression networks
- Start with SGD optimizer and default weight initialization before trying Adam
- Train quantiles jointly (single model with multiple quantile outputs) rather than independently to reduce quantile crossing
- Add a monotonicity penalty or post-hoc sorting to enforce quantile ordering
- Calibrate: after training, check that the 10th percentile prediction is exceeded ~90% of the time on held-out data

**Detection:** Calibration plot: bucket predictions by predicted quantile and check observed frequency. If the 25th percentile is exceeded 60% of the time, the model is miscalibrated. Also check: does quantile 0.75 > quantile 0.50 > quantile 0.25 for every prediction?

**Phase mapping:** Core ML implementation phase. The loss function should be unit-tested before any model training.

---

### Pitfall 4: Mixing Market Odds Into Training Features

**What goes wrong:** Using betting odds (moneyline, spreads) as input features for the kill prediction model creates a form of "spec leakage" -- the model learns to parrot the market's implied probabilities rather than discovering independent signal. The existing calibration already found that pre-match moneyline odds have "near-zero signal" for individual kill counts.

**Why it happens:** It is tempting to use all available data. Odds are quantitative and seem informative. But odds reflect the market's consensus on match outcome, not individual player kill distributions. Including them makes the model dependent on having odds at inference time and masks whether the model has learned anything genuinely new.

**Consequences:** The model cannot identify mispricings because it was trained on the very market it is trying to beat. Predictions collapse to market-implied expectations. The mispricing alerts become circular.

**Prevention:**
- Exclude all betting odds from training features. Use only player performance history, map stats, agent compositions, and team records.
- The existing matchup adjustment (alpha/beta/gamma) should remain a separate, post-prediction adjustment layer -- not an input to the neural network.
- If you want to use odds, use them only as evaluation targets (compare model output to market for mispricing detection) never as inputs.

**Detection:** Train the model with and without odds features. If removing odds causes a large accuracy drop, the model was relying on them rather than learning player-level signal.

**Phase mapping:** Feature engineering phase, before model training begins.

---

### Pitfall 5: UI Redesign Scope Creep That Delays ML Work

**What goes wrong:** The "full UI/UX redesign" expands to consume all available time, leaving insufficient runway for the ML implementation that carries most of the course rubric weight (algorithm implementation 10%, application quality 10%, working demo 10%).

**Why it happens:** UI work is visible and satisfying. Every component can always look "a little better." The current codebase has massive monolithic components (matchup-page.tsx at 1600+ lines) that invite refactoring. The Bloomberg/DraftKings aesthetic aspiration is inherently ambitious. Each UI section (Parlay Builder, Map Probability, Player Kill Projections, etc.) can absorb unlimited polish time.

**Consequences:** The ML pipeline is rushed or incomplete. The "from-scratch algorithm" requirement is not met convincingly. The demo shows a pretty UI with weak predictions, which scores poorly on the course rubric. The project fails its primary purpose.

**Prevention:**
- Time-box the UI redesign strictly. Set a hard deadline after which only bug fixes are allowed.
- Implement ML first, then redesign the UI to display ML results. This ensures the demo has substance.
- For the UI, focus on the design system (colors, typography, spacing, component library) first. Apply it to existing components rather than rewriting component structure.
- Resist the urge to refactor matchup-page.tsx into perfect components during the redesign phase -- extract only what is needed for the ML integration.

**Detection:** If more than 50% of elapsed project time has been spent on UI without a working ML pipeline, the project is in danger.

**Phase mapping:** This is a project-level risk. The roadmap must sequence ML implementation before or in parallel with UI work, never after.

---

## Technical Debt Patterns

Issues that do not cause immediate failure but accumulate into major problems.

### Pattern 1: PyTorch Inference Latency Inside Flask

**What goes wrong:** PyTorch model inference inside a Flask request handler is 5-10x slower than standalone execution. Each API call to `/api/matchup/player-kills` triggers a forward pass, and the accumulated latency makes the matchup page feel sluggish.

**Why it happens:** Flask's synchronous, single-threaded model means each request blocks while waiting for PyTorch inference. PyTorch also has per-call overhead for tensor creation, gradient context management, and CUDA synchronization (even on CPU). Without `torch.inference_mode()`, PyTorch tracks gradients unnecessarily during inference.

**Prevention:**
- Always wrap inference in `with torch.inference_mode():` (not `torch.no_grad()` -- `inference_mode` is faster)
- Pre-load the model at Flask app startup, not per-request. Store it as a module-level singleton.
- Batch inference: when the matchup endpoint needs predictions for 10 players, run one batched forward pass instead of 10 individual calls
- Cache predictions with a TTL (the existing `Config.CACHE_DURATION` of 6 hours is appropriate)
- Consider pre-computing predictions after each data scrape rather than computing on-demand

**Phase mapping:** ML integration phase, when connecting PyTorch models to Flask endpoints.

### Pattern 2: Model-Database Coupling

**What goes wrong:** The ML model code directly imports and calls `Database` methods, creating tight coupling between the model layer and the data access layer. When the schema changes or a query method signature evolves (both common in this codebase), the ML code breaks.

**Prevention:**
- Create a data preparation layer that transforms raw database results into model-ready tensors
- The model code should accept tensors/arrays, never database connections
- This separation also makes unit testing possible -- you can test the model with synthetic data without a database

**Phase mapping:** ML architecture phase, before implementation begins.

### Pattern 3: Silent Failure Propagation from Database to Model

**What goes wrong:** The existing codebase has 55+ `except Exception as e` blocks in `database.py` that return empty results silently. When the ML model receives empty arrays because a query silently failed, it either crashes with an obscure tensor shape error or produces garbage predictions without any indication of the root cause.

**Prevention:**
- For ML-critical queries, let exceptions propagate rather than catching them
- Validate input data shapes and ranges before feeding into the model
- Add assertions: `assert len(kill_samples) >= MIN_SAMPLES, f"Only {len(kill_samples)} samples for {player}"`

**Phase mapping:** Data pipeline phase, before model training.

---

## Performance Traps

### Trap 1: Training on Raw Kill Counts Without Normalization

**What goes wrong:** Raw kill counts (ranging from 0-40+) are used directly as targets without normalization. Combined with other features on different scales (win rates 0-1, rounds played 10-30, agent pick rates 0-100%), the model struggles to converge.

**Prevention:**
- Normalize kill counts by rounds played (kills per round) as the primary target, then convert back to total kills at prediction time
- Standardize all input features (zero mean, unit variance) using training set statistics only (compute mean/std on train, apply to val/test)
- Store normalization parameters alongside the model for inference

### Trap 2: k-NN on Un-normalized Embedding Space

**What goes wrong:** When implementing k-NN from scratch for similar-player retrieval, features with large ranges dominate the distance calculation. A player's total kill count (0-400+ per event) drowns out their agent diversity score (0-5). k-NN returns players with similar total kills regardless of playstyle.

**Prevention:**
- Normalize all features before distance computation (Min-Max or Z-score)
- Use cosine similarity instead of Euclidean distance for the embedding space -- it is scale-invariant and more meaningful for learned embeddings
- Validate results qualitatively: do the "similar players" make intuitive sense to someone who follows VCT?

### Trap 3: Recomputing Embeddings on Every Request

**What goes wrong:** If embeddings are generated by a forward pass through the network on each API call, the matchup page (which fetches 10+ players) triggers 10+ forward passes per load.

**Prevention:**
- Pre-compute and cache all player embeddings in the database or a pickle file after each training run
- k-NN lookup should be a pure distance computation on cached vectors, not a model forward pass
- Recompute embeddings only when the model is retrained or new data is scraped

---

## UX Pitfalls

### Pitfall 1: Data Density Without Information Hierarchy

**What goes wrong:** Attempting a Bloomberg Terminal aesthetic without Bloomberg's information hierarchy produces a wall of numbers that overwhelms users. The current matchup page already has 12+ sections. Adding ML outputs (confidence intervals, embedding visualizations, similar player cards) without restructuring creates cognitive overload.

**Why it happens:** The instinct is "we have it, so show it." Every ML feature seems important enough to display. But more data does not equal more value -- it creates "data vomit" (a recognized anti-pattern in dashboard design).

**Prevention:**
- Use progressive disclosure: show headline numbers (projected kills, over/under probability) at the top, let users expand for confidence intervals, embedding details, and methodology
- Group related sections: "Predictions" (kills, map scores, confidence), "Analysis" (comps, pick/ban, records), "Tools" (parlay builder, mispricing)
- Each section should answer one question. If a section tries to answer three questions, split it.
- Apply the "5-second test": can a user identify the key prediction within 5 seconds of page load?

**Phase mapping:** UI redesign phase. Information architecture must be planned before visual design begins.

### Pitfall 2: Redesigning for New Users While Alienating Existing Workflow

**What goes wrong:** A wholesale UI redesign breaks the workflow of anyone already using ThunderEdge. Navigation changes, section reordering, and removed shortcut paths force relearning.

**Prevention:**
- Since ThunderEdge is pre-public (localhost only), this risk is lower than in production software
- Still, maintain URL structure (`/team`, `/prizepicks`, etc.) and keep the same information accessible even if layout changes
- Do not remove existing data sections -- restructure their placement and visual hierarchy

### Pitfall 3: Confidence Intervals That Users Cannot Interpret

**What goes wrong:** Quantile regression outputs (10th/25th/50th/75th/90th percentiles) are displayed raw, and users have no idea what "Q10: 8, Q90: 19" means for their betting decision.

**Prevention:**
- Translate quantile outputs into betting language: "8-19 kills (80% confidence)" or "Over 12.5: 62% likely"
- Use visual indicators (gradient bars, range plots) instead of raw numbers
- Connect confidence intervals to actionable signals: "Line is 14.5, model says 72% under -- moderate edge"
- Always show the model's point estimate (median) alongside the range

---

## "Looks Done But Isn't" Checklist

Things that appear complete but hide unresolved issues.

| Item | Looks Done When... | Actually Done When... |
|------|--------------------|-----------------------|
| Embeddings trained | Training loss converges | Validation loss also converges, k-NN returns sensible neighbors, embedding visualization shows meaningful clusters |
| Quantile regression works | Model produces different outputs for different quantiles | Calibration plot shows predicted quantiles match observed frequencies within 5% |
| k-NN from scratch | Code returns k nearest neighbors | Features are normalized, distance metric is appropriate (cosine > Euclidean for embeddings), results validated qualitatively |
| Model beats baseline | Test set accuracy exceeds Poisson/NegBinom | Improvement holds on walk-forward temporal validation, not just random split |
| UI redesign complete | Pages look different and use dark theme | Information hierarchy is clear, progressive disclosure works, page load time has not regressed, all existing data sections remain accessible |
| Flask serves predictions | Endpoint returns JSON | Latency is under 500ms per request, model is loaded once at startup, `inference_mode()` is active, predictions are cached |
| Data pipeline ready | Model trains on database data | Temporal split is enforced, no future data leakage, normalization uses train-set-only statistics, empty-data cases handled gracefully |
| "From scratch" requirement met | Code does not import sklearn | The algorithm is genuinely implemented (not a thin wrapper around another library), the implementation is explainable, edge cases are handled (e.g., k-NN with ties, quantile crossing) |
| Walk-forward validation works | Multiple train/test splits are evaluated | Each split is strictly temporal, aggregate metrics (not just best split) are reported, variance across splits is reasonable |

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Data preparation | Temporal leakage in train/test split | Sort by event_id, split temporally, validate that no future data leaks into training features |
| Feature engineering | Including betting odds as features | Exclude all market data from model inputs; use only player/team/map performance features |
| Embedding training | Overfitting on 540 matches | Keep dimensions 4-8, use weight decay + dropout + early stopping, validate with k-NN sanity checks |
| Quantile regression | Loss function bugs, quantile crossing | Unit test loss function, train quantiles jointly, add monotonicity constraints, run calibration checks |
| k-NN implementation | Un-normalized features, meaningless distances | Normalize features before distance computation, use cosine similarity for embedding space, validate results qualitatively |
| Flask integration | Slow inference, model reloaded per request | Load model at startup, use `inference_mode()`, batch predictions, cache with TTL |
| UI redesign | Scope creep consuming ML time | Time-box UI work, implement ML first, apply design system to existing components rather than rewriting |
| UI data display | Raw quantile outputs confuse users | Translate to betting language, use visual indicators, connect to actionable signals |
| Monolithic refactoring | Refactoring 1600-line components during redesign | Only extract components needed for ML feature integration; defer full decomposition |
| Demo preparation | Model works but demo flow unclear | Script the demo path: open page, select teams, show prediction, explain the from-scratch algorithm |

---

## Sources

- [Information Leakage in Backtesting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3836631) -- temporal leakage in financial/sports backtesting
- [Quantile Regression Using PyTorch](https://jamesmccaffreyblog.com/2025/02/28/quantile-regression-using-a-pytorch-neural-network-with-a-quantile-loss-function/) -- implementation gotchas (SGD vs Adam, batch norm issues)
- [Quantile Loss in Neural Networks](https://shrmtmt.medium.com/quantile-loss-in-neural-networks-6ea215fcee99) -- vectorized loss function implementation
- [The Curse of Dimensionality in ML](https://www.datacamp.com/blog/curse-of-dimensionality-machine-learning) -- embedding dimension constraints for small datasets
- [Machine Learning with Small and Limited Data](https://link.springer.com/article/10.1186/s40537-025-01346-9) -- strategies for limited-data ML
- [PyTorch Inference Slow Inside Flask API](https://discuss.pytorch.org/t/pytorch-inference-is-slow-inside-flask-api/95476) -- Flask + PyTorch latency issues
- [The Impossible Bloomberg Makeover](https://uxmag.com/articles/the-impossible-bloomberg-makeover) -- data-dense UI redesign complexity
- [UI Density](https://mattstromawn.com/writing/ui-density/) -- density vs. clutter distinction
- [Designing for Data Density](https://paulwallas.medium.com/designing-for-data-density-what-most-ui-tutorials-wont-teach-you-091b3e9b51f4) -- progressive disclosure in data-heavy UIs
- [A Systematic Review of ML in Sports Betting](https://arxiv.org/html/2410.21484v1) -- common modeling mistakes in sports prediction
- [Build a Winning NFL Betting Model](https://nxtbets.com/winning-nfl-betting-model/) -- walk-forward validation, data leakage prevention
- [PyTorch Model Serving](https://pytorch.org/blog/model-serving-in-pyorch/) -- inference optimization patterns
