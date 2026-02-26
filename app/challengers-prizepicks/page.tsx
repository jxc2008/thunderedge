'use client'

import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { AppHeader } from '@/components/app-header'
import { OverUnderDisplay } from '@/components/over-under-display'
import { StatsGrid, type StatCardData } from '@/components/stats-grid'
import { DataTable, type Column } from '@/components/data-table'
import { EventCard, type EventCardData } from '@/components/event-card'
import { RecommendationCard } from '@/components/recommendation-card'
import { DistributionChart } from '@/components/distribution-chart'
import { EmptyState } from '@/components/ux-patterns'

const ACCENT = '#6D28D9'
const SECONDARY = '#10B981'

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

function buildResult(player: string, line: number) {
  const stats: StatCardData[] = [
    { label: 'Model Mean', value: (line + 1.7).toFixed(1), delta: 'kills / map', semantic: 'positive' },
    { label: 'PP Line', value: line.toFixed(1), delta: 'kill line', semantic: 'neutral' },
    { label: 'Sample Size', value: 28, delta: 'maps analyzed', semantic: 'neutral' },
    { label: 'K/Map Avg', value: (line + 1.3).toFixed(1), delta: 'last 12 maps', semantic: 'neutral' },
    { label: 'Edge', value: '+5.9pp', delta: 'vs market', semantic: 'positive' },
    { label: 'VLR Rating', value: '1.18', delta: 'challengers rating', semantic: 'neutral' },
  ]
  const agents: AgentRow[] = [
    { agent: 'Raze', maps: 8, killsPerMap: line + 2.4, overPct: 62.5 },
    { agent: 'Jett', maps: 7, killsPerMap: line + 1.1, overPct: 57.1 },
    { agent: 'Neon', maps: 6, killsPerMap: line + 0.3, overPct: 50.0 },
    { agent: 'Phoenix', maps: 5, killsPerMap: line - 1.2, overPct: 40.0 },
    { agent: 'Reyna', maps: 2, killsPerMap: line - 2.5, overPct: 50.0 },
  ]
  const events: EventCardData[] = [
    {
      id: '1', eventName: 'VCT Challengers Americas 2025', date: 'Feb 2025',
      isCached: true, overCount: 4, underCount: 2, defaultOpen: true,
      maps: [
        { map: 'Ascent', kills: Math.round(line + 2), line },
        { map: 'Bind', kills: Math.round(line + 4), line },
        { map: 'Pearl', kills: Math.round(line - 1), line },
      ],
    },
    {
      id: '2', eventName: 'VCT Challengers Americas — Kickoff', date: 'Jan 2025',
      isCached: true, overCount: 3, underCount: 2,
      maps: [
        { map: 'Haven', kills: Math.round(line + 1), line },
        { map: 'Icebox', kills: Math.round(line - 2), line },
      ],
    },
  ]
  const dist = Array.from({ length: 15 }, (_, i) => {
    const k = i + Math.floor(line) - 4
    return {
      kills: k,
      modelPct: parseFloat((Math.exp(-Math.pow(k - (line + 1.7), 2) / 18) * 17).toFixed(2)),
      marketPct: parseFloat((Math.exp(-Math.pow(k - line, 2) / 20) * 15).toFixed(2)),
    }
  })
  return { player, line, stats, agents, events, dist }
}

const inputStyle: React.CSSProperties = {
  background: 'rgba(9,9,18,0.8)',
  border: '1px solid rgba(109,40,217,0.3)',
  color: '#ffffff',
  padding: '0.75rem 1rem',
  fontSize: '0.875rem',
  fontFamily: 'inherit',
  outline: 'none',
  borderRadius: 0,
  width: '100%',
  transition: 'border-color 0.15s',
}

const labelStyle: React.CSSProperties = {
  fontSize: '0.7rem',
  fontWeight: 500,
  textTransform: 'uppercase' as const,
  letterSpacing: '0.12em',
  color: 'rgba(255,255,255,0.4)',
  display: 'block',
  marginBottom: '0.5rem',
}

