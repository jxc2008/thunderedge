'use client'

import { DistributionChart } from './distribution-chart'

export interface EdgeData {
  edge: {
    recommended: string
    ev_over: number
    ev_under: number
    prob_edge_over: number
    prob_edge_under: number
    roi_over_pct: number
    roi_under_pct: number
  }
  model: { p_over: number; p_under: number; mu: number }
  market: { p_over_vigfree: number; p_under_vigfree: number; mu_implied: number }
  player: { confidence: string; sample_size: number }
  visualization: { x: number[]; model_pmf: number[]; market_pmf: number[] }
}

interface EdgeSectionProps {
  edge: EdgeData
  line: number
}

export function EdgeSection({ edge, line }: EdgeSectionProps) {
  const e = edge?.edge
  const model = edge?.model
  const market = edge?.market
  const viz = edge?.visualization
  const recommended = e?.recommended ?? 'NO BET'
  const isOver = recommended === 'OVER'
  const isUnder = recommended === 'UNDER'
  const accentColor = isOver ? '#22c55e' : isUnder ? '#ef4444' : 'rgba(255,255,255,0.4)'

  const dist = (viz?.x ?? []).map((x, i) => ({
    kills: x,
    modelPct: +((viz?.model_pmf?.[i] ?? 0) * 100).toFixed(3),
    marketPct: +((viz?.market_pmf?.[i] ?? 0) * 100).toFixed(3),
  }))

  const confLevel = edge?.player?.confidence ?? 'LOW'
  const confClass =
    confLevel === 'HIGH'
      ? 'bg-[rgba(34,197,94,0.15)] text-[#22c55e] border-[rgba(34,197,94,0.3)]'
      : confLevel === 'MED'
        ? 'bg-[rgba(234,179,8,0.15)] text-[#eab308] border-[rgba(234,179,8,0.3)]'
        : 'bg-[rgba(239,68,68,0.15)] text-[#ef4444] border-[rgba(239,68,68,0.3)]'

  const metrics = [
    {
      label: 'Model P(Over)',
      value: `${((model?.p_over ?? 0) * 100).toFixed(1)}%`,
      positive: (model?.p_over ?? 0) > 0.5,
    },
    {
      label: 'Market P(Over)',
      value: `${((market?.p_over_vigfree ?? 0) * 100).toFixed(1)}%`,
      positive: false,
    },
    {
      label: 'Prob Edge Over',
      value: `${(e?.prob_edge_over ?? 0) > 0 ? '+' : ''}${((e?.prob_edge_over ?? 0) * 100).toFixed(1)}pp`,
      positive: (e?.prob_edge_over ?? 0) > 0,
    },
    {
      label: 'EV Over',
      value: `${(e?.ev_over ?? 0) > 0 ? '+' : ''}${(e?.ev_over ?? 0).toFixed(4)}`,
      positive: (e?.ev_over ?? 0) > 0,
    },
    {
      label: 'Model P(Under)',
      value: `${((model?.p_under ?? 0) * 100).toFixed(1)}%`,
      positive: (model?.p_under ?? 0) > 0.5,
    },
    {
      label: 'Market P(Under)',
      value: `${((market?.p_under_vigfree ?? 0) * 100).toFixed(1)}%`,
      positive: false,
    },
    {
      label: 'Prob Edge Under',
      value: `${(e?.prob_edge_under ?? 0) > 0 ? '+' : ''}${((e?.prob_edge_under ?? 0) * 100).toFixed(1)}pp`,
      positive: (e?.prob_edge_under ?? 0) > 0,
    },
    {
      label: 'EV Under',
      value: `${(e?.ev_under ?? 0) > 0 ? '+' : ''}${(e?.ev_under ?? 0).toFixed(4)}`,
      positive: (e?.ev_under ?? 0) > 0,
    },
  ]

  const tableRows = [
    {
      side: 'OVER',
      modelP: model?.p_over ?? 0,
      mktP: market?.p_over_vigfree ?? 0,
      edgePP: e?.prob_edge_over ?? 0,
      ev: e?.ev_over ?? 0,
      roi: e?.roi_over_pct ?? 0,
    },
    {
      side: 'UNDER',
      modelP: model?.p_under ?? 0,
      mktP: market?.p_under_vigfree ?? 0,
      edgePP: e?.prob_edge_under ?? 0,
      ev: e?.ev_under ?? 0,
      roi: e?.roi_under_pct ?? 0,
    },
  ]

  return (
    <div className="mt-1.5">
      {/* Recommendation banner */}
      <div
        className={
          'border p-6 text-center mb-5 ' +
          (isOver
            ? 'bg-[rgba(34,197,94,0.05)] border-[rgba(34,197,94,0.3)]'
            : isUnder
              ? 'bg-[rgba(239,68,68,0.05)] border-[rgba(239,68,68,0.3)]'
              : 'bg-[rgba(255,255,255,0.03)] border-[rgba(255,255,255,0.15)]')
        }
      >
        <div className="font-display font-black text-2xl mb-2" style={{ color: accentColor }}>
          {recommended === 'NO BET' ? 'NO EDGE' : `BET ${recommended}`}
        </div>
        <div className="font-display font-black text-5xl text-[#F0E040] leading-none my-3 tabular-nums">
          {recommended !== 'NO BET'
            ? `+${Math.max(e?.roi_over_pct ?? 0, e?.roi_under_pct ?? 0).toFixed(1)}% ROI`
            : `${Math.max(e?.ev_over ?? 0, e?.ev_under ?? 0).toFixed(3)} EV`}
        </div>
        <span className={`text-[0.65rem] font-bold uppercase tracking-[0.08em] px-2.5 py-1 border ${confClass}`}>
          {confLevel} CONFIDENCE — {edge?.player?.sample_size ?? 0} maps
        </span>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3 mb-5">
        {metrics.map((m) => (
          <div
            key={m.label}
            className="bg-[#0a0a0a] border border-[rgba(240,224,64,0.1)] px-4 py-4"
            style={{ borderLeft: '3px solid #F0E040' }}
          >
            <div className="text-[0.65rem] uppercase tracking-[0.12em] text-white/40 mb-2">
              {m.label}
            </div>
            <div
              className="font-display font-bold text-2xl tabular-nums"
              style={{
                color: m.positive
                  ? '#22c55e'
                  : m.value.startsWith('-')
                    ? '#ef4444'
                    : '#e4e4e7',
              }}
            >
              {m.value}
            </div>
          </div>
        ))}
      </div>

      {/* Distribution chart */}
      {dist.length > 0 && (
        <div className="bg-[#0a0a0a] border border-[rgba(255,255,255,0.06)] px-5 py-5 mb-5">
          <div className="font-display font-bold text-center mb-4 text-[#e4e4e7] text-sm uppercase tracking-[0.06em]">
            Kill Distribution: Model vs Market
          </div>
          <DistributionChart
            data={dist}
            killLine={line}
            modelOverPct={(model?.p_over ?? 0) * 100}
            marketOverPct={(market?.p_over_vigfree ?? 0) * 100}
          />
        </div>
      )}

      {/* Comparison table */}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse min-w-[280px]">
          <thead>
            <tr>
              {['Side', 'Model Prob', 'Market Prob', 'Edge (pp)', 'EV', 'ROI %'].map((h) => (
                <th
                  key={h}
                  className="px-4 py-3 text-left text-[0.65rem] uppercase tracking-[0.1em] text-white/40 border-b border-[rgba(255,255,255,0.08)]"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tableRows.map((row) => (
              <tr key={row.side} className="border-b border-[rgba(255,255,255,0.06)]">
                <td
                  className="px-4 py-3 font-display font-bold text-sm"
                  style={{ color: row.side === 'OVER' ? '#22c55e' : '#ef4444' }}
                >
                  {row.side}
                </td>
                <td className="px-4 py-3 text-sm text-[#e4e4e7] tabular-nums">
                  {(row.modelP * 100).toFixed(1)}%
                </td>
                <td className="px-4 py-3 text-sm text-[#e4e4e7] tabular-nums">
                  {(row.mktP * 100).toFixed(1)}%
                </td>
                <td
                  className="px-4 py-3 text-sm font-bold tabular-nums"
                  style={{ color: row.edgePP > 0 ? '#22c55e' : '#ef4444' }}
                >
                  {row.edgePP > 0 ? '+' : ''}
                  {(row.edgePP * 100).toFixed(1)}pp
                </td>
                <td
                  className="px-4 py-3 text-sm font-bold tabular-nums"
                  style={{ color: row.ev > 0 ? '#22c55e' : '#ef4444' }}
                >
                  {row.ev > 0 ? '+' : ''}
                  {row.ev.toFixed(4)}
                </td>
                <td
                  className="px-4 py-3 text-sm font-bold tabular-nums"
                  style={{ color: row.roi > 0 ? '#22c55e' : '#ef4444' }}
                >
                  {row.roi > 0 ? '+' : ''}
                  {row.roi.toFixed(2)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
