'use client'

import { useState, useRef } from 'react'
import { Loader2, AlertCircle } from 'lucide-react'
import * as Tabs from '@radix-ui/react-tabs'
import { AppHeader } from '@/components/app-header'
import { OverUnderDisplay } from '@/components/over-under-display'
import { StatsGrid, type StatCardData } from '@/components/stats-grid'
import { DataTable, type Column } from '@/components/data-table'
import { RecommendationCard } from '@/components/recommendation-card'
import { CollapsibleSection } from '@/components/collapsible-section'
import { EventTimeline, type EventDetail } from '@/components/event-timeline'
import { MatchupBox } from '@/components/matchup-box'
import { EdgeSection, type EdgeData } from '@/components/edge-section'
import { API_BASE } from '@/lib/api'

// ─── Types ────────────────────────────────────────────────────────────────────

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

// ─── Column definitions ────────────────────────────────────────────────────────

const AGENT_COLS: Column<AgentStat>[] = [
  { key: 'agent', label: 'Agent', sortable: true },
  { key: 'maps', label: 'Maps', sortable: true, align: 'right' },
  {
    key: 'avg_kills',
    label: 'Avg K',
    sortable: true,
    align: 'right',
    render: (v) => (v != null ? (v as number).toFixed(1) : '—'),
  },
  {
    key: 'over_count',
    label: 'Over',
    sortable: true,
    align: 'right',
    render: (v) => (v != null ? String(v) : '—'),
  },
  {
    key: 'under_count',
    label: 'Under',
    sortable: true,
    align: 'right',
    render: (v) => (v != null ? String(v) : '—'),
  },
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
  {
    key: 'avg_kills_per_map',
    label: 'Avg K/Map',
    sortable: true,
    align: 'right',
    render: (v) => (v != null ? (v as number).toFixed(1) : '—'),
  },
  {
    key: 'kd_ratio',
    label: 'K/D',
    sortable: true,
    align: 'right',
    render: (v) => (v != null ? (v as number).toFixed(2) : '—'),
  },
  {
    key: 'avg_acs',
    label: 'ACS',
    sortable: true,
    align: 'right',
    render: (v) => (v != null ? (v as number).toFixed(1) : '—'),
  },
]

// ─── Param input fields config ─────────────────────────────────────────────────

const PARAM_FIELDS = [
  { label: 'Kill Line', key: 'killLine', type: 'number', step: '0.5', placeholder: '15.5' },
  { label: 'Over Odds', key: 'overOdds', type: 'text', placeholder: '-110' },
  { label: 'Under Odds', key: 'underOdds', type: 'text', placeholder: '-110' },
  { label: 'Team Odds', key: 'teamOdds', type: 'number', placeholder: '1.62' },
  { label: 'Opp Odds', key: 'oppOdds', type: 'number', placeholder: '2.30' },
] as const

