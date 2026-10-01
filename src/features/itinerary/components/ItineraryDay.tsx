import type { Stop } from '../data'
import { imageUrl } from '../data'
import {
  ChevronLeft,
  ChevronRight,
  Edit3,
  MessageCircle,
  MoreHorizontal,
  Send,
  Trash2,
  X,
} from 'lucide-react'

type Props = {
  day: number
  stops: Stop[]
  showDistances: boolean
  activeMenu: string | null
  activeComment: string | null
  comments: Record<string, string[]>
  commentDraft: string

  onOpenAddPlace: (day: number) => void
  onToggleMenu: (stopId: string) => void
  onRemoveStop: (stopId: string) => void
  onToggleComment: (stopId: string) => void
  onCommentDraftChange: (value: string) => void
  onAddComment: (stopId: string) => void

  onEditStop: (stopId: string) => void
  onMoveStop: (
    stopId: string,
    direction: 'previous' | 'next',
  ) => void
}

export function ItineraryDay({
  day,
  stops,
  showDistances,
  activeMenu,
  activeComment,
  comments,
  commentDraft,
  onOpenAddPlace,
  onToggleMenu,
  onRemoveStop,
  onToggleComment,
  onCommentDraftChange,
  onAddComment,
  onEditStop,
  onMoveStop,
}: Props) {
  return (
    <section className="mb-10">
      {/* Day header */}
      <div className="mb-4 flex items-center gap-3">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-neutral-950 text-sm font-semibold text-white shadow-sm">
          {day}
        </div>

        <div>
          <h3 className="text-base font-semibold text-neutral-900">
            Day {day}
          </h3>

          <p className="mt-0.5 text-sm text-neutral-500">
            Da Lat, Vietnam
          </p>
        </div>
      </div>

      {/* Timeline */}
      <div className="relative ml-5 border-l border-neutral-200 pl-6 sm:ml-6 sm:pl-8">
        {stops.map((stop) => {
          const stopComments = comments[stop.id] ?? []
          const commentCount = stopComments.length

          const isMenuOpen = activeMenu === stop.id
          const isCommentOpen = activeComment === stop.id

          return (
            <div
              key={stop.id}
              className="relative mb-4"
            >
              {/* Timeline dot */}
              <span className="absolute -left-[31px] top-8 h-3 w-3 rounded-full border-[3px] border-white bg-neutral-400 shadow-sm sm:-left-[39px]" />

              {/* Place + comment wrapper */}
              <div className="relative">
                {/* Place card */}
                <article
                  className={`group relative rounded-2xl border bg-white transition-all duration-200 ${
                    isMenuOpen || isCommentOpen
                      ? 'border-neutral-300 shadow-sm'
                      : 'border-neutral-200 hover:border-neutral-300 hover:shadow-md'
                  }`}
                >
                  <div className="flex gap-4 p-4">
                    {/* Image */}
                    <img
                      src={imageUrl(stop.image)}
                      alt=""
                      className="h-24 w-24 shrink-0 rounded-xl object-cover sm:h-28 sm:w-36"
                    />

                    {/* Content */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <h4 className="truncate text-base font-semibold text-neutral-900">
                            {stop.name}
                          </h4>

                          <div className="mt-1.5 flex items-center gap-2 text-sm text-neutral-500">
                            <span>{stop.start}</span>
                            <span className="text-neutral-300">
                              →
                            </span>
                            <span>{stop.end}</span>
                          </div>

                          {showDistances && stop.distance && (
                            <div className="mt-2 inline-flex rounded-full bg-neutral-50 px-2.5 py-1 text-xs text-neutral-500">
                              {stop.distance} to next stop
                            </div>
                          )}
                        </div>

                        {/* Hover actions */}
                        <div
                          className={`relative flex shrink-0 items-center gap-1 transition-opacity duration-150 ${
                            isMenuOpen ||
                            isCommentOpen ||
                            commentCount > 0
                              ? 'opacity-100'
                              : 'opacity-0 group-hover:opacity-100'
                          }`}
                        >
                          {/* Comment */}
                          <button
                            type="button"
                            aria-label={`Comments on ${stop.name}`}
                            onClick={() =>
                              onToggleComment(stop.id)
                            }
                            className={`inline-flex h-9 min-w-9 items-center justify-center gap-1.5 rounded-full px-2.5 transition-all ${
                              isCommentOpen
                                ? 'bg-neutral-950 text-white shadow-sm'
                                : 'text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900'
                            }`}
                          >
                            <MessageCircle
                              size={17}
                              strokeWidth={1.9}
                            />

                            {commentCount > 0 && (
                              <span
                                className={`text-xs font-medium leading-none ${
                                  isCommentOpen
                                    ? 'text-white'
                                    : 'text-neutral-600'
                                }`}
                              >
                                {commentCount}
                              </span>
                            )}
                          </button>

                          {/* More */}
                          <div className="relative">
                            <button
                              type="button"
                              aria-label={`Actions for ${stop.name}`}
                              onClick={() =>
                                onToggleMenu(stop.id)
                              }
                              className={`grid h-9 w-9 place-items-center rounded-full transition ${
                                isMenuOpen
                                  ? 'bg-neutral-100 text-neutral-900'
                                  : 'text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900'
                              }`}
                            >
                              <MoreHorizontal
                                size={18}
                                strokeWidth={1.9}
                              />
                            </button>

                            {/* Action menu beside ... */}
                            {isMenuOpen && (
                              <div className="absolute right-0 top-11 z-50 w-52 rounded-xl border border-neutral-200 bg-white p-1.5 shadow-xl">
                                {/* Edit details */}
                                <button
                                  type="button"
                                  onClick={() =>
                                    onEditStop(stop.id)
                                  }
                                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-neutral-700 transition hover:bg-neutral-50"
                                >
                                  <Edit3
                                    size={16}
                                    strokeWidth={1.8}
                                    className="shrink-0 text-neutral-500"
                                  />

                                  <span>Edit details</span>
                                </button>

                                {/* Move previous */}
                                <button
                                  type="button"
                                  disabled={day <= 1}
                                  onClick={() =>
                                    onMoveStop(
                                      stop.id,
                                      'previous',
                                    )
                                  }
                                  className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition ${
                                    day <= 1
                                      ? 'cursor-not-allowed text-neutral-300'
                                      : 'text-neutral-700 hover:bg-neutral-50'
                                  }`}
                                >
                                  <ChevronLeft
                                    size={17}
                                    strokeWidth={1.8}
                                    className={
                                      day <= 1
                                        ? 'text-neutral-300'
                                        : 'text-neutral-500'
                                    }
                                  />

                                  <span>
                                    Move to previous day
                                  </span>
                                </button>

                                {/* Move next */}
                                <button
                                  type="button"
                                  disabled={day >= 4}
                                  onClick={() =>
                                    onMoveStop(
                                      stop.id,
                                      'next',
                                    )
                                  }
                                  className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition ${
                                    day >= 4
                                      ? 'cursor-not-allowed text-neutral-300'
                                      : 'text-neutral-700 hover:bg-neutral-50'
                                  }`}
                                >
                                  <ChevronRight
                                    size={17}
                                    strokeWidth={1.8}
                                    className={
                                      day >= 4
                                        ? 'text-neutral-300'
                                        : 'text-neutral-500'
                                    }
                                  />

                                  <span>
                                    Move to next day
                                  </span>
                                </button>

                                <div className="my-1 border-t border-neutral-100" />

                                {/* Remove */}
                                <button
                                  type="button"
                                  onClick={() =>
                                    onRemoveStop(stop.id)
                                  }
                                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-red-600 transition hover:bg-red-50"
                                >
                                  <Trash2
                                    size={16}
                                    strokeWidth={1.8}
                                  />

                                  <span>Remove</span>
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </article>

                {/* Comment area */}
                {isCommentOpen && (
                  <div className="mt-1.5 overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-sm">
                    {/* Comment header */}
                    <div className="flex items-center justify-between border-b border-neutral-100 px-3 py-2">
                      <div className="flex min-w-0 items-center gap-2">
                        <MessageCircle
                          size={15}
                          className="shrink-0 text-neutral-500"
                        />

                        <span className="truncate text-xs font-medium text-neutral-600">
                          Comments on {stop.name}
                        </span>

                        {commentCount > 0 && (
                          <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-[10px] font-medium text-neutral-500">
                            {commentCount}
                          </span>
                        )}
                      </div>

                      {/* Close comment */}
                      <button
                        type="button"
                        aria-label="Close comments"
                        onClick={() =>
                          onToggleComment(stop.id)
                        }
                        className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-neutral-400 transition hover:bg-neutral-100 hover:text-neutral-800"
                      >
                        <X size={15} />
                      </button>
                    </div>

                    {/* Existing comments */}
                    {commentCount > 0 && (
                      <div className="space-y-1.5 px-3 pt-2.5">
                        {stopComments.map(
                          (comment, index) => (
                            <div
                              key={index}
                              className="rounded-xl bg-neutral-50 px-3.5 py-2.5 text-sm text-neutral-700"
                            >
                              {comment}
                            </div>
                          ),
                        )}
                      </div>
                    )}

                    {/* Add comment */}
                    <form
                      onSubmit={(event) => {
                        event.preventDefault()
                        onAddComment(stop.id)
                      }}
                      className={`flex items-center gap-2.5 p-3 ${
                        commentCount > 0
                          ? 'pt-2.5'
                          : ''
                      }`}
                    >
                      {/* Avatar */}
                      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-neutral-100 text-[11px] font-semibold text-neutral-600">
                        AL
                      </div>

                      {/* Input */}
                      <input
                        value={commentDraft}
                        onChange={(event) =>
                          onCommentDraftChange(
                            event.target.value,
                          )
                        }
                        placeholder="Add a comment..."
                        autoFocus
                        className="h-10 min-w-0 flex-1 rounded-xl border border-neutral-200 bg-neutral-50 px-3.5 text-sm text-neutral-900 outline-none transition placeholder:text-neutral-400 focus:border-neutral-400 focus:bg-white"
                      />

                      {/* Send */}
                      <button
                        type="submit"
                        aria-label="Send comment"
                        disabled={!commentDraft.trim()}
                        className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-neutral-950 text-white transition hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-30"
                      >
                        <Send
                          size={16}
                          strokeWidth={1.9}
                        />
                      </button>
                    </form>
                  </div>
                )}
              </div>
            </div>
          )
        })}

        {/* Add place */}
        <button
          type="button"
          onClick={() => onOpenAddPlace(day)}
          className="group flex w-full items-center gap-3 rounded-2xl border border-dashed border-neutral-300 bg-white px-4 py-3.5 text-left transition hover:border-neutral-500 hover:bg-neutral-50"
        >
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-neutral-200 bg-white text-lg text-neutral-500 transition group-hover:border-neutral-400 group-hover:text-neutral-900">
            +
          </span>

          <div>
            <p className="text-sm font-medium text-neutral-700">
              Add a place
            </p>

            <p className="text-xs text-neutral-400">
              Add another stop to Day {day}
            </p>
          </div>
        </button>
      </div>
    </section>
  )
}

