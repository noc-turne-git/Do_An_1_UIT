import {
  CalendarDays,
  Search,
  SlidersHorizontal,
  X,
} from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { imageUrl, suggestions, type PlaceSuggestion } from '../data'

type Tab = 'Search' | 'Ideas' | 'Saved' | 'Custom'

type Props = {
  day: number | null
  savedPlaces: string[]
  onClose: () => void
  onAddPlace: (name: string, image?: string, time?: string) => void
}

type FilterState = {
  price: string | null
  duration: string | null
}

/* ===============================================================
   PLACE CARD
=============================================================== */

function PlaceCard({
  place,
  index,
  onAdd,
}: {
  place: PlaceSuggestion
  index: number
  onAdd: () => void
}) {
  return (
    <article className="min-w-0">
      <div className="relative mb-4 overflow-hidden rounded-[20px]">
        <img
          src={imageUrl(place.image)}
          alt=""
          className="h-56 w-full object-cover"
        />

        <button
          onClick={onAdd}
          className="absolute right-4 top-4 rounded-full bg-white px-4 py-2 text-sm font-medium shadow-sm transition hover:bg-neutral-50"
        >
          + Add
        </button>
      </div>

      <div className="flex items-center justify-between gap-2">
        <h5 className="truncate text-base font-semibold">
          {place.name}
        </h5>

        <span className="shrink-0 text-sm">
          ★ {['4.4', '4.2', '4.5'][index % 3]}
        </span>
      </div>

      <p className="mt-1 text-sm text-neutral-500">
        {place.type} · Da Lat, Lâm Đồng
      </p>
    </article>
  )
}

/* ===============================================================
   ADD PLACE MODAL
=============================================================== */

