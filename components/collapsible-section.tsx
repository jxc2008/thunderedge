'use client'

import { useState, type ReactNode } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

interface CollapsibleSectionProps {
  title: string
  children: ReactNode
  defaultOpen?: boolean
  accentColor?: string
}

export function CollapsibleSection({
  title,
  children,
  defaultOpen = false,
  accentColor = '#F0E040',
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div
      style={{
        background: '#0D0D0D',
        border: '1px solid rgba(240,224,64,0.12)',
        borderLeft: `3px solid ${accentColor}`,
        overflow: 'hidden',
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          padding: '1rem 1.25rem',
          background: open ? 'rgba(255,255,255,0.02)' : 'transparent',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
          fontFamily: 'var(--font-display)',
          fontWeight: 700,
          fontSize: '0.9rem',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          color: '#e4e4e7',
          transition: 'background 0.15s',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = 'rgba(255,255,255,0.04)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = open ? 'rgba(255,255,255,0.02)' : 'transparent'
        }}
      >
        {open ? (
          <ChevronDown size={18} style={{ color: accentColor, flexShrink: 0 }} />
        ) : (
          <ChevronRight size={18} style={{ color: accentColor, flexShrink: 0 }} />
        )}
        {title}
      </button>
      {open && (
        <div style={{ padding: '0 1.25rem 1.25rem', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
          <div style={{ paddingTop: '1.25rem' }}>{children}</div>
        </div>
      )}
    </div>
  )
}
