'use client'

import { useState, useMemo } from 'react'
import { ChevronUp, ChevronDown, ChevronsUpDown, Search } from 'lucide-react'

export interface Column<T> {
  key: keyof T
  label: string
  sortable?: boolean
  align?: 'left' | 'right' | 'center'
  /** Render a kill-rate bar beside the numeric value */
  killRateBar?: boolean
  /** Max numeric value for bar scaling */
  barMax?: number
  render?: (value: T[keyof T], row: T) => React.ReactNode
}

interface DataTableProps<T extends Record<string, unknown>> {
  columns: Column<T>[]
  data: T[]
  filterPlaceholder?: string
  filterKey?: keyof T
  maxHeight?: number
}

type SortDir = 'asc' | 'desc' | null

function SortIcon({ dir }: { dir: SortDir }) {
  if (dir === 'asc') return <ChevronUp size={13} style={{ color: '#3b82f6' }} />
  if (dir === 'desc') return <ChevronDown size={13} style={{ color: '#3b82f6' }} />
  return <ChevronsUpDown size={13} style={{ color: '#3f3f46' }} />
}

export function DataTable<T extends Record<string, unknown>>({
  columns,
  data,
  filterPlaceholder = 'Filter...',
  filterKey,
  maxHeight = 480,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<keyof T | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>(null)
  const [filter, setFilter] = useState('')

  const toggleSort = (key: keyof T) => {
    if (sortKey !== key) {
      setSortKey(key)
      setSortDir('asc')
    } else if (sortDir === 'asc') {
      setSortDir('desc')
    } else {
      setSortKey(null)
      setSortDir(null)
    }
  }

  const processed = useMemo(() => {
    let rows = [...data]
    if (filter && filterKey) {
      const q = filter.toLowerCase()
      rows = rows.filter((r) => String(r[filterKey]).toLowerCase().includes(q))
    }
    if (sortKey && sortDir) {
      rows.sort((a, b) => {
        const av = a[sortKey]
        const bv = b[sortKey]
        const cmp =
          typeof av === 'number' && typeof bv === 'number'
            ? av - bv
            : String(av).localeCompare(String(bv))
        return sortDir === 'asc' ? cmp : -cmp
      })
    }
    return rows
  }, [data, filter, filterKey, sortKey, sortDir])

  return (
    <div
      className="rounded-[12px] border overflow-hidden"
      style={{ background: '#0a0a0a', borderColor: '#27272a' }}
    >
      {/* Filter */}
      {filterKey && (
        <div
          className="flex items-center justify-end gap-2 px-4 py-3 border-b"
          style={{ borderColor: '#27272a' }}
        >
          <div className="relative">
            <Search
              size={13}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
              style={{ color: '#52525b' }}
            />
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder={filterPlaceholder}
              className="h-8 pl-7 pr-3 rounded-[6px] border text-[0.8rem] outline-none transition-colors"
              style={{
                background: '#18181b',
                borderColor: '#3f3f46',
                color: '#ffffff',
                width: '180px',
              }}
              onFocus={(e) => (e.currentTarget.style.borderColor = '#3b82f6')}
              onBlur={(e) => (e.currentTarget.style.borderColor = '#3f3f46')}
            />
          </div>
        </div>
      )}

      {/* Table scroll container */}
      <div style={{ maxHeight, overflowY: 'auto' }}>
        <table className="w-full border-collapse text-sm">
          {/* Sticky header */}
          <thead className="sticky top-0 z-10" style={{ background: '#18181b' }}>
            <tr style={{ borderBottom: '1px solid #27272a' }}>
              {columns.map((col) => (
                <th
                  key={String(col.key)}
                  className={`px-4 py-3 text-[0.65rem] uppercase tracking-[0.05em] font-medium select-none ${
                    col.align === 'right'
                      ? 'text-right'
                      : col.align === 'center'
                        ? 'text-center'
                        : 'text-left'
                  }`}
                  style={{ color: '#a1a1aa', whiteSpace: 'nowrap' }}
                >
                  {col.sortable ? (
                    <button
                      className="flex items-center gap-1 hover:text-white transition-colors"
                      style={{
                        color: sortKey === col.key ? '#ffffff' : '#a1a1aa',
                        marginLeft: col.align === 'right' ? 'auto' : undefined,
                      }}
                      onClick={() => toggleSort(col.key)}
                    >
                      {col.label}
                      <SortIcon dir={sortKey === col.key ? sortDir : null} />
                    </button>
                  ) : (
                    col.label
                  )}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {processed.map((row, ri) => (
              <tr
                key={ri}
                className="transition-colors duration-100"
                style={{
                  background: ri % 2 === 0 ? '#0a0a0a' : '#111113',
                  borderBottom: '1px solid rgba(39,39,42,0.5)',
                }}
                onMouseEnter={(e) => {
                  ;(e.currentTarget as HTMLTableRowElement).style.background = '#18181b'
                }}
                onMouseLeave={(e) => {
                  ;(e.currentTarget as HTMLTableRowElement).style.background =
                    ri % 2 === 0 ? '#0a0a0a' : '#111113'
                }}
              >
                {columns.map((col, ci) => {
                  const val = row[col.key]
                  const displayVal = col.render ? col.render(val, row) : String(val ?? '—')

                  return (
                    <td
                      key={String(col.key)}
                      className={`px-4 py-2.5 tabular-nums ${
                        col.align === 'right'
                          ? 'text-right'
                          : col.align === 'center'
                            ? 'text-center'
                            : 'text-left'
                      }`}
                      style={{
                        color: ci === 0 ? '#ffffff' : '#a1a1aa',
                        fontWeight: ci === 0 ? 600 : 400,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {col.killRateBar && typeof val === 'number' ? (
                        <div className="flex items-center gap-2 justify-end">
                          <span>{displayVal}</span>
                          <div
                            className="rounded-full overflow-hidden"
                            style={{ width: 80, height: 4, background: '#27272a' }}
                          >
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${Math.min(100, (val / (col.barMax ?? 30)) * 100)}%`,
                                background: '#22c55e',
                              }}
                            />
                          </div>
                        </div>
                      ) : (
                        displayVal
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}

            {processed.length === 0 && (
              <tr>
                <td
                  colSpan={columns.length}
                  className="text-center py-10 text-sm"
                  style={{ color: '#52525b' }}
                >
                  No data
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
