interface KpiCardProps {
  label: string
  value: string | number
  sub?: string
  color?: string
  accentLeft?: boolean
}

function KpiCard({ label, value, sub, color, accentLeft }: KpiCardProps) {
  return (
    <div
      className="bg-[#0a0a0a] border border-[rgba(255,255,255,0.06)] px-4 py-4 flex-1 min-w-[110px]"
      style={accentLeft ? { borderLeft: '2px solid #F0E040' } : undefined}
    >
      <div className="text-[0.56rem] uppercase tracking-[0.14em] text-white/30 mb-2 font-bold">
        {label}
      </div>
      <div
        className="font-display font-black text-2xl tabular-nums leading-none"
        style={{ color: color || '#e4e4e7' }}
      >
        {value}
      </div>
      {sub && (
        <div className="text-[0.6rem] text-white/25 mt-1.5 font-mono">{sub}</div>
      )}
    </div>
  )
}

export interface KpiStripProps {
  killLine: number
  overPct: number
  underPct: number
  overCount: number
  underCount: number
  totalMaps: number
  weightedKpr: number
  elapsed: string
  cachedCount: number
  liveCount: number
  confidence: string
}

function confColor(c: string) {
  const u = c.toUpperCase()
  if (u.startsWith('HIGH') || u.includes('STRONG')) return '#22c55e'
  if (u.startsWith('MED') || u.includes('LEAN')) return '#f59e0b'
  return '#ef4444'
}

export function KpiStrip({
  killLine,
  overPct,
  underPct,
  overCount,
  underCount,
  totalMaps,
  weightedKpr,
  elapsed,
  cachedCount,
  liveCount,
  confidence,
}: KpiStripProps) {
  const overColor =
    overPct >= 55 ? '#22c55e' : overPct <= 45 ? '#ef4444' : '#e4e4e7'
  const underColor =
    underPct >= 55 ? '#22c55e' : underPct <= 45 ? '#ef4444' : '#e4e4e7'

  return (
    <div className="flex gap-2 overflow-x-auto pb-0.5">
      <KpiCard
        label="Kill Line"
        value={killLine ?? '—'}
        sub="Thunderpick"
        color="#F0E040"
        accentLeft
      />
      <KpiCard
        label="Over %"
        value={`${(overPct ?? 0).toFixed(1)}%`}
        sub={`${overCount ?? 0} / ${totalMaps} maps`}
        color={overColor}
      />
      <KpiCard
        label="Under %"
        value={`${(underPct ?? 0).toFixed(1)}%`}
        sub={`${underCount ?? 0} / ${totalMaps} maps`}
        color={underColor}
      />
      <KpiCard
        label="Wtd KPR"
        value={(weightedKpr ?? 0).toFixed(3)}
        sub="1.5× recent event"
      />
      <KpiCard
        label="Maps"
        value={totalMaps ?? 0}
        sub={`${elapsed}s · ${cachedCount}c/${liveCount}l`}
      />
      <KpiCard
        label="Confidence"
        value={confidence ?? '—'}
        sub="sample quality"
        color={confColor(confidence ?? '')}
      />
    </div>
  )
}
