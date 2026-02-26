'use client'

import { useState } from 'react'
import { Loader2, RefreshCw, Flag } from 'lucide-react'

/* ─── Types ─────────────────────────────────────────────── */
export interface UpcomingPick {
  teamA: string
  teamB: string
  marketOdds: string
  modelPFair: number
  recommendation: 'BET' | 'SKIP' | 'MONITOR'
}

export interface BetLogEntry {
  date: string
  matchup: string
  odds: string
  result: 'W' | 'L' | 'P'
  profit: number
  flagged?: boolean
}

export interface WalkForwardYear {
  year: number | string
  bets: number
  record: string
  roi: number
  avgOdds: string
  isTotal?: boolean
}

export interface MonthlyReview {
  month: string
  bets: number
  roi: number
  record: string
}

export interface MoneylinePageProps {
  roi: number
  record: string
  activeBetsToday: number
  upcomingPicks: UpcomingPick[]
  betLog: BetLogEntry[]
  walkForward: WalkForwardYear[]
  monthly: MonthlyReview[]
  isScrapingVlr?: boolean
  onScrapeVlr?: () => void
}

/* ─── Sub-components ─────────────────────────────────────── */
const REC_STYLE: Record<UpcomingPick['recommendation'], { bg: string; color: string; border: string }> = {
  BET: { bg: 'rgba(34,197,94,0.12)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.25)' },
  SKIP: { bg: 'rgba(113,113,122,0.12)', color: '#71717a', border: '1px solid rgba(113,113,122,0.2)' },
  MONITOR: { bg: 'rgba(59,130,246,0.12)', color: '#3b82f6', border: '1px solid rgba(59,130,246,0.25)' },
}

const RESULT_STYLE: Record<BetLogEntry['result'], { bg: string; color: string }> = {
  W: { bg: 'rgba(34,197,94,0.12)', color: '#22c55e' },
  L: { bg: 'rgba(239,68,68,0.12)', color: '#ef4444' },
  P: { bg: 'rgba(113,113,122,0.12)', color: '#71717a' },
}

const TABS = ['Walk-Forward', 'Upcoming', 'Monthly', 'Bet Log'] as const
type Tab = (typeof TABS)[number]

