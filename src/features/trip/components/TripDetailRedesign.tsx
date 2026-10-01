import { useState } from 'react'
import {
  ArrowLeft,
  MoreHorizontal,
  Send,
  Sparkles,
  Pencil,
  Star,
  Trash2,
} from 'lucide-react'
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom'
import { useAddTripChat, useTrip, useUpdateTrip } from '../hooks/useTrips'
import { TripWorkspace } from './TripWorkspace'
import { TripFieldModals } from './TripFieldModals'

export function TripDetailRedesign() {
  const { tripId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  const { data: trip, isLoading } = useTrip(tripId)
  const updateTrip = useUpdateTrip()
  const addTripChat = useAddTripChat()

  const [chatOverride, setChatOverride] = useState<
    string | null | undefined
  >(undefined)

  const [editing, setEditing] = useState<
    'Where' | 'When' | 'Who' | 'Budget' | null
  >(null)

  const [draft, setDraft] = useState('')
  const [sent, setSent] = useState<string[]>([])

  // Chat menu state
  const [openChatMenu, setOpenChatMenu] = useState<string | null>(null)

  const chatId =
    chatOverride === undefined
      ? searchParams.get('chatId')
      : chatOverride

  if (isLoading) {
    return <p className="p-8 text-slate-500">Loading trip...</p>
  }

  if (!trip) {
    return (
      <div className="p-8">
        <p>This trip could not be found.</p>

        <Link
          className="mt-3 inline-block underline"
          to="/trips"
        >
          Back to trips
        </Link>
      </div>
    )
  }

  const selected = trip.chats.find(
    (chat) => chat.id === chatId,
  )

  const mainChat =
    trip.chats.find((chat) => chat.main) ??
    trip.chats[0]

  const back = () => {
    if (!chatId) {
      navigate('/trips')
      return
    }

    setChatOverride(null)
    setOpenChatMenu(null)

    const next = new URLSearchParams(searchParams)
    next.delete('chatId')

    setSearchParams(next, { replace: true })
  }

  const submit = async (
    event: React.FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault()

    if (!draft.trim()) return

    const text = draft.trim()
    setDraft('')

    if (!chatId) {
      const updatedTrip = await addTripChat.mutateAsync({
        tripId: trip.id,
        firstMessage: text,
      })
      setChatOverride(updatedTrip.chats.at(-1)?.id ?? null)
      return
    }

    setSent((items) => [...items, text])
  }

  const summary = [
    ['Where', trip.destination.split(',')[0]],
    ['When', trip.duration],
    [
      'Who',
      `${trip.travelers.length} traveler${
        trip.travelers.length === 1
          ? ''
          : 's'
      }`,
    ],
    ['Budget', trip.budget],
  ] as const

  /*
   * ------------------------------------------------------------
   * CHAT ACTIONS
   * ------------------------------------------------------------
   *
   * Các action bên dưới hiện chỉ đóng menu.
   *
   * Khi bạn có hook/API cho chat:
   *
   * - Rename chat
   * - Set as main chat
   * - Delete chat
   *
   * chỉ cần gọi mutation tương ứng trong các handler này.
   */

  const handleRenameChat = (
    chatId: string,
  ) => {
    setOpenChatMenu(null)

    // TODO:
    // Mở Edit Chat Name modal hiện tại của bạn.
    //
    // Ví dụ:
    // setEditingChatId(chatId)
  }

  const handleSetMainChat = (
    chatId: string,
  ) => {
    setOpenChatMenu(null)

    // TODO:
    // Gọi API để set chat này làm main chat.
    //
    // Ví dụ:
    // setMainChatMutation.mutate({
    //   tripId: trip.id,
    //   chatId,
    // })
  }

  const handleDeleteChat = (
    chatId: string,
  ) => {
    setOpenChatMenu(null)

    // TODO:
    // Gọi API delete chat.
    //
    // Ví dụ:
    // deleteChatMutation.mutate({
    //   tripId: trip.id,
    //   chatId,
    // })
  }

  return (
    <div className="trip-layout flex h-screen min-h-0 flex-col overflow-hidden lg:flex-row">

      {/* =========================================================
          LEFT SIDEBAR
      ========================================================== */}

      <section
        className="
          trip-sidebar
          flex
          min-h-0
          w-full
          shrink-0
          flex-col
          overflow-hidden
          border-b
          border-slate-200/90
          bg-white
          lg:w-[410px]
          lg:border-b-0
          lg:border-r
        "
        aria-label="Trip details and chats"
      >
        <div className="flex min-h-0 flex-1 flex-col space-y-5 p-5 sm:p-6">

          {/* =====================================================
              HEADER
          ====================================================== */}

          <div className="flex items-center gap-3.5">
            <button
              type="button"
              onClick={back}
              aria-label="Go back"
              className="
                grid
                h-9
                w-9
                shrink-0
                place-items-center
                rounded-full
                border
                border-slate-200
                text-slate-500
                transition
                hover:bg-slate-50
                hover:text-slate-900
              "
            >
              <ArrowLeft className="h-4 w-4" />
            </button>

            <div className="min-w-0">
              <h1
                className="
                  truncate
                  text-xl
                  font-bold
                  tracking-tight
                  text-slate-900
                "
              >
                {trip.name}
              </h1>

              <p className="text-xs font-medium text-slate-500">
                {trip.destination}
              </p>
            </div>
          </div>

          {/* =====================================================
              TRIP SUMMARY
          ====================================================== */}

          <div
            className="
              grid
              grid-cols-4
              items-center
              divide-x
              divide-slate-200/80
              rounded-full
              border
              border-slate-200
              bg-slate-50/80
              px-2
              py-2
              text-center
              shadow-sm
            "
          >
            {summary.map(
              ([label, value]) => (
                <button
                  type="button"
                  key={label}
                  onClick={() =>
                    setEditing(label)
                  }
                  title={`${label}: ${value}`}
                  className="
                    min-w-0
                    truncate
                    px-1
                    text-[11px]
                    font-semibold
                    text-slate-700
                    hover:text-slate-950
                  "
                >
                  {value}
                </button>
              ),
            )}
          </div>

          {/* =====================================================
              ALL CHATS VIEW
          ====================================================== */}

          {!chatId ? (
            <div className="min-h-0 flex-1 space-y-5 overflow-y-auto">
              {/* =================================================
                  TRIP INSIGHT
              ================================================== */}

              <div
                className="
                  rounded-2xl
                  border
                  border-amber-200/80
                  bg-gradient-to-br
                  from-amber-50
                  via-amber-50/70
                  to-orange-50/50
                  p-4
                  shadow-sm
                "
              >
                <span
                  className="
                    mb-2
                    inline-flex
                    items-center
                    gap-1.5
                    rounded-full
                    bg-amber-100
                    px-2.5
                    py-1
                    text-[10px]
                    font-bold
                    uppercase
                    tracking-wider
                    text-amber-800
                  "
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  Trip insight
                </span>

                <p className="text-[13px] leading-relaxed text-slate-700">
                  {mainChat?.messages[0]?.text}
                </p>
              </div>

              {/* =================================================
                  ASK ANYTHING INPUT
              ================================================== */}

              <form
                onSubmit={submit}
                className="
                  flex
                  w-full
                  items-center
                  gap-3
                  rounded-2xl
                  border
                  border-slate-300
                  bg-white
                  px-4
                  py-3
                  shadow-sm
                  transition-all
                  focus-within:border-slate-500
                  focus-within:shadow-md
                "
              >
                <input
                  value={draft}
                  onChange={(event) =>
                    setDraft(event.target.value)
                  }
                  placeholder="Ask anything else..."
                  className="
                    min-w-0
                    flex-1
                    border-0
                    bg-transparent
                    p-0
                    text-sm
                    font-medium
                    text-slate-800
                    placeholder:text-slate-400
                    outline-none
                    focus:border-0
                    focus:outline-none
                    focus:ring-0
                  "
                />

                <button
                  type="submit"
                  aria-label="Send"
                  className="
                    flex
                    h-9
                    w-9
                    shrink-0
                    items-center
                    justify-center
                    rounded-full
                    text-slate-400
                    transition
                    hover:bg-slate-100
                    hover:text-slate-800
                  "
                >
                  <Send className="h-4 w-4" />
                </button>
              </form>

              {/* =================================================
                  SENT MESSAGES
              ================================================== */}

              {/* =================================================
                  TRIP CHATS
              ================================================== */}

              <div className="space-y-3 pt-1">
                <div className="flex items-center justify-between">
                  <h2
                    className="
                      text-[11px]
                      font-bold
                      uppercase
                      tracking-wider
                      text-slate-400
                    "
                  >
                    Trip chats
                  </h2>
                </div>

                {trip.chats.map((chat) => (
                  /*
                   * Dùng div thay vì button ở ngoài.
                   * Điều này tránh nested <button>
                   * vì bên trong có button "..."
                   */
                  <div
                    key={chat.id}
                    className="relative"
                  >
                    {/* Chat item */}

                    <button
                      type="button"
                      onClick={() => {
                        setChatOverride(
                          chat.id,
                        )
                        setOpenChatMenu(null)
                      }}
                      className={`
                        group
                        flex
                        w-full
                        items-center
                        justify-between
                        rounded-xl
                        border
                        p-3
                        text-left
                        transition
                        ${
                          chat.main
                            ? 'border-slate-200/90 bg-slate-50/70'
                            : 'border-transparent hover:border-slate-200/70 hover:bg-slate-50/80'
                        }
                      `}
                    >
                      <span className="min-w-0 space-y-1 pr-2">
                        <span className="flex items-center gap-2">
                          <span
                            className="
                              truncate
                              text-xs
                              font-semibold
                              text-slate-900
                            "
                          >
                            {chat.name}
                          </span>

                          {chat.main && (
                            <span
                              className="
                                rounded-full
                                bg-slate-900
                                px-1.5
                                py-0.5
                                text-[9px]
                                font-bold
                                text-white
                              "
                            >
                              Main
                            </span>
                          )}
                        </span>

                        <span
                          className="
                            block
                            text-[11px]
                            font-medium
                            text-slate-400
                          "
                        >
                          {chat.updated}
                        </span>
                      </span>
                    </button>

                    {/* =================================================
                        MORE BUTTON
                    ================================================== */}

                    <button
                      type="button"
                      aria-label={`Chat options for ${chat.name}`}
                      onClick={(event) => {
                        event.stopPropagation()

                        setOpenChatMenu(
                          (current) =>
                            current === chat.id
                              ? null
                              : chat.id,
                        )
                      }}
                      className="
                        absolute
                        right-2
                        top-1/2
                        z-20
                        flex
                        h-8
                        w-8
                        -translate-y-1/2
                        items-center
                        justify-center
                        rounded-lg
                        text-slate-400
                        transition
                        hover:bg-slate-200/80
                        hover:text-slate-800
                      "
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </button>

                    {/* =================================================
                        CHAT OPTIONS DROPDOWN
                    ================================================== */}

                    {openChatMenu === chat.id && (
                      <div
                        className="
                          absolute
                          right-2
                          top-full
                          z-50
                          mt-1.5
                          w-52
                          overflow-hidden
                          rounded-xl
                          border
                          border-slate-200
                          bg-white
                          p-1.5
                          shadow-xl
                          ring-1
                          ring-black/5
                        "
                        onClick={(event) =>
                          event.stopPropagation()
                        }
                      >
                        {/* Rename */}

                        <button
                          type="button"
                          onClick={() =>
                            handleRenameChat(
                              chat.id,
                            )
                          }
                          className="
                            flex
                            w-full
                            items-center
                            gap-3
                            rounded-lg
                            px-3
                            py-2.5
                            text-left
                            text-sm
                            font-medium
                            text-slate-700
                            transition
                            hover:bg-slate-100
                          "
                        >
                          <Pencil className="h-4 w-4 text-slate-500" />

                          <span>
                            Rename chat
                          </span>
                        </button>

                        {/* Set as main */}

                        {!chat.main && (
                          <button
                            type="button"
                            onClick={() =>
                              handleSetMainChat(
                                chat.id,
                              )
                            }
                            className="
                              flex
                              w-full
                              items-center
                              gap-3
                              rounded-lg
                              px-3
                              py-2.5
                              text-left
                              text-sm
                              font-medium
                              text-slate-700
                              transition
                              hover:bg-slate-100
                            "
                          >
                            <Star className="h-4 w-4 text-slate-500" />

                            <span>
                              Set as main chat
                            </span>
                          </button>
                        )}

                        {/* Delete */}

                        <button
                          type="button"
                          onClick={() =>
                            handleDeleteChat(
                              chat.id,
                            )
                          }
                          className="
                            flex
                            w-full
                            items-center
                            gap-3
                            rounded-lg
                            px-3
                            py-2.5
                            text-left
                            text-sm
                            font-medium
                            text-red-600
                            transition
                            hover:bg-red-50
                          "
                        >
                          <Trash2 className="h-4 w-4" />

                          <span>
                            Delete chat
                          </span>
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            /* =====================================================
               SELECTED CHAT VIEW
            ====================================================== */

            <div className="flex min-h-0 flex-1 flex-col">

              {/* Chat header */}

              <div className="mb-3 flex items-center justify-between">
                <h2
                  className="
                    text-[11px]
                    font-bold
                    uppercase
                    tracking-wider
                    text-slate-400
                  "
                >
                  {selected?.name ??
                    'Trip chat'}
                </h2>

                <button
                  type="button"
                  onClick={back}
                  className="
                    text-xs
                    font-medium
                    text-slate-500
                    hover:text-slate-900
                  "
                >
                  All chats
                </button>
              </div>

              {/* Messages */}

              <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain">
                {(selected?.messages ?? []).map(
                  (message, index) => (
                    <div
                      key={index}
                      className={`
                        max-w-[92%]
                        rounded-2xl
                        p-3
                        text-sm
                        ${
                          message.from === 'You'
                            ? 'ml-auto bg-slate-900 text-white'
                            : 'bg-slate-100 text-slate-800'
                        }
                      `}
                    >
                      {message.text}
                    </div>
                  ),
                )}

                {sent.map(
                  (message, index) => (
                    <div
                      key={`sent-${index}`}
                      className="
                        ml-auto
                        max-w-[92%]
                        rounded-2xl
                        bg-slate-900
                        p-3
                        text-sm
                        text-white
                      "
                    >
                      {message}
                    </div>
                  ),
                )}
              </div>

              {/* Chat input */}

              <form
                onSubmit={submit}
                className="
                  sticky
                  bottom-0
                  mt-3
                  flex
                  w-full
                  items-center
                  gap-2
                  rounded-2xl
                  border
                  border-slate-200
                  bg-white
                  px-3
                  py-2.5
                  pb-[max(0.625rem,env(safe-area-inset-bottom))]
                  shadow-sm
                  transition-all
                  focus-within:border-slate-400
                  focus-within:shadow-md
                "
              >
                <input
                  value={draft}
                  onChange={(event) =>
                    setDraft(event.target.value)
                  }
                  placeholder="Ask anything else..."
                  className="
                    min-w-0
                    flex-1
                    border-0
                    bg-transparent
                    p-0
                    text-sm
                    text-slate-800
                    placeholder:text-slate-400
                    outline-none
                    focus:border-0
                    focus:outline-none
                    focus:ring-0
                  "
                />

                <button
                  type="submit"
                  aria-label="Send"
                  className="
                    flex
                    h-8
                    w-8
                    shrink-0
                    items-center
                    justify-center
                    rounded-full
                    text-slate-400
                    transition
                    hover:bg-slate-100
                    hover:text-slate-800
                  "
                >
                  <Send className="h-4 w-4" />
                </button>
              </form>
            </div>
          )}
        </div>
      </section>

      {/* =========================================================
          TRIP FIELD MODALS
      ========================================================== */}

      <TripFieldModals
        field={editing}
        destination={trip.destination}
        when={trip.when}
        budget={trip.budget}
        travelerCount={
          trip.travelers.length
        }
        onClose={() =>
          setEditing(null)
        }
        onSave={(changes) =>
          updateTrip.mutate({
            id: trip.id,
            changes: {
              ...(changes.destination
                ? {
                    destination:
                      changes.destination,
                  }
                : {}),

              ...(changes.when
                ? {
                    when: changes.when,
                  }
                : {}),

              ...(changes.budget
                ? {
                    budget:
                      changes.budget,
                  }
                : {}),

              ...(changes.travelers
                ? {
                    travelers:
                      Array.from(
                        {
                          length:
                            changes.travelers,
                        },
                        (_, index) =>
                          trip.travelers[
                            index
                          ] ??
                          `T${
                            index + 1
                          }`,
                      ),
                  }
                : {}),
            },
          })
        }
      />

      {/* =========================================================
          MAIN WORKSPACE
      ========================================================== */}

      <TripWorkspace trip={trip} />
    </div>
  )
}
