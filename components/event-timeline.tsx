import { KillChips } from './kill-chips'

export interface EventDetail {
  event_name: string
  map_kills: number[]
  event_over: number
  event_under: number
  event_maps: number
  cached: boolean
  kpr?: number
  rounds?: number
  is_recent?: boolean
}

interface EventTimelineProps {
  events: EventDetail[]
  line: number
}

export function EventTimeline({ events, line }: EventTimelineProps) {
  return (
    <div className="flex flex-col gap-1.5">
      {events.map((ev, i) => {
        const ou =
          ev.event_maps > 0
            ? `O:${ev.event_over}/${ev.event_maps} U:${ev.event_under}/${ev.event_maps}`
            : ''
        return (
          <div
            key={i}
            className={
              'flex items-start gap-3 py-2.5 pl-4 ml-1 border-l-2 flex-wrap ' +
              (ev.cached
                ? 'border-l-[rgba(34,197,94,0.25)]'
                : 'border-l-[rgba(245,158,11,0.35)]')
            }
          >
            {/* Timeline dot */}
            <div
              className={
                'w-2 h-2 rounded-full shrink-0 mt-1 ' +
                (ev.cached ? 'bg-[#22c55e]' : 'bg-[#f59e0b]')
              }
              style={{ marginLeft: -19 }}
            />

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-[#e4e4e7] text-sm">{ev.event_name}</span>
                {ou && <span className="text-xs text-white/40">{ou}</span>}
                <span
                  className={
                    'text-[0.65rem] px-1.5 py-0.5 font-bold uppercase tracking-widest border ' +
                    (ev.cached
                      ? 'bg-[rgba(34,197,94,0.15)] text-[#22c55e] border-[rgba(34,197,94,0.3)]'
                      : 'bg-[rgba(245,158,11,0.15)] text-[#f59e0b] border-[rgba(245,158,11,0.3)]')
                  }
                >
                  {ev.cached ? 'CACHED' : 'LIVE'}
                </span>
                {ev.is_recent && (
                  <span className="text-[0.65rem] px-1.5 py-0.5 font-bold uppercase tracking-widest bg-[rgba(240,224,64,0.15)] text-[#F0E040] border border-[rgba(240,224,64,0.3)]">
                    RECENT
                  </span>
                )}
              </div>
              {ev.map_kills && ev.map_kills.length > 0 && (
                <KillChips kills={ev.map_kills} line={line} />
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
