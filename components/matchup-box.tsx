export interface MatchupAdjustedProbabilities {
  p_over: number
  p_under: number
  team_win_prob: number
  mu_base: number
  mu_adjusted: number
  multiplier: number
  input_method: string
}

interface MatchupBoxProps {
  adj: MatchupAdjustedProbabilities
}

export function MatchupBox({ adj }: MatchupBoxProps) {
  return (
    <div
      className="bg-[rgba(240,224,64,0.05)] border border-[rgba(240,224,64,0.2)] px-6 py-4"
      style={{ borderLeft: '3px solid #F0E040' }}
    >
      <div className="text-[0.7rem] uppercase tracking-[0.1em] text-white/40 mb-3">
        Matchup Adjustment Applied
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
        <span className="text-white/50">
          Win Prob:{' '}
          <span className="font-display font-bold text-[#F0E040]">
            {(adj.team_win_prob * 100).toFixed(1)}%
          </span>
        </span>
        <span className="text-white/50">
          μ Base:{' '}
          <span className="font-semibold text-[#e4e4e7]">{adj.mu_base?.toFixed(2)}</span>
        </span>
        <span className="text-white/50">
          μ Adj:{' '}
          <span className="font-semibold text-[#e4e4e7]">{adj.mu_adjusted?.toFixed(2)}</span>
        </span>
        <span className="text-white/50">
          ×<span className="font-semibold text-[#e4e4e7]">{adj.multiplier?.toFixed(3)}</span>
        </span>
        <span className="text-white/50">
          Adj P(Over):{' '}
          <span className="font-display font-bold text-[#22c55e]">
            {(adj.p_over * 100).toFixed(1)}%
          </span>
        </span>
      </div>
    </div>
  )
}
