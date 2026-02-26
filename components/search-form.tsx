'use client'

import { useState } from 'react'
import { Search, Loader2 } from 'lucide-react'

interface SearchFormProps {
  onSubmit?: (data: SearchFormData) => void
  isLoading?: boolean
  lastQuery?: { player: string; ms: number } | null
  showUnderOdds?: boolean
  placeholder?: string
  submitLabel?: string
}

export interface SearchFormData {
  player: string
  killLine: string
  overOdds: string
  underOdds: string
}

export function SearchForm({
  onSubmit,
  isLoading = false,
  lastQuery = null,
  showUnderOdds = true,
  placeholder = 'e.g. TenZ#NA1',
  submitLabel = 'Analyze Player',
}: SearchFormProps) {
  const [form, setForm] = useState<SearchFormData>({
    player: '',
    killLine: '',
    overOdds: '',
    underOdds: '',
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit?.(form)
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      onSubmit?.(form)
    }
  }

  // Shared input style — focus ring is handled by globals.css :focus-visible
  const inputStyle: React.CSSProperties = {
    background: '#18181b',
    borderColor: '#3f3f46',
    color: '#ffffff',
  }

  return (
    <div
      className="w-full max-w-[640px] mx-auto rounded-[12px] border p-6"
      style={{ background: '#0a0a0a', borderColor: '#27272a' }}
    >
      <form onSubmit={handleSubmit} onKeyDown={handleKey} noValidate>
        <div className="flex flex-col gap-4">
          {/* Player IGN */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="player-ign"
              className="text-[0.7rem] uppercase tracking-[0.12em] font-medium"
              style={{ color: '#71717a' }}
            >
              Player IGN
            </label>
            <input
              id="player-ign"
              type="text"
              value={form.player}
              onChange={(e) => setForm((f) => ({ ...f, player: e.target.value }))}
              placeholder={placeholder}
              required
              className="h-11 px-3 rounded-[8px] border text-sm outline-none transition-all duration-150"
              style={inputStyle}
            />
          </div>

          {/* Kill Line + Over Odds row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="kill-line"
                className="text-[0.7rem] uppercase tracking-[0.12em] font-medium"
                style={{ color: '#71717a' }}
              >
                Kill Line
              </label>
              <input
                id="kill-line"
                type="number"
                step="0.5"
                min="0"
                value={form.killLine}
                onChange={(e) => setForm((f) => ({ ...f, killLine: e.target.value }))}
                placeholder="19.5"
                required
                className="h-11 px-3 rounded-[8px] border text-sm outline-none transition-all duration-150 tabular-nums"
                style={inputStyle}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="over-odds"
                className="text-[0.7rem] uppercase tracking-[0.12em] font-medium"
                style={{ color: '#71717a' }}
              >
                Over Odds
              </label>
              <input
                id="over-odds"
                type="number"
                value={form.overOdds}
                onChange={(e) => setForm((f) => ({ ...f, overOdds: e.target.value }))}
                placeholder="-110"
                className="h-11 px-3 rounded-[8px] border text-sm outline-none transition-all duration-150 tabular-nums"
                style={inputStyle}
              />
            </div>
          </div>

          {/* Under Odds (optional) */}
          {showUnderOdds && (
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="under-odds"
                className="text-[0.7rem] uppercase tracking-[0.12em] font-medium flex items-center gap-2"
                style={{ color: '#71717a' }}
              >
                Under Odds{' '}
                <span
                  className="text-[0.65rem] px-1.5 py-0.5 rounded-[4px] normal-case tracking-normal"
                  style={{ background: '#27272a', color: '#71717a', marginLeft: 6 }}
                >
                  Optional
                </span>
              </label>
              <input
                id="under-odds"
                type="number"
                value={form.underOdds}
                onChange={(e) => setForm((f) => ({ ...f, underOdds: e.target.value }))}
                placeholder="-110"
                className="h-11 px-3 rounded-[8px] border text-sm outline-none transition-all duration-150 tabular-nums"
                style={inputStyle}
              />
            </div>
          )}

          {/* CTA Button */}
          <div className="flex flex-col gap-1.5">
            <button
              type="submit"
              disabled={isLoading}
              className="w-full h-11 rounded-[8px] text-sm font-semibold text-white transition-opacity duration-150 flex items-center justify-center gap-2 disabled:opacity-70 disabled:cursor-not-allowed"
              style={{
                background: 'linear-gradient(135deg, #3b82f6, #0ea5e9)',
              }}
            >
              {isLoading ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  <span>Analyzing...</span>
                </>
              ) : (
                <>
                  <Search size={15} />
                  <span>{submitLabel}</span>
                </>
              )}
            </button>
            {/* Keyboard shortcut hint — separate line so it never overlaps button text */}
            <p
              className="text-right text-[0.65rem] select-none"
              style={{ color: 'rgba(255,255,255,0.2)' }}
            >
              ⌘ + Enter
            </p>
          </div>
        </div>
      </form>

      {/* Last query bar */}
      {lastQuery && (
        <div
          className="mt-4 pt-3 border-t text-[0.75rem] flex items-center gap-1.5"
          style={{ borderColor: '#27272a', color: '#71717a' }}
        >
          <span>Last query:</span>
          <span style={{ color: '#a1a1aa' }}>{lastQuery.player}</span>
          <span>—</span>
          <span className="tabular-nums">{lastQuery.ms}ms</span>
        </div>
      )}
    </div>
  )
}
