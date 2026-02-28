'use client'

import { useState } from 'react'

/* ─── Types ─────────────────────────────────────────────── */
export interface MapAction {
  map: string
  count: number
  rate: number
}

export interface PickBanStats {
  total_matches: number
  first_ban: MapAction[]
  second_ban: MapAction[]
  first_pick: MapAction[]
  second_pick: MapAction[]
}

export interface MapRecord {
  map: string
  wins: number
  losses: number
  played: number
  win_rate: number
  avg_team_rounds: number
  avg_opp_rounds: number
  avg_total_rounds: number
}

export interface RecentMatch {
  match_id: number
  match_url: string
  opponent: string
  event_name: string
  result: 'W' | 'L' | null
  score: string | null
}

export interface AgentCount {
  agent: string
  times: number
}

export interface CompEntry {
  agents: string[]
  count: number
  pct: number
}

export interface EventOverview {
  event_name: string
  event_id: number
  fights_per_round: number | null
  kills: number
  deaths: number
  rounds: number
  matches_played: number
}

export interface TeamOverview {
  resolved_name: string
  total_kills: number
  total_deaths: number
  total_rounds: number
  total_matches: number
  total_maps: number
  overall_fpr: number | null
  overall_kd: string | null
  avg_rounds_per_map: number | null
  events: EventOverview[]
}

export interface H2HMatch {
  match_id: number
  match_url: string
  team1: string
  team2: string
  event_name: string
  winner: string | null
  team1_maps: number | null
  team2_maps: number | null
}

export interface OddsInfo {
  team1_odds: number
  team2_odds: number
  team1_win_prob: number
  team2_win_prob: number
  vig_pct: number
}

export interface FightsPerRoundEntry {
  kills: number
  deaths: number
  rounds: number
  fights_per_round: number | null
  kills_per_round: number | null
  deaths_per_round: number | null
  sample_maps: number
}

export interface PerMapKDEntry {
  kills: number
  deaths: number
  assists: number
  kd: number | null
  rounds: number
  sample_maps: number
  is_low_sample: boolean
}

export interface ProjectedScoreEntry {
  projectedWinner: 'team1' | 'team2'
  projectedScore: string
  confidence: number
  team1AvgRounds: number
  team2AvgRounds: number
  sampleMaps1: number
  sampleMaps2: number
}

export interface PlayerMapStat {
  mean: number
  std: number | null
  sample: number
  is_low_sample: boolean
}

export interface PlayerKillStats {
  player_name: string
  per_map: Record<string, PlayerMapStat>
  aggregate: { mean: number | null; std: number | null; sample: number }
}

export interface PlayerKillsData {
  team1: { name: string; players: PlayerKillStats[] }
  team2: { name: string; players: PlayerKillStats[] }
}

export interface MapProbEntry {
  map: string
  p_played: number
  p_ban_t1: number
  p_ban_t2: number
}

export interface MapProbsData {
  maps: MapProbEntry[]
  top3_projected_pool: string[]
}

export interface MispricingPlayer {
  player_name: string
  projected_kills: number | null
  std: number | null
  sample: number
  suggested_line: number | null
}

export interface MispricingData {
  team1: { name: string; players: MispricingPlayer[] }
  team2: { name: string; players: MispricingPlayer[] }
}

export interface TeamMatchupData {
  name: string
  overview: TeamOverview
  pick_ban: PickBanStats
  map_records: MapRecord[]
  recent_matches: RecentMatch[]
  comps_per_map: Record<string, CompEntry[]>
  fights_per_round: Record<string, FightsPerRoundEntry>
  per_map_kd: Record<string, PerMapKDEntry>
}

export interface MatchupData {
  team1: TeamMatchupData
  team2: TeamMatchupData
  head_to_head: H2HMatch[]
  odds: OddsInfo | null
  projected_scores: Record<string, ProjectedScoreEntry>
  player_kills?: PlayerKillsData
  map_probs?: MapProbsData
  mispricing?: MispricingData
}

/* ─── Constants ──────────────────────────────────────────── */
const T1_COLOR = '#3b82f6'
const T2_COLOR = '#f97316'
const T1_BG = 'rgba(59,130,246,0.1)'
const T2_BG = 'rgba(249,115,22,0.1)'
const T1_BORDER = 'rgba(59,130,246,0.25)'
const T2_BORDER = 'rgba(249,115,22,0.25)'

/* ─── Small helpers ───────────────────────────────────────── */
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="text-[0.65rem] uppercase tracking-[0.12em] font-semibold mb-3"
      style={{ color: 'rgba(255,255,255,0.3)' }}
    >
      {children}
    </p>
  )
}

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div
      className="rounded-none border"
      style={{ background: '#0a0a0a', borderColor: '#27272a', ...style }}
    >
      {children}
    </div>
  )
}

function TeamBadge({ name, color, bg, border }: { name: string; color: string; bg: string; border: string }) {
  return (
    <span
      className="text-[0.65rem] uppercase tracking-widest px-2 py-0.5 font-bold"
      style={{ background: bg, color, border: `1px solid ${border}` }}
    >
      {name}
    </span>
  )
}

/* ─── Stat pill ──────────────────────────────────────────── */
function StatRow({ label, v1, v2 }: { label: string; v1: string | number; v2: string | number }) {
  return (
    <div className="flex items-center gap-2 py-1.5" style={{ borderBottom: '1px solid #18181b' }}>
      <span className="w-[40%] text-right text-sm font-semibold tabular-nums" style={{ color: T1_COLOR }}>{v1}</span>
      <span className="flex-1 text-center text-[0.65rem] uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.3)' }}>{label}</span>
      <span className="w-[40%] text-left text-sm font-semibold tabular-nums" style={{ color: T2_COLOR }}>{v2}</span>
    </div>
  )
}

