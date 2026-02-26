'use client'

import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

/* ─── Types ─────────────────────────────────────────────── */
export interface Player {
  ign: string
  role: string
}

export interface MapChip {
  map: string
  rate: number
  type: 'first-pick' | 'second-pick' | 'first-ban' | 'second-ban'
}

export interface TeamEventStats {
  fpr: number
  kills: number
  deaths: number
  rounds: number
  matchesPlayed: number
  maps: MapChip[]
}

export interface TeamEvent {
  id: string
  date: string
  eventName: string
  stats: TeamEventStats
  defaultOpen?: boolean
}

export interface TeamData {
  name: string
  region: string
  players: Player[]
  fprAvg: number
  totalMatches: number
  avgKillsPerRound: number
  events: TeamEvent[]
}

/* ─── Map chip ───────────────────────────────────────────── */
const MAP_CHIP_STYLES: Record<MapChip['type'], { bg: string; border: string; color: string }> = {
  'first-pick': {
    bg: 'rgba(59,130,246,0.12)',
    border: 'rgba(59,130,246,0.3)',
    color: '#3b82f6',
  },
  'second-pick': {
    bg: 'rgba(14,165,233,0.12)',
    border: 'rgba(14,165,233,0.3)',
    color: '#0ea5e9',
  },
  'first-ban': {
    bg: 'rgba(239,68,68,0.12)',
    border: 'rgba(239,68,68,0.3)',
    color: '#ef4444',
  },
  'second-ban': {
    bg: 'rgba(239,68,68,0.07)',
    border: 'rgba(239,68,68,0.2)',
    color: '#f87171',
  },
}

function MapChipComponent({ map, rate, type }: MapChip) {
  const style = MAP_CHIP_STYLES[type]
  const width = Math.max(60, Math.min(120, 60 + rate * 0.6))

  return (
    <div
      className="flex flex-col items-center justify-center shrink-0 rounded-[8px] border px-2 py-2 gap-0.5"
      style={{
        background: style.bg,
        borderColor: style.border,
        width,
        minWidth: width,
      }}
    >
      <span className="text-[0.65rem] font-semibold uppercase tracking-wide truncate w-full text-center" style={{ color: style.color }}>
        {map}
      </span>
      <span className="text-[0.7rem] tabular-nums font-medium" style={{ color: '#a1a1aa' }}>
        {rate.toFixed(0)}%
      </span>
      <span className="text-[0.6rem] capitalize" style={{ color: '#52525b' }}>
        {type.replace('-', ' ')}
      </span>
    </div>
  )
}

/* ─── Stat pill ──────────────────────────────────────────── */
function StatPill({ label, value }: { label: string; value: string | number }) {
  return (
    <div
      className="flex flex-col items-center px-4 py-2.5 rounded-[8px] border"
      style={{ background: '#0a0a0a', borderColor: '#27272a' }}
    >
      <span className="text-[0.65rem] uppercase tracking-[0.1em]" style={{ color: '#52525b' }}>
        {label}
      </span>
      <span
        className="font-bold tabular-nums mt-0.5"
        style={{ fontSize: '1.25rem', color: '#ffffff' }}
      >
        {value}
      </span>
    </div>
  )
}

