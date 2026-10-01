import { useState } from 'react'
import { ChevronDown, MoreHorizontal, Plus, Share2, Users } from 'lucide-react'
import type { Trip } from '../types'
import { Button } from '../../../components/Button'
import { IdeaBoard } from '../../idea'
import { CalendarBoard, ItineraryBoard, PreferencesBoard } from '../../itinerary'
import { TripMap } from '../../map'

type Tab = 'Ideas' | 'Itinerary' | 'Trip preferences' | 'Calendar' | 'Map'
const tabs: Tab[] = ['Ideas', 'Itinerary', 'Trip preferences', 'Calendar', 'Map']

export function TripWorkspace({ trip }: { trip: Trip }) {
  const [tab, setTab] = useState<Tab>('Ideas')
  const [noteOpen, setNoteOpen] = useState(false)
  const [note, setNote] = useState('')
  const [notes, setNotes] = useState<string[]>([])
  const [itineraryAdds, setItineraryAdds] = useState<string[]>([])

  return <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-white lg:rounded-l-[24px] lg:border-l lg:border-slate-200/80 lg:shadow-[-12px_0_35px_-20px_rgba(15,23,42,0.25)]">
    <header className="flex min-h-16 shrink-0 flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-3 sm:px-8">
      <div className="flex items-center gap-3 text-slate-400"><span className="hidden h-7 w-7 items-center justify-center rounded-full border border-slate-200 sm:flex"><ChevronDown className="h-4 w-4 -rotate-90" /></span><div className="flex -space-x-2" aria-label={`${trip.travelers.length} trip members`}>{trip.travelers.slice(0, 3).map((traveler, index) => <span key={`${traveler}-${index}`} className={`grid h-7 w-7 place-items-center rounded-full border-2 border-white text-[9px] font-bold ${['bg-amber-100 text-amber-800', 'bg-emerald-100 text-emerald-800', 'bg-indigo-100 text-indigo-800'][index % 3]}`}>{traveler.slice(0, 2)}</span>)}</div><span className="hidden items-center gap-1 text-xs font-medium text-slate-500 sm:inline-flex"><Users className="h-3.5 w-3.5" /> {trip.travelers.length}</span></div>
      <div className="ml-auto flex flex-wrap items-center gap-2"><Button className="!h-8 !rounded-full !border-slate-200 !px-3.5 !text-xs"><Plus className="mr-1 h-3.5 w-3.5"/>Invite</Button><Button className="!h-8 !rounded-full !border-slate-200 !px-3.5 !text-xs"><Share2 className="mr-1 h-3.5 w-3.5"/>Share / Export</Button><Button onClick={() => setNoteOpen(!noteOpen)} className="!h-8 !rounded-full !border-slate-200 !px-3.5 !text-xs"><Plus className="mr-1 h-3.5 w-3.5"/>Add note</Button><Button aria-label="More trip actions" className="!h-8 !w-8 !rounded-full !border-slate-200 !p-0"><MoreHorizontal className="h-4 w-4"/></Button></div>
    </header>
    <nav className="flex shrink-0 gap-6 overflow-x-auto border-b border-slate-200/80 bg-white px-5 sm:gap-8 sm:px-8" aria-label="Trip workspace tabs">{tabs.map((item) => <button key={item} role="tab" aria-selected={tab === item} onClick={() => setTab(item)} className={`shrink-0 border-b-2 py-3.5 text-xs tracking-wide transition-colors ${tab === item ? 'border-slate-900 font-semibold text-slate-900' : 'border-transparent font-medium text-slate-500 hover:text-slate-900'}`}>{item}</button>)}</nav>
    <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-8">
      {noteOpen && <form onSubmit={(event) => { event.preventDefault(); if (note.trim()) setNotes((items) => [...items, note.trim()]); setNote(''); setNoteOpen(false) }} className="mb-4 flex gap-2"><input autoFocus value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add a trip note" className="min-w-0 flex-1 rounded-xl border border-slate-200 p-3 text-sm"/><Button variant="primary" type="submit">Save note</Button></form>}
      {notes.map((item,index) => <p key={index} className="mb-3 rounded-xl border border-amber-100 bg-amber-50 p-3 text-sm text-slate-700">{item}</p>)}
      {tab === 'Ideas' && <IdeaBoard onAddToItinerary={(name) => setItineraryAdds((items) => [...items,name])}/>}
      {tab === 'Itinerary' && <><ItineraryBoard duration={trip.duration}/>{itineraryAdds.length > 0 && <div className="mt-4 rounded-xl border p-3"><h3 className="mb-2 text-sm font-semibold">Added from ideas</h3>{itineraryAdds.map((name,index)=><p key={index} className="py-1 text-sm">{name}</p>)}</div>}</>}
      {tab === 'Trip preferences' && <PreferencesBoard/>}
      {tab === 'Calendar' && <CalendarBoard when={trip.when}/>}
      {tab === 'Map' && <TripMap destination={trip.destination}/>}
    </div>
  </section>
}
