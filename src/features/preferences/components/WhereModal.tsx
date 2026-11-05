import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { MapPin, Plus, X } from 'lucide-react'

export function WhereModal({ locations, onSave, onClose }: { locations: string[]; onSave: (locations: string[]) => void; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [draft, setDraft] = useState(locations)
  const [query, setQuery] = useState('')
  const [adding, setAdding] = useState(locations.length === 0)

  useEffect(() => {
    const dialog = dialogRef.current
    dialog?.showModal()
    return () => dialog?.close()
  }, [])

  useEffect(() => { if (adding) inputRef.current?.focus() }, [adding])

  function withQuery() {
    const location = query.trim()
    return location && !draft.some((item) => item.toLowerCase() === location.toLowerCase()) ? [...draft, location] : draft
  }

  function addLocation() {
    if (!query.trim()) return
    setDraft(withQuery())
    setQuery('')
    setAdding(false)
  }

  return createPortal(
    <dialog ref={dialogRef} className="preferences-where-modal" aria-labelledby="where-title" onCancel={(event) => { event.preventDefault(); onClose() }} onClick={(event) => {
      if (event.target !== event.currentTarget) return
      const bounds = event.currentTarget.getBoundingClientRect()
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose()
    }}>
      <button type="button" className="where-close" aria-label="Close Where" onClick={onClose}><X size={20} /></button>
      <h2 id="where-title">Where</h2>
      <div className="where-body">
        {draft.map((location, index) => <div className="where-location" key={location}>
          <span className="where-location-icon"><MapPin size={24} /></span>
          <strong>{location}</strong>
          <button type="button" aria-label={`Remove ${location}`} onClick={() => {
            setDraft((items) => items.filter((_, itemIndex) => itemIndex !== index))
            if (draft.length === 1) setAdding(true)
          }}><X size={18} /></button>
        </div>)}
        {adding && <div className="where-search">
          <label className="sr-only" htmlFor="where-location-input">Location</label>
          <input ref={inputRef} id="where-location-input" placeholder="Location" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => {
            if (event.key === 'Enter') { event.preventDefault(); addLocation() }
          }} />
          {query.trim() && <button type="button" className="where-add-result" onClick={addLocation}><MapPin size={18} /><span>Add “{query.trim()}”</span><Plus size={18} /></button>}
        </div>}
        {!adding && <button type="button" className="where-add" onClick={() => setAdding(true)}><Plus size={16} />Add location</button>}
      </div>
      <footer><button type="button" className="where-save" disabled={!draft.length && !query.trim() && !locations.length} onClick={() => onSave(withQuery())}>Save</button></footer>
    </dialog>, document.body,
  )
}
