'use client'

import { useState } from 'react'
import { Search, Loader2, ChevronDown, ChevronRight, TrendingUp, TrendingDown } from 'lucide-react'
import { AppHeader } from '@/components/app-header'
import { OverUnderDisplay } from '@/components/over-under-display'
import { StatsGrid, type StatCardData } from '@/components/stats-grid'

/* ─── API response types ─────────────────────────────────── */
interface EventDetail {
  event_name: string
  map_kills: number[]
  event_maps: number
  event_over: number
  event_under: number
  cached: boolean
}

interface MarginStats {
  total_maps: number
  total_wins: number
  total_losses: number
  wins_over_pct: number
  wins_under_pct: number
  losses_over_pct: number
  losses_under_pct: number
  wins: { close: { count: number; over_pct: number }; regular: { count: number; over_pct: number }; blowout: { count: number; over_pct: number } }
  losses: { close: { count: number; over_pct: number }; regular: { count: number; over_pct: number }; blowout: { count: number; over_pct: number } }
}

interface MatchupAdjustedProbabilities {
  p_over: number
  p_under: number
  team_win_prob: number
  mu_base: number
  mu_adjusted: number
  multiplier: number
  input_method: string
}

interface PlayerAnalysis {
  player_ign: string
  team: string
  kill_line: number
  over_percentage: number
  under_percentage: number
  over_count: number
  under_count: number
  total_maps: number
  events_analyzed: number
  total_kpr: number
  weighted_kpr: number
  rounds_needed: number
  classification: string
  recommendation: string
  confidence: string
  all_map_kills: number[]
  event_details: EventDetail[]
  margin_stats?: MarginStats
  matchup_adjusted_probabilities?: MatchupAdjustedProbabilities
}

interface AgentStat {
  agent: string
  maps: number
  avg_kills: number
  over_count: number
  under_count: number
}

interface MapStat {
  map: string
  maps: number
  avg_kills: number
  over_count: number
  under_count: number
}

interface EdgeData {
  success: boolean
  edge: {
    recommended: string
    ev_over: number
    ev_under: number
    best_ev: number
    roi_over_pct: number
    roi_under_pct: number
    prob_edge_over: number
    prob_edge_under: number
  }
  model: { mu: number; var: number; dist: string; p_over: number; p_under: number }
  market: { p_over_vigfree: number; p_under_vigfree: number; vig_percentage: number; mu_implied: number }
  player: { sample_size: number; confidence: string }
}

