import { useState } from 'react'
import {
  ArrowUpDown,
  MoreHorizontal,
  Route,
} from 'lucide-react'
import { AddPlaceModal } from './AddPlaceModal'
import { ItineraryDay } from './ItineraryDay'
import { initialStops, suggestions } from '../data'

type Props = {
  duration: string
}

function addOneHour(time: string) {
  const [hour, minute] = time.split(':').map(Number)

  const end = new Date(2000, 0, 1, hour, minute + 60)

  return `${String(end.getHours()).padStart(2, '0')}:${String(
    end.getMinutes(),
  ).padStart(2, '0')}`
}

export function ItineraryBoardRefactored({ duration }: Props) {
  const [stops, setStops] = useState(initialStops)

  const [showDistances, setShowDistances] = useState(true)

  const [menu, setMenu] = useState<string | null>(null)

  const [commentFor, setCommentFor] = useState<string | null>(null)

  const [comments, setComments] = useState<Record<string, string[]>>({})

  const [commentDraft, setCommentDraft] = useState('')

  const [addDay, setAddDay] = useState<number | null>(null)

  const [savedPlaces] = useState<string[]>([])

  function openAddPlace(day: number) {
    setAddDay(day)
    setMenu(null)
  }

  function addStop(
    name: string,
    image = suggestions[0].image,
    start = '15:00',
  ) {
    if (addDay === null) return

    setStops((items) => [
      ...items,
      {
        id: `new-${Date.now()}`,
        day: addDay,
        name,
        start,
        end: addOneHour(start),
        distance: '',
        image,
      },
    ])

    setAddDay(null)
  }

  function addComment(stopId: string) {
    const comment = commentDraft.trim()

    if (!comment) return

    setComments((items) => ({
      ...items,
      [stopId]: [...(items[stopId] ?? []), comment],
    }))

    setCommentDraft('')
  }

  function removeStop(stopId: string) {
    setStops((items) =>
      items.filter((stop) => stop.id !== stopId),
    )

    setMenu(null)

    if (commentFor === stopId) {
      setCommentFor(null)
    }
  }

  function editStop(stopId: string) {
    /*
     * Nối hàm này với Edit Details modal hiện có của bạn.
     *
     * Ví dụ:
     * setEditingStop(stopId)
     * setEditModalOpen(true)
     */
    console.log('Edit details:', stopId)

    setMenu(null)
  }

  function moveStop(
    stopId: string,
    direction: 'previous' | 'next',
  ) {
    setStops((items) =>
      items.map((stop) => {
        if (stop.id !== stopId) {
          return stop
        }

        const newDay =
          direction === 'previous'
            ? Math.max(1, stop.day - 1)
            : Math.min(4, stop.day + 1)

        return {
          ...stop,
          day: newDay,
        }
      }),
    )

    setMenu(null)
  }

  function sortByStartTime() {
    setStops((items) =>
      [...items].sort((left, right) =>
        left.start.localeCompare(right.start),
      ),
    )

    setMenu(null)
  }

  const totalDays = Math.max(
    1,
    ...stops.map((stop) => stop.day),
  )

  return (
    <section className="mx-auto w-full max-w-5xl">
      {/* Header */}
      <header className="mb-8">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-neutral-400">
              Your trip
            </p>

            <h2 className="text-3xl font-semibold tracking-tight text-neutral-950">
              Itinerary
            </h2>

            <p className="mt-1.5 text-sm text-neutral-500">
              {duration}
            </p>
          </div>

          {/* Header actions */}
          <div className="relative flex items-center gap-2">
            <button
              type="button"
              onClick={() =>
                setShowDistances((value) => !value)
              }
              className={`inline-flex h-10 items-center gap-2 rounded-full border px-4 text-sm font-medium transition ${
                showDistances
                  ? 'border-neutral-950 bg-neutral-950 text-white'
                  : 'border-neutral-200 bg-white text-neutral-600 hover:border-neutral-400'
              }`}
            >
              <Route size={15} />

              <span>Distances</span>

              <span
                className={`rounded-full px-1.5 py-0.5 text-[10px] ${
                  showDistances
                    ? 'bg-white/15 text-white'
                    : 'bg-neutral-100 text-neutral-500'
                }`}
              >
                {showDistances ? 'On' : 'Off'}
              </span>
            </button>

            <button
              type="button"
              aria-label="Itinerary actions"
              onClick={() =>
                setMenu(menu === 'all' ? null : 'all')
              }
              className={`grid h-10 w-10 place-items-center rounded-full border transition ${
                menu === 'all'
                  ? 'border-neutral-300 bg-neutral-100'
                  : 'border-neutral-200 bg-white hover:bg-neutral-50'
              }`}
            >
              <MoreHorizontal size={18} />
            </button>

            {menu === 'all' && (
              <div className="absolute right-0 top-12 z-30 w-48 rounded-xl border border-neutral-200 bg-white p-1.5 shadow-lg">
                <button
                  type="button"
                  onClick={sortByStartTime}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm text-neutral-700 transition hover:bg-neutral-50"
                >
                  <ArrowUpDown size={15} />

                  <span>Sort by start time</span>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Summary */}
        <div className="mt-6 flex items-center gap-3 rounded-2xl border border-neutral-200 bg-neutral-50 px-4 py-3">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-white shadow-sm">
            <Route
              size={16}
              className="text-neutral-600"
            />
          </div>

          <div>
            <p className="text-sm font-medium text-neutral-800">
              {stops.length} stops planned
            </p>

            <p className="text-xs text-neutral-500">
              Your itinerary across {totalDays} days
            </p>
          </div>
        </div>
      </header>

      {/* Days */}
      <div>
        {[1, 2, 3, 4].map((day) => (
          <ItineraryDay
            key={day}
            day={day}
            stops={stops.filter(
              (stop) => stop.day === day,
            )}
            showDistances={showDistances}
            activeMenu={menu}
            activeComment={commentFor}
            comments={comments}
            commentDraft={commentDraft}
            onOpenAddPlace={openAddPlace}
            onToggleMenu={(stopId) =>
              setMenu(
                menu === stopId ? null : stopId,
              )
            }
            onRemoveStop={removeStop}
            onToggleComment={(stopId) => {
              setCommentFor(
                commentFor === stopId
                  ? null
                  : stopId,
              )

              setMenu(null)
            }}
            onCommentDraftChange={setCommentDraft}
            onAddComment={addComment}
            onEditStop={editStop}
            onMoveStop={moveStop}
          />
        ))}
      </div>

      {/* Add Place Modal */}
      <AddPlaceModal
        day={addDay}
        savedPlaces={savedPlaces}
        onClose={() => setAddDay(null)}
        onAddPlace={addStop}
      />
    </section>
  )
}
