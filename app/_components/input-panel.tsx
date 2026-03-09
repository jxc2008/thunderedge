'use client'

import { Loader2 } from 'lucide-react'

export interface InputPanelProps {
  playerInput: string
  setPlayerInput: (v: string) => void
  killLine: string
  setKillLine: (v: string) => void
  overOdds: string
  setOverOdds: (v: string) => void
  underOdds: string
  setUnderOdds: (v: string) => void
  teamOdds: string
  setTeamOdds: (v: string) => void
  oppOdds: string
  setOppOdds: (v: string) => void
  isLoading: boolean
  onAnalyze: () => void
  onKeyDown: (e: React.KeyboardEvent) => void
  // Post-analysis quick summary
  playerIGN?: string
  playerTeam?: string
  recType?: 'BET_OVER' | 'BET_UNDER' | 'NO_BET'
}

const INPUT_BASE =
  'w-full px-3 py-2 bg-black border border-[rgba(255,255,255,0.1)] text-white text-sm font-mono outline-none ' +
  'focus:border-[#F0E040] focus:ring-0 transition-colors duration-150 placeholder:text-white/20'

const LABEL_BASE =
  'block text-[0.6rem] uppercase tracking-[0.12em] text-white/40 mb-1.5 font-bold'

export function InputPanel({
  playerInput,
  setPlayerInput,
  killLine,
  setKillLine,
  overOdds,
  setOverOdds,
  underOdds,
  setUnderOdds,
  teamOdds,
  setTeamOdds,
  oppOdds,
  setOppOdds,
  isLoading,
  onAnalyze,
  onKeyDown,
  playerIGN,
  playerTeam,
  recType,
}: InputPanelProps) {
  const canAnalyze = !isLoading && !!playerInput.trim()

  return (
    <aside
      className={
        'w-full bg-[#060608] ' +
        'border-b border-[rgba(255,255,255,0.06)] md:border-b-0 md:border-r ' +
        'flex flex-col h-full'
      }
    >
      {/* Panel header */}
      <div className="px-5 pt-6 pb-5 border-b border-[rgba(255,255,255,0.05)]">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[#F0E040] shrink-0" />
          <span className="text-[0.58rem] uppercase tracking-[0.18em] text-[#F0E040]/60 font-bold">
            ThunderEdge
          </span>
        </div>
        <h2 className="font-display font-black text-[1.35rem] text-white uppercase leading-[1.05] tracking-[0.01em]">
          Kill Line
          <br />
          Analyzer
        </h2>
        <p className="text-[0.65rem] text-white/25 mt-2 font-mono">
          neg-binom · VLR.gg live
        </p>
      </div>

      {/* Form fields */}
      <div className="px-5 py-5 flex flex-col gap-4 flex-1">
        {/* Player IGN */}
        <div>
          <label className={LABEL_BASE} htmlFor="ign-input">
            Player IGN
          </label>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#F0E040]/50 font-display font-bold text-sm pointer-events-none select-none">
              {'>'}
            </span>
            <input
              id="ign-input"
              type="text"
              value={playerInput}
              onChange={(e) => setPlayerInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="enter IGN..."
              aria-label="Player IGN"
              autoComplete="off"
              spellCheck={false}
              className={INPUT_BASE + ' pl-8'}
            />
          </div>
        </div>

        {/* Kill Line */}
        <div>
          <label className={LABEL_BASE} htmlFor="kill-line-input">
            Kill Line
          </label>
          <input
            id="kill-line-input"
            type="number"
            step="0.5"
            value={killLine}
            onChange={(e) => setKillLine(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="15.5"
            aria-label="Kill Line"
            className={INPUT_BASE}
          />
        </div>

        {/* Over / Under Odds side by side */}
        <div>
          <label className={LABEL_BASE}>Over / Under Odds</label>
          <div className="grid grid-cols-2 gap-2">
            <input
              type="text"
              value={overOdds}
              onChange={(e) => setOverOdds(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Over (-110)"
              aria-label="Over Odds"
              className={INPUT_BASE}
            />
            <input
              type="text"
              value={underOdds}
              onChange={(e) => setUnderOdds(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Under (-110)"
              aria-label="Under Odds"
              className={INPUT_BASE}
            />
          </div>
        </div>

        {/* Team / Opp Odds side by side */}
        <div>
          <label className={LABEL_BASE}>Team / Opp Odds</label>
          <div className="grid grid-cols-2 gap-2">
            <input
              type="number"
              value={teamOdds}
              onChange={(e) => setTeamOdds(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Team (1.62)"
              aria-label="Team Odds"
              className={INPUT_BASE}
            />
            <input
              type="number"
              value={oppOdds}
              onChange={(e) => setOppOdds(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Opp (2.30)"
              aria-label="Opp Odds"
              className={INPUT_BASE}
            />
          </div>
        </div>

        {/* Analyze CTA */}
        <button
          type="button"
          onClick={onAnalyze}
          disabled={!canAnalyze}
          aria-label="Analyze player"
          className={
            'w-full py-3 font-display font-black text-[0.85rem] uppercase tracking-[0.12em] ' +
            'flex items-center justify-center gap-2 transition-opacity duration-150 border-0 ' +
            (canAnalyze
              ? 'bg-[#F0E040] text-black cursor-pointer hover:opacity-90'
              : 'bg-[#F0E040]/25 text-black/40 cursor-not-allowed')
          }
        >
          {isLoading ? (
            <>
              <Loader2 size={13} className="animate-spin" />
              Analyzing…
            </>
          ) : (
            'Analyze Player'
          )}
        </button>
      </div>

      {/* Quick summary after analysis */}
      {playerIGN && (
        <div className="border-t border-[rgba(255,255,255,0.05)] px-5 py-4">
          <div className="text-[0.58rem] uppercase tracking-[0.14em] text-white/25 mb-1.5 font-bold">
            Current Player
          </div>
          <div className="font-display font-black text-base text-white leading-none mb-0.5">
            {playerIGN}
          </div>
          {playerTeam && (
            <div className="text-[0.7rem] text-white/35 mb-2.5">{playerTeam}</div>
          )}
          {recType && (
            <span
              className={
                'inline-flex px-2 py-0.5 text-[0.58rem] uppercase tracking-[0.12em] font-bold border ' +
                (recType === 'BET_OVER'
                  ? 'bg-[rgba(34,197,94,0.12)] text-[#22c55e] border-[rgba(34,197,94,0.3)]'
                  : recType === 'BET_UNDER'
                    ? 'bg-[rgba(239,68,68,0.12)] text-[#ef4444] border-[rgba(239,68,68,0.3)]'
                    : 'bg-[rgba(240,224,64,0.06)] text-[#F0E040]/60 border-[rgba(240,224,64,0.15)]')
              }
            >
              {recType === 'BET_OVER'
                ? 'Bet Over'
                : recType === 'BET_UNDER'
                  ? 'Bet Under'
                  : 'No Edge'}
            </span>
          )}
        </div>
      )}
    </aside>
  )
}
