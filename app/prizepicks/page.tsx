'use client'

import { useState, useRef, useCallback } from 'react'
import { Loader2, RefreshCw, Upload, History } from 'lucide-react'
import { AppHeader } from '@/components/app-header'
import { OverUnderDisplay } from '@/components/over-under-display'
import { StatsGrid, type StatCardData } from '@/components/stats-grid'
import { RecommendationCard } from '@/components/recommendation-card'
import { DistributionChart } from '@/components/distribution-chart'
import { EmptyState } from '@/components/ux-patterns'

const ACCENT = '#8B2BFA'
const ACCENT_BG = 'rgba(139,43,250,0.08)'
const ACCENT_BORDER = 'rgba(139,43,250,0.2)'

// ─── Types ────────────────────────────────────────────────────────────────────

type Tab = 'leaderboard' | 'analyze' | 'parlay' | 'history'
type SortKey = 'hit_desc' | 'hit_asc' | 'line_asc' | 'line_desc' | 'adj_desc'
type FilterSide = 'all' | 'over' | 'under'

interface LbRow {
  rank: number
  player_name: string
  vlr_ign?: string
  team?: string
  line?: number
  mu?: number
  p_hit?: number
  p_over?: number
  p_under?: number
  adj_p_hit?: number
  adj_p_over?: number
  adj_p_under?: number
  best_side?: string
  adj_best_side?: string
  sample_size?: number
  incomplete?: boolean
  reason?: string
}

interface PpAnalysis {
  player_ign?: string
  team?: string
  kill_line?: number
  over_percentage?: number
  under_percentage?: number
  total_maps?: number
  classification?: string
  recommendation?: string
  confidence?: string
  mean_kills?: number
  median_kills?: number
}

interface PpEdgeData {
  player?: { ign: string; sample_size: number; confidence: string }
  line?: number
  model?: { p_over: number; p_under: number; mu: number }
  market?: { p_over_vigfree: number; p_under_vigfree: number; mu_implied: number }
  edge?: { recommended: string; ev_over: number; ev_under: number; roi_over_pct: number; roi_under_pct: number }
  visualization?: { x: number[]; model_pmf: number[]; market_pmf: number[] }
}

interface ParlayLeg { ign: string; line: number; side: 'over' | 'under' }
interface ParlayResult { hit_probability: number; expected_value?: number; details?: unknown[] }

interface HistoryItem {
  id: string; created_at: string; player_count: number; source?: string; snapshot_type?: string
}

interface Matchup { team1: string; team2: string; team1_odds: number; team2_odds: number }

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getHitColor(pct: number) {
  if (pct >= 70) return '#22c55e'
  if (pct >= 60) return '#84cc16'
  if (pct >= 50) return '#eab308'
  return '#ef4444'
}
function getRankColor(rank: number) {
  if (rank === 1) return ACCENT
  if (rank <= 3) return '#ccc'
  return '#555'
}

function s(val: React.CSSProperties): React.CSSProperties { return val }

const INPUT = s({ background: 'rgba(14,6,24,0.8)', border: `1px solid ${ACCENT_BORDER}`, color: '#fff', padding: '0.75rem 1rem', fontSize: '0.875rem', fontFamily: 'inherit', outline: 'none', borderRadius: 0, width: '100%' })
const LABEL = s({ fontSize: '0.7rem', fontWeight: 500, textTransform: 'uppercase' as const, letterSpacing: '0.12em', color: 'rgba(255,255,255,0.4)', display: 'block', marginBottom: '0.5rem' })
const BTN_PRIMARY = s({ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.9rem', textTransform: 'uppercase' as const, letterSpacing: '0.06em', padding: '0.75rem 2rem', background: ACCENT, color: '#fff', border: 'none', borderRadius: 0, cursor: 'pointer' })

// ─── Leaderboard card ─────────────────────────────────────────────────────────

function StatPill({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 52 }}>
      <div style={{ fontSize: '0.6rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'rgba(255,255,255,0.35)', marginBottom: 2 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.95rem', color: color ?? '#e4e4e7' }}>{value}</div>
    </div>
  )
}

