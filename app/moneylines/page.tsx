'use client'

import { useEffect, useState } from 'react'
import { Loader2, TrendingUp, RefreshCw } from 'lucide-react'
import { AppHeader } from '@/components/app-header'

/* ─── API response types ─────────────────────────────────── */
interface UpcomingPick {
  team_a?: string
  team_b?: string
  teamA?: string
  teamB?: string
  market_odds?: string
  marketOdds?: string
  model_p_fair?: number
  modelPFair?: number
  recommendation?: string
}

interface BetLogEntry {
  date: string
  matchup: string
  odds: string
  result: string
  profit: number
  flagged?: boolean
}

interface WalkForwardRow {
  year: number | string
  bets: number
  record: string
  roi: number
  avgOdds?: string
  isTotal?: boolean
}

interface MonthlyRow {
  month: string
  bets: number
  roi: number
  record: string
}

interface ConsistencyData {
  currentStreak?: { type: string; count: number }
  longestWin?: number
  longestLoss?: number
  winRate?: number
  avgReturn?: number
  stdDev?: number
}

interface Strategy {
  method?: string
  baseStake?: number
  maxStake?: number
  minEdgePct?: number
}

interface StrategyData {
  success?: boolean
  upcomingPicks?: UpcomingPick[]
  betLog?: BetLogEntry[]
  walkForward?: WalkForwardRow[]
  monthly?: MonthlyRow[]
  consistency?: ConsistencyData
  strategy?: Strategy
  roi?: number
  record?: string
  activeBetsToday?: number
}

interface MoneylineStats {
  success?: boolean
  heavy_fav_win_rate?: number
  moderate_fav_win_rate?: number
  even_win_rate?: number
  total_matches?: number
}

/* ─── Small stat card ────────────────────────────────────── */
function StatCard({ label, value, detail, color = '#ffffff' }: { label: string; value: string | number; detail?: string; color?: string }) {
  return (
    <div
      className="rounded-[10px] border p-4 flex flex-col gap-1"
      style={{ background: '#0a0a0a', borderColor: '#27272a' }}
    >
      <p className="text-[0.65rem] uppercase tracking-[0.1em]" style={{ color: '#71717a' }}>{label}</p>
      <p className="font-bold tabular-nums" style={{ fontSize: '1.5rem', color }}>{value}</p>
      {detail && <p className="text-[0.7rem]" style={{ color: '#52525b' }}>{detail}</p>}
    </div>
  )
}

/* ─── Section wrapper ────────────────────────────────────── */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-4">
      <h2
        className="font-bold uppercase tracking-wider pb-3 border-b"
        style={{ fontFamily: '"Barlow Condensed", sans-serif', fontSize: '1.1rem', color: '#ffffff', borderColor: 'rgba(255,255,255,0.06)' }}
      >
        {title}
      </h2>
      {children}
    </div>
  )
}

