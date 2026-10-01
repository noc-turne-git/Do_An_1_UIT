import { useState } from 'react'
import { Check, Plus, X } from 'lucide-react'

export function PreferencesBoardRefactored() {
  const [suggestions, setSuggestions] = useState([
    'Prefer short travel distances',
    'Avoid rainy days',
  ])

  const [preferences, setPreferences] = useState([
    'Local food and coffee shops',
  ])

  const [draft, setDraft] = useState('')

  const add = () => {
    const value = draft.trim()

    if (value && !preferences.includes(value)) {
      setPreferences((items) => [...items, value])
    }

    setDraft('')
  }

  const acceptSuggestion = (item: string) => {
    setPreferences((items) =>
      items.includes(item) ? items : [...items, item],
    )

    setSuggestions((items) =>
      items.filter((value) => value !== item),
    )
  }

  const dismissSuggestion = (item: string) => {
    setSuggestions((items) =>
      items.filter((value) => value !== item),
    )
  }

  return (
    <section className="w-full max-w-3xl">
      {/* Header */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold tracking-tight text-neutral-950">
          Trip preferences
        </h2>

        <p className="mt-2 max-w-xl text-sm leading-6 text-neutral-500">
          Tell your travel assistant what matters to you.
          These preferences will help personalize your trip.
        </p>
      </div>

      {/* Suggested preferences */}
      {suggestions.length > 0 && (
        <div className="mb-8">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
              Suggested for this trip
            </h3>

            <span className="text-xs text-neutral-400">
              Based on your trip
            </span>
          </div>

          <div className="space-y-2">
            {suggestions.map((item) => (
              <div
                key={item}
                className="group flex items-center gap-3 rounded-2xl border border-neutral-200 bg-white px-4 py-3.5 shadow-sm transition hover:border-neutral-300 hover:shadow-md"
              >
                {/* Icon */}
                <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-amber-50 text-amber-600">
                  <span className="text-sm">✦</span>
                </div>

                {/* Text */}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-neutral-800">
                    {item}
                  </p>

                  <p className="mt-0.5 text-xs text-neutral-400">
                    Suggested based on your trip
                  </p>
                </div>

                {/* Accept */}
                <button
                  type="button"
                  onClick={() => acceptSuggestion(item)}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-neutral-950 px-4 py-2 text-xs font-medium text-white transition hover:bg-neutral-800"
                >
                  <Check size={14} />
                  Accept
                </button>

                {/* Dismiss */}
                <button
                  type="button"
                  aria-label={`Dismiss preference: ${item}`}
                  onClick={() => dismissSuggestion(item)}
                  className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-neutral-400 transition hover:bg-neutral-100 hover:text-neutral-700"
                >
                  <X size={15} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Your preferences */}
      <div>
        <div className="mb-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
            Your preferences
          </h3>
        </div>

        {/* Add preference */}
        {/* <form
          onSubmit={(event) => {
            event.preventDefault()
            add()
          }}
          className="mb-5 flex items-center gap-2 rounded-2xl border border-neutral-200 bg-white p-1.5 shadow-sm transition focus-within:border-neutral-400 focus-within:ring-2 focus-within:ring-neutral-100"
        >
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="e.g. We prefer hotels with free breakfast"
            className="min-w-0 flex-1 bg-transparent px-3 py-2.5 text-sm text-neutral-900 outline-none placeholder:text-neutral-400"
          />

          <button
            type="submit"
            aria-label="Add trip preference"
            disabled={!draft.trim()}
            className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-neutral-950 text-white transition hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-30"
          >
            <Plus size={18} />
          </button>
        </form> */}

        <form
          onSubmit={(event) => {
            event.preventDefault()
            add()
          }}
          className="mb-5 flex items-center gap-2 rounded-2xl border border-neutral-200 bg-white px-2 py-2 shadow-sm transition focus-within:border-neutral-300 focus-within:ring-2 focus-within:ring-neutral-100"
        >
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="e.g. We prefer hotels with free breakfast"
            className="min-w-0 flex-1 bg-transparent px-3 py-2 text-sm text-neutral-900 outline-none placeholder:text-neutral-400"
          />

          <button
            type="submit"
            aria-label="Add trip preference"
            disabled={!draft.trim()}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-neutral-200 bg-white text-neutral-700 shadow-sm transition hover:border-neutral-300 hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-30"
          >
            <Plus size={17} strokeWidth={2} />
          </button>
        </form>

        {/* Preference chips */}
        {preferences.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {preferences.map((item) => (
              <div
                key={item}
                className="group inline-flex items-center gap-2 rounded-full border border-neutral-200 bg-neutral-50 py-2 pl-4 pr-2 text-sm text-neutral-700 transition hover:border-neutral-300 hover:bg-neutral-100"
              >
                <span>{item}</span>

                <button
                  type="button"
                  aria-label={`Remove ${item}`}
                  onClick={() =>
                    setPreferences((items) =>
                      items.filter(
                        (value) => value !== item,
                      ),
                    )
                  }
                  className="grid h-6 w-6 place-items-center rounded-full text-neutral-400 transition hover:bg-white hover:text-neutral-700"
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-neutral-200 px-6 py-8 text-center">
            <p className="text-sm text-neutral-400">
              No preferences added yet.
            </p>

            <p className="mt-1 text-xs text-neutral-400">
              Add something to help personalize your trip.
            </p>
          </div>
        )}
      </div>
    </section>
  )
}