export default function ChallengersPrizePicksPage() {
  const [playerInput, setPlayerInput] = useState('')
  const [lineInput, setLineInput] = useState('16.5')
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult] = useState<ReturnType<typeof buildResult> | null>(null)

  const handleAnalyze = () => {
    if (!playerInput.trim()) return
    const l = parseFloat(lineInput) || 16.5
    setIsLoading(true)
    setResult(null)
    setTimeout(() => {
      setResult(buildResult(playerInput.trim(), l))
      setIsLoading(false)
    }, 1200)
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleAnalyze()
  }

  return (
    <>
      <AppHeader activePage="/challengers-prizepicks" />

      <div className="page-container" style={{ padding: '0 24px 3rem' }}>
        {/* Hero */}
        <div style={{ textAlign: 'center', padding: '3rem 0 2rem' }}>
          <h1
            className="font-display uppercase"
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 900,
              fontSize: 'clamp(2rem, 5vw, 4rem)',
              letterSpacing: '-0.02em',
              lineHeight: 1.05,
              color: '#ffffff',
              marginBottom: '1rem',
            }}
          >
            Challengers <span style={{ color: ACCENT }}>×</span>{' '}
            Prize<span style={{ color: SECONDARY }}>Picks</span>
          </h1>
          <p style={{ fontSize: '0.875rem', color: 'rgba(255,255,255,0.5)', maxWidth: 600, margin: '0 auto 2rem' }}>
            PrizePicks kill-line analytics for VCT Challengers circuit players — combining circuit-specific modelling with platform pricing.
          </p>
        </div>

        {/* Search section */}
        <div
          style={{
            background: 'rgba(109,40,217,0.06)',
            border: '1px solid rgba(109,40,217,0.2)',
            borderLeft: `3px solid ${ACCENT}`,
            padding: '2rem',
            marginBottom: '2rem',
          }}
        >
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end' }}>
            <div style={{ flex: '1 1 200px' }}>
              <label style={labelStyle}>Challengers Player IGN</label>
              <input
                type="text"
                value={playerInput}
                onChange={(e) => setPlayerInput(e.target.value)}
                onKeyDown={handleKey}
                placeholder="e.g. s0m#NA1"
                style={inputStyle}
              />
            </div>
            <div style={{ flex: '0 1 160px' }}>
              <label style={labelStyle}>PrizePicks Line</label>
              <input
                type="number"
                step="0.5"
                value={lineInput}
                onChange={(e) => setLineInput(e.target.value)}
                onKeyDown={handleKey}
                placeholder="16.5"
                style={inputStyle}
              />
            </div>
            <button
              onClick={handleAnalyze}
              disabled={isLoading || !playerInput.trim()}
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 700,
                fontSize: '0.9rem',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                padding: '0.75rem 2rem',
                background: isLoading || !playerInput.trim() ? 'rgba(109,40,217,0.4)' : ACCENT,
                color: '#ffffff',
                border: 'none',
                borderRadius: 0,
                cursor: isLoading || !playerInput.trim() ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                flexShrink: 0,
                alignSelf: 'flex-end',
              }}
            >
              {isLoading ? <><Loader2 size={14} className="animate-spin" /> Analyzing...</> : 'Analyze Pick'}
            </button>
          </div>
        </div>

        {/* Loading */}
        {isLoading && (
          <div style={{ textAlign: 'center', padding: '3rem', color: '#71717a' }}>
            <div style={{
              width: 40, height: 40,
              border: '3px solid #27272a',
              borderTop: `3px solid ${ACCENT}`,
              borderRadius: '50%',
              animation: 'spin 0.8s linear infinite',
              margin: '0 auto 1rem',
            }} />
            <p style={{ fontWeight: 600, color: '#e4e4e7', marginBottom: 4 }}>Analyzing Pick</p>
            <p style={{ fontSize: '0.875rem' }}>Running Challengers model against PrizePicks line...</p>
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
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
                background: 'rgba(109,40,217,0.06)',
                border: '1px solid rgba(109,40,217,0.15)',
                borderLeft: `3px solid ${ACCENT}`,
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
                <span style={{ color: ACCENT, fontFamily: 'var(--font-display)', fontWeight: 700 }}>
                  {result.player}
                </span>
              </span>
              <span>
                Line:{' '}
                <span style={{ color: SECONDARY, fontFamily: 'var(--font-display)', fontWeight: 700 }}>
                  {result.line.toFixed(1)} kills
                </span>
              </span>
              <span>
                Circuit:{' '}
                <span style={{ color: ACCENT, fontFamily: 'var(--font-display)', fontWeight: 700 }}>
                  Challengers
                </span>
              </span>
              <span>
                Platform:{' '}
                <span style={{ color: SECONDARY, fontFamily: 'var(--font-display)', fontWeight: 700 }}>
                  PrizePicks
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
              {/* Left */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                <OverUnderDisplay overPct={58.7} underPct={41.3} sampleSize={28} killLine={result.line} />
                <RecommendationCard
                  type="BET_OVER"
                  ev={0.059}
                  confidence="MED"
                  reason={`Model mean ${(result.line + 1.7).toFixed(1)} exceeds PrizePicks line ${result.line.toFixed(1)} for Challengers circuit player.`}
                />
                <StatsGrid stats={result.stats} columns={3} />
              </div>

              {/* Right */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                <DistributionChart
                  data={result.dist}
                  killLine={result.line}
                  modelOverPct={58.7}
                  marketOverPct={51.4}
                />
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {result.events.map((ev) => (
                    <EventCard key={ev.id} {...ev} />
                  ))}
                </div>
              </div>
            </div>

            {/* Agent breakdown */}
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

      <style>{`
        @media (max-width: 768px) {
          .result-grid { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </>
  )
}
