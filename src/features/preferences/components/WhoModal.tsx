import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Minus, Plus, X } from 'lucide-react'
import './WhoModal.css'

export type Travelers = { adults: number; children: number; infants: number; pets: number }
const rows = [
  { key: 'adults', label: 'Adults', description: 'Ages 13 or above', min: 1 },
  { key: 'children', label: 'Children', description: 'Ages 2–12', min: 0 },
  { key: 'infants', label: 'Infants', description: 'Under 2', min: 0 },
  { key: 'pets', label: 'Pets', description: 'Bringing a service animal?', min: 0 },
] as const

export function WhoModal({ value, onSave, onClose }: { value: Travelers; onSave: (value: Travelers) => void; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [draft, setDraft] = useState<Travelers>({ ...value, adults: Math.max(1, value.adults) })
  const total = draft.adults + draft.children + draft.infants

  useEffect(() => {
    const dialog = dialogRef.current
    dialog?.showModal()
    return () => dialog?.close()
  }, [])

  return createPortal(
    <dialog ref={dialogRef} className="preferences-who-modal" aria-labelledby="who-title" onCancel={(event) => { event.preventDefault(); onClose() }} onClick={(event) => {
      if (event.target !== event.currentTarget) return
      const bounds = event.currentTarget.getBoundingClientRect()
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose()
    }}>
      <header>
        <button type="button" className="who-close" aria-label="Close Who" onClick={onClose}><X size={20} /></button>
        <h2 id="who-title">Who</h2>
        <p aria-live="polite">{total} {total === 1 ? 'traveler' : 'travelers'}</p>
      </header>
      <div className="who-body">
        {rows.map(({ key, label, description, min }) => <div className="who-row" key={key}>
          <div className="who-label"><strong>{label}</strong><span>{description}</span></div>
          <div className="who-counter" role="group" aria-label={label}>
            <button type="button" aria-label={`Remove ${label.toLowerCase()}`} disabled={draft[key] <= min} onClick={() => setDraft((current) => ({ ...current, [key]: Math.max(min, current[key] - 1) }))}><Minus size={20} /></button>
            <output aria-live="polite" aria-label={`${label} count`}>{draft[key]}</output>
            <button type="button" aria-label={`Add ${label.toLowerCase()}`} disabled={draft[key] >= 99} onClick={() => setDraft((current) => ({ ...current, [key]: Math.min(99, current[key] + 1) }))}><Plus size={20} /></button>
          </div>
        </div>)}
      </div>
      <footer><button type="button" className="who-update" onClick={() => onSave(draft)}>Update</button></footer>
    </dialog>, document.body,
  )
}
