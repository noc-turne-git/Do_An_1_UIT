import { useMemo, useState } from 'react'
import {
  Search,
  SlidersHorizontal,
  X,
  MapPin,
} from 'lucide-react'
import { useExplorePlaces, useSavedPlaces } from '../hooks/usePlaces'
import { usePlaceCollection } from '../store/usePlaceCollection'
import { PlaceCard } from './PlaceCard'

const categories = [
  'All',
  'Stays',
  'Restaurants',
  'Events',
  'Attractions',
  'Activities',
  'Locations',
]

type SortOption = 'recent' | 'az' | 'nearby'

type Coordinates = {
  latitude: number
  longitude: number
}

function getDistance(
  latitude1: number,
  longitude1: number,
  latitude2: number,
  longitude2: number,
) {
  const earthRadius = 6371

  const latitudeDifference =
    ((latitude2 - latitude1) * Math.PI) / 180

  const longitudeDifference =
    ((longitude2 - longitude1) * Math.PI) / 180

  const a =
    Math.sin(latitudeDifference / 2) ** 2 +
    Math.cos((latitude1 * Math.PI) / 180) *
      Math.cos((latitude2 * Math.PI) / 180) *
      Math.sin(longitudeDifference / 2) ** 2

  return (
    earthRadius *
    2 *
    Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  )
}

function getPlaceCoordinates(place: unknown): Coordinates | null {
  if (!place || typeof place !== 'object') {
    return null
  }

  const value = place as Record<string, unknown>

  const latitude =
    typeof value.latitude === 'number'
      ? value.latitude
      : typeof value.lat === 'number'
        ? value.lat
        : null

  const longitude =
    typeof value.longitude === 'number'
      ? value.longitude
      : typeof value.lng === 'number'
        ? value.lng
        : typeof value.lon === 'number'
          ? value.lon
          : null

  if (latitude === null || longitude === null) {
    return null
  }

  return {
    latitude,
    longitude,
  }
}

