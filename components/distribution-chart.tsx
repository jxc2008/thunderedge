'use client'

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Cell,
} from 'recharts'

interface KillDistPoint {
  kills: number
  modelPct: number
  marketPct: number
}

interface DistributionChartProps {
  data: KillDistPoint[]
  killLine: number
  modelOverPct: number
  marketOverPct: number
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: { name: string; value: number; fill: string }[]
  label?: string | number
}) {
  if (!active || !payload?.length) return null

  return (
    <div
      className="rounded-[8px] border px-3 py-2.5 text-sm"
      style={{ background: '#18181b', borderColor: '#3f3f46', minWidth: 160 }}
    >
      <p className="font-semibold mb-1.5" style={{ color: '#ffffff' }}>
        {label} kills
      </p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-1.5">
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ background: p.fill }}
            />
            <span style={{ color: '#a1a1aa' }}>{p.name}</span>
          </div>
          <span className="font-medium tabular-nums" style={{ color: '#ffffff' }}>
            {p.value.toFixed(1)}%
          </span>
        </div>
      ))}
    </div>
  )
}

export function DistributionChart({
  data,
  killLine,
  modelOverPct,
  marketOverPct,
}: DistributionChartProps) {
  const edge = modelOverPct - marketOverPct

  return (
    <div
      className="rounded-[12px] border p-5"
      style={{ background: '#0a0a0a', borderColor: '#27272a' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-sm" style={{ color: '#ffffff' }}>
          Kill Distribution
        </h3>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ background: '#3b82f6' }}
            />
            <span className="text-[0.75rem]" style={{ color: '#a1a1aa' }}>
              Model
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ background: '#71717a' }}
            />
            <span className="text-[0.75rem]" style={{ color: '#a1a1aa' }}>
              Market
            </span>
          </div>
        </div>
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={220}>
        <BarChart
          data={data}
          margin={{ top: 4, right: 4, bottom: 0, left: -16 }}
          barGap={2}
          barCategoryGap="20%"
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="rgba(255,255,255,0.04)"
            vertical={false}
          />
          <XAxis
            dataKey="kills"
            tick={{ fill: '#71717a', fontSize: 11 }}
            axisLine={{ stroke: '#27272a' }}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(v) => `${v}%`}
            tick={{ fill: '#71717a', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />

          {/* Kill line reference */}
          <ReferenceLine
            x={killLine}
            stroke="#f59e0b"
            strokeDasharray="4 4"
            strokeWidth={1.5}
            label={{
              value: `Line: ${killLine}`,
              fill: '#f59e0b',
              fontSize: 11,
              position: 'top',
            }}
          />

          <Bar dataKey="modelPct" name="Model" fill="rgba(59,130,246,0.7)" radius={[2, 2, 0, 0]}>
            {data.map((entry, idx) => (
              <Cell
                key={idx}
                fill={entry.kills > killLine ? 'rgba(59,130,246,0.75)' : 'rgba(59,130,246,0.4)'}
              />
            ))}
          </Bar>
          <Bar
            dataKey="marketPct"
            name="Market"
            fill="rgba(113,113,122,0.4)"
            radius={[2, 2, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>

      {/* Summary row */}
      <div
        className="mt-4 pt-3 border-t flex items-center justify-between flex-wrap gap-2 text-[0.75rem] tabular-nums"
        style={{ borderColor: '#27272a' }}
      >
        <span style={{ color: '#a1a1aa' }}>
          Model suggests{' '}
          <span className="font-semibold" style={{ color: '#3b82f6' }}>
            {modelOverPct.toFixed(1)}%
          </span>{' '}
          Over
        </span>
        <span style={{ color: '#a1a1aa' }}>
          Market suggests{' '}
          <span className="font-semibold" style={{ color: '#71717a' }}>
            {marketOverPct.toFixed(1)}%
          </span>{' '}
          Over
        </span>
        <span style={{ color: '#a1a1aa' }}>
          Edge:{' '}
          <span
            className="font-semibold"
            style={{ color: edge > 0 ? '#22c55e' : edge < 0 ? '#ef4444' : '#a1a1aa' }}
          >
            {edge > 0 ? '+' : ''}
            {edge.toFixed(1)}pp
          </span>
        </span>
      </div>
    </div>
  )
}
