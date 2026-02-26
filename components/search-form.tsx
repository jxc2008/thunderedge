'use client'

import { useState } from 'react'
import { Loader2 } from 'lucide-react'

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

  const inputStyle: React.CSSProperties = {
    background: '#0a0a0a',
    border: '1px solid rgba(255,255,255,0.1)',
    color: '#ffffff',
    padding: '0.75rem 1rem',
    fontSize: '0.875rem',
    fontFamily: 'inherit',
    transition: 'border-color 0.15s',
    outline: 'none',
    borderRadius: 0,
    width: '100%',
  }

  const labelStyle: React.CSSProperties = {
    fontFamily: 'inherit',
    fontSize: '0.7rem',
    fontWeight: 500,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.12em',
    color: 'rgba(255,255,255,0.4)',
    display: 'block',
    marginBottom: '0.5rem',
  }

  return (
    <div
      className="w-full"
      style={{
        background: '#0D0D0D',
        border: '1px solid rgba(240,224,64,0.15)',
        borderLeft: '3px solid #F0E040',
        padding: '2rem',
      }}
    >
      <form onSubmit={handleSubmit} onKeyDown={handleKey} noValidate>
        <div className="flex flex-col gap-4">
          {/* Player IGN */}
          <div>
            <label htmlFor="player-ign" style={labelStyle}>
              Player IGN
            </label>
            <input
              id="player-ign"
              type="text"
              value={form.player}
              onChange={(e) => setForm((f) => ({ ...f, player: e.target.value }))}
              placeholder={placeholder}
              required
              style={inputStyle}
            />
          </div>

          {/* Kill Line + Over Odds row */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="kill-line" style={labelStyle}>
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
                style={{ ...inputStyle, fontVariantNumeric: 'tabular-nums' }}
              />
            </div>

            <div>
              <label htmlFor="over-odds" style={labelStyle}>
                Over Odds
              </label>
              <input
                id="over-odds"
                type="number"
                value={form.overOdds}
                onChange={(e) => setForm((f) => ({ ...f, overOdds: e.target.value }))}
                placeholder="-110"
                style={{ ...inputStyle, fontVariantNumeric: 'tabular-nums' }}
              />
            </div>
          </div>

          {/* Under Odds */}
          {showUnderOdds && (
            <div>
              <label htmlFor="under-odds" style={labelStyle}>
                Under Odds{' '}
                <span
                  style={{
                    background: 'rgba(255,255,255,0.08)',
                    color: 'rgba(255,255,255,0.4)',
                    fontSize: '0.65rem',
                    padding: '0.1rem 0.4rem',
                    marginLeft: 6,
                    textTransform: 'none',
                    letterSpacing: 'normal',
                  }}
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
                style={{ ...inputStyle, fontVariantNumeric: 'tabular-nums' }}
              />
            </div>
          )}

          {/* CTA Button — yellow, sharp corners, Barlow Condensed */}
          <div className="flex flex-col gap-1.5">
            <button
              type="submit"
              disabled={isLoading}
              className="w-full flex items-center justify-center gap-2"
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 700,
                fontSize: '0.9rem',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                padding: '0.75rem 2rem',
                background: isLoading ? 'rgba(240,224,64,0.5)' : '#F0E040',
                color: '#000000',
                border: 'none',
                borderRadius: 0,
                cursor: isLoading ? 'not-allowed' : 'pointer',
                transition: 'background 0.15s, transform 0.15s',
              }}
              onMouseEnter={(e) => {
                if (!isLoading) (e.currentTarget as HTMLButtonElement).style.background = '#ffffff'
              }}
              onMouseLeave={(e) => {
                if (!isLoading) (e.currentTarget as HTMLButtonElement).style.background = '#F0E040'
              }}
            >
              {isLoading ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  <span>Analyzing...</span>
                </>
              ) : (
                <span>{submitLabel}</span>
              )}
            </button>
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
          style={{ borderColor: 'rgba(255,255,255,0.08)', color: '#71717a' }}
        >
          <span>Last query:</span>
          <span style={{ color: '#a1a1aa' }}>{lastQuery.player}</span>
          <span>—</span>
          <span style={{ fontVariantNumeric: 'tabular-nums' }}>{lastQuery.ms}ms</span>
        </div>
      )}
    </div>
  )
}
