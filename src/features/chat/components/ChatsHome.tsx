
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  ArrowUp,
  AudioWaveform,
  CalendarPlus,
  Map,
  MapPin,
  Sparkles,
} from 'lucide-react'

import { Modal } from '../../../components/Modal'
import { chatService } from '../services/chatService'
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
  const [prompt, setPrompt] = useState('')
  const [createTripOpen, setCreateTripOpen] = useState(false)
  const [tripField, setTripField] = useState<TripField | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()

  useEffect(() => {
    if (searchParams.get('newTrip') === '1') setCreateTripOpen(true)
  }, [searchParams])

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

  const submitPrompt = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (prompt.trim()) {
      setPrompt('')
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
      <div className="flex min-h-0 flex-1 overflow-hidden max-[900px]:flex-col max-[900px]:overflow-visible">
        {/* Chat area */}
        <section className="relative flex w-1/2 min-w-0 items-center justify-center bg-white max-[900px]:w-full max-[900px]:min-h-[min(650px,calc(100vh-60px))]">
          <div className="flex flex-col items-center justify-center px-7 pb-[90px] text-center">
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
              Where to today, Linh?
            </h1>

            <p className="m-0 text-[clamp(16px,1.6vw,22px)] leading-[1.45] text-[#222]">
              Hey there, I’m here to assist you in planning your experience.
              <br />
              Ask me anything travel related.
            </p>

            <button
              type="button"
              className="mt-[23px] inline-flex items-center gap-[9px] rounded-full border-0 bg-[#f1f1f1] px-4 py-[11px] text-[15px] text-[#222]"
            >
              <AudioWaveform size={16} />
              Update my assistant
            </button>
          </div>

          {/* Composer */}
          <div className="absolute bottom-2 left-6 right-6">
            <form
              onSubmit={submitPrompt}
              className="flex items-end gap-2 rounded-[18px] border border-[#ddd] bg-white p-2 shadow-[0_2px_12px_#0000000a]"
            >
              <textarea
                aria-label="Ask anything else"
                placeholder="Ask anything else..."
                rows={2}
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                className="min-w-0 flex-1 resize-none border-0 p-2.5 text-[15px] outline-none"
              />

              <button
                type="submit"
                aria-label="Send message"
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

        {/* Discover */}
        <div className="w-1/2 min-w-0 overflow-y-auto rounded-tl-[22px] bg-[#f8f8f8] max-[900px]:w-full max-[900px]:rounded-t-[20px] max-[900px]:rounded-tl-[20px]">
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
        open={createTripOpen}
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
