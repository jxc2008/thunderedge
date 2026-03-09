# ThunderEdge — Design System

Dark-mode Valorant/esports analytics aesthetic. Data-dense, terminal-inspired, monochrome with electric-yellow accents.

---

## Design Tokens (`app/globals.css`)

| Token | Value | Usage |
|---|---|---|
| `--color-background` | `#000000` | Body background |
| `--color-surface` | `#0a0a0a` | Card / data table backgrounds |
| `--color-surface-raised` | `#0D0D0D` | Accent cards, command bar |
| `--color-border` | `#27272a` | Default borders |
| `--color-border-subtle` | `rgba(255,255,255,0.06)` | Dividers, section rules |
| `--color-text-primary` | `#e4e4e7` | Body copy |
| `--color-text-secondary` | `#a1a1aa` | Table cells, secondary labels |
| `--color-text-muted` | `#71717a` | Timestamps, captions |
| `--color-accent-yellow` | `#F0E040` | Brand accent, CTA, active indicators |
| `--color-success` | `#22c55e` | Over / positive / cached |
| `--color-danger` | `#ef4444` | Under / negative / error |
| `--color-warning` | `#f59e0b` | Live events, caution |

---

## Typography Scale

| Role | Font | Weight | Size |
|---|---|---|---|
| Display / headings | Barlow Condensed (`font-display`) | 700–900 | `clamp(2.5rem,6vw,5rem)` for hero |
| Section labels | Barlow Condensed | 700 | `0.9rem`, `uppercase`, `tracking-[0.06em]` |
| Body | Inter | 400–600 | `0.875rem` (14px) default |
| Mono / numbers | `font-mono` (Courier New fallback) | 400 | `1rem` for formulas |
| Stat values | Barlow Condensed | 900 | `2rem` (StatCard) |

---

## Layout Rules

- **Dashboard layout**: `flex flex-col md:flex-row` — stacked on mobile, side-by-side on desktop
- **Left panel**: `w-full md:w-[300px]`, `sticky top-[56px]`, `max-height: calc(100vh - 56px)`, bg `#060608`
- **Right panel**: `flex-1 min-w-0`, natural document flow / scrollable
- **Header height**: `--header-h: 56px` CSS variable (used for sticky offset)
- **Section gaps**: `gap-4` between SectionCards; `gap-3` inside KPI strip
- **Z-index scale**: `z-50` (sticky header), `z-10` (table sticky thead)
- **Page container** (non-dashboard pages): `max-width: 1400px`, centered, `24px` horizontal padding

---

## Key Component Patterns

### Accent Card
```html
<div
  class="bg-[#0D0D0D] border border-[rgba(240,224,64,0.15)]"
  style="border-left: 3px solid #F0E040;"
>
```
Used for: command bar, status bar, matchup box, section wrappers.

### CollapsibleSection
- Yellow (or semantic) left-border card
- Header button with `ChevronDown/Right` icon
- Content animated via CSS `grid-template-rows: 0fr → 1fr` (200ms ease)
- **Props**: `title`, `defaultOpen`, `accentColor`

### Tabs (Radix)
```html
<Tabs.List class="flex border-b border-[rgba(255,255,255,0.06)]">
  <Tabs.Trigger class="... data-[state=active]:text-white data-[state=active]:border-[#F0E040]">
```
Active indicator: 2px bottom border in brand yellow.

### Kill Chips
- Inline `<span>` per kill value
- Green background / border for Over (`k > line`), red for Under
- `font-display font-bold` for the number

### Semantic Colors in JSX
Use Tailwind arbitrary values or inline `style={{ color }}` for dynamic semantic colors:
- Over/positive: `#22c55e`
- Under/negative: `#ef4444`
- Warning/live: `#f59e0b`
- Accent: `#F0E040`

---

## Component Hierarchy

```
AppHeader
└── Navigation (dropdowns + direct links + sync button)

page.tsx (HomePage) — split-panel dashboard
├── LEFT PANEL (300px sticky)
│   └── InputPanel (app/_components/input-panel.tsx)
│       ├── Panel header (title + tagline)
│       ├── Player IGN input
│       ├── Kill Line input
│       ├── Over/Under Odds (2-col grid)
│       ├── Team/Opp Odds (2-col grid)
│       ├── Analyze CTA button
│       └── Quick summary (post-analysis: player name + recType badge)
└── RIGHT PANEL (flex-1 scrollable)
    ├── ErrorBanner (conditional)
    ├── LoadingSkeleton (conditional)
    ├── EmptyState (conditional — "Ready" typographic placeholder)
    └── Results (conditional)
        ├── KpiStrip (app/_components/kpi-strip.tsx)
        │   └── 6× KpiCard (Kill Line / Over% / Under% / Wtd KPR / Maps / Confidence)
        └── Radix Tabs (Overview / Stats / History / Edge)
            ├── Overview → SectionCard × N
            │   ├── Recommendation → RecommendationCard
            │   ├── Over/Under → OverUnderDisplay
            │   ├── Expected Rounds (inline display)
            │   └── Matchup Adjustment → MatchupBox (conditional)
            ├── Stats → SectionCard × 2
            │   ├── Key Stats → StatsGrid
            │   └── Agent & Map Breakdown → Radix Tabs → DataTable
            ├── History → SectionCard
            │   └── VCT Events Timeline → EventTimeline → KillChips
            └── Edge → SectionCard (conditional)
                └── EdgeSection → DistributionChart
```

### SectionCard
Reusable content wrapper with title + optional badge:
```html
<div class="bg-[#0D0D0D] border border-[rgba(255,255,255,0.06)]"
     style="border-left: 3px solid {accentColor}">  <!-- optional -->
  <div class="px-5 py-3 border-b ...">
    <span class="font-display font-bold text-[0.72rem] uppercase tracking-[0.1em] text-white/55">
      {title}
    </span>
    {badge}  <!-- optional ReactNode -->
  </div>
  <div class="px-5 py-4">{children}</div>
</div>
```

---

## Anti-patterns to Avoid

- No neon glow / scanline effects (not our brand)
- No `scale` transform on hover (causes layout shift)
- No emoji as UI icons — use Lucide SVG icons throughout
- No inline `style` for spacing — use Tailwind utilities
- Exception: `style={{ borderLeft: '3px solid ...' }}` is acceptable for dynamic accent borders
