import { ChevronUp, ChevronDown } from 'lucide-react'

interface OverUnderDisplayProps {
  overPct: number
  underPct: number
  sampleSize: number
  killLine?: number
}

export function OverUnderDisplay({
  overPct,
  underPct,
  sampleSize,
  killLine,
}: OverUnderDisplayProps) {
  const overWins = overPct >= underPct

  return (
    <div
      className="w-full rounded-[16px] border"
      style={{ background: '#0a0a0a', borderColor: '#27272a', overflow: 'visible' }}
    >
      {/* Two panels */}
      <div className="flex">
        {/* OVER panel */}
        <div
          className="flex-1 flex flex-col items-center justify-center py-8 px-6 relative transition-colors duration-200"
          style={{
            background: overWins ? 'rgba(34,197,94,0.06)' : 'transparent',
            borderTop: overWins ? '3px solid rgba(34,197,94,0.5)' : '3px solid transparent',
          }}
        >
          <div
            className="flex items-center gap-2 tabular-nums"
            style={{
              fontSize: '4rem',
              fontWeight: 900,
              lineHeight: 1,
              color: '#22c55e',
            }}
          >
            {overWins && (
              <ChevronUp
                size={36}
                strokeWidth={3}
                className="shrink-0"
                style={{ color: '#22c55e' }}
              />
            )}
            {overPct.toFixed(1)}%
          </div>
          <p
            className="mt-2 text-[0.75rem] uppercase tracking-[0.1em]"
            style={{ color: '#71717a' }}
          >
            Over
          </p>
          <p className="mt-1 text-[0.7rem]" style={{ color: '#52525b' }}>
            (N={sampleSize} maps)
          </p>
        </div>

        {/* Vertical divider */}
        <div className="w-px self-stretch" style={{ background: '#27272a' }} />

        {/* UNDER panel */}
        <div
          className="flex-1 flex flex-col items-center justify-center py-8 px-6 relative transition-colors duration-200"
          style={{
            background: !overWins ? 'rgba(239,68,68,0.06)' : 'transparent',
            borderTop: !overWins ? '3px solid rgba(239,68,68,0.5)' : '3px solid transparent',
          }}
        >
          <div
            className="flex items-center gap-2 tabular-nums"
            style={{
              fontSize: '4rem',
              fontWeight: 900,
              lineHeight: 1,
              color: '#ef4444',
            }}
          >
            {!overWins && (
              <ChevronDown
                size={36}
                strokeWidth={3}
                className="shrink-0"
                style={{ color: '#ef4444' }}
              />
            )}
            {underPct.toFixed(1)}%
          </div>
          <p
            className="mt-2 text-[0.75rem] uppercase tracking-[0.1em]"
            style={{ color: '#71717a' }}
          >
            Under
          </p>
          <p className="mt-1 text-[0.7rem]" style={{ color: '#52525b' }}>
            (N={sampleSize} maps)
          </p>
        </div>
      </div>

      {/* Hit-rate progress bar */}
      <div className="px-6 pb-5 pt-4 border-t" style={{ borderColor: '#27272a' }}>
        <div className="flex items-center justify-between mb-1.5 gap-3 min-w-0">
          <span className="text-[0.7rem] tabular-nums shrink-0" style={{ color: '#22c55e' }}>
            {overPct.toFixed(1)}% Over
          </span>
          {killLine !== undefined && (
            <span className="text-[0.7rem] tabular-nums" style={{ color: '#71717a' }}>
              Line:&nbsp;{killLine}
            </span>
          )}
          <span className="text-[0.7rem] tabular-nums shrink-0" style={{ color: '#ef4444' }}>
            {underPct.toFixed(1)}% Under
          </span>
        </div>
        <div
          className="relative w-full rounded-full overflow-hidden"
          style={{ height: '6px', background: 'rgba(239,68,68,0.3)' }}
        >
          {/* Green fill (over) */}
          <div
            className="absolute left-0 top-0 h-full rounded-full transition-all duration-500"
            style={{
              width: `${overPct}%`,
              background: 'rgba(34,197,94,0.7)',
            }}
          />
          {/* 50% tick */}
          <div
            className="absolute top-0 bottom-0 w-px"
            style={{ left: '50%', background: '#71717a', zIndex: 2 }}
          />
        </div>
      </div>
    </div>
  )
}
