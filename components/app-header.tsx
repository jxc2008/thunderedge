'use client'

import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { ChevronDown, Menu, X, RefreshCw, Check, AlertCircle } from 'lucide-react'

// Dropdown nav items matching original HTML nav structure
const NAV_DROPDOWNS = [
  {
    label: 'Thunderpick Kill Line',
    links: [
      { label: 'VCT Player', href: '/' },
      { label: 'Challengers', href: '/challengers' },
    ],
  },
  {
    label: 'PrizePicks',
    links: [
      { label: 'PrizePicks', href: '/prizepicks' },
      { label: 'Challengers PP', href: '/challengers-prizepicks' },
    ],
  },
]

const NAV_DIRECT = [
  { label: 'Matchup', href: '/team' },
  { label: 'MoneyLine', href: '/moneylines' },
]

// Page badge labels, matched to route
const PAGE_BADGES: Record<string, string> = {
  '/': 'Kill Line',
  '/challengers': 'Challengers',
  '/prizepicks': 'PrizePicks',
  '/challengers-prizepicks': 'Challengers PP',
  '/team': 'Matchup',
  '/moneylines': 'MoneyLine',
}

interface AppHeaderProps {
  activePage?: string
}

type SyncState = 'idle' | 'running' | 'done' | 'error'

