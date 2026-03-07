# Technology Stack: ML Pipeline & UI Redesign

**Project:** ThunderEdge - Valorant Esports Analytics
**Researched:** 2026-03-07
**Scope:** Additions to existing stack (Next.js 15 / React 19 / Flask 3 / SQLite stay)

## Recommended Stack

### ML / Model Training (Python Backend)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| PyTorch | 2.6.x (latest stable) | Model training, embeddings, inference | Course requirement (CSCI-UA 473). 2.6 is latest stable as of early 2026. Do NOT use 2.10 nightly. | HIGH |
| scikit-learn | 1.6.x | PCA for dimensionality reduction visualization only | Use ONLY for PCA/UMAP viz preprocessing on backend. k-NN and quantile regression must be from scratch per rubric. | HIGH |
| umap-learn | 0.5.x | Embedding space visualization (2D projection) | Better than t-SNE for preserving global structure. Compute on backend, send 2D coords to frontend. | MEDIUM |
| joblib | 1.4.x | Model serialization | Ships with scikit-learn. Simpler than pickle for PyTorch state_dict + preprocessing pipeline. | HIGH |

### Model Serving (Flask Integration)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Flask (existing) | 3.0.0 | Serve predictions via REST | Already in place. Load model at app startup, run inference in request handlers. No need for TorchServe or separate serving infra at this scale. | HIGH |
| torch.jit (TorchScript) | (bundled with PyTorch) | Model optimization | Script trained models for faster inference. Optional but easy win for CPU-only serving. | MEDIUM |

**Integration pattern:** Load the trained PyTorch model once at Flask app startup (`torch.load()` / `model.load_state_dict()`), keep it in memory as a module-level variable. Inference on each API request is a forward pass -- sub-millisecond for a small embedding + regression network on CPU. No GPU needed. No model server needed. No async needed. The dataset is ~540 matches; the model is tiny.

```python
# backend/ml/model.py
import torch

class KillPredictor(torch.nn.Module):
    """Embedding + quantile regression head."""
    def __init__(self, n_players, n_maps, embed_dim=16, n_quantiles=3):
        super().__init__()
        self.player_embed = torch.nn.Embedding(n_players, embed_dim)
        self.map_embed = torch.nn.Embedding(n_maps, embed_dim)
        # Quantile regression head (from scratch -- no library)
        self.head = torch.nn.Linear(embed_dim * 2 + n_features, n_quantiles)

    def forward(self, player_ids, map_ids, features):
        p = self.player_embed(player_ids)
        m = self.map_embed(map_ids)
        x = torch.cat([p, m, features], dim=-1)
        return self.head(x)  # outputs [q25, q50, q75]

# backend/ml/serve.py -- loaded once at startup
_model = None
def get_model():
    global _model
    if _model is None:
        _model = KillPredictor(...)
        _model.load_state_dict(torch.load("models/kill_predictor.pt"))
        _model.eval()
    return _model
```

### Quantile Regression (From Scratch)

| Component | Implementation | Why |
|-----------|---------------|-----|
| Pinball loss | Custom `torch.autograd` function | Course rubric requires from-scratch. Loss = max(q * e, (q-1) * e) where e = y - y_hat. 5 lines of code. |
| Quantile crossing fix | Sort output quantiles | Simple monotonicity enforcement. No need for constrained optimization (CJQR-ALM is overkill for this scale). |
| Optimizer | Adam with lr=1e-3 | SGD is fine too but Adam converges faster on small datasets. |

### k-NN Retrieval (From Scratch)

| Component | Implementation | Why |
|-----------|---------------|-----|
| Similarity metric | Cosine similarity via `torch.nn.functional.cosine_similarity` | Standard for embedding spaces. Using the PyTorch op is fine -- the k-NN selection logic is what must be from scratch. |
| k-NN search | Brute-force pairwise distance matrix | With ~200 players, brute force is instant. No need for FAISS, Annoy, or any ANN library. |
| Embedding storage | SQLite table + `.pt` file | Store embedding vectors as a `.pt` tensor file. Store player-to-index mapping in SQLite. Load once at startup. |

