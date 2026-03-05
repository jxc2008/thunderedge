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
      className="bg-[#0D0D0D] border border-[rgba(240,224,64,0.12)] overflow-hidden"
      style={{ borderLeft: `3px solid ${accentColor}` }}
    >
      {/* Toggle button */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={
          'w-full flex items-center gap-3 px-5 py-4 text-left cursor-pointer ' +
          'font-display font-bold text-[0.9rem] uppercase tracking-[0.06em] text-[#e4e4e7] ' +
          'transition-colors duration-150 border-none ' +
          (open
            ? 'bg-[rgba(255,255,255,0.02)] hover:bg-[rgba(255,255,255,0.04)]'
            : 'bg-transparent hover:bg-[rgba(255,255,255,0.04)]')
        }
      >
        {open ? (
          <ChevronDown size={16} style={{ color: accentColor }} className="shrink-0" />
        ) : (
          <ChevronRight size={16} style={{ color: accentColor }} className="shrink-0" />
        )}
        {title}
      </button>

      {/* Animated content via CSS grid trick */}
      <div
        style={{
          display: 'grid',
          gridTemplateRows: open ? '1fr' : '0fr',
          transition: 'grid-template-rows 0.2s ease',
        }}
      >
        <div style={{ overflow: 'hidden' }}>
          <div className="px-5 pb-5 border-t border-[rgba(255,255,255,0.06)]">
            <div className="pt-5">{children}</div>
          </div>
        </div>
      </div>
    </div>
  )
}
