import { useState } from 'react'
import { Button } from '../../../components/Button'
import { Modal } from '../../../components/Modal'
import { TripFieldModals } from './TripFieldModals'

export type NewTripInput = { name: string; destination: string; when: string; budget: string; travelers: number; prompt: string }

export function NewTripModal({ open, onClose, onCreate, isPending = false }: {
  open: boolean
  onClose: () => void
  onCreate: (input: NewTripInput) => void
  isPending?: boolean
}) {
  const [prompt, setPrompt] = useState('')
  const [destination, setDestination] = useState('')
  const [when, setWhen] = useState('')
  const [travelers, setTravelers] = useState(1)
  const [budget, setBudget] = useState('Any budget')
  const [field, setField] = useState<'Where' | 'When' | 'Who' | 'Budget' | null>(null)
  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const place = destination.trim()
    onCreate({ name: place ? `${place} trip` : 'New trip', destination: place || 'Destination to be decided', when: when || 'Dates flexible', budget, travelers, prompt: prompt.trim() })
  }

  const saveField = (changes: { destination?: string; when?: string; budget?: string; travelers?: number }) => {
    if (changes.destination !== undefined) setDestination(changes.destination)
    if (changes.when !== undefined) setWhen(changes.when)
    if (changes.budget !== undefined) setBudget(changes.budget)
    if (changes.travelers !== undefined) setTravelers(changes.travelers)
  }
  return <>
  <Modal open={open && field === null} onClose={onClose}>
    <form onSubmit={submit} className="space-y-5">
      <header className="flex items-start justify-between gap-4"><div><p className="text-sm font-medium text-neutral-500">New trip</p><h2 className="mt-1 text-2xl font-semibold tracking-tight">What should I keep in mind?</h2></div><button type="button" onClick={onClose} aria-label="Close" className="grid h-9 w-9 shrink-0 place-items-center rounded-full hover:bg-neutral-100">×</button></header>
      <label className="block text-sm font-medium">Trip ideas or requests<textarea value={prompt} onChange={(event) => setPrompt(event.target.value.slice(0, 2000))} maxLength={2000} rows={3} placeholder="Somewhere warm with 3 kids..." className="mt-2 w-full resize-y rounded-xl border border-neutral-200 p-3 font-normal"/><span className="mt-1 block text-right text-xs text-neutral-400">{prompt.length}/2000</span></label>
      <div className="divide-y divide-neutral-100 overflow-hidden rounded-2xl border border-neutral-200">{([['Where', destination || 'Select destination'], ['When', when || 'Select dates'], ['Who', `${travelers} ${travelers === 1 ? 'traveler' : 'travelers'}`], ['Budget', budget === 'Any budget' ? 'Set budget' : budget]] as const).map(([label, value]) => <button type="button" key={label} onClick={() => setField(label)} className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left hover:bg-neutral-50"><span className="text-sm text-neutral-500">{label}</span><span className={`truncate text-sm ${value !== 'Select destination' && value !== 'Select dates' && value !== 'Set budget' ? 'font-medium text-neutral-900' : 'text-neutral-400'}`}>{value}<span className="ml-3 text-neutral-400">›</span></span></button>)}</div>
      <div className="flex justify-end gap-2 border-t border-neutral-100 pt-4"><Button type="button" onClick={onClose}>Cancel</Button><Button variant="primary" type="submit" disabled={isPending || (!destination.trim() && !prompt.trim())}>{isPending ? 'Creating...' : 'Create trip'}</Button></div>
    </form>
  </Modal>
  <TripFieldModals field={open ? field : null} destination={destination} when={when} budget={budget} travelerCount={travelers} onClose={() => setField(null)} onSave={saveField}/>
  </>
}
