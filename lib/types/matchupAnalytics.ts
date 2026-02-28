// lib/types/matchupAnalytics.ts
// Central type registry for matchup analytics — re-exports all matchup-page interfaces

export type {
  MapAction,
  PickBanStats,
  MapRecord,
  RecentMatch,
  AgentCount,
  CompEntry,
  EventOverview,
  TeamOverview,
  H2HMatch,
  OddsInfo,
  FightsPerRoundEntry,
  PerMapKDEntry,
  ProjectedScoreEntry,
  PlayerMapStat,
  PlayerKillStats,
  PlayerKillsData,
  MapProbEntry,
  MapProbsData,
  MispricingPlayer,
  MispricingData,
  AtkDefEntry,
  TeamMatchupData,
  MatchupData,
} from '@/components/matchup-page'

export interface AgentCompWinrateEntry {
  agents: string[]
  wins: number
  losses: number
  played: number
  win_rate: number
}

export interface CompWinratesData {
  team1: { name: string; comp_winrates: Record<string, AgentCompWinrateEntry[]> }
  team2: { name: string; comp_winrates: Record<string, AgentCompWinrateEntry[]> }
}
