'use client'

import { useEffect, useState, useCallback } from 'react'
import { X, Search, AlertCircle } from 'lucide-react'

/* ════════════════════════════════════════════════════════
   TOAST SYSTEM
   ════════════════════════════════════════════════════════ */
export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface ToastItem {
  id: string
  type: ToastType
  title: string
  message?: string
}

const TOAST_STYLES: Record<ToastType, { border: string; color: string; titleColor: string }> = {
  success: { border: '#22c55e', color: 'rgba(34,197,94,0.08)', titleColor: '#22c55e' },
  error: { border: '#ef4444', color: 'rgba(239,68,68,0.08)', titleColor: '#ef4444' },
  warning: { border: '#f59e0b', color: 'rgba(245,158,11,0.08)', titleColor: '#f59e0b' },
  info: { border: '#3b82f6', color: 'rgba(59,130,246,0.08)', titleColor: '#3b82f6' },
}

function ToastItem({ toast, onDismiss }: { toast: ToastItem; onDismiss: (id: string) => void }) {
  const [progress, setProgress] = useState(100)
  const style = TOAST_STYLES[toast.type]

  useEffect(() => {
    const start = Date.now()
    const duration = 4000
    const interval = setInterval(() => {
      const elapsed = Date.now() - start
      setProgress(Math.max(0, 100 - (elapsed / duration) * 100))
    }, 16)
    const timeout = setTimeout(() => onDismiss(toast.id), duration)
    return () => {
      clearInterval(interval)
      clearTimeout(timeout)
    }
  }, [toast.id, onDismiss])

  return (
    <div
      className="relative rounded-[10px] border overflow-hidden shadow-lg"
      style={{
        background: '#0a0a0a',
        borderColor: '#27272a',
        borderLeft: `4px solid ${style.border}`,
        minWidth: 280,
        maxWidth: 360,
        animation: 'slideInRight 0.2s ease-out',
      }}
    >
      <div className="flex items-start gap-3 px-4 py-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold" style={{ color: style.titleColor }}>
            {toast.title}
          </p>
          {toast.message && (
            <p className="text-[0.8rem] mt-0.5" style={{ color: '#a1a1aa' }}>
              {toast.message}
            </p>
          )}
        </div>
        <button
          onClick={() => onDismiss(toast.id)}
          className="shrink-0 mt-0.5 transition-colors"
          style={{ color: '#52525b' }}
          onMouseEnter={(e) => ((e.currentTarget as HTMLButtonElement).style.color = '#a1a1aa')}
          onMouseLeave={(e) => ((e.currentTarget as HTMLButtonElement).style.color = '#52525b')}
          aria-label="Dismiss notification"
        >
          <X size={14} />
        </button>
      </div>
      {/* Progress bar */}
      <div style={{ height: 2, background: 'rgba(255,255,255,0.06)' }}>
        <div
          style={{
            height: '100%',
            width: `${progress}%`,
            background: style.border,
            transition: 'width 16ms linear',
          }}
        />
      </div>
    </div>
  )
}

export function ToastProvider({ toasts, onDismiss }: { toasts: ToastItem[]; onDismiss: (id: string) => void }) {
  return (
    <div
      className="fixed bottom-5 right-5 z-[9999] flex flex-col gap-2 items-end"
      role="region"
      aria-label="Notifications"
      aria-live="polite"
    >
      {toasts.slice(-3).map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
      <style>{`
        @keyframes slideInRight {
          from { opacity: 0; transform: translateX(24px); }
          to   { opacity: 1; transform: translateX(0); }
        }
      `}</style>
    </div>
  )
}

/** Hook to manage toasts */
export function useToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const toast = useCallback((type: ToastType, title: string, message?: string) => {
    const id = Math.random().toString(36).slice(2)
    setToasts((prev) => [...prev, { id, type, title, message }])
  }, [])

  return { toasts, dismiss, toast }
}

/* ════════════════════════════════════════════════════════
   SKELETON LOADERS
   ════════════════════════════════════════════════════════ */
function Shimmer({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return <div className={`skeleton-shimmer ${className ?? ''}`} style={style} />
}

/** Skeleton for the OverUnderDisplay */
export function SkeletonOverUnder() {
  return (
    <div
      className="rounded-[16px] border overflow-hidden"
      style={{ background: '#0a0a0a', borderColor: '#27272a' }}
    >
      <div className="flex">
        <div className="flex-1 flex flex-col items-center py-8 px-6 gap-3">
          <Shimmer style={{ width: 100, height: 56, borderRadius: 8 }} />
          <Shimmer style={{ width: 50, height: 12, borderRadius: 4 }} />
          <Shimmer style={{ width: 70, height: 10, borderRadius: 4 }} />
        </div>
        <div className="w-px" style={{ background: '#27272a' }} />
        <div className="flex-1 flex flex-col items-center py-8 px-6 gap-3">
          <Shimmer style={{ width: 100, height: 56, borderRadius: 8 }} />
          <Shimmer style={{ width: 50, height: 12, borderRadius: 4 }} />
          <Shimmer style={{ width: 70, height: 10, borderRadius: 4 }} />
        </div>
      </div>
      <div className="px-6 py-4 border-t" style={{ borderColor: '#27272a' }}>
        <Shimmer style={{ width: '100%', height: 6, borderRadius: 99 }} />
      </div>
    </div>
  )
}

/** Skeleton for StatsGrid */
export function SkeletonStatsGrid({ count = 6, columns = 3 }: { count?: number; columns?: number }) {
  return (
    <div
      className="grid gap-3"
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
    >
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="rounded-[10px] border p-4 flex flex-col gap-2"
          style={{ background: '#0a0a0a', borderColor: '#27272a' }}
        >
          <Shimmer style={{ width: '60%', height: 10, borderRadius: 4 }} />
          <Shimmer style={{ width: '45%', height: 28, borderRadius: 6 }} />
          <Shimmer style={{ width: '55%', height: 10, borderRadius: 4 }} />
        </div>
      ))}
    </div>
  )
}

