'use client'

import { useState } from 'react'
import { Search, Loader2, ChevronDown, ChevronRight, Users } from 'lucide-react'
import { AppHeader } from '@/components/app-header'

/* ─── API response types ─────────────────────────────────── */
interface PickBanRates {
  first_ban: Record<string, number>
  second_ban: Record<string, number>
  first_pick: Record<string, number>
  second_pick: Record<string, number>
}

interface TeamEvent {
  event_name: string
  matches_played: number
  total_rounds: number
  total_kills: number
  total_deaths: number
  fights_per_round: number | string
  pick_ban_rates: PickBanRates
}

interface TeamAnalysis {
  team_name: string
  roster: string[]
  events: TeamEvent[]
}

/* ─── Event accordion ────────────────────────────────────── */
const PICK_BAN_TYPES: { key: keyof PickBanRates; label: string; color: string; dimColor: string }[] = [
  { key: 'first_pick', label: 'First Pick', color: '#3b82f6', dimColor: 'rgba(59,130,246,0.12)' },
  { key: 'second_pick', label: 'Second Pick', color: '#0ea5e9', dimColor: 'rgba(14,165,233,0.12)' },
  { key: 'first_ban', label: 'First Ban', color: '#ef4444', dimColor: 'rgba(239,68,68,0.12)' },
  { key: 'second_ban', label: 'Second Ban', color: '#f87171', dimColor: 'rgba(239,68,68,0.08)' },
]

