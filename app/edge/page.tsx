'use client'

import { useState } from 'react'
import { Loader2, BarChart2 } from 'lucide-react'
import { AppHeader } from '@/components/app-header'
import { DistributionChart } from '@/components/distribution-chart'

/* ─── API types ──────────────────────────────────────────── */
interface EdgeResponse {
  success: boolean
  player: { ign: string; sample_size: number; confidence: string }
  line: number
  model: { dist: string; mu: number; var: number; p_over: number; p_under: number }
  market: {
    over_odds: number
    under_odds: number
    p_over_vigfree: number
    p_under_vigfree: number
    vig_percentage: number
    mu_implied: number
  }
  matchup_adjustment: { applied: boolean; team_win_prob?: number; mu_base?: number; mu_adjusted?: number; multiplier?: number }
  edge: {
    prob_edge_over: number
    prob_edge_under: number
    ev_over: number
    ev_under: number
    recommended: string
    best_ev: number
    roi_over_pct: number
    roi_under_pct: number
  }
  visualization: {
    x: number[]
    model_pmf: number[]
    market_pmf: number[]
    line_position: number
  }
}

/* ─── Helpers ────────────────────────────────────────────── */
function confidenceStyle(ev: number): { bg: string; color: string; label: string } {
  const roi = ev * 100
  if (roi >= 8) return { bg: 'rgba(34,197,94,0.15)', color: '#22c55e', label: 'HIGH CONFIDENCE' }
  if (roi >= 3) return { bg: 'rgba(245,158,11,0.15)', color: '#f59e0b', label: 'MEDIUM CONFIDENCE' }
  return { bg: 'rgba(239,68,68,0.15)', color: '#ef4444', label: 'LOW CONFIDENCE' }
}

