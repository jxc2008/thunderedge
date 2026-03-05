import { ArrowUp, ArrowDown, Minus } from 'lucide-react'

type RecommendationType = 'BET_OVER' | 'BET_UNDER' | 'NO_BET'
type ConfidenceLevel = 'HIGH' | 'MED' | 'LOW'

interface RecommendationCardProps {
  type: RecommendationType
  ev: number
  confidence: ConfidenceLevel
  reason?: string
}

const CONFIG: Record<
  RecommendationType,
  {
    label: string
    accentColor: string
    dimColor: string
    Icon: typeof ArrowUp
    iconBg: string
  }
> = {
  BET_OVER: {
    label: 'BET OVER',
    accentColor: '#22c55e',
    dimColor: 'rgba(34,197,94,0.05)',
    Icon: ArrowUp,
    iconBg: 'rgba(34,197,94,0.15)',
  },
  BET_UNDER: {
    label: 'BET UNDER',
    accentColor: '#ef4444',
    dimColor: 'rgba(239,68,68,0.05)',
    Icon: ArrowDown,
    iconBg: 'rgba(239,68,68,0.15)',
  },
  NO_BET: {
    label: 'NO BET',
    accentColor: '#3f3f46',
    dimColor: 'rgba(63,63,70,0.05)',
    Icon: Minus,
    iconBg: 'rgba(63,63,70,0.2)',
  },
}

const CONFIDENCE_STYLE: Record<
  ConfidenceLevel,
  { bg: string; color: string; border: string }
> = {
  HIGH: {
    bg: 'rgba(34,197,94,0.12)',
    color: '#22c55e',
    border: '1px solid rgba(34,197,94,0.25)',
  },
  MED: {
    bg: 'rgba(245,158,11,0.12)',
    color: '#f59e0b',
    border: '1px solid rgba(245,158,11,0.25)',
  },
  LOW: {
    bg: 'rgba(239,68,68,0.12)',
    color: '#ef4444',
    border: '1px solid rgba(239,68,68,0.25)',
  },
}

export function RecommendationCard({
  type,
  ev,
  confidence,
  reason,
}: RecommendationCardProps) {
  const cfg = CONFIG[type]
  const confStyle = CONFIDENCE_STYLE[confidence]
  const evPositive = ev > 0
  const evColor = evPositive ? '#22c55e' : ev < 0 ? '#ef4444' : '#a1a1aa'

  return (
    <div
      className="w-full rounded-[12px] border relative flex items-stretch flex-col md:flex-row"
      style={{
        borderColor: '#27272a',
        background: `linear-gradient(to right, ${cfg.dimColor}, transparent 40%)`,
        borderLeft: `6px solid ${cfg.accentColor}`,
      }}
    >
      {/* Left: icon */}
      <div className="flex items-center justify-center px-5 py-5 shrink-0">
        <div
          className="w-12 h-12 rounded-full flex items-center justify-center"
          style={{ background: cfg.iconBg }}
        >
          <cfg.Icon size={22} style={{ color: cfg.accentColor }} strokeWidth={2.5} />
        </div>
      </div>

      {/* Center: recommendation text + reason */}
      <div className="flex-1 flex flex-col justify-center py-5 px-5 md:pl-0 md:pr-4">
        <p
          className="uppercase"
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 900,
            fontSize: '1.75rem',
            letterSpacing: '-0.01em',
            color: '#ffffff',
          }}
        >
          {cfg.label}
        </p>
        {reason && (
          <p className="mt-1 text-sm" style={{ color: '#71717a' }}>
            {reason}
          </p>
        )}
      </div>

      {/* Right: EV + confidence */}
      <div className="flex flex-col items-start md:items-end justify-center py-5 px-5 shrink-0">
        <p
          className="tabular-nums leading-none"
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 900,
            fontSize: '2.5rem',
            letterSpacing: '-0.02em',
            color: evColor,
          }}
        >
          {evPositive ? '+' : ''}{ev.toFixed(2)}
        </p>
        <p className="text-[0.65rem] uppercase tracking-[0.08em] mt-0.5" style={{ color: '#52525b' }}>
          Expected Value
        </p>
        <span
          className="mt-2 text-[0.7rem] font-semibold uppercase tracking-widest px-2 py-0.5 rounded-[4px]"
          style={confStyle}
        >
          {confidence}
        </span>
      </div>
    </div>
  )
}