function EventAccordion({ event, defaultOpen = false }: { event: TeamEvent; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)

  const hasPickBan = PICK_BAN_TYPES.some((t) => Object.keys(event.pick_ban_rates[t.key] ?? {}).length > 0)

  return (
    <div
      className="rounded-[10px] border overflow-hidden"
      style={{ background: '#0a0a0a', borderColor: '#27272a' }}
    >
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left transition-colors"
        onClick={() => setOpen((v) => !v)}
        style={{ background: open ? '#111111' : 'transparent' }}
        onMouseEnter={(e) => ((e.currentTarget as HTMLButtonElement).style.background = '#111111')}
        onMouseLeave={(e) => ((e.currentTarget as HTMLButtonElement).style.background = open ? '#111111' : 'transparent')}
      >
        <span style={{ color: '#52525b' }}>
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <span className="font-semibold text-sm flex-1 min-w-0 truncate" style={{ color: '#ffffff' }}>
          {event.event_name}
        </span>
        <span className="text-[0.7rem] shrink-0 tabular-nums" style={{ color: '#71717a' }}>
          {event.matches_played} matches
        </span>
      </button>

      {open && (
        <div className="border-t px-4 py-4 flex flex-col gap-4" style={{ borderColor: '#1a1a1a' }}>
          {/* Stats row */}
          <div className="flex flex-wrap gap-2">
            {[
              { label: 'Fights/Round', value: typeof event.fights_per_round === 'number' ? event.fights_per_round.toFixed(3) : event.fights_per_round },
              { label: 'Total Kills', value: event.total_kills },
              { label: 'Total Deaths', value: event.total_deaths },
              { label: 'Total Rounds', value: event.total_rounds },
              { label: 'Matches', value: event.matches_played },
            ].map(({ label, value }) => (
              <div
                key={label}
                className="flex flex-col items-center px-4 py-2.5 rounded-[8px] border"
                style={{ background: '#111111', borderColor: '#27272a' }}
              >
                <span className="text-[0.6rem] uppercase tracking-[0.1em]" style={{ color: '#52525b' }}>
                  {label}
                </span>
                <span className="font-bold tabular-nums mt-0.5" style={{ fontSize: '1.25rem', color: '#ffffff' }}>
                  {value}
                </span>
              </div>
            ))}
          </div>

          {/* Pick/ban */}
          {hasPickBan ? (
            <div>
              <p className="text-[0.65rem] uppercase tracking-[0.1em] mb-2" style={{ color: '#52525b' }}>
                Map Pick/Ban Rates
              </p>
              <div
                className="grid gap-3"
                style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}
              >
                {PICK_BAN_TYPES.map(({ key, label, color, dimColor }) => {
                  const rates = event.pick_ban_rates[key] ?? {}
                  const entries = Object.entries(rates)
                  if (entries.length === 0) return null
                  return (
                    <div
                      key={key}
                      className="rounded-[8px] p-3"
                      style={{ background: dimColor, border: `1px solid ${color}40` }}
                    >
                      <p className="text-[0.65rem] font-semibold uppercase tracking-wider mb-2" style={{ color }}>
                        {label}
                      </p>
                      <div className="flex flex-col gap-1.5">
                        {entries.map(([map, pct]) => (
                          <div key={map} className="flex justify-between items-center">
                            <span className="text-[0.8rem]" style={{ color: '#e4e4e7' }}>{map}</span>
                            <span className="text-[0.8rem] font-semibold tabular-nums" style={{ color }}>{pct}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ) : (
            <p className="text-sm" style={{ color: '#71717a' }}>No pick/ban data available</p>
          )}
        </div>
      )}
    </div>
  )
}

/* ─── Main page ──────────────────────────────────────────── */
export default function TeamPage() {
  const [teamName, setTeamName] = useState('')
  const [region, setRegion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [analysis, setAnalysis] = useState<TeamAnalysis | null>(null)
  const [elapsed, setElapsed] = useState<number | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const name = teamName.trim()
    if (!name) { setError('Please enter a team name'); return }

    setLoading(true)
    setError(null)
    setAnalysis(null)

    try {
      const t0 = performance.now()
      let url = `/api/team/${encodeURIComponent(name)}`
      if (region.trim()) url += `?region=${encodeURIComponent(region.trim())}`
      const res = await fetch(url)
      const data = await res.json()
      setElapsed((performance.now() - t0) / 1000)

      if (data.error) { setError(data.error); return }
      if (!data.analysis) { setError('No analysis data received'); return }
      setAnalysis(data.analysis)
    } catch (err) {
      setError('Error connecting to server: ' + (err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <AppHeader activePage="/team" />

      <main className="page-container py-8 flex flex-col gap-6">
        {/* Hero */}
        <div className="text-center pt-4 pb-2">
          <h1
            className="font-bold uppercase tracking-tight text-balance"
            style={{ fontFamily: '"Barlow Condensed", sans-serif', fontSize: 'clamp(2rem, 6vw, 4rem)', color: '#ffffff' }}
          >
            VCT Team Analysis
          </h1>
          <p className="text-sm mt-1" style={{ color: 'rgba(255,255,255,0.5)' }}>
            Team statistics, fights per round, and map pick/ban rates
          </p>
        </div>

        {/* Search */}
        <form onSubmit={handleSubmit}>
          <div
            className="p-6 flex flex-col gap-4"
            style={{ background: '#141210', border: '1px solid rgba(249,115,22,0.15)', borderLeft: '3px solid #F97316' }}
          >
            <div className="flex flex-col gap-1.5">
              <label className="text-[0.7rem] uppercase tracking-[0.12em] font-medium" style={{ color: '#a1a1aa' }}>
                Team Name
              </label>
              <input
                type="text"
                value={teamName}
                onChange={(e) => setTeamName(e.target.value)}
                placeholder="Sentinels, LOUD, Fnatic..."
                className="h-11 px-3 rounded-[8px] border text-sm outline-none"
                style={{ background: '#0a0a0a', borderColor: '#27272a', color: '#ffffff' }}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-[0.7rem] uppercase tracking-[0.12em] font-medium" style={{ color: '#a1a1aa' }}>
                Region <span className="normal-case tracking-normal text-[0.65rem]" style={{ color: '#52525b' }}>(Optional)</span>
              </label>
              <input
                type="text"
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                placeholder="Americas, EMEA, Pacific, China"
                className="h-11 px-3 rounded-[8px] border text-sm outline-none"
                style={{ background: '#0a0a0a', borderColor: '#27272a', color: '#ffffff' }}
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="h-11 flex items-center justify-center gap-2 font-bold uppercase tracking-wide text-sm disabled:opacity-50"
              style={{ background: '#F97316', color: '#000', fontFamily: '"Barlow Condensed", sans-serif', fontSize: '0.9rem' }}
            >
              {loading ? <><Loader2 size={15} className="animate-spin" /> Analyzing...</> : <>Analyze Team</>}
            </button>
          </div>
        </form>

        {/* Error */}
        {error && (
          <div
            className="px-4 py-3 text-sm font-semibold rounded-[8px]"
            style={{ background: 'rgba(127,29,29,1)', border: '1px solid #991b1b', color: '#fca5a5' }}
          >
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex flex-col items-center gap-3 py-12">
            <div
              className="w-10 h-10 rounded-full border-t-2"
              style={{ borderColor: '#27272a', borderTopColor: '#3b82f6', animation: 'spin 1s linear infinite' }}
            />
            <p className="font-semibold text-sm" style={{ color: '#e4e4e7' }}>Fetching Team Data</p>
            <p className="text-sm" style={{ color: '#71717a' }}>Scraping team statistics from VLR.gg...</p>
            <style>{`@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}`}</style>
          </div>
        )}

        {/* Results */}
        {analysis && !loading && (
          <div
            className="rounded-[12px] border p-6"
            style={{ background: '#18181b', borderColor: '#27272a' }}
          >
            {/* Team header */}
            <div className="flex justify-between items-start pb-5 mb-5 border-b flex-wrap gap-4" style={{ borderColor: '#27272a' }}>
              <div>
                <h2 className="font-bold" style={{ fontSize: '2rem', color: '#ffffff' }}>
                  {analysis.team_name}
                </h2>
                <div className="flex flex-wrap gap-2 mt-2">
                  {analysis.roster.map((player) => (
                    <span
                      key={player}
                      className="text-[0.8rem] px-3 py-1 rounded-[6px]"
                      style={{ background: '#0a0a0a', border: '1px solid #27272a', color: '#e4e4e7' }}
                    >
                      {player}
                    </span>
                  ))}
                </div>
              </div>
              {elapsed !== null && (
                <span className="text-sm" style={{ color: '#71717a' }}>
                  Query time: {elapsed.toFixed(2)}s
                </span>
              )}
            </div>

            {/* Events */}
            <div className="flex flex-col gap-3">
              {analysis.events.length > 0 ? (
                analysis.events.map((ev, i) => (
                  <EventAccordion key={i} event={ev} defaultOpen={i === 0} />
                ))
              ) : (
                <p className="text-sm" style={{ color: '#71717a' }}>No events found for this team</p>
              )}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!analysis && !loading && !error && (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Users size={56} style={{ color: '#ffffff', opacity: 0.1 }} />
            <p className="text-sm" style={{ color: 'rgba(255,255,255,0.25)' }}>
              Enter a team name above to start analysis
            </p>
            <p className="text-xs" style={{ color: 'rgba(255,255,255,0.15)' }}>
              e.g. Sentinels, LOUD, Fnatic, NRG
            </p>
          </div>
        )}
      </main>
    </>
  )
}
