import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Filter, Plus, Search, X } from 'lucide-react'

import { useCreateTrip, useTrips } from '../hooks/useTrips'
import { TripCard } from './TripCard'
import { NewTripModal, type NewTripInput } from './NewTripModal'

export function TripList() {
  const { data = [], isLoading, isError } = useTrips()
  const create = useCreateTrip()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [search, setSearch] = useState('')
  const [showFilter, setShowFilter] = useState(false)
  const [statusFilter, setStatusFilter] = useState<
    'all' | 'upcoming' | 'past'
  >('all')

  const open = searchParams.get('newTrip') === '1'

  const close = () => {
    const next = new URLSearchParams(searchParams)
    next.delete('newTrip')

    setSearchParams(next, { replace: true })
  }

  const submit = async (input: NewTripInput) => {
    const trip = await create.mutateAsync(input)

    close()
    navigate(`/trips/${trip.id}`)
  }

  const filteredTrips = data.filter((trip) => {
    const matchesSearch = trip.name
      ?.toLowerCase()
      .includes(search.toLowerCase())

    // Status filtering can be connected to your actual trip date field later.
    // Currently, all trips are shown for "all".
    const matchesStatus =
      statusFilter === 'all' ? true : true

    return matchesSearch && matchesStatus
  })

  const clearFilters = () => {
    setStatusFilter('all')
    setSearch('')
  }

  const hasActiveFilter =
    statusFilter !== 'all' || search.trim() !== ''

  return (
    <section className="mx-auto max-w-7xl px-6 py-8 sm:px-10 sm:py-10">
      {/* Header */}
      <header className="mb-9 flex flex-wrap items-center justify-between gap-4">
        {/* Title */}
        <h1 className="text-4xl font-extrabold tracking-tight text-neutral-950 sm:text-[42px]">
          Your trips
        </h1>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {/* Search */}
          <div className="relative">
            <Search
              className="
                pointer-events-none
                absolute left-4 top-1/2
                h-4 w-4
                -translate-y-1/2
                text-neutral-400
              "
            />

            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search trips..."
              className="
                h-11
                w-48
                rounded-full
                border border-neutral-200
                bg-white
                pl-10 pr-9
                text-sm font-medium
                text-neutral-900
                outline-none
                transition-all duration-200
                placeholder:text-neutral-400
                hover:border-neutral-300
                focus:w-60
                focus:border-neutral-400
                focus:ring-4
                focus:ring-neutral-100
              "
            />

            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                className="
                  absolute right-3 top-1/2
                  grid h-6 w-6
                  -translate-y-1/2
                  place-items-center
                  rounded-full
                  text-neutral-400
                  transition-colors
                  hover:bg-neutral-100
                  hover:text-neutral-700
                "
                aria-label="Clear search"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {/* Filter */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowFilter((value) => !value)}
              className={`
                inline-flex
                h-11
                items-center
                gap-2
                rounded-full
                border
                px-4
                text-sm
                font-semibold
                transition-all
                ${
                  showFilter || hasActiveFilter
                    ? 'border-neutral-900 bg-neutral-900 text-white'
                    : 'border-neutral-200 bg-white text-neutral-700 hover:border-neutral-300 hover:bg-neutral-50'
                }
              `}
            >
              <Filter className="h-4 w-4" />

              <span className="hidden sm:inline">
                Filter
              </span>

              {hasActiveFilter && (
                <span
                  className="
                    grid h-5 min-w-5
                    place-items-center
                    rounded-full
                    bg-white
                    px-1
                    text-[10px]
                    font-bold
                    text-neutral-900
                  "
                >
                  {statusFilter !== 'all' && search
                    ? 2
                    : 1}
                </span>
              )}
            </button>

            {/* Filter Dropdown */}
            {showFilter && (
              <div
                className="
                  absolute right-0 top-[calc(100%+10px)]
                  z-30
                  w-64
                  overflow-hidden
                  rounded-2xl
                  border border-neutral-200
                  bg-white
                  p-2
                  shadow-[0_12px_40px_rgba(0,0,0,0.12)]
                "
              >
                {/* Filter Header */}
                <div className="flex items-center justify-between px-3 py-2.5">
                  <div>
                    <p className="text-sm font-bold text-neutral-900">
                      Filters
                    </p>

                    <p className="mt-0.5 text-xs text-neutral-400">
                      Narrow down your trips
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={() => setShowFilter(false)}
                    className="
                      grid h-7 w-7
                      place-items-center
                      rounded-full
                      text-neutral-400
                      transition-colors
                      hover:bg-neutral-100
                      hover:text-neutral-700
                    "
                    aria-label="Close filters"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                <div className="my-1 h-px bg-neutral-100" />

                {/* Trip Status */}
                <div className="p-1">
                  <p
                    className="
                      px-2 py-2
                      text-[11px]
                      font-bold
                      uppercase
                      tracking-wider
                      text-neutral-400
                    "
                  >
                    Trip status
                  </p>

                  {/* All */}
                  <button
                    type="button"
                    onClick={() => setStatusFilter('all')}
                    className={`
                      flex w-full
                      items-center
                      justify-between
                      rounded-xl
                      px-3 py-2.5
                      text-left
                      text-sm
                      transition-colors
                      ${
                        statusFilter === 'all'
                          ? 'bg-neutral-100 font-semibold text-neutral-900'
                          : 'font-medium text-neutral-600 hover:bg-neutral-50 hover:text-neutral-900'
                      }
                    `}
                  >
                    <span>All trips</span>

                    {statusFilter === 'all' && (
                      <span
                        className="
                          grid h-5 w-5
                          place-items-center
                          rounded-full
                          bg-neutral-900
                          text-[10px]
                          font-bold
                          text-white
                        "
                      >
                        ✓
                      </span>
                    )}
                  </button>

                  {/* Upcoming */}
                  <button
                    type="button"
                    onClick={() =>
                      setStatusFilter('upcoming')
                    }
                    className={`
                      mt-1 flex w-full
                      items-center
                      justify-between
                      rounded-xl
                      px-3 py-2.5
                      text-left
                      text-sm
                      transition-colors
                      ${
                        statusFilter === 'upcoming'
                          ? 'bg-neutral-100 font-semibold text-neutral-900'
                          : 'font-medium text-neutral-600 hover:bg-neutral-50 hover:text-neutral-900'
                      }
                    `}
                  >
                    <span>Upcoming</span>

                    {statusFilter === 'upcoming' && (
                      <span
                        className="
                          grid h-5 w-5
                          place-items-center
                          rounded-full
                          bg-neutral-900
                          text-[10px]
                          font-bold
                          text-white
                        "
                      >
                        ✓
                      </span>
                    )}
                  </button>

                  {/* Past */}
                  <button
                    type="button"
                    onClick={() =>
                      setStatusFilter('past')
                    }
                    className={`
                      mt-1 flex w-full
                      items-center
                      justify-between
                      rounded-xl
                      px-3 py-2.5
                      text-left
                      text-sm
                      transition-colors
                      ${
                        statusFilter === 'past'
                          ? 'bg-neutral-100 font-semibold text-neutral-900'
                          : 'font-medium text-neutral-600 hover:bg-neutral-50 hover:text-neutral-900'
                      }
                    `}
                  >
                    <span>Past trips</span>

                    {statusFilter === 'past' && (
                      <span
                        className="
                          grid h-5 w-5
                          place-items-center
                          rounded-full
                          bg-neutral-900
                          text-[10px]
                          font-bold
                          text-white
                        "
                      >
                        ✓
                      </span>
                    )}
                  </button>
                </div>

                <div className="my-1 h-px bg-neutral-100" />
              </div>
            )}
          </div>

          {/* New Trip */}
          <button
            type="button"
            onClick={() => setSearchParams({ newTrip: '1' })}
            className="
              inline-flex
              h-11
              items-center
              gap-2
              rounded-full
              bg-black
              px-5
              text-sm
              font-semibold
              text-white
              shadow-sm
              transition-all
              duration-200
              hover:-translate-y-0.5
              hover:bg-neutral-800
              hover:shadow-md
              active:translate-y-0
              active:scale-[0.98]
            "
          >
            <Plus className="h-4 w-4 stroke-[2.5]" />
            <span>New trip</span>
          </button>
        </div>
      </header>

      {/* Content */}
      {isLoading ? (
        <div className="py-10 text-center">
          <p className="text-sm font-medium text-neutral-500">
            Loading trips...
          </p>
        </div>
      ) : isError ? (
        <div
          role="alert"
          className="
            rounded-2xl
            border border-red-200
            bg-red-50
            px-5 py-4
            text-sm
            font-medium
            text-red-700
          "
        >
          Could not load trips.
        </div>
      ) : filteredTrips.length ? (
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
          {filteredTrips.map((trip) => (
            <TripCard
              key={trip.id}
              trip={trip}
            />
          ))}
        </div>
      ) : (
        <div
          className="
            flex
            min-h-[280px]
            flex-col
            items-center
            justify-center
            rounded-3xl
            border
            border-dashed
            border-neutral-300
            bg-neutral-50
            px-6
            text-center
          "
        >
          <h2 className="text-lg font-bold text-neutral-900">
            {search ? 'No trips found' : 'No trips yet'}
          </h2>

          <p className="mt-1 text-sm text-neutral-500">
            {search
              ? `No trips match "${search}".`
              : 'Create your first trip and start planning.'}
          </p>

          {search ? (
            <button
              type="button"
              onClick={() => setSearch('')}
              className="
                mt-5
                rounded-full
                border
                border-neutral-200
                bg-white
                px-5 py-2.5
                text-sm
                font-semibold
                text-neutral-700
                transition-colors
                hover:bg-neutral-100
              "
            >
              Clear search
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setSearchParams({ newTrip: '1' })}
              className="
                mt-5
                inline-flex
                items-center
                gap-2
                rounded-full
                bg-black
                px-5 py-2.5
                text-sm
                font-semibold
                text-white
                transition-all
                hover:bg-neutral-800
                active:scale-[0.98]
              "
            >
              <Plus className="h-4 w-4" />
              Create trip
            </button>
          )}
        </div>
      )}

      {/* New Trip Modal */}
      <NewTripModal
        key={open ? 'open' : 'closed'}
        open={open}
        onClose={close}
        onCreate={submit}
        isPending={create.isPending}
      />
    </section>
  )
}