/* ─── Event card ─────────────────────────────────────────── */
function EventRow({
  event,
  killLine,
  defaultOpen = false,
}: {
  event: EventDetail
  killLine: number
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div
      className="rounded-[8px] border overflow-hidden"
      style={{
        borderColor: event.cached ? 'rgba(34,197,94,0.25)' : 'rgba(245,158,11,0.25)',
        background: '#0a0a0a',
        borderLeft: `3px solid ${event.cached ? '#22c55e' : '#f59e0b'}`,
      }}
    >
      <button
        className="w-full flex items-center gap-3 px-4 py-2.5 text-left"
        onClick={() => setOpen((v) => !v)}
        style={{ background: open ? '#111111' : 'transparent' }}
      >
        <span style={{ color: '#52525b' }}>
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </span>
        <span className="text-sm font-medium flex-1 min-w-0 truncate" style={{ color: '#e4e4e7' }}>
          {event.event_name}
        </span>
        {event.event_maps > 0 && (
          <span className="text-[0.7rem] shrink-0" style={{ color: '#52525b' }}>
            O:{event.event_over}/{event.event_maps} &nbsp; U:{event.event_under}/{event.event_maps}
          </span>
        )}
        <span
          className="text-[0.6rem] font-semibold uppercase tracking-wider px-1.5 py-0.5 shrink-0"
          style={{
            background: event.cached ? 'rgba(34,197,94,0.12)' : 'rgba(245,158,11,0.12)',
            color: event.cached ? '#22c55e' : '#f59e0b',
            border: `1px solid ${event.cached ? 'rgba(34,197,94,0.25)' : 'rgba(245,158,11,0.25)'}`,
          }}
        >
          {event.cached ? 'CACHED' : 'LIVE'}
        </span>
      </button>
      {open && event.map_kills.length > 0 && (
        <div className="px-4 pb-3 pt-1 border-t flex flex-wrap gap-2" style={{ borderColor: '#1a1a1a' }}>
          {event.map_kills.map((k, i) => {
            const isOver = k > killLine
            return (
              <span
                key={i}
                className="text-[0.8rem] font-bold px-2.5 py-1 tabular-nums"
                style={{
                  background: isOver ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
                  color: isOver ? '#22c55e' : '#ef4444',
                  border: `1px solid ${isOver ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                }}
              >
                {k} {isOver ? '✓' : '✗'}
              </span>
            )
          })}
        </div>
      )}
    </div>
  )
}

/* ─── Edge summary ───────────────────────────────────────── */
function EdgeSummary({ edge }: { edge: EdgeData }) {
  const rec = edge.edge.recommended
  const isBetOver = rec === 'OVER'
  const isBetUnder = rec === 'UNDER'
  const accentColor = isBetOver ? '#22c55e' : isBetUnder ? '#ef4444' : '#71717a'
  const bestEV = edge.edge.best_ev * 100

  return (
    <div
      className="rounded-[10px] border p-4 flex items-center justify-between gap-4 flex-wrap"
      style={{
        background: '#0a0a0a',
        borderColor: '#27272a',
        borderLeft: `4px solid ${accentColor}`,
      }}
    >
      <div>
        <p className="text-[0.65rem] uppercase tracking-[0.1em]" style={{ color: '#71717a' }}>
          Edge Recommendation
        </p>
        <p className="font-bold mt-0.5" style={{ fontSize: '1.25rem', color: accentColor }}>
          {rec === 'NO BET' ? 'NO BET' : `BET ${rec}`}
        </p>
        {edge.edge.recommended !== 'NO BET' && (
          <p className="text-[0.75rem] mt-0.5" style={{ color: '#a1a1aa' }}>
            Model: {(edge.model.p_over * 100).toFixed(1)}% over vs market: {(edge.market.p_over_vigfree * 100).toFixed(1)}%
          </p>
        )}
      </div>
      <div className="text-right">
        <p
          className="font-extrabold tabular-nums"
          style={{ fontSize: '1.75rem', color: bestEV >= 0 ? '#22c55e' : '#ef4444' }}
        >
          {bestEV >= 0 ? '+' : ''}{bestEV.toFixed(1)}%
        </p>
        <p className="text-[0.65rem] uppercase tracking-wide mt-0.5" style={{ color: '#52525b' }}>
          Expected ROI
        </p>
      </div>
    </div>
  )
}

/* ─── Main page ──────────────────────────────────────────── */
export default function PlayerPage() {
  const [form, setForm] = useState({
    player: '',
    killLine: '15.5',
    overOdds: '',
    underOdds: '',
    teamOdds: '',
    oppOdds: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [analysis, setAnalysis] = useState<PlayerAnalysis | null>(null)
  const [agentStats, setAgentStats] = useState<AgentStat[]>([])
  const [mapStats, setMapStats] = useState<MapStat[]>([])
  const [edgeData, setEdgeData] = useState<EdgeData | null>(null)
  const [elapsed, setElapsed] = useState<number | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const ign = form.player.trim()
    if (!ign) { setError('Please enter a player IGN'); return }
    const killLine = parseFloat(form.killLine)
    if (!form.killLine || killLine <= 0) { setError('Please enter a valid kill line'); return }

    setLoading(true)
    setError(null)
    setAnalysis(null)
    setEdgeData(null)

    const teamOdds = parseFloat(form.teamOdds)
    const oppOdds = parseFloat(form.oppOdds)
    const matchupQuery = (!isNaN(teamOdds) && !isNaN(oppOdds))
      ? `&team_odds=${teamOdds}&opp_odds=${oppOdds}`
      : ''

    try {
      const t0 = performance.now()
      const res = await fetch(`/api/player/${encodeURIComponent(ign)}?line=${killLine}${matchupQuery}`)
      const data = await res.json()
      const ms = performance.now() - t0
      setElapsed(ms / 1000)

      if (data.error) { setError(data.error); return }

      setAnalysis(data.analysis)
      setAgentStats(data.agent_stats || [])
      setMapStats(data.map_stats || [])

      // Optionally fetch edge analysis if odds are provided
      const overOdds = parseFloat(form.overOdds)
      const underOdds = parseFloat(form.underOdds)
      if (!isNaN(overOdds) && !isNaN(underOdds)) {
        try {
          const edgeRes = await fetch(
            `/api/edge/${encodeURIComponent(ign)}?line=${killLine}&over_odds=${overOdds}&under_odds=${underOdds}${matchupQuery}`
          )
          if (edgeRes.ok) {
            const ed = await edgeRes.json()
            setEdgeData(ed)
          }
        } catch {
          // edge analysis is optional — ignore failures
        }
      }
    } catch (err) {
      setError('Error connecting to server: ' + (err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  /* build stat cards from analysis */
  function buildStats(a: PlayerAnalysis): StatCardData[] {
    return [
      { label: 'Kill Line', value: a.kill_line, delta: 'target', semantic: 'neutral' },
      { label: 'Total KPR', value: a.total_kpr ?? a.weighted_kpr, delta: 'kills per round', semantic: 'neutral' },
      { label: 'Weighted KPR', value: a.weighted_kpr, delta: '1.5x recent event', semantic: 'warning' },
      { label: 'Rounds Needed', value: a.rounds_needed, delta: 'to hit line', semantic: 'neutral' },
      { label: 'Over Rate', value: `${a.over_percentage}%`, delta: `${a.over_count} maps`, semantic: 'positive' },
      { label: 'Under Rate', value: `${a.under_percentage}%`, delta: `${a.under_count} maps`, semantic: 'negative' },
      { label: 'Maps Analyzed', value: a.total_maps, delta: `${a.events_analyzed} events`, semantic: 'neutral' },
      { label: 'Confidence', value: a.confidence, delta: 'sample quality', semantic: 'neutral' },
    ]
  }

  function classificationColor(c: string): string {
    const l = c.toLowerCase()
    if (l.includes('underpriced')) return '#22c55e'
    if (l.includes('overpriced')) return '#ef4444'
    return '#f59e0b'
  }

  return (
    <>
      <AppHeader activePage="/" />

      <main className="page-container py-8 flex flex-col gap-6">

        {/* Hero */}
        <div className="text-center pt-4 pb-2">
          <h1
            className="font-bold uppercase tracking-tight text-balance"
            style={{ fontFamily: '"Barlow Condensed", sans-serif', fontSize: 'clamp(2.5rem, 8vw, 5rem)', color: '#ffffff' }}
          >
            Thunder<span style={{ color: '#F0E040' }}>Edge</span>
          </h1>
          <p className="text-sm mt-1 text-pretty" style={{ color: 'rgba(255,255,255,0.5)' }}>
            Valorant kill line analytics — enter a player IGN to analyze
          </p>
        </div>

        {/* Search bar (command bar style matching index.html) */}
        <form onSubmit={handleSubmit}>
          <div
            className="flex items-center gap-2 px-4 py-3 mb-0"
            style={{ background: '#0a0a0a', border: '1px solid rgba(240,224,64,0.2)', borderBottom: 'none' }}
          >
            <span style={{ fontFamily: '"Barlow Condensed", sans-serif', fontWeight: 700, fontSize: '1.2rem', color: '#F0E040' }}>{'>'}</span>
            <input
              type="text"
              value={form.player}
              onChange={(e) => setForm((f) => ({ ...f, player: e.target.value }))}
              placeholder="enter player ign and press enter..."
              className="flex-1 bg-transparent text-white outline-none text-base"
              style={{ fontFamily: '"Courier New", monospace', fontSize: '1rem' }}
            />
            <button
              type="submit"
              disabled={loading}
              className="flex items-center gap-2 px-4 py-1.5 text-sm font-bold uppercase tracking-wide disabled:opacity-50"
              style={{ background: '#F0E040', color: '#000', fontFamily: '"Barlow Condensed", sans-serif' }}
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
              Analyze
            </button>
          </div>

          {/* Secondary options row — scrollable on mobile */}
          <div
            className="overflow-x-auto"
            style={{ background: '#0a0a0a', border: '1px solid rgba(240,224,64,0.2)' }}
          >
          <div
            className="flex items-center gap-x-5 gap-y-0 px-4 py-2 text-sm min-w-max"
            style={{ color: 'rgba(255,255,255,0.5)' }}
          >
            <label className="flex items-center gap-2 whitespace-nowrap">
              Kill Line:
              <input
                type="number"
                step="0.5"
                value={form.killLine}
                onChange={(e) => setForm((f) => ({ ...f, killLine: e.target.value }))}
                className="w-16 px-2 py-0.5 text-white bg-transparent border rounded outline-none text-sm tabular-nums"
                style={{ borderColor: 'rgba(255,255,255,0.15)' }}
              />
            </label>
            <label className="flex items-center gap-2 whitespace-nowrap">
              Over Odds:
              <input
                type="text"
                placeholder="-110"
                value={form.overOdds}
                onChange={(e) => setForm((f) => ({ ...f, overOdds: e.target.value }))}
                className="w-20 px-2 py-0.5 text-white bg-transparent border rounded outline-none text-sm tabular-nums"
                style={{ borderColor: 'rgba(255,255,255,0.15)' }}
              />
            </label>
            <label className="flex items-center gap-2 whitespace-nowrap">
              Under Odds:
              <input
                type="text"
                placeholder="-110"
                value={form.underOdds}
                onChange={(e) => setForm((f) => ({ ...f, underOdds: e.target.value }))}
                className="w-20 px-2 py-0.5 text-white bg-transparent border rounded outline-none text-sm tabular-nums"
                style={{ borderColor: 'rgba(255,255,255,0.15)' }}
              />
            </label>
            <label className="flex items-center gap-2 whitespace-nowrap">
              Team Odds:
              <input
                type="number"
                placeholder="1.62 or -160"
                value={form.teamOdds}
                onChange={(e) => setForm((f) => ({ ...f, teamOdds: e.target.value }))}
                className="w-28 px-2 py-0.5 text-white bg-transparent border rounded outline-none text-sm tabular-nums"
                style={{ borderColor: 'rgba(255,255,255,0.15)' }}
              />
            </label>
            <label className="flex items-center gap-2 whitespace-nowrap">
              Opp Odds:
              <input
                type="number"
                placeholder="2.30 or +140"
                value={form.oppOdds}
                onChange={(e) => setForm((f) => ({ ...f, oppOdds: e.target.value }))}
                className="w-28 px-2 py-0.5 text-white bg-transparent border rounded outline-none text-sm tabular-nums"
                style={{ borderColor: 'rgba(255,255,255,0.15)' }}
              />
            </label>
          </div>
          </div>
        </form>

        {/* Error */}
        {error && (
          <div
            className="px-4 py-3 text-sm font-semibold"
            style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444' }}
          >
            {error}
          </div>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div className="flex flex-col gap-3">
            <div className="skeleton-shimmer h-20 rounded-[8px]" />
            <div className="skeleton-shimmer h-48 rounded-[8px]" />
            <div className="skeleton-shimmer h-32 rounded-[8px]" />
          </div>
        )}

        {/* Results */}
        {analysis && !loading && (
          <>
            {/* Performance bar */}
            <div
              className="flex flex-wrap gap-x-6 gap-y-1 px-4 py-2.5 text-sm"
              style={{ background: '#0D0D0D', border: '1px solid rgba(240,224,64,0.15)', borderLeft: '3px solid #F0E040' }}
            >
              {elapsed !== null && (
                <span style={{ color: 'rgba(255,255,255,0.5)' }}>
                  Query Time: <span style={{ color: '#F0E040', fontWeight: 700 }}>{elapsed.toFixed(2)}s</span>
                </span>
              )}
              <span style={{ color: 'rgba(255,255,255,0.5)' }}>
                Events: <span style={{ color: '#22c55e', fontWeight: 700 }}>
                  {analysis.event_details?.filter((e) => e.cached).length ?? 0} cached
                </span>
                {' / '}
                <span style={{ color: '#f59e0b', fontWeight: 700 }}>
                  {analysis.event_details?.filter((e) => !e.cached).length ?? 0} live
                </span>
              </span>
              <span style={{ color: 'rgba(255,255,255,0.5)' }}>
                Maps Analyzed: <span style={{ color: '#F0E040', fontWeight: 700 }}>{analysis.total_maps}</span>
              </span>
            </div>

            {/* Two-column layout — stacks on mobile */}
            <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,58%)_minmax(0,42%)] gap-6">

              {/* LEFT — events */}
              <div className="flex flex-col gap-4">
                {/* Edge summary if available */}
                {edgeData && <EdgeSummary edge={edgeData} />}

                {/* Events section */}
                <div
                  className="p-5"
                  style={{ background: '#0D0D0D', border: '1px solid rgba(240,224,64,0.15)', borderLeft: '3px solid #F0E040' }}
                >
                  <h3
                    className="font-bold mb-1 pb-3 border-b"
                    style={{ fontFamily: '"Barlow Condensed", sans-serif', fontSize: '1.1rem', color: '#ffffff', borderColor: 'rgba(255,255,255,0.06)' }}
                  >
                    VCT Events Analyzed
                  </h3>
                  <p className="text-sm mb-4" style={{ color: 'rgba(255,255,255,0.5)' }}>
                    Total KPR: {analysis.total_kpr ?? analysis.weighted_kpr} &nbsp;|&nbsp; Weighted KPR: {analysis.weighted_kpr} &nbsp;|&nbsp; Total Rounds: {analysis.total_maps}
                  </p>
                  <div className="flex flex-col gap-2">
                    {analysis.event_details && analysis.event_details.length > 0 ? (
                      analysis.event_details.map((ev, i) => (
                        <EventRow key={i} event={ev} killLine={analysis.kill_line} defaultOpen={i === 0} />
                      ))
                    ) : (
                      <p className="text-sm" style={{ color: '#71717a' }}>No event details available</p>
                    )}
                  </div>
                </div>
              </div>

              {/* RIGHT — player card */}
              <div className="flex flex-col gap-4">
                {/* Player header */}
                <div
                  className="p-5"
                  style={{ background: '#0D0D0D', border: '1px solid rgba(240,224,64,0.15)', borderLeft: '3px solid #F0E040' }}
                >
                  <div className="flex justify-between items-start mb-5 flex-wrap gap-3">
                    <div>
                      <h2 className="font-bold" style={{ fontFamily: '"Barlow Condensed", sans-serif', fontSize: 'clamp(1.5rem, 4vw, 2.25rem)', color: '#ffffff' }}>
                        {analysis.player_ign}
                      </h2>
                      <p className="text-sm mt-0.5" style={{ color: 'rgba(255,255,255,0.5)' }}>
                        {analysis.team || 'Unknown Team'}
                      </p>
                    </div>
                  </div>

                  {/* Over/Under */}
                  <OverUnderDisplay
                    overPct={analysis.over_percentage}
                    underPct={analysis.under_percentage}
                    sampleSize={analysis.total_maps}
                    killLine={analysis.kill_line}
                  />

                  {/* Matchup-adjusted probabilities if available */}
                  {analysis.matchup_adjusted_probabilities && (
                    <div
                      className="mt-4 p-3 rounded-[8px]"
                      style={{ background: '#0a0a0a', border: '1px solid rgba(59,130,246,0.25)' }}
                    >
                      <p className="text-[0.65rem] uppercase tracking-[0.1em] mb-2" style={{ color: '#71717a' }}>
                        Matchup Adjusted (Win Prob: {(analysis.matchup_adjusted_probabilities.team_win_prob * 100).toFixed(1)}%)
                      </p>
                      <div className="flex gap-4">
                        <div>
                          <p className="text-[0.7rem]" style={{ color: '#71717a' }}>Adj. Over</p>
                          <p className="font-bold tabular-nums" style={{ fontSize: '1.25rem', color: '#22c55e' }}>
                            {(analysis.matchup_adjusted_probabilities.p_over * 100).toFixed(1)}%
                          </p>
                        </div>
                        <div>
                          <p className="text-[0.7rem]" style={{ color: '#71717a' }}>Adj. Under</p>
                          <p className="font-bold tabular-nums" style={{ fontSize: '1.25rem', color: '#ef4444' }}>
                            {(analysis.matchup_adjusted_probabilities.p_under * 100).toFixed(1)}%
                          </p>
                        </div>
                        <div>
                          <p className="text-[0.7rem]" style={{ color: '#71717a' }}>Multiplier</p>
                          <p className="font-bold tabular-nums" style={{ fontSize: '1.25rem', color: '#f59e0b' }}>
                            {analysis.matchup_adjusted_probabilities.multiplier?.toFixed(3) ?? '—'}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Classification */}
                  <div
                    className="mt-4 p-4 text-center"
                    style={{
                      border: `1px solid ${classificationColor(analysis.classification)}40`,
                      background: `${classificationColor(analysis.classification)}10`,
                    }}
                  >
                    <p
                      className="font-bold uppercase tracking-wide"
                      style={{ fontFamily: '"Barlow Condensed", sans-serif', fontSize: '1.3rem', color: classificationColor(analysis.classification) }}
                    >
                      {analysis.classification}
                    </p>
                    <p className="text-sm mt-1 font-medium" style={{ color: '#a1a1aa' }}>
                      {analysis.recommendation}
                    </p>
                  </div>

                  {/* Formula */}
                  <div
                    className="mt-4 p-4 text-center"
                    style={{ background: '#0a0a0a', border: '1px solid rgba(240,224,64,0.15)', borderLeft: '3px solid #F0E040' }}
                  >
                    <p className="text-[0.65rem] uppercase tracking-[0.12em] mb-2" style={{ color: 'rgba(255,255,255,0.4)' }}>
                      Formula: Kill Line / Weighted KPR = Rounds Needed
                    </p>
                    <p className="font-mono text-sm" style={{ color: '#F0E040' }}>
                      {analysis.kill_line} / {analysis.weighted_kpr} =
                    </p>
                    <p className="font-bold tabular-nums mt-1" style={{ fontFamily: '"Barlow Condensed", sans-serif', fontSize: '2rem', color: '#ffffff' }}>
                      {analysis.rounds_needed} rounds
                    </p>
                  </div>
                </div>

                {/* Stats grid */}
                <StatsGrid stats={buildStats(analysis)} columns={2} />

                {/* Agent stats */}
                {agentStats.length > 0 && (
                  <div
                    className="p-4"
                    style={{ background: '#0D0D0D', border: '1px solid rgba(255,255,255,0.06)' }}
                  >
                    <h4 className="font-bold mb-3 text-sm uppercase tracking-wider" style={{ color: '#ffffff', fontFamily: '"Barlow Condensed", sans-serif' }}>
                      Agent Breakdown
                    </h4>
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr>
                          {['Agent', 'Maps', 'Avg K', 'Over', 'Under'].map((h) => (
                            <th key={h} className="text-left pb-2 text-[0.65rem] uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.4)', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {agentStats.map((a, i) => (
                          <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                            <td className="py-2" style={{ color: '#e4e4e7' }}>{a.agent}</td>
                            <td className="py-2 tabular-nums" style={{ color: '#a1a1aa' }}>{a.maps}</td>
                            <td className="py-2 tabular-nums" style={{ color: '#ffffff' }}>{a.avg_kills?.toFixed(1) ?? '—'}</td>
                            <td className="py-2 tabular-nums" style={{ color: '#22c55e' }}>{a.over_count}</td>
                            <td className="py-2 tabular-nums" style={{ color: '#ef4444' }}>{a.under_count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Map stats */}
                {mapStats.length > 0 && (
                  <div
                    className="p-4"
                    style={{ background: '#0D0D0D', border: '1px solid rgba(255,255,255,0.06)' }}
                  >
                    <h4 className="font-bold mb-3 text-sm uppercase tracking-wider" style={{ color: '#ffffff', fontFamily: '"Barlow Condensed", sans-serif' }}>
                      Map Breakdown
                    </h4>
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr>
                          {['Map', 'Maps', 'Avg K', 'Over', 'Under'].map((h) => (
                            <th key={h} className="text-left pb-2 text-[0.65rem] uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.4)', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {mapStats.map((m, i) => (
                          <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                            <td className="py-2" style={{ color: '#e4e4e7' }}>{m.map}</td>
                            <td className="py-2 tabular-nums" style={{ color: '#a1a1aa' }}>{m.maps}</td>
                            <td className="py-2 tabular-nums" style={{ color: '#ffffff' }}>{m.avg_kills?.toFixed(1) ?? '—'}</td>
                            <td className="py-2 tabular-nums" style={{ color: '#22c55e' }}>{m.over_count}</td>
                            <td className="py-2 tabular-nums" style={{ color: '#ef4444' }}>{m.under_count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          </>
        )}

        {/* Empty state — shown before any query */}
        {!analysis && !loading && !error && (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <div style={{ fontSize: '3rem', opacity: 0.1 }}>
              <TrendingUp size={64} style={{ color: '#ffffff' }} />
            </div>
            <p className="text-sm" style={{ color: 'rgba(255,255,255,0.25)' }}>
              Enter a player IGN above to start analysis
            </p>
            <p className="text-xs" style={{ color: 'rgba(255,255,255,0.15)' }}>
              e.g. TenZ, aspas, cNed, Zekken
            </p>
          </div>
        )}

      </main>
    </>
  )
}