/* ─── Overview comparison ────────────────────────────────── */
function OverviewSection({ t1, t2 }: { t1: TeamOverview; t2: TeamOverview }) {
  return (
    <Card style={{ padding: '1.25rem 1.5rem' }}>
      <SectionLabel>Team Overview</SectionLabel>
      <div className="flex flex-col gap-0.5">
        <StatRow label="K/D" v1={t1.overall_kd ?? '—'} v2={t2.overall_kd ?? '—'} />
        <StatRow label="Total Rounds" v1={t1.total_rounds.toLocaleString()} v2={t2.total_rounds.toLocaleString()} />
        <StatRow label="Maps Played" v1={t1.total_maps} v2={t2.total_maps} />
        <StatRow label="Total Matches" v1={t1.total_matches} v2={t2.total_matches} />
        <StatRow
          label="Avg Rounds / Map"
          v1={t1.avg_rounds_per_map != null ? t1.avg_rounds_per_map.toFixed(1) : '—'}
          v2={t2.avg_rounds_per_map != null ? t2.avg_rounds_per_map.toFixed(1) : '—'}
        />
      </div>

      {/* Per-event breakdown */}
      {(t1.events.length > 0 || t2.events.length > 0) && (
        <div className="mt-4 pt-3" style={{ borderTop: '1px solid #27272a' }}>
          <p className="text-[0.6rem] uppercase tracking-[0.12em] mb-2" style={{ color: 'rgba(255,255,255,0.25)' }}>
            By Event
          </p>
          <div className="grid grid-cols-2 gap-3">
            {[{ events: t1.events, color: T1_COLOR }, { events: t2.events, color: T2_COLOR }].map(({ events, color }, idx) => (
              <div key={idx} className="flex flex-col gap-1">
                {events.slice(0, 4).map((ev) => (
                  <div key={ev.event_id} className="text-[0.7rem] px-2 py-1.5" style={{ background: '#141414', border: '1px solid #27272a' }}>
                    <div className="font-medium truncate mb-0.5" style={{ color: '#e4e4e7' }}>{ev.event_name}</div>
                    <div className="flex gap-2 text-[0.6rem]" style={{ color: 'rgba(255,255,255,0.45)' }}>
                      <span style={{ color }}>FPR {ev.fights_per_round ?? '—'}</span>
                      <span>{ev.matches_played}M</span>
                      <span>{ev.rounds}R</span>
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}

/* ─── Pick/Ban section ───────────────────────────────────── */
function BarCell({ rate, count, color }: { rate: number; count: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full" style={{ background: '#27272a' }}>
        <div className="h-full rounded-full" style={{ width: `${Math.min(100, rate)}%`, background: color }} />
      </div>
      <span className="text-[0.7rem] tabular-nums w-10 text-right" style={{ color: 'rgba(255,255,255,0.6)' }}>
        {rate}%
      </span>
    </div>
  )
}

type PickBanAction = 'first_ban' | 'second_ban' | 'first_pick' | 'second_pick'

const PB_LABELS: Record<PickBanAction, string> = {
  first_ban: '1st Ban',
  second_ban: '2nd Ban',
  first_pick: '1st Pick',
  second_pick: '2nd Pick',
}

const PB_COLORS: Record<PickBanAction, string> = {
  first_ban: '#ef4444',
  second_ban: '#f87171',
  first_pick: T1_COLOR,
  second_pick: '#0ea5e9',
}

function PickBanTeamCol({ pb, teamColor }: { pb: PickBanStats; teamColor: string }) {
  const actions: PickBanAction[] = ['first_ban', 'second_ban', 'first_pick', 'second_pick']
  return (
    <div className="flex flex-col gap-3">
      {actions.map((action) => {
        const items = (pb[action] || []).slice(0, 4)
        if (items.length === 0) return null
        return (
          <div key={action}>
            <p className="text-[0.6rem] uppercase tracking-[0.1em] mb-1.5" style={{ color: 'rgba(255,255,255,0.3)' }}>
              {PB_LABELS[action]}
            </p>
            <div className="flex flex-col gap-1">
              {items.map((item) => (
                <div key={item.map} className="flex items-center gap-2">
                  <span className="text-[0.7rem] w-16 truncate" style={{ color: '#e4e4e7' }}>{item.map}</span>
                  <BarCell rate={item.rate} count={item.count} color={PB_COLORS[action]} />
                </div>
              ))}
            </div>
          </div>
        )
      })}
      {pb.total_matches > 0 && (
        <p className="text-[0.6rem]" style={{ color: 'rgba(255,255,255,0.25)' }}>
          Based on {pb.total_matches} matches
        </p>
      )}
    </div>
  )
}

function PickBanSection({ t1, t2 }: { t1: TeamMatchupData; t2: TeamMatchupData }) {
  return (
    <Card style={{ padding: '1.25rem 1.5rem' }}>
      <SectionLabel>Map Pick / Ban Tendencies</SectionLabel>
      <div className="grid grid-cols-2 gap-6">
        <PickBanTeamCol pb={t1.pick_ban} teamColor={T1_COLOR} />
        <PickBanTeamCol pb={t2.pick_ban} teamColor={T2_COLOR} />
      </div>
    </Card>
  )
}

/* ─── Map Records section ────────────────────────────────── */
function winRateColor(wr: number) {
  if (wr >= 60) return '#22c55e'
  if (wr >= 40) return '#f59e0b'
  return '#ef4444'
}

function MapRecordsSection({ t1, t2 }: { t1: TeamMatchupData; t2: TeamMatchupData }) {
  // Collect all maps from both teams
  const allMaps = Array.from(
    new Set([...t1.map_records.map((m) => m.map), ...t2.map_records.map((m) => m.map)])
  ).sort()

  const rec1 = Object.fromEntries(t1.map_records.map((m) => [m.map, m]))
  const rec2 = Object.fromEntries(t2.map_records.map((m) => [m.map, m]))

  if (allMaps.length === 0) return null

  return (
    <Card style={{ padding: '1.25rem 1.5rem' }}>
      <SectionLabel>Per-Map Records</SectionLabel>
      <div style={{ overflowX: 'auto' }}>
        <table className="w-full text-sm" style={{ borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th className="text-left text-[0.65rem] uppercase tracking-[0.1em] pb-2" style={{ color: 'rgba(255,255,255,0.3)', fontWeight: 600 }}>Map</th>
              <th className="text-center text-[0.65rem] uppercase tracking-[0.1em] pb-2" style={{ color: T1_COLOR, fontWeight: 600 }}>W–L</th>
              <th className="text-center text-[0.65rem] uppercase tracking-[0.1em] pb-2" style={{ color: T1_COLOR, fontWeight: 600 }}>Win%</th>
              <th className="text-center text-[0.65rem] uppercase tracking-[0.1em] pb-2" style={{ color: T1_COLOR, fontWeight: 600 }}>Avg Score</th>
              <th className="w-6" />
              <th className="text-center text-[0.65rem] uppercase tracking-[0.1em] pb-2" style={{ color: T2_COLOR, fontWeight: 600 }}>W–L</th>
              <th className="text-center text-[0.65rem] uppercase tracking-[0.1em] pb-2" style={{ color: T2_COLOR, fontWeight: 600 }}>Win%</th>
              <th className="text-center text-[0.65rem] uppercase tracking-[0.1em] pb-2" style={{ color: T2_COLOR, fontWeight: 600 }}>Avg Score</th>
            </tr>
          </thead>
          <tbody>
            {allMaps.map((map) => {
              const r1 = rec1[map]
              const r2 = rec2[map]
              return (
                <tr key={map} style={{ borderTop: '1px solid #18181b' }}>
                  <td className="py-2 text-[0.8rem] font-medium" style={{ color: '#e4e4e7' }}>{map}</td>
                  <td className="py-2 text-center text-[0.75rem] tabular-nums" style={{ color: r1 ? '#a1a1aa' : '#3f3f46' }}>
                    {r1 ? `${r1.wins}–${r1.losses}` : '—'}
                  </td>
                  <td className="py-2 text-center text-[0.8rem] font-semibold tabular-nums" style={{ color: r1 ? winRateColor(r1.win_rate) : '#3f3f46' }}>
                    {r1 ? `${r1.win_rate}%` : '—'}
                  </td>
                  <td className="py-2 text-center text-[0.7rem] tabular-nums" style={{ color: r1 ? 'rgba(255,255,255,0.5)' : '#3f3f46' }}>
                    {r1 ? `${r1.avg_team_rounds}–${r1.avg_opp_rounds}` : '—'}
                  </td>
                  <td className="py-2 text-center text-[0.7rem]" style={{ color: 'rgba(255,255,255,0.15)' }}>|</td>
                  <td className="py-2 text-center text-[0.75rem] tabular-nums" style={{ color: r2 ? '#a1a1aa' : '#3f3f46' }}>
                    {r2 ? `${r2.wins}–${r2.losses}` : '—'}
                  </td>
                  <td className="py-2 text-center text-[0.8rem] font-semibold tabular-nums" style={{ color: r2 ? winRateColor(r2.win_rate) : '#3f3f46' }}>
                    {r2 ? `${r2.win_rate}%` : '—'}
                  </td>
                  <td className="py-2 text-center text-[0.7rem] tabular-nums" style={{ color: r2 ? 'rgba(255,255,255,0.5)' : '#3f3f46' }}>
                    {r2 ? `${r2.avg_team_rounds}–${r2.avg_opp_rounds}` : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

/* ─── Agent comps section ────────────────────────────────── */
function AgentCompsSection({ t1, t2 }: { t1: TeamMatchupData; t2: TeamMatchupData }) {
  const allMaps = Array.from(
    new Set([...Object.keys(t1.comps_per_map), ...Object.keys(t2.comps_per_map)])
  ).sort()

  const [selectedMap, setSelectedMap] = useState(allMaps[0] ?? '')

  if (allMaps.length === 0) return null

  const comps1 = (t1.comps_per_map[selectedMap] ?? []).slice(0, 5)
  const comps2 = (t2.comps_per_map[selectedMap] ?? []).slice(0, 5)

  return (
    <Card style={{ padding: '1.25rem 1.5rem' }}>
      <SectionLabel>Agent Comps Per Map</SectionLabel>

      {/* Map selector */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {allMaps.map((m) => (
          <button
            key={m}
            onClick={() => setSelectedMap(m)}
            className="text-[0.65rem] px-2.5 py-1 uppercase tracking-wide font-medium transition-colors"
            style={{
              background: selectedMap === m ? 'rgba(255,255,255,0.08)' : 'transparent',
              border: `1px solid ${selectedMap === m ? 'rgba(255,255,255,0.2)' : '#27272a'}`,
              color: selectedMap === m ? '#ffffff' : 'rgba(255,255,255,0.4)',
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            {m}
          </button>
        ))}
      </div>

      {/* Two-column comp lists */}
      <div className="grid grid-cols-2 gap-6">
        {[
          { comps: comps1, color: T1_COLOR, bg: T1_BG },
          { comps: comps2, color: T2_COLOR, bg: T2_BG },
        ].map(({ comps, color, bg }, idx) => (
          <div key={idx}>
            {comps.length === 0 ? (
              <p className="text-[0.75rem]" style={{ color: 'rgba(255,255,255,0.25)' }}>No data</p>
            ) : (
              <div className="flex flex-col gap-1">
                {comps.map((comp, i) => (
                  <div
                    key={comp.agents.join(',')}
                    className="flex items-center justify-between gap-2 px-2 py-1.5 text-[0.7rem]"
                    style={{
                      background: i === 0 ? bg : 'transparent',
                      border: `1px solid ${i === 0 ? color + '33' : '#27272a'}`,
                    }}
                  >
                    <span
                      className="flex-1 min-w-0 truncate"
                      style={{ color: i === 0 ? color : '#a1a1aa' }}
                    >
                      {comp.agents.join(' \u00B7 ')}
                    </span>
                    <span
                      className="shrink-0 tabular-nums text-[0.65rem]"
                      style={{ color: 'rgba(255,255,255,0.4)' }}
                    >
                      {comp.count}× {comp.pct.toFixed(1)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  )
}

/* ─── Projected Map Scores section ──────────────────────── */
function confidenceColor(c: number) {
  if (c >= 0.65) return '#22c55e'
  if (c >= 0.35) return '#f59e0b'
  return '#71717a'
}

function ProjectedScoresSection({
  projected,
  t1Name,
  t2Name,
}: {
  projected: Record<string, ProjectedScoreEntry>
  t1Name: string
  t2Name: string
}) {
  const maps = Object.keys(projected).sort()
  if (maps.length === 0) return null

  return (
    <Card style={{ padding: '1.25rem 1.5rem' }}>
      <SectionLabel>Projected Map Scores</SectionLabel>
      <div style={{ overflowX: 'auto' }}>
        <table className="w-full text-sm" style={{ borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th className="text-left text-[0.65rem] uppercase tracking-[0.1em] pb-2" style={{ color: 'rgba(255,255,255,0.3)', fontWeight: 600 }}>Map</th>
              <th className="text-center text-[0.65rem] uppercase tracking-[0.1em] pb-2" style={{ color: 'rgba(255,255,255,0.3)', fontWeight: 600 }}>Projected</th>
              <th className="text-center text-[0.65rem] uppercase tracking-[0.1em] pb-2" style={{ color: 'rgba(255,255,255,0.3)', fontWeight: 600 }}>Score</th>
              <th className="text-center text-[0.65rem] uppercase tracking-[0.1em] pb-2" style={{ color: 'rgba(255,255,255,0.3)', fontWeight: 600 }}>Conf</th>
            </tr>
          </thead>
          <tbody>
            {maps.map((map) => {
              const e = projected[map]
              const winnerName = e.projectedWinner === 'team1' ? t1Name : t2Name
              const winnerColor = e.projectedWinner === 'team1' ? T1_COLOR : T2_COLOR
              return (
                <tr key={map} style={{ borderTop: '1px solid #18181b' }}>
                  <td className="py-2 text-[0.8rem] font-medium" style={{ color: '#e4e4e7' }}>{map}</td>
                  <td className="py-2 text-center text-[0.75rem] font-semibold" style={{ color: winnerColor }}>
                    {winnerName}
                  </td>
                  <td className="py-2 text-center text-[0.75rem] tabular-nums font-mono" style={{ color: 'rgba(255,255,255,0.6)' }}>
                    {e.projectedScore}
                  </td>
                  <td className="py-2 text-center text-[0.75rem] tabular-nums font-semibold" style={{ color: confidenceColor(e.confidence) }}>
                    {Math.round(e.confidence * 100)}%
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[0.6rem] mt-2" style={{ color: 'rgba(255,255,255,0.2)' }}>
        Projected from historical avg rounds scored/conceded. Confidence reflects sample size + win-rate margin.
      </p>
    </Card>
  )
}

/* ─── Per-Map K/D Comparison section ────────────────────── */
function PerMapKDSection({ t1, t2 }: { t1: TeamMatchupData; t2: TeamMatchupData }) {
  const allMaps = Array.from(
    new Set([...Object.keys(t1.per_map_kd ?? {}), ...Object.keys(t2.per_map_kd ?? {})])
  ).sort()

  if (allMaps.length === 0) return null

  return (
    <Card style={{ padding: '1.25rem 1.5rem' }}>
      <SectionLabel>Per-Map K/D &amp; Fights/Round</SectionLabel>
      <div style={{ overflowX: 'auto' }}>
        <table className="w-full text-sm" style={{ borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th className="text-left text-[0.65rem] uppercase tracking-[0.1em] pb-2" style={{ color: 'rgba(255,255,255,0.3)', fontWeight: 600 }}>Map</th>
              <th className="text-center text-[0.65rem] uppercase tracking-[0.1em] pb-2" style={{ color: T1_COLOR, fontWeight: 600 }}>K/D</th>
              <th className="text-center text-[0.65rem] uppercase tracking-[0.1em] pb-2" style={{ color: T1_COLOR, fontWeight: 600 }}>FPR</th>
              <th className="w-4" />
              <th className="text-center text-[0.65rem] uppercase tracking-[0.1em] pb-2" style={{ color: T2_COLOR, fontWeight: 600 }}>K/D</th>
              <th className="text-center text-[0.65rem] uppercase tracking-[0.1em] pb-2" style={{ color: T2_COLOR, fontWeight: 600 }}>FPR</th>
            </tr>
          </thead>
          <tbody>
            {allMaps.map((map) => {
              const k1 = (t1.per_map_kd ?? {})[map]
              const k2 = (t2.per_map_kd ?? {})[map]
              const f1 = (t1.fights_per_round ?? {})[map]
              const f2 = (t2.fights_per_round ?? {})[map]
              const kdColor = (kd: number | null | undefined) => {
                if (kd == null) return '#3f3f46'
                if (kd >= 1.05) return '#22c55e'
                if (kd >= 0.95) return '#f59e0b'
                return '#ef4444'
              }
              return (
                <tr key={map} style={{ borderTop: '1px solid #18181b' }}>
                  <td className="py-2 text-[0.8rem] font-medium" style={{ color: '#e4e4e7' }}>{map}</td>
                  <td className="py-2 text-center text-[0.8rem] font-semibold tabular-nums" style={{ color: kdColor(k1?.kd) }}>
                    {k1?.kd != null ? k1.kd.toFixed(2) : '—'}
                    {k1?.is_low_sample && <span style={{ color: '#71717a', fontSize: '0.55rem' }}> *</span>}
                  </td>
                  <td className="py-2 text-center text-[0.7rem] tabular-nums" style={{ color: f1?.fights_per_round != null ? 'rgba(255,255,255,0.55)' : '#3f3f46' }}>
                    {f1?.fights_per_round != null ? f1.fights_per_round.toFixed(2) : '—'}
                  </td>
                  <td className="py-2 text-center text-[0.65rem]" style={{ color: 'rgba(255,255,255,0.15)' }}>|</td>
                  <td className="py-2 text-center text-[0.8rem] font-semibold tabular-nums" style={{ color: kdColor(k2?.kd) }}>
                    {k2?.kd != null ? k2.kd.toFixed(2) : '—'}
                    {k2?.is_low_sample && <span style={{ color: '#71717a', fontSize: '0.55rem' }}> *</span>}
                  </td>
                  <td className="py-2 text-center text-[0.7rem] tabular-nums" style={{ color: f2?.fights_per_round != null ? 'rgba(255,255,255,0.55)' : '#3f3f46' }}>
                    {f2?.fights_per_round != null ? f2.fights_per_round.toFixed(2) : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[0.6rem] mt-2" style={{ color: 'rgba(255,255,255,0.2)' }}>
        * low sample (&lt;5 maps). FPR = (kills + deaths) / rounds.
      </p>
    </Card>
  )
}

/* ─── Player Kill Projections section ────────────────────── */
function PlayerKillsSection({ playerKills, t1Name, t2Name }: {
  playerKills: PlayerKillsData
  t1Name: string
  t2Name: string
}) {
  const allMaps = Array.from(new Set([
    ...playerKills.team1.players.flatMap((p) => Object.keys(p.per_map)),
    ...playerKills.team2.players.flatMap((p) => Object.keys(p.per_map)),
  ])).sort()

  const [selectedMap, setSelectedMap] = useState<string>('All')
  const mapOptions = ['All', ...allMaps]

  function renderPlayers(players: PlayerKillStats[], color: string) {
    if (players.length === 0) return <p className="text-[0.75rem]" style={{ color: 'rgba(255,255,255,0.25)' }}>No data</p>
    const sorted = [...players].sort((a, b) => (b.aggregate.mean ?? 0) - (a.aggregate.mean ?? 0))
    return (
      <div className="flex flex-col gap-0.5">
        {sorted.map((p) => {
          const stat = selectedMap === 'All' ? p.aggregate : p.per_map[selectedMap]
          const mean = stat?.mean ?? null
          return (
            <div
              key={p.player_name}
              className="flex items-center justify-between gap-3 px-2 py-1.5 text-[0.72rem]"
              style={{ borderBottom: '1px solid #18181b' }}
            >
              <span className="font-medium w-24 truncate" style={{ color: '#e4e4e7' }}>{p.player_name}</span>
              <span className="tabular-nums font-semibold" style={{ color: mean != null ? color : '#52525b' }}>
                {mean != null ? mean.toFixed(1) : '—'}
              </span>
              {stat && 'std' in stat && stat.std != null && (
                <span className="tabular-nums text-[0.62rem]" style={{ color: 'rgba(255,255,255,0.3)' }}>
                  ±{stat.std.toFixed(1)}
                </span>
              )}
              <span className="text-[0.62rem] ml-auto" style={{ color: 'rgba(255,255,255,0.2)' }}>
                n={stat && 'sample' in stat ? stat.sample : '?'}
              </span>
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <Card style={{ padding: '1.25rem 1.5rem' }}>
      <SectionLabel>Player Kill Projections</SectionLabel>
      {/* Map filter */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {mapOptions.map((m) => (
          <button
            key={m}
            onClick={() => setSelectedMap(m)}
            className="text-[0.65rem] px-2.5 py-1 uppercase tracking-wide font-medium transition-colors"
            style={{
              background: selectedMap === m ? 'rgba(255,255,255,0.08)' : 'transparent',
              border: `1px solid ${selectedMap === m ? 'rgba(255,255,255,0.2)' : '#27272a'}`,
              color: selectedMap === m ? '#ffffff' : 'rgba(255,255,255,0.4)',
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            {m}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-6">
        <div>
          <p className="text-[0.6rem] uppercase tracking-wide mb-2" style={{ color: T1_COLOR }}>{t1Name}</p>
          {renderPlayers(playerKills.team1.players, T1_COLOR)}
        </div>
        <div>
          <p className="text-[0.6rem] uppercase tracking-wide mb-2" style={{ color: T2_COLOR }}>{t2Name}</p>
          {renderPlayers(playerKills.team2.players, T2_COLOR)}
        </div>
      </div>
      <p className="text-[0.6rem] mt-2" style={{ color: 'rgba(255,255,255,0.2)' }}>
        Avg kills ± std dev from 2026 VCT maps. Select a map for map-specific projections.
      </p>
    </Card>
  )
}

/* ─── Map Probability section ────────────────────────────── */
function mapProbColor(p: number): string {
  if (p >= 0.6) return '#22c55e'
  if (p >= 0.3) return '#f59e0b'
  return '#f97316'
}

function MapProbabilitySection({ data, t1Name, t2Name }: { data: MapProbsData; t1Name: string; t2Name: string }) {
  const sorted = [...data.maps].sort((a, b) => b.p_played - a.p_played)
  const maxP = Math.max(...sorted.map((m) => m.p_played), 0.01)

  return (
    <Card style={{ padding: '1.25rem 1.5rem' }}>
      <SectionLabel>Map Pool Probabilities</SectionLabel>
      {data.top3_projected_pool.length > 0 && (
        <p className="text-[0.75rem] mb-4" style={{ color: 'rgba(255,255,255,0.5)' }}>
          Likely pool:{' '}
          <span style={{ color: '#e4e4e7', fontWeight: 600 }}>
            {data.top3_projected_pool.join(' \u00B7 ')}
          </span>
        </p>
      )}
      <div className="flex flex-col gap-2">
        {sorted.map((entry) => (
          <div key={entry.map} className="flex items-center gap-3">
            <span className="text-[0.75rem] font-medium w-20 shrink-0" style={{ color: '#e4e4e7' }}>
              {entry.map}
            </span>
            <div className="flex-1 h-5 relative" style={{ background: '#18181b', borderRadius: 2 }}>
              <div
                className="h-full"
                style={{
                  width: `${(entry.p_played / maxP) * 100}%`,
                  minWidth: 2,
                  background: mapProbColor(entry.p_played),
                  borderRadius: 2,
                  transition: 'width 0.3s ease',
                }}
              />
              <span
                className="absolute right-2 top-0 h-full flex items-center text-[0.65rem] font-semibold tabular-nums"
                style={{ color: 'rgba(255,255,255,0.7)' }}
              >
                {(entry.p_played * 100).toFixed(0)}%
              </span>
            </div>
            <div className="flex gap-2 shrink-0 text-[0.6rem] tabular-nums" style={{ color: 'rgba(255,255,255,0.3)' }}>
              <span title={`${t1Name} ban prob`} style={{ color: T1_COLOR }}>
                Ban {(entry.p_ban_t1 * 100).toFixed(0)}%
              </span>
              <span title={`${t2Name} ban prob`} style={{ color: T2_COLOR }}>
                Ban {(entry.p_ban_t2 * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

/* ─── Mispricing section ─────────────────────────────────── */
function MispricingSection({ data, t1Name, t2Name }: { data: MispricingData; t1Name: string; t2Name: string }) {
  function renderTeam(players: MispricingPlayer[], color: string) {
    const sorted = [...players].sort((a, b) => (b.projected_kills ?? 0) - (a.projected_kills ?? 0))
    if (sorted.length === 0) {
      return <p className="text-[0.75rem]" style={{ color: 'rgba(255,255,255,0.25)' }}>No data</p>
    }
    return (
      <div className="flex flex-col gap-0.5">
        {sorted.map((p) => {
          const hasData = p.projected_kills != null && p.std != null
          let signal: { label: string; color: string } | null = null
          if (hasData && p.suggested_line != null) {
            if (p.suggested_line > p.projected_kills! * 1.05) {
              signal = { label: '\u2193 UNDER', color: '#ef4444' }
            } else if (p.suggested_line < p.projected_kills! * 0.95) {
              signal = { label: '\u2191 OVER', color: '#22c55e' }
            }
          }
          return (
            <div
              key={p.player_name}
              className="flex items-center gap-2 px-2 py-1.5 text-[0.72rem]"
              style={{ borderBottom: '1px solid #18181b' }}
            >
              <span className="font-medium w-24 truncate" style={{ color: '#e4e4e7' }}>{p.player_name}</span>
              <span className="tabular-nums" style={{ color: hasData ? color : '#52525b' }}>
                {hasData ? `Proj: ${p.projected_kills!.toFixed(1)} \u00B1 ${p.std!.toFixed(1)}` : '—'}
              </span>
              {p.suggested_line != null && (
                <span className="tabular-nums text-[0.65rem]" style={{ color: 'rgba(255,255,255,0.35)' }}>
                  Line: {p.suggested_line.toFixed(1)}
                </span>
              )}
              {signal && (
                <span className="text-[0.65rem] font-bold ml-auto" style={{ color: signal.color }}>
                  {signal.label}
                </span>
              )}
              {p.sample < 5 && (
                <span className="text-[0.55rem] ml-auto" style={{ color: '#71717a' }}>
                  low sample (n={p.sample})
                </span>
              )}
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <Card style={{ padding: '1.25rem 1.5rem' }}>
      <SectionLabel>Kill Line Mispricing</SectionLabel>
      <div className="grid grid-cols-2 gap-6">
        <div>
          <p className="text-[0.6rem] uppercase tracking-wide mb-2" style={{ color: T1_COLOR }}>{t1Name}</p>
          {renderTeam(data.team1.players, T1_COLOR)}
        </div>
        <div>
          <p className="text-[0.6rem] uppercase tracking-wide mb-2" style={{ color: T2_COLOR }}>{t2Name}</p>
          {renderTeam(data.team2.players, T2_COLOR)}
        </div>
      </div>
      <p className="text-[0.6rem] mt-2" style={{ color: 'rgba(255,255,255,0.2)' }}>
        Suggested line = model fair value. OVER/UNDER signal when line deviates &gt;5% from projection.
      </p>
    </Card>
  )
}

/* ─── Parlay Builder section ─────────────────────────────── */
interface ParlayLeg {
  playerName: string
  team: 'team1' | 'team2'
  line: number
  direction: 'over' | 'under'
  projectedMean: number | null
  projectedStd: number | null
}

function normCDF(x: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(x))
  const d = 0.3989423 * Math.exp(-x * x / 2)
  const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.7814779 + t * (-1.8212560 + t * 1.3302744))))
  return x > 0 ? 1 - p : p
}

function pOver(mean: number, std: number, line: number): number {
  if (std <= 0) return mean > line ? 1 : 0
  return 1 - normCDF((line - mean) / std)
}

function ParlayBuilderSection({ playerKills }: { playerKills: PlayerKillsData }) {
  const [legs, setLegs] = useState<ParlayLeg[]>([])

  const allPlayers: { name: string; team: 'team1' | 'team2'; mean: number | null; std: number | null }[] = [
    ...playerKills.team1.players.map((p) => ({
      name: p.player_name,
      team: 'team1' as const,
      mean: p.aggregate.mean,
      std: p.aggregate.std,
    })),
    ...playerKills.team2.players.map((p) => ({
      name: p.player_name,
      team: 'team2' as const,
      mean: p.aggregate.mean,
      std: p.aggregate.std,
    })),
  ].sort((a, b) => (b.mean ?? 0) - (a.mean ?? 0))

  const addedNames = new Set(legs.map((l) => l.playerName))

  function addLeg(player: typeof allPlayers[number]) {
    setLegs((prev) => [
      ...prev,
      {
        playerName: player.name,
        team: player.team,
        line: player.mean != null ? Math.round(player.mean * 2) / 2 : 15,
        direction: 'over',
        projectedMean: player.mean,
        projectedStd: player.std,
      },
    ])
  }

  function removeLeg(idx: number) {
    setLegs((prev) => prev.filter((_, i) => i !== idx))
  }

  function updateLeg(idx: number, updates: Partial<ParlayLeg>) {
    setLegs((prev) => prev.map((leg, i) => (i === idx ? { ...leg, ...updates } : leg)))
  }

  function legProb(leg: ParlayLeg): number | null {
    if (leg.projectedMean == null || leg.projectedStd == null) return null
    const po = pOver(leg.projectedMean, leg.projectedStd, leg.line)
    return leg.direction === 'over' ? po : 1 - po
  }

  const legProbs = legs.map(legProb)
  const combinedProb = legProbs.every((p) => p != null)
    ? legProbs.reduce((acc, p) => acc! * p!, 1)
    : null

  return (
    <Card style={{ padding: '1.25rem 1.5rem' }}>
      <SectionLabel>Parlay Builder</SectionLabel>

      {/* Player list to add */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {allPlayers.map((p) => {
          const isAdded = addedNames.has(p.name)
          const color = p.team === 'team1' ? T1_COLOR : T2_COLOR
          return (
            <button
              key={p.name}
              disabled={isAdded}
              onClick={() => addLeg(p)}
              className="text-[0.65rem] px-2 py-1 tracking-wide font-medium transition-colors"
              style={{
                background: isAdded ? 'rgba(255,255,255,0.03)' : 'transparent',
                border: `1px solid ${isAdded ? '#27272a' : color + '44'}`,
                color: isAdded ? '#3f3f46' : color,
                cursor: isAdded ? 'not-allowed' : 'pointer',
                fontFamily: 'inherit',
              }}
            >
              {isAdded ? p.name : `+ ${p.name}`}
            </button>
          )
        })}
      </div>

      {/* Active legs */}
      {legs.length > 0 && (
        <div className="flex flex-col gap-2 mb-4">
          {legs.map((leg, idx) => {
            const prob = legProbs[idx]
            const color = leg.team === 'team1' ? T1_COLOR : T2_COLOR
            return (
              <div
                key={leg.playerName}
                className="flex items-center gap-3 px-3 py-2"
                style={{ background: '#0f0f0f', border: '1px solid #1c1c1e' }}
              >
                <span className="text-[0.75rem] font-medium w-24 truncate" style={{ color }}>
                  {leg.playerName}
                </span>
                <button
                  onClick={() => updateLeg(idx, { direction: leg.direction === 'over' ? 'under' : 'over' })}
                  className="text-[0.65rem] font-bold px-2 py-0.5"
                  style={{
                    background: leg.direction === 'over' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                    border: `1px solid ${leg.direction === 'over' ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                    color: leg.direction === 'over' ? '#22c55e' : '#ef4444',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    minWidth: 60,
                    textAlign: 'center',
                  }}
                >
                  {leg.direction === 'over' ? '\u2191 OVER' : '\u2193 UNDER'}
                </button>
                <input
                  type="number"
                  step="0.5"
                  value={leg.line}
                  onChange={(e) => updateLeg(idx, { line: parseFloat(e.target.value) || 0 })}
                  className="text-[0.75rem] tabular-nums w-16 text-center"
                  style={{
                    background: '#0a0a0a',
                    border: '1px solid #27272a',
                    color: '#e4e4e7',
                    padding: '0.25rem',
                    fontFamily: 'inherit',
                    outline: 'none',
                  }}
                />
                <span className="text-[0.7rem] tabular-nums" style={{ color: prob != null && prob >= 0.5 ? '#22c55e' : prob != null ? '#f59e0b' : '#52525b' }}>
                  {prob != null ? `${(prob * 100).toFixed(1)}%` : '—'}
                </span>
                <button
                  onClick={() => removeLeg(idx)}
                  className="text-[0.65rem] ml-auto"
                  style={{ color: '#71717a', cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'inherit' }}
                >
                  Remove
                </button>
              </div>
            )
          })}
        </div>
      )}

      {/* Combined probability */}
      {legs.length > 0 && (
        <div className="flex items-center justify-between px-3 py-2" style={{ background: '#141414', border: '1px solid #27272a' }}>
          <span className="text-[0.7rem] uppercase tracking-wide font-semibold" style={{ color: 'rgba(255,255,255,0.4)' }}>
            Combined Probability ({legs.length} legs)
          </span>
          <span className="text-[0.9rem] font-bold tabular-nums" style={{ color: combinedProb != null ? (combinedProb >= 0.3 ? '#22c55e' : '#f59e0b') : '#52525b' }}>
            {combinedProb != null ? `${(combinedProb * 100).toFixed(1)}%` : '—'}
          </span>
          {combinedProb != null && combinedProb > 0 && (
            <span className="text-[0.65rem] tabular-nums" style={{ color: 'rgba(255,255,255,0.3)' }}>
              Fair odds: {(1 / combinedProb).toFixed(2)}x
            </span>
          )}
          <button
            onClick={() => setLegs([])}
            className="text-[0.65rem] font-medium"
            style={{ color: '#ef4444', cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'inherit' }}
          >
            Clear All
          </button>
        </div>
      )}

      {legs.length === 0 && (
        <p className="text-[0.75rem] text-center py-4" style={{ color: 'rgba(255,255,255,0.25)' }}>
          Click a player above to add a kill line leg to your parlay.
        </p>
      )}
      <p className="text-[0.6rem] mt-2" style={{ color: 'rgba(255,255,255,0.2)' }}>
        Probabilities assume Normal distribution and independence between legs.
      </p>
    </Card>
  )
}

/* ─── Recent matches section ─────────────────────────────── */
function MatchRow({ match, color }: { match: RecentMatch; color: string }) {
  const resultColor = match.result === 'W' ? '#22c55e' : match.result === 'L' ? '#ef4444' : 'rgba(255,255,255,0.3)'
  return (
    <div className="flex items-center gap-2 py-1.5 text-[0.75rem]" style={{ borderBottom: '1px solid #18181b' }}>
      <span className="font-bold w-4 shrink-0 text-center" style={{ color: resultColor }}>
        {match.result ?? '?'}
      </span>
      <span className="flex-1 truncate" style={{ color: '#e4e4e7' }}>{match.opponent || 'Unknown'}</span>
      {match.score && (
        <span className="tabular-nums shrink-0" style={{ color: 'rgba(255,255,255,0.45)' }}>{match.score}</span>
      )}
    </div>
  )
}

function RecentMatchesSection({ t1, t2 }: { t1: TeamMatchupData; t2: TeamMatchupData }) {
  return (
    <Card style={{ padding: '1.25rem 1.5rem' }}>
      <SectionLabel>Recent Matches</SectionLabel>
      <div className="grid grid-cols-2 gap-6">
        {[
          { matches: t1.recent_matches.slice(0, 10), color: T1_COLOR },
          { matches: t2.recent_matches.slice(0, 10), color: T2_COLOR },
        ].map(({ matches, color }, idx) => (
          <div key={idx}>
            {matches.length === 0 ? (
              <p className="text-[0.75rem]" style={{ color: 'rgba(255,255,255,0.25)' }}>No match history</p>
            ) : (
              <div>
                {matches.map((m) => (
                  <MatchRow key={m.match_id} match={m} color={color} />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  )
}

/* ─── Head-to-Head section ───────────────────────────────── */
function HeadToHeadSection({
  h2h,
  team1Name,
  team2Name,
}: {
  h2h: H2HMatch[]
  team1Name: string
  team2Name: string
}) {
  if (h2h.length === 0) return null

  const t1Lower = team1Name.toLowerCase()

  return (
    <Card style={{ padding: '1.25rem 1.5rem' }}>
      <SectionLabel>Head-to-Head History ({h2h.length} matches)</SectionLabel>
      <div className="flex flex-col gap-1">
        {h2h.map((m) => {
          const t1won = m.winner ? t1Lower.split(' ').some((w) => (m.winner ?? '').toLowerCase().includes(w)) : null
          const t1maps = m.team1.toLowerCase().includes(t1Lower.split(' ')[0]) ? m.team1_maps : m.team2_maps
          const t2maps = m.team1.toLowerCase().includes(t1Lower.split(' ')[0]) ? m.team2_maps : m.team1_maps

          return (
            <div
              key={m.match_id}
              className="flex items-center gap-3 px-3 py-2 text-[0.75rem]"
              style={{ background: '#0f0f0f', border: '1px solid #1c1c1e' }}
            >
              <span className="flex-1 truncate" style={{ color: 'rgba(255,255,255,0.4)' }}>{m.event_name}</span>
              <div className="flex items-center gap-2 shrink-0">
                <span
                  className="font-semibold"
                  style={{ color: t1won === true ? T1_COLOR : t1won === false ? 'rgba(255,255,255,0.3)' : '#a1a1aa' }}
                >
                  {m.team1}
                </span>
                <span className="font-bold tabular-nums" style={{ color: '#e4e4e7' }}>
                  {t1maps ?? 0}–{t2maps ?? 0}
                </span>
                <span
                  className="font-semibold"
                  style={{ color: t1won === false ? T2_COLOR : t1won === true ? 'rgba(255,255,255,0.3)' : '#a1a1aa' }}
                >
                  {m.team2}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

/* ─── Odds bar ───────────────────────────────────────────── */
function OddsBar({ odds, t1Name, t2Name }: { odds: OddsInfo; t1Name: string; t2Name: string }) {
  const p1 = odds.team1_win_prob
  const p2 = odds.team2_win_prob
  return (
    <div
      className="rounded-none border px-4 py-3"
      style={{ background: '#0f0f0f', borderColor: '#27272a' }}
    >
      <div className="flex items-center justify-between mb-2 text-[0.7rem]">
        <span style={{ color: T1_COLOR, fontWeight: 600 }}>{t1Name}</span>
        <span style={{ color: 'rgba(255,255,255,0.3)' }}>Vig: {odds.vig_pct}%</span>
        <span style={{ color: T2_COLOR, fontWeight: 600 }}>{t2Name}</span>
      </div>
      <div className="flex h-3 rounded-full overflow-hidden">
        <div style={{ width: `${p1 * 100}%`, background: T1_COLOR }} />
        <div style={{ width: `${p2 * 100}%`, background: T2_COLOR }} />
      </div>
      <div className="flex items-center justify-between mt-1.5 text-[0.75rem]">
        <span className="font-bold tabular-nums" style={{ color: T1_COLOR }}>
          {(p1 * 100).toFixed(1)}% ({odds.team1_odds}x)
        </span>
        <span className="font-bold tabular-nums" style={{ color: T2_COLOR }}>
          ({odds.team2_odds}x) {(p2 * 100).toFixed(1)}%
        </span>
      </div>
    </div>
  )
}

/* ─── Column headers (team names) ────────────────────────── */
function TeamColumnHeaders({ t1Name, t2Name }: { t1Name: string; t2Name: string }) {
  return (
    <div className="grid grid-cols-2 gap-6 mb-1">
      <div
        className="px-3 py-2 text-sm font-bold uppercase tracking-wide text-center"
        style={{ background: T1_BG, border: `1px solid ${T1_BORDER}`, color: T1_COLOR }}
      >
        {t1Name}
      </div>
      <div
        className="px-3 py-2 text-sm font-bold uppercase tracking-wide text-center"
        style={{ background: T2_BG, border: `1px solid ${T2_BORDER}`, color: T2_COLOR }}
      >
        {t2Name}
      </div>
    </div>
  )
}

/* ─── Main MatchupPage component ─────────────────────────── */
export function MatchupPage({ data }: { data: MatchupData }) {
  const t1 = data.team1
  const t2 = data.team2
  const t1DisplayName = t1.overview?.resolved_name || t1.name
  const t2DisplayName = t2.overview?.resolved_name || t2.name

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div
        className="flex flex-wrap items-center justify-center gap-3 py-4 px-6 text-center"
        style={{ background: '#0f0f0f', border: '1px solid #27272a' }}
      >
        <span className="text-2xl font-bold tracking-tight" style={{ color: T1_COLOR }}>
          {t1DisplayName}
        </span>
        <span className="text-lg font-light" style={{ color: 'rgba(255,255,255,0.25)' }}>vs</span>
        <span className="text-2xl font-bold tracking-tight" style={{ color: T2_COLOR }}>
          {t2DisplayName}
        </span>
      </div>

      {/* Odds bar */}
      {data.odds && (
        <OddsBar odds={data.odds} t1Name={t1DisplayName} t2Name={t2DisplayName} />
      )}

      {/* Head-to-head */}
      {data.head_to_head.length > 0 && (
        <HeadToHeadSection h2h={data.head_to_head} team1Name={t1.name} team2Name={t2.name} />
      )}

      {/* Team column headers */}
      <TeamColumnHeaders t1Name={t1DisplayName} t2Name={t2DisplayName} />

      {/* Overview comparison */}
      <OverviewSection t1={t1.overview} t2={t2.overview} />

      {/* Projected map scores */}
      {data.projected_scores && Object.keys(data.projected_scores).length > 0 && (
        <ProjectedScoresSection
          projected={data.projected_scores}
          t1Name={t1DisplayName}
          t2Name={t2DisplayName}
        />
      )}

      {/* Map pool probabilities */}
      {data.map_probs && (
        <MapProbabilitySection data={data.map_probs} t1Name={t1DisplayName} t2Name={t2DisplayName} />
      )}

      {/* Kill line mispricing */}
      {data.mispricing && (
        <MispricingSection data={data.mispricing} t1Name={t1DisplayName} t2Name={t2DisplayName} />
      )}

      {/* Per-map K/D + fights/round */}
      <PerMapKDSection t1={t1} t2={t2} />

      {/* Map records */}
      <MapRecordsSection t1={t1} t2={t2} />

      {/* Pick/Ban tendencies */}
      <PickBanSection t1={t1} t2={t2} />

      {/* Agent comps */}
      <AgentCompsSection t1={t1} t2={t2} />

      {/* Player kill projections + parlay builder */}
      {data.player_kills && (
        <>
          <PlayerKillsSection
            playerKills={data.player_kills}
            t1Name={t1DisplayName}
            t2Name={t2DisplayName}
          />
          <ParlayBuilderSection playerKills={data.player_kills} />
        </>
      )}

      {/* Recent matches */}
      <RecentMatchesSection t1={t1} t2={t2} />
    </div>
  )
}
