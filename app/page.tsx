'use client'

import { useState, useRef } from 'react'
import { Loader2 } from 'lucide-react'
import { AppHeader } from '@/components/app-header'
import { OverUnderDisplay } from '@/components/over-under-display'
import { StatsGrid, type StatCardData } from '@/components/stats-grid'
import { DataTable, type Column } from '@/components/data-table'
import { RecommendationCard } from '@/components/recommendation-card'
import { DistributionChart } from '@/components/distribution-chart'
import { CollapsibleSection } from '@/components/collapsible-section'
import { API_BASE } from '@/lib/api'

const ACCENT = '#F0E040'

// ─── Types ────────────────────────────────────────────────────────────────────

interface EventDetail {
  event_name: string
  map_kills: number[]
  event_over: number
  event_under: number
  event_maps: number
  cached: boolean
  kpr?: number
  rounds?: number
  is_recent?: boolean
}

interface Analysis {
  player_ign: string
  team: string
  kill_line: number
  over_percentage: number
  under_percentage: number
  over_count: number
  under_count: number
  total_maps: number
  events_analyzed: number
  classification: string
  recommendation: string
  confidence: string
  total_kpr: number
  weighted_kpr: number
  rounds_needed: number
  total_rounds?: number
  event_details: EventDetail[]
  matchup_adjusted_probabilities?: {
    p_over: number
    p_under: number
    team_win_prob: number
    mu_base: number
    mu_adjusted: number
    multiplier: number
    input_method: string
  }
  all_map_kills?: number[]
}

interface AgentStat {
  agent: string
  maps: number
  avg_kills: number
  over_count?: number
  under_count?: number
  over_pct?: number
}

interface MapStat {
  map_name: string
  times_played: number
  avg_kills_per_map: number
  kd_ratio?: number
  avg_acs?: number
  avg_adr?: number
  avg_kast?: number
}

interface EdgeData {
  edge: {
    recommended: string
    ev_over: number
    ev_under: number
    prob_edge_over: number
    prob_edge_under: number
    roi_over_pct: number
    roi_under_pct: number
  }
  model: { p_over: number; p_under: number; mu: number }
  market: { p_over_vigfree: number; p_under_vigfree: number; mu_implied: number }
  player: { confidence: string; sample_size: number }
  visualization: { x: number[]; model_pmf: number[]; market_pmf: number[] }
}

interface Result {
  analysis: Analysis
  agentStats: AgentStat[]
  mapStats: MapStat[]
  edgeData: EdgeData | null
  elapsed: string
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function classificationToType(cls?: string): 'BET_OVER' | 'BET_UNDER' | 'NO_BET' {
  if (!cls) return 'NO_BET'
  const l = cls.toLowerCase()
  if (l.includes('underpriced')) return 'BET_OVER'
  if (l.includes('overpriced')) return 'BET_UNDER'
  return 'NO_BET'
}

function parseConfidence(c?: string): 'HIGH' | 'MED' | 'LOW' {
  if (!c) return 'LOW'
  const u = c.toUpperCase()
  if (u.startsWith('HIGH') || u.includes('STRONG')) return 'HIGH'
  if (u.startsWith('MEDIUM') || u.startsWith('MED') || u.includes('LEAN')) return 'MED'
  return 'LOW'
}

const AGENT_COLS: Column<AgentStat>[] = [
  { key: 'agent', label: 'Agent', sortable: true },
  { key: 'maps', label: 'Maps', sortable: true, align: 'right' },
  { key: 'avg_kills', label: 'Avg K', sortable: true, align: 'right', render: (v) => (v != null ? (v as number).toFixed(1) : '—') },
  { key: 'over_count', label: 'Over', sortable: true, align: 'right', render: (v) => (v != null ? String(v) : '—') },
  { key: 'under_count', label: 'Under', sortable: true, align: 'right', render: (v) => (v != null ? String(v) : '—') },
  {
    key: 'over_pct',
    label: 'Over %',
    sortable: true,
    align: 'right',
    render: (v) => {
      const n = v != null ? (v as number) : null
      if (n == null) return '—'
      return (
        <span style={{ color: n >= 55 ? '#22c55e' : n <= 45 ? '#ef4444' : '#a1a1aa' }}>
          {n.toFixed(1)}%
        </span>
      )
    },
  },
]

const MAP_COLS: Column<MapStat>[] = [
  { key: 'map_name', label: 'Map', sortable: true },
  { key: 'times_played', label: 'Times Played', sortable: true, align: 'right' },
  { key: 'avg_kills_per_map', label: 'Avg K/Map', sortable: true, align: 'right', render: (v) => (v != null ? (v as number).toFixed(1) : '—') },
  { key: 'kd_ratio', label: 'K/D', sortable: true, align: 'right', render: (v) => (v != null ? (v as number).toFixed(2) : '—') },
  { key: 'avg_acs', label: 'ACS', sortable: true, align: 'right', render: (v) => (v != null ? (v as number).toFixed(1) : '—') },
]

// ─── Kill chip row component ───────────────────────────────────────────────

function KillChips({ kills, line }: { kills: number[]; line: number }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', marginTop: '0.5rem' }}>
      {kills.map((k, i) => {
        const over = k > line
        return (
          <span
            key={i}
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: '0.875rem',
              padding: '0.3rem 0.6rem',
              border: `1px solid ${over ? 'rgba(34,197,94,0.4)' : 'rgba(239,68,68,0.4)'}`,
              background: over ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
              color: over ? '#22c55e' : '#ef4444',
            }}
          >
            {k} {over ? '✓' : '✗'}
          </span>
        )
      })}
    </div>
  )
}