export function AddPlaceModal({
  day,
  savedPlaces,
  onClose,
  onAddPlace,
}: Props) {
  const [tab, setTab] = useState<Tab>('Search')
  const [search, setSearch] = useState('')

  const [showFilters, setShowFilters] = useState(false)

  const [filters, setFilters] = useState<FilterState>({
    price: null,
    duration: null,
  })

  const [appliedFilters, setAppliedFilters] = useState<FilterState>({
    price: null,
    duration: null,
  })

  /* =============================================================
     CUSTOM PLACE STATE
  ============================================================= */

  const [customName, setCustomName] = useState('')
  const [customAddress, setCustomAddress] = useState('')
  const [customPrice, setCustomPrice] = useState<string | null>(null)
  const [customDuration, setCustomDuration] = useState('')

  /* =============================================================
     START TIME
     This belongs to the whole Add to trip modal.
  ============================================================= */

  const [startTime, setStartTime] = useState(() => {
    const date = new Date()

    // Round current time up to the next 30-minute interval.
    const minutes = date.getMinutes()

    date.setMinutes(Math.ceil(minutes / 30) * 30, 0, 0)

    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const hours = String(date.getHours()).padStart(2, '0')
    const mins = String(date.getMinutes()).padStart(2, '0')

    return `${year}-${month}-${day}T${hours}:${mins}`
  })

  const startTimeInputRef = useRef<HTMLInputElement>(null)

  const places = useMemo(() => {
    const source =
      tab === 'Ideas'
        ? suggestions.slice(0, 4)
        : tab === 'Saved'
          ? suggestions.filter((place) =>
              savedPlaces.includes(place.name),
            )
          : suggestions

    return source.filter((place) =>
      place.name.toLowerCase().includes(search.toLowerCase()),
    )
  }, [savedPlaces, search, tab])

  if (day === null) return null

  /* =============================================================
     HELPERS
  ============================================================= */

  function formatStartTime(value: string) {
    if (!value) return 'Select start time'

    const date = new Date(value)

    if (Number.isNaN(date.getTime())) {
      return 'Select start time'
    }

    const hours = String(date.getHours()).padStart(2, '0')
    const minutes = String(date.getMinutes()).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const year = date.getFullYear()

    return `${hours}:${minutes} · ${day}/${month}/${year}`
  }

  function addPlace(place: PlaceSuggestion) {
    onAddPlace(place.name, place.image, startTime)
  }

  function addCustomPlace() {
    const name = customName.trim()

    if (!name) return

    onAddPlace(name, undefined, startTime)
  }

  function openFilters() {
    setFilters(appliedFilters)
    setShowFilters(true)
  }

  function applyFilters() {
    setAppliedFilters(filters)
    setShowFilters(false)
  }

  const activeFilterCount =
    (appliedFilters.price ? 1 : 0) +
    (appliedFilters.duration ? 1 : 0)

  return (
    <div
      className="fixed inset-0 z-[70] grid place-items-center bg-black/45 p-4"
      onMouseDown={onClose}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-place-title"
        className="flex max-h-[calc(100vh-48px)] min-h-[620px] w-full max-w-[880px] flex-col overflow-hidden rounded-[20px] bg-white shadow-2xl"
        onMouseDown={(event) => event.stopPropagation()}
      >
        {/* =====================================================
            HEADER
        ====================================================== */}

        <header className="relative flex h-[84px] shrink-0 items-center justify-center border-b border-neutral-200">
          <button
            aria-label="Close add place dialog"
            onClick={onClose}
            className="absolute left-8 top-5 text-[27px] leading-none text-black transition hover:text-neutral-500"
          >
            ×
          </button>

          <h3
            id="add-place-title"
            className="text-2xl font-bold tracking-tight"
          >
            Add to trip
          </h3>
        </header>

        {/* =====================================================
            TABS
        ====================================================== */}

        <nav className="mx-[30px] flex shrink-0 gap-6 border-b border-neutral-200 pt-4">
          {(['Search', 'Ideas', 'Saved', 'Custom'] as const).map(
            (item) => (
              <button
                key={item}
                onClick={() => setTab(item)}
                className={`border-b-2 px-2 pb-3 pt-2 text-base transition ${
                  tab === item
                    ? 'border-black font-medium text-black'
                    : 'border-transparent text-neutral-500 hover:text-black'
                }`}
              >
                {item}
              </button>
            ),
          )}
        </nav>

        {/* =====================================================
            CONTENT
        ====================================================== */}

        <div className="min-h-0 flex-1 overflow-y-auto px-[30px] pb-8 pt-7">
          {tab === 'Custom' ? (
            <CustomPlaceForm
              customName={customName}
              customAddress={customAddress}
              customPrice={customPrice}
              customDuration={customDuration}
              onNameChange={setCustomName}
              onAddressChange={setCustomAddress}
              onPriceChange={setCustomPrice}
              onDurationChange={setCustomDuration}
              onAdd={addCustomPlace}
            />
          ) : (
            <>
              {/* =================================================
                  SEARCH + FILTER
              ================================================== */}

              <div className="mb-6 flex gap-3">
                {/* SEARCH */}

                <div className="relative min-w-0 flex-1">
                  <Search
                    size={19}
                    className="absolute left-4 top-1/2 -translate-y-1/2 text-neutral-500"
                  />

                  <input
                    value={search}
                    onChange={(event) =>
                      setSearch(event.target.value)
                    }
                    placeholder="Search places"
                    className="h-[52px] w-full rounded-full border border-neutral-200 bg-neutral-50 pl-12 pr-12 text-[15px] outline-none transition focus:border-neutral-400 focus:bg-white"
                  />

                  {search && (
                    <button
                      onClick={() => setSearch('')}
                      className="absolute right-3 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-full bg-neutral-200 text-neutral-600 transition hover:bg-neutral-300"
                    >
                      <X size={15} />
                    </button>
                  )}
                </div>

                {/* FILTER */}

                <button
                  onClick={openFilters}
                  className="flex h-[52px] shrink-0 items-center gap-2 rounded-full border border-neutral-200 bg-white px-5 text-[15px] font-medium transition hover:bg-neutral-50"
                >
                  <SlidersHorizontal
                    size={18}
                    strokeWidth={2}
                  />

                  <span>Filters</span>

                  {activeFilterCount > 0 && (
                    <span className="grid h-5 min-w-5 place-items-center rounded-full bg-black px-1.5 text-[11px] font-semibold text-white">
                      {activeFilterCount}
                    </span>
                  )}
                </button>
              </div>

              {/* =================================================
                  SAVED EMPTY
              ================================================== */}

              {tab === 'Saved' && places.length === 0 ? (
                <p className="text-neutral-500">
                  Places you save will appear here.
                </p>
              ) : (
                <div className="grid gap-7 sm:grid-cols-2 lg:grid-cols-3">
                  {places.map((place, index) => (
                    <PlaceCard
                      key={place.name}
                      place={place}
                      index={index}
                      onAdd={() => addPlace(place)}
                    />
                  ))}
                </div>
              )}

              {/* =================================================
                  SEARCH EMPTY
              ================================================== */}

              {tab === 'Search' && places.length === 0 && (
                <div className="py-10 text-center">
                  <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-full bg-neutral-100">
                    <Search
                      size={20}
                      className="text-neutral-500"
                    />
                  </div>

                  <p className="text-sm font-medium text-neutral-900">
                    No matching places.
                  </p>

                  <p className="mt-1 text-sm text-neutral-500">
                    Try another search.
                  </p>
                </div>
              )}
            </>
          )}
        </div>

        {/* =====================================================
            START TIME FOOTER
            This is the footer of the ENTIRE Add to trip modal.
        ====================================================== */}

        <footer className="flex shrink-0 items-center justify-between gap-4 border-t border-neutral-200 bg-white px-[30px] py-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-neutral-100">
              <CalendarDays
                size={19}
                strokeWidth={2}
                className="text-neutral-700"
              />
            </div>

            <div className="min-w-0">
              <p className="text-xs font-medium text-neutral-500">
                Start time
              </p>

              <p className="mt-0.5 truncate text-[15px] font-semibold text-neutral-900">
                {formatStartTime(startTime)}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => startTimeInputRef.current?.showPicker?.()}
            className="shrink-0 rounded-full border border-neutral-200 bg-white px-5 py-2.5 text-[14px] font-medium transition hover:border-neutral-400 hover:bg-neutral-50"
          >
            Change time
          </button>

          <input
            ref={startTimeInputRef}
            type="datetime-local"
            value={startTime}
            onChange={(event) => setStartTime(event.target.value)}
            className="sr-only"
            aria-label="Start time"
          />
        </footer>

        {/* =====================================================
            FILTER MODAL
        ====================================================== */}

        {showFilters && (
          <FilterModal
            price={filters.price}
            duration={filters.duration}
            onPriceChange={(value) =>
              setFilters((current) => ({
                ...current,
                price: value,
              }))
            }
            onDurationChange={(value) =>
              setFilters((current) => ({
                ...current,
                duration: value,
              }))
            }
            onClose={() => setShowFilters(false)}
            onApply={applyFilters}
          />
        )}
      </section>
    </div>
  )
}

