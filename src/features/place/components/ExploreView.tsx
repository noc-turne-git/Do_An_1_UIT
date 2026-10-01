import { useMemo, useState } from 'react'
import {
  Check,
  ChevronDown,
  ChevronLeft,
  Heart,
  MapPin,
  Plus,
  Search,
  SlidersHorizontal,
  X,
} from 'lucide-react'

import { useExplorePlaces } from '../hooks/usePlaces'
import { usePlaceCollection } from '../store/usePlaceCollection'
import { PlaceCard } from './PlaceCard'

const categories = [
  'For you',
  'Experiences',
  'Restaurants',
  'Stays',
  'Locations',
  'Guides',
]

const markers = [
  ['Po Nagar Cham Towers', 47, 24],
  ['Hon Chong', 62, 42],
  ['Nha Trang Beach', 42, 61],
  ['Long Son Pagoda', 56, 76],
]

type Trip = {
  id: number
  name: string
  location: string
  duration: string
  image: string
}

const trips: Trip[] = [
  {
    id: 1,
    name: 'Trip to Da Lat',
    location: 'Lam Dong Province',
    duration: '4 days in Dec',
    image:
      'https://images.unsplash.com/photo-1557750255-c76072a7aad1?auto=format&fit=crop&w=300&q=80',
  },
  {
    id: 2,
    name: 'Trip to Nha Trang',
    location: 'Nha Trang',
    duration: '3 days',
    image:
      'https://images.unsplash.com/photo-1559592413-7cec4d0cae2b?auto=format&fit=crop&w=300&q=80',
  },
]

type Toast = {
  id: number
  message: string
}