function LbCard({ row, onAddToParlay }: { row: LbRow; onAddToParlay: (ign: string, line: number) => void }) {
  const isIncomplete = row.incomplete === true
  const rankVal = row.rank > 0 ? row.rank : '—'
  const top3 = !isIncomplete && row.rank >= 1 && row.rank <= 3
  const isAdj = row.adj_p_hit != null
  const hitPct = isAdj ? row.adj_p_hit! * 100 : (row.p_hit ?? 0) * 100
  const pOver = isAdj ? (row.adj_p_over ?? row.p_over ?? 0) * 100 : (row.p_over ?? 0) * 100
  const pUnder = isAdj ? (row.adj_p_under ?? row.p_under ?? 0) * 100 : (row.p_under ?? 0) * 100
  const bestSide = row.adj_best_side || row.best_side || 'N/A'
  const ign = row.vlr_ign || row.player_name || ''

  return (
    <div
      style={{
        padding: '0.75rem 1rem',
        border: '1px solid rgba(255,255,255,0.06)',
        borderLeft: `3px solid ${top3 ? ACCENT : isIncomplete ? 'rgba(255,255,255,0.08)' : 'rgba(139,43,250,0.25)'}`,
        marginBottom: '0.4rem',
        opacity: isIncomplete ? 0.45 : 1,
        background: top3 ? ACCENT_BG : 'transparent',
      }}
    >
      {/* Top row: rank · name · team · hit% */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        {/* Rank */}
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '2rem', color: getRankColor(row.rank), lineHeight: 1, minWidth: 36, textAlign: 'center' }}>
          {rankVal}
        </div>

        {/* Identity */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 700, fontSize: '1rem', color: isIncomplete ? '#71717a' : '#fff' }}>
              {row.player_name}
            </span>
            {row.vlr_ign && row.vlr_ign !== row.player_name && (
              <span style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.35)', fontFamily: 'monospace' }}>@{row.vlr_ign}</span>
            )}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.45)', marginTop: 1 }}>
            {row.team ?? '—'}
          </div>
          {isIncomplete && row.reason && (
            <div style={{ fontSize: '0.7rem', color: '#71717a', marginTop: 2 }}>{row.reason}</div>
          )}
        </div>

        {/* Hit % — large, right-aligned */}
        {!isIncomplete && (
          <div style={{ textAlign: 'right', flexShrink: 0 }}>
            {isAdj && <div style={{ fontSize: '0.6rem', color: ACCENT, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 1 }}>ADJ</div>}
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '2rem', lineHeight: 1, color: getHitColor(hitPct) }}>
              {hitPct.toFixed(1)}%
            </div>
            <div style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', color: bestSide === 'over' ? '#22c55e' : '#ef4444', marginTop: 2 }}>
              {bestSide}
            </div>
          </div>
        )}

        {/* Add to parlay */}
        {!isIncomplete && ign && (
          <button
            onClick={() => onAddToParlay(ign, row.line ?? 30.5)}
            title="Add to parlay"
            style={{ width: 28, height: 28, padding: 0, fontSize: '1.1rem', lineHeight: '1', background: ACCENT_BG, border: `1px solid ${ACCENT}`, color: ACCENT, cursor: 'pointer', flexShrink: 0 }}
          >+</button>
        )}
      </div>

      {/* Stats row */}
      {!isIncomplete && (
        <div style={{
          display: 'flex', gap: '0.5rem', marginTop: '0.6rem',
          paddingTop: '0.6rem', borderTop: '1px solid rgba(255,255,255,0.06)',
          flexWrap: 'wrap',
        }}>
          <StatPill label="Line" value={row.line != null ? `${row.line}` : '—'} color="rgba(255,255,255,0.8)" />
          <div style={{ width: 1, background: 'rgba(255,255,255,0.08)', alignSelf: 'stretch', margin: '0 2px' }} />
          <StatPill label="μ (Model)" value={row.mu != null ? row.mu.toFixed(1) : '—'} color={ACCENT} />
          <div style={{ width: 1, background: 'rgba(255,255,255,0.08)', alignSelf: 'stretch', margin: '0 2px' }} />
          <StatPill label="P(Over)" value={`${pOver.toFixed(1)}%`} color="#22c55e" />
          <StatPill label="P(Under)" value={`${pUnder.toFixed(1)}%`} color="#ef4444" />
          <div style={{ width: 1, background: 'rgba(255,255,255,0.08)', alignSelf: 'stretch', margin: '0 2px' }} />
          <StatPill label="Sample" value={row.sample_size != null ? `${row.sample_size}m` : '—'} color="rgba(255,255,255,0.55)" />
        </div>
      )}
    </div>
  )
}

// ─── Leaderboard tab ──────────────────────────────────────────────────────────

