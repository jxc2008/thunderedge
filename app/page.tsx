'use client'

import { useState } from 'react'
import { AppHeader } from '@/components/app-header'
import { SearchForm, type SearchFormData } from '@/components/search-form'
import { OverUnderDisplay } from '@/components/over-under-display'
import { StatsGrid, type StatCardData } from '@/components/stats-grid'
import { DataTable, type Column } from '@/components/data-table'
import { EventCard, type EventCardData } from '@/components/event-card'
import { RecommendationCard } from '@/components/recommendation-card'
import { DistributionChart } from '@/components/distribution-chart'
import { TeamPage, type TeamData } from '@/components/team-page'
import { MoneylinePage, type MoneylinePageProps } from '@/components/moneyline-page'
import {
  ToastProvider,
  useToast,
  EmptyState,
  ErrorState,
  SkeletonOverUnder,
  SkeletonStatsGrid,
  SkeletonTable,
  SkeletonEventCards,
} from '@/components/ux-patterns'
import { BarChart2 } from 'lucide-react'

/* ─── Sample data ────────────────────────────────────────── */
const SAMPLE_STATS: StatCardData[] = [
  { label: 'Model Mean', value: '21.4', delta: 'kills / map', semantic: 'positive' },
  { label: 'Market-Implied Mean', value: '19.5', delta: 'kill line', semantic: 'neutral' },
  { label: 'Sample Size', value: 47, delta: 'maps analyzed', semantic: 'neutral' },
  { label: 'Kill / Map Avg', value: '20.8', delta: 'last 20 maps', semantic: 'neutral' },
  { label: 'Edge', value: '+9.2pp', delta: 'vs market', semantic: 'positive' },
  { label: 'Rating', value: '1.34', delta: 'VLR rating', semantic: 'neutral' },
]

interface AgentRow { agent: string; maps: number; killsPerMap: number; overPct: number }
const AGENT_COLS: Column<AgentRow>[] = [
  { key: 'agent', label: 'Agent', sortable: true },
  { key: 'maps', label: 'Maps', sortable: true, align: 'right' },
  { key: 'killsPerMap', label: 'K/Map', sortable: true, align: 'right', killRateBar: true, barMax: 30 },
  {
    key: 'overPct',
    label: 'Over %',
    sortable: true,
    align: 'right',
    render: (v) => (
      <span style={{ color: (v as number) >= 55 ? '#22c55e' : (v as number) <= 45 ? '#ef4444' : '#a1a1aa' }}>
        {(v as number).toFixed(1)}%
      </span>
    ),
  },
]
const AGENT_DATA: AgentRow[] = [
  { agent: 'Jett', maps: 14, killsPerMap: 23.4, overPct: 71.4 },
  { agent: 'Neon', maps: 12, killsPerMap: 21.1, overPct: 58.3 },
  { agent: 'Raze', maps: 10, killsPerMap: 19.8, overPct: 50.0 },
  { agent: 'Reyna', maps: 7, killsPerMap: 18.6, overPct: 42.9 },
  { agent: 'Iso', maps: 4, killsPerMap: 16.3, overPct: 25.0 },
]

const EVENTS: EventCardData[] = [
  {
    id: '1',
    eventName: 'VCT Americas 2025 — Masters',
    date: 'Feb 2025',
    isCached: true,
    overCount: 6,
    underCount: 2,
    maps: [
      { map: 'Ascent', kills: 22, line: 19.5 },
      { map: 'Bind', kills: 25, line: 19.5 },
      { map: 'Haven', kills: 18, line: 19.5 },
    ],
    defaultOpen: true,
  },
  {
    id: '2',
    eventName: 'VCT Americas 2025 — Kickoff',
    date: 'Jan 2025',
    isCached: true,
    overCount: 4,
    underCount: 3,
    maps: [
      { map: 'Pearl', kills: 21, line: 19.5 },
      { map: 'Icebox', kills: 17, line: 19.5 },
      { map: 'Lotus', kills: 20, line: 19.5 },
    ],
  },
  {
    id: '3',
    eventName: 'Champions 2024',
    date: 'Aug 2024',
    isLive: false,
    isCached: true,
    overCount: 5,
    underCount: 1,
    maps: [
      { map: 'Split', kills: 23, line: 19.5 },
      { map: 'Fracture', kills: 24, line: 19.5 },
    ],
  },
]

const DIST_DATA = Array.from({ length: 15 }, (_, i) => {
  const k = i + 12
  const modelPct = Math.exp(-Math.pow(k - 21, 2) / 18) * 18
  const marketPct = Math.exp(-Math.pow(k - 19.5, 2) / 20) * 16
  return { kills: k, modelPct: parseFloat(modelPct.toFixed(2)), marketPct: parseFloat(marketPct.toFixed(2)) }
})

