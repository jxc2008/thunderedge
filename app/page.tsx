'use client'

import { useState } from 'react'
import { AppHeader } from '@/components/app-header'
import { SearchForm, type SearchFormData } from '@/components/search-form'
import { OverUnderDisplay } from '@/components/over-under-display'
import { StatsGrid, type StatCardData } from '@/components/stats-grid'
import { DataTable, type Column } from '@/components/data-table'
import { EventCard, type EventCardData } from '@/components/event-card'
import { RecommendationCard } from '@/components/recommendation-card'
import { DistributionChart } from '@/components/distribution-chart'
import {
  ToastProvider,
  useToast,
  EmptyState,
  SkeletonOverUnder,
  SkeletonStatsGrid,
  SkeletonTable,
  SkeletonEventCards,
} from '@/components/ux-patterns'

/* ─── Sample result data (simulates API response) ─────── */
interface AgentRow { agent: string; maps: number; killsPerMap: number; overPct: number }
const AGENT_COLS: Column<AgentRow>[] = [
  { key: 'agent', label: 'Agent', sortable: true },
  { key: 'maps', label: 'Maps', sortable: true, align: 'right' },
  { key: 'killsPerMap', label: 'K/Map', sortable: true, align: 'right', killRateBar: true, barMax: 30 },
  {
    key: 'overPct',
    label: 'Over %',
    sortable: true,
    align: 'right',
    render: (v) => (
      <span style={{ color: (v as number) >= 55 ? '#22c55e' : (v as number) <= 45 ? '#ef4444' : '#a1a1aa' }}>
        {(v as number).toFixed(1)}%
      </span>
    ),
  },
]

function buildResult(player: string) {
  const stats: StatCardData[] = [
    { label: 'Model Mean', value: '21.4', delta: 'kills / map', semantic: 'positive' },
    { label: 'Market Implied', value: '19.5', delta: 'kill line', semantic: 'neutral' },
    { label: 'Sample Size', value: 47, delta: 'maps analyzed', semantic: 'neutral' },
    { label: 'K/Map Avg', value: '20.8', delta: 'last 20 maps', semantic: 'neutral' },
    { label: 'Edge', value: '+9.2pp', delta: 'vs market', semantic: 'positive' },
    { label: 'VLR Rating', value: '1.34', delta: 'overall rating', semantic: 'neutral' },
  ]
  const agents: AgentRow[] = [
    { agent: 'Jett', maps: 14, killsPerMap: 23.4, overPct: 71.4 },
    { agent: 'Neon', maps: 12, killsPerMap: 21.1, overPct: 58.3 },
    { agent: 'Raze', maps: 10, killsPerMap: 19.8, overPct: 50.0 },
    { agent: 'Reyna', maps: 7, killsPerMap: 18.6, overPct: 42.9 },
    { agent: 'Iso', maps: 4, killsPerMap: 16.3, overPct: 25.0 },
  ]
  const events: EventCardData[] = [
    {
      id: '1', eventName: 'VCT Americas 2025 — Masters', date: 'Feb 2025',
      isCached: true, overCount: 6, underCount: 2, defaultOpen: true,
      maps: [
        { map: 'Ascent', kills: 22, line: 19.5 },
        { map: 'Bind', kills: 25, line: 19.5 },
        { map: 'Haven', kills: 18, line: 19.5 },
      ],
    },
    {
      id: '2', eventName: 'VCT Americas 2025 — Kickoff', date: 'Jan 2025',
      isCached: true, overCount: 4, underCount: 3,
      maps: [
        { map: 'Pearl', kills: 21, line: 19.5 },
        { map: 'Icebox', kills: 17, line: 19.5 },
        { map: 'Lotus', kills: 20, line: 19.5 },
      ],
    },
    {
      id: '3', eventName: 'Champions 2024', date: 'Aug 2024',
      isCached: true, overCount: 5, underCount: 1,
      maps: [
        { map: 'Split', kills: 23, line: 19.5 },
        { map: 'Fracture', kills: 24, line: 19.5 },
      ],
    },
  ]
  const dist = Array.from({ length: 15 }, (_, i) => {
    const k = i + 12
    return {
      kills: k,
      modelPct: parseFloat((Math.exp(-Math.pow(k - 21, 2) / 18) * 18).toFixed(2)),
      marketPct: parseFloat((Math.exp(-Math.pow(k - 19.5, 2) / 20) * 16).toFixed(2)),
    }
  })
  return { player, stats, agents, events, dist }
}