export function AppHeader({ activePage }: AppHeaderProps) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [isClosingMobile, setIsClosingMobile] = useState(false)
  const [openDropdown, setOpenDropdown] = useState<string | null>(null)
  const [syncState, setSyncState] = useState<SyncState>('idle')
  const [syncStep, setSyncStep] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pathname = usePathname()

  const currentPath = activePage ?? pathname

  const STEP_LABELS: Record<string, string> = {
    populate_db: 'Fetching matches…',
    atk_def:     'Atk/def data…',
    pick_bans:   'Pick/bans…',
    moneyline:   'Odds data…',
    clear_cache: 'Clearing cache…',
  }

  function stopPolling() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }

  useEffect(() => () => stopPolling(), [])

  async function handleSync() {
    if (syncState === 'running') return
    setSyncState('running')
    setSyncStep('Starting…')
    try {
      await fetch('/api/admin/sync', { method: 'POST' })
    } catch {
      setSyncState('error')
      setSyncStep('Network error')
      return
    }
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch('/api/admin/sync-status')
        const data = await res.json()
        // Show label for last in-progress step
        const running = (data.steps ?? []).filter((s: { ok: boolean | null }) => s.ok === null)
        const last    = (data.steps ?? []).at(-1)
        if (running.length > 0) {
          setSyncStep(STEP_LABELS[running[0].step] ?? running[0].step)
        } else if (last) {
          setSyncStep(STEP_LABELS[last.step] ?? last.step)
        }
        if (!data.running) {
          stopPolling()
          const anyFailed = (data.steps ?? []).some((s: { ok: boolean | null }) => s.ok === false)
          setSyncState(anyFailed || data.error ? 'error' : 'done')
          setTimeout(() => { setSyncState('idle'); setSyncStep('') }, 4000)
        }
      } catch { /* ignore transient poll errors */ }
    }, 1500)
  }

  const isActive = (href: string) => currentPath === href

  const isDropdownActive = (links: { href: string }[]) =>
    links.some((l) => currentPath === l.href)

  const handleToggleMobile = () => {
    if (mobileOpen) {
      setIsClosingMobile(true)
      setTimeout(() => {
        setMobileOpen(false)
        setIsClosingMobile(false)
      }, 180)
    } else {
      setMobileOpen(true)
    }
  }

  const handleNavLinkClick = () => {
    setIsClosingMobile(true)
    setTimeout(() => {
      setMobileOpen(false)
      setIsClosingMobile(false)
    }, 180)
  }

  const pageBadge = PAGE_BADGES[currentPath]

  return (
    <header
      className="sticky top-0 z-50"
      style={{
        background: 'rgba(0,0,0,0.85)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        padding: '1rem 0',
      }}
    >
      <div className="page-container flex items-center justify-between">
        {/* Logo — ⚡ THUNDEREDGE in Barlow Condensed */}
        <Link href="/" className="flex items-center gap-3 shrink-0" style={{ textDecoration: 'none' }}>
          <span
            className="font-display font-extrabold text-white"
            style={{ fontSize: '1.4rem', letterSpacing: '-0.01em', lineHeight: 1 }}
          >
            <span style={{ color: '#F0E040' }}>⚡</span>{' '}
            THUNDEREDGE
          </span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-2" aria-label="Main navigation">
          {/* Dropdown groups */}
          {NAV_DROPDOWNS.map((group) => {
            const active = isDropdownActive(group.links)
            return (
              <div
                key={group.label}
                className="relative"
                onMouseEnter={() => setOpenDropdown(group.label)}
                onMouseLeave={() => setOpenDropdown(null)}
              >
                <button
                  className="flex items-center gap-1 px-[0.75rem] py-[0.5rem] text-[0.8rem] font-medium uppercase tracking-[0.08em] transition-colors duration-150"
                  style={{
                    color: active ? '#ffffff' : 'rgba(255,255,255,0.55)',
                    background: 'none',
                    border: 'none',
                    borderBottom: active ? '2px solid #F0E040' : '2px solid transparent',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                  }}
                >
                  {group.label}
                  <ChevronDown size={12} style={{ opacity: 0.6 }} />
                </button>

                {/* Dropdown menu */}
                {openDropdown === group.label && (
                  <div
                    className="absolute top-full left-0 z-50 py-2"
                    style={{
                      minWidth: '180px',
                      background: 'rgba(0,0,0,0.95)',
                      border: '1px solid rgba(255,255,255,0.08)',
                      boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                    }}
                  >
                    {group.links.map((link) => (
                      <Link
                        key={link.href}
                        href={link.href}
                        className="block px-4 py-2.5 text-[0.8rem] transition-colors duration-100"
                        style={{
                          color: isActive(link.href) ? '#F0E040' : 'rgba(255,255,255,0.7)',
                          background: isActive(link.href) ? 'rgba(255,255,255,0.04)' : 'transparent',
                          borderLeft: isActive(link.href) ? '3px solid #F0E040' : '3px solid transparent',
                          textDecoration: 'none',
                        }}
                        onMouseEnter={(e) => {
                          if (!isActive(link.href)) {
                            e.currentTarget.style.color = '#ffffff'
                            e.currentTarget.style.background = 'rgba(255,255,255,0.06)'
                            e.currentTarget.style.borderLeftColor = '#F0E040'
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (!isActive(link.href)) {
                            e.currentTarget.style.color = 'rgba(255,255,255,0.7)'
                            e.currentTarget.style.background = 'transparent'
                            e.currentTarget.style.borderLeftColor = 'transparent'
                          }
                        }}
                      >
                        {link.label}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            )
          })}

          {/* Direct nav links */}
          {NAV_DIRECT.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="px-[0.75rem] py-[0.5rem] text-[0.8rem] font-medium uppercase tracking-[0.08em] transition-colors duration-150 whitespace-nowrap"
              style={{
                color: isActive(link.href) ? '#ffffff' : 'rgba(255,255,255,0.55)',
                borderBottom: isActive(link.href) ? '2px solid #F0E040' : '2px solid transparent',
                textDecoration: 'none',
              }}
              aria-current={isActive(link.href) ? 'page' : undefined}
            >
              {link.label}
            </Link>
          ))}

          {/* Page badge */}
          {pageBadge && (
            <span
              className="font-display font-semibold uppercase ml-2"
              style={{
                fontSize: '0.75rem',
                letterSpacing: '0.06em',
                padding: '0.35rem 0.65rem',
                background: 'rgba(240, 224, 64, 0.15)',
                border: '1px solid rgba(240, 224, 64, 0.3)',
                color: '#F0E040',
              }}
            >
              {pageBadge}
            </span>
          )}
        </nav>

        {/* Sync data button */}
        <button
          onClick={handleSync}
          disabled={syncState === 'running'}
          title={syncState === 'running' ? syncStep : 'Sync latest VCT data'}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.35rem 0.75rem',
            background: syncState === 'done'  ? 'rgba(34,197,94,0.15)'
                      : syncState === 'error' ? 'rgba(239,68,68,0.15)'
                      : syncState === 'running' ? 'rgba(240,224,64,0.1)'
                      : 'rgba(255,255,255,0.07)',
            border: `1px solid ${
              syncState === 'done'    ? 'rgba(34,197,94,0.4)'
            : syncState === 'error'  ? 'rgba(239,68,68,0.4)'
            : syncState === 'running'? 'rgba(240,224,64,0.3)'
            : 'rgba(255,255,255,0.12)'}`,
            borderRadius: '6px',
            color: syncState === 'done'  ? '#22c55e'
                 : syncState === 'error' ? '#ef4444'
                 : syncState === 'running' ? '#F0E040'
                 : 'rgba(255,255,255,0.6)',
            fontSize: '0.72rem',
            fontWeight: 600,
            letterSpacing: '0.04em',
            cursor: syncState === 'running' ? 'not-allowed' : 'pointer',
            transition: 'all 0.2s',
            whiteSpace: 'nowrap',
            opacity: syncState === 'running' ? 0.9 : 1,
          }}
        >
          {syncState === 'running' ? (
            <RefreshCw size={12} className="animate-spin" />
          ) : syncState === 'done' ? (
            <Check size={12} />
          ) : syncState === 'error' ? (
            <AlertCircle size={12} />
          ) : (
            <RefreshCw size={12} />
          )}
          {syncState === 'running' ? syncStep
         : syncState === 'done'    ? 'Up to date'
         : syncState === 'error'   ? 'Sync failed'
         : 'Sync Data'}
        </button>

        {/* Mobile hamburger */}
        <button
          className="md:hidden flex items-center justify-center w-9 h-9 transition-colors"
          style={{ color: '#a1a1aa', background: 'none', border: 'none', cursor: 'pointer' }}
          onClick={handleToggleMobile}
          aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
          aria-expanded={mobileOpen}
        >
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div
          className={`md:hidden ${isClosingMobile ? 'mobile-drawer-close' : 'mobile-drawer-open'}`}
          style={{
            background: 'rgba(0,0,0,0.98)',
            borderTop: '1px solid rgba(255,255,255,0.06)',
          }}
          role="navigation"
          aria-label="Mobile navigation"
        >
          <div className="max-w-[1400px] mx-auto px-6 py-4 flex flex-col gap-4">
            {NAV_DROPDOWNS.map((group) => (
              <div key={group.label}>
                <p
                  className="text-[0.7rem] uppercase tracking-[0.1em] font-medium mb-2"
                  style={{ color: 'rgba(255,255,255,0.35)' }}
                >
                  {group.label}
                </p>
                <div className="flex flex-col gap-0.5">
                  {group.links.map((link) => (
                    <Link
                      key={link.href}
                      href={link.href}
                      onClick={handleNavLinkClick}
                      className="px-3 py-2 text-sm font-medium transition-colors"
                      style={{
                        color: isActive(link.href) ? '#F0E040' : 'rgba(255,255,255,0.7)',
                        borderLeft: isActive(link.href) ? '3px solid #F0E040' : '3px solid transparent',
                        textDecoration: 'none',
                      }}
                    >
                      {link.label}
                    </Link>
                  ))}
                </div>
              </div>
            ))}
            <div>
              <p
                className="text-[0.7rem] uppercase tracking-[0.1em] font-medium mb-2"
                style={{ color: 'rgba(255,255,255,0.35)' }}
              >
                Pages
              </p>
              <div className="flex flex-col gap-0.5">
                {NAV_DIRECT.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    onClick={handleNavLinkClick}
                    className="px-3 py-2 text-sm font-medium transition-colors"
                    style={{
                      color: isActive(link.href) ? '#F0E040' : 'rgba(255,255,255,0.7)',
                      borderLeft: isActive(link.href) ? '3px solid #F0E040' : '3px solid transparent',
                      textDecoration: 'none',
                    }}
                  >
                    {link.label}
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </header>
  )
}
