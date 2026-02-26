'use client'

import { AppHeader } from '@/components/app-header'
import { MoneylinePage, type MoneylinePageProps } from '@/components/moneyline-page'

const DATA: MoneylinePageProps = {
  roi: 12.3,
  record: '47W-31L',
  activeBetsToday: 3,
  upcomingPicks: [
    { teamA: 'Sentinels', teamB: 'NRG', marketOdds: '-150', modelPFair: 0.62, recommendation: 'BET' },
    { teamA: 'Cloud9', teamB: 'EG', marketOdds: '+120', modelPFair: 0.44, recommendation: 'SKIP' },
    { teamA: 'LOUD', teamB: '100T', marketOdds: '-105', modelPFair: 0.53, recommendation: 'MONITOR' },
  ],
  betLog: [
    { date: '2025-02-20', matchup: 'SEN vs NRG', odds: '-140', result: 'W', profit: 0.71 },
    { date: '2025-02-18', matchup: 'C9 vs EG', odds: '+110', result: 'L', profit: -1.0 },
    { date: '2025-02-15', matchup: 'LOUD vs 100T', odds: '-120', result: 'W', profit: 0.83, flagged: true },
    { date: '2025-02-12', matchup: 'T1 vs FNATIC', odds: '+200', result: 'P', profit: 0 },
  ],
  walkForward: [
    { year: 2022, bets: 38, record: '21W-17L', roi: 4.2, avgOdds: '-112' },
    { year: 2023, bets: 51, record: '29W-22L', roi: 8.7, avgOdds: '-118' },
    { year: 2024, bets: 67, record: '39W-28L', roi: 14.1, avgOdds: '-115' },
    { year: 2025, bets: 22, record: '13W-9L', roi: 11.4, avgOdds: '-121' },
    { year: 'Total', bets: 178, record: '102W-76L', roi: 10.4, avgOdds: '-116', isTotal: true },
  ],
  monthly: [
    { month: 'Jan 2025', bets: 11, roi: 9.1, record: '7W-4L' },
    { month: 'Feb 2025', bets: 11, roi: 13.8, record: '6W-5L' },
    { month: 'Dec 2024', bets: 14, roi: 18.4, record: '9W-5L' },
    { month: 'Nov 2024', bets: 12, roi: -2.1, record: '5W-7L' },
  ],
  consistency: {
    currentStreak: { type: 'W', count: 5 },
    longestWin: 9,
    longestLoss: 4,
    winRate: 60.2,
    avgReturn: 0.41,
    stdDev: 1.12,
  },
  calibration: [
    { range: '-200 to -151', modelPct: 68.0, actualPct: 71.4, bets: 28 },
    { range: '-150 to -121', modelPct: 60.0, actualPct: 58.3, bets: 36 },
    { range: '-120 to -101', modelPct: 54.5, actualPct: 56.1, bets: 41 },
    { range: '-100 to +100', modelPct: 50.0, actualPct: 47.8, bets: 23 },
    { range: '+101 to +150', modelPct: 42.0, actualPct: 40.0, bets: 15 },
    { range: '+151 to +200', modelPct: 36.0, actualPct: 33.3, bets: 9 },
  ],
  strategy: {
    method: 'Kelly Quarter',
    baseStake: 1.0,
    maxStake: 3.0,
    minEdgePct: 5.0,
    minOdds: '+100',
    maxOdds: '-200',
  },
}

export default function MoneylineStrategyPage() {
  return (
    <>
      <AppHeader activePage="/moneylines" />
      <div className="page-container" style={{ padding: '0 24px 3rem' }}>
        {/* Hero */}
        <div style={{ textAlign: 'center', padding: '3rem 0 2rem' }}>
          <h1
            className="font-display uppercase"
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 900,
              fontSize: 'clamp(2.5rem, 6vw, 5rem)',
              letterSpacing: '-0.02em',
              lineHeight: 1.05,
              color: '#ffffff',
              marginBottom: '1rem',
            }}
          >
            MoneyLine <span style={{ color: '#16A34A' }}>Strategy</span>
          </h1>
          <p style={{ fontSize: '0.875rem', color: 'rgba(255,255,255,0.5)', maxWidth: 620, margin: '0 auto 2rem' }}>
            Americas+China · 0.55≤p_fair≤0.70 · 1u flat — validated walk-forward (Champions Tour 2024+)
          </p>
        </div>
        <MoneylinePage {...DATA} />
      </div>
    </>
  )
}