### Data Visualization (Frontend)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Recharts (existing) | 2.15.4 | Charts (bar, line, area, scatter) | Already installed. shadcn/ui chart components are built on Recharts. Dark mode works via CSS variables. Sufficient for kill distributions, win rates, projected scores. | HIGH |
| react-plotly.js | 2.6.0 | 3D scatter plot for embedding space visualization | Only library with good 3D interactive scatter support in React. Use ONLY for the embedding visualization -- Recharts handles everything else. Bundle size is large (~3MB) so lazy-load it. | MEDIUM |
| plotly.js | 2.35.x | Peer dependency of react-plotly.js | Required. Use partial bundle (`plotly.js-gl3d-dist`) to reduce size to ~1MB. | MEDIUM |

### Data Tables (Frontend)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| @tanstack/react-table | 8.21.x | Data-dense sortable/filterable tables | shadcn/ui DataTable is built on TanStack Table. Already the standard pairing. Sorting, filtering, column visibility, pagination all built in. | HIGH |

### UI / Dark Theme (Frontend)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| shadcn/ui (existing) | latest | Component primitives | Already installed (full Radix suite). Use `npx shadcn-ui add chart` and `npx shadcn-ui add data-table` to scaffold chart/table components. | HIGH |
| next-themes (existing) | 0.4.6 | Dark/light mode toggle | Already installed. Set `defaultTheme="dark"` and define dark palette in CSS variables. | HIGH |
| Tailwind CSS (existing) | 4.1.x | Utility styling | Already installed. Use `dark:` variants and CSS variables for the dark palette. | HIGH |
| Framer Motion | 11.x | Micro-animations, transitions | Subtle entrance animations for cards, charts loading in. Lightweight. Not required but improves perceived quality significantly. | LOW |

### Dark Theme Color System

No new library needed. Define in `app/globals.css`:

```css
:root {
  /* Dark-first design (Bloomberg/DraftKings aesthetic) */
  --background: 222 47% 6%;      /* near-black blue */
  --foreground: 210 40% 96%;     /* soft white */
  --card: 222 47% 8%;            /* slightly lighter than bg */
  --card-foreground: 210 40% 96%;
  --primary: 142 76% 46%;        /* green accent (profit/positive) */
  --destructive: 0 84% 60%;      /* red (loss/negative) */
  --muted: 215 20% 15%;          /* muted panels */
  --chart-1: 142 76% 46%;        /* green */
  --chart-2: 199 89% 48%;        /* blue */
  --chart-3: 45 93% 47%;         /* gold/warning */
  --chart-4: 280 65% 60%;        /* purple */
  --chart-5: 0 84% 60%;          /* red */
}
```

## What NOT to Use

| Technology | Why Not |
|------------|---------|
| TorchServe / Triton | Massive overkill. You have 200 players, a tiny model, and single-digit QPS. Flask in-process inference is the right answer. |
| FAISS / Annoy / ScaNN | Overkill for ~200 vectors. Brute-force cosine similarity is O(n) with n=200. These add C++ build dependencies for zero benefit. |
| ONNX Runtime | Adds complexity for negligible speedup on a model this small. Stick with native PyTorch. |
| Nivo | Heavier than Recharts, you already have Recharts + shadcn chart integration working. Switching gains nothing. |
| Tremor | Built on Recharts anyway but adds abstraction that limits customization. Redundant with shadcn/ui. |
| D3.js (raw) | Too low-level. Recharts and Plotly cover all needed chart types without writing SVG by hand. |
| AG Grid | Commercial license needed for advanced features. TanStack Table + shadcn does everything needed here for free. |
| Visx | Low-level D3 wrapper. More work than Recharts for the same result. |
| sklearn for k-NN/quantile reg | Course rubric requires from-scratch implementation. Using sklearn defeats the purpose and loses 10% of the grade. |
| react-three-fiber / Three.js | Too heavy for a 2D/3D scatter plot. Plotly handles 3D scatter with orbit controls out of the box. |
| Prisma / Drizzle ORM | SQLite with raw queries works. Adding an ORM to an existing backend with ~20 query methods is churn, not progress. |
| Redis / PostgreSQL | Dataset is ~540 matches. SQLite handles this trivially. No need for a separate database server. |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not Alternative |
|----------|-------------|-------------|---------------------|
| ML framework | PyTorch | TensorFlow/JAX | Course requires PyTorch. Also better for custom loss functions and from-scratch implementations. |
| Model serving | Flask in-process | TorchServe | Project is local-only, single user, tiny model. TorchServe adds Docker, gRPC, config complexity. |
| Embedding viz | react-plotly.js | deck.gl | deck.gl is for geospatial. Plotly has better 3D scatter with hover tooltips and orbit controls. |
| Charts | Recharts (keep) | ECharts | ECharts is better for 10K+ data points but overkill here. Recharts already integrated with shadcn. |
| Tables | TanStack Table | AG Grid | AG Grid enterprise features cost money. TanStack is free and shadcn wraps it natively. |
| Dim. reduction | UMAP | t-SNE | UMAP preserves global structure better, runs faster, and is more interpretable for a course project. |