/* ===============================================================
   CUSTOM PLACE FORM
=============================================================== */

function CustomPlaceForm({
  customName,
  customAddress,
  customPrice,
  customDuration,
  onNameChange,
  onAddressChange,
  onPriceChange,
  onDurationChange,
  onAdd,
}: {
  customName: string
  customAddress: string
  customPrice: string | null
  customDuration: string
  onNameChange: (value: string) => void
  onAddressChange: (value: string) => void
  onPriceChange: (value: string | null) => void
  onDurationChange: (value: string) => void
  onAdd: () => void
}) {
  const prices = ['$', '$$', '$$$', '$$$$']

  const durations = [
    {
      value: '30 min',
      label: '30 min',
    },
    {
      value: '1 hr',
      label: '1 hr',
    },
    {
      value: '2 hrs',
      label: '2 hrs',
    },
    {
      value: '3+ hrs',
      label: '3+ hrs',
    },
  ]

  const canAdd = customName.trim().length > 0

  return (
    <div className="w-full max-w-[680px]">
      {/* INTRO */}

      <div className="mb-8">
        <h4 className="text-[22px] font-semibold tracking-tight">
          Add a custom place
        </h4>

        <p className="mt-1.5 text-sm text-neutral-500">
          Add somewhere that isn't in the list.
        </p>
      </div>

      <div className="space-y-7">
        {/* =====================================================
            TITLE
        ====================================================== */}

        <section>
          <label className="mb-2.5 block text-[15px] font-semibold text-neutral-900">
            Title
          </label>

          <input
            value={customName}
            onChange={(event) =>
              onNameChange(event.target.value)
            }
            placeholder="e.g. Crazy House"
            className="h-[54px] w-full rounded-xl border border-neutral-200 bg-white px-4 text-[15px] outline-none transition placeholder:text-neutral-400 focus:border-black"
          />
        </section>

        {/* =====================================================
            ADDRESS
        ====================================================== */}

        <section>
          <label className="mb-2.5 block text-[15px] font-semibold text-neutral-900">
            Address
          </label>

          <input
            value={customAddress}
            onChange={(event) =>
              onAddressChange(event.target.value)
            }
            placeholder="Enter an address or location"
            className="h-[54px] w-full rounded-xl border border-neutral-200 bg-white px-4 text-[15px] outline-none transition placeholder:text-neutral-400 focus:border-black"
          />
        </section>

        {/* =====================================================
            PRICE
        ====================================================== */}

        <section>
          <label className="mb-2.5 block text-[15px] font-semibold text-neutral-900">
            Price
          </label>

          <div className="flex gap-2">
            {prices.map((price) => {
              const active = customPrice === price

              return (
                <button
                  key={price}
                  type="button"
                  onClick={() =>
                    onPriceChange(active ? null : price)
                  }
                  className={`rounded-full border px-5 py-2.5 text-[15px] font-medium transition ${
                    active
                      ? 'border-black bg-black text-white'
                      : 'border-neutral-200 bg-white hover:border-neutral-400'
                  }`}
                >
                  {price}
                </button>
              )
            })}
          </div>

          <p className="mt-2 text-xs text-neutral-400">
            Choose an approximate price range.
          </p>
        </section>

        {/* =====================================================
            DURATION
        ====================================================== */}

        <section>
          <label className="mb-2.5 block text-[15px] font-semibold text-neutral-900">
            Duration
          </label>

          <div className="flex flex-wrap gap-2">
            {durations.map((item) => {
              const active = customDuration === item.value

              return (
                <button
                  key={item.value}
                  type="button"
                  onClick={() =>
                    onDurationChange(
                      active ? '' : item.value,
                    )
                  }
                  className={`rounded-full border px-5 py-2.5 text-[15px] font-medium transition ${
                    active
                      ? 'border-black bg-black text-white'
                      : 'border-neutral-200 bg-white hover:border-neutral-400'
                  }`}
                >
                  {item.label}
                </button>
              )
            })}

            {/* CUSTOM DURATION */}

            <input
              value={
                durations.some(
                  (item) => item.value === customDuration,
                )
                  ? ''
                  : customDuration
              }
              onChange={(event) =>
                onDurationChange(event.target.value)
              }
              placeholder="Custom"
              className="h-[42px] w-[110px] rounded-full border border-neutral-200 px-4 text-[14px] outline-none transition placeholder:text-neutral-400 focus:border-black"
            />
          </div>

          <p className="mt-2 text-xs text-neutral-400">
            How long do you expect to spend here?
          </p>
        </section>
      </div>

      {/* ACTION */}

      <div className="mt-9 flex justify-end">
        <button
          disabled={!canAdd}
          onClick={onAdd}
          className="rounded-full bg-black px-7 py-3.5 text-[15px] font-semibold text-white transition hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-35"
        >
          Add place
        </button>
      </div>
    </div>
  )
}

