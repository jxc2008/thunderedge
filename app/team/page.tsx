'use client'

import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { AppHeader } from '@/components/app-header'
import { TeamPage, type TeamData } from '@/components/team-page'
import { EmptyState } from '@/components/ux-patterns'

/* ─── Sample data simulating API response ────────────────── */
function buildTeam(name: string, region: string): TeamData {
  return {
    name: name || 'Sentinels',
    region: region || 'Americas',
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
}

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

export default function TeamAnalysisPage() {
  const [teamInput, setTeamInput] = useState('')
  const [regionInput, setRegionInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult] = useState<TeamData | null>(null)

  const handleAnalyze = () => {
    if (!teamInput.trim()) return
    setIsLoading(true)
    setResult(null)
    setTimeout(() => {
      setResult(buildTeam(teamInput.trim(), regionInput.trim()))
      setIsLoading(false)
    }, 1200)
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
            VCT Team <span style={{ color: '#F97316' }}>Analysis</span>
          </h1>
          <p style={{ fontSize: '0.875rem', color: 'rgba(255,255,255,0.5)', maxWidth: 600, margin: '0 auto 2rem' }}>
            Team statistics, fights per round, and map pick/ban rates — scraped live from VLR.gg.
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
            <div style={{ flex: '1 1 200px' }}>
              <label style={labelStyle}>Team Name</label>
              <input
                type="text"
                value={teamInput}
                onChange={(e) => setTeamInput(e.target.value)}
                onKeyDown={handleKey}
                placeholder="Sentinels, LOUD, Fnatic..."
                style={inputStyle}
              />
            </div>
            <div style={{ flex: '1 1 180px' }}>
              <label style={labelStyle}>Region <span style={{ textTransform: 'none', letterSpacing: 'normal', color: 'rgba(255,255,255,0.25)' }}>(optional)</span></label>
              <input
                type="text"
                value={regionInput}
                onChange={(e) => setRegionInput(e.target.value)}
                onKeyDown={handleKey}
                placeholder="Americas, EMEA, Pacific, China"
                style={inputStyle}
              />
            </div>
            <button
              onClick={handleAnalyze}
              disabled={isLoading || !teamInput.trim()}
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 700,
                fontSize: '0.9rem',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                padding: '0.75rem 2rem',
                background: isLoading || !teamInput.trim() ? 'rgba(249,115,22,0.5)' : '#F97316',
                color: '#000000',
                border: 'none',
                borderRadius: 0,
                cursor: isLoading || !teamInput.trim() ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                flexShrink: 0,
                alignSelf: 'flex-end',
              }}
            >
              {isLoading ? <><Loader2 size={14} className="animate-spin" /> Fetching...</> : 'Analyze Team'}
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
            <p style={{ fontWeight: 600, color: '#e4e4e7', marginBottom: 4 }}>Fetching Team Data</p>
            <p style={{ fontSize: '0.875rem' }}>Scraping statistics from VLR.gg...</p>
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !result && (
          <div style={{ background: '#0a0a0a', border: '1px solid #27272a', borderRadius: 12 }}>
            <EmptyState />
          </div>
        )}

        {/* Results */}
        {!isLoading && result && <TeamPage team={result} />}
      </div>
    </>
  )
}
