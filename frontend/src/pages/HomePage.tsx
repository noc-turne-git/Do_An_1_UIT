import { Link } from 'react-router-dom'
import { TripCard, useTrips } from '../features/trip'

export function HomePage() {
  const { data: trips = [] } = useTrips()

  return (
    <div className="mx-auto max-w-7xl p-6 sm:p-10">
      <header className="mb-10">
        <p className="text-sm text-neutral-500">
          Your travel planner
        </p>

        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          Where to next?
        </h1>

        <p className="mt-3 max-w-xl text-neutral-500">
          Explore new places, save ideas, and plan a trip together.
        </p>

        <div className="mt-6 flex gap-3">
          <Link
            to="/explore"
            className="rounded-xl bg-neutral-900 px-5 py-3 text-sm font-medium text-white"
          >
            Explore places
          </Link>

          <Link
            to="/chats"
            className="rounded-xl border px-5 py-3 text-sm font-medium"
          >
            Plan with AI
          </Link>
        </div>
      </header>

      <section className="mb-12">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold">
            Your trips
          </h2>

          <Link
            to="/trips"
            className="text-sm text-neutral-500"
          >
            See all →
          </Link>
        </div>

        {trips.length ? (
          <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {trips.slice(0, 3).map((trip) => (
              <TripCard
                key={trip.id}
                trip={trip}
              />
            ))}
          </div>
        ) : (
          <p className="rounded-2xl border border-dashed p-8 text-neutral-500">
            Your planned trips will appear here.
          </p>
        )}
      </section>

      <section>
        <h2 className="mb-4 text-xl font-semibold">
          Continue planning
        </h2>

        <Link
          to="/chats"
          className="block max-w-xl rounded-2xl border p-5 hover:bg-neutral-50"
        >
          <span className="text-xl">✦</span>

          <strong className="ml-3">
            Start a travel conversation
          </strong>

          <span className="mt-2 block text-sm text-neutral-500">
            Ask for ideas and build an itinerary with your assistant.
          </span>
        </Link>
      </section>
    </div>
  )
}