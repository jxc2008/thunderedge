# Feature Landscape

**Domain:** Esports betting analytics with ML kill predictions + UI/UX overhaul
**Researched:** 2026-03-07

## Table Stakes

Features users expect from an ML-powered betting analytics tool. Missing = product feels incomplete or untrustworthy.

### ML Prediction Features

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Point prediction with confidence intervals | Every serious prediction tool shows uncertainty bands, not just a single number. Users distrust bare predictions. | Med | Quantile regression at 10th/25th/50th/75th/90th percentiles. From-scratch implementation satisfies course rubric. |
| Model accuracy metrics / backtesting display | Users need to know WHY they should trust the model. Show hit rate, calibration, comparison vs naive baseline. | Med | Compare ML model vs current Poisson/NegBinom on held-out data. Display "Model hits X% of overs" type stats. |
| Per-player kill distribution visualization | Already exists (Poisson/NegBin charts). Must upgrade to show ML-predicted distribution overlaid on historical. | Low | Extend existing `distribution-chart.tsx`. Show both statistical and ML distributions side-by-side. |
| Feature importance / explainability | Users want to know what drives a prediction (map, opponent, agent, recent form). Black box = no trust. | Med | Display top 3-5 factors for each prediction. SHAP-like bar chart or simple feature contribution bars. |
| Similar player lookups | "Players like X" is table stakes for any analytics tool with embeddings. If you build embeddings and don't expose similarity search, users wonder why. | Med | k-NN in embedding space (from-scratch). Show top 5 similar players with similarity scores. |
| Matchup-adjusted predictions | Already partially exists (alpha/beta/gamma). ML model should inherently account for opponent strength. | High | Opponent encoding as input feature. Current calibration showed genuine signal in results-based adjustment. |

