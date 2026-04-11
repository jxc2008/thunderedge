'use client'

import { useState } from 'react'
import { Loader2, Calendar, ChevronRight } from 'lucide-react'
import { AppHeader } from '@/components/app-header'
import { MatchupPage, type MatchupData, type PredictionResult } from '@/components/matchup-page'
import { API_BASE } from '@/lib/api'

const inputStyle: React.CSSProperties = {
  background: '#0a0a0a',
  border: '1px solid rgba(255,255,255,0.1)',
  color: '#ffffff',
  padding: '0.75rem 1rem',
  fontSize: '0.875rem',
  fontFamily: 'inherit',
  outline: 'none',
  borderRadius: 0,
  width: '100%',
  transition: 'border-color 0.15s',
}

const labelStyle: React.CSSProperties = {
  fontSize: '0.7rem',
  fontWeight: 500,
  textTransform: 'uppercase' as const,
  letterSpacing: '0.12em',
  color: 'rgba(255,255,255,0.4)',
  display: 'block',
  marginBottom: '0.5rem',
}

interface TomorrowMatch {
  team_a: string
  team_b: string
  event: string
  match_url: string
  day: string
  prediction: (PredictionResult & { success?: boolean }) | null
  error: string | null
}

function edgeColor(edge: number) {
  const a = Math.abs(edge)
  return a >= 0.05 ? (edge > 0 ? '#22c55e' : '#ef4444') : a >= 0.02 ? '#f59e0b' : '#71717a'
}

function TomorrowPanel({
  matches,
  onSelect,
  loading,
}: {
  matches: TomorrowMatch[]
  onSelect: (teamA: string, teamB: string) => void
  loading: boolean
}) {
  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '2rem', color: '#71717a' }}>
        <Loader2 size={20} className="animate-spin" style={{ margin: '0 auto 0.5rem' }} />
        <p style={{ fontSize: '0.875rem' }}>Scraping VLR.gg + running predictions...</p>
        <p style={{ fontSize: '0.75rem', color: '#52525b', marginTop: 4 }}>~10s per match</p>
      </div>
    )
  }

  if (matches.length === 0) {
    return (
      <p style={{ fontSize: '0.875rem', color: '#52525b', padding: '1rem 0' }}>
        No upcoming VCT matches found for today/tomorrow.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {matches.map((m, i) => {
        const pred = m.prediction
        const ask = 50
        const edge = pred ? pred.expected_theo - ask / 100 : null
        const eColor = edge !== null ? edgeColor(edge) : '#71717a'
        return (
          <button
            key={i}
            onClick={() => onSelect(m.team_a, m.team_b)}
            style={{
              background: '#0a0a0a',
              border: '1px solid #27272a',
              padding: '0.75rem 1rem',
              cursor: 'pointer',
              textAlign: 'left',
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              fontFamily: 'inherit',
              transition: 'border-color 0.15s',
            }}
            onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.borderColor = '#3f3f46')}
            onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.borderColor = '#27272a')}
          >
            {/* Teams */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontSize: '0.875rem', fontWeight: 600, color: '#e4e4e7', marginBottom: 2 }}>
                {m.team_a} <span style={{ color: 'rgba(255,255,255,0.25)', fontWeight: 400 }}>vs</span> {m.team_b}
              </p>
              <p style={{ fontSize: '0.7rem', color: '#52525b', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {m.event} &middot; {m.day}
              </p>
            </div>

            {/* Prediction badge */}
            {pred && edge !== null && (
              <div style={{ textAlign: 'right', flexShrink: 0 }}>
                <p style={{ fontSize: '0.8rem', fontWeight: 700, color: eColor, fontVariantNumeric: 'tabular-nums' }}>
                  {edge >= 0 ? '+' : ''}{(edge * 100).toFixed(1)}c
                </p>
                <p style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.3)' }}>
                  {pred.model_confidence} · theo {(pred.expected_theo * 100).toFixed(0)}c
                </p>
              </div>
            )}
            {m.error && (
              <p style={{ fontSize: '0.7rem', color: '#71717a', flexShrink: 0 }}>no data</p>
            )}

            <ChevronRight size={14} style={{ color: '#3f3f46', flexShrink: 0 }} />
          </button>
        )
      })}
    </div>
  )
}