## Installation

### Backend (Python)

```bash
# ML dependencies (add to requirements.txt)
pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu
pip install scikit-learn==1.6.1
pip install umap-learn==0.5.7
pip install joblib==1.4.2
```

**Note:** Use CPU-only PyTorch (`--index-url .../cpu`). No GPU needed for a model with ~200 embeddings and a linear head. Saves ~2GB of download vs the CUDA build.

### Frontend (npm)

```bash
# 3D embedding visualization (lazy-loaded)
npm install react-plotly.js plotly.js-gl3d-dist

# Data tables (if not already scaffolded)
npx shadcn-ui add data-table
npx shadcn-ui add chart

# Optional: animations
npm install framer-motion

# TanStack Table (peer dep for shadcn data-table)
npm install @tanstack/react-table
```

## File Structure for ML Components

```
backend/
  ml/
    __init__.py
    model.py          # KillPredictor(nn.Module) definition
    train.py           # Training script (run offline, saves .pt)
    quantile_loss.py   # From-scratch pinball loss
    knn.py             # From-scratch k-NN on embeddings
    embeddings.py      # Embedding extraction & UMAP projection
    serve.py           # Model loading & inference helpers
models/
  kill_predictor.pt    # Serialized model weights
  embeddings.pt        # Player/map embedding matrix
  umap_coords.json     # Pre-computed 2D UMAP projections
```

## Sources

- [PyTorch Flask REST API Tutorial](https://docs.pytorch.org/tutorials/intermediate/flask_rest_api_tutorial.html) -- official PyTorch docs on Flask deployment
- [PyTorch Releases](https://github.com/pytorch/pytorch/releases) -- version tracking
- [PyTorch CosineSimilarity docs](https://docs.pytorch.org/docs/stable/generated/torch.nn.CosineSimilarity.html) -- embedding similarity
- [Quantile Regression with PyTorch (McCaffrey, Feb 2025)](https://jamesmccaffreyblog.com/2025/02/28/quantile-regression-using-a-pytorch-neural-network-with-a-quantile-loss-function/) -- pinball loss implementation
- [shadcn/ui Chart docs](https://ui.shadcn.com/docs/components/radix/chart) -- Recharts integration
- [shadcn/ui Data Table docs](https://ui.shadcn.com/docs/components/radix/data-table) -- TanStack Table integration
- [TanStack Table](https://tanstack.com/table/latest) -- v8.21.x headless table
- [react-plotly.js GitHub](https://github.com/plotly/react-plotly.js) -- 3D scatter visualization
- [UMAP documentation](https://umap-learn.readthedocs.io/en/latest/) -- dimensionality reduction
- [shadcn/ui chart discussion](https://github.com/shadcn-ui/ui/discussions/4133) -- community charting patterns
- [Plotly t-SNE and UMAP projections](https://plotly.com/python/t-sne-and-umap-projections/) -- embedding visualization patterns

---

*Stack research: 2026-03-07*