export function ExploreView() {
  const { data = [], isLoading } = useExplorePlaces()

  const [category, setCategory] = useState('For you')
  const [query, setQuery] = useState('')

  const [location, setLocation] = useState('Nha Trang')
  const [showLocationPicker, setShowLocationPicker] = useState(false)

  const [showFilters, setShowFilters] = useState(false)

  const [selectedBudget, setSelectedBudget] = useState<string | null>(null)
  const [distance, setDistance] = useState('')
  const [distanceUnit, setDistanceUnit] = useState('km')

  const [savePlace, setSavePlace] = useState<{
    id: string
    name: string
  } | null>(null)

  const [toasts, setToasts] = useState<Toast[]>([])

  const savedIds = usePlaceCollection((state) => state.savedIds)
  const toggleSaved = usePlaceCollection((state) => state.toggleSaved)

  const filtered = useMemo(() => {
    return data.filter((place) =>
      `${place.name} ${place.location}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    )
  }, [data, query])

  function showToast(message: string) {
    const id = Date.now()

    setToasts((current) => [...current, { id, message }])

    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id))
    }, 2600)
  }

  function handleSave(place: any) {
    toggleSaved(place.id)

    const isSaved = savedIds.includes(place.id)

    showToast(
      isSaved
        ? `${place.name} removed from saved places`
        : `${place.name} saved`,
    )
  }

  function handleSaveToTrip(trip: Trip) {
    if (!savePlace) return

    showToast(`${savePlace.name} saved to ${trip.name}`)
    setSavePlace(null)
  }

  return (
    <div className="relative flex h-screen min-h-[600px] flex-col overflow-hidden bg-white xl:flex-row">
      {/* =========================================================
          LEFT CONTENT
      ========================================================== */}

      <section className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[900px] px-6 py-7 sm:px-8">
          {/* HEADER */}
          <header className="relative mb-6">
            <button
              onClick={() => setShowLocationPicker((value) => !value)}
              className="group flex items-center gap-1.5 text-left"
            >
              <h1 className="text-[25px] font-semibold tracking-[-0.02em] text-neutral-950">
                {location}
              </h1>

              <ChevronDown
                size={19}
                strokeWidth={2.2}
                className={`mt-1 transition-transform ${
                  showLocationPicker ? 'rotate-180' : ''
                }`}
              />
            </button>

            {/* LOCATION PICKER */}
            {showLocationPicker && (
              <LocationPicker
                value={location}
                onSelect={(value) => {
                  setLocation(value)
                  setShowLocationPicker(false)
                }}
              />
            )}
          </header>

          {/* SEARCH + FILTER */}
          <div className="mb-5 flex gap-3">
            <div className="relative min-w-0 flex-1">
              <Search
                size={19}
                className="absolute left-4 top-1/2 -translate-y-1/2 text-neutral-500"
              />

              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search places"
                className="h-[52px] w-full rounded-full border border-neutral-200 bg-neutral-50 pl-12 pr-5 text-[15px] outline-none transition focus:border-neutral-400 focus:bg-white"
              />

              {query && (
                <button
                  onClick={() => setQuery('')}
                  className="absolute right-3 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-full bg-neutral-200 text-neutral-600 transition hover:bg-neutral-300"
                >
                  <X size={15} />
                </button>
              )}
            </div>

            <button
              onClick={() => setShowFilters(true)}
              className="flex h-[52px] shrink-0 items-center gap-2 rounded-full border border-neutral-200 bg-white px-5 text-[15px] font-medium transition hover:bg-neutral-50"
            >
              <SlidersHorizontal size={18} strokeWidth={2} />
              <span>Filters</span>

              {(selectedBudget || distance) && (
                <span className="grid h-5 min-w-5 place-items-center rounded-full bg-black px-1.5 text-[11px] font-semibold text-white">
                  {(selectedBudget ? 1 : 0) + (distance ? 1 : 0)}
                </span>
              )}
            </button>
          </div>

          {/* CATEGORY */}
          <div className="mb-7 flex gap-1 overflow-x-auto border-b border-neutral-100 pb-1 scrollbar-none">
            {categories.map((item) => (
              <button
                key={item}
                onClick={() => setCategory(item)}
                className={`relative shrink-0 px-4 py-3 text-[14px] font-medium transition ${
                  category === item
                    ? 'text-black'
                    : 'text-neutral-500 hover:text-black'
                }`}
              >
                {item}

                {category === item && (
                  <span className="absolute bottom-[-1px] left-4 right-4 h-[2px] rounded-full bg-black" />
                )}
              </button>
            ))}
          </div>

          {/* SECTION TITLE */}
          <div className="mb-5 flex items-end justify-between">
            <div>
              <h2 className="text-[21px] font-semibold tracking-[-0.02em]">
                {category === 'For you' ? 'Experiences' : category}
              </h2>

              <p className="mt-1 text-sm text-neutral-500">
                Places worth discovering in {location}
              </p>
            </div>

          </div>

          {/* PLACES */}
          {isLoading ? (
            <div className="grid gap-5 sm:grid-cols-2">
              {[1, 2, 3, 4].map((item) => (
                <div
                  key={item}
                  className="h-[340px] animate-pulse rounded-2xl bg-neutral-100"
                />
              ))}
            </div>
          ) : filtered.length ? (
            <div className="grid gap-x-5 gap-y-8 sm:grid-cols-2">
              {filtered.map((place) => (
                <PlaceCard
                  key={place.id}
                  place={place}
                  saved={savedIds.includes(place.id)}
                  onToggleSaved={() => handleSave(place)}
                  onAddToTrip={() =>
                    setSavePlace({
                      id: place.id,
                      name: place.name,
                    })
                  }
                />
              ))}
            </div>
          ) : (
            <div className="py-20 text-center">
              <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-full bg-neutral-100">
                <Search size={22} className="text-neutral-500" />
              </div>

              <p className="font-medium text-neutral-900">
                No places found
              </p>

              <p className="mt-1 text-sm text-neutral-500">
                Try another search.
              </p>
            </div>
          )}
        </div>
      </section>

      {/* =========================================================
          MAP
      ========================================================== */}

      <ExploreMap />

      {/* =========================================================
          FILTER MODAL
      ========================================================== */}

      {showFilters && (
        <FilterModal
          budget={selectedBudget}
          distance={distance}
          distanceUnit={distanceUnit}
          onBudgetChange={setSelectedBudget}
          onDistanceChange={setDistance}
          onDistanceUnitChange={setDistanceUnit}
          onClose={() => setShowFilters(false)}
          onApply={() => {
            setShowFilters(false)
            showToast('Filters applied')
          }}
        />
      )}

      {/* =========================================================
          SAVE TO TRIP MODAL
      ========================================================== */}

      {savePlace && (
        <SaveToTripModal
          placeName={savePlace.name}
          trips={trips}
          onClose={() => setSavePlace(null)}
          onSave={handleSaveToTrip}
        />
      )}

      {/* =========================================================
          TOASTS
      ========================================================== */}

      <div className="pointer-events-none fixed bottom-6 left-1/2 z-[100] flex -translate-x-1/2 flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className="flex items-center gap-3 rounded-full bg-neutral-950 px-5 py-3 text-sm font-medium text-white shadow-2xl"
          >
            <span className="grid h-5 w-5 place-items-center rounded-full bg-white text-black">
              <Check size={13} strokeWidth={3} />
            </span>

            {toast.message}
          </div>
        ))}
      </div>
    </div>
  )
}

/* ===============================================================
   LOCATION PICKER
================================================================ */

function LocationPicker({
  value,
  onSelect,
}: {
  value: string
  onSelect: (value: string) => void
}) {
  const recentLocations = [
    {
      name: 'Nha Trang',
      subtitle: 'Khanh Hoa Province, Vietnam',
      image:
        'https://images.unsplash.com/photo-1559592413-7cec4d0cae2b?auto=format&fit=crop&w=120&q=80',
    },
    {
      name: 'Da Lat',
      subtitle: 'Lam Dong Province, Vietnam',
      image:
        'https://images.unsplash.com/photo-1557750255-c76072a7aad1?auto=format&fit=crop&w=120&q=80',
    },
    {
      name: 'Lam Dong Province',
      subtitle: 'Vietnam',
      image:
        'https://images.unsplash.com/photo-1528127269322-539801943592?auto=format&fit=crop&w=120&q=80',
    },
    {
      name: 'Binh Tien',
      subtitle: 'Ho Chi Minh City, Vietnam',
      image:
        'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=120&q=80',
    },
    {
      name: 'Ho Chi Minh City',
      subtitle: 'Vietnam',
      image:
        'https://images.unsplash.com/photo-1583417319070-4a69db38a482?auto=format&fit=crop&w=120&q=80',
    },
  ]

  return (
    <div className="absolute left-0 top-[48px] z-50 w-[460px] overflow-hidden rounded-2xl border border-neutral-200 bg-white p-4 shadow-[0_12px_40px_rgba(0,0,0,0.14)]">
      {/* INPUT */}
      <div className="relative mb-4">
        <input
          autoFocus
          value={`${value}, Vietnam`}
          readOnly
          className="h-[44px] w-full rounded-full border border-neutral-900 px-4 pr-11 text-[15px] font-medium outline-none"
        />

        <button className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-full bg-neutral-200 text-neutral-500">
          <X size={15} />
        </button>
      </div>

      {/* CURRENT LOCATION */}
      <button className="mb-4 flex w-full items-center gap-3 rounded-xl px-2 py-2.5 text-left transition hover:bg-neutral-50">
        <span className="grid h-11 w-11 place-items-center rounded-xl bg-neutral-100">
          <MapPin size={20} />
        </span>

        <span className="text-[15px] font-semibold">
          Use current location
        </span>
      </button>

      <p className="mb-2 px-2 text-xs font-medium text-neutral-400">
        Recent locations
      </p>

      <div className="space-y-1">
        {recentLocations.map((item) => (
          <button
            key={item.name}
            onClick={() => onSelect(item.name)}
            className={`flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left transition hover:bg-neutral-50 ${
              item.name === value ? 'bg-neutral-50' : ''
            }`}
          >
            <img
              src={item.image}
              alt=""
              className="h-11 w-11 rounded-xl object-cover"
            />

            <span className="min-w-0">
              <span className="block truncate text-[15px] font-semibold text-neutral-900">
                {item.name}
              </span>

              <span className="block truncate text-sm text-neutral-500">
                {item.subtitle}
              </span>
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

/* ===============================================================
   FILTER MODAL
================================================================ */

function FilterModal({
  budget,
  distance,
  distanceUnit,
  onBudgetChange,
  onDistanceChange,
  onDistanceUnitChange,
  onClose,
  onApply,
}: {
  budget: string | null
  distance: string
  distanceUnit: string
  onBudgetChange: (value: string | null) => void
  onDistanceChange: (value: string) => void
  onDistanceUnitChange: (value: string) => void
  onClose: () => void
  onApply: () => void
}) {
  const budgets = ['$', '$$', '$$$', '$$$$']

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/35 p-5 backdrop-blur-[2px]"
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
          >
            <X size={21} />
          </button>

          <h2 className="text-[22px] font-semibold">Filters</h2>
        </div>

        <div className="px-7 py-7">
          {/* BUDGET */}
          <section>
            <h3 className="mb-4 text-[17px] font-semibold">Budget</h3>

            <div className="flex gap-2">
              {budgets.map((item) => {
                const active = budget === item

                return (
                  <button
                    key={item}
                    onClick={() =>
                      onBudgetChange(active ? null : item)
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

          {/* DISTANCE */}
          <section>
            <h3 className="mb-4 text-[17px] font-semibold">Distance</h3>

            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <input
                  type="number"
                  min="0"
                  value={distance}
                  onChange={(event) =>
                    onDistanceChange(event.target.value)
                  }
                  placeholder="Any distance"
                  className="h-[52px] w-full rounded-xl border border-neutral-200 px-4 pr-3 text-[15px] outline-none transition focus:border-black"
                />
              </div>

              <select
                value={distanceUnit}
                onChange={(event) =>
                  onDistanceUnitChange(event.target.value)
                }
                className="h-[52px] rounded-xl border border-neutral-200 bg-white px-4 text-[15px] outline-none"
              >
                <option value="km">km</option>
                <option value="mi">mi</option>
              </select>
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              {['1.5', '5', '15', '50'].map((item) => (
                <button
                  key={item}
                  onClick={() => onDistanceChange(item)}
                  className={`rounded-full border px-4 py-2 text-sm transition ${
                    distance === item
                      ? 'border-black bg-black text-white'
                      : 'border-neutral-200 hover:border-neutral-400'
                  }`}
                >
                  {item} km
                </button>
              ))}
            </div>
          </section>
        </div>

        {/* FOOTER */}
        <div className="flex justify-end border-t border-neutral-100 px-7 py-5">
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

/* ===============================================================
   SAVE TO TRIP MODAL
================================================================ */

function SaveToTripModal({
  placeName,
  trips,
  onClose,
  onSave,
}: {
  placeName: string
  trips: Trip[]
  onClose: () => void
  onSave: (trip: Trip) => void
}) {
  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/45 p-5 backdrop-blur-[2px]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div className="w-full max-w-[620px] overflow-hidden rounded-[24px] bg-white shadow-2xl">
        {/* HEADER */}
        <div className="relative flex h-[74px] items-center justify-center border-b border-neutral-100">
          <button
            onClick={onClose}
            className="absolute left-5 grid h-9 w-9 place-items-center transition hover:bg-neutral-100"
          >
            <X size={21} />
          </button>

          <h2 className="text-[21px] font-semibold">Save to trip</h2>
        </div>

        <div className="px-6 py-6">
          <p className="mb-4 text-sm text-neutral-500">
            Save <span className="font-semibold text-neutral-900">{placeName}</span>{' '}
            to one of your trips
          </p>

          <div className="space-y-2">
            {trips.map((trip) => (
              <button
                key={trip.id}
                onClick={() => onSave(trip)}
                className="group flex w-full items-center gap-4 rounded-2xl p-3 text-left transition hover:bg-neutral-50"
              >
                <img
                  src={trip.image}
                  alt=""
                  className="h-[68px] w-[68px] shrink-0 rounded-xl object-cover"
                />

                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[16px] font-semibold text-neutral-900">
                    {trip.name}
                  </span>

                  <span className="mt-1 block truncate text-sm text-neutral-500">
                    {trip.location}
                    <span className="mx-1.5">·</span>
                    {trip.duration}
                  </span>
                </span>

                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-neutral-300 transition group-hover:border-black group-hover:bg-black group-hover:text-white">
                  <Plus size={19} />
                </span>
              </button>
            ))}
          </div>

          {/* CREATE TRIP */}
          <button
            onClick={() => {
              onClose()
              window.setTimeout(() => {
                // Replace this with your NewTripModal navigation/action.
                window.dispatchEvent(new CustomEvent('create-trip'))
              }, 100)
            }}
            className="mt-5 flex w-full items-center gap-4 rounded-2xl p-3 text-left transition hover:bg-neutral-50"
          >
            <span className="grid h-[52px] w-[52px] place-items-center rounded-full bg-black text-white">
              <Plus size={25} />
            </span>

            <span className="text-[16px] font-semibold">
              Create a trip
            </span>
          </button>
        </div>
      </div>
    </div>
  )
}

/* ===============================================================
   MAP
================================================================ */

function ExploreMap() {
  const [selected, setSelected] = useState('Hon Chong')
  const [zoom, setZoom] = useState(1)

  return (
    <section
      aria-label="Nha Trang map"
      className="relative min-h-[360px] flex-1 overflow-hidden bg-[#edf0e9] xl:min-h-0"
    >
      <div className="absolute left-[3%] top-[20%] h-48 w-60 rounded-[50%] bg-[#dce8d4]" />

      <div className="absolute bottom-[10%] right-[12%] h-32 w-48 rounded-[50%] bg-[#d5e5e8]" />

      <div className="absolute left-[-10%] top-[48%] h-4 w-[120%] rotate-[-16deg] border-y-2 border-white/80" />

      <div className="absolute left-[42%] top-[-10%] h-[120%] w-3 rotate-[22deg] border-x-2 border-white/80" />

      <span className="absolute left-1/3 top-1/2 text-xs tracking-widest text-neutral-500">
        NHA TRANG
      </span>

      {markers.map(([name, x, y]) => (
        <button
          key={name}
          onClick={() => setSelected(String(name))}
          style={{
            left: `${x}%`,
            top: `${y}%`,
          }}
          className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-full border px-3 py-2 text-xs shadow-md transition ${
            selected === name
              ? 'border-neutral-900 bg-neutral-900 text-white'
              : 'border-white bg-white hover:scale-105'
          }`}
        >
          ● {name}
        </button>
      ))}

      {/* MAP CONTROLS */}
      <div className="absolute right-5 top-5 flex flex-col overflow-hidden rounded-full border border-neutral-200 bg-white shadow-md">
        <button className="grid h-11 w-11 place-items-center hover:bg-neutral-50">
          <ChevronLeft size={19} />
        </button>
      </div>

      <div className="absolute bottom-5 right-5 grid overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-lg">
        <button
          onClick={() => setZoom(zoom + 1)}
          className="grid h-11 w-11 place-items-center text-xl hover:bg-neutral-50"
        >
          +
        </button>

        <button
          onClick={() => setZoom(Math.max(1, zoom - 1))}
          className="grid h-11 w-11 place-items-center border-t text-xl hover:bg-neutral-50"
        >
          −
        </button>
      </div>

      <button
        aria-label="Show my location"
        className="absolute bottom-5 left-5 grid h-11 w-11 place-items-center rounded-xl border border-neutral-200 bg-white shadow-lg transition hover:bg-neutral-50"
      >
        <MapPin size={19} />
      </button>

      <span className="absolute bottom-2 right-24 text-[10px] text-neutral-500">
        Map data © OpenStreetMap · zoom {zoom}
      </span>
    </section>
  )
}