'use client'

import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { AppHeader } from '@/components/app-header'
import { RecommendationCard } from '@/components/recommendation-card'
import { StatsGrid, type StatCardData } from '@/components/stats-grid'
import { DistributionChart } from '@/components/distribution-chart'

/* ─── Simple client-side edge calculation ────────────────── */
function americanToDecimal(odds: number) {
  if (odds >= 100) return odds / 100 + 1
  return 100 / Math.abs(odds) + 1
}

function calcEdge(line: number, overOdds: number, underOdds: number) {
  const decOver = americanToDecimal(overOdds)
  const decUnder = americanToDecimal(underOdds)
  const impliedOver = 1 / decOver
  const impliedUnder = 1 / decUnder
  const vig = impliedOver + impliedUnder - 1
  const pOverVigfree = impliedOver / (impliedOver + impliedUnder)
  const pUnderVigfree = 1 - pOverVigfree
  // Simple normal approximation for model
  const modelMu = line + 1.8 // placeholder: model slightly bullish
  const sigma = 4.2
  const z = (line + 0.5 - modelMu) / sigma
  const pOver = 1 - 0.5 * (1 + Math.sign(z) * (1 - Math.exp(-0.7 * z * z)))
  const pUnder = 1 - pOver
  const evOver = pOver * decOver - 1
  const evUnder = pUnder * decUnder - 1
  const roiOver = evOver * 100
  const roiUnder = evUnder * 100
  const recommended =
    roiOver > 3 && roiOver > roiUnder ? 'BET_OVER' as const
    : roiUnder > 3 && roiUnder > roiOver ? 'BET_UNDER' as const
    : 'NO_BET' as const
  const bestEv = recommended === 'BET_OVER' ? evOver : recommended === 'BET_UNDER' ? evUnder : Math.max(evOver, evUnder)
  const stats: StatCardData[] = [
    { label: 'Model Mean', value: modelMu.toFixed(1), delta: 'kills / map', semantic: 'positive' },
    { label: 'Market Implied Mean', value: (pOverVigfree > 0.5 ? line + 0.3 : line - 0.3).toFixed(1), delta: `${(vig * 100).toFixed(1)}% vig`, semantic: 'neutral' },
    { label: 'Model P(Over)', value: `${(pOver * 100).toFixed(1)}%`, delta: 'neg. binomial', semantic: pOver > pOverVigfree ? 'positive' : 'negative' },
    { label: 'Market P(Over)', value: `${(pOverVigfree * 100).toFixed(1)}%`, delta: 'vig-free', semantic: 'neutral' },
    { label: 'EV (Over)', value: `${roiOver >= 0 ? '+' : ''}${roiOver.toFixed(1)}%`, delta: 'expected ROI', semantic: roiOver > 0 ? 'positive' : 'negative' },
    { label: 'EV (Under)', value: `${roiUnder >= 0 ? '+' : ''}${roiUnder.toFixed(1)}%`, delta: 'expected ROI', semantic: roiUnder > 0 ? 'positive' : 'negative' },
  ]
  const dist = Array.from({ length: 15 }, (_, i) => {
    const k = i + Math.floor(line) - 5
    const model = Math.exp(-Math.pow(k - modelMu, 2) / (2 * sigma * sigma)) * 18
    const market = Math.exp(-Math.pow(k - line, 2) / (2 * sigma * sigma)) * 16
    return { kills: k, modelPct: parseFloat(model.toFixed(2)), marketPct: parseFloat(market.toFixed(2)) }
  })
  const confidence = Math.abs(roiOver - roiUnder) > 10 ? 'HIGH' as const : Math.abs(roiOver - roiUnder) > 5 ? 'MED' as const : 'LOW' as const
  return { recommended, bestEv, stats, dist, modelMu, pOver, pUnder, pOverVigfree, pUnderVigfree, roiOver, roiUnder, vig, confidence }
}

const inputStyle: React.CSSProperties = {
  background: '#09090b',
  border: '1px solid #27272a',
  borderRadius: 8,
  color: '#e4e4e7',
  padding: '0.75rem 1rem',
  fontSize: '1rem',
  fontFamily: 'inherit',
  outline: 'none',
  width: '100%',
  transition: 'border-color 0.15s',
}

const labelStyle: React.CSSProperties = {
  fontSize: '0.875rem',
  fontWeight: 500,
  color: '#a1a1aa',
  display: 'block',
  marginBottom: '0.5rem',
}

type Result = ReturnType<typeof calcEdge>

