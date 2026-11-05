import { useEffect, useRef, useState } from 'react'
import { Plus, Sparkles, X } from 'lucide-react'

function PlaceList({ title, places, onChange }: { title: string; places: string[]; onChange: (places: string[]) => void }) {
  const [adding, setAdding] = useState(false)
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  useEffect(() => { if (adding) inputRef.current?.focus() }, [adding])
  function addPlace() {
    const name = query.trim()
    if (!name) return
    if (!places.some((place) => place.toLowerCase() === name.toLowerCase())) onChange([...places, name])
    setQuery('')
    inputRef.current?.focus()
  }
  return <section className="preferences-place-list" aria-label={title}>
    <h2>{title}{places.length > 0 && <span className="preferences-place-count">{places.length}</span>}</h2>
    <div className="preferences-place-tags">
      {places.map((place) => <span className="preferences-place-tag" key={place}>{place}<button type="button" aria-label={`Remove ${place} from ${title}`} onClick={() => onChange(places.filter((item) => item !== place))}><X size={14} /></button></span>)}
    </div>
    {adding ? <div className="preferences-place-editor">
      <div className="preferences-place-search">
        <input ref={inputRef} aria-label={`Add to ${title}`} placeholder="Search cities, countries, regions, or neighborhoods" maxLength={120} value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => {
          if (event.key === 'Enter') { event.preventDefault(); addPlace() }
          if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setAdding(false); setQuery('') }
        }} />
        <button type="button" aria-label="Cancel adding place" onClick={() => { setAdding(false); setQuery('') }}><X size={18} /></button>
      </div>
      {query.trim() && <button type="button" className="preferences-place-suggestion" onClick={addPlace}><Plus size={16} />Add “{query.trim()}”</button>}
    </div> : <button type="button" className="preferences-add-place" onClick={() => setAdding(true)}><Plus size={16} />Add place</button>}
  </section>
}

export type PlacePreferences = { visited: string[]; wishlist: string[] }
export function PlacesStep({ value, onChange }: { value: PlacePreferences; onChange: (value: PlacePreferences) => void }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => { headingRef.current?.focus() }, [])
  return <div className="personality-content next-trip-content preferences-places-content">
    <div className="onboarding-logo" aria-hidden="true"><Sparkles size={30} fill="currentColor" /></div>
    <h1 id="onboarding-title" tabIndex={-1} ref={headingRef}>Share a few places you’ve been and want to go</h1>
    <p className="preferences-places-intro">These help me understand the kinds of trips you like and recommend what’s next.</p>
    <PlaceList title="Favorite places you’ve been" places={value.visited} onChange={(visited) => onChange({ ...value, visited })} />
    <PlaceList title="Places you want to go" places={value.wishlist} onChange={(wishlist) => onChange({ ...value, wishlist })} />
  </div>
}
