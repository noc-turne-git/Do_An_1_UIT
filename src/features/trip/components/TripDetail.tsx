import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Button } from '../../../components/Button'
import { useAddTripChat, useTrip, useUpdateTrip } from '../hooks/useTrips'
import { TripWorkspace } from './TripWorkspace'
import { TripFieldModals } from './TripFieldModals'

export function TripDetail() {
  const { tripId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const { data: trip, isLoading } = useTrip(tripId)
  const updateTrip = useUpdateTrip()
  const addChat = useAddTripChat()
  const [chatOverride, setChatOverride] = useState<string | null | undefined>(undefined)
  const chatId = chatOverride === undefined ? searchParams.get('chatId') : chatOverride
  const [draft, setDraft] = useState('')
  const [sent, setSent] = useState<string[]>([])
  const [editing, setEditing] = useState<'Where' | 'When' | 'Who' | 'Budget' | null>(null)
  if (isLoading) return <p className="p-8 text-neutral-500">Loading trip...</p>
  if (!trip) return <div className="p-8"><p>This trip could not be found.</p><Link className="mt-3 inline-block underline" to="/trips">Back to trips</Link></div>

  const selected = trip.chats.find((chat) => chat.id === chatId)
  const mainChat = trip.chats.find((chat) => chat.main) ?? trip.chats[0]
  const messages = selected?.messages ?? []
  const back = () => {
    if (!chatId) return navigate('/trips')
    setChatOverride(null)
    const next = new URLSearchParams(searchParams)
    next.delete('chatId')
    setSearchParams(next, { replace: true })
  }
  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!draft.trim()) return
    setSent((items) => [...items, draft.trim()])
    setDraft('')
  }
  const openEdit = (label: 'Where' | 'When' | 'Who' | 'Budget') => setEditing(label)

  return <div className="flex h-screen min-h-[600px] flex-col lg:flex-row">
    <section className="flex min-h-[420px] w-full flex-col border-b border-neutral-200 lg:w-[min(44%,560px)] lg:min-w-[370px] lg:border-b-0 lg:border-r">
      <header className="border-b border-neutral-200 p-5">
        <div className="mb-3 flex items-center gap-3"><button onClick={back} aria-label="Back" className="grid h-9 w-9 place-items-center rounded-full border">←</button><div className="min-w-0"><h1 className="truncate text-lg font-semibold">{trip.name}</h1><p className="text-sm text-neutral-500">{trip.destination}</p></div></div>
        <div className="flex flex-wrap gap-2">{([['Where',trip.destination],['When',trip.when],['Who',`${trip.travelers.length} travelers`],['Budget',trip.budget]] as const).map(([label,value]) => <Button key={label} onClick={() => openEdit(label)} className="px-3 py-1.5 text-xs"><span className="text-neutral-500">{label}</span> {value}</Button>)}</div>
      </header>
      {!chatId && <><div className="m-4 rounded-xl bg-amber-50 p-4 text-sm"><strong className="mb-1 block">Trip assistant</strong>{mainChat?.messages[0]?.text}</div><div className="min-h-0 flex-1 overflow-y-auto px-4 pb-5"><h2 className="mb-3 text-sm font-semibold text-neutral-500">CHATS</h2>{trip.chats.map((chat) => <button key={chat.id} onClick={() => setChatOverride(chat.id)} className="mb-1 flex w-full items-center justify-between rounded-xl p-3 text-left hover:bg-neutral-50"><span><strong className="block font-medium">{chat.name}{chat.main && <small className="ml-2 rounded bg-neutral-100 px-2 py-1">Main</small>}</strong><small className="text-neutral-500">{chat.updated}</small></span><span>›</span></button>)}<button onClick={async () => { const updated = await addChat.mutateAsync(trip.id); setChatOverride(updated.chats.at(-1)?.id ?? null) }} className="mt-2 w-full rounded-xl border border-dashed p-3 text-sm">+ New chat</button></div></>}
      {chatId && <><div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">{messages.map((item,index) => <div key={index} className={`max-w-[90%] rounded-2xl p-4 text-sm ${item.from === 'You' ? 'ml-auto bg-neutral-900 text-white' : 'bg-neutral-100'}`}><small className="mb-1 block opacity-60">{item.from}</small>{item.text}</div>)}{sent.map((item,index)=><div key={`sent-${index}`} className="ml-auto max-w-[90%] rounded-2xl bg-neutral-900 p-4 text-sm text-white"><small className="mb-1 block opacity-60">You</small>{item}</div>)}</div><form onSubmit={submit} className="flex gap-2 border-t p-4"><input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Ask anything else..." className="min-w-0 flex-1 rounded-xl border px-4 py-3"/><Button variant="primary" type="submit">Send</Button></form></>}
    </section>
    <TripFieldModals field={editing} destination={trip.destination} when={trip.when} budget={trip.budget} travelerCount={trip.travelers.length} onClose={() => setEditing(null)} onSave={(changes) => updateTrip.mutate({ id: trip.id, changes: { ...(changes.destination ? { destination: changes.destination } : {}), ...(changes.when ? { when: changes.when } : {}), ...(changes.budget ? { budget: changes.budget } : {}), ...(changes.travelers ? { travelers: Array.from({ length: changes.travelers }, (_, index) => trip.travelers[index] ?? `T${index + 1}`) } : {}) } })}/>
    <TripWorkspace trip={trip} />
  </div>
}