const TEAM: TeamData = {
  name: 'Sentinels',
  region: 'NA',
  players: [
    { ign: 'TenZ', role: 'Duelist' },
    { ign: 'Zellsis', role: 'Initiator' },
    { ign: 'Sacy', role: 'Initiator' },
    { ign: 'Pryze', role: 'Controller' },
    { ign: 'Zekken', role: 'Sentinel' },
  ],
  fprAvg: 0.842,
  totalMatches: 48,
  avgKillsPerRound: 0.74,
  events: [
    {
      id: 'e1',
      eventName: 'VCT Americas 2025 — Masters',
      date: 'Feb 2025',
      defaultOpen: true,
      stats: {
        fpr: 0.871,
        kills: 512,
        deaths: 487,
        rounds: 624,
        matchesPlayed: 12,
        maps: [
          { map: 'Ascent', rate: 45, type: 'first-pick' },
          { map: 'Bind', rate: 32, type: 'second-pick' },
          { map: 'Haven', rate: 28, type: 'first-ban' },
          { map: 'Icebox', rate: 18, type: 'second-ban' },
          { map: 'Pearl', rate: 22, type: 'first-pick' },
          { map: 'Lotus', rate: 15, type: 'second-ban' },
        ],
      },
    },
    {
      id: 'e2',
      eventName: 'VCT Americas 2025 — Kickoff',
      date: 'Jan 2025',
      stats: {
        fpr: 0.813,
        kills: 340,
        deaths: 358,
        rounds: 416,
        matchesPlayed: 8,
        maps: [
          { map: 'Split', rate: 38, type: 'first-pick' },
          { map: 'Fracture', rate: 25, type: 'first-ban' },
          { map: 'Breeze', rate: 20, type: 'second-pick' },
        ],
      },
    },
  ],
}

const MONEYLINE: MoneylinePageProps = {
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

/* ─── Section wrapper ────────────────────────────────────── */
function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <span
          className="text-[0.65rem] uppercase tracking-[0.15em] font-semibold"
          style={{ color: '#3f3f46' }}
        >
          {label}
        </span>
        <div className="flex-1 h-px" style={{ background: '#27272a' }} />
      </div>
      {children}
    </section>
  )
}