/* ─── Page ───────────────────────────────────────────────── */
function KillLinePage() {
  const { toasts, dismiss, toast } = useToast()
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult] = useState<ReturnType<typeof buildResult> | null>(null)
  const [lastQuery, setLastQuery] = useState<{ player: string; ms: number } | null>(null)

  const handleSearch = (data: SearchFormData) => {
    if (!data.player) return
    setIsLoading(true)
    setResult(null)
    const t0 = Date.now()
    setTimeout(() => {
      const r = buildResult(data.player)
      setResult(r)
      const ms = Date.now() - t0
      setLastQuery({ player: data.player, ms })
      setIsLoading(false)
      toast('success', 'Analysis complete', `${data.player} · ${ms}ms`)
    }, 1400)
  }

  return (
    <>
      <AppHeader activePage="/" />

      <div className="page-container" style={{ padding: '0 24px 3rem' }}>
        {/* Hero */}
        <div style={{ textAlign: 'center', padding: '3rem 0 2rem' }}>
          <h1
            className="font-display uppercase"
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 900,
              fontSize: 'clamp(2.5rem, 6vw, 5rem)',
              letterSpacing: '-0.02em',
              lineHeight: 1.05,
              color: '#ffffff',
              textShadow: '0 0 1px #F0E040',
              marginBottom: '1rem',
            }}
          >
            Thunder<span style={{ color: '#F0E040' }}>Edge</span>
          </h1>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.875rem', color: 'rgba(255,255,255,0.5)', maxWidth: 600, margin: '0 auto 2rem' }}>
            Valorant kill-line analytics powered by negative binomial modelling. Enter a player IGN,
            set the line, and get a mathematically grounded OVER / UNDER recommendation.
          </p>
        </div>

        {/* Search section */}
        <div style={{ marginBottom: '2rem' }}>
          <SearchForm
            onSubmit={handleSearch}
            isLoading={isLoading}
            lastQuery={lastQuery}
            placeholder="e.g. TenZ#NA1"
            submitLabel="Analyze Player"
          />
        </div>

        {/* Loading skeletons */}
        {isLoading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <SkeletonOverUnder />
            <SkeletonStatsGrid count={6} columns={3} />
            <SkeletonTable rows={5} cols={4} />
            <SkeletonEventCards count={3} />
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !result && (
          <div style={{ background: '#0a0a0a', border: '1px solid #27272a', borderRadius: 12 }}>
            <EmptyState />
          </div>
        )}

        {/* Results */}
        {!isLoading && result && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {/* Performance bar */}
            <div
              style={{
                background: '#0D0D0D',
                border: '1px solid rgba(240,224,64,0.15)',
                borderLeft: '3px solid #F0E040',
                padding: '0.875rem 1.5rem',
                display: 'flex',
                flexWrap: 'wrap',
                gap: '1.5rem',
                fontSize: '0.875rem',
                color: 'rgba(255,255,255,0.5)',
              }}
            >
              <span>
                Player:{' '}
                <span style={{ color: '#F0E040', fontFamily: 'var(--font-display)', fontWeight: 700 }}>
                  {result.player}
                </span>
              </span>
              <span>
                Model:{' '}
                <span style={{ color: '#F0E040', fontFamily: 'var(--font-display)', fontWeight: 700 }}>
                  Neg. Binomial
                </span>
              </span>
              <span>
                Sample:{' '}
                <span style={{ color: '#F0E040', fontFamily: 'var(--font-display)', fontWeight: 700 }}>
                  47 maps
                </span>
              </span>
              <span style={{ marginLeft: 'auto', color: '#22c55e' }}>✓ Cached</span>
            </div>

            {/* Two-column results grid */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(0, 58%) minmax(0, 42%)',
                gap: '1.5rem',
              }}
              className="result-grid"
            >
              {/* Left column */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                <OverUnderDisplay overPct={63.8} underPct={36.2} sampleSize={47} killLine={19.5} />
                <RecommendationCard
                  type="BET_OVER"
                  ev={0.092}
                  confidence="HIGH"
                  reason="Model mean 21.4 exceeds market-implied mean 19.5 by 9.7%. Positive EV across all line scenarios."
                />
                <StatsGrid stats={result.stats} columns={3} />
              </div>

              {/* Right column */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                <DistributionChart
                  data={result.dist}
                  killLine={19.5}
                  modelOverPct={63.8}
                  marketOverPct={54.6}
                />
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {result.events.map((ev) => (
                    <EventCard key={ev.id} {...ev} />
                  ))}
                </div>
              </div>
            </div>

            {/* Agent breakdown — full width */}
            <div>
              <h3
                style={{
                  fontFamily: 'var(--font-display)',
                  fontWeight: 700,
                  fontSize: '1rem',
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  color: 'rgba(255,255,255,0.4)',
                  marginBottom: '0.75rem',
                }}
              >
                Agent Breakdown
              </h3>
              <DataTable<AgentRow>
                columns={AGENT_COLS}
                data={result.agents}
                filterPlaceholder="Filter agents..."
                filterKey="agent"
              />
            </div>
          </div>
        )}
      </div>

      {/* Responsive grid override */}
      <style>{`
        @media (max-width: 768px) {
          .result-grid { grid-template-columns: 1fr !important; }
        }
      `}</style>

      <ToastProvider toasts={toasts} onDismiss={dismiss} />
    </>
  )
}

export default function Page() {
  return <KillLinePage />
}
