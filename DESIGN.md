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

- **Max width**: `1400px`, centered, `24px` horizontal padding (`.page-container`)
- **Column pattern**: Single column on all viewports; `.page-container` handles centering
- **Section gaps**: `gap-3` (12px) between collapsible sections; `gap-4`/`gap-5` within cards
- **Z-index scale**: `z-50` (sticky header), `z-10` (table sticky thead)

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

page.tsx (HomePage)
├── Hero
├── CommandBar
│   ├── PlayerInput + AnalyzeButton
│   └── ParamsBar (KillLine, Over/Under Odds, Team Odds)
├── ErrorBanner (conditional)
├── LoadingSkeleton (conditional)
└── Results (conditional)
    ├── StatusBar
    └── CollapsibleSection × N
        ├── Recommendation → RecommendationCard
        ├── Over/Under → OverUnderDisplay
        ├── Expected Rounds (inline display)
        ├── Key Stats → StatsGrid
        ├── Matchup Adjustment → MatchupBox (conditional)
        ├── Agent & Map Breakdown → Radix Tabs → DataTable
        ├── VCT Events Timeline → EventTimeline → KillChips
        └── Edge Analysis → EdgeSection → DistributionChart
```

---

## Anti-patterns to Avoid

- No neon glow / scanline effects (not our brand)
- No `scale` transform on hover (causes layout shift)
- No emoji as UI icons — use Lucide SVG icons throughout
- No inline `style` for spacing — use Tailwind utilities
- Exception: `style={{ borderLeft: '3px solid ...' }}` is acceptable for dynamic accent borders