/* ─── Event timeline item ────────────────────────────────── */
function TeamEventItem({ date, eventName, stats, defaultOpen = false }: TeamEvent) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className="flex gap-4">
      {/* Timeline spine */}
      <div className="flex flex-col items-center pt-1">
        <div
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: '#3b82f6' }}
        />
        <div className="flex-1 w-px mt-1" style={{ background: '#27272a' }} />
      </div>

      {/* Card */}
      <div
        className="flex-1 rounded-[12px] border mb-4 overflow-hidden"
        style={{ background: '#0a0a0a', borderColor: '#27272a' }}
      >
        <button
          className="w-full flex items-center gap-3 px-4 py-3 text-left transition-colors"
          onClick={() => setOpen((v) => !v)}
          style={{ background: open ? '#0f0f0f' : 'transparent' }}
          onMouseEnter={(e) =>
            ((e.currentTarget as HTMLButtonElement).style.background = '#0f0f0f')
          }
          onMouseLeave={(e) =>
            ((e.currentTarget as HTMLButtonElement).style.background = open ? '#0f0f0f' : 'transparent')
          }
        >
          <span style={{ color: '#52525b' }}>
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
          <span className="font-semibold text-sm" style={{ color: '#ffffff' }}>
            {eventName}
          </span>
          <span className="text-[0.75rem] ml-auto shrink-0" style={{ color: '#71717a' }}>
            {date}
          </span>
        </button>

        {open && (
          <div className="border-t px-4 py-4 flex flex-col gap-4" style={{ borderColor: '#27272a' }}>
            {/* Stats grid */}
            <div className="flex flex-wrap gap-2">
              <StatPill label="FPR" value={stats.fpr.toFixed(3)} />
              <StatPill label="Kills" value={stats.kills} />
              <StatPill label="Deaths" value={stats.deaths} />
              <StatPill label="Rounds" value={stats.rounds} />
              <StatPill label="Matches" value={stats.matchesPlayed} />
            </div>

            {/* Map performance */}
            {stats.maps.length > 0 && (
              <div>
                <p
                  className="text-[0.65rem] uppercase tracking-[0.1em] mb-2"
                  style={{ color: '#52525b' }}
                >
                  Map Performance
                </p>
                <div
                  className="flex gap-2 overflow-x-auto pb-1"
                  style={{ scrollbarWidth: 'thin' }}
                >
                  {stats.maps.map((m, i) => (
                    <MapChipComponent key={i} {...m} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/* ─── Main TeamPage ──────────────────────────────────────── */
export function TeamPage({ team }: { team: TeamData }) {
  return (
    <div className="flex flex-col gap-6">
      {/* Team header card */}
      <div
        className="rounded-[12px] border p-5"
        style={{ background: '#0a0a0a', borderColor: '#27272a' }}
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h1
                className="font-bold tracking-tight"
                style={{ fontSize: '2rem', color: '#ffffff' }}
              >
                {team.name}
              </h1>
              <span
                className="text-[0.7rem] uppercase tracking-widest px-2 py-1 rounded-[6px] font-semibold"
                style={{
                  background: 'rgba(59,130,246,0.12)',
                  color: '#3b82f6',
                  border: '1px solid rgba(59,130,246,0.25)',
                }}
              >
                {team.region}
              </span>
            </div>

            {/* Roster pills */}
            <div className="flex flex-wrap gap-1.5 mt-3">
              {team.players.map((p) => (
                <span
                  key={p.ign}
                  className="text-[0.75rem] px-2.5 py-1 rounded-[6px] font-medium"
                  style={{
                    background: '#18181b',
                    color: '#a1a1aa',
                    border: '1px solid #27272a',
                  }}
                >
                  {p.ign}
                  <span className="ml-1.5 text-[0.65rem]" style={{ color: '#52525b' }}>
                    {p.role}
                  </span>
                </span>
              ))}
            </div>
          </div>

          {/* Summary stats */}
          <div className="flex gap-3 flex-wrap">
            <StatPill label="FPR Avg" value={team.fprAvg.toFixed(3)} />
            <StatPill label="Total Matches" value={team.totalMatches} />
            <StatPill label="Avg K/R" value={team.avgKillsPerRound.toFixed(2)} />
          </div>
        </div>
      </div>

      {/* Event timeline */}
      <div>
        <h2
          className="text-[0.7rem] uppercase tracking-[0.1em] mb-4"
          style={{ color: '#52525b' }}
        >
          Event Timeline
        </h2>
        <div>
          {team.events.map((ev) => (
            <TeamEventItem key={ev.id} {...ev} />
          ))}
        </div>
      </div>
    </div>
  )
}