/* ===============================================================
   FILTER MODAL
=============================================================== */

function FilterModal({
  price,
  duration,
  onPriceChange,
  onDurationChange,
  onClose,
  onApply,
}: {
  price: string | null
  duration: string | null
  onPriceChange: (value: string | null) => void
  onDurationChange: (value: string | null) => void
  onClose: () => void
  onApply: () => void
}) {
  const prices = ['$', '$$', '$$$', '$$$$']

  const durations = [
    'Under 1 hr',
    '1–2 hrs',
    '2–4 hrs',
    '4+ hrs',
  ]

  return (
    <div
      className="absolute inset-0 z-[90] flex items-center justify-center bg-black/35 p-5 backdrop-blur-[2px]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div className="w-full max-w-[540px] overflow-hidden rounded-[28px] bg-white shadow-2xl">
        {/* HEADER */}

        <div className="relative flex h-[76px] items-center justify-center border-b border-neutral-100">
          <button
            onClick={onClose}
            className="absolute left-5 grid h-10 w-10 place-items-center rounded-full bg-neutral-100 transition hover:bg-neutral-200"
            aria-label="Close filters"
          >
            <X size={21} />
          </button>

          <h2 className="text-[22px] font-semibold">
            Filters
          </h2>
        </div>

        {/* BODY */}

        <div className="px-7 py-7">
          {/* PRICE */}

          <section>
            <h3 className="mb-4 text-[17px] font-semibold">
              Price
            </h3>

            <div className="flex gap-2">
              {prices.map((item) => {
                const active = price === item

                return (
                  <button
                    key={item}
                    onClick={() =>
                      onPriceChange(active ? null : item)
                    }
                    className={`rounded-full border px-5 py-2.5 text-[15px] font-medium transition ${
                      active
                        ? 'border-black bg-black text-white'
                        : 'border-neutral-200 bg-white hover:border-neutral-400'
                    }`}
                  >
                    {item}
                  </button>
                )
              })}
            </div>
          </section>

          <div className="my-7 h-px bg-neutral-100" />

          {/* DURATION */}

          <section>
            <h3 className="mb-4 text-[17px] font-semibold">
              Duration
            </h3>

            <div className="flex flex-wrap gap-2">
              {durations.map((item) => {
                const active = duration === item

                return (
                  <button
                    key={item}
                    onClick={() =>
                      onDurationChange(
                        active ? null : item,
                      )
                    }
                    className={`rounded-full border px-4 py-2.5 text-[14px] font-medium transition ${
                      active
                        ? 'border-black bg-black text-white'
                        : 'border-neutral-200 bg-white hover:border-neutral-400'
                    }`}
                  >
                    {item}
                  </button>
                )
              })}
            </div>
          </section>
        </div>

        {/* FOOTER */}

        <div className="flex justify-between border-t border-neutral-100 px-7 py-5">
          <button
            onClick={() => {
              onPriceChange(null)
              onDurationChange(null)
            }}
            className="rounded-full px-5 py-3 text-[15px] font-medium text-neutral-600 transition hover:bg-neutral-100 hover:text-black"
          >
            Clear all
          </button>

          <button
            onClick={onApply}
            className="rounded-full bg-black px-7 py-3.5 text-[15px] font-semibold text-white transition hover:bg-neutral-800"
          >
            Show places
          </button>
        </div>
      </div>
    </div>
  )
}
