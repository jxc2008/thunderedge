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

export interface TeamMatchupData {
  name: string
  overview: TeamOverview
  pick_ban: PickBanStats
  map_records: MapRecord[]
  recent_matches: RecentMatch[]
  comps_per_map: Record<string, CompEntry[]>
}

export interface PoolEntry {
  maps: [string, string, string]
  prob: number
  theo: number
  data_w: number
}

export interface PredictionResult {
  expected_theo: number
  model_confidence: 'HIGH' | 'MED' | 'LOW'
  data_weight: number
  top_pools: PoolEntry[]
  team_a_data: { n: number; alpha: number }
  team_b_data: { n: number; alpha: number }
}

export interface MatchupData {
  team1: TeamMatchupData
  team2: TeamMatchupData
  head_to_head: H2HMatch[]
  odds: OddsInfo | null
  prediction?: PredictionResult | null
  ask?: number
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
  const pct = Math.round(rate * 100)
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full" style={{ background: '#27272a' }}>
        <div className="h-full rounded-full" style={{ width: `${Math.min(100, pct)}%`, background: color }} />
      </div>
      <span className="text-[0.7rem] tabular-nums w-10 text-right" style={{ color: 'rgba(255,255,255,0.6)' }}>
        {pct}%
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

/* ─── Prediction panel ───────────────────────────────────── */
function confColor(conf: string) {
  if (conf === 'HIGH') return '#22c55e'
  if (conf === 'MED')  return '#f59e0b'
  return '#71717a'
}

function PredictionPanel({
  pred,
  ask,
  t1Name,
  t2Name,
}: {
  pred: PredictionResult
  ask: number
  t1Name: string
  t2Name: string
}) {
  const edge = pred.expected_theo - ask / 100
  const edgeAbs = Math.abs(edge)
  const edgeColor = edgeAbs >= 0.05 ? (edge > 0 ? '#22c55e' : '#ef4444')
                  : edgeAbs >= 0.02 ? '#f59e0b'
                  : '#71717a'
  const side = edge > 0 ? `BUY YES (${t1Name})` : `BUY NO (${t2Name})`

  return (
    <Card style={{ padding: '1.25rem 1.5rem' }}>
      <SectionLabel>Model Prediction (Pre-Veto)</SectionLabel>

      {/* Summary row */}
      <div className="flex flex-wrap gap-4 mb-4">
        <div>
          <p className="text-[0.6rem] uppercase tracking-wide mb-0.5" style={{ color: 'rgba(255,255,255,0.3)' }}>
            Expected Theo
          </p>
          <p className="text-2xl font-bold tabular-nums" style={{ color: '#e4e4e7' }}>
            {(pred.expected_theo * 100).toFixed(1)}c
          </p>
        </div>
        <div>
          <p className="text-[0.6rem] uppercase tracking-wide mb-0.5" style={{ color: 'rgba(255,255,255,0.3)' }}>
            Kalshi Ask
          </p>
          <p className="text-2xl font-bold tabular-nums" style={{ color: 'rgba(255,255,255,0.45)' }}>
            {ask}c
          </p>
        </div>
        <div>
          <p className="text-[0.6rem] uppercase tracking-wide mb-0.5" style={{ color: 'rgba(255,255,255,0.3)' }}>
            Edge
          </p>
          <p className="text-2xl font-bold tabular-nums" style={{ color: edgeColor }}>
            {edge >= 0 ? '+' : ''}{(edge * 100).toFixed(1)}c
          </p>
        </div>
        <div>
          <p className="text-[0.6rem] uppercase tracking-wide mb-0.5" style={{ color: 'rgba(255,255,255,0.3)' }}>
            Signal
          </p>
          <p className="text-sm font-bold" style={{ color: edgeColor }}>
            {edgeAbs >= 0.02 ? side : 'No edge'}
          </p>
        </div>
        <div>
          <p className="text-[0.6rem] uppercase tracking-wide mb-0.5" style={{ color: 'rgba(255,255,255,0.3)' }}>
            Confidence
          </p>
          <p className="text-sm font-bold" style={{ color: confColor(pred.model_confidence) }}>
            {pred.model_confidence}
          </p>
        </div>
      </div>

      {/* Data coverage */}
      <div className="flex gap-4 mb-4 text-[0.7rem]" style={{ color: 'rgba(255,255,255,0.4)' }}>
        <span style={{ color: T1_COLOR }}>{t1Name}: n={pred.team_a_data.n} alpha={pred.team_a_data.alpha.toFixed(2)}</span>
        <span style={{ color: T2_COLOR }}>{t2Name}: n={pred.team_b_data.n} alpha={pred.team_b_data.alpha.toFixed(2)}</span>
      </div>

      {/* Top map pools */}
      {pred.top_pools.length > 0 && (
        <div>
          <p className="text-[0.6rem] uppercase tracking-[0.12em] mb-2" style={{ color: 'rgba(255,255,255,0.25)' }}>
            Top Predicted Map Pools
          </p>
          <div className="flex flex-col gap-1">
            {pred.top_pools.slice(0, 6).map((p, i) => {
              const poolEdge = p.theo - ask / 100
              const poolEdgeColor = Math.abs(poolEdge) >= 0.05
                ? (poolEdge > 0 ? '#22c55e' : '#ef4444')
                : '#71717a'
              return (
                <div
                  key={p.maps.join('/')}
                  className="flex items-center gap-3 px-3 py-1.5 text-[0.75rem]"
                  style={{ background: i === 0 ? '#0f0f0f' : 'transparent', border: `1px solid ${i === 0 ? '#27272a' : '#1c1c1e'}` }}
                >
                  <span className="tabular-nums w-10 text-right shrink-0" style={{ color: 'rgba(255,255,255,0.4)' }}>
                    {(p.prob * 100).toFixed(1)}%
                  </span>
                  <span className="flex-1" style={{ color: '#e4e4e7' }}>
                    {p.maps[0]} &middot; {p.maps[1]} &middot; {p.maps[2]}
                  </span>
                  <span className="tabular-nums shrink-0" style={{ color: poolEdgeColor }}>
                    {p.theo > ask / 100 ? '+' : ''}{((p.theo - ask / 100) * 100).toFixed(1)}c
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </Card>
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

      {/* Map records */}
      <MapRecordsSection t1={t1} t2={t2} />

      {/* Model prediction */}
      {data.prediction && (
        <PredictionPanel
          pred={data.prediction}
          ask={data.ask ?? 50}
          t1Name={t1DisplayName}
          t2Name={t2DisplayName}
        />
      )}

      {/* Pick/Ban tendencies */}
      <PickBanSection t1={t1} t2={t2} />

      {/* Agent comps */}
      <AgentCompsSection t1={t1} t2={t2} />

      {/* Recent matches */}
      <RecentMatchesSection t1={t1} t2={t2} />
    </div>
  )
}