/* ─── Main page ──────────────────────────────────────────── */
export default function MoneyLinesPage() {
  const [strategyData, setStrategyData] = useState<StrategyData | null>(null)
  const [stats, setStats] = useState<MoneylineStats | null>(null)
  const [upcoming, setUpcoming] = useState<UpcomingPick[]>([])
  const [loading, setLoading] = useState(true)
  const [upcomingLoading, setUpcomingLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchData() {
      setLoading(true)
      try {
        const [stratRes, statsRes] = await Promise.all([
          fetch('/api/moneylines/strategy'),
          fetch('/api/moneylines/stats'),
        ])
        const stratJson = await stratRes.json()
        const statsJson = await statsRes.json()
        if (stratJson.success !== false) setStrategyData(stratJson)
        if (statsJson.success !== false) setStats(statsJson)
      } catch (err) {
        setError('Failed to load moneyline data: ' + (err as Error).message)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  async function fetchUpcoming() {
    setUpcomingLoading(true)
    try {
      const res = await fetch('/api/moneylines/upcoming')
      const data = await res.json()
      if (data.picks) setUpcoming(data.picks)
      else if (Array.isArray(data)) setUpcoming(data)
    } catch {
      // silently fail
    } finally {
      setUpcomingLoading(false)
    }
  }

  function recColor(rec?: string): string {
    if (!rec) return '#71717a'
    const r = rec.toUpperCase()
    if (r === 'BET') return '#22c55e'
    if (r === 'SKIP') return '#ef4444'
    return '#f59e0b'
  }

  function roiColor(roi: number): string {
    return roi >= 0 ? '#22c55e' : '#ef4444'
  }

  return (
    <>
      <AppHeader activePage="/moneylines" />

      <main className="page-container py-8 flex flex-col gap-8">
        {/* Hero */}
        <div className="text-center pt-4 pb-2">
          <h1
            className="font-bold uppercase tracking-tight text-balance"
            style={{ fontFamily: '"Barlow Condensed", sans-serif', fontSize: 'clamp(2rem, 6vw, 4rem)', color: '#ffffff' }}
          >
            MoneyLine Strategy
          </h1>
          <p className="text-sm mt-1" style={{ color: 'rgba(255,255,255,0.5)' }}>
            Walk-forward backtested moneyline strategy results and upcoming picks
          </p>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center gap-3 py-16">
            <Loader2 size={20} className="animate-spin" style={{ color: '#16a34a' }} />
            <span className="text-sm" style={{ color: '#71717a' }}>Loading strategy data...</span>
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div
            className="px-4 py-3 text-sm font-semibold rounded-[8px]"
            style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444' }}
          >
            {error}
          </div>
        )}

        {/* No data state */}
        {!loading && !strategyData && !error && (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <TrendingUp size={56} style={{ color: '#ffffff', opacity: 0.1 }} />
            <p className="text-sm" style={{ color: 'rgba(255,255,255,0.25)' }}>
              No moneyline data available
            </p>
            <p className="text-xs" style={{ color: 'rgba(255,255,255,0.15)' }}>
              Run: python scripts/populate_moneyline.py
            </p>
          </div>
        )}

        {/* Main content */}
        {strategyData && !loading && (
          <div className="flex flex-col gap-10">

            {/* Summary stats */}
            <Section title="Strategy Overview">
              <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
                {strategyData.roi !== undefined && (
                  <StatCard label="Overall ROI" value={`${strategyData.roi >= 0 ? '+' : ''}${strategyData.roi?.toFixed(1)}%`} detail="walk-forward" color={roiColor(strategyData.roi ?? 0)} />
                )}
                {strategyData.record && (
                  <StatCard label="Record" value={strategyData.record} detail="all time" />
                )}
                {stats?.heavy_fav_win_rate !== undefined && (
                  <StatCard label="Heavy Fav Win Rate" value={`${(stats.heavy_fav_win_rate * 100).toFixed(1)}%`} detail=">70% implied" color="#3b82f6" />
                )}
                {stats?.moderate_fav_win_rate !== undefined && (
                  <StatCard label="Moderate Fav Win Rate" value={`${(stats.moderate_fav_win_rate * 100).toFixed(1)}%`} detail="55–70% implied" color="#0ea5e9" />
                )}
                {stats?.even_win_rate !== undefined && (
                  <StatCard label="Even Match Win Rate" value={`${(stats.even_win_rate * 100).toFixed(1)}%`} detail="45–55% implied" />
                )}
                {stats?.total_matches !== undefined && (
                  <StatCard label="Total Matches" value={stats.total_matches} detail="in database" />
                )}
              </div>
            </Section>

            {/* Upcoming picks */}
            <Section title="Upcoming Picks">
              <button
                onClick={fetchUpcoming}
                disabled={upcomingLoading}
                className="self-start flex items-center gap-2 px-4 py-2 rounded-[8px] text-sm font-medium disabled:opacity-50"
                style={{ background: 'rgba(22,163,74,0.15)', border: '1px solid rgba(22,163,74,0.3)', color: '#16a34a' }}
              >
                {upcomingLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                Fetch Upcoming Matches
              </button>
              {upcoming.length > 0 && (
                <div className="overflow-x-auto rounded-[10px] border" style={{ borderColor: '#27272a' }}>
                  <table className="w-full border-collapse text-sm" style={{ minWidth: 480 }}>
                    <thead>
                      <tr style={{ background: '#111111' }}>
                        {['Matchup', 'Market Odds', 'Model P(Fair)', 'Recommendation'].map((h) => (
                          <th key={h} className="text-left py-3 px-4 text-[0.65rem] uppercase tracking-wider" style={{ color: '#71717a', borderBottom: '1px solid #27272a' }}>
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {upcoming.map((pick, i) => {
                        const teamA = pick.teamA ?? pick.team_a ?? '?'
                        const teamB = pick.teamB ?? pick.team_b ?? '?'
                        const odds = pick.marketOdds ?? pick.market_odds ?? '—'
                        const pFair = pick.modelPFair ?? pick.model_p_fair
                        const rec = pick.recommendation
                        return (
                          <tr key={i} style={{ borderBottom: '1px solid #1a1a1a' }}>
                            <td className="py-3 px-4 font-medium" style={{ color: '#e4e4e7' }}>{teamA} vs {teamB}</td>
                            <td className="py-3 px-4 tabular-nums" style={{ color: '#a1a1aa' }}>{odds}</td>
                            <td className="py-3 px-4 tabular-nums" style={{ color: '#ffffff' }}>
                              {pFair !== undefined ? `${(pFair * 100).toFixed(1)}%` : '—'}
                            </td>
                            <td className="py-3 px-4">
                              <span
                                className="text-[0.7rem] font-bold uppercase tracking-wider px-2 py-1"
                                style={{
                                  background: `${recColor(rec)}20`,
                                  color: recColor(rec),
                                  border: `1px solid ${recColor(rec)}40`,
                                }}
                              >
                                {rec ?? '—'}
                              </span>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              {upcoming.length === 0 && !upcomingLoading && (
                <p className="text-sm" style={{ color: '#71717a' }}>
                  Click above to fetch upcoming match picks
                </p>
              )}
            </Section>

            {/* Walk-forward results */}
            {strategyData.walkForward && strategyData.walkForward.length > 0 && (
              <Section title="Walk-Forward Results">
                <div className="overflow-x-auto rounded-[10px] border" style={{ borderColor: '#27272a' }}>
                  <table className="w-full border-collapse text-sm" style={{ minWidth: 400 }}>
                    <thead>
                      <tr style={{ background: '#111111' }}>
                        {['Year', 'Bets', 'Record', 'ROI', 'Avg Odds'].map((h) => (
                          <th key={h} className="text-left py-3 px-4 text-[0.65rem] uppercase tracking-wider" style={{ color: '#71717a', borderBottom: '1px solid #27272a' }}>
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {strategyData.walkForward.map((row, i) => (
                        <tr
                          key={i}
                          style={{
                            borderBottom: '1px solid #1a1a1a',
                            background: row.isTotal ? '#0f1a0f' : 'transparent',
                            fontWeight: row.isTotal ? 700 : 400,
                          }}
                        >
                          <td className="py-3 px-4" style={{ color: row.isTotal ? '#16a34a' : '#e4e4e7' }}>{row.year}</td>
                          <td className="py-3 px-4 tabular-nums" style={{ color: '#a1a1aa' }}>{row.bets}</td>
                          <td className="py-3 px-4 tabular-nums" style={{ color: '#e4e4e7' }}>{row.record}</td>
                          <td className="py-3 px-4 tabular-nums font-semibold" style={{ color: roiColor(row.roi) }}>
                            {row.roi >= 0 ? '+' : ''}{row.roi.toFixed(1)}%
                          </td>
                          <td className="py-3 px-4 tabular-nums" style={{ color: '#a1a1aa' }}>{row.avgOdds ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Section>
            )}

            {/* Bet log */}
            {strategyData.betLog && strategyData.betLog.length > 0 && (
              <Section title="Bet Log">
                <div className="overflow-x-auto rounded-[10px] border" style={{ borderColor: '#27272a' }}>
                  <table className="w-full border-collapse text-sm" style={{ minWidth: 480 }}>
                    <thead>
                      <tr style={{ background: '#111111' }}>
                        {['Date', 'Matchup', 'Odds', 'Result', 'P/L'].map((h) => (
                          <th key={h} className="text-left py-3 px-4 text-[0.65rem] uppercase tracking-wider" style={{ color: '#71717a', borderBottom: '1px solid #27272a' }}>
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {strategyData.betLog.map((entry, i) => (
                        <tr
                          key={i}
                          style={{
                            borderBottom: '1px solid #1a1a1a',
                            background: entry.flagged ? 'rgba(245,158,11,0.04)' : 'transparent',
                          }}
                        >
                          <td className="py-2.5 px-4 tabular-nums" style={{ color: '#71717a' }}>{entry.date}</td>
                          <td className="py-2.5 px-4" style={{ color: '#e4e4e7' }}>
                            {entry.matchup}
                            {entry.flagged && (
                              <span className="ml-2 text-[0.6rem] px-1.5 py-0.5 rounded" style={{ background: 'rgba(245,158,11,0.15)', color: '#f59e0b' }}>
                                flagged
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 px-4 tabular-nums" style={{ color: '#a1a1aa' }}>{entry.odds}</td>
                          <td
                            className="py-2.5 px-4 font-bold"
                            style={{ color: entry.result === 'W' ? '#22c55e' : entry.result === 'L' ? '#ef4444' : '#f59e0b' }}
                          >
                            {entry.result}
                          </td>
                          <td
                            className="py-2.5 px-4 tabular-nums font-semibold"
                            style={{ color: entry.profit > 0 ? '#22c55e' : entry.profit < 0 ? '#ef4444' : '#a1a1aa' }}
                          >
                            {entry.profit > 0 ? '+' : ''}{entry.profit.toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Section>
            )}

            {/* Monthly breakdown */}
            {strategyData.monthly && strategyData.monthly.length > 0 && (
              <Section title="Monthly Breakdown">
                <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}>
                  {strategyData.monthly.map((m, i) => (
                    <div
                      key={i}
                      className="rounded-[10px] border p-4"
                      style={{ background: '#0a0a0a', borderColor: '#27272a' }}
                    >
                      <p className="text-[0.7rem] uppercase tracking-wider" style={{ color: '#52525b' }}>{m.month}</p>
                      <p className="font-bold tabular-nums mt-1" style={{ fontSize: '1.5rem', color: roiColor(m.roi) }}>
                        {m.roi >= 0 ? '+' : ''}{m.roi.toFixed(1)}%
                      </p>
                      <p className="text-sm mt-1" style={{ color: '#a1a1aa' }}>{m.record} &nbsp;·&nbsp; {m.bets} bets</p>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Strategy details */}
            {strategyData.strategy && (
              <Section title="Strategy Parameters">
                <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))' }}>
                  {[
                    { label: 'Method', value: strategyData.strategy.method ?? '—' },
                    { label: 'Base Stake', value: strategyData.strategy.baseStake !== undefined ? `${strategyData.strategy.baseStake}u` : '—' },
                    { label: 'Max Stake', value: strategyData.strategy.maxStake !== undefined ? `${strategyData.strategy.maxStake}u` : '—' },
                    { label: 'Min Edge', value: strategyData.strategy.minEdgePct !== undefined ? `${strategyData.strategy.minEdgePct}%` : '—' },
                  ].map(({ label, value }) => (
                    <StatCard key={label} label={label} value={value} />
                  ))}
                </div>
              </Section>
            )}

          </div>
        )}
      </main>
    </>
  )
}