// ─── Main page ─────────────────────────────────────────────────────────────────

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

  const paramValues: Record<string, string> = { killLine, overOdds, underOdds, teamOdds, oppOdds }
  const paramSetters: Record<string, (v: string) => void> = {
    killLine: setKillLine,
    overOdds: setOverOdds,
    underOdds: setUnderOdds,
    teamOdds: setTeamOdds,
    oppOdds: setOppOdds,
  }

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
          const er = await fetch(
            `${base}/api/edge/${encodeURIComponent(ign)}?line=${line}&over_odds=${parsedOver}&under_odds=${parsedUnder}${teamQ}`,
          )
          if (er.ok) {
            const ed = await er.json()
            if (ed.success) edgeData = ed
          }
        } catch {
          /* edge is optional */
        }
      }

      const elapsed = ((performance.now() - t0) / 1000).toFixed(2)
      const agentStats = (data.agent_stats || []).map((a: Record<string, unknown>) => ({
        agent: a.agent,
        maps: a.maps ?? a.maps_played ?? 0,
        avg_kills:
          a.avg_kills ??
          (a.maps_played && a.total_kills
            ? (a.total_kills as number) / (a.maps_played as number)
            : 0),
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

  // Build stats array for StatsGrid
  const stats: StatCardData[] = analysis
    ? [
        {
          label: 'Kill Line',
          value: analysis.kill_line ?? '—',
          delta: 'Thunderpick',
          semantic: 'neutral',
        },
        {
          label: 'Total KPR',
          value: (analysis.total_kpr ?? analysis.weighted_kpr ?? 0).toFixed(3),
          delta: 'Weighted by rounds',
          semantic: 'neutral',
        },
        {
          label: 'Weighted KPR',
          value: (analysis.weighted_kpr ?? 0).toFixed(3),
          delta: '1.5× recent event',
          semantic: 'neutral',
        },
        {
          label: 'Rounds Needed',
          value: (analysis.rounds_needed ?? 0).toFixed(1),
          delta: 'to hit line',
          semantic: 'neutral',
        },
        {
          label: 'Maps Analyzed',
          value: analysis.total_maps ?? 0,
          delta: `${analysis.events_analyzed ?? 0} events`,
          semantic: 'neutral',
        },
        {
          label: 'Confidence',
          value: analysis.confidence ?? '—',
          delta: 'Sample quality',
          semantic:
            parseConfidence(analysis?.confidence) === 'HIGH'
              ? 'positive'
              : parseConfidence(analysis?.confidence) === 'LOW'
                ? 'negative'
                : 'neutral',
        },
      ]
    : []

  const recType = analysis ? classificationToType(analysis.classification) : 'NO_BET'
  const recEV = edgeData?.edge
    ? edgeData.edge.recommended === 'OVER'
      ? edgeData.edge.ev_over
      : edgeData.edge.recommended === 'UNDER'
        ? edgeData.edge.ev_under
        : 0
    : 0
  const recConfidence = parseConfidence(edgeData?.player.confidence || analysis?.confidence)
  const cachedCount = analysis?.event_details?.filter((e) => e.cached).length ?? 0
  const liveCount = (analysis?.event_details?.length ?? 0) - cachedCount
  const recAccent =
    recType === 'BET_OVER' ? '#22c55e' : recType === 'BET_UNDER' ? '#ef4444' : '#F0E040'

  return (
    <>
      <AppHeader activePage="/" />

      <div className="page-container pb-12">
        {/* ── Hero ─────────────────────────────────────────────────────── */}
        <div className="text-center pt-10 pb-6">
          <h1
            className="font-display font-black uppercase leading-[1.05] tracking-[-0.02em] text-white mb-3"
            style={{ fontSize: 'clamp(2.5rem, 6vw, 5rem)' }}
          >
            Thunderpick <span className="text-[#F0E040]">Kill Line</span>
          </h1>
          <p className="text-sm text-white/50 max-w-lg mx-auto leading-relaxed">
            Negative binomial kill-line analytics for VCT players — live data from VLR.gg
          </p>
        </div>

        {/* ── Command bar ──────────────────────────────────────────────── */}
        <div
          className="bg-[#0D0D0D] border border-[rgba(240,224,64,0.15)]"
          style={{ borderLeft: '3px solid #F0E040' }}
        >
          {/* Primary input row */}
          <div className="flex items-center gap-2 px-4 py-3">
            <span
              className="font-display font-bold text-xl text-[#F0E040] shrink-0 select-none"
              aria-hidden="true"
            >
              {'>'}
            </span>
            <input
              ref={playerRef}
              id="player-ign"
              type="text"
              value={playerInput}
              onChange={(e) => setPlayerInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="enter player ign and press enter..."
              aria-label="Player IGN"
              autoComplete="off"
              spellCheck={false}
              className="flex-1 bg-transparent border-none outline-none font-mono text-[1.05rem] text-white placeholder:text-white/25"
            />
            <button
              type="button"
              onClick={handleAnalyze}
              disabled={isLoading || !playerInput.trim()}
              aria-label="Analyze player"
              className={
                'font-display font-bold text-sm uppercase tracking-[0.06em] px-4 py-1.5 ' +
                'flex items-center gap-1.5 shrink-0 transition-opacity ' +
                'bg-[#F0E040] text-black border-0 ' +
                (isLoading || !playerInput.trim()
                  ? 'opacity-40 cursor-not-allowed'
                  : 'opacity-100 hover:opacity-90 cursor-pointer')
              }
            >
              {isLoading ? (
                <>
                  <Loader2 size={12} className="animate-spin" />
                  Analyzing
                </>
              ) : (
                'Analyze'
              )}
            </button>
          </div>

          {/* Secondary params row */}
          <div className="flex flex-wrap gap-x-5 gap-y-2 items-center px-4 py-2.5 border-t border-[rgba(255,255,255,0.06)]">
            {PARAM_FIELDS.map((f) => (
              <label
                key={f.key}
                className="flex items-center gap-1.5 text-[0.78rem] text-white/50 cursor-text"
              >
                <span className="whitespace-nowrap">{f.label}:</span>
                <input
                  type={f.type}
                  step={'step' in f ? f.step : undefined}
                  value={paramValues[f.key]}
                  onChange={(e) => paramSetters[f.key](e.target.value)}
                  onKeyDown={handleKey}
                  placeholder={f.placeholder}
                  aria-label={f.label}
                  className="w-20 px-2 py-1 text-[0.78rem] bg-[#0a0a0a] border border-[rgba(255,255,255,0.12)] text-white outline-none"
                  style={{ borderRadius: 0 }}
                />
              </label>
            ))}
          </div>
        </div>

        {/* ── Error banner ─────────────────────────────────────────────── */}
        {error && (
          <div className="flex items-center gap-3 bg-[rgba(239,68,68,0.1)] border border-[rgba(239,68,68,0.3)] text-[#ef4444] px-5 py-3.5 mt-4 font-semibold text-sm">
            <AlertCircle size={16} className="shrink-0" />
            {error}
          </div>
        )}

        {/* ── Loading skeleton ──────────────────────────────────────────── */}
        {isLoading && (
          <div className="mt-6 flex flex-col gap-3">
            <div className="skeleton-shimmer" style={{ height: 64 }} />
            <div className="skeleton-shimmer" style={{ height: 180 }} />
            <div className="skeleton-shimmer" style={{ height: 100 }} />
          </div>
        )}

        {/* ── Analysis-level error ─────────────────────────────────────── */}
        {!isLoading && result && analysis && !analysis.player_ign && (
          <div className="flex items-center gap-3 bg-[rgba(239,68,68,0.1)] border border-[rgba(239,68,68,0.3)] text-[#ef4444] px-5 py-3.5 mt-4 font-semibold text-sm">
            <AlertCircle size={16} className="shrink-0" />
            {(analysis as unknown as Record<string, string>).error ||
              'Insufficient data for this player'}
          </div>
        )}

        {/* ── Results ──────────────────────────────────────────────────── */}
        {!isLoading && result && analysis && analysis.player_ign && (
          <div className="mt-6 flex flex-col gap-6">
            {/* Status / performance bar */}
            <div
              className="bg-[#0D0D0D] border border-[rgba(240,224,64,0.12)] px-5 py-3.5 flex flex-wrap gap-x-5 gap-y-1.5 text-sm text-white/50 items-center"
              style={{ borderLeft: '3px solid #F0E040' }}
            >
              <span>
                <strong className="text-white font-semibold">{analysis.player_ign}</strong>
                {analysis.team && (
                  <span className="text-white/40"> · {analysis.team}</span>
                )}
              </span>
              <span>
                Query:{' '}
                <span className="font-display font-bold text-[#F0E040] tabular-nums">
                  {result.elapsed}s
                </span>
              </span>
              <span>
                <span className="font-display font-bold text-[#22c55e] tabular-nums">
                  {cachedCount} cached
                </span>
                <span className="mx-1">/</span>
                <span className="font-display font-bold text-[#f59e0b] tabular-nums">
                  {liveCount} live
                </span>
              </span>
              <span>
                Maps:{' '}
                <span className="font-display font-bold text-[#F0E040] tabular-nums">
                  {analysis.total_maps ?? 0}
                </span>
              </span>
              {edgeData && (
                <span className="text-[#22c55e] font-semibold text-xs ml-auto">
                  ✓ Edge loaded
                </span>
              )}
            </div>

            {/* ── Collapsible result sections ─────────────────────────── */}
            <div className="flex flex-col gap-3">
            <CollapsibleSection
              title="Recommendation"
              defaultOpen
              accentColor={recAccent}
            >
              <div className="flex items-center gap-2 mb-4 flex-wrap">
                <span
                  className={
                    'font-display font-bold text-xs px-3 py-1.5 uppercase tracking-[0.08em] border ' +
                    (recType === 'BET_OVER'
                      ? 'bg-[rgba(34,197,94,0.12)] text-[#22c55e] border-[rgba(34,197,94,0.3)]'
                      : recType === 'BET_UNDER'
                        ? 'bg-[rgba(239,68,68,0.12)] text-[#ef4444] border-[rgba(239,68,68,0.3)]'
                        : 'bg-[rgba(240,224,64,0.12)] text-[#F0E040] border-[rgba(240,224,64,0.3)]')
                  }
                >
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

            <CollapsibleSection title="Empirical Over/Under Percentages" accentColor="#F0E040">
              <OverUnderDisplay
                overPct={analysis.over_percentage ?? 0}
                underPct={analysis.under_percentage ?? 0}
                sampleSize={analysis.total_maps ?? 0}
                killLine={analysis.kill_line}
              />
              <p className="text-xs text-white/40 text-center mt-3">
                Based on {analysis.total_maps ?? 0} maps across {analysis.events_analyzed ?? 0}{' '}
                VCT events
              </p>
            </CollapsibleSection>

            <CollapsibleSection title="Expected Rounds" accentColor="#F0E040">
              <div className="bg-[#0a0a0a] border border-[rgba(240,224,64,0.1)] px-6 py-6 text-center">
                <div className="text-[0.68rem] uppercase tracking-[0.12em] text-white/40 mb-3">
                  Formula: Kill Line / Weighted KPR = Rounds Needed
                </div>
                <div className="font-mono text-sm text-[#F0E040] mb-2 tabular-nums">
                  {analysis.kill_line ?? '—'} / {(analysis.weighted_kpr ?? 0).toFixed(3)} =
                </div>
                <div className="font-display font-black text-5xl text-white tabular-nums leading-none">
                  {(analysis.rounds_needed ?? 0).toFixed(1)}
                  <span className="text-2xl font-bold text-white/60 ml-2">rounds</span>
                </div>
              </div>
            </CollapsibleSection>

            <CollapsibleSection title="Key Stats" accentColor="#F0E040">
              <StatsGrid stats={stats} columns={3} />
            </CollapsibleSection>

            {analysis.matchup_adjusted_probabilities && (
              <CollapsibleSection title="Matchup Adjustment" accentColor="#F0E040">
                <MatchupBox adj={analysis.matchup_adjusted_probabilities} />
              </CollapsibleSection>
            )}

            {/* Agent & Map Breakdown — tabbed UX */}
            <CollapsibleSection title="Agent and Map Breakdown" accentColor="#F0E040">
              <Tabs.Root defaultValue="agents">
                <Tabs.List className="flex border-b border-[rgba(255,255,255,0.06)] mb-5 -mx-0">
                  <Tabs.Trigger
                    value="agents"
                    className={
                      'px-4 py-2.5 text-[0.78rem] font-semibold uppercase tracking-wider ' +
                      'text-white/50 border-b-2 border-transparent ' +
                      'data-[state=active]:text-white data-[state=active]:border-[#F0E040] ' +
                      'transition-colors duration-150 cursor-pointer bg-transparent border-none outline-none'
                    }
                  >
                    By Agent
                  </Tabs.Trigger>
                  <Tabs.Trigger
                    value="maps"
                    className={
                      'px-4 py-2.5 text-[0.78rem] font-semibold uppercase tracking-wider ' +
                      'text-white/50 border-b-2 border-transparent ' +
                      'data-[state=active]:text-white data-[state=active]:border-[#F0E040] ' +
                      'transition-colors duration-150 cursor-pointer bg-transparent border-none outline-none'
                    }
                  >
                    By Map
                  </Tabs.Trigger>
                </Tabs.List>

                <Tabs.Content value="agents">
                  {result.agentStats && result.agentStats.length > 0 ? (
                    <DataTable<AgentStat>
                      columns={AGENT_COLS}
                      data={result.agentStats}
                      filterPlaceholder="Filter agents..."
                      filterKey="agent"
                    />
                  ) : (
                    <p className="text-white/40 text-sm py-4">
                      No agent data available. Populate the database with match details to see
                      per-agent stats.
                    </p>
                  )}
                </Tabs.Content>

                <Tabs.Content value="maps">
                  {result.mapStats && result.mapStats.length > 0 ? (
                    <DataTable<MapStat>
                      columns={MAP_COLS}
                      data={result.mapStats}
                      filterPlaceholder="Filter maps..."
                      filterKey="map_name"
                    />
                  ) : (
                    <p className="text-white/40 text-sm py-4">
                      No map data available. Populate the database with match details to see
                      per-map stats.
                    </p>
                  )}
                </Tabs.Content>
              </Tabs.Root>
            </CollapsibleSection>

            {analysis.event_details && analysis.event_details.length > 0 && (
              <CollapsibleSection title="VCT Events Timeline" accentColor="#F0E040">
                <p className="text-sm text-white/40 mb-4">
                  Total KPR:{' '}
                  {(analysis.total_kpr ?? analysis.weighted_kpr ?? 0).toFixed(3)} · Weighted KPR:{' '}
                  {(analysis.weighted_kpr ?? 0).toFixed(3)} · Rounds:{' '}
                  {analysis.total_rounds ?? '—'}
                </p>
                <EventTimeline
                  events={analysis.event_details}
                  line={analysis.kill_line ?? 15.5}
                />
              </CollapsibleSection>
            )}

            {edgeData && (
              <CollapsibleSection
                title="Monte-Carlo & Mathematical Edge Analysis"
                accentColor="#F0E040"
              >
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
