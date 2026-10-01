import { useMemo, useRef, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  Clock3,
  GripVertical,
  MapPin,
} from 'lucide-react'

type CalendarEvent = {
  id: string
  day: number
  startHour: number
  duration: number
  title: string
  type: string
}

type DragState = {
  id: string
  mode: 'move' | 'resize'
  startX: number
  startY: number
  originalDay: number
  originalStartHour: number
  originalDuration: number
}

const HOUR_HEIGHT = 80
const HALF_HOUR_HEIGHT = HOUR_HEIGHT / 2
const DAY_WIDTH = 184

const START_HOUR = 13
const MIN_DURATION = 0.5
const MAX_DURATION = 8

function formatHour(hour: number) {
  const totalMinutes = Math.round(hour * 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60

  const suffix = hours >= 12 ? 'PM' : 'AM'
  const displayHour = hours % 12 || 12

  return `${displayHour}:${minutes
    .toString()
    .padStart(2, '0')} ${suffix}`
}

function formatTimeRange(startHour: number, duration: number) {
  return `${formatHour(startHour)} – ${formatHour(
    startHour + duration,
  )}`
}

function snapToHalfHour(value: number) {
  return Math.round(value * 2) / 2
}

export function CalendarBoardRefactored({
  when,
}: {
  when: string
}) {
  const [offset, setOffset] = useState(0)

  const [events, setEvents] = useState<CalendarEvent[]>([
    {
      id: 'xuan-huong',
      day: 0,
      startHour: 14,
      duration: 1,
      title: 'Xuan Huong Lake',
      type: 'Nature',
    },
    {
      id: 'yersin-park',
      day: 1,
      startHour: 16,
      duration: 1,
      title: 'Yersin Park',
      type: 'Sightseeing',
    },
    {
      id: 'night-market',
      day: 2,
      startHour: 18,
      duration: 1.5,
      title: 'Da Lat Night Market',
      type: 'Food & Shopping',
    },
  ])

  const [dragState, setDragState] =
    useState<DragState | null>(null)

  const calendarRef = useRef<HTMLDivElement | null>(null)

  const times = [
    '1 PM',
    '2 PM',
    '3 PM',
    '4 PM',
    '5 PM',
    '6 PM',
    '7 PM',
    '8 PM',
  ]

  const days = [0, 1, 2, 3]

  const visibleEvents = useMemo(() => {
    return events
  }, [events])

  const getEvent = (id: string) => {
    return events.find((event) => event.id === id)
  }

  const handlePointerDown = (
    event: React.PointerEvent,
    calendarEvent: CalendarEvent,
    mode: 'move' | 'resize',
  ) => {
    event.preventDefault()
    event.stopPropagation()

    setDragState({
      id: calendarEvent.id,
      mode,
      startX: event.clientX,
      startY: event.clientY,
      originalDay: calendarEvent.day,
      originalStartHour: calendarEvent.startHour,
      originalDuration: calendarEvent.duration,
    })

    document.body.style.userSelect = 'none'
  }

  const handlePointerMove = (
    event: React.PointerEvent,
  ) => {
    if (!dragState || !calendarRef.current) return

    const currentEvent = getEvent(dragState.id)

    if (!currentEvent) return

    const deltaX = event.clientX - dragState.startX
    const deltaY = event.clientY - dragState.startY

    if (dragState.mode === 'move') {
      const dayDelta = Math.round(deltaX / DAY_WIDTH)

      const hourDelta = snapToHalfHour(
        deltaY / HOUR_HEIGHT,
      )

      const newDay = Math.min(
        3,
        Math.max(
          0,
          dragState.originalDay + dayDelta,
        ),
      )

      const newStartHour = Math.min(
        20 - dragState.originalDuration,
        Math.max(
          START_HOUR,
          dragState.originalStartHour + hourDelta,
        ),
      )

      setEvents((current) =>
        current.map((item) =>
          item.id === dragState.id
            ? {
                ...item,
                day: newDay,
                startHour: newStartHour,
              }
            : item,
        ),
      )
    }

    if (dragState.mode === 'resize') {
      const durationDelta = snapToHalfHour(
        deltaY / HOUR_HEIGHT,
      )

      const maxDuration = Math.min(
        MAX_DURATION,
        20 - dragState.originalStartHour,
      )

      const newDuration = Math.min(
        maxDuration,
        Math.max(
          MIN_DURATION,
          dragState.originalDuration +
            durationDelta,
        ),
      )

      setEvents((current) =>
        current.map((item) =>
          item.id === dragState.id
            ? {
                ...item,
                duration: newDuration,
              }
            : item,
        ),
      )
    }
  }

  const handlePointerUp = () => {
    if (!dragState) return

    setDragState(null)
    document.body.style.userSelect = ''
  }

  const getEventStyle = (
    event: CalendarEvent,
  ) => {
    const top =
      (event.startHour - START_HOUR) *
      HOUR_HEIGHT

    const height =
      event.duration * HOUR_HEIGHT - 12

    return {
      top,
      height: Math.max(height, 32),
    }
  }

  return (
    <section className="w-full">
      {/* Header */}
      <header className="mb-6 flex items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-2xl font-semibold tracking-tight text-neutral-900">
              Calendar
            </h2>

            <span className="rounded-full bg-neutral-100 px-2.5 py-1 text-xs font-medium text-neutral-600">
              4 days
            </span>
          </div>

          <p className="mt-1.5 text-sm text-neutral-500">
            {when}
          </p>
        </div>

        {/* Navigation */}
        <div className="flex items-center gap-1.5 rounded-xl border border-neutral-200 bg-white p-1 shadow-sm">
          <button
            type="button"
            aria-label="Previous calendar days"
            disabled={offset === 0}
            onClick={() =>
              setOffset((value) =>
                Math.max(0, value - 4),
              )
            }
            className="flex h-8 w-8 items-center justify-center rounded-lg text-neutral-600 transition hover:bg-neutral-100 hover:text-neutral-900 disabled:cursor-not-allowed disabled:opacity-30"
          >
            <ChevronLeft
              size={17}
              strokeWidth={1.8}
            />
          </button>

          <button
            type="button"
            aria-label="Next calendar days"
            onClick={() =>
              setOffset((value) => value + 4)
            }
            className="flex h-8 w-8 items-center justify-center rounded-lg text-neutral-600 transition hover:bg-neutral-100 hover:text-neutral-900"
          >
            <ChevronRight
              size={17}
              strokeWidth={1.8}
            />
          </button>
        </div>
      </header>

      {/* Calendar */}
      <div className="overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
        <div className="overflow-x-auto">
          <div
            ref={calendarRef}
            className="min-w-[820px]"
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
            onPointerLeave={(event) => {
              if (
                dragState &&
                event.buttons === 0
              ) {
                handlePointerUp()
              }
            }}
          >
            {/* Day Header */}
            <div className="grid grid-cols-[82px_repeat(4,minmax(184px,1fr))]">
              {/* Time column */}
              <div className="border-b border-r border-neutral-200 bg-neutral-50/80 p-4">
                <span className="text-[11px] font-medium uppercase tracking-wider text-neutral-400">
                  Time
                </span>
              </div>

              {days.map((day) => (
                <div
                  key={day}
                  className="border-b border-r border-neutral-200 bg-white p-4"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-sm font-semibold text-neutral-900">
                        Day {day + 1 + offset}
                      </p>

                      <p className="mt-0.5 text-xs text-neutral-500">
                        December {12 + day + offset}
                      </p>
                    </div>

                    {day === 0 &&
                      offset === 0 && (
                        <span className="rounded-full bg-neutral-900 px-2 py-0.5 text-[10px] font-medium text-white">
                          Start
                        </span>
                      )}
                  </div>

                  {/* Hotel */}
                  <div className="mt-3 flex items-center gap-2 rounded-lg border border-sky-100 bg-sky-50 px-2.5 py-2">
                    <MapPin
                      size={13}
                      className="shrink-0 text-sky-600"
                      strokeWidth={2}
                    />

                    <span className="truncate text-xs font-medium text-sky-900">
                      D House Dalat
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* Timeline */}
            <div className="relative">
              {/* Grid */}
              <div className="grid grid-cols-[82px_repeat(4,minmax(184px,1fr))]">
                {times.map((time) => (
                  <div
                    key={time}
                    className="contents"
                  >
                    {/* Time */}
                    <div className="h-20 border-b border-r border-neutral-200 bg-neutral-50/40 px-3 py-3 text-right">
                      <span className="text-[11px] font-medium text-neutral-400">
                        {time}
                      </span>
                    </div>

                    {/* Empty calendar cells */}
                    {days.map((day) => (
                      <div
                        key={`${time}-${day}`}
                        className="h-20 border-b border-r border-neutral-200 bg-white transition hover:bg-neutral-50/60"
                      />
                    ))}
                  </div>
                ))}
              </div>

              {/* Events */}
              <div className="pointer-events-none absolute inset-0">
                {visibleEvents.map((event) => {
                  const style =
                    getEventStyle(event)

                  const left =
                    82 +
                    event.day * DAY_WIDTH +
                    6

                  const width =
                    DAY_WIDTH - 12

                  const isDragging =
                    dragState?.id === event.id

                  return (
                    <div
                      key={event.id}
                      className="pointer-events-auto absolute"
                      style={{
                        top: style.top + 6,
                        left,
                        width,
                        height: style.height,
                        zIndex: isDragging ? 20 : 10,
                      }}
                    >
                      {/* Event */}
                      <div
                        onPointerDown={(e) =>
                          handlePointerDown(
                            e,
                            event,
                            'move',
                          )
                        }
                        className={`group relative h-full cursor-grab overflow-hidden rounded-xl border bg-emerald-50/95 p-2.5 shadow-sm transition ${
                          isDragging
                            ? 'scale-[1.02] border-emerald-300 shadow-lg'
                            : 'border-emerald-100 hover:border-emerald-200 hover:shadow-md'
                        } active:cursor-grabbing`}
                      >
                        {/* Drag indicator */}
                        <div className="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 transition group-hover:opacity-40">
                          <GripVertical
                            size={14}
                            className="text-emerald-700"
                          />
                        </div>

                        <div className="flex items-start gap-2">
                          <div className="mt-1 h-2 w-2 shrink-0 rounded-full bg-emerald-500" />

                          <div className="min-w-0 flex-1">
                            <p className="truncate text-xs font-semibold text-emerald-950">
                              {event.title}
                            </p>

                            <div className="mt-1 flex items-center gap-1 text-[10px] text-emerald-700">
                              <Clock3
                                size={10}
                                strokeWidth={2}
                              />

                              <span>
                                {formatTimeRange(
                                  event.startHour,
                                  event.duration,
                                )}
                              </span>
                            </div>

                            {event.duration >=
                              1.5 && (
                              <p className="mt-1.5 truncate text-[10px] text-emerald-600">
                                {event.type}
                              </p>
                            )}
                          </div>
                        </div>

                        {/* Resize handle */}
                        <div
                          onPointerDown={(e) =>
                            handlePointerDown(
                              e,
                              event,
                              'resize',
                            )
                          }
                          className="absolute bottom-0 left-0 right-0 flex h-3 cursor-ns-resize items-end justify-center opacity-0 transition group-hover:opacity-100"
                        >
                          <div className="mb-1 h-1 w-8 rounded-full bg-emerald-400" />
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Helper */}
      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-neutral-500">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
          <span>Activity</span>
        </div>

        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-sky-500" />
          <span>Stay</span>
        </div>

        <span className="text-neutral-400">
          Drag to move · Drag bottom edge to resize
        </span>
      </div>
    </section>
  )
}