export default function EdgeAnalysisPage() {
  const [player, setPlayer] = useState('yay')
  const [line, setLine] = useState('18.5')
  const [overOdds, setOverOdds] = useState('-110')
  const [underOdds, setUnderOdds] = useState('-110')
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult] = useState<Result | null>(null)
  const [error, setError] = useState('')

  const handleAnalyze = () => {
    const l = parseFloat(line)
    const ov = parseFloat(overOdds)
    const un = parseFloat(underOdds)
    if (!player || isNaN(l) || isNaN(ov) || isNaN(un)) {
      setError('Please fill in all required fields with valid values.')
      return
    }
    setError('')
    setIsLoading(true)
    setResult(null)
    setTimeout(() => {
      setResult(calcEdge(l, ov, un))
      setIsLoading(false)
    }, 800)
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleAnalyze()
  }

  return (
    <>
      <AppHeader activePage="/edge" />

      <div className="page-container" style={{ padding: '0 24px 3rem' }}>
        {/* Hero */}
        <div style={{ textAlign: 'center', padding: '2rem 0 1rem' }}>
          <h1
            className="font-display uppercase"
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 900,
              fontSize: 'clamp(2rem, 5vw, 4rem)',
              letterSpacing: '-0.02em',
              lineHeight: 1.05,
              color: '#ffffff',
              marginBottom: '0.5rem',
            }}
          >
            Mathematical <span style={{ color: '#3B82F6' }}>Edge</span> Analysis
          </h1>
          <p style={{ fontSize: '1rem', color: '#71717a', maxWidth: 600, margin: '0 auto' }}>
            Compare your model&apos;s probability distribution against market odds to find profitable betting edges.
          </p>
        </div>

        {/* Input section */}
        <div
          style={{
            background: '#18181b',
            border: '1px solid #27272a',
            borderRadius: 12,
            padding: '2rem',
            margin: '2rem 0',
          }}
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: '1.5rem',
              marginBottom: '1.5rem',
            }}
          >
            <div>
              <label style={labelStyle}>Player IGN</label>
              <input type="text" value={player} onChange={(e) => setPlayer(e.target.value)} onKeyDown={handleKey} placeholder="e.g., yay" style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Kill Line</label>
              <input type="number" step="0.5" value={line} onChange={(e) => setLine(e.target.value)} onKeyDown={handleKey} placeholder="18.5" style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Over Odds</label>
              <input type="number" value={overOdds} onChange={(e) => setOverOdds(e.target.value)} onKeyDown={handleKey} placeholder="-110" style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Under Odds</label>
              <input type="number" value={underOdds} onChange={(e) => setUnderOdds(e.target.value)} onKeyDown={handleKey} placeholder="-110" style={inputStyle} />
            </div>
          </div>

          <button
            onClick={handleAnalyze}
            disabled={isLoading}
            style={{
              width: '100%',
              padding: '0.875rem 2rem',
              background: isLoading ? 'rgba(59,130,246,0.5)' : 'linear-gradient(135deg, #3b82f6 0%, #0ea5e9 100%)',
              border: 'none',
              borderRadius: 8,
              color: '#ffffff',
              fontWeight: 600,
              fontSize: '1rem',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              transition: 'opacity 0.15s',
            }}
          >
            {isLoading ? <><Loader2 size={16} className="animate-spin" /> Analyzing...</> : 'Analyze Edge'}
          </button>

          {error && (
            <div style={{ marginTop: '1rem', background: 'rgba(239,68,68,0.1)', border: '1px solid #ef4444', borderRadius: 8, padding: '0.75rem 1rem', color: '#ef4444', fontSize: '0.875rem' }}>
              {error}
            </div>
          )}
        </div>

        {/* Results */}
        {result && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', marginTop: '1rem' }}>
            <RecommendationCard
              type={result.recommended}
              ev={result.bestEv}
              confidence={result.confidence}
              reason={
                result.recommended === 'BET_OVER'
                  ? `Model mean ${result.modelMu.toFixed(1)} exceeds market. Over has ${result.roiOver.toFixed(1)}% expected ROI.`
                  : result.recommended === 'BET_UNDER'
                  ? `Model mean ${result.modelMu.toFixed(1)} is below market. Under has ${result.roiUnder.toFixed(1)}% expected ROI.`
                  : 'Insufficient edge to justify a bet. Market appears efficiently priced.'
              }
            />
            <StatsGrid stats={result.stats} columns={3} />
            <DistributionChart
              data={result.dist}
              killLine={parseFloat(line)}
              modelOverPct={result.pOver * 100}
              marketOverPct={result.pOverVigfree * 100}
            />

            {/* Comparison table */}
            <div style={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 12, padding: '1.5rem' }}>
              <h3 style={{ fontSize: '1.125rem', fontWeight: 600, color: '#ffffff', marginBottom: '1rem', borderBottom: '1px solid #27272a', paddingBottom: '0.5rem' }}>
                Probability Comparison
              </h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                  <thead>
                    <tr>
                      {['Side', 'Model P(Win)', 'Market P(Win)', 'Prob Edge', 'EV per $1', 'ROI %'].map(h => (
                        <th key={h} style={{ padding: '0.5rem 0.75rem', textAlign: 'left', borderBottom: '1px solid #27272a', color: '#71717a', fontWeight: 500, textTransform: 'uppercase', fontSize: '0.75rem', letterSpacing: '0.05em' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { side: 'OVER', model: result.pOver, market: result.pOverVigfree, ev: result.roiOver / 100, roi: result.roiOver },
                      { side: 'UNDER', model: result.pUnder, market: result.pUnderVigfree, ev: result.roiUnder / 100, roi: result.roiUnder },
                    ].map(row => (
                      <tr key={row.side}>
                        <td style={{ padding: '0.75rem', borderBottom: '1px solid #27272a', fontWeight: 700, color: '#ffffff' }}>{row.side}</td>
                        <td style={{ padding: '0.75rem', borderBottom: '1px solid #27272a', color: '#e4e4e7' }}>{(row.model * 100).toFixed(2)}%</td>
                        <td style={{ padding: '0.75rem', borderBottom: '1px solid #27272a', color: '#e4e4e7' }}>{(row.market * 100).toFixed(2)}%</td>
                        <td style={{ padding: '0.75rem', borderBottom: '1px solid #27272a', color: row.model - row.market >= 0 ? '#22c55e' : '#ef4444' }}>
                          {row.model - row.market >= 0 ? '+' : ''}{((row.model - row.market) * 100).toFixed(2)}%
                        </td>
                        <td style={{ padding: '0.75rem', borderBottom: '1px solid #27272a', color: row.ev >= 0 ? '#22c55e' : '#ef4444' }}>
                          ${row.ev.toFixed(4)}
                        </td>
                        <td style={{ padding: '0.75rem', borderBottom: '1px solid #27272a', color: row.roi >= 0 ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
                          {row.roi >= 0 ? '+' : ''}{row.roi.toFixed(2)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