/* ─── Page ───────────────────────────────────────────────── */
export default function ShowcasePage() {
  const { toasts, dismiss, toast } = useToast()
  const [isLoading, setIsLoading] = useState(false)
  const [lastQuery, setLastQuery] = useState<{ player: string; ms: number } | null>(null)
  const [showSkeletons, setShowSkeletons] = useState(false)
  const [showError, setShowError] = useState(false)

  const handleSearch = (data: SearchFormData) => {
    setIsLoading(true)
    setShowSkeletons(true)
    setTimeout(() => {
      setIsLoading(false)
      setShowSkeletons(false)
      setLastQuery({ player: data.player || 'TenZ#NA1', ms: 342 })
      toast('success', 'Analysis complete', `Results loaded for ${data.player || 'TenZ#NA1'}`)
    }, 1800)
  }

  return (
    <>
      <AppHeader activePage="/" />

      <main className="max-w-[1400px] mx-auto px-6 py-10 flex flex-col gap-14">

        {/* Hero */}
        <div className="text-center py-8">
          <div
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-[0.75rem] font-medium mb-5"
            style={{
              background: 'rgba(59,130,246,0.1)',
              border: '1px solid rgba(59,130,246,0.2)',
              color: '#3b82f6',
            }}
          >
            <BarChart2 size={12} />
            React Component Library — Design Reference
          </div>
          <h1
            className="font-bold tracking-tight text-balance mb-3"
            style={{ fontSize: 'clamp(2rem, 5vw, 3.5rem)', color: '#ffffff' }}
          >
            Thunder<span className="gradient-text">Edge</span> Design System
          </h1>
          <p className="text-sm max-w-lg mx-auto text-pretty" style={{ color: '#71717a' }}>
            Production-ready React components for the ThunderEdge Valorant analytics platform.
            Built with shadcn/ui + Tailwind, faithful to the established dark design language.
          </p>
          {/* Demo controls */}
          <div className="flex items-center justify-center gap-3 mt-6 flex-wrap">
            <button
              onClick={() => toast('success', 'BET OVER recommended', 'TenZ +9.2pp edge vs market')}
              className="text-sm font-medium px-4 py-2 rounded-[8px] border transition-opacity hover:opacity-80"
              style={{ background: 'rgba(34,197,94,0.1)', borderColor: 'rgba(34,197,94,0.25)', color: '#22c55e' }}
            >
              Toast: Success
            </button>
            <button
              onClick={() => toast('error', 'Player not found', 'Could not locate TenZ in VLR database')}
              className="text-sm font-medium px-4 py-2 rounded-[8px] border transition-opacity hover:opacity-80"
              style={{ background: 'rgba(239,68,68,0.1)', borderColor: 'rgba(239,68,68,0.25)', color: '#ef4444' }}
            >
              Toast: Error
            </button>
            <button
              onClick={() => toast('warning', 'Rate limit approaching', '4 of 5 API calls used')}
              className="text-sm font-medium px-4 py-2 rounded-[8px] border transition-opacity hover:opacity-80"
              style={{ background: 'rgba(245,158,11,0.1)', borderColor: 'rgba(245,158,11,0.25)', color: '#f59e0b' }}
            >
              Toast: Warning
            </button>
            <button
              onClick={() => toast('info', 'Cache hit', 'Returning cached result from 5m ago')}
              className="text-sm font-medium px-4 py-2 rounded-[8px] border transition-opacity hover:opacity-80"
              style={{ background: 'rgba(59,130,246,0.1)', borderColor: 'rgba(59,130,246,0.25)', color: '#3b82f6' }}
            >
              Toast: Info
            </button>
            <button
              onClick={() => setShowError((v) => !v)}
              className="text-sm font-medium px-4 py-2 rounded-[8px] border transition-opacity hover:opacity-80"
              style={{ background: 'rgba(113,113,122,0.1)', borderColor: '#3f3f46', color: '#a1a1aa' }}
            >
              Toggle Error State
            </button>
          </div>
        </div>

        {/* 1. Search Form */}
        <Section label="Search Form">
          <SearchForm
            onSubmit={handleSearch}
            isLoading={isLoading}
            lastQuery={lastQuery}
          />
        </Section>

        {/* 2. Over/Under Display */}
        <Section label="Over / Under Hero Display">
          {showSkeletons ? (
            <SkeletonOverUnder />
          ) : (
            <OverUnderDisplay
              overPct={63.8}
              underPct={36.2}
              sampleSize={47}
              killLine={19.5}
            />
          )}
        </Section>

        {/* 3. Recommendation Card */}
        <Section label="Recommendation Card">
          <RecommendationCard
            type="BET_OVER"
            ev={0.092}
            confidence="HIGH"
            reason="Model mean 21.4 exceeds market-implied mean 19.5 by 9.7%. Positive EV across all line scenarios."
          />
          <RecommendationCard
            type="NO_BET"
            ev={-0.024}
            confidence="LOW"
            reason="Insufficient edge to justify bet. Market appears efficiently priced."
          />
          <RecommendationCard
            type="BET_UNDER"
            ev={0.041}
            confidence="MED"
            reason="Player underperforming on large maps. Under has hit in 4 of last 5."
          />
        </Section>

        {/* 4. Stats Grid */}
        <Section label="Stats Grid">
          {showSkeletons ? (
            <SkeletonStatsGrid count={6} columns={3} />
          ) : (
            <StatsGrid stats={SAMPLE_STATS} columns={3} />
          )}
        </Section>

        {/* 5. Kill Distribution Chart */}
        <Section label="Kill Distribution Chart">
          <DistributionChart
            data={DIST_DATA}
            killLine={19.5}
            modelOverPct={63.8}
            marketOverPct={54.6}
          />
        </Section>

        {/* 6. Agent Stats Table */}
        <Section label="Agent Stats Table">
          {showSkeletons ? (
            <SkeletonTable rows={5} cols={4} />
          ) : (
            <DataTable<AgentRow>
              columns={AGENT_COLS}
              data={AGENT_DATA}
              filterPlaceholder="Filter agents..."
              filterKey="agent"
            />
          )}
        </Section>

        {/* 7. Event Cards */}
        <Section label="Event Cards">
          {showSkeletons ? (
            <SkeletonEventCards count={3} />
          ) : showError ? (
            <ErrorState
              message="Failed to fetch match history from VLR. API returned 503."
              onRetry={() => setShowError(false)}
            />
          ) : (
            <div className="flex flex-col gap-2">
              {EVENTS.map((ev) => (
                <EventCard key={ev.id} {...ev} />
              ))}
            </div>
          )}
        </Section>

        {/* 8. Empty State */}
        <Section label="Empty State">
          <div
            className="rounded-[12px] border"
            style={{ background: '#0a0a0a', borderColor: '#27272a' }}
          >
            <EmptyState />
          </div>
        </Section>

        {/* 9. Team Page */}
        <Section label="Team Analysis Page">
          <TeamPage team={TEAM} />
        </Section>

        {/* 10. Moneyline Strategy Page */}
        <Section label="MoneyLine Strategy Page">
          <MoneylinePage {...MONEYLINE} />
        </Section>

      </main>

      {/* Toast notifications */}
      <ToastProvider toasts={toasts} onDismiss={dismiss} />
    </>
  )
}