export function SavedPlacesView() {
  const { data = [], isLoading } = useSavedPlaces()
  const { data: explorePlaces = [] } = useExplorePlaces()

  const savedIds = usePlaceCollection(
    (state) => state.savedIds,
  )

  const toggleSaved = usePlaceCollection(
    (state) => state.toggleSaved,
  )

  const [category, setCategory] = useState('All')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<SortOption>('recent')
  const [showSort, setShowSort] = useState(false)

  const [userLocation, setUserLocation] =
    useState<Coordinates | null>(null)

  const [locationLoading, setLocationLoading] =
    useState(false)

  const [locationError, setLocationError] =
    useState(false)

  /*
   * Combine saved places from both sources
   * and remove duplicates.
   */
  const allSavedPlaces = useMemo(() => {
    const places = [
      ...data,
      ...explorePlaces.filter((place) =>
        savedIds.includes(place.id),
      ),
    ]

    return Array.from(
      new Map(
        places.map((place) => [place.id, place]),
      ).values(),
    ).filter((place) => savedIds.includes(place.id))
  }, [data, explorePlaces, savedIds])

  /*
   * Category counts
   */
  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {}

    for (const item of categories) {
      if (item === 'All') {
        counts[item] = allSavedPlaces.length
      } else {
        counts[item] = allSavedPlaces.filter(
          (place) => place.category === item,
        ).length
      }
    }

    return counts
  }, [allSavedPlaces])

  /*
   * Ask browser for current location.
   */
  const requestUserLocation = () => {
    if (!navigator.geolocation) {
      setLocationError(true)
      return
    }

    setLocationLoading(true)
    setLocationError(false)

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setUserLocation({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        })

        setLocationLoading(false)
      },
      () => {
        setLocationLoading(false)
        setLocationError(true)
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 300000,
      },
    )
  }

  /*
   * Select sorting option.
   */
  const handleSortChange = (
    value: SortOption,
  ) => {
    setSort(value)
    setShowSort(false)

    if (value === 'nearby' && !userLocation) {
      requestUserLocation()
    }
  }

  /*
   * Filter by category + search.
   * Then sort according to selected option.
   */
  const filtered = useMemo(() => {
    const normalizedQuery = query
      .trim()
      .toLowerCase()

    const result = allSavedPlaces.filter(
      (place) => {
        const matchesCategory =
          category === 'All' ||
          place.category === category

        const matchesSearch =
          !normalizedQuery ||
          `${place.name} ${place.location} ${place.category}`
            .toLowerCase()
            .includes(normalizedQuery)

        return (
          matchesCategory &&
          matchesSearch
        )
      },
    )

    /*
     * Recently saved
     *
     * We intentionally do not sort here because
     * the API/store order is treated as the current
     * saved order.
     */
    if (sort === 'recent') {
      return result
    }

    /*
     * A-Z
     */
    if (sort === 'az') {
      return [...result].sort((a, b) =>
        a.name.localeCompare(b.name),
      )
    }

    /*
     * Near me
     */
    if (
      sort === 'nearby' &&
      userLocation
    ) {
      return [...result].sort(
        (a, b) => {
          const coordinatesA =
            getPlaceCoordinates(a)

          const coordinatesB =
            getPlaceCoordinates(b)

          /*
           * Places without coordinates
           * are placed at the bottom.
           */
          if (
            !coordinatesA &&
            !coordinatesB
          ) {
            return 0
          }

          if (!coordinatesA) {
            return 1
          }

          if (!coordinatesB) {
            return -1
          }

          const distanceA =
            getDistance(
              userLocation.latitude,
              userLocation.longitude,
              coordinatesA.latitude,
              coordinatesA.longitude,
            )

          const distanceB =
            getDistance(
              userLocation.latitude,
              userLocation.longitude,
              coordinatesB.latitude,
              coordinatesB.longitude,
            )

          return distanceA - distanceB
        },
      )
    }

    return result
  }, [
    allSavedPlaces,
    category,
    query,
    sort,
    userLocation,
  ])

  const hasFilters =
    query.trim() !== '' ||
    category !== 'All'

  const clearFilters = () => {
    setQuery('')
    setCategory('All')
  }

  const sortLabel =
    sort === 'nearby'
      ? 'Near me'
      : sort === 'az'
        ? 'Name A–Z'
        : 'Recently saved'

  return (
    <section className="mx-auto max-w-7xl px-6 py-10 sm:px-10 lg:px-12 lg:py-12">
      {/* =====================================================
          HEADER
      ===================================================== */}

      <header className="mb-8">
        <div className="flex flex-col gap-6">
          <div>
            <h1 className="text-4xl font-bold tracking-[-0.045em] text-neutral-950 sm:text-5xl">
              Your saved places
            </h1>

            <p className="mt-3 text-[15px] leading-6 text-neutral-500">
              Places you have saved for your next adventure.
            </p>
          </div>

          {/* Search */}
          <div className="relative max-w-2xl">
            <Search className="pointer-events-none absolute left-5 top-1/2 h-5 w-5 -translate-y-1/2 text-neutral-400" />

            <input
              aria-label="Search saved places"
              value={query}
              onChange={(event) =>
                setQuery(event.target.value)
              }
              placeholder="Search saved places..."
              className="h-14 w-full rounded-full border border-neutral-200 bg-neutral-50 pl-13 pr-12 text-[15px] text-neutral-900 outline-none transition-all placeholder:text-neutral-400 hover:border-neutral-300 hover:bg-white focus:border-neutral-300 focus:bg-white focus:ring-4 focus:ring-neutral-100"
            />

            {query && (
              <button
                onClick={() => setQuery('')}
                aria-label="Clear search"
                className="absolute right-4 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-full bg-neutral-200 text-neutral-500 transition-colors hover:bg-neutral-300 hover:text-neutral-900"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      </header>

      {/* =====================================================
          CATEGORIES + SORT
      ===================================================== */}

      <div className="mb-8 flex items-center gap-3">
        {/* Categories */}
        <div className="flex min-w-0 flex-1 gap-2 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {categories.map((item) => {
            const active =
              category === item

            return (
              <button
                key={item}
                onClick={() =>
                  setCategory(item)
                }
                className={[
                  'flex shrink-0 items-center gap-1.5 rounded-full px-4 py-2.5 text-sm font-medium transition-all',
                  active
                    ? 'bg-neutral-900 text-white'
                    : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200 hover:text-neutral-900',
                ].join(' ')}
              >
                {item}

                <span
                  className={
                    active
                      ? 'text-[11px] text-white/50'
                      : 'text-[11px] text-neutral-400'
                  }
                >
                  {categoryCounts[item]}
                </span>
              </button>
            )
          })}
        </div>

        {/* Sort */}
        <div className="relative shrink-0">
          <button
            onClick={() =>
              setShowSort(
                (value) => !value,
              )
            }
            className={[
              'flex h-10 items-center gap-2 rounded-full border px-4 text-sm font-medium transition-all',
              showSort
                ? 'border-neutral-900 bg-neutral-900 text-white'
                : 'border-neutral-200 bg-white text-neutral-600 hover:border-neutral-300 hover:text-neutral-900',
            ].join(' ')}
          >
            <SlidersHorizontal className="h-4 w-4" />

            <span className="hidden sm:inline">
              {sortLabel}
            </span>
          </button>

          {showSort && (
            <div className="absolute right-0 top-12 z-30 w-52 rounded-2xl border border-neutral-200 bg-white p-1.5 shadow-xl shadow-black/10">
              <SortButton
                active={
                  sort === 'recent'
                }
                onClick={() =>
                  handleSortChange(
                    'recent',
                  )
                }
              >
                Recently saved
              </SortButton>

              <SortButton
                active={
                  sort === 'az'
                }
                onClick={() =>
                  handleSortChange('az')
                }
              >
                Name A–Z
              </SortButton>

              <SortButton
                active={
                  sort === 'nearby'
                }
                onClick={() =>
                  handleSortChange(
                    'nearby',
                  )
                }
              >
                <span className="flex items-center gap-2">
                  <MapPin className="h-4 w-4" />
                  Near me
                </span>
              </SortButton>
            </div>
          )}
        </div>
      </div>

      {/* =====================================================
          LOCATION ERROR
      ===================================================== */}

      {sort === 'nearby' &&
        locationError && (
          <div className="mb-6 flex items-center justify-between gap-4 rounded-2xl border border-neutral-200 bg-neutral-50 px-4 py-3">
            <div className="flex items-center gap-3">
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-white">
                <MapPin className="h-4 w-4 text-neutral-500" />
              </div>

              <p className="text-sm text-neutral-600">
                We could not access your
                location.
              </p>
            </div>

            <button
              onClick={
                requestUserLocation
              }
              className="shrink-0 rounded-full bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-neutral-800"
            >
              Try again
            </button>
          </div>
        )}

      {/* =====================================================
          LOADING
      ===================================================== */}

      {isLoading ? (
        <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
          {[
            1,
            2,
            3,
            4,
            5,
            6,
          ].map((item) => (
            <div
              key={item}
              className="h-[340px] animate-pulse rounded-3xl bg-neutral-100"
            />
          ))}
        </div>
      ) : filtered.length ? (
        <>
          {/* Result heading */}
          <div className="mb-5 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-neutral-400">
                {sort === 'nearby'
                  ? 'Sorted by distance'
                  : hasFilters
                    ? 'Matching places'
                    : 'Your collection'}
              </p>

              <h2 className="mt-0.5 text-lg font-semibold tracking-tight text-neutral-900">
                {filtered.length}{' '}
                {filtered.length === 1
                  ? 'saved place'
                  : 'saved places'}
              </h2>
            </div>

            {hasFilters && (
              <button
                onClick={
                  clearFilters
                }
                className="rounded-full px-3 py-2 text-sm font-medium text-neutral-500 transition-colors hover:bg-neutral-100 hover:text-neutral-900"
              >
                Clear filters
              </button>
            )}
          </div>

          {/* Cards */}
          <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
            {filtered.map(
              (place) => (
                <PlaceCard
                  key={place.id}
                  place={place}
                  saved
                  onToggleSaved={() =>
                    toggleSaved(
                      place.id,
                    )
                  }
                />
              ),
            )}
          </div>
        </>
      ) : (
        /* ===================================================
           EMPTY STATE
        =================================================== */

        <div className="flex min-h-[380px] flex-col items-center justify-center rounded-3xl border border-dashed border-neutral-200 bg-neutral-50 px-6 text-center">
          <div className="mb-5 grid h-16 w-16 place-items-center rounded-2xl bg-white shadow-sm ring-1 ring-neutral-200">
            {sort === 'nearby' ? (
              <MapPin className="h-7 w-7 text-neutral-400" />
            ) : (
              <svg
                className="h-7 w-7 text-neutral-400"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
              >
                <path d="M6 3.5h12v17l-6-3.5-6 3.5v-17Z" />
              </svg>
            )}
          </div>

          <h2 className="text-xl font-semibold tracking-tight text-neutral-900">
            {sort === 'nearby'
              ? 'Location data unavailable'
              : hasFilters
                ? 'No saved places found'
                : 'Your saved places are empty'}
          </h2>

          <p className="mt-2 max-w-sm text-sm leading-6 text-neutral-500">
            {sort === 'nearby'
              ? 'Some saved places do not have coordinates, so they cannot be sorted by distance.'
              : hasFilters
                ? 'Try another search or category.'
                : 'Save places you love and they will appear here.'}
          </p>

          {hasFilters && (
            <button
              onClick={
                clearFilters
              }
              className="mt-6 rounded-full bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-neutral-800"
            >
              Show all places
            </button>
          )}
        </div>
      )}
    </section>
  )
}

/* =============================================================
   SORT MENU ITEM
============================================================= */

function SortButton({
  children,
  active,
  onClick,
}: {
  children: React.ReactNode
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={[
        'flex w-full items-center justify-between rounded-xl px-3.5 py-2.5 text-left text-sm transition-colors',
        active
          ? 'bg-neutral-100 font-medium text-neutral-900'
          : 'text-neutral-600 hover:bg-neutral-50 hover:text-neutral-900',
      ].join(' ')}
    >
      {children}

      {active && (
        <span className="h-1.5 w-1.5 rounded-full bg-neutral-900" />
      )}
    </button>
  )
}