/** Skeleton for DataTable */
export function SkeletonTable({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  const widths = ['40%', '15%', '15%', '15%', '15%']
  return (
    <div
      className="rounded-[12px] border overflow-hidden"
      style={{ background: '#0a0a0a', borderColor: '#27272a' }}
    >
      {/* Header */}
      <div
        className="flex gap-4 px-4 py-3 border-b"
        style={{ borderColor: '#27272a', background: '#18181b' }}
      >
        {Array.from({ length: cols }).map((_, i) => (
          <Shimmer key={i} style={{ height: 10, borderRadius: 4, flex: i === 0 ? 2 : 1 }} />
        ))}
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, ri) => (
        <div
          key={ri}
          className="flex gap-4 items-center px-4 py-3 border-b last:border-b-0"
          style={{ borderColor: 'rgba(39,39,42,0.4)', background: ri % 2 === 0 ? '#0a0a0a' : '#111113' }}
        >
          {Array.from({ length: cols }).map((_, ci) => (
            <Shimmer
              key={ci}
              style={{
                height: 12,
                borderRadius: 4,
                flex: ci === 0 ? 2 : 1,
                width: widths[ci] ?? '15%',
              }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

/** Skeleton for EventCards */
export function SkeletonEventCards({ count = 3 }: { count?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="rounded-[12px] border flex items-center gap-3 px-4 py-3.5"
          style={{ background: '#0a0a0a', borderColor: '#27272a' }}
        >
          <Shimmer style={{ width: 14, height: 14, borderRadius: 4 }} />
          <Shimmer style={{ flex: 1, height: 14, borderRadius: 4, maxWidth: 220 }} />
          <Shimmer style={{ width: 80, height: 12, borderRadius: 4 }} />
          <Shimmer style={{ width: 40, height: 20, borderRadius: 4, marginLeft: 'auto' }} />
        </div>
      ))}
    </div>
  )
}

/* ════════════════════════════════════════════════════════
   EMPTY STATE
   ════════════════════════════════════════════════════════ */
export function EmptyState({
  title = 'Search for a player to begin',
  subtitle = 'Enter a player IGN and kill line above to see over/under analytics',
}: {
  title?: string
  subtitle?: string
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div
        className="w-14 h-14 rounded-[12px] flex items-center justify-center mb-5"
        style={{ background: '#18181b', border: '1px solid #27272a' }}
      >
        <Search size={24} style={{ color: '#3f3f46' }} />
      </div>
      <h3
        className="font-semibold mb-2"
        style={{ fontSize: '1.125rem', color: '#a1a1aa' }}
      >
        {title}
      </h3>
      <p className="text-sm max-w-xs" style={{ color: '#52525b' }}>
        {subtitle}
      </p>
    </div>
  )
}

/* ════════════════════════════════════════════════════════
   ERROR STATE
   ════════════════════════════════════════════════════════ */
export function ErrorState({
  message = 'Something went wrong',
  onRetry,
}: {
  message?: string
  onRetry?: () => void
}) {
  return (
    <div
      className="rounded-[12px] border p-6 flex flex-col items-center text-center gap-4"
      style={{
        background: 'rgba(239,68,68,0.05)',
        borderColor: 'rgba(239,68,68,0.3)',
      }}
    >
      <div
        className="w-11 h-11 rounded-full flex items-center justify-center"
        style={{ background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.25)' }}
      >
        <AlertCircle size={20} style={{ color: '#ef4444' }} />
      </div>
      <div>
        <p className="font-semibold text-sm" style={{ color: '#ef4444' }}>
          Error
        </p>
        <p className="text-sm mt-1" style={{ color: '#a1a1aa' }}>
          {message}
        </p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-sm font-medium px-4 py-2 rounded-[6px] border transition-colors"
          style={{
            background: 'transparent',
            borderColor: '#3f3f46',
            color: '#a1a1aa',
          }}
          onMouseEnter={(e) => {
            const el = e.currentTarget as HTMLButtonElement
            el.style.borderColor = '#71717a'
            el.style.color = '#ffffff'
          }}
          onMouseLeave={(e) => {
            const el = e.currentTarget as HTMLButtonElement
            el.style.borderColor = '#3f3f46'
            el.style.color = '#a1a1aa'
          }}
        >
          Try Again
        </button>
      )}
    </div>
  )
}