/* ─── Main page ──────────────────────────────────────────── */
export default function EdgePage() {
  const [form, setForm] = useState({
    player: '',
    line: '18.5',
    overOdds: '-110',
    underOdds: '-110',
    teamOdds: '',
    oppOdds: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<EdgeResponse | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const player = form.player.trim()
    const line = parseFloat(form.line)
    const overOdds = parseFloat(form.overOdds)
    const underOdds = parseFloat(form.underOdds)

    if (!player || isNaN(line) || isNaN(overOdds) || isNaN(underOdds)) {
      setError('Please fill in all required fields with valid values')
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    const teamOdds = parseFloat(form.teamOdds)
    const oppOdds = parseFloat(form.oppOdds)
    const matchupQuery = (!isNaN(teamOdds) && !isNaN(oppOdds))
      ? `&team_odds=${teamOdds}&opp_odds=${oppOdds}`
      : ''

    try {
      const res = await fetch(
        `/api/edge/${encodeURIComponent(player)}?line=${line}&over_odds=${overOdds}&under_odds=${underOdds}${matchupQuery}`
      )
      const data = await res.json()
      if (data.error) { setError(data.error); return }
      setResult(data)
    } catch (err) {
      setError('Failed to fetch analysis: ' + (err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  /* Build chart data from PMF arrays */
  function buildChartData(r: EdgeResponse) {
    return r.visualization.x.map((k, i) => ({
      kills: k,
      modelPct: parseFloat(((r.visualization.model_pmf[i] ?? 0) * 100).toFixed(2)),
      marketPct: parseFloat(((r.visualization.market_pmf[i] ?? 0) * 100).toFixed(2)),
    }))
  }

  const rec = result?.edge.recommended ?? ''
  const recColor = rec === 'OVER' ? '#22c55e' : rec === 'UNDER' ? '#ef4444' : '#71717a'
  const bestEVPct = (result?.edge.best_ev ?? 0) * 100
  const confStyle = result ? confidenceStyle(result.edge.best_ev) : null

  return (
    <>
      <AppHeader activePage="/edge" />

      <main className="page-container py-8 flex flex-col gap-6">
        {/* Hero */}
        <div className="text-center pt-4 pb-2">
          <h1
            className="font-bold tracking-tight text-balance"
            style={{ fontSize: 'clamp(1.75rem, 4vw, 2.5rem)', color: '#ffffff' }}
          >
            Mathematical Edge Analysis
          </h1>
          <p className="text-sm mt-1 max-w-lg mx-auto text-pretty" style={{ color: '#71717a' }}>
            Compare your model&apos;s probability distribution against market odds to find profitable betting edges
          </p>
        </div>

        {/* Input form */}
        <form onSubmit={handleSubmit}>
          <div
            className="rounded-[12px] border p-6"
            style={{ background: '#18181b', borderColor: '#27272a' }}
          >
            <div
              className="grid gap-4 mb-5"
              style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}
            >
              {[
                { id: 'player', label: 'Player IGN', type: 'text', placeholder: 'e.g. yay', key: 'player' as keyof typeof form },
                { id: 'line', label: 'Kill Line', type: 'number', placeholder: 'e.g. 18.5', key: 'line' as keyof typeof form },
                { id: 'overOdds', label: 'Over Odds', type: 'number', placeholder: 'e.g. -110', key: 'overOdds' as keyof typeof form },
                { id: 'underOdds', label: 'Under Odds', type: 'number', placeholder: 'e.g. -110', key: 'underOdds' as keyof typeof form },
                { id: 'teamOdds', label: 'Team Odds (optional)', type: 'number', placeholder: 'e.g. 1.65 or -155', key: 'teamOdds' as keyof typeof form },
                { id: 'oppOdds', label: 'Opponent Odds (optional)', type: 'number', placeholder: 'e.g. 2.25 or +140', key: 'oppOdds' as keyof typeof form },
              ].map(({ id, label, type, placeholder, key }) => (
                <div key={id} className="flex flex-col gap-1.5">
                  <label htmlFor={id} className="text-sm font-medium" style={{ color: '#a1a1aa' }}>
                    {label}
                  </label>
                  <input
                    id={id}
                    type={type}
                    step={type === 'number' ? '0.5' : undefined}
                    placeholder={placeholder}
                    value={form[key]}
                    onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                    className="h-11 px-3 rounded-[8px] border text-sm outline-none"
                    style={{ background: '#09090b', borderColor: '#27272a', color: '#e4e4e7' }}
                  />
                </div>
              ))}
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full h-11 rounded-[8px] text-sm font-semibold text-white flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ background: 'linear-gradient(135deg, #3b82f6, #0ea5e9)' }}
            >
              {loading ? <><Loader2 size={15} className="animate-spin" /> Analyzing...</> : 'Analyze Edge'}
            </button>
            {error && (
              <div
                className="mt-3 px-3 py-2 rounded-[8px] text-sm"
                style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid #ef4444', color: '#ef4444' }}
              >
                {error}
              </div>
            )}
          </div>
        </form>

        {/* Loading */}
        {loading && (
          <div className="text-center py-8" style={{ color: '#71717a' }}>
            Analyzing...
          </div>
        )}

        {/* Results */}
        {result && !loading && (
          <div className="flex flex-col gap-5">
            {/* Recommendation card */}
            <div
              className="rounded-[12px] border-2 p-6 text-center"
              style={{
                borderColor: recColor,
                background: `linear-gradient(180deg, #18181b 0%, ${rec === 'OVER' ? 'rgba(34,197,94,0.05)' : rec === 'UNDER' ? 'rgba(239,68,68,0.05)' : 'rgba(113,113,122,0.05)'} 100%)`,
              }}
            >
              <p className="font-bold" style={{ fontSize: '1.5rem', color: recColor }}>
                {rec === 'NO BET' ? 'NO BET' : `BET ${rec}`}
              </p>
              <p className="font-extrabold tabular-nums mt-2" style={{ fontSize: '2.5rem', color: bestEVPct >= 0 ? '#22c55e' : '#ef4444' }}>
                {bestEVPct >= 0 ? '+' : ''}{bestEVPct.toFixed(1)}% ROI
              </p>
              {confStyle && (
                <span
                  className="inline-block mt-2 text-[0.7rem] font-semibold uppercase tracking-widest px-3 py-1 rounded-[6px]"
                  style={{ background: confStyle.bg, color: confStyle.color }}
                >
                  {confStyle.label}
                </span>
              )}
              <p className="mt-3 text-sm" style={{ color: '#a1a1aa' }}>
                Your model suggests stronger edge on the {rec === 'NO BET' ? 'neither' : rec.toLowerCase()} side
              </p>
            </div>

            {/* Stats grid */}
            <div
              className="grid gap-4"
              style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}
            >
              {[
                { label: 'Model Mean', value: result.model.mu.toFixed(2), detail: result.model.dist },
                { label: 'Market Implied Mean', value: result.market.mu_implied.toFixed(2), detail: `${result.market.vig_percentage.toFixed(2)}% vig` },
                { label: 'Sample Size', value: result.player.sample_size, detail: 'maps analyzed' },
                { label: 'Best EV', value: `${(result.edge.best_ev * 100).toFixed(1)}%`, detail: result.edge.recommended },
              ].map(({ label, value, detail }) => (
                <div
                  key={label}
                  className="rounded-[12px] border p-5"
                  style={{ background: '#18181b', borderColor: '#27272a' }}
                >
                  <p className="text-sm" style={{ color: '#71717a' }}>{label}</p>
                  <p className="font-bold tabular-nums mt-1" style={{ fontSize: '1.5rem', color: '#e4e4e7' }}>{value}</p>
                  <p className="text-xs mt-0.5" style={{ color: '#a1a1aa' }}>{detail}</p>
                </div>
              ))}
            </div>

            {/* Distribution chart */}
            <div
              className="rounded-[12px] border p-6"
              style={{ background: '#18181b', borderColor: '#27272a' }}
            >
              <h3 className="text-lg font-semibold text-center mb-5" style={{ color: '#ffffff' }}>
                Kill Distribution: Model vs Market
              </h3>
              <DistributionChart
                data={buildChartData(result)}
                killLine={result.line}
                modelOverPct={result.model.p_over * 100}
                marketOverPct={result.market.p_over_vigfree * 100}
              />
            </div>

            {/* Comparison table */}
            <div
              className="rounded-[12px] border p-6"
              style={{ background: '#18181b', borderColor: '#27272a' }}
            >
              <h3 className="text-lg font-semibold mb-4" style={{ color: '#ffffff' }}>
                Probability Comparison
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm" style={{ minWidth: 480 }}>
                  <thead>
                    <tr>
                      {['Side', 'Model P(Win)', 'Market P(Win)', 'Prob Edge', 'EV per $1', 'ROI %'].map((h) => (
                        <th
                          key={h}
                          className="text-left py-3 px-4 text-[0.75rem] uppercase tracking-wider font-semibold"
                          style={{ color: '#71717a', borderBottom: '1px solid #27272a' }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      {
                        side: 'OVER',
                        modelP: result.model.p_over,
                        marketP: result.market.p_over_vigfree,
                        edge: result.edge.prob_edge_over,
                        ev: result.edge.ev_over,
                        roi: result.edge.roi_over_pct,
                      },
                      {
                        side: 'UNDER',
                        modelP: result.model.p_under,
                        marketP: result.market.p_under_vigfree,
                        edge: result.edge.prob_edge_under,
                        ev: result.edge.ev_under,
                        roi: result.edge.roi_under_pct,
                      },
                    ].map((row) => (
                      <tr key={row.side} style={{ borderBottom: '1px solid #27272a' }}>
                        <td className="py-4 px-4 font-semibold" style={{ color: row.side === 'OVER' ? '#22c55e' : '#ef4444' }}>
                          {row.side}
                        </td>
                        <td className="py-4 px-4 tabular-nums" style={{ color: '#e4e4e7' }}>
                          {(row.modelP * 100).toFixed(1)}%
                        </td>
                        <td className="py-4 px-4 tabular-nums" style={{ color: '#e4e4e7' }}>
                          {(row.marketP * 100).toFixed(1)}%
                        </td>
                        <td className="py-4 px-4 tabular-nums" style={{ color: row.edge >= 0 ? '#22c55e' : '#ef4444' }}>
                          {row.edge >= 0 ? '+' : ''}{(row.edge * 100).toFixed(1)}pp
                        </td>
                        <td className="py-4 px-4 tabular-nums font-semibold" style={{ color: row.ev >= 0 ? '#22c55e' : '#ef4444' }}>
                          {row.ev >= 0 ? '+' : ''}{row.ev.toFixed(3)}
                        </td>
                        <td className="py-4 px-4 tabular-nums font-semibold" style={{ color: row.roi >= 0 ? '#22c55e' : '#ef4444' }}>
                          {row.roi >= 0 ? '+' : ''}{row.roi.toFixed(1)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Empty state */}
        {!result && !loading && !error && (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <BarChart2 size={56} style={{ color: '#ffffff', opacity: 0.1 }} />
            <p className="text-sm" style={{ color: 'rgba(255,255,255,0.25)' }}>
              Fill in the form above to analyze edge
            </p>
          </div>
        )}
      </main>
    </>
  )
}
