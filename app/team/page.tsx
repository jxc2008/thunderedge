'use client'

import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { AppHeader } from '@/components/app-header'
import { MatchupPage, type MatchupData } from '@/components/matchup-page'
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

export default function MatchupAnalysisPage() {
  const [team1, setTeam1] = useState('')
  const [team2, setTeam2] = useState('')
  const [team1Odds, setTeam1Odds] = useState('')
  const [team2Odds, setTeam2Odds] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult] = useState<MatchupData | null>(null)
  const [error, setError] = useState<string | null>(null)

  const canAnalyze = team1.trim().length > 0 && team2.trim().length > 0

  const handleAnalyze = async () => {
    if (!canAnalyze) return
    setIsLoading(true)
    setResult(null)
    setError(null)

    const params = new URLSearchParams({
      team1: team1.trim(),
      team2: team2.trim(),
    })
    if (team1Odds.trim()) params.set('team1_odds', team1Odds.trim())
    if (team2Odds.trim()) params.set('team2_odds', team2Odds.trim())

    try {
      const res = await fetch(`${API_BASE}/api/matchup?${params}`)
      const json = await res.json()
      if (!res.ok || json.error) {
        setError(json.error ?? 'Unknown error')
        return
      }

      // Fetch supplemental data (separate endpoints, non-critical)
      const killsParams = new URLSearchParams({ team1: team1.trim(), team2: team2.trim() })
      try {
        const [killsRes, probsRes, mispricingRes, compWinratesRes] = await Promise.all([
          fetch(`${API_BASE}/api/matchup/player-kills?${killsParams}`),
          fetch(`${API_BASE}/api/matchup/map-probs?${killsParams}`),
          fetch(`${API_BASE}/api/matchup/mispricing?${killsParams}`),
          fetch(`${API_BASE}/api/matchup/comp-winrates?${killsParams}`),
        ])
        const killsJson = await killsRes.json()
        if (killsRes.ok && killsJson.success) {
          json.player_kills = killsJson
        }
        const probsJson = await probsRes.json()
        if (probsRes.ok && probsJson.success) {
          json.map_probs = probsJson
        }
        const mispricingJson = await mispricingRes.json()
        if (mispricingRes.ok && mispricingJson.success) {
          json.mispricing = mispricingJson
        }
        const compWinratesJson = await compWinratesRes.json()
        if (compWinratesRes.ok && compWinratesJson.success) {
          json.comp_winrates = compWinratesJson
        }
      } catch {
        // supplemental endpoints are non-critical; proceed without them
      }

      setResult(json)
    } catch (e) {
      setError(String(e))
    } finally {
      setIsLoading(false)
    }
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
            Compare two VCT teams: map records, pick/ban tendencies, agent comps, and recent history.
          </p>
        </div>

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
              <label style={{ ...labelStyle, color: '#3b82f6' }}>Team 1</label>
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
              <label style={{ ...labelStyle, color: '#f97316' }}>Team 2</label>
              <input
                type="text"
                value={team2}
                onChange={(e) => setTeam2(e.target.value)}
                onKeyDown={handleKey}
                placeholder="Cloud9, 100T..."
                style={{ ...inputStyle, borderColor: team2.trim() ? 'rgba(249,115,22,0.4)' : 'rgba(255,255,255,0.1)' }}
              />
            </div>

            {/* Odds (optional) */}
            <div style={{ flex: '0 1 100px' }}>
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

            <div style={{ flex: '0 1 100px' }}>
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
              onClick={handleAnalyze}
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
            <p style={{ fontWeight: 600, color: '#e4e4e7', marginBottom: 4 }}>Fetching Matchup Data</p>
            <p style={{ fontSize: '0.875rem' }}>Querying historical records...</p>
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
            <p style={{ fontSize: '0.875rem' }}>Enter two team names above to compare</p>
          </div>
        )}

        {/* Results */}
        {!isLoading && result && <MatchupPage data={result} />}
      </div>
    </>
  )
}
