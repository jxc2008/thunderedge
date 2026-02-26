import { ReactNode } from 'react'

export interface StatCardData {
  label: string
  value: string | number
  delta?: string
  icon?: ReactNode
  /** 'positive' | 'negative' | 'warning' | 'neutral' */
  semantic?: 'positive' | 'negative' | 'warning' | 'neutral'
  monospace?: boolean
}

const SEMANTIC_COLORS: Record<string, string> = {
  positive: '#22c55e',
  negative: '#ef4444',
  warning: '#f59e0b',
  neutral: '#ffffff',
}

function StatCard({ label, value, delta, icon, semantic = 'neutral', monospace }: StatCardData) {
  const valueColor = SEMANTIC_COLORS[semantic]

  return (
    <div
      className="rounded-[10px] border p-4 flex flex-col gap-1 transition-colors duration-150 group"
      style={{
        background: '#0a0a0a',
        borderColor: '#27272a',
      }}
      onMouseEnter={(e) => {
        ;(e.currentTarget as HTMLDivElement).style.borderColor = '#3f3f46'
      }}
      onMouseLeave={(e) => {
        ;(e.currentTarget as HTMLDivElement).style.borderColor = '#27272a'
      }}
    >
      {/* Label row */}
      <div className="flex items-center gap-1.5">
        {icon && (
          <span className="shrink-0" style={{ color: '#71717a' }}>
            {icon}
          </span>
        )}
        <span
          className="text-[0.65rem] uppercase tracking-[0.1em] font-medium"
          style={{ color: '#71717a' }}
        >
          {label}
        </span>
      </div>

      {/* Value */}
      <p
        className={`font-bold tabular-nums leading-none${monospace ? ' font-mono' : ''}`}
        style={{ fontSize: '1.75rem', color: valueColor }}
      >
        {value}
      </p>

      {/* Delta / secondary */}
      {delta && (
        <p className="text-[0.7rem] tabular-nums" style={{ color: '#71717a' }}>
          {delta}
        </p>
      )}
    </div>
  )
}

interface StatsGridProps {
  stats: StatCardData[]
  columns?: 2 | 3
}

export function StatsGrid({ stats, columns = 3 }: StatsGridProps) {
  return (
    <div
      className="grid gap-3"
      style={{
        gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
      }}
    >
      {stats.map((stat, i) => (
        <StatCard key={i} {...stat} />
      ))}
    </div>
  )
}
