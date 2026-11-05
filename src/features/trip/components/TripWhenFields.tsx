import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  X,
} from 'lucide-react'
import { actionClass, closeClass } from './tripFieldModalTypes'

type Props = {
  when: string
  onClose: () => void
  onSave: (when: string) => void
}

function formatDate(year: number, month: number, day: number) {
  return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

export function TripWhenFields({
  when,
  onClose,
  onSave,
}: Props) {
  const [today] = useState(() => new Date())
  const savedDates = when.match(/\d{4}-\d{2}-\d{2}/g) ?? []

  const [tab, setTab] = useState<'dates' | 'flexible'>(
    /\d+ days/.test(when) ? 'flexible' : 'dates',
  )

  const [month, setMonth] = useState(
    () =>
      savedDates.length ? new Date(`${savedDates[0]}T12:00:00`) : new Date(
        today.getFullYear(),
        today.getMonth(),
        1,
      ),
  )

  const [dates, setDates] = useState<string[]>(() => savedDates.slice(0, 2).sort())
  const [days, setDays] = useState(() => Number(when.match(/^(\d+) days/)?.[1]) || 5)

  const [monthOffset, setMonthOffset] = useState(0)
  const [months, setMonths] = useState<string[]>(() => /\d+ days, /.test(when) ? when.split(' days, ')[1].split(', ').filter((name) => name !== 'Anytime') : [])

  const [showDatePicker, setShowDatePicker] =
    useState(false)

  const datePickerRef = useRef<HTMLDivElement>(null)

  const monthNames = useMemo(
    () => [
      'January',
      'February',
      'March',
      'April',
      'May',
      'June',
      'July',
      'August',
      'September',
      'October',
      'November',
      'December',
    ],
    [],
  )

  const flexibleMonths = useMemo(() => {
    return Array.from({ length: 6 }, (_, index) => {
      const date = new Date(
        today.getFullYear(),
        today.getMonth() + monthOffset + index,
        1,
      )

      return date.toLocaleDateString('en-US', {
        month: 'long',
      })
    })
  }, [monthOffset, today])

  const years = useMemo(() => {
    const startYear = today.getFullYear() - 5
    const endYear = today.getFullYear() + 15

    return Array.from(
      { length: endYear - startYear + 1 },
      (_, index) => startYear + index,
    )
  }, [today])

  const label =
    tab === 'flexible'
      ? `${days} days, ${months.length ? months.join(', ') : 'Anytime'}`
      : dates.length >= 2
      ? `${dates[0]} – ${dates.at(-1)}`
      : dates.length === 1
        ? dates[0]
        : months.length
          ? `${days} days, ${months.join(', ')}`
          : when || 'Dates flexible'

  /*
   * Close month/year picker when clicking outside.
   */
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        datePickerRef.current &&
        !datePickerRef.current.contains(
          event.target as Node,
        )
      ) {
        setShowDatePicker(false)
      }
    }

    if (showDatePicker) {
      document.addEventListener(
        'mousedown',
        handleClickOutside,
      )
    }

    return () => {
      document.removeEventListener(
        'mousedown',
        handleClickOutside,
      )
    }
  }, [showDatePicker])

  function toggleDate(value: string) {
    setDates((current) => !current.length || current.length === 2
      ? [value]
      : [current[0], value].sort())
  }

  function previousMonth() {
    setMonth(
      (current) =>
        new Date(
          current.getFullYear(),
          current.getMonth() - 1,
          1,
        ),
    )
  }

  function nextMonth() {
    setMonth(
      (current) =>
        new Date(
          current.getFullYear(),
          current.getMonth() + 1,
          1,
        ),
    )
  }

  function selectMonth(monthIndex: number) {
    setMonth(
      (current) =>
        new Date(
          current.getFullYear(),
          monthIndex,
          1,
        ),
    )
  }

  function selectYear(year: number) {
    setMonth(
      (current) =>
        new Date(
          year,
          current.getMonth(),
          1,
        ),
    )
  }

  function renderCalendar(offset: number) {
    const visibleMonth = new Date(month.getFullYear(), month.getMonth() + offset, 1)
    const year = visibleMonth.getFullYear()
    const monthIndex = visibleMonth.getMonth()

    const firstDay = new Date(
      year,
      monthIndex,
      1,
    ).getDay()

    const leadingDays = firstDay

    const daysInMonth = new Date(
      year,
      monthIndex + 1,
      0,
    ).getDate()

    return (
      <div className="w-full">
        {/* Calendar header */}
        <div className="relative mb-7 flex items-center justify-between">
          {/* Previous month */}
          <button
            type="button"
            onClick={previousMonth}
            aria-label="Previous month"
            className={`${offset === 1 ? 'invisible' : ''} grid h-9 w-9 shrink-0 place-items-center rounded-full text-neutral-400 transition hover:bg-neutral-100 hover:text-neutral-900`}
          >
            <ChevronLeft
              size={22}
              strokeWidth={1.8}
            />
          </button>

          {/* Month + Year */}
          {offset === 1 ? <h3 className="py-2 text-center text-[17px] font-semibold text-neutral-900">{visibleMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</h3> : <div
            ref={datePickerRef}
            className="relative"
          >
            <button
              type="button"
              onClick={() =>
                setShowDatePicker(
                  (value) => !value,
                )
              }
              className="group flex items-center gap-1.5 rounded-xl px-3 py-2 text-[17px] font-semibold text-neutral-900 transition hover:bg-neutral-100"
              aria-expanded={showDatePicker}
              aria-label="Select month and year"
            >
              <span>
                {month.toLocaleDateString(
                  'en-US',
                  {
                    month: 'long',
                  },
                )}
              </span>

              <span>
                {month.getFullYear()}
              </span>

              {/* Chevron only appears on hover */}
              <ChevronDown
                size={16}
                strokeWidth={2}
                className={`ml-0.5 opacity-0 transition-all duration-150 group-hover:opacity-100 ${
                  showDatePicker
                    ? 'rotate-180 opacity-100'
                    : ''
                }`}
              />
            </button>

            {/* Month / Year picker */}
            {showDatePicker && (
              <div className="absolute left-1/2 top-[52px] z-50 w-[min(390px,calc(100vw-64px))] -translate-x-1/2 rounded-2xl border border-neutral-200 bg-white p-4 shadow-xl">
                {/* Close */}
                <div className="mb-3 flex justify-end">
                  <button
                    type="button"
                    onClick={() =>
                      setShowDatePicker(false)
                    }
                    aria-label="Close month and year picker"
                    className="grid h-8 w-8 place-items-center rounded-full text-neutral-500 transition hover:bg-neutral-100 hover:text-neutral-900"
                  >
                    <X
                      size={17}
                      strokeWidth={1.8}
                    />
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  {/* Months */}
                  <div>
                    <div className="mb-2 px-2 text-xs font-medium text-neutral-400">
                      Month
                    </div>

                    <div className="h-[250px] overflow-y-auto rounded-xl bg-neutral-50 p-1">
                      {monthNames.map(
                        (name, index) => {
                          const selected =
                            month.getMonth() ===
                            index

                          return (
                            <button
                              type="button"
                              key={name}
                              onClick={() =>
                                selectMonth(
                                  index,
                                )
                              }
                              className={`w-full rounded-lg px-3 py-2.5 text-left text-sm transition ${
                                selected
                                  ? 'bg-black font-medium text-white'
                                  : 'text-neutral-800 hover:bg-white'
                              }`}
                            >
                              {name}
                            </button>
                          )
                        },
                      )}
                    </div>
                  </div>

                  {/* Years */}
                  <div>
                    <div className="mb-2 px-2 text-xs font-medium text-neutral-400">
                      Year
                    </div>

                    <div className="h-[250px] overflow-y-auto rounded-xl bg-neutral-50 p-1">
                      {years.map((year) => {
                        const selected =
                          month.getFullYear() ===
                          year

                        return (
                          <button
                            type="button"
                            key={year}
                            onClick={() =>
                              selectYear(
                                year,
                              )
                            }
                            className={`w-full rounded-lg px-3 py-2.5 text-left text-sm transition ${
                              selected
                                ? 'bg-black font-medium text-white'
                                : 'text-neutral-800 hover:bg-white'
                            }`}
                          >
                            {year}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>}

          {/* Next month */}
          <button
            type="button"
            onClick={nextMonth}
            aria-label="Next month"
            className={`${offset === 0 ? 'invisible' : ''} grid h-9 w-9 shrink-0 place-items-center rounded-full text-neutral-900 transition hover:bg-neutral-100`}
          >
            <ChevronRight
              size={22}
              strokeWidth={1.8}
            />
          </button>
        </div>

        {/* Weekdays */}
        <div className="grid grid-cols-7 text-center">
          {[
            'CN',
            'T2',
            'T3',
            'T4',
            'T5',
            'T6',
            'T7',
          ].map((day, index) => (
            <span
              key={`${day}-${index}`}
              className="pb-4 text-[13px] font-medium text-neutral-400"
            >
              {day}
            </span>
          ))}

          {/* Empty cells */}
          {Array.from(
            { length: leadingDays },
            (_, index) => (
              <span
                key={`empty-${index}`}
              />
            ),
          )}

          {/* Calendar days */}
          {Array.from(
            { length: daysInMonth },
            (_, index) => {
              const day = index + 1

              const value = formatDate(
                year,
                monthIndex,
                day,
              )

              const selected = dates.includes(value)
              const inRange = dates.length === 2 && value > dates[0] && value < dates[1]
              const past = value < formatDate(today.getFullYear(), today.getMonth(), today.getDate())

              return (
                <button
                  type="button"
                  key={value}
                  disabled={past}
                  aria-label={new Date(year, monthIndex, day).toLocaleDateString('en-US', { dateStyle: 'full' })}
                  aria-pressed={selected || inRange}
                  onClick={() =>
                    toggleDate(value)
                  }
                  className={`mb-2 grid h-10 w-full place-items-center text-sm transition disabled:cursor-not-allowed disabled:opacity-30 ${
                    selected
                      ? 'rounded-full bg-black text-white'
                      : inRange ? 'bg-neutral-200 text-neutral-900 enabled:hover:bg-neutral-300' : 'rounded-full text-neutral-900 enabled:hover:bg-neutral-100'
                  }`}
                >
                  {day}
                </button>
              )
            },
          )}
        </div>
      </div>
    )
  }

  function nextFlexibleMonths() {
    setMonthOffset(
      (current) => current + 6,
    )
  }

  function previousFlexibleMonths() {
    setMonthOffset((current) =>
      Math.max(0, current - 6),
    )
  }

  return (
      <div className="relative flex min-h-[640px] flex-col">
        {/* Header */}
        <div className="relative flex items-center justify-center">
          <button
            onClick={onClose}
            className={`absolute left-0 ${closeClass}`}
            aria-label="Close"
          >
            ×
          </button>

          <h2 className="text-[22px] font-semibold text-neutral-900">
            When
          </h2>
        </div>


      {/* Tabs */}
      <div className="flex justify-center py-6 border-b border-neutral-200 pb-[18px]">
        <div className="flex rounded-full bg-neutral-100 p-1">
          <button
            type="button"
            onClick={() =>
              setTab('dates')
            }
            className={`min-w-[78px] rounded-full px-4 text-sm font-medium transition ${
              tab === 'dates'
                ? 'bg-white text-neutral-900 shadow-sm'
                : 'text-neutral-900'
            }`}
          >
            Dates
          </button>

          <button
            type="button"
            onClick={() =>
              setTab('flexible')
            }
            className={`min-w-[78px] rounded-full px-4  text-sm font-medium transition ${
              tab === 'flexible'
                ? 'bg-white text-neutral-900 shadow-sm'
                : 'text-neutral-900'
            }`}
          >
            Flexible
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1">
        {tab === 'dates' ? (
          <div className="mx-auto w-full px-2 pt-5">
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 sm:gap-10">
              {renderCalendar(0)}
              {renderCalendar(1)}
            </div>
            <p role="status" className="my-4 text-center text-sm text-neutral-500">
              {dates.length === 2 ? `${dates[0]} – ${dates[1]}` : dates.length === 1 ? `${dates[0]} — Select an end date` : 'Select a start date and an end date'}
            </p>
          </div>
        ) : (
          <div className="flex h-full flex-col items-center px-7 pt-[62px]">
            {/* How many days */}
            <h3 className="text-[20px] font-semibold text-neutral-900">
              How many days?
            </h3>

            <div className="mt-5 flex items-center gap-3">
              <button
                type="button"
                disabled={days <= 1}
                onClick={() =>
                  setDays((value) =>
                    Math.max(
                      1,
                      value - 1,
                    ),
                  )
                }
                aria-label="Decrease days"
                className="grid h-9 w-9 place-items-center rounded-full border border-neutral-300 text-xl text-neutral-700 transition hover:bg-neutral-50 disabled:opacity-40"
              >
                −
              </button>

              <div className="grid h-11 w-[104px] place-items-center rounded-full border border-neutral-300 bg-white text-[18px] text-neutral-900">
                {days}
              </div>

              <button
                type="button"
                onClick={() =>
                  setDays(
                    (value) => value + 1,
                  )
                }
                aria-label="Increase days"
                className="grid h-9 w-9 place-items-center rounded-full border border-neutral-300 text-xl text-neutral-700 transition hover:bg-neutral-50"
              >
                +
              </button>
            </div>

            {/* Travel anytime */}
            <h3 className="mt-[58px] text-[20px] font-semibold text-neutral-900">
              Travel anytime
            </h3>

            <div className="relative mt-5 w-full">
              {/* Previous months */}
              {monthOffset > 0 && (
                <button
                  type="button"
                  onClick={
                    previousFlexibleMonths
                  }
                  aria-label="Previous months"
                  className="absolute -left-4 top-1/2 z-10 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-full border border-neutral-200 bg-white shadow-sm"
                >
                  <ChevronLeft
                    size={20}
                    strokeWidth={1.8}
                  />
                </button>
              )}

              {/* Month cards */}
              <div className="flex gap-2 overflow-hidden px-0.5">
                {flexibleMonths.map(
                  (name) => {
                    const selected =
                      months.includes(name)

                    return (
                      <button
                        type="button"
                        key={name}
                        onClick={() =>
                          setMonths(
                            (current) =>
                              current.includes(
                                name,
                              )
                                ? current.filter(
                                    (item) =>
                                      item !==
                                      name,
                                  )
                                : [
                                    ...current,
                                    name,
                                  ],
                          )
                        }
                        className={`flex h-[120px] min-w-[120px] flex-1 flex-col items-center justify-center rounded-[16px] border transition ${
                          selected
                            ? 'border-black bg-black text-white'
                            : 'border-neutral-200 bg-white text-neutral-900 hover:border-neutral-300'
                        }`}
                      >
                        <CalendarDays
                          size={27}
                          strokeWidth={1.5}
                          className={
                            selected
                              ? 'text-white'
                              : 'text-neutral-500'
                          }
                        />

                        <span className="mt-3 text-[16px] font-medium">
                          {name}
                        </span>
                      </button>
                    )
                  },
                )}
              </div>

              {/* Next months */}
              <button
                type="button"
                onClick={
                  nextFlexibleMonths
                }
                aria-label="Next months"
                className="absolute -right-4 top-1/2 z-10 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-full border border-neutral-200 bg-white shadow-sm transition hover:bg-neutral-50"
              >
                <ChevronRight
                  size={20}
                  strokeWidth={1.8}
                />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex shrink-0 justify-end border-t border-neutral-200 pt-4">
        <button
          type="button"
          onClick={() => onSave(label)}
          disabled={tab === 'dates' && dates.length !== 2}
          className={`${actionClass} disabled:cursor-not-allowed disabled:opacity-40`}
        >
          Update
        </button>
      </div>
    </div>
  )
}