### UI/UX Features

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Dark theme (true dark, not gray) | Every serious trading/betting tool uses dark backgrounds. Bloomberg terminal, DraftKings, FanDuel all use dark. Users expect it in this domain. | Med | Full dark theme with Tailwind dark mode. Use shadcn/ui built-in dark mode support. High contrast text on near-black backgrounds (#0a0a0f range). |
| Consistent design system | Current UI is functional but visually inconsistent. A cohesive design language (spacing, colors, typography) is table stakes for any "redesign". | Med | Define design tokens: background, surface, border, accent colors. Consistent card/panel components. Use Tailwind theme config. |
| Global navigation overhaul | Current navigation is fragmented across pages. Users need to move between player analysis, matchups, PrizePicks without friction. | Med | Sidebar or top nav with clear hierarchy. Current `app-header.tsx` needs redesign. Group: Analysis tools, Matchups, Market data. |
| Loading states and skeleton screens | Data-fetching tools without proper loading states feel broken. Current approach uses simple loading text. | Low | Skeleton components matching card layouts. Pulse animation on data cells. Already have shadcn primitives. |
| Responsive data tables | Current `data-table.tsx` exists but needs polish. Sortable, filterable tables are expected for any data-dense tool. | Low | Column sorting, sticky headers, horizontal scroll on mobile. Keep existing component, add features. |
| Error states with retry | Current inline error banners are minimal. Users expect clear error messages and ability to retry failed requests. | Low | Toast notifications for transient errors, inline error panels with retry buttons for persistent failures. |

## Differentiators

Features that set ThunderEdge apart. Not expected, but create competitive advantage.

### ML Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Player embedding space visualization | Interactive 2D/3D scatter plot of all players in embedding space. Users can explore who clusters together, discover non-obvious similarities. No competing tool does this for Valorant. | High | PCA or t-SNE reduction of learned embeddings. Interactive plot (click to see player details, hover for stats). This is the "wow" feature for the course demo. |
| Quantile-based over/under with calibrated probabilities | Instead of just "over 55% / under 45%", show the full predicted kill distribution from quantile regression with calibrated confidence. More nuanced than any existing tool. | High | Multiple quantile models (0.05 to 0.95 in steps). Plot predicted CDF. Compare predicted distribution shape to market-implied line. From-scratch implementation. |
| Map-conditional predictions | Show how kill predictions change per map. "On Ascent, projected 18.5 kills (75th: 22). On Lotus, projected 15.2 kills (75th: 18)." Most tools give one number. | Med | Map embedding as input feature. Display predictions broken down by likely maps (use existing map probability data). |
| Mispricing confidence scoring | Current mispricing alerts are binary. Add a confidence score: "HIGH confidence mispricing" vs "marginal edge, proceed with caution." | Med | Combine prediction uncertainty (quantile width) with edge magnitude. Wide quantile range + small edge = low confidence. |
| Agent composition impact analysis | Show how different agent comps shift kill predictions. "When TenZ plays Jett: +2.1 projected kills. When on Iso: -0.8." Unique to Valorant analytics. | High | Agent one-hot or embedding as model input. Show counterfactual predictions with different agent selections. Requires existing comp data from `get_team_comps_per_map`. |
| Parlay correlation matrix | Visual correlation matrix showing which player prop legs are positively/negatively correlated. "These two players on same map = correlated legs, reduces true parlay value." | Med | Compute from embedding similarity or historical co-occurrence. Display as heatmap in parlay builder. |

### UI Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Progressive disclosure / drill-down panels | Summary view shows key numbers. Click to expand into full statistical breakdown. Reduces initial clutter while preserving data density for power users. | Med | Collapsible sections already exist (`collapsible-section.tsx`). Systematize: Level 1 (KPIs), Level 2 (charts), Level 3 (raw data tables). |
| KPI strip / dashboard header | Bloomberg-style top strip showing key metrics at a glance. On matchup page: win prob, projected total maps, key player matchup. Always visible. | Low | Already started (`kpi-strip.tsx` in `_components`). Extend to all pages. Fixed position or sticky. |
| Sparkline mini-charts in tables | Small inline trend charts in data table cells. Show last 5 match kill counts as a sparkline next to the prediction number. | Med | Lightweight SVG sparklines (recharts `ResponsiveContainer` at tiny size, or raw SVG). Adds visual scanning without clutter. |
| Keyboard shortcuts for power users | Bloomberg terminal users expect keyboard navigation. Tab between sections, Enter to expand, number keys to switch maps. | Low | Not many betting tools have this. Low effort, high perceived quality for target audience. |
| Animated transitions between data states | Smooth number counters, chart transitions when switching maps or players. Makes the tool feel premium. | Low | Framer Motion or CSS transitions. Number counting animation on KPI changes. |
| Command palette / quick search | Cmd+K to search for any player, team, or matchup. Power user feature that feels professional. | Med | Simple modal with fuzzy search across known players/teams from database. cmdk library or build with Radix Dialog. |

## Anti-Features

Features to explicitly NOT build. Each would waste effort or harm the product.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Real-time odds streaming | Requires paid API subscriptions, WebSocket infrastructure, and introduces latency/reliability concerns. Manual input is fine for the use case (pre-match analysis, not live betting). | Keep manual odds input. Add a "paste odds" quick-entry for faster input. |
| User accounts / authentication | Adds complexity with zero value for a local-first analytics tool. No personalization needed at this stage. | Stay public/local. If needed later, use simple localStorage preferences. |
| Chat/AI assistant for betting advice | LLM integration for "ask me about this matchup" is gimmicky, unreliable for actual betting decisions, and distracts from the core value (data-driven predictions). | Let the data and visualizations speak. Add better tooltips and contextual help instead. |
| Social features / community picks | Leaderboards, shared parlays, and social validation create noise. The target user is a solo analytical bettor, not a social bettor. | Focus on individual analysis tools. The existing PrizePicks leaderboard OCR feature is sufficient. |
| Mobile-first design | The project explicitly targets desktop analytical workflows. Data-dense UIs fundamentally conflict with small screens. Responsive is fine; mobile-optimized is not. | Ensure responsive breakpoints don't break the layout. But design for 1280px+ primary viewport. |
| Automated betting / bet placement | Legal liability, API integration complexity, and fundamentally different product category. ThunderEdge is an analysis tool, not a betting platform. | Show "suggested bet" with copy-pasteable amounts, not one-click betting. |
| Complex multi-model ensemble | Diminishing returns on ~540 match records. Ensemble of 5 models on small data = overfitting theater. | Single well-tuned model with proper cross-validation. Demonstrate it beats the statistical baseline honestly. |
| Live in-game predictions | Requires real-time game state data feed that doesn't exist for Valorant at the amateur/public level. Different product entirely. | Focus on pre-match predictions. If round-level data becomes available, revisit. |

## Feature Dependencies

```
Core ML Pipeline
  Embeddings Training --> Similar Player Lookup (k-NN)
  Embeddings Training --> Embedding Space Visualization (PCA/t-SNE)
  Embeddings Training --> Quantile Regression Model (uses embeddings as features)
  Quantile Regression --> Confidence Intervals on Predictions
  Quantile Regression --> Mispricing Confidence Scoring
  Quantile Regression --> Map-Conditional Predictions
  Quantile Regression --> Agent Composition Impact (counterfactuals)

UI Foundation
  Design System (tokens, theme) --> Dark Theme
  Design System --> KPI Strip
  Design System --> All other UI components
  Global Navigation Overhaul --> Progressive Disclosure
  Loading States --> All data-fetching pages

Feature Integration
  ML Predictions API --> Frontend Prediction Display
  Confidence Intervals --> Parlay Correlation Matrix
  Embedding Space Visualization --> Similar Player Lookup UI
  Map-Conditional Predictions --> Enhanced Matchup Page
  Model Accuracy Metrics --> Backtesting Display Page
```

## MVP Recommendation

### Phase 1: UI Foundation (do first)
Prioritize because every subsequent ML feature needs a solid display layer.

1. **Design system + dark theme** -- defines the visual language for everything else
2. **Global navigation overhaul** -- restructure information architecture before adding new pages
3. **Loading states + skeleton screens** -- needed before ML endpoints (which will be slower)
4. **KPI strip component** -- reusable across all pages

### Phase 2: Core ML
5. **Player/map embeddings** -- foundation for all ML features, satisfies course requirement
6. **Quantile regression (from scratch)** -- replaces Poisson/NegBin as primary predictor, satisfies course "from scratch" requirement
7. **Confidence intervals on predictions** -- immediate payoff from quantile regression
8. **Model accuracy metrics / backtesting** -- prove the model works

### Phase 3: ML-Powered Features
9. **Similar player lookup (k-NN from scratch)** -- second from-scratch algorithm, satisfies course requirement
10. **Feature importance / explainability** -- build trust in predictions
11. **Map-conditional predictions** -- leverage existing map probability data
12. **Mispricing confidence scoring** -- upgrade existing mispricing alerts

### Phase 4: Differentiators
13. **Embedding space visualization** -- the "wow" demo feature
14. **Progressive disclosure redesign** -- polish the full UX
15. **Sparkline mini-charts** -- visual density upgrade
16. **Parlay correlation matrix** -- advanced feature for power users

**Defer indefinitely:** Agent composition impact (requires more data than available), command palette (nice-to-have), keyboard shortcuts (nice-to-have).

## Prioritization Matrix

| Feature | Impact | Effort | Risk | Priority |
|---------|--------|--------|------|----------|
| Design system + dark theme | High | Med | Low | P0 |
| Navigation overhaul | High | Med | Low | P0 |
| Player/map embeddings | High | High | Med | P0 |
| Quantile regression (from scratch) | High | High | Med | P0 |
| Confidence intervals | High | Low | Low | P1 |
| Model accuracy / backtesting | High | Med | Low | P1 |
| Similar player lookup (k-NN) | Med | Med | Low | P1 |
| Loading states / skeletons | Med | Low | Low | P1 |
| KPI strip | Med | Low | Low | P1 |
| Feature importance | Med | Med | Med | P2 |
| Map-conditional predictions | Med | Med | Med | P2 |
| Embedding visualization | High | Med | Med | P2 |
| Mispricing confidence scoring | Med | Low | Low | P2 |
| Progressive disclosure | Med | Med | Low | P2 |
| Sparklines in tables | Low | Low | Low | P3 |
| Parlay correlation matrix | Med | Med | Med | P3 |
| Agent comp impact | Med | High | High | Defer |
| Command palette | Low | Med | Low | Defer |
| Keyboard shortcuts | Low | Low | Low | Defer |

## Sources

- [DraftKings Stats Hub features](https://dknetwork.draftkings.com/2024/04/11/draftkings-sportsbook-how-to-use-enhanced-features-on-stats-hub/)
- [Quantile regression in sports betting (PLOS ONE)](https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0287601&type=printable)
- [NBA2Vec: Player embeddings with dimensionality reduction](https://arxiv.org/pdf/2302.13386)
- [Football2Vec: Embedding players using NLP techniques](https://github.com/ofirmg/football2vec)
- [Valorant player performance prediction with Random Forest](https://ijrm.net/index.php/ijrm/article/view/39)
- [Round outcome prediction in Valorant using tactical features](https://arxiv.org/html/2510.17199v1)
- [Tremor: React dashboard components with dark mode](https://www.tremor.so/)
- [Bloomberg Terminal color accessibility design](https://www.bloomberg.com/ux/2021/10/14/designing-the-terminal-for-color-accessibility/)
- [Sports betting UI/UX design guide](https://www.gammastack.com/blog/sports-betting-ui-ux-guide/)
- [GRID Insights: AI predictive analytics for esports](https://ministryofsport.com/grid-esports-launches-ai-predictive-analytics-product-for-esports-broadcasts/)
- [Player recommender tools with embeddings](https://medium.com/analytics-vidhya/building-a-player-recommender-tool-666b5892336f)
- [UMAP for soccer player analysis](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8307339/)
