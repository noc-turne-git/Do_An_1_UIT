import { useMemo, useState } from 'react'
import { MessageSquarePlus, MapPlus, Search } from 'lucide-react'
import { useTrips } from '../../trip'

export function ChatsOverlay({
  onNavigate,
}: {
  onNavigate: (to: string) => void
}) {
  // =========================
  // 1. Search state
  // =========================

  const [query, setQuery] = useState('')

  // =========================
  // 2. Get trips
  // =========================

  const { data: trips = [] } = useTrips()

  // =========================
  // 3. Get chats from all trips
  // =========================

  const chats = useMemo(() => {
    return trips
      .flatMap((trip) =>
        trip.chats.map((chat) => ({
          tripId: trip.id,
          chatId: chat.id,
          name: chat.name,
          trip: trip.name,
        })),
      )
      .filter((chat) =>
        `${chat.name} ${chat.trip}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      )
  }, [trips, query])

  // =========================
  // 4. Filter trips
  // =========================

  const visibleTrips = trips.filter((trip) =>
    trip.name.toLowerCase().includes(query.toLowerCase()),
  )

  // =========================
  // 5. UI
  // =========================

  return (
    <div className="flex h-full flex-col overflow-y-auto p-5">
      {/* =========================
          Search
          ========================= */}

      <div className="relative">
        <Search className="absolute left-3 top-4 h-4 w-4 text-neutral-800" />

        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Search trips and chats"
          placeholder="Search..."
          className="w-full rounded-xl bg-neutral-200 py-3 pl-9 pr-3 text-sm outline-none transition-colors focus:border focus:border-neutral-800 focus:bg-white"
        />
      </div>

      {/* =========================
          Actions
          ========================= */}

      <div className="my-4 flex flex-col gap-1">
        {/* New chat */}

        <button
          onClick={() => onNavigate('/chats')}
          className="group flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-md font-semibold text-neutral-900 transition-colors hover:bg-neutral-200"
        >
          <span className="grid h-6 w-6 shrink-0 place-items-center rounded-lg text-neutral-600">
            <MessageSquarePlus
              aria-hidden="true"
              className="h-5 w-5"
            />
          </span>

          <span>New chat</span>
        </button>

        {/* New trip */}

        <button
          onClick={() => onNavigate('/chats?newTrip=1')}
          className="group flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-md font-semibold text-neutral-900 transition-colors hover:bg-neutral-200"
        >
          <span className="grid h-6 w-6 shrink-0 place-items-center rounded-lg text-neutral-600">
            <MapPlus
              aria-hidden="true"
              className="h-5 w-5"
            />
          </span>

          <span>New trip</span>
        </button>
      </div>

      {/* =========================
          Trips
          ========================= */}

      <h2 className="mb-2 mt-3 text-xs font-semibold uppercase tracking-wider text-neutral-500">
        Trips
      </h2>

      {visibleTrips.map((trip) => (
        <button
          key={trip.id}
          onClick={() => onNavigate(`/trips/${trip.id}`)}
          className="group flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-md font-semibold text-neutral-900 transition-colors hover:bg-neutral-200"
        >
          {/* Trip image */}

          <img
            src={trip.cover}
            alt=""
            className="h-9 w-9 shrink-0 rounded-lg object-cover"
          />

          {/* Trip name */}

          <span>{trip.name}</span>
        </button>
      ))}

      {/* =========================
          Chats
          ========================= */}

      <h2 className="mb-2 mt-6 text-xs font-semibold uppercase tracking-wider text-neutral-500">
        Chats
      </h2>

      {chats.map((chat) => (
        <button
          key={`${chat.tripId}-${chat.chatId}`}
          onClick={() =>
            onNavigate(
              `/trips/${chat.tripId}?chatId=${chat.chatId}`,
            )
          }
          className="group flex w-full items-center rounded-xl px-3 py-2 text-left transition-colors hover:bg-neutral-200"
        >
          <div>
            <span className="block text-md font-semibold text-neutral-900">
              {chat.name}
            </span>

            <span className="mt-1 block text-xs font-normal text-neutral-500">
              {chat.trip}
            </span>
          </div>
        </button>
      ))}
    </div>
  )
}