/* ─── MoneylinePage ──────────────────────────────────────── */
export function MoneylinePage({
  roi,
  record,
  activeBetsToday,
  upcomingPicks,
  betLog,
  walkForward,
  monthly,
  isScrapingVlr = false,
  onScrapeVlr,
}: MoneylinePageProps) {
  const [activeTab, setActiveTab] = useState<Tab>('Upcoming')

  return (
    <div className="flex flex-col gap-5">
      {/* Strategy summary bar */}
      <div
        className="rounded-[10px] border px-5 py-3 flex items-center flex-wrap gap-4"
        style={{ background: '#0a0a0a', borderColor: '#27272a' }}
      >
        <div className="flex items-center gap-2">
          <span className="text-[0.7rem] uppercase tracking-[0.1em]" style={{ color: '#71717a' }}>
            ROI
          </span>
          <span
            className="font-bold tabular-nums text-base"
            style={{ color: roi >= 0 ? '#22c55e' : '#ef4444' }}
          >
            {roi >= 0 ? '+' : ''}{roi.toFixed(1)}%
          </span>
        </div>
        <div className="w-px h-4" style={{ background: '#27272a' }} />
        <div className="flex items-center gap-2">
          <span className="text-[0.7rem] uppercase tracking-[0.1em]" style={{ color: '#71717a' }}>
            Record
          </span>
          <span className="font-bold text-base" style={{ color: '#ffffff' }}>
            {record}
          </span>
        </div>
        <div className="w-px h-4" style={{ background: '#27272a' }} />
        <div className="flex items-center gap-2">
          <span className="text-[0.7rem] uppercase tracking-[0.1em]" style={{ color: '#71717a' }}>
            Active Bets
          </span>
          <span
            className="font-bold tabular-nums text-base"
            style={{ color: activeBetsToday > 0 ? '#f59e0b' : '#71717a' }}
          >
            {activeBetsToday} today
          </span>
        </div>
      </div>

      {/* Pill tab nav */}
      <div
        className="inline-flex rounded-[10px] p-1"
        style={{ background: '#18181b', border: '1px solid #27272a' }}
        role="tablist"
      >
        {TABS.map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={activeTab === tab}
            onClick={() => setActiveTab(tab)}
            className="px-4 py-2 rounded-[8px] text-sm font-medium transition-colors duration-150 whitespace-nowrap"
            style={{
              background: activeTab === tab ? '#27272a' : 'transparent',
              color: activeTab === tab ? '#ffffff' : '#71717a',
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab panels */}
      {activeTab === 'Upcoming' && (
        <div
          className="rounded-[12px] border overflow-hidden"
          style={{ background: '#0a0a0a', borderColor: '#27272a' }}
        >
          <div
            className="flex items-center justify-between px-4 py-3 border-b"
            style={{ borderColor: '#27272a', background: '#18181b' }}
          >
            <h2 className="text-sm font-semibold" style={{ color: '#ffffff' }}>
              Upcoming Picks
            </h2>
            <button
              onClick={onScrapeVlr}
              disabled={isScrapingVlr}
              className="flex items-center gap-1.5 text-[0.75rem] font-medium px-3 py-1.5 rounded-[6px] border transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              style={{
                background: 'rgba(59,130,246,0.1)',
                color: '#3b82f6',
                borderColor: 'rgba(59,130,246,0.25)',
              }}
            >
              {isScrapingVlr ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <RefreshCw size={12} />
              )}
              Scrape VLR
            </button>
          </div>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr style={{ borderBottom: '1px solid #27272a' }}>
                {['Matchup', 'Market Odds', 'Model p_fair', 'Recommendation'].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-2.5 text-left text-[0.65rem] uppercase tracking-[0.08em]"
                    style={{ color: '#71717a', background: '#18181b' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {upcomingPicks.map((pick, i) => {
                const recStyle = REC_STYLE[pick.recommendation]
                return (
                  <tr
                    key={i}
                    style={{
                      background: i % 2 === 0 ? '#0a0a0a' : '#111113',
                      borderBottom: '1px solid rgba(39,39,42,0.4)',
                    }}
                    onMouseEnter={(e) =>
                      ((e.currentTarget as HTMLTableRowElement).style.background = '#18181b')
                    }
                    onMouseLeave={(e) =>
                      ((e.currentTarget as HTMLTableRowElement).style.background =
                        i % 2 === 0 ? '#0a0a0a' : '#111113')
                    }
                  >
                    <td className="px-4 py-3 font-medium" style={{ color: '#ffffff' }}>
                      {pick.teamA}{' '}
                      <span style={{ color: '#52525b' }}>vs</span> {pick.teamB}
                    </td>
                    <td className="px-4 py-3 tabular-nums" style={{ color: '#a1a1aa' }}>
                      {pick.marketOdds}
                    </td>
                    <td className="px-4 py-3 tabular-nums" style={{ color: '#a1a1aa' }}>
                      {(pick.modelPFair * 100).toFixed(1)}%
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className="text-[0.7rem] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-[4px]"
                        style={recStyle}
                      >
                        {pick.recommendation}
                      </span>
                    </td>
                  </tr>
                )
              })}
              {upcomingPicks.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-sm" style={{ color: '#52525b' }}>
                    No upcoming picks — click Scrape VLR to populate
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'Walk-Forward' && (
        <div
          className="rounded-[12px] border overflow-hidden"
          style={{ background: '#0a0a0a', borderColor: '#27272a' }}
        >
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr style={{ borderBottom: '1px solid #27272a', background: '#18181b' }}>
                {['Year', 'Bets', 'Record', 'ROI', 'Avg Odds'].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-2.5 text-left text-[0.65rem] uppercase tracking-[0.08em]"
                    style={{ color: '#71717a' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {walkForward.map((row, i) => (
                <tr
                  key={i}
                  style={{
                    background: row.isTotal ? '#0f0f0f' : i % 2 === 0 ? '#0a0a0a' : '#111113',
                    borderBottom: row.isTotal
                      ? '2px solid #3f3f46'
                      : '1px solid rgba(39,39,42,0.4)',
                    borderTop: row.isTotal ? '2px solid #3f3f46' : undefined,
                  }}
                >
                  <td
                    className="px-4 py-2.5 tabular-nums"
                    style={{
                      color: '#ffffff',
                      fontWeight: row.isTotal ? 700 : 400,
                    }}
                  >
                    {row.year}
                  </td>
                  <td className="px-4 py-2.5 tabular-nums" style={{ color: '#a1a1aa' }}>
                    {row.bets}
                  </td>
                  <td className="px-4 py-2.5 tabular-nums" style={{ color: '#a1a1aa' }}>
                    {row.record}
                  </td>
                  <td
                    className="px-4 py-2.5 tabular-nums font-semibold"
                    style={{ color: row.roi >= 0 ? '#22c55e' : '#ef4444' }}
                  >
                    {row.roi >= 0 ? '+' : ''}{row.roi.toFixed(1)}%
                  </td>
                  <td className="px-4 py-2.5 tabular-nums" style={{ color: '#a1a1aa' }}>
                    {row.avgOdds}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'Monthly' && (
        <div
          className="rounded-[12px] border overflow-hidden"
          style={{ background: '#0a0a0a', borderColor: '#27272a' }}
        >
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr style={{ borderBottom: '1px solid #27272a', background: '#18181b' }}>
                {['Month', 'Bets', 'Record', 'ROI'].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-2.5 text-left text-[0.65rem] uppercase tracking-[0.08em]"
                    style={{ color: '#71717a' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {monthly.map((row, i) => (
                <tr
                  key={i}
                  style={{
                    background: i % 2 === 0 ? '#0a0a0a' : '#111113',
                    borderBottom: '1px solid rgba(39,39,42,0.4)',
                  }}
                >
                  <td className="px-4 py-2.5 font-medium" style={{ color: '#ffffff' }}>
                    {row.month}
                  </td>
                  <td className="px-4 py-2.5 tabular-nums" style={{ color: '#a1a1aa' }}>
                    {row.bets}
                  </td>
                  <td className="px-4 py-2.5 tabular-nums" style={{ color: '#a1a1aa' }}>
                    {row.record}
                  </td>
                  <td
                    className="px-4 py-2.5 tabular-nums font-semibold"
                    style={{ color: row.roi >= 0 ? '#22c55e' : '#ef4444' }}
                  >
                    {row.roi >= 0 ? '+' : ''}{row.roi.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'Bet Log' && (
        <div
          className="rounded-[12px] border overflow-hidden"
          style={{ background: '#0a0a0a', borderColor: '#27272a' }}
        >
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr style={{ borderBottom: '1px solid #27272a', background: '#18181b' }}>
                {['Date', 'Matchup', 'Odds', 'Result', 'P/L', 'Flag'].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-2.5 text-left text-[0.65rem] uppercase tracking-[0.08em]"
                    style={{ color: '#71717a' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {betLog.map((entry, i) => {
                const resStyle = RESULT_STYLE[entry.result]
                return (
                  <tr
                    key={i}
                    style={{
                      background: i % 2 === 0 ? '#0a0a0a' : '#111113',
                      borderBottom: '1px solid rgba(39,39,42,0.4)',
                    }}
                    onMouseEnter={(e) =>
                      ((e.currentTarget as HTMLTableRowElement).style.background = '#18181b')
                    }
                    onMouseLeave={(e) =>
                      ((e.currentTarget as HTMLTableRowElement).style.background =
                        i % 2 === 0 ? '#0a0a0a' : '#111113')
                    }
                  >
                    <td className="px-4 py-2.5 tabular-nums" style={{ color: '#71717a' }}>
                      {entry.date}
                    </td>
                    <td className="px-4 py-2.5 font-medium" style={{ color: '#ffffff' }}>
                      {entry.matchup}
                    </td>
                    <td className="px-4 py-2.5 tabular-nums" style={{ color: '#a1a1aa' }}>
                      {entry.odds}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className="text-[0.7rem] font-bold px-2 py-0.5 rounded-[4px]"
                        style={resStyle}
                      >
                        {entry.result}
                      </span>
                    </td>
                    <td
                      className="px-4 py-2.5 tabular-nums font-medium"
                      style={{ color: entry.profit >= 0 ? '#22c55e' : '#ef4444' }}
                    >
                      {entry.profit >= 0 ? '+' : ''}{entry.profit.toFixed(2)}u
                    </td>
                    <td className="px-4 py-2.5">
                      {entry.flagged && <Flag size={13} style={{ color: '#f59e0b' }} />}
                    </td>
                  </tr>
                )
              })}
              {betLog.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-sm" style={{ color: '#52525b' }}>
                    No bets logged
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
