'use client'

import { useState } from 'react'
import { Loader2, RefreshCw, Flag } from 'lucide-react'

/* ─── Types ─────────────────────────────────────────────── */
export interface ConsistencyData {
  currentStreak: { type: 'W' | 'L'; count: number }
  longestWin: number
  longestLoss: number
  winRate: number
  avgReturn: number
  stdDev: number
}

export interface CalibrationBucket {
  range: string
  modelPct: number
  actualPct: number
  bets: number
}

export interface StrategyConfig {
  method: string
  baseStake: number
  maxStake: number
  minEdgePct: number
  minOdds: string
  maxOdds: string
}

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
  consistency?: ConsistencyData
  calibration?: CalibrationBucket[]
  strategy?: StrategyConfig
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

const TABS = ['Walk-Forward', 'Upcoming', 'Monthly', 'Bet Log', 'Consistency', 'Calibration', 'Strategy'] as const
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
  consistency,
  calibration,
  strategy,
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

      {/* Pill tab nav — scrollable on mobile */}
      <div className="overflow-x-auto -mx-1 px-1 pb-0.5">
        <div
          className="inline-flex rounded-[10px] p-1 min-w-max"
          style={{ background: '#18181b', border: '1px solid #27272a' }}
          role="tablist"
        >
          {TABS.map((tab) => (
            <button
              key={tab}
              role="tab"
              aria-selected={activeTab === tab}
              onClick={() => setActiveTab(tab)}
              className="px-3 py-1.5 rounded-[8px] text-[0.8rem] font-medium transition-colors duration-150 whitespace-nowrap"
              style={{
                background: activeTab === tab ? '#27272a' : 'transparent',
                color: activeTab === tab ? '#ffffff' : '#71717a',
              }}
            >
              {tab}
            </button>
          ))}
        </div>
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
          <div className="table-scroll">
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
                    className="data-row"
                    style={{
                      background: i % 2 === 0 ? '#0a0a0a' : '#111113',
                      borderBottom: '1px solid rgba(39,39,42,0.4)',
                    }}
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
        </div>
      )}

      {activeTab === 'Walk-Forward' && (
        <div
          className="rounded-[12px] border overflow-hidden"
          style={{ background: '#0a0a0a', borderColor: '#27272a' }}
        >
          <div className="table-scroll">
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
        </div>
      )}

      {activeTab === 'Monthly' && (
        <div
          className="rounded-[12px] border overflow-hidden"
          style={{ background: '#0a0a0a', borderColor: '#27272a' }}
        >
          <div className="table-scroll">
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
        </div>
      )}

      {activeTab === 'Consistency' && (
        <div className="flex flex-col gap-4">
          {consistency ? (
            <>
              {/* Current streak hero */}
              <div
                className="rounded-[12px] border px-6 py-5 flex items-center gap-6"
                style={{ background: '#0a0a0a', borderColor: '#27272a' }}
              >
                <div className="flex flex-col gap-1">
                  <span className="text-[0.65rem] uppercase tracking-[0.1em]" style={{ color: '#71717a' }}>
                    Current Streak
                  </span>
                  <span
                    className="font-black tabular-nums"
                    style={{
                      fontSize: '3rem',
                      lineHeight: 1,
                      color: consistency.currentStreak.type === 'W' ? '#22c55e' : '#ef4444',
                    }}
                  >
                    {consistency.currentStreak.type}{consistency.currentStreak.count}
                  </span>
                </div>
                <div className="w-px self-stretch" style={{ background: '#27272a' }} />
                <div className="grid grid-cols-2 gap-x-8 gap-y-3 flex-1">
                  {[
                    { label: 'Win Rate', value: `${consistency.winRate.toFixed(1)}%`, color: consistency.winRate >= 55 ? '#22c55e' : '#ffffff' },
                    { label: 'Avg Return', value: `${consistency.avgReturn >= 0 ? '+' : ''}${consistency.avgReturn.toFixed(2)}u`, color: consistency.avgReturn >= 0 ? '#22c55e' : '#ef4444' },
                    { label: 'Longest W Streak', value: `${consistency.longestWin}`, color: '#22c55e' },
                    { label: 'Longest L Streak', value: `${consistency.longestLoss}`, color: '#ef4444' },
                    { label: 'Std Deviation', value: `${consistency.stdDev.toFixed(2)}u`, color: '#a1a1aa' },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="flex flex-col gap-0.5">
                      <span className="text-[0.65rem] uppercase tracking-[0.08em]" style={{ color: '#71717a' }}>{label}</span>
                      <span className="font-bold text-base tabular-nums" style={{ color }}>{value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div
              className="rounded-[12px] border py-12 text-center text-sm"
              style={{ background: '#0a0a0a', borderColor: '#27272a', color: '#52525b' }}
            >
              No consistency data available
            </div>
          )}
        </div>
      )}

      {activeTab === 'Calibration' && (
        <div
          className="rounded-[12px] border overflow-hidden"
          style={{ background: '#0a0a0a', borderColor: '#27272a' }}
        >
          <div
            className="px-4 py-3 border-b"
            style={{ borderColor: '#27272a', background: '#18181b' }}
          >
            <h2 className="text-sm font-semibold" style={{ color: '#ffffff' }}>
              Model Calibration
            </h2>
            <p className="text-[0.72rem] mt-0.5" style={{ color: '#71717a' }}>
              Predicted win probability vs. actual outcomes by odds range
            </p>
          </div>
          {calibration && calibration.length > 0 ? (
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr style={{ borderBottom: '1px solid #27272a', background: '#18181b' }}>
                  {['Odds Range', 'Model Win%', 'Actual Win%', 'Bets', 'Deviation'].map((h) => (
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
                {calibration.map((row, i) => {
                  const dev = row.actualPct - row.modelPct
                  const devColor = Math.abs(dev) < 3 ? '#71717a' : dev > 0 ? '#22c55e' : '#ef4444'
                  return (
                    <tr
                      key={i}
                      style={{
                        background: i % 2 === 0 ? '#0a0a0a' : '#111113',
                        borderBottom: '1px solid rgba(39,39,42,0.4)',
                      }}
                    >
                      <td className="px-4 py-2.5 font-medium" style={{ color: '#ffffff' }}>
                        {row.range}
                      </td>
                      <td className="px-4 py-2.5 tabular-nums" style={{ color: '#3b82f6' }}>
                        {row.modelPct.toFixed(1)}%
                      </td>
                      <td className="px-4 py-2.5 tabular-nums" style={{ color: '#a1a1aa' }}>
                        {row.actualPct.toFixed(1)}%
                      </td>
                      <td className="px-4 py-2.5 tabular-nums" style={{ color: '#71717a' }}>
                        {row.bets}
                      </td>
                      <td className="px-4 py-2.5 tabular-nums font-semibold" style={{ color: devColor }}>
                        {dev >= 0 ? '+' : ''}{dev.toFixed(1)}pp
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          ) : (
            <div className="py-12 text-center text-sm" style={{ color: '#52525b' }}>
              No calibration data available
            </div>
          )}
        </div>
      )}

      {activeTab === 'Strategy' && (
        <div
          className="rounded-[12px] border"
          style={{ background: '#0a0a0a', borderColor: '#27272a' }}
        >
          <div
            className="px-4 py-3 border-b"
            style={{ borderColor: '#27272a', background: '#18181b' }}
          >
            <h2 className="text-sm font-semibold" style={{ color: '#ffffff' }}>
              Betting Strategy
            </h2>
            <p className="text-[0.72rem] mt-0.5" style={{ color: '#71717a' }}>
              Active parameters for bet sizing and filtering
            </p>
          </div>
          {strategy ? (
            <div className="grid grid-cols-2 gap-px" style={{ background: '#27272a' }}>
              {[
                { label: 'Method', value: strategy.method, note: 'Stake sizing algorithm' },
                { label: 'Base Stake', value: `${strategy.baseStake.toFixed(1)}u`, note: 'Per-bet unit size' },
                { label: 'Max Stake', value: `${strategy.maxStake.toFixed(1)}u`, note: 'Hard cap per bet' },
                { label: 'Min Edge', value: `${strategy.minEdgePct.toFixed(1)}%`, note: 'Required model edge to bet' },
                { label: 'Min Odds Filter', value: strategy.minOdds, note: 'Ignore lines beyond this' },
                { label: 'Max Odds Filter', value: strategy.maxOdds, note: 'Ignore lines beyond this' },
              ].map(({ label, value, note }) => (
                <div
                  key={label}
                  className="flex flex-col gap-1 p-4"
                  style={{ background: '#0a0a0a' }}
                >
                  <span className="text-[0.65rem] uppercase tracking-[0.1em]" style={{ color: '#71717a' }}>
                    {label}
                  </span>
                  <span className="font-bold text-lg tabular-nums" style={{ color: '#ffffff' }}>
                    {value}
                  </span>
                  <span className="text-[0.7rem]" style={{ color: '#52525b' }}>
                    {note}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-12 text-center text-sm" style={{ color: '#52525b' }}>
              No strategy configuration available
            </div>
          )}
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