function LeaderboardTab({ onAddToParlay, onSwitchToParlay, onSwitchToHistory }: {
  onAddToParlay: (ign: string, line: number) => void
  onSwitchToParlay: () => void
  onSwitchToHistory: () => void
}) {
  const [rows, setRows] = useState<LbRow[]>([])
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [progressMsg, setProgressMsg] = useState('')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<SortKey>('hit_desc')
  const [filter, setFilter] = useState<FilterSide>('all')
  const [comboMaps, setComboMaps] = useState(2)
  const [uploadCombo, setUploadCombo] = useState('3')
  const [message, setMessage] = useState('')
  const [oddsStatus, setOddsStatus] = useState<string | null>(null)
  const [matchups, setMatchups] = useState<Matchup[]>([])
  const [currentLb, setCurrentLb] = useState<LbRow[]>([])
  const uploadRef = useRef<HTMLInputElement>(null)
  const oddsRef = useRef<HTMLInputElement>(null)

  const renderLb = useCallback((data: { leaderboard?: LbRow[]; message?: string; created_at?: string }) => {
    const lb = data.leaderboard || []
    setCurrentLb(lb)
    setRows(lb)
    setMessage(data.message || (data.created_at ? `Loaded from history – ${new Date(data.created_at).toLocaleString()}` : ''))
  }, [])

  async function handleRefresh() {
    setLoading(true); setProgress(10); setProgressMsg('Fetching live leaderboard...')
    try {
      const r = await fetch(`/api/prizepicks/leaderboard?combo_maps=${comboMaps}`)
      const d = await r.json()
      if (!r.ok || d.error) throw new Error(d.error || 'Failed')
      renderLb(d)
    } catch (e) {
      setMessage((e as Error).message)
    } finally { setLoading(false); setProgress(0) }
  }

  function handleUpload(input: HTMLInputElement) {
    const files = input.files
    if (!files || files.length === 0) return
    setLoading(true); setProgress(5); setProgressMsg('Uploading...')

    const fd = new FormData()
    if (files.length === 1) fd.append('image', files[0])
    else Array.from(files).forEach((f) => fd.append('images', f))
    input.value = ''

    const comboVal = uploadCombo ? `?combo_maps=${uploadCombo}` : ''
    const xhr = new XMLHttpRequest()

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) setProgress(Math.round((e.loaded / e.total) * 40))
    }
    const interval = setInterval(() => {
      setProgress((p) => { if (p >= 95) return p; return p + 3 })
      setProgressMsg((msg) => (msg.startsWith('Up') ? 'Parsing & ranking players...' : msg))
    }, 500)

    xhr.onload = () => {
      clearInterval(interval); setProgress(100); setProgressMsg('Done!')
      try {
        const d = JSON.parse(xhr.responseText)
        if (xhr.status >= 400 || d.error) { setMessage(d.error || 'Upload failed'); }
        else renderLb(d)
      } catch { setMessage('Parse error') }
      setLoading(false)
    }
    xhr.onerror = () => { clearInterval(interval); setLoading(false); setMessage('Network error') }
    xhr.open('POST', `/api/prizepicks/leaderboard/upload${comboVal}`, true)
    xhr.send(fd)
  }

  async function handleOddsUpload(input: HTMLInputElement) {
    const file = input.files?.[0]
    if (!file) return
    input.value = ''
    if (!currentLb.length) { setOddsStatus('Load a leaderboard first before uploading odds.'); return }
    setOddsStatus('Parsing odds screenshot with Gemini...')
    const fd = new FormData()
    fd.append('image', file)
    fd.append('leaderboard', JSON.stringify(currentLb))
    try {
      const r = await fetch('/api/prizepicks/leaderboard/apply-matchup', { method: 'POST', body: fd })
      const d = await r.json()
      if (!r.ok || !d.success) { setOddsStatus(d.error || 'Failed to parse odds'); return }
      renderLb(d)
      setMatchups(d.matchups_parsed || [])
      setOddsStatus(null)
    } catch (e) { setOddsStatus((e as Error).message) }
  }

  // Filter + sort
  const visible = rows
    .filter((r) => {
      if (search && !(r.player_name || '').toLowerCase().includes(search.toLowerCase())) return false
      const side = r.adj_best_side || r.best_side || ''
      if (filter === 'over' && side !== 'over') return false
      if (filter === 'under' && side !== 'under') return false
      return true
    })
    .sort((a, b) => {
      const aHit = (a.adj_p_hit ?? a.p_hit ?? 0) * 100
      const bHit = (b.adj_p_hit ?? b.p_hit ?? 0) * 100
      if (sort === 'hit_desc') return bHit - aHit
      if (sort === 'hit_asc') return aHit - bHit
      if (sort === 'line_asc') return (a.line ?? 0) - (b.line ?? 0)
      if (sort === 'line_desc') return (b.line ?? 0) - (a.line ?? 0)
      if (sort === 'adj_desc') return ((b.adj_p_hit ?? b.p_hit ?? 0) - (a.adj_p_hit ?? a.p_hit ?? 0))
      return (a.rank || 999) - (b.rank || 999)
    })
  const completeCount = rows.filter((r) => !r.incomplete).length

  const tabBtn = (val: string, label: string, active: boolean, onClick: () => void) => (
    <button
      type="button" onClick={onClick}
      style={{
        padding: '0.4rem 0.7rem', fontSize: '0.7rem', fontFamily: 'var(--font-display)', fontWeight: 600,
        textTransform: 'uppercase', letterSpacing: '0.06em',
        background: active ? ACCENT : 'transparent',
        color: active ? '#fff' : 'rgba(255,255,255,0.6)',
        border: `1px solid ${active ? ACCENT : 'rgba(255,255,255,0.2)'}`, cursor: 'pointer',
      }}
    >
      {label}
    </button>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Control bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.75rem 1rem', borderBottom: '1px solid rgba(255,255,255,0.06)', flexWrap: 'wrap' }}>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '1rem', color: '#fff' }}>LEADERBOARD</span>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: '0.75rem', padding: '0.2rem 0.5rem', background: ACCENT_BG, color: ACCENT }}>{completeCount}</span>
        <input
          type="text" value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder="/ to filter players..."
          style={{ flex: 1, minWidth: 120, padding: '0.4rem 0.6rem', fontSize: '0.8rem', background: ACCENT_BG, border: `1px solid ${ACCENT_BORDER}`, color: '#fff', outline: 'none' }}
        />
        <select
          value={sort} onChange={(e) => setSort(e.target.value as SortKey)}
          style={{ padding: '0.4rem 0.6rem', fontSize: '0.8rem', background: ACCENT_BG, border: `1px solid ${ACCENT_BORDER}`, color: '#fff' }}
        >
          <option value="hit_desc">Hit% ↓</option>
          <option value="hit_asc">Hit% ↑</option>
          <option value="line_asc">Line ↑</option>
          <option value="line_desc">Line ↓</option>
          <option value="adj_desc">Adj% ↓</option>
        </select>
        <div style={{ display: 'flex', gap: '0.25rem' }}>
          {tabBtn('all', 'ALL', filter === 'all', () => setFilter('all'))}
          {tabBtn('over', 'OVER', filter === 'over', () => setFilter('over'))}
          {tabBtn('under', 'UNDER', filter === 'under', () => setFilter('under'))}
        </div>
      </div>

      {/* Row 2 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 1rem', borderBottom: '1px solid rgba(255,255,255,0.06)', flexWrap: 'wrap' }}>
        {/* Bo3/Bo5 toggle */}
        <div style={{ display: 'flex', background: '#27272a', borderRadius: 8, padding: 2 }}>
          {[{ n: 2, l: 'Bo3' }, { n: 3, l: 'Bo5' }].map(({ n, l }) => (
            <button
              key={n} type="button" onClick={() => setComboMaps(n)}
              style={{ padding: '0.5rem 1rem', border: 'none', borderRadius: 6, background: comboMaps === n ? '#3b82f6' : 'transparent', color: comboMaps === n ? '#fff' : '#a1a1aa', fontWeight: 600, cursor: 'pointer', fontSize: '0.875rem' }}
            >{l}</button>
          ))}
        </div>

        {/* Refresh */}
        <button
          type="button" onClick={handleRefresh} disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0.5rem 1rem', background: ACCENT_BG, border: `1px solid ${ACCENT_BORDER}`, color: '#e4e4e7', cursor: loading ? 'not-allowed' : 'pointer', fontSize: '0.8rem', borderRadius: 8 }}
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />} Refresh
        </button>

        {/* Upload leaderboard screenshot */}
        <label style={{ cursor: 'pointer', padding: '0.5rem 1rem', background: 'linear-gradient(135deg,#16a34a 0%,#22c55e 100%)', borderRadius: 8, fontSize: '0.8rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6, color: '#fff' }}>
          <Upload size={14} /> Upload
          <input type="file" accept="image/*" multiple ref={uploadRef} style={{ display: 'none' }} onChange={(e) => handleUpload(e.target as HTMLInputElement)} />
        </label>

        <select
          value={uploadCombo} onChange={(e) => setUploadCombo(e.target.value)}
          title="Force Bo3 or Bo5"
          style={{ background: '#27272a', color: '#e4e4e7', border: '1px solid #3f3f46', borderRadius: 6, padding: '0.4rem 0.6rem', fontSize: '0.8rem' }}
        >
          <option value="">Auto-detect</option>
          <option value="2">Bo3</option>
          <option value="3">Bo5</option>
        </select>
      </div>

      {/* Progress bar */}
      {loading && (
        <div style={{ padding: '1rem', textAlign: 'center', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
          <p style={{ fontSize: '0.875rem', color: 'rgba(255,255,255,0.5)', marginBottom: '0.5rem' }}>{progressMsg}</p>
          <div style={{ maxWidth: 320, margin: '0 auto', background: '#27272a', borderRadius: 8, overflow: 'hidden', height: 8 }}>
            <div style={{ height: '100%', width: `${progress}%`, background: 'linear-gradient(90deg,#3b82f6,#22c55e)', transition: 'width 0.3s ease' }} />
          </div>
          <p style={{ color: '#a1a1aa', fontSize: '0.875rem', marginTop: '0.5rem', fontWeight: 600 }}>{progress}%</p>
        </div>
      )}

      {/* Scrollable leaderboard list */}
      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '0.75rem 1rem' }}>
        {message && <p style={{ color: '#71717a', fontSize: '0.875rem', marginBottom: '0.75rem' }}>{message}</p>}

        {visible.length === 0 && !loading ? (
          <div style={{ textAlign: 'center', padding: '3rem 1rem' }}>
            <div style={{ fontSize: '2rem', opacity: 0.2, marginBottom: '0.75rem' }}>◦◦◦</div>
            <div style={{ fontSize: '0.875rem', color: 'rgba(255,255,255,0.25)' }}>
              {rows.length === 0 ? 'Load a leaderboard to see ranked players' : 'No players match the current filter'}
            </div>
          </div>
        ) : (
          visible.map((row, i) => (
            <LbCard key={i} row={row} onAddToParlay={(ign, line) => { onAddToParlay(ign, line); onSwitchToParlay() }} />
          ))
        )}

        {/* Matchup odds section */}
        <div
          style={{
            marginTop: '1.25rem', padding: '1rem',
            background: ACCENT_BG, border: `2px dashed rgba(139,43,250,0.4)`,
          }}
        >
          <div style={{ fontWeight: 600, color: '#e4e4e7', fontSize: '0.9rem' }}>Matchup Odds</div>
          <div style={{ fontSize: '0.8rem', color: '#71717a', marginTop: '0.2rem' }}>
            Upload a screenshot of today's moneyline odds — adjusted Over%/Under% will appear in the leaderboard
          </div>
          <label style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: '0.5rem', padding: '0.5rem 1rem', background: 'linear-gradient(135deg,#7c3aed 0%,#a855f7 100%)', borderRadius: 8, fontSize: '0.875rem', fontWeight: 600, color: '#fff' }}>
            <Upload size={14} /> Upload Odds Screenshot
            <input type="file" accept="image/*" ref={oddsRef} style={{ display: 'none' }} onChange={(e) => handleOddsUpload(e.target as HTMLInputElement)} />
          </label>
          {oddsStatus && <p style={{ color: '#f59e0b', fontSize: '0.875rem', marginTop: '0.75rem' }}>{oddsStatus}</p>}
          {matchups.length > 0 && (
            <div style={{ marginTop: '0.75rem' }}>
              <div style={{ fontSize: '0.78rem', color: '#a1a1aa', marginBottom: '0.4rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Detected matchups</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                {matchups.map((m, i) => {
                  const o1 = m.team1_odds > 0 ? `+${m.team1_odds}` : `${m.team1_odds}`
                  const o2 = m.team2_odds > 0 ? `+${m.team2_odds}` : `${m.team2_odds}`
                  return (
                    <span key={i} style={{ background: '#27272a', border: '1px solid #3f3f46', borderRadius: 6, padding: '0.3rem 0.6rem', fontSize: '0.8rem', color: '#e4e4e7' }}>
                      {m.team1} <span style={{ color: '#a855f7', fontWeight: 700 }}>{o1}</span> vs {m.team2} <span style={{ color: '#a855f7', fontWeight: 700 }}>{o2}</span>
                    </span>
                  )
                })}
              </div>
            </div>
          )}
        </div>

        {/* View history */}
        <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid #27272a' }}>
          <button
            type="button" onClick={onSwitchToHistory}
            style={{ background: '#27272a', color: '#e4e4e7', padding: '0.5rem 1rem', border: 'none', cursor: 'pointer', fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <History size={14} /> View History
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Analyze tab ──────────────────────────────────────────────────────────────

function AnalyzeTab() {
  const [playerInput, setPlayerInput] = useState('')
  const [killLine, setKillLine] = useState('30.5')
  const [comboMaps, setComboMaps] = useState(2)
  const [overOdds, setOverOdds] = useState('')
  const [underOdds, setUnderOdds] = useState('')
  const [teamOdds, setTeamOdds] = useState('')
  const [oppOdds, setOppOdds] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ edge: PpEdgeData; elapsed: string } | null>(null)

  const lineLabel = comboMaps === 2 ? 'PrizePicks Line (Maps 1+2 Combined)' : 'PrizePicks Line (Maps 1+2+3 Combined)'

  async function handleAnalyze() {
    const ign = playerInput.trim(); if (!ign) return
    const line = parseFloat(killLine) || 30.5
    const parsedOver = parseFloat(overOdds)
    const parsedUnder = parseFloat(underOdds)
    const teamQ = teamOdds && oppOdds ? `&team_odds=${teamOdds}&opp_odds=${oppOdds}` : ''
    const oddsQ = !isNaN(parsedOver) && !isNaN(parsedUnder) ? `&over_odds=${parsedOver}&under_odds=${parsedUnder}` : ''

    setLoading(true); setError(null); setResult(null)
    try {
      const t0 = performance.now()
      const endpoint = `/api/prizepicks/edge/${encodeURIComponent(ign)}?line=${line}&combo_maps=${comboMaps}${oddsQ}${teamQ}`
      const r = await fetch(endpoint)
      const d = await r.json()
      if (!r.ok || d.error) throw new Error(d.error || 'API error')
      setResult({ edge: d, elapsed: ((performance.now() - t0) / 1000).toFixed(2) })
    } catch (e) { setError((e as Error).message) }
    finally { setLoading(false) }
  }

  const kk = (e: React.KeyboardEvent) => { if (e.key === 'Enter') handleAnalyze() }
  const edge = result?.edge

  const stats: StatCardData[] = edge ? [
    { label: 'Model Mean', value: edge.model?.mu?.toFixed(1) ?? '—', delta: 'kills (combined)', semantic: 'neutral' },
    { label: 'Market Implied', value: edge.market?.mu_implied?.toFixed(1) ?? '—', delta: 'kill line', semantic: 'neutral' },
    { label: 'Sample Size', value: edge.player?.sample_size ?? '—', delta: 'combo samples', semantic: 'neutral' },
    { label: 'Model P(Over)', value: `${((edge.model?.p_over ?? 0) * 100).toFixed(1)}%`, delta: 'probability', semantic: (edge.model?.p_over ?? 0) >= 0.55 ? 'positive' : 'neutral' },
    { label: 'EV Over', value: `${(edge.edge?.ev_over ?? 0) > 0 ? '+' : ''}${(edge.edge?.ev_over ?? 0).toFixed(4)}`, delta: 'expected value', semantic: (edge.edge?.ev_over ?? 0) > 0 ? 'positive' : 'negative' },
    { label: 'Confidence', value: edge.player?.confidence ?? '—', delta: 'data quality', semantic: edge.player?.confidence === 'HIGH' ? 'positive' : edge.player?.confidence === 'LOW' ? 'negative' : 'neutral' },
  ] : []

  const dist = edge?.visualization
    ? (edge.visualization.x || []).map((x, i) => ({
        kills: x,
        modelPct: +((edge.visualization!.model_pmf[i] ?? 0) * 100).toFixed(3),
        marketPct: +((edge.visualization!.market_pmf[i] ?? 0) * 100).toFixed(3),
      }))
    : []

  const recommended = edge?.edge?.recommended ?? 'NO BET'
  const recType: 'BET_OVER' | 'BET_UNDER' | 'NO_BET' = recommended === 'OVER' ? 'BET_OVER' : recommended === 'UNDER' ? 'BET_UNDER' : 'NO_BET'
  const recEV = recommended === 'OVER' ? (edge?.edge?.ev_over ?? 0) : recommended === 'UNDER' ? (edge?.edge?.ev_under ?? 0) : 0

  return (
    <div style={{ padding: '1rem', overflowY: 'auto' }}>
      {/* Form */}
      <div style={{ background: ACCENT_BG, border: `1px solid ${ACCENT_BORDER}`, borderLeft: `3px solid ${ACCENT}`, padding: '1.5rem', marginBottom: '1.5rem' }}>
        {/* Bo3/Bo5 toggle */}
        <div style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'inline-flex', background: '#27272a', borderRadius: 8, padding: 2 }}>
            {[{ n: 2, l: 'Bo3' }, { n: 3, l: 'Bo5' }].map(({ n, l }) => (
              <button key={n} type="button" onClick={() => setComboMaps(n)}
                style={{ padding: '0.4rem 0.9rem', border: 'none', borderRadius: 6, background: comboMaps === n ? '#3b82f6' : 'transparent', color: comboMaps === n ? '#fff' : '#a1a1aa', fontWeight: 600, cursor: 'pointer', fontSize: '0.85rem' }}
              >{l}</button>
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end' }}>
          <div style={{ flex: '1 1 180px' }}>
            <label style={LABEL}>Player IGN</label>
            <input type="text" value={playerInput} onChange={(e) => setPlayerInput(e.target.value)} onKeyDown={kk} placeholder="aspas, TenZ, Demon1..." style={INPUT} />
          </div>
          <div style={{ flex: '1 1 160px' }}>
            <label style={LABEL}>{lineLabel}</label>
            <input type="number" step="0.5" value={killLine} onChange={(e) => setKillLine(e.target.value)} onKeyDown={kk} placeholder={comboMaps === 2 ? '30.5' : '45.5'} style={INPUT} />
          </div>
          <div style={{ flex: '0 1 120px' }}>
            <label style={LABEL}>Over Odds</label>
            <input type="number" value={overOdds} onChange={(e) => setOverOdds(e.target.value)} onKeyDown={kk} placeholder="-110" style={INPUT} />
          </div>
          <div style={{ flex: '0 1 120px' }}>
            <label style={LABEL}>Under Odds</label>
            <input type="number" value={underOdds} onChange={(e) => setUnderOdds(e.target.value)} onKeyDown={kk} placeholder="-110" style={INPUT} />
          </div>
          <div style={{ flex: '0 1 120px' }}>
            <label style={LABEL}>Team Odds</label>
            <input type="number" value={teamOdds} onChange={(e) => setTeamOdds(e.target.value)} onKeyDown={kk} placeholder="1.62" style={INPUT} />
          </div>
          <div style={{ flex: '0 1 120px' }}>
            <label style={LABEL}>Opp Odds</label>
            <input type="number" value={oppOdds} onChange={(e) => setOppOdds(e.target.value)} onKeyDown={kk} placeholder="2.30" style={INPUT} />
          </div>
          <button onClick={handleAnalyze} disabled={loading || !playerInput.trim()}
            style={{ ...BTN_PRIMARY, opacity: loading || !playerInput.trim() ? 0.5 : 1, cursor: loading || !playerInput.trim() ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: 6, alignSelf: 'flex-end' }}>
            {loading ? <><Loader2 size={14} className="animate-spin" /> Analyzing</> : 'Analyze PrizePicks Line'}
          </button>
        </div>
      </div>

      {error && <div style={{ color: '#ef4444', padding: '1rem', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', marginBottom: '1rem' }}>✗ {error}</div>}

      {!loading && !result && !error && <div style={{ background: '#0a0a0a', border: '1px solid #27272a', borderRadius: 12 }}><EmptyState /></div>}

      {loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {[80, 120, 200].map((h, i) => <div key={i} style={{ height: h, background: 'linear-gradient(90deg,#1a1a1a 25%,#252525 50%,#1a1a1a 75%)', backgroundSize: '200% 100%', animation: 'shimmer 1.4s infinite' }} />)}
        </div>
      )}

      {!loading && edge && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Performance bar */}
          <div style={{ background: ACCENT_BG, border: `1px solid ${ACCENT_BORDER}`, borderLeft: `3px solid ${ACCENT}`, padding: '0.875rem 1.5rem', display: 'flex', flexWrap: 'wrap', gap: '1.5rem', fontSize: '0.875rem', color: 'rgba(255,255,255,0.5)' }}>
            <span>Player: <span style={{ color: ACCENT, fontFamily: 'var(--font-display)', fontWeight: 700 }}>{edge.player?.ign}</span></span>
            <span>Line: <span style={{ color: ACCENT, fontFamily: 'var(--font-display)', fontWeight: 700 }}>{edge.line} kills ({comboMaps === 2 ? 'Bo3' : 'Bo5'})</span></span>
            <span>Model: <span style={{ color: ACCENT, fontFamily: 'var(--font-display)', fontWeight: 700 }}>{edge.model?.mu?.toFixed(2)} μ</span></span>
            <span style={{ marginLeft: 'auto' }}>Query time: <span style={{ color: ACCENT }}>{result?.elapsed}s</span></span>
          </div>

          <div className="result-grid" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,58%) minmax(0,42%)', gap: '1.5rem' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              <OverUnderDisplay
                overPct={(edge.model?.p_over ?? 0) * 100}
                underPct={(edge.model?.p_under ?? 0) * 100}
                sampleSize={edge.player?.sample_size ?? 0}
                killLine={edge.line ?? 30.5}
              />
              <RecommendationCard
                type={recType}
                ev={recEV}
                confidence={(edge.player?.confidence ?? 'LOW') as 'HIGH' | 'MED' | 'LOW'}
                reason={`Model mean ${edge.model?.mu?.toFixed(1)} vs ${edge.line?.toFixed(1)} kill line. ${recommended !== 'NO BET' ? `Bet ${recommended} — ROI: +${(recommended === 'OVER' ? edge.edge?.roi_over_pct : edge.edge?.roi_under_pct ?? 0).toFixed(1)}%` : 'No positive EV found.'}`}
              />
              <StatsGrid stats={stats} columns={3} />
            </div>
            <div>
              {dist.length > 0 && (
                <DistributionChart
                  data={dist}
                  killLine={edge.line ?? 30.5}
                  modelOverPct={(edge.model?.p_over ?? 0) * 100}
                  marketOverPct={(edge.market?.p_over_vigfree ?? 0) * 100}
                />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Parlay tab ───────────────────────────────────────────────────────────────

function ParlayTab({ prefillLegs }: { prefillLegs: ParlayLeg[] }) {
  const [legs, setLegs] = useState<ParlayLeg[]>(
    prefillLegs.length >= 2 ? prefillLegs : [{ ign: '', line: 30.5, side: 'over' }, { ign: '', line: 30.5, side: 'over' }]
  )
  const [comboMaps, setComboMaps] = useState(2)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ParlayResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Sync if prefill legs arrive later
  if (prefillLegs.length >= 2 && legs.every((l) => l.ign === '')) {
    setLegs(prefillLegs)
  }

  function updateLeg(i: number, field: keyof ParlayLeg, val: string) {
    setLegs((ls) => ls.map((l, idx) => idx === i ? { ...l, [field]: field === 'line' ? parseFloat(val) || l.line : val } : l))
  }
  function addLeg() { if (legs.length >= 6) return; setLegs((ls) => [...ls, { ign: '', line: 30.5, side: 'over' }]) }
  function removeLeg(i: number) { if (legs.length <= 2) return; setLegs((ls) => ls.filter((_, idx) => idx !== i)) }

  async function simulate() {
    const validLegs = legs.filter((l) => l.ign.trim())
    if (validLegs.length < 2) { setError('Need at least 2 complete legs'); return }
    setLoading(true); setError(null); setResult(null)
    try {
      const r = await fetch('/api/prizepicks/parlay', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ legs: validLegs, combo_maps: comboMaps }),
      })
      const d = await r.json()
      if (!r.ok || d.error) throw new Error(d.error || 'Failed')
      setResult(d)
    } catch (e) { setError((e as Error).message) }
    finally { setLoading(false) }
  }

  const hitPct = result?.hit_probability != null ? (result.hit_probability * 100).toFixed(1) : null

  return (
    <div style={{ padding: '1rem', overflowY: 'auto' }}>
      {/* Parlay summary */}
      <div style={{ padding: '0.75rem 0', marginBottom: '1rem', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.12em', color: 'rgba(255,255,255,0.4)', marginBottom: '0.25rem' }}>PARLAY HIT PROBABILITY</div>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '2.5rem', color: hitPct ? getHitColor(parseFloat(hitPct)) : ACCENT }}>
          {hitPct ? `${hitPct}%` : '—'}
        </div>
      </div>

      <h3 style={{ marginBottom: '1rem', color: '#fff', fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '1rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        PrizePicks Parlay Simulator (2–6 legs)
      </h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1rem' }}>
        {legs.map((leg, i) => (
          <div key={i} style={{ display: 'grid', gridTemplateColumns: 'minmax(160px,1fr) 110px 110px auto', gap: '0.75rem', alignItems: 'end' }}>
            <div>
              <label style={LABEL}>Player IGN</label>
              <input type="text" value={leg.ign} onChange={(e) => updateLeg(i, 'ign', e.target.value)} placeholder="aspas" style={{ ...INPUT, width: '100%' }} />
            </div>
            <div>
              <label style={LABEL}>Line</label>
              <input type="number" step="0.5" value={leg.line} onChange={(e) => updateLeg(i, 'line', e.target.value)} style={{ ...INPUT, width: '100%' }} />
            </div>
            <div>
              <label style={LABEL}>Side</label>
              <select value={leg.side} onChange={(e) => updateLeg(i, 'side', e.target.value)} style={{ ...INPUT, width: '100%' }}>
                <option value="over">Over</option>
                <option value="under">Under</option>
              </select>
            </div>
            <button type="button" onClick={() => removeLeg(i)} style={{ padding: '0.875rem 1rem', background: '#3f3f46', color: '#e4e4e7', border: 'none', cursor: 'pointer', alignSelf: 'flex-end' }}>
              Remove
            </button>
          </div>
        ))}
      </div>

      {/* Bo3/Bo5 */}
      <div style={{ marginBottom: '1rem', display: 'inline-flex', background: '#27272a', borderRadius: 8, padding: 2 }}>
        {[{ n: 2, l: 'Bo3' }, { n: 3, l: 'Bo5' }].map(({ n, l }) => (
          <button key={n} type="button" onClick={() => setComboMaps(n)}
            style={{ padding: '0.4rem 0.9rem', border: 'none', borderRadius: 6, background: comboMaps === n ? '#3b82f6' : 'transparent', color: comboMaps === n ? '#fff' : '#a1a1aa', fontWeight: 600, cursor: 'pointer', fontSize: '0.85rem' }}>
            {l}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
        <button type="button" onClick={addLeg} disabled={legs.length >= 6}
          style={{ padding: '0.875rem 1.5rem', background: ACCENT_BG, border: `1px solid ${ACCENT_BORDER}`, color: ACCENT, cursor: legs.length >= 6 ? 'not-allowed' : 'pointer' }}>
          + Add Leg
        </button>
        <button type="button" onClick={simulate} disabled={loading}
          style={{ padding: '0.875rem 1.5rem', background: 'linear-gradient(135deg,#16a34a 0%,#22c55e 100%)', color: '#fff', border: 'none', cursor: loading ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
          {loading ? <><Loader2 size={14} className="animate-spin" /> Simulating...</> : 'Simulate Parlay'}
        </button>
      </div>

      {error && <div style={{ color: '#ef4444', padding: '1rem', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', marginTop: '1rem' }}>{error}</div>}

      {result && !error && (
        <div style={{ marginTop: '1.5rem', background: ACCENT_BG, border: `1px solid ${ACCENT_BORDER}`, borderLeft: `3px solid ${ACCENT}`, padding: '1.5rem' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '1rem', color: '#fff', marginBottom: '1rem', textTransform: 'uppercase' }}>Parlay Results</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: '1rem' }}>
            <div>
              <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'rgba(255,255,255,0.4)', marginBottom: '0.5rem' }}>Hit Probability</div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '3rem', color: hitPct ? getHitColor(parseFloat(hitPct)) : ACCENT }}>
                {hitPct}%
              </div>
            </div>
            {result.expected_value != null && (
              <div>
                <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'rgba(255,255,255,0.4)', marginBottom: '0.5rem' }}>Expected Value</div>
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '3rem', color: result.expected_value > 0 ? '#22c55e' : '#ef4444' }}>
                  {result.expected_value > 0 ? '+' : ''}{result.expected_value.toFixed(4)}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── History tab ──────────────────────────────────────────────────────────────

function HistoryTab() {
  const [snapshots, setSnapshots] = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const r = await fetch('/api/prizepicks/leaderboard/history?limit=50')
      const d = await r.json()
      setSnapshots(d.snapshots || [])
      setLoaded(true)
    } catch { setLoaded(true) }
    finally { setLoading(false) }
  }

  if (!loaded && !loading) load()

  return (
    <div style={{ padding: '1rem', overflowY: 'auto' }}>
      <h3 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '1rem', textTransform: 'uppercase', letterSpacing: '0.06em', color: '#fff', marginBottom: '1rem' }}>
        Leaderboard History
      </h3>
      {loading && <p style={{ color: 'rgba(255,255,255,0.5)', display: 'flex', alignItems: 'center', gap: 6 }}><Loader2 size={14} className="animate-spin" /> Loading...</p>}
      {!loading && snapshots.length === 0 && <p style={{ color: 'rgba(255,255,255,0.25)', fontSize: '0.875rem' }}>No history available.</p>}
      {snapshots.map((s) => (
        <div key={s.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem 1rem', border: '1px solid rgba(255,255,255,0.06)', marginBottom: '0.5rem' }}>
          <div>
            <div style={{ fontWeight: 600, color: '#e4e4e7', fontSize: '0.875rem' }}>{new Date(s.created_at).toLocaleString()}</div>
            <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)' }}>
              {s.player_count} players · {s.source || 'manual'} · {s.snapshot_type || 'vct'}
            </div>
          </div>
          <a
            href={`/api/prizepicks/leaderboard/${s.id}`} target="_blank" rel="noreferrer"
            style={{ fontSize: '0.8rem', color: ACCENT, textDecoration: 'none', padding: '0.35rem 0.7rem', border: `1px solid ${ACCENT}`, fontFamily: 'var(--font-display)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}
          >
            View
          </a>
        </div>
      ))}
    </div>
  )
}

// ─── Main page ─────────────────────────────────────────────────────────────

export default function PrizePicksPage() {
  const [tab, setTab] = useState<Tab>('leaderboard')
  const [parlayLegs, setParlayLegs] = useState<ParlayLeg[]>([])

  function addToParlay(ign: string, line: number) {
    setParlayLegs((ls) => {
      const next = [...ls, { ign, line, side: 'over' as const }]
      return next.slice(0, 6)
    })
  }

  const tabStyle = (t: Tab): React.CSSProperties => ({
    padding: '0.85rem 1.25rem', fontSize: '0.85rem',
    background: 'transparent', border: 'none',
    borderBottom: `3px solid ${tab === t ? ACCENT : 'transparent'}`,
    color: tab === t ? '#fff' : 'rgba(255,255,255,0.55)',
    cursor: 'pointer',
    fontFamily: 'var(--font-display)', fontWeight: 600,
    textTransform: 'uppercase', letterSpacing: '0.06em',
  })

  return (
    <>
      <AppHeader activePage="/prizepicks" />

      <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 56px)' }}>
        {/* Mode tabs */}
        <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid rgba(255,255,255,0.08)', padding: '0 1rem', flexShrink: 0 }}>
          <button style={tabStyle('leaderboard')} onClick={() => setTab('leaderboard')}>LEADERBOARD</button>
          <button style={tabStyle('analyze')} onClick={() => setTab('analyze')}>ANALYZE</button>
          <button style={tabStyle('parlay')} onClick={() => setTab('parlay')}>PARLAY</button>
          <button style={tabStyle('history')} onClick={() => setTab('history')}>HISTORY</button>
        </div>

        {/* Panel */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {tab === 'leaderboard' && (
            <LeaderboardTab
              onAddToParlay={addToParlay}
              onSwitchToParlay={() => setTab('parlay')}
              onSwitchToHistory={() => { setTab('history') }}
            />
          )}
          {tab === 'analyze' && <AnalyzeTab />}
          {tab === 'parlay' && <ParlayTab prefillLegs={parlayLegs} />}
          {tab === 'history' && <HistoryTab />}
        </div>
      </div>

      <style>{`
        @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        @media (max-width: 768px) { .result-grid { grid-template-columns: 1fr !important; } }
      `}</style>
    </>
  )
}
