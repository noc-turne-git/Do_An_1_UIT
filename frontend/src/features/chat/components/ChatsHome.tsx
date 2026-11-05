
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  ArrowUp,
  AudioWaveform,
  CalendarPlus,
  Map,
  MapPin,
  Sparkles,
} from 'lucide-react'

import { useAuthStore } from '../../auth/store/useAuthStore'
import { chatService } from '../services/chatService'
import { chatApi, type ChatMessage } from '../services/chatApi'
import { useTrips } from '../../trip'
import { useCreateTrip } from '../../trip/hooks/useTrips'
import {
  NewTripModal,
  type NewTripInput,
} from '../../trip/components/NewTripModal'
import { TripFieldModals } from '../../trip/components/TripFieldModals'

const photo = (id: string) =>
  `https://images.unsplash.com/${id}?auto=format&fit=crop&w=720&q=80`

type Suggestion = {
  tripId?: string
  title: string
  detail?: string
  tag?: string
  image: string
}

type TripField = 'Where' | 'When' | 'Who' | 'Budget'

export function ChatsHome() {
  const firstName = useAuthStore((state) => state.user?.firstName.trim() || state.user?.lastName.trim() || '')
  const [prompt, setPrompt] = useState('')
  const queryClient = useQueryClient()
  const [pendingMessage, setPendingMessage] = useState<ChatMessage | null>(null)
  const splitRef = useRef<HTMLDivElement>(null)
  const [chatWidth, setChatWidth] = useState(50)
  const [resizing, setResizing] = useState(false)
  const resizeChat = (width: number) => setChatWidth(Math.min(70, Math.max(30, width)))
  const [createTripOpen, setCreateTripOpen] = useState(false)
  const [tripField, setTripField] = useState<TripField | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const conversationId = searchParams.get('conversation_id') ?? searchParams.get('chatTrip') ?? undefined
  const authUserId = useAuthStore((state) => state.user?.id)
  const [sending, setSending] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [chatError, setChatError] = useState('')
  const history = useQuery({
    queryKey: ['chat', 'messages', authUserId, conversationId],
    queryFn: () => chatApi.history(conversationId!),
    enabled: !!conversationId && !!authUserId,
    retry: false,
  })

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [sending, history.data, pendingMessage])

  const [tripDetails, setTripDetails] = useState({
    destination: '',
    when: '',
    budget: 'Any budget',
    travelers: 1,
  })

  const { data: inspiration } = useQuery({
    queryKey: ['chat', 'inspiration'],
    queryFn: chatService.inspirations,
  })

  const { data: trips = [] } = useTrips()
  const createTrip = useCreateTrip()
  const navigate = useNavigate()

  const closeCreateTrip = () => {
    setCreateTripOpen(false)
    if (searchParams.has('newTrip')) {
      const next = new URLSearchParams(searchParams)
      next.delete('newTrip')
      setSearchParams(next, { replace: true })
    }
  }

  const recentItems: Suggestion[] = [
    ...(inspiration?.trips ?? []),
    ...trips.slice(0, 2).map((trip) => ({
      tripId: trip.id,
      title: trip.name,
      detail: trip.destination,
      tag: 'Trip',
      image: trip.cover,
    })),
  ].slice(0, 5)

  const submitPrompt = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!prompt.trim() || sending || history.isFetching) return
    const content = prompt.trim()
    setPendingMessage({
      message_id: `pending-${crypto.randomUUID()}`,
      conversation_id: conversationId ?? '',
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    })
    setPrompt('')
    setSending(true)
    setChatError('')
    try {
      const message = await chatApi.send(content, conversationId)
      queryClient.setQueryData<ChatMessage[]>(
        ['chat', 'messages', authUserId, message.conversation_id],
        (current = []) => [
          ...current.filter((item) => item.message_id !== message.message_id),
          message,
          message.assistant,
          ...(message.trip_summary ? [message.trip_summary] : []),
        ],
      )
      setPendingMessage(null)
      if (!conversationId) {
        const next = new URLSearchParams(searchParams)
        next.delete('chatTrip')
        next.set('conversation_id', message.conversation_id)
        setSearchParams(next, { replace: true })
      }
    } catch (error) {
      setPendingMessage(null)
      setPrompt(content)
      setChatError(error instanceof Error ? error.message : 'Không thể gửi tin nhắn.')
    } finally {
      setSending(false)
    }
  }

  const saveTrip = (input: NewTripInput) => {
    createTrip.mutate(input, {
      onSuccess: (trip) => {
        setCreateTripOpen(false)
        navigate(`/trips/${trip.id}`)
      },
    })
  }

  return (
    <div className="flex h-[100dvh] min-h-0 flex-col overflow-hidden bg-white">
      {/* Header */}
      <header className="relative flex h-[60px] flex-none items-center justify-end gap-4 border-b border-[#eee] px-6 max-[540px]:min-h-[60px] max-[540px]:px-4">
        <div className="ml-auto flex items-center gap-3.5">
          <div className="absolute left-1/2 flex -translate-x-1/2 rounded-full border border-[#e7e7e7] p-1 max-[900px]:hidden">
            {(['Where', 'When', 'Who', 'Budget'] as const).map((label) => (
              <button
                key={label}
                type="button"
                onClick={() => setTripField(label)}
                className="border-0 border-r border-[#eee] bg-transparent px-[13px] py-[7px] text-sm text-[#888] last:border-r-0"
              >
                {label}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => setCreateTripOpen(true)}
            className="inline-flex items-center gap-2 rounded-full bg-[#050505] px-4 py-2.5 text-sm font-semibold text-white no-underline max-[540px]:px-3 max-[540px]:py-[9px] max-[540px]:text-xs"
          >
            <CalendarPlus size={17} />
            Create a trip
          </button>
        </div>
      </header>

      {/* Main */}
      <div ref={splitRef} style={{ '--chat-width': `${chatWidth}%` } as React.CSSProperties} className={`flex min-h-0 flex-1 overflow-hidden max-[900px]:flex-col max-[900px]:overflow-visible ${resizing ? 'cursor-col-resize select-none' : ''}`}>
        {/* Chat area */}
        <section id="chat-panel" className="relative flex w-[var(--chat-width)] min-w-0 shrink-0 items-center justify-center bg-white max-[900px]:w-full max-[900px]:min-h-[min(650px,calc(100vh-60px))]">
          {conversationId || sending ? (
            <div className="absolute inset-x-0 top-0 bottom-36 overflow-y-auto px-7 py-8 max-[540px]:px-4" aria-live="polite">
              {history.isPending && authUserId && <p>Đang tải tin nhắn...</p>}
              <div className="mx-auto flex w-full max-w-[800px] flex-col gap-7">
                {[...(history.data ?? []), ...(pendingMessage ? [pendingMessage] : [])].map((message) => {
                  const isUser = message.role === 'user'
                  return (
                    <article
                      key={message.message_id}
                      aria-label={isUser ? 'Tin nhắn của bạn' : 'Phản hồi từ Travelio'}
                      className={`flex min-w-0 items-start gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}
                    >
                      {!isUser && (
                        <span aria-hidden="true" className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-full border border-[#e8e8e8] bg-white text-[#171717]">
                          <Sparkles size={16} strokeWidth={1.8} />
                        </span>
                      )}
                      <div className={isUser
                        ? 'max-w-[85%] rounded-[22px] rounded-br-md bg-[#f1f3f5] px-5 py-3 text-[#202124]'
                        : 'min-w-0 max-w-[calc(100%-44px)] flex-1 py-1 text-[#202124]'}>
                        <p className="m-0 whitespace-pre-wrap text-left text-[15px] leading-7 [overflow-wrap:anywhere]">{message.content}</p>
                      </div>
                    </article>
                  )
                })}
                {sending && (
                  <div role="status" aria-label="Travelio đang nhập" className="flex items-center gap-3">
                    <span aria-hidden="true" className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-[#e8e8e8] bg-white text-[#171717]">
                      <Sparkles size={16} strokeWidth={1.8} />
                    </span>
                    <div aria-hidden="true" className="flex items-center gap-1.5 rounded-full bg-[#f1f3f5] px-4 py-3.5">
                      {[0, 150, 300].map((delay) => (
                        <span key={delay} style={{ animationDelay: `${delay}ms` }} className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#888] motion-reduce:animate-none" />
                      ))}
                    </div>
                    <span className="sr-only">Travelio đang nhập...</span>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            </div>
          ) : <div className="flex flex-col items-center justify-center px-7 pb-[90px] text-center">
            <div className="relative mb-[23px] grid h-[120px] w-[120px] place-items-center rounded-full bg-[#b8f2d8] text-[#111] max-[540px]:h-24 max-[540px]:w-24">
              <Sparkles
                size={34}
                strokeWidth={1.8}
              />

              <span className="absolute right-[31px] top-8 grid h-[22px] w-[22px] place-items-center rounded-full bg-[#f42d55] text-white">
                <MapPin
                  size={13}
                  fill="currentColor"
                />
              </span>
            </div>

            <h1 className="mb-[17px] text-[clamp(28px,2.6vw,36px)] font-semibold tracking-[-1px] text-[#111]">
              Where to today{firstName ? `, ${firstName}` : ''}?
            </h1>

            <p className="m-0 text-[15px]  leading-[1.45] text-[#222]">
              Hey there, I’m here to assist you in planning your experience.
              <br />
              Ask me anything travel related.
            </p>

            <button
              type="button"
              className="mt-[23px] mb-[23px] inline-flex items-center gap-[9px] rounded-full border-0 bg-[#f1f1f1] px-4 py-[11px] text-[15px] text-[#222]"
            >
              <AudioWaveform size={16} />
              Update my assistant
            </button>
          </div>}

          {/* Composer */}
          <div className="absolute bottom-2 left-6 right-6">
            {(chatError || history.error) && <p role="alert" className="mb-2 text-sm text-red-600">{chatError || history.error?.message}</p>}
            <form
              onSubmit={submitPrompt}
              className="flex items-end gap-2 rounded-[18px] border border-[#ddd] bg-white p-2 shadow-[0_2px_12px_#0000000a]"
            >
              <textarea
                aria-label="Ask anything else"
                placeholder="Ask anything else..."
                rows={2}
                maxLength={10000}
                disabled={sending}
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
                    event.preventDefault()
                    event.currentTarget.form?.requestSubmit()
                  }
                }}
                className="min-w-0 flex-1 resize-none border-0 p-2.5 text-[15px] outline-none"
              />

              <button
                type="submit"
                aria-label="Send message"
                disabled={sending || !prompt.trim() || history.isFetching}
                className="grid h-[38px] w-[38px] flex-none place-items-center rounded-full border-0 bg-[#111] text-white"
              >
                <ArrowUp size={18} />
              </button>
            </form>

            <p className="my-2 text-center text-xs text-[#888]">
              ⓘ Travelio can make mistakes. Check important info.
            </p>
          </div>
        </section>

        <div
          role="separator"
          tabIndex={0}
          aria-label="Điều chỉnh độ rộng khung chat"
          aria-orientation="vertical"
          aria-controls="chat-panel"
          aria-valuemin={30}
          aria-valuemax={70}
          aria-valuenow={Math.round(chatWidth)}
          onPointerDown={(event) => {
            if (event.button !== 0) return
            event.preventDefault()
            event.currentTarget.focus()
            event.currentTarget.setPointerCapture(event.pointerId)
            setResizing(true)
          }}
          onPointerMove={(event) => {
            if (!event.currentTarget.hasPointerCapture(event.pointerId)) return
            const bounds = splitRef.current?.getBoundingClientRect()
            if (bounds?.width) resizeChat(((event.clientX - bounds.left) / bounds.width) * 100)
          }}
          onPointerUp={(event) => {
            if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
            setResizing(false)
          }}
          onLostPointerCapture={() => setResizing(false)}
          onPointerCancel={() => setResizing(false)}
          onDoubleClick={() => resizeChat(50)}
          onKeyDown={(event) => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
            event.preventDefault()
            resizeChat(event.key === 'Home' ? 30 : event.key === 'End' ? 70 : chatWidth + (event.key === 'ArrowLeft' ? -2 : 2))
          }}
          className="group flex w-2 shrink-0 touch-none cursor-col-resize items-center justify-center bg-[#f8f8f8] outline-none hover:bg-slate-200 focus-visible:bg-slate-200 max-[900px]:hidden"
        >
          <span className="h-12 w-1 rounded-full bg-slate-300 group-hover:bg-slate-500 group-focus-visible:bg-slate-500" />
        </div>

        {/* Discover */}
        <div className="min-w-0 flex-1 overflow-y-auto rounded-tl-[22px] bg-[#f8f8f8] max-[900px]:w-full max-[900px]:rounded-t-[20px] max-[900px]:rounded-tl-[20px]">
          <div className="pb-[30px] pt-[10px]">
            <SuggestionSection
              title="Jump back in"
              items={recentItems}
              onItemClick={(item) => {
                if (item.tripId) navigate(`/trips/${item.tripId}`)
              }}
            />

            <SuggestionSection
              title={
                <>
                  <span>For you in</span>
                  <MapPin size={19} />
                  <span>Ho Chi Minh City</span>
                </>
              }
              items={inspiration?.places ?? []}
              action={
                <button
                  type="button"
                  className="inline-flex items-center gap-2 rounded-full border border-[#ddd] bg-transparent px-[13px] py-2 text-sm text-[#222]"
                >
                  <Map size={16} />
                  Map
                </button>
              }
              seeAll="Explore"
              onSeeAll={() => navigate('/explore')}
            />

          </div>
        </div>
      </div>

      {/* Create trip */}
      <NewTripModal
        open={createTripOpen || searchParams.get('newTrip') === '1'}
        onClose={closeCreateTrip}
        onCreate={saveTrip}
        isPending={createTrip.isPending}
      />

      {/* Trip fields */}
      <TripFieldModals
        field={tripField}
        destination={tripDetails.destination}
        when={tripDetails.when}
        budget={tripDetails.budget}
        travelerCount={tripDetails.travelers}
        onClose={() => setTripField(null)}
        onSave={(changes) =>
          setTripDetails((current) => ({
            ...current,
            ...changes,
          }))
        }
      />
    </div>
  )
}

function SuggestionSection({
  title,
  items,
  action,
  seeAll,
  onSeeAll,
  onItemClick,
}: {
  title: React.ReactNode
  items: Suggestion[]
  action?: React.ReactNode
  seeAll?: string
  onSeeAll?: () => void
  onItemClick?: (item: Suggestion) => void
}) {
  return (
    <section className="mb-[35px]">
      <div className="mb-3.5 flex min-h-[42px] items-center gap-3 px-[34px] max-[540px]:px-5">
        <h2 className="m-0 flex items-center gap-3 whitespace-nowrap text-[22px] font-semibold tracking-[-0.3px] text-[#111] max-[540px]:gap-1.5 max-[540px]:text-[17px]">
          {title}
        </h2>

        {action}

        {seeAll && (
          <button
            type="button"
            onClick={onSeeAll}
            className="ml-auto inline-flex items-center gap-2 border-0 bg-transparent p-2 text-sm text-[#222] whitespace-nowrap"
          >
            {seeAll}
          </button>
        )}
      </div>

      {!!items.length && (
        <div className="flex gap-4 overflow-x-auto px-[34px] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden max-[540px]:px-5">
          {items.map((item) => (
            <button
              type="button"
              onClick={() => onItemClick?.(item)}
              disabled={!item.tripId}
              key={item.title}
              className="relative h-[260px] w-[272px] flex-none overflow-hidden rounded-[18px] border-0 bg-[#ddd] p-0 text-left max-[540px]:h-[220px] max-[540px]:w-[230px] disabled:cursor-default"
            >
              <img
                src={
                  item.image.startsWith('https:')
                    ? item.image
                    : photo(item.image)
                }
                alt=""
                className="h-full w-full object-cover"
              />

              <div className="absolute inset-0 bg-[#00000047]" />

              {item.tag && (
                <span className="absolute bottom-[71px] left-[17px] rounded-[10px] bg-[#464646cc] px-[9px] py-1 text-xs font-semibold text-white">
                  {item.tag}
                </span>
              )}

              <div className="absolute bottom-[17px] left-[17px] right-[14px] flex flex-col text-white">
                <strong className="text-[17px] leading-[21px]">
                  {item.title}
                </strong>

                {item.detail && (
                  <span className="mt-0.5 text-sm leading-[19px] text-[#f0f0f0]">
                    {item.detail}
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </section>
  )
}