export default function MatchupAnalysisPage() {
  const [team1, setTeam1] = useState('')
  const [team2, setTeam2] = useState('')
  const [team1Odds, setTeam1Odds] = useState('')
  const [team2Odds, setTeam2Odds] = useState('')
  const [ask, setAsk] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult] = useState<MatchupData | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [showTomorrow, setShowTomorrow] = useState(false)
  const [tomorrowLoading, setTomorrowLoading] = useState(false)
  const [tomorrowMatches, setTomorrowMatches] = useState<TomorrowMatch[]>([])
  const [tomorrowError, setTomorrowError] = useState<string | null>(null)

  const canAnalyze = team1.trim().length > 0 && team2.trim().length > 0

  const handleAnalyze = async (t1 = team1, t2 = team2) => {
    if (!t1.trim() || !t2.trim()) return
    setIsLoading(true)
    setResult(null)
    setError(null)

    const askVal = parseInt(ask) || 50

    const params = new URLSearchParams({ team1: t1.trim(), team2: t2.trim() })
    if (team1Odds.trim()) params.set('team1_odds', team1Odds.trim())
    if (team2Odds.trim()) params.set('team2_odds', team2Odds.trim())

    try {
      // Fetch matchup data + prediction in parallel
      const [matchupRes, predRes] = await Promise.all([
        fetch(`${API_BASE}/api/matchup?${params}`),
        fetch(`${API_BASE}/api/matchup/prediction?team1=${encodeURIComponent(t1.trim())}&team2=${encodeURIComponent(t2.trim())}&ask=${askVal}`),
      ])

      const matchupJson = await matchupRes.json()
      if (!matchupRes.ok || matchupJson.error) {
        setError(matchupJson.error ?? 'Unknown error')
        return
      }

      let prediction: PredictionResult | null = null
      if (predRes.ok) {
        const predJson = await predRes.json()
        if (predJson.success) prediction = predJson
      }

      setResult({ ...matchupJson, prediction, ask: askVal })
    } catch (e) {
      setError(String(e))
    } finally {
      setIsLoading(false)
    }
  }

  const handleTomorrow = async () => {
    setShowTomorrow(true)
    if (tomorrowMatches.length > 0) return   // cached
    setTomorrowLoading(true)
    setTomorrowError(null)
    try {
      const res = await fetch(`${API_BASE}/api/tomorrow?ask=50`)
      const json = await res.json()
      if (!res.ok || json.error) {
        setTomorrowError(json.error ?? 'Failed to fetch matches')
      } else {
        setTomorrowMatches(json.matches ?? [])
      }
    } catch (e) {
      setTomorrowError(String(e))
    } finally {
      setTomorrowLoading(false)
    }
  }

  const handleSelectMatch = (teamA: string, teamB: string) => {
    setTeam1(teamA)
    setTeam2(teamB)
    setShowTomorrow(false)
    handleAnalyze(teamA, teamB)
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleAnalyze()
  }

  return (
    <>
      <AppHeader activePage="/team" />

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
            Team <span style={{ color: '#F97316' }}>Matchup</span>
          </h1>
          <p style={{ fontSize: '0.875rem', color: 'rgba(255,255,255,0.5)', maxWidth: 600, margin: '0 auto 2rem' }}>
            Compare two VCT teams: map records, pick/ban tendencies, model prediction, and Kalshi edge.
          </p>
        </div>

        {/* Tomorrow button */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.75rem' }}>
          <button
            onClick={handleTomorrow}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: showTomorrow ? 'rgba(249,115,22,0.12)' : 'transparent',
              border: `1px solid ${showTomorrow ? 'rgba(249,115,22,0.4)' : 'rgba(255,255,255,0.12)'}`,
              color: showTomorrow ? '#F97316' : 'rgba(255,255,255,0.6)',
              padding: '0.5rem 1rem',
              fontSize: '0.8rem',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              cursor: 'pointer',
              fontFamily: 'inherit',
              borderRadius: 0,
            }}
          >
            <Calendar size={13} />
            Upcoming Matches
          </button>
        </div>

        {/* Tomorrow panel */}
        {showTomorrow && (
          <div
            style={{
              background: '#0a0a0a',
              border: '1px solid rgba(249,115,22,0.15)',
              borderLeft: '3px solid #F97316',
              padding: '1.25rem 1.5rem',
              marginBottom: '1.5rem',
            }}
          >
            <p style={{ fontSize: '0.7rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'rgba(255,255,255,0.3)', marginBottom: '1rem' }}>
              Today / Tomorrow — VCT Matches (@ 50c market)
            </p>
            {tomorrowError && (
              <p style={{ color: '#fca5a5', fontSize: '0.85rem' }}>{tomorrowError}</p>
            )}
            <TomorrowPanel
              matches={tomorrowMatches}
              onSelect={handleSelectMatch}
              loading={tomorrowLoading}
            />
          </div>
        )}

        {/* Search section */}
        <div
          style={{
            background: '#141210',
            border: '1px solid rgba(249,115,22,0.15)',
            borderLeft: '3px solid #F97316',
            padding: '2rem',
            marginBottom: '2rem',
          }}
        >
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end' }}>
            {/* Team 1 */}
            <div style={{ flex: '1 1 160px' }}>
              <label style={{ ...labelStyle, color: '#3b82f6' }}>Team 1 (YES)</label>
              <input
                type="text"
                value={team1}
                onChange={(e) => setTeam1(e.target.value)}
                onKeyDown={handleKey}
                placeholder="Sentinels, LOUD..."
                style={{ ...inputStyle, borderColor: team1.trim() ? 'rgba(59,130,246,0.4)' : 'rgba(255,255,255,0.1)' }}
              />
            </div>

            {/* Team 2 */}
            <div style={{ flex: '1 1 160px' }}>
              <label style={{ ...labelStyle, color: '#f97316' }}>Team 2 (NO)</label>
              <input
                type="text"
                value={team2}
                onChange={(e) => setTeam2(e.target.value)}
                onKeyDown={handleKey}
                placeholder="Cloud9, 100T..."
                style={{ ...inputStyle, borderColor: team2.trim() ? 'rgba(249,115,22,0.4)' : 'rgba(255,255,255,0.1)' }}
              />
            </div>

            {/* Kalshi Ask */}
            <div style={{ flex: '0 1 90px' }}>
              <label style={labelStyle}>
                Kalshi Ask{' '}
                <span style={{ textTransform: 'none', letterSpacing: 'normal', color: 'rgba(255,255,255,0.2)' }}>(¢)</span>
              </label>
              <input
                type="text"
                value={ask}
                onChange={(e) => setAsk(e.target.value)}
                onKeyDown={handleKey}
                placeholder="50"
                style={inputStyle}
              />
            </div>

            {/* Odds (optional) */}
            <div style={{ flex: '0 1 90px' }}>
              <label style={labelStyle}>
                T1 Odds{' '}
                <span style={{ textTransform: 'none', letterSpacing: 'normal', color: 'rgba(255,255,255,0.2)' }}>(opt)</span>
              </label>
              <input
                type="text"
                value={team1Odds}
                onChange={(e) => setTeam1Odds(e.target.value)}
                onKeyDown={handleKey}
                placeholder="1.50"
                style={inputStyle}
              />
            </div>

            <div style={{ flex: '0 1 90px' }}>
              <label style={labelStyle}>
                T2 Odds{' '}
                <span style={{ textTransform: 'none', letterSpacing: 'normal', color: 'rgba(255,255,255,0.2)' }}>(opt)</span>
              </label>
              <input
                type="text"
                value={team2Odds}
                onChange={(e) => setTeam2Odds(e.target.value)}
                onKeyDown={handleKey}
                placeholder="2.40"
                style={inputStyle}
              />
            </div>

            <button
              onClick={() => handleAnalyze()}
              disabled={isLoading || !canAnalyze}
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 700,
                fontSize: '0.9rem',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                padding: '0.75rem 2rem',
                background: isLoading || !canAnalyze ? 'rgba(249,115,22,0.5)' : '#F97316',
                color: '#000000',
                border: 'none',
                borderRadius: 0,
                cursor: isLoading || !canAnalyze ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                flexShrink: 0,
                alignSelf: 'flex-end',
              }}
            >
              {isLoading ? <><Loader2 size={14} className="animate-spin" /> Analyzing...</> : 'Analyze Matchup'}
            </button>
          </div>
        </div>

        {/* Loading */}
        {isLoading && (
          <div style={{ textAlign: 'center', padding: '3rem', color: '#71717a' }}>
            <div style={{
              width: 40, height: 40,
              border: '3px solid #27272a',
              borderTop: '3px solid #F97316',
              borderRadius: '50%',
              animation: 'spin 0.8s linear infinite',
              margin: '0 auto 1rem',
            }} />
            <p style={{ fontWeight: 600, color: '#e4e4e7', marginBottom: 4 }}>Fetching Matchup + Prediction</p>
            <p style={{ fontSize: '0.875rem' }}>Running pick/ban model...</p>
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </div>
        )}

        {/* Error */}
        {!isLoading && error && (
          <div
            style={{
              background: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.2)',
              borderLeft: '3px solid #ef4444',
              padding: '1rem 1.25rem',
              color: '#fca5a5',
              fontSize: '0.875rem',
            }}
          >
            {error}
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !result && !error && (
          <div
            style={{
              textAlign: 'center',
              padding: '4rem 2rem',
              background: '#0a0a0a',
              border: '1px solid #27272a',
              color: 'rgba(255,255,255,0.25)',
            }}
          >
            <p style={{ fontSize: '2rem', marginBottom: '0.75rem' }}>⚔</p>
            <p style={{ fontSize: '0.875rem' }}>Enter two team names above, or click Upcoming Matches</p>
          </div>
        )}

        {/* Results */}
        {!isLoading && result && <MatchupPage data={result} />}
      </div>
    </>
  )
}