// ─── Event timeline ────────────────────────────────────────────────────────

function EventTimeline({ events, line }: { events: EventDetail[]; line: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      {events.map((ev, i) => {
        const ou = ev.event_maps > 0 ? `O:${ev.event_over}/${ev.event_maps} U:${ev.event_under}/${ev.event_maps}` : ''
        return (
          <div
            key={i}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.75rem',
              padding: '0.5rem 0 0.5rem 1rem',
              marginLeft: 4,
              borderLeft: `2px solid ${ev.cached ? 'rgba(34,197,94,0.25)' : 'rgba(245,158,11,0.35)'}`,
              flexWrap: 'wrap',
            }}
          >
            <div
              style={{
                width: 8, height: 8, borderRadius: '50%',
                background: ev.cached ? '#22c55e' : '#f59e0b',
                flexShrink: 0, marginLeft: -20, marginTop: 4,
              }}
            />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                <span style={{ fontWeight: 600, color: '#e4e4e7', fontSize: '0.875rem' }}>{ev.event_name}</span>
                {ou && <span style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)' }}>{ou}</span>}
                <span
                  style={{
                    fontSize: '0.65rem', padding: '0.15rem 0.4rem', fontWeight: 700,
                    background: ev.cached ? 'rgba(34,197,94,0.15)' : 'rgba(245,158,11,0.15)',
                    color: ev.cached ? '#22c55e' : '#f59e0b',
                    border: `1px solid ${ev.cached ? 'rgba(34,197,94,0.3)' : 'rgba(245,158,11,0.3)'}`,
                    textTransform: 'uppercase', letterSpacing: '0.04em',
                  }}
                >
                  {ev.cached ? 'CACHED' : 'LIVE'}
                </span>
                {ev.is_recent && (
                  <span style={{ fontSize: '0.65rem', padding: '0.15rem 0.4rem', background: 'rgba(240,224,64,0.15)', color: ACCENT, border: `1px solid rgba(240,224,64,0.3)`, fontWeight: 700 }}>
                    RECENT
                  </span>
                )}
              </div>
              {ev.map_kills && ev.map_kills.length > 0 && (
                <KillChips kills={ev.map_kills} line={line} />
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── Matchup adjustment info ───────────────────────────────────────────────

function MatchupBox({ adj }: { adj: NonNullable<Analysis['matchup_adjusted_probabilities']> }) {
  return (
    <div style={{
      background: 'rgba(240,224,64,0.05)',
      border: '1px solid rgba(240,224,64,0.2)',
      borderLeft: `3px solid ${ACCENT}`,
      padding: '1rem 1.5rem',
    }}>
      <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'rgba(255,255,255,0.4)', marginBottom: '0.75rem' }}>
        Matchup Adjustment Applied
      </div>
      <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap', fontSize: '0.875rem' }}>
        <span style={{ color: 'rgba(255,255,255,0.5)' }}>Win Prob: <span style={{ color: ACCENT, fontFamily: 'var(--font-display)', fontWeight: 700 }}>{(adj.team_win_prob * 100).toFixed(1)}%</span></span>
        <span style={{ color: 'rgba(255,255,255,0.5)' }}>μ Base: <span style={{ color: '#e4e4e7', fontWeight: 600 }}>{adj.mu_base?.toFixed(2)}</span></span>
        <span style={{ color: 'rgba(255,255,255,0.5)' }}>μ Adj: <span style={{ color: '#e4e4e7', fontWeight: 600 }}>{adj.mu_adjusted?.toFixed(2)}</span></span>
        <span style={{ color: 'rgba(255,255,255,0.5)' }}>×<span style={{ color: '#e4e4e7', fontWeight: 600 }}>{adj.multiplier?.toFixed(3)}</span></span>
        <span style={{ color: 'rgba(255,255,255,0.5)' }}>Adj P(Over): <span style={{ color: '#22c55e', fontFamily: 'var(--font-display)', fontWeight: 700 }}>{(adj.p_over * 100).toFixed(1)}%</span></span>
      </div>
    </div>
  )
}

// ─── Edge section ─────────────────────────────────────────────────────────

function EdgeSection({ edge, line }: { edge: EdgeData; line: number }) {
  const e = edge?.edge
  const model = edge?.model
  const market = edge?.market
  const viz = edge?.visualization
  const recommended = e?.recommended ?? 'NO BET'
  const isOver = recommended === 'OVER'
  const isUnder = recommended === 'UNDER'
  const accentColor = isOver ? '#22c55e' : isUnder ? '#ef4444' : 'rgba(255,255,255,0.4)'

  const dist = (viz?.x ?? []).map((x, i) => ({
    kills: x,
    modelPct: +((viz?.model_pmf?.[i] ?? 0) * 100).toFixed(3),
    marketPct: +((viz?.market_pmf?.[i] ?? 0) * 100).toFixed(3),
  }))

  return (
    <div style={{ background: '#0D0D0D', border: '1px solid rgba(240,224,64,0.12)', borderLeft: `3px solid ${ACCENT}`, padding: '2rem', marginTop: '1.5rem' }}>
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '1rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'rgba(255,255,255,0.4)', marginBottom: '1.5rem' }}>
        Mathematical Edge Analysis
      </div>

      {/* Recommendation card */}
      <div style={{
        background: isOver ? 'rgba(34,197,94,0.05)' : isUnder ? 'rgba(239,68,68,0.05)' : 'rgba(255,255,255,0.03)',
        border: `1px solid ${isOver ? 'rgba(34,197,94,0.3)' : isUnder ? 'rgba(239,68,68,0.3)' : 'rgba(255,255,255,0.15)'}`,
        padding: '1.5rem', textAlign: 'center', marginBottom: '1.5rem',
      }}>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '1.5rem', color: accentColor, marginBottom: '0.5rem' }}>
          {recommended === 'NO BET' ? 'NO EDGE' : `BET ${recommended}`}
        </div>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '3rem', color: ACCENT, lineHeight: 1, margin: '0.75rem 0' }}>
          {recommended !== 'NO BET'
            ? `+${Math.max(e?.roi_over_pct ?? 0, e?.roi_under_pct ?? 0).toFixed(1)}% ROI`
            : `${Math.max(e?.ev_over ?? 0, e?.ev_under ?? 0).toFixed(3)} EV`}
        </div>
        <span style={{
          fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em',
          padding: '0.25rem 0.6rem',
          background: (edge?.player?.confidence === 'HIGH') ? 'rgba(34,197,94,0.15)' : (edge?.player?.confidence === 'MED') ? 'rgba(234,179,8,0.15)' : 'rgba(239,68,68,0.15)',
          color: (edge?.player?.confidence === 'HIGH') ? '#22c55e' : (edge?.player?.confidence === 'MED') ? '#eab308' : '#ef4444',
          border: `1px solid ${(edge?.player?.confidence === 'HIGH') ? 'rgba(34,197,94,0.3)' : (edge?.player?.confidence === 'MED') ? 'rgba(234,179,8,0.3)' : 'rgba(239,68,68,0.3)'}`,
        }}>
          {edge?.player?.confidence ?? 'LOW'} CONFIDENCE — {edge?.player?.sample_size ?? 0} maps
        </span>
      </div>

      {/* Metrics grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        {[
          { label: 'Model P(Over)', value: `${((model?.p_over ?? 0) * 100).toFixed(1)}%`, positive: (model?.p_over ?? 0) > 0.5 },
          { label: 'Market P(Over)', value: `${((market?.p_over_vigfree ?? 0) * 100).toFixed(1)}%`, positive: false },
          { label: 'Prob Edge Over', value: `${(e?.prob_edge_over ?? 0) > 0 ? '+' : ''}${((e?.prob_edge_over ?? 0) * 100).toFixed(1)}pp`, positive: (e?.prob_edge_over ?? 0) > 0 },
          { label: 'EV Over', value: `${(e?.ev_over ?? 0) > 0 ? '+' : ''}${(e?.ev_over ?? 0).toFixed(4)}`, positive: (e?.ev_over ?? 0) > 0 },
          { label: 'Model P(Under)', value: `${((model?.p_under ?? 0) * 100).toFixed(1)}%`, positive: (model?.p_under ?? 0) > 0.5 },
          { label: 'Market P(Under)', value: `${((market?.p_under_vigfree ?? 0) * 100).toFixed(1)}%`, positive: false },
          { label: 'Prob Edge Under', value: `${(e?.prob_edge_under ?? 0) > 0 ? '+' : ''}${((e?.prob_edge_under ?? 0) * 100).toFixed(1)}pp`, positive: (e?.prob_edge_under ?? 0) > 0 },
          { label: 'EV Under', value: `${(e?.ev_under ?? 0) > 0 ? '+' : ''}${(e?.ev_under ?? 0).toFixed(4)}`, positive: (e?.ev_under ?? 0) > 0 },
        ].map((m) => (
          <div key={m.label} style={{ background: '#0a0a0a', border: '1px solid rgba(240,224,64,0.1)', borderLeft: `3px solid ${ACCENT}`, padding: '1.25rem' }}>
            <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.12em', color: 'rgba(255,255,255,0.4)', marginBottom: '0.5rem' }}>{m.label}</div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '1.5rem', color: m.positive ? '#22c55e' : m.value.startsWith('-') ? '#ef4444' : '#e4e4e7' }}>{m.value}</div>
          </div>
        ))}
      </div>

      {/* Distribution chart */}
      {dist.length > 0 && (
        <div style={{ background: '#0a0a0a', border: '1px solid rgba(255,255,255,0.06)', padding: '1.5rem' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, textAlign: 'center', marginBottom: '1rem', color: '#e4e4e7', fontSize: '1rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Kill Distribution: Model vs Market
          </div>
          <DistributionChart data={dist} killLine={line} modelOverPct={(model?.p_over ?? 0) * 100} marketOverPct={(market?.p_over_vigfree ?? 0) * 100} />
        </div>
      )}

      {/* Comparison table */}
      <div style={{ overflowX: 'auto', marginTop: '1.5rem' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 280 }}>
          <thead>
            <tr>
              {['Side', 'Model Prob', 'Market Prob', 'Edge (pp)', 'EV', 'ROI %'].map((h) => (
                <th key={h} style={{ padding: '1rem', textAlign: 'left', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'rgba(255,255,255,0.4)', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[
              { side: 'OVER', modelP: model?.p_over ?? 0, mktP: market?.p_over_vigfree ?? 0, edgePP: e?.prob_edge_over ?? 0, ev: e?.ev_over ?? 0, roi: e?.roi_over_pct ?? 0 },
              { side: 'UNDER', modelP: model?.p_under ?? 0, mktP: market?.p_under_vigfree ?? 0, edgePP: e?.prob_edge_under ?? 0, ev: e?.ev_under ?? 0, roi: e?.roi_under_pct ?? 0 },
            ].map((row) => (
              <tr key={row.side} style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                <td style={{ padding: '1rem', fontWeight: 700, color: row.side === 'OVER' ? '#22c55e' : '#ef4444', fontFamily: 'var(--font-display)' }}>{row.side}</td>
                <td style={{ padding: '1rem', color: '#e4e4e7' }}>{(row.modelP * 100).toFixed(1)}%</td>
                <td style={{ padding: '1rem', color: '#e4e4e7' }}>{(row.mktP * 100).toFixed(1)}%</td>
                <td style={{ padding: '1rem', color: row.edgePP > 0 ? '#22c55e' : '#ef4444', fontWeight: 700 }}>{row.edgePP > 0 ? '+' : ''}{(row.edgePP * 100).toFixed(1)}pp</td>
                <td style={{ padding: '1rem', color: row.ev > 0 ? '#22c55e' : '#ef4444', fontWeight: 700 }}>{row.ev > 0 ? '+' : ''}{row.ev.toFixed(4)}</td>
                <td style={{ padding: '1rem', color: row.roi > 0 ? '#22c55e' : '#ef4444', fontWeight: 700 }}>{row.roi > 0 ? '+' : ''}{row.roi.toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Main page ─────────────────────────────────────────────────────────────

export default function HomePage() {
  const [playerInput, setPlayerInput] = useState('')
  const [killLine, setKillLine] = useState('15.5')
  const [overOdds, setOverOdds] = useState('')
  const [underOdds, setUnderOdds] = useState('')
  const [teamOdds, setTeamOdds] = useState('')
  const [oppOdds, setOppOdds] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<Result | null>(null)
  const playerRef = useRef<HTMLInputElement>(null)

  async function handleAnalyze() {
    const ign = playerInput.trim()
    if (!ign) return
    const line = parseFloat(killLine) || 15.5

    const teamQ = teamOdds && oppOdds ? `&team_odds=${teamOdds}&opp_odds=${oppOdds}` : ''

    setIsLoading(true)
    setError(null)
    setResult(null)

    try {
      const t0 = performance.now()
      // Use direct backend URL to avoid Next.js proxy 30s timeout (VLR scrape can take 40+ seconds)
      const base = API_BASE || 'http://localhost:5000'
      const res = await fetch(`${base}/api/player/${encodeURIComponent(ign)}?line=${line}${teamQ}`)
      const data = await res.json()
      if (!res.ok || data.error) throw new Error(data.error || 'API error')

      // Fetch edge data if odds provided
      let edgeData: EdgeData | null = null
      const parsedOver = parseFloat(overOdds)
      const parsedUnder = parseFloat(underOdds)
      if (!isNaN(parsedOver) && !isNaN(parsedUnder)) {
        try {
          const er = await fetch(`${base}/api/edge/${encodeURIComponent(ign)}?line=${line}&over_odds=${parsedOver}&under_odds=${parsedUnder}${teamQ}`)
          if (er.ok) {
            const ed = await er.json()
            if (ed.success) edgeData = ed
          }
        } catch { /* edge is optional */ }
      }

      const elapsed = ((performance.now() - t0) / 1000).toFixed(2)
      const agentStats = (data.agent_stats || []).map((a: Record<string, unknown>) => ({
        agent: a.agent,
        maps: a.maps ?? a.maps_played ?? 0,
        avg_kills: a.avg_kills ?? (a.maps_played && a.total_kills ? (a.total_kills as number) / (a.maps_played as number) : 0),
        over_count: a.over_count,
        under_count: a.under_count,
        over_pct: a.over_pct,
      }))
      const mapStats = (data.map_stats || []).map((m: Record<string, unknown>) => ({
        map_name: m.map_name,
        times_played: m.times_played ?? 0,
        avg_kills_per_map: m.avg_kills_per_map ?? 0,
        kd_ratio: m.kd_ratio,
        avg_acs: m.avg_acs,
        avg_adr: m.avg_adr,
        avg_kast: m.avg_kast,
      }))
      setResult({ analysis: data.analysis, agentStats, mapStats, edgeData, elapsed })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect to backend')
    } finally {
      setIsLoading(false)
    }
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      e.stopPropagation()
      handleAnalyze()
    }
  }

  const analysis = result?.analysis
  const edgeData = result?.edgeData

  // Build stats for StatsGrid from analysis (defensive: avoid "Cannot read properties of undefined")
  const stats: StatCardData[] = analysis ? [
    { label: 'Kill Line', value: analysis.kill_line ?? '—', delta: 'Thunderpick', semantic: 'neutral' },
    { label: 'Total KPR', value: (analysis.total_kpr ?? analysis.weighted_kpr ?? 0).toFixed(3), delta: 'Weighted by rounds', semantic: 'neutral' },
    { label: 'Weighted KPR', value: (analysis.weighted_kpr ?? 0).toFixed(3), delta: '1.5× recent event', semantic: 'neutral' },
    { label: 'Rounds Needed', value: (analysis.rounds_needed ?? 0).toFixed(1), delta: 'to hit line', semantic: 'neutral' },
    { label: 'Maps Analyzed', value: analysis.total_maps ?? 0, delta: `${analysis.events_analyzed ?? 0} events`, semantic: 'neutral' },
    { label: 'Confidence', value: analysis.confidence ?? '—', delta: 'Sample quality', semantic: parseConfidence(analysis?.confidence) === 'HIGH' ? 'positive' : parseConfidence(analysis?.confidence) === 'LOW' ? 'negative' : 'neutral' },
  ] : []

  // Determine recommendation type + EV
  const recType = analysis ? classificationToType(analysis.classification) : 'NO_BET'
  const recEV = edgeData?.edge
    ? (edgeData.edge.recommended === 'OVER' ? edgeData.edge.ev_over : edgeData.edge.recommended === 'UNDER' ? edgeData.edge.ev_under : 0)
    : 0
  const recConfidence = parseConfidence(edgeData?.player.confidence || analysis?.confidence)

  // Count cached/live events
  const cachedCount = analysis?.event_details?.filter((e) => e.cached).length ?? 0
  const liveCount = (analysis?.event_details?.length ?? 0) - cachedCount

  return (
    <>
      <AppHeader activePage="/" />

      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '0 24px 3rem' }}>

        {/* Hero */}
        <div style={{ textAlign: 'center', padding: '2.5rem 0 1.5rem' }}>
          <h1 style={{
            fontFamily: 'var(--font-display)', fontWeight: 900,
            fontSize: 'clamp(2.5rem, 6vw, 5rem)', letterSpacing: '-0.02em', lineHeight: 1.05,
            color: '#ffffff', marginBottom: '0.75rem', textTransform: 'uppercase',
          }}>
            Thunderpick <span style={{ color: ACCENT }}>Kill Line</span>
          </h1>
          <p style={{ fontSize: '0.875rem', color: 'rgba(255,255,255,0.5)', maxWidth: 600, margin: '0 auto' }}>
            Negative binomial kill-line analytics for VCT players — live data from VLR.gg
          </p>
        </div>

        {/* ── Command bar ──────────────────────────────────────────────────── */}
        <div style={{ background: '#0D0D0D', border: '1px solid rgba(240,224,64,0.15)', borderLeft: `3px solid ${ACCENT}`, marginBottom: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 1rem' }}>
            <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '1.2rem', color: ACCENT, flexShrink: 0 }}>{'>'}</span>
            <input
              ref={playerRef}
              type="text"
              value={playerInput}
              onChange={(e) => setPlayerInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="enter player ign and press enter..."
              style={{
                flex: 1, background: 'transparent', border: 'none', outline: 'none',
                fontFamily: "'Courier New', monospace", fontSize: '1.1rem', color: '#ffffff',
              }}
            />
            <button
              type="button"
              onClick={handleAnalyze}
              disabled={isLoading || !playerInput.trim()}
              style={{
                fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.85rem',
                textTransform: 'uppercase', letterSpacing: '0.06em',
                padding: '0.4rem 1.1rem',
                background: isLoading || !playerInput.trim() ? 'rgba(240,224,64,0.4)' : ACCENT,
                color: '#000',
                border: 'none', borderRadius: 0, cursor: isLoading || !playerInput.trim() ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0,
              }}
            >
              {isLoading ? <><Loader2 size={12} className="animate-spin" /> Analyzing</> : 'Analyze'}
            </button>
          </div>

          {/* Secondary params bar */}
          <div style={{
            display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center',
            padding: '0.5rem 1rem',
            borderTop: '1px solid rgba(255,255,255,0.06)',
            fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)',
          }}>
            {[
              { label: 'Kill Line', val: killLine, set: setKillLine, type: 'number', step: '0.5', placeholder: '15.5', width: 80 },
              { label: 'Over Odds', val: overOdds, set: setOverOdds, type: 'text', placeholder: '-110', width: 80 },
              { label: 'Under Odds', val: underOdds, set: setUnderOdds, type: 'text', placeholder: '-110', width: 80 },
              { label: 'Team Odds', val: teamOdds, set: setTeamOdds, type: 'number', placeholder: '1.62', width: 80 },
              { label: 'Opp Odds', val: oppOdds, set: setOppOdds, type: 'number', placeholder: '2.30', width: 80 },
            ].map((f) => (
              <span key={f.label} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                {f.label}:
                <input
                  type={f.type}
                  step={(f as { step?: string }).step}
                  value={f.val}
                  onChange={(e) => f.set(e.target.value)}
                  onKeyDown={handleKey}
                  placeholder={f.placeholder}
                  style={{
                    width: f.width, padding: '0.25rem 0.5rem', fontSize: '0.8rem',
                    background: '#0a0a0a', border: '1px solid rgba(255,255,255,0.12)',
                    color: '#fff', outline: 'none', borderRadius: 0,
                  }}
                />
              </span>
            ))}
          </div>
        </div>

        {/* Error */}
        {error && (
          <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444', padding: '1rem 1.5rem', marginTop: '1rem', fontWeight: 600 }}>
            ✗ {error}
          </div>
        )}

        {/* Loading skeleton */}
        {isLoading && (
          <div style={{ marginTop: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {[80, 200, 120].map((h, i) => (
              <div key={i} style={{ height: h, background: 'linear-gradient(90deg,#1a1a1a 25%,#252525 50%,#1a1a1a 75%)', backgroundSize: '200% 100%', animation: 'shimmer 1.4s infinite' }} />
            ))}
            <style>{`@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}`}</style>
          </div>
        )}


        {/* Backend returned an analysis-level error (insufficient data etc.) */}
        {!isLoading && result && analysis && !analysis.player_ign && (
          <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444', padding: '1rem 1.5rem', marginTop: '1rem', fontWeight: 600 }}>
            ✗ {(analysis as unknown as Record<string, string>).error || 'Insufficient data for this player'}
          </div>
        )}

        {/* ── Results ──────────────────────────────────────────────────────── */}
        {!isLoading && result && analysis && analysis.player_ign && (
          <div style={{ marginTop: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

            {/* Performance bar */}
            <div style={{
              background: '#0D0D0D', border: '1px solid rgba(240,224,64,0.12)', borderLeft: `3px solid ${ACCENT}`,
              padding: '0.875rem 1.5rem', display: 'flex', flexWrap: 'wrap', gap: '1.5rem',
              fontSize: '0.875rem', color: 'rgba(255,255,255,0.5)',
            }}>
              <span><strong style={{ color: '#fff' }}>{analysis.player_ign}</strong> · {analysis.team || 'Unknown Team'}</span>
              <span>Query Time: <span style={{ color: ACCENT, fontFamily: 'var(--font-display)', fontWeight: 700 }}>{result.elapsed}s</span></span>
              <span>Events: <span style={{ color: '#22c55e', fontFamily: 'var(--font-display)', fontWeight: 700 }}>{cachedCount} cached</span> / <span style={{ color: '#f59e0b', fontFamily: 'var(--font-display)', fontWeight: 700 }}>{liveCount} live</span></span>
              <span>Maps: <span style={{ color: ACCENT, fontFamily: 'var(--font-display)', fontWeight: 700 }}>{analysis.total_maps ?? 0}</span></span>
              {edgeData && <span style={{ marginLeft: 'auto', color: '#22c55e', fontWeight: 600 }}>✓ Edge data loaded</span>}
            </div>

            {/* Collapsible data sections */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>

              <CollapsibleSection title="Recommendation" defaultOpen accentColor={recType === 'BET_OVER' ? '#22c55e' : recType === 'BET_UNDER' ? '#ef4444' : ACCENT}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
                  <span style={{
                    fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.75rem',
                    padding: '0.35rem 0.75rem', textTransform: 'uppercase', letterSpacing: '0.08em',
                    background: recType === 'BET_OVER' ? 'rgba(34,197,94,0.12)' : recType === 'BET_UNDER' ? 'rgba(239,68,68,0.12)' : 'rgba(240,224,64,0.12)',
                    color: recType === 'BET_OVER' ? '#22c55e' : recType === 'BET_UNDER' ? '#ef4444' : ACCENT,
                    border: `1px solid ${recType === 'BET_OVER' ? 'rgba(34,197,94,0.3)' : recType === 'BET_UNDER' ? 'rgba(239,68,68,0.3)' : 'rgba(240,224,64,0.3)'}`,
                  }}>
                    {analysis.classification ?? '—'}
                  </span>
                </div>
                <RecommendationCard
                  type={recType}
                  ev={recEV ?? 0}
                  confidence={recConfidence}
                  reason={analysis.recommendation ?? undefined}
                />
              </CollapsibleSection>

              <CollapsibleSection title="Empirical Over/Under Percentages" accentColor={ACCENT}>
                <OverUnderDisplay
                  overPct={analysis.over_percentage ?? 0}
                  underPct={analysis.under_percentage ?? 0}
                  sampleSize={analysis.total_maps ?? 0}
                  killLine={analysis.kill_line}
                />
                <div style={{ fontSize: '0.875rem', color: 'rgba(255,255,255,0.4)', textAlign: 'center', marginTop: '1rem' }}>
                  Based on {analysis.total_maps ?? 0} maps across {analysis.events_analyzed ?? 0} VCT events
                </div>
              </CollapsibleSection>

              <CollapsibleSection title="Expected Rounds" accentColor={ACCENT}>
                <div style={{ background: '#0a0a0a', border: '1px solid rgba(240,224,64,0.1)', padding: '1.5rem', textAlign: 'center' }}>
                  <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.12em', color: 'rgba(255,255,255,0.4)', marginBottom: '0.75rem' }}>
                    Formula: Kill Line / Weighted KPR = Rounds Needed
                  </div>
                  <div style={{ fontFamily: 'monospace', fontSize: '1rem', color: ACCENT, margin: '0.5rem 0' }}>
                    {analysis.kill_line ?? '—'} / {(analysis.weighted_kpr ?? 0).toFixed(3)} =
                  </div>
                  <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '2.5rem', color: '#fff' }}>
                    {(analysis.rounds_needed ?? 0).toFixed(1)} rounds
                  </div>
                </div>
              </CollapsibleSection>

              <CollapsibleSection title="Key Stats" accentColor={ACCENT}>
                <StatsGrid stats={stats} columns={3} />
              </CollapsibleSection>

              {analysis.matchup_adjusted_probabilities && (
                <CollapsibleSection title="Matchup Adjustment" accentColor={ACCENT}>
                  <MatchupBox adj={analysis.matchup_adjusted_probabilities} />
                </CollapsibleSection>
              )}

              <CollapsibleSection title="Agent and Map Breakdown" accentColor={ACCENT}>
                {result.agentStats && result.agentStats.length > 0 ? (
                  <>
                    <h4 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)', marginBottom: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Agent Performance</h4>
                    <DataTable<AgentStat>
                      columns={AGENT_COLS}
                      data={result.agentStats}
                      filterPlaceholder="Filter agents..."
                      filterKey="agent"
                    />
                  </>
                ) : (
                  <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.875rem', marginBottom: '1rem' }}>No agent data available. Populate the database with match details to see per-agent stats.</p>
                )}
                {result.mapStats && result.mapStats.length > 0 ? (
                  <>
                    <h4 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)', marginTop: '1.5rem', marginBottom: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Map Performance</h4>
                    <DataTable<MapStat>
                      columns={MAP_COLS}
                      data={result.mapStats}
                      filterPlaceholder="Filter maps..."
                      filterKey="map_name"
                    />
                  </>
                ) : (
                  <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.875rem' }}>No map data available. Populate the database with match details to see per-map stats.</p>
                )}
              </CollapsibleSection>

              {analysis.event_details && analysis.event_details.length > 0 && (
                <CollapsibleSection title="VCT Events Timeline" accentColor={ACCENT}>
                  <p style={{ fontSize: '0.875rem', color: 'rgba(255,255,255,0.5)', margin: '0 0 1rem' }}>
                    Total KPR: {(analysis.total_kpr ?? analysis.weighted_kpr ?? 0).toFixed(3)} · Weighted KPR: {(analysis.weighted_kpr ?? 0).toFixed(3)} · Rounds: {analysis.total_rounds ?? '—'}
                  </p>
                  <EventTimeline events={analysis.event_details} line={analysis.kill_line ?? 15.5} />
                </CollapsibleSection>
              )}

              {edgeData && (
                <CollapsibleSection title="Monte-Carlo & Mathematical Edge Analysis" accentColor={ACCENT}>
                  <EdgeSection edge={edgeData} line={analysis.kill_line ?? 15.5} />
                </CollapsibleSection>
              )}
            </div>
          </div>
        )}
      </div>

    </>
  )
}
