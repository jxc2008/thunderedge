'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Menu, X } from 'lucide-react'

const NAV_GROUPS = [
  {
    label: 'VCT',
    links: [
      { label: 'Player', href: '/' },
      { label: 'Edge', href: '/edge' },
      { label: 'Team', href: '/team' },
    ],
  },
  {
    label: 'Props',
    links: [
      { label: 'PrizePicks', href: '/prizepicks' },
      { label: 'Challengers PP', href: '/challengers-prizepicks' },
    ],
  },
  {
    label: 'Challengers',
    links: [{ label: 'Challengers Player', href: '/challengers' }],
  },
  {
    label: 'Strategy',
    links: [{ label: 'MoneyLines', href: '/moneylines' }],
  },
]

interface AppHeaderProps {
  activePage?: string
}

export function AppHeader({ activePage }: AppHeaderProps) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const pathname = usePathname()

  const isActive = (href: string) => {
    if (activePage) return activePage === href
    return pathname === href
  }

  const isGroupActive = (group: (typeof NAV_GROUPS)[0]) =>
    group.links.some((l) => isActive(l.href))

  return (
    <header
      className="sticky top-0 z-50 h-16 border-b"
      style={{
        background: 'rgba(10,10,10,0.95)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        borderColor: '#27272a',
      }}
    >
      <div className="max-w-[1400px] mx-auto px-6 h-full flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2.5 shrink-0 no-underline">
          <span
            className="w-8 h-8 flex items-center justify-center text-white font-bold text-base shrink-0"
            style={{
              background: 'linear-gradient(135deg, #3b82f6, #0ea5e9)',
              borderRadius: '6px',
            }}
          >
            T
          </span>
          <span className="text-white font-semibold text-[1.05rem] tracking-tight whitespace-nowrap">
            Thunder<span className="gradient-text">Edge</span>
          </span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-1" aria-label="Main navigation">
          {NAV_GROUPS.map((group, gi) => (
            <div key={group.label} className="flex items-center">
              {/* Group divider (not before first group) */}
              {gi > 0 && (
                <span
                  className="mx-2 w-px h-4 shrink-0"
                  style={{ background: '#27272a' }}
                  aria-hidden="true"
                />
              )}
              {/* Group label */}
              <span
                className="text-[0.65rem] uppercase tracking-widest mr-1.5 shrink-0"
                style={{ color: '#3f3f46', letterSpacing: '0.12em' }}
              >
                {group.label}
              </span>
              {/* Links */}
              {group.links.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="relative px-3 py-1 rounded-[6px] text-[0.8rem] font-medium transition-colors duration-150 whitespace-nowrap"
                  style={{
                    color: isActive(link.href) ? '#ffffff' : '#a1a1aa',
                    background: isActive(link.href) ? '#18181b' : 'transparent',
                  }}
                  aria-current={isActive(link.href) ? 'page' : undefined}
                >
                  {link.label}
                </Link>
              ))}
            </div>
          ))}
        </nav>

        {/* Mobile hamburger */}
        <button
          className="md:hidden flex items-center justify-center w-9 h-9 rounded-[6px] transition-colors"
          style={{ color: '#a1a1aa' }}
          onClick={() => setMobileOpen((v) => !v)}
          aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
          aria-expanded={mobileOpen}
        >
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div
          className="md:hidden border-t"
          style={{
            background: 'rgba(10,10,10,0.98)',
            borderColor: '#27272a',
          }}
          role="navigation"
          aria-label="Mobile navigation"
        >
          <div className="max-w-[1400px] mx-auto px-6 py-4 flex flex-col gap-4">
            {NAV_GROUPS.map((group) => (
              <div key={group.label}>
                <p
                  className="text-[0.65rem] uppercase tracking-widest mb-2"
                  style={{ color: '#3f3f46', letterSpacing: '0.12em' }}
                >
                  {group.label}
                </p>
                <div className="flex flex-col gap-0.5">
                  {group.links.map((link) => (
                    <Link
                      key={link.href}
                      href={link.href}
                      onClick={() => setMobileOpen(false)}
                      className="px-3 py-2 rounded-[6px] text-sm font-medium transition-colors"
                      style={{
                        color: isActive(link.href) ? '#ffffff' : '#a1a1aa',
                        background: isActive(link.href) ? '#18181b' : 'transparent',
                      }}
                      aria-current={isActive(link.href) ? 'page' : undefined}
                    >
                      {link.label}
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </header>
  )
}
