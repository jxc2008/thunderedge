'use client'

import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

export interface MapResult {
  map: string
  kills: number
  line: number
}

export interface EventCardData {
  id: string
  eventName: string
  date: string
  isLive?: boolean
  isCached?: boolean
  overCount: number
  underCount: number
  maps: MapResult[]
  /** Start expanded (e.g. most recent event) */
  defaultOpen?: boolean
}

function MapRow({ map, kills, line }: MapResult) {
  const diff = kills - line
  const isOver = kills > line
  const isUnder = kills < line
  const isEqual = kills === line

  const pillStyle = isOver
    ? { background: 'rgba(34,197,94,0.15)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.3)' }
    : isUnder
      ? { background: 'rgba(239,68,68,0.15)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.3)' }
      : { background: 'rgba(113,113,122,0.15)', color: '#71717a', border: '1px solid rgba(113,113,122,0.3)' }

  return (
    <div
      className="flex items-center justify-between px-4 py-2.5 border-b last:border-b-0"
      style={{ borderColor: 'rgba(39,39,42,0.5)' }}
    >
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium" style={{ color: '#ffffff', minWidth: 80 }}>
          {map}
        </span>
        <span
          className="text-[0.65rem] uppercase tracking-widest"
          style={{ color: '#52525b' }}
        >
          Line: {line}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span
          className="text-base font-bold tabular-nums"
          style={{ color: isOver ? '#22c55e' : isUnder ? '#ef4444' : '#71717a' }}
        >
          {kills}
        </span>
        <span
          className="text-[0.7rem] px-1.5 py-0.5 rounded-[4px] tabular-nums font-medium"
          style={pillStyle}
        >
          {isEqual ? '=' : isOver ? `+${diff.toFixed(1)}` : diff.toFixed(1)}
        </span>
      </div>
    </div>
  )
}

export function EventCard({
  eventName,
  date,
  isLive = false,
  isCached = false,
  overCount,
  underCount,
  maps,
  defaultOpen = false,
}: EventCardData) {
  const [open, setOpen] = useState(defaultOpen)
  const total = overCount + underCount

  return (
    <div
      className="rounded-[12px] border overflow-hidden"
      style={{ background: '#0a0a0a', borderColor: '#27272a' }}
    >
      {/* Header (clickable) */}
      <button
        className="w-full flex items-center justify-between gap-3 px-4 py-3.5 transition-colors duration-150 text-left"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={{ background: open ? '#0f0f0f' : 'transparent' }}
        onMouseEnter={(e) =>
          ((e.currentTarget as HTMLButtonElement).style.background = '#0f0f0f')
        }
        onMouseLeave={(e) =>
          ((e.currentTarget as HTMLButtonElement).style.background = open ? '#0f0f0f' : 'transparent')
        }
      >
        <div className="flex items-center gap-3 min-w-0">
          {/* Expand icon */}
          <span style={{ color: '#52525b', flexShrink: 0 }}>
            {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
          </span>

          {/* Event name */}
          <span className="font-semibold text-sm truncate" style={{ color: '#ffffff' }}>
            {eventName}
          </span>

          {/* Date */}
          <span className="text-[0.75rem] shrink-0" style={{ color: '#71717a' }}>
            {date}
          </span>
        </div>

        {/* Right: summary pills + badge */}
        <div className="flex items-center gap-2 shrink-0">
          {total > 0 && (
            <>
              <span
                className="text-[0.7rem] px-2 py-0.5 rounded-[4px] font-medium tabular-nums"
                style={{
                  background: 'rgba(34,197,94,0.12)',
                  color: '#22c55e',
                  border: '1px solid rgba(34,197,94,0.2)',
                }}
              >
                {overCount}O
              </span>
              <span
                className="text-[0.7rem] px-2 py-0.5 rounded-[4px] font-medium tabular-nums"
                style={{
                  background: 'rgba(239,68,68,0.12)',
                  color: '#ef4444',
                  border: '1px solid rgba(239,68,68,0.2)',
                }}
              >
                {underCount}U
              </span>
            </>
          )}

          {isLive && (
            <span
              className="flex items-center gap-1 text-[0.65rem] px-2 py-0.5 rounded-[4px] font-medium uppercase tracking-wide"
              style={{
                background: 'rgba(34,197,94,0.12)',
                color: '#22c55e',
                border: '1px solid rgba(34,197,94,0.2)',
              }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full live-dot shrink-0"
                style={{ background: '#22c55e' }}
              />
              Live
            </span>
          )}
          {isCached && !isLive && (
            <span
              className="text-[0.65rem] px-2 py-0.5 rounded-[4px] font-medium uppercase tracking-wide"
              style={{
                background: 'rgba(113,113,122,0.12)',
                color: '#71717a',
                border: '1px solid rgba(113,113,122,0.2)',
              }}
            >
              Cached
            </span>
          )}
        </div>
      </button>

      {/* Expandable body — always in DOM for smooth height animation */}
      <div
        style={{
          overflow: 'hidden',
          maxHeight: open ? '1200px' : '0',
          opacity: open ? 1 : 0,
          transition: 'max-height 0.22s ease, opacity 0.15s ease',
        }}
      >
        <div className="border-t" style={{ borderColor: '#27272a' }}>
          {maps.map((m, i) => (
            <MapRow key={i} {...m} />
          ))}
          {maps.length === 0 && (
            <p className="py-4 text-center text-sm" style={{ color: '#52525b' }}>
              No map data
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
