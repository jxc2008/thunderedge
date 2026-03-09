# ThunderEdge UI Changelog

## Split-Panel Dashboard Redesign

### Layout (Structural)

| # | Before | After |
|---|--------|-------|
| 1 | Single centered column, max-width 1400px | Split-panel: 300px sticky left sidebar + flex-1 scrollable right panel |
| 2 | Full-page hero heading above inputs | Hero moved into left panel header (always visible, doesn't steal screen height) |
| 3 | Inputs in a "command bar" block at page top | Inputs in a dedicated sidebar panel with labeled form fields |
| 4 | Results stack below inputs, requiring scroll past command bar | Results in right panel, visible alongside inputs without scrolling |
| 5 | Left panel scrolls away with page | Left sidebar is `position: sticky` — stays visible while right panel scrolls |

### Information Hierarchy

| # | Before | After |
|---|--------|-------|
| 6 | Results in 7 collapsible accordion sections | Results in 4-tab deep-dive (Overview / Stats / History / Edge) |
| 7 | No at-a-glance summary — user must open sections to see data | KPI Strip: 6 stat cards at top of right panel (Kill Line, Over%, Under%, Wtd KPR, Maps, Confidence) |
| 8 | Player name/team only visible in status bar buried in results | Quick summary in left sidebar (player name, team, recommendation badge) after analysis |
| 9 | Recommendation section mixed with other content in accordion | Recommendation is first card in Overview tab with clear classification badge |
| 10 | Status bar at top of results with live/cached counts | Cache/live counts surfaced in KPI strip Maps card subtitle |

### Form / Input UX

| # | Before | After |
|---|--------|-------|
| 11 | Inline label+input pairs in a single horizontal flex bar | Stacked label-above-input layout with explicit `<label htmlFor>` association |
| 12 | Over/Under odds squeezed into single row with 4 other params | Over/Under pair and Team/Opp pair each in a 2-column grid for clear grouping |
| 13 | `>` prompt prefix inline in the same box as other inputs | `>` prefix as absolute-positioned icon inside IGN field only |
| 14 | Analyze button small, right-aligned in the command bar row | Full-width yellow CTA button below the form fields — maximum affordance |

### Visual Design

| # | Before | After |
|---|--------|-------|
| 15 | Results section cards open on `.bg-[#0D0D0D]` same as page | Left panel uses `#060608` — visibly darker than the `#000000` right panel |
| 16 | Section headers only inside collapsible toggles | `SectionCard` component with consistent title + badge pattern across all content blocks |
| 17 | O/U percentages and Expected Rounds in separate accordion items | Displayed side-by-side in a 2-column grid on wide screens (lg:grid-cols-2) |
| 18 | Empty state: nothing rendered | "Ready" typographic placeholder fills the right panel before analysis |

### Component Architecture

| # | Before | After |
|---|--------|-------|
| 19 | All inputs, form state, and layout in one 650-line page.tsx | Inputs extracted to `app/_components/input-panel.tsx`; KPI cards to `app/_components/kpi-strip.tsx` |
| 20 | No reusable section wrapper | `SectionCard` component with title/badge/accentColor props used for all content blocks |
