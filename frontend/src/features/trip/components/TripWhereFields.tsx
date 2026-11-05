import { useEffect, useState } from 'react'
import { MapPin } from 'lucide-react'
import { actionClass, fieldClass } from './tripFieldModalTypes'

type Props = {
  destination: string
  onClose: () => void
  onSave: (destination: string) => void
}

type LocationInfo = {
  name: string
  description: string
  image: string
}

const LOCATION_DATA: Record<string, LocationInfo> = {
  'Nha Trang': {
    name: 'Nha Trang',
    description: 'Khanh Hoa Province, Vietnam',
    image:
      'https://images.unsplash.com/photo-1583417319070-4a69db38a482?auto=format&fit=crop&w=160&q=80',
  },
  'Hhohbo District': {
    name: 'Hhohbo District',
    description: 'Eswatini (Swaziland)',
    image:
      'https://images.unsplash.com/photo-1489392191049-fc10c97e64b6?auto=format&fit=crop&w=160&q=80',
  },
}

const SUGGESTIONS: LocationInfo[] = [
  LOCATION_DATA['Hhohbo District'],
]

function getLocationInfo(location: string): LocationInfo {
  const key = location.split(',')[0].trim()

  if (LOCATION_DATA[key]) {
    return LOCATION_DATA[key]
  }

  const parts = location.split(',')

  return {
    name: parts[0]?.trim() || location,
    description:
      parts.slice(1).join(',').trim() || 'Destination',
    image:
      'https://images.unsplash.com/photo-1500534623283-312aade485b7?auto=format&fit=crop&w=160&q=80',
  }
}

