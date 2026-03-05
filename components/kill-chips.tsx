interface KillChipsProps {
  kills: number[]
  line: number
}

export function KillChips({ kills, line }: KillChipsProps) {
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {kills.map((k, i) => {
        const over = k > line
        return (
          <span
            key={i}
            className={
              'font-display font-bold text-sm leading-none px-2.5 py-1.5 border tabular-nums ' +
              (over
                ? 'border-[rgba(34,197,94,0.4)] bg-[rgba(34,197,94,0.08)] text-[#22c55e]'
                : 'border-[rgba(239,68,68,0.4)] bg-[rgba(239,68,68,0.08)] text-[#ef4444]')
            }
          >
            {k} {over ? '✓' : '✗'}
          </span>
        )
      })}
    </div>
  )
}