export function TripWhereFields({
  destination,
  onClose,
  onSave,
}: Props) {
  const [locations, setLocations] = useState<string[]>([])
  const [draft, setDraft] = useState('')
  const [isAdding, setIsAdding] = useState(false)
  const [isRoadTrip, setIsRoadTrip] = useState(false)

  useEffect(() => {
    setLocations(
      destination
        ? destination.split(' · ').filter(Boolean)
        : [],
    )

    setDraft('')
    setIsAdding(false)
    setIsRoadTrip(false)
  }, [destination])

  function selectLocation(location: LocationInfo) {
    if (!locations.includes(location.name)) {
      setLocations((items) => [...items, location.name])
    }

    setDraft('')
    setIsAdding(false)
  }

  function addLocation(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const location = draft.trim()

    if (!location) return

    if (!locations.includes(location)) {
      setLocations((items) => [...items, location])
    }

    setDraft('')
    setIsAdding(false)
  }

  const filteredSuggestions =
    draft.trim().length > 0
      ? SUGGESTIONS.filter((location) =>
          `${location.name} ${location.description}`
            .toLowerCase()
            .includes(draft.toLowerCase()),
        )
      : []

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="relative flex h-9 items-center justify-center">
        <h2 className="text-[20px] font-bold tracking-tight text-neutral-950">
          Where
        </h2>

        <button
          type="button"
          onClick={onClose}
          className="absolute left-0 grid h-9 w-9 place-items-center rounded-full text-[27px] leading-none text-neutral-950 transition hover:bg-neutral-100"
          aria-label="Close"
        >
          ×
        </button>
      </div>

      {/* Locations */}
      <div className="space-y-3">
        {locations.map((location, index) => {
          const info = getLocationInfo(location)

          return (
            <div
              key={`${location}-${index}`}
              className="flex min-h-[68px] items-center justify-between rounded-[13px] border border-neutral-200 bg-white px-2.5 py-2"
            >
              <div className="flex min-w-0 items-center gap-3">
                <img
                  src={info.image}
                  alt=""
                  className="h-12 w-12 shrink-0 rounded-[9px] object-cover"
                />

                <div className="min-w-0">
                  <div className="truncate text-[16px] font-bold leading-5 text-neutral-950">
                    {info.name}
                  </div>

                  <div className="mt-0.5 flex min-w-0 items-center gap-1 text-[14px] leading-5 text-neutral-700">
                    <MapPin
                      size={15}
                      strokeWidth={1.8}
                      className="shrink-0"
                    />

                    <span className="truncate">
                      {info.description}
                    </span>
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={() =>
                  setLocations((items) =>
                    items.filter(
                      (_, itemIndex) => itemIndex !== index,
                    ),
                  )
                }
                className="ml-3 grid h-8 w-8 shrink-0 place-items-center rounded-full text-[25px] leading-none text-neutral-950 transition hover:bg-neutral-100"
                aria-label={`Remove ${location}`}
              >
                ×
              </button>
            </div>
          )
        })}

        {/* Location input */}
        {isAdding && (
          <div className="relative">
            <form onSubmit={addLocation}>
              <input
                autoFocus
                value={draft}
                onChange={(event) =>
                  setDraft(event.target.value)
                }
                placeholder="Location"
                className={`${fieldClass} h-[52px] rounded-[26px] border-neutral-300 px-4 text-[16px] outline-none focus:border-neutral-950 focus:ring-0`}
              />

              {draft.length > 0 && (
                <button
                  type="button"
                  onClick={() => setDraft('')}
                  className="absolute right-3 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-full bg-neutral-200 text-[18px] leading-none text-neutral-500"
                  aria-label="Clear"
                >
                  ×
                </button>
              )}
            </form>

            {/* Suggestions */}
            {filteredSuggestions.length > 0 && (
              <div className="absolute left-0 right-0 top-[60px] z-20 overflow-hidden rounded-[13px] border border-neutral-200 bg-white p-2 shadow-[0_8px_24px_rgba(0,0,0,0.12)]">
                {filteredSuggestions.map((suggestion) => (
                  <button
                    key={suggestion.name}
                    type="button"
                    onClick={() =>
                      selectLocation(suggestion)
                    }
                    className="flex w-full items-center gap-3 rounded-[10px] px-3 py-2.5 text-left transition hover:bg-neutral-100"
                  >
                    <img
                      src={suggestion.image}
                      alt=""
                      className="h-10 w-10 shrink-0 rounded-[7px] object-cover"
                    />

                    <span className="min-w-0 truncate text-[15px] font-medium text-neutral-900">
                      {suggestion.name},{' '}
                      {suggestion.description}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Add location + Road trip */}
      <div className="flex items-center justify-between">
        {!isAdding ? (
          <button
            type="button"
            onClick={() => setIsAdding(true)}
            className="rounded-full bg-neutral-100 px-4 py-2.5 text-[14px] font-semibold text-neutral-900 transition hover:bg-neutral-200"
          >
            + Add location
          </button>
        ) : (
          <div />
        )}

        <div className="flex items-center gap-2">
          <span className="text-[14px] font-medium text-neutral-900">
            Road trip?
          </span>

          <button
            type="button"
            role="switch"
            aria-checked={isRoadTrip}
            onClick={() =>
              setIsRoadTrip((value) => !value)
            }
            className={`relative h-[26px] w-[44px] rounded-full transition-colors ${
              isRoadTrip
                ? 'bg-neutral-950'
                : 'bg-neutral-300'
            }`}
          >
            <span
              className={`absolute top-[3px] h-5 w-5 rounded-full bg-white shadow-sm transition-transform ${
                isRoadTrip
                  ? 'translate-x-[21px]'
                  : 'translate-x-[3px]'
              }`}
            />
          </button>
        </div>
      </div>

      {/* Save */}
      <div className="flex justify-end pt-1">
        <button
          type="button"
          disabled={locations.length === 0}
          onClick={() =>
            onSave(locations.join(' · '))
          }
          className={`${actionClass} h-[44px] min-w-[181px] rounded-full px-8 text-[15px] font-semibold disabled:cursor-not-allowed`}
        >
          Save
        </button>
      </div>
    </div>
  )
}