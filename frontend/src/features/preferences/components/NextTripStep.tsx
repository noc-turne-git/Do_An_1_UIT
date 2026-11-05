import { useEffect, useRef, useState } from 'react'
import { WhereModal } from './WhereModal'
import { WhenModal } from './WhenModal'
import { WhoModal } from './WhoModal'
import { Sparkles } from 'lucide-react'

export type NextTripPreferences = {
  hasTrip: boolean | null
  description: string
  destination: string
  destinations?: string[]
  dateMode?: 'dates' | 'flexible'
  flexibleDays?: number
  flexibleMonths?: string[]
  startDate: string
  endDate: string
  adults: number
  children: number
  infants?: number
  pets?: number
}

export function NextTripStep({ value, onChange }: { value: NextTripPreferences; onChange: (value: NextTripPreferences) => void }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const [whereOpen, setWhereOpen] = useState(false)
  const [whenOpen, setWhenOpen] = useState(false)
  const [whoOpen, setWhoOpen] = useState(false)
  const travelerCount = value.adults + value.children + (value.infants ?? 0)
  useEffect(() => { headingRef.current?.focus() }, [])
  function update(changes: Partial<NextTripPreferences>) { onChange({ ...value, ...changes }) }

  return (
    <div className="personality-content next-trip-content">
      <div className="onboarding-logo" aria-hidden="true"><Sparkles size={30} fill="currentColor" /></div>
      <h1 id="onboarding-title" ref={headingRef} tabIndex={-1}>Do you have a trip in mind now?</h1>
      <div className="next-trip-choices" role="group" aria-label="Do you have a trip in mind now?">
        <button type="button" aria-pressed={value.hasTrip === true} onClick={() => update({ hasTrip: true })}>Yes</button>
        <button type="button" aria-pressed={value.hasTrip === false} onClick={() => update({ hasTrip: false })}>No</button>
      </div>
      {value.hasTrip === true && <div className="next-trip-details">
        <label className="sr-only" htmlFor="next-trip-description">Describe your trip</label>
        <textarea id="next-trip-description" maxLength={2000} rows={4} placeholder="Somewhere warm with 3 kids" value={value.description} onChange={(event) => update({ description: event.target.value })} aria-describedby="next-trip-count" />
        <p id="next-trip-count" className="next-trip-count">{value.description.length}/2000</p>
        <p className="next-trip-hint">Have details? Share what you know.</p>
        <button type="button" className="next-trip-field next-trip-where-trigger" aria-haspopup="dialog" onClick={() => setWhereOpen(true)}><strong>Where</strong><span>{value.destination.trim() || 'Select destination'}</span></button>
        {whereOpen && <WhereModal locations={value.destinations ?? (value.destination.trim() ? [value.destination.trim()] : [])} onClose={() => setWhereOpen(false)} onSave={(locations) => {
          update({ destinations: locations, destination: locations.join(', ') })
          setWhereOpen(false)
        }} />}
        <button type="button" className="next-trip-field next-trip-where-trigger" aria-haspopup="dialog" onClick={() => setWhenOpen(true)}><strong>When</strong><span>{value.dateMode === 'flexible' ? `${value.flexibleDays ?? 5} days ? ${value.flexibleMonths?.length ? value.flexibleMonths.join(', ') : 'Anytime'}` : value.startDate ? `${value.startDate} ? ${value.endDate}` : 'Select dates'}</span></button>
        {whenOpen && <WhenModal value={value} onClose={() => setWhenOpen(false)} onSave={(dates) => {
          update(dates)
          setWhenOpen(false)
        }} />}
        <button type="button" className="next-trip-field next-trip-where-trigger" aria-haspopup="dialog" onClick={() => setWhoOpen(true)}><strong>Who</strong><span>{travelerCount ? `${travelerCount} ${travelerCount === 1 ? 'traveler' : 'travelers'}${value.pets ? `, ${value.pets} ${value.pets === 1 ? 'pet' : 'pets'}` : ''}` : 'Add people'}</span></button>
        {whoOpen && <WhoModal value={{ adults: value.adults, children: value.children, infants: value.infants ?? 0, pets: value.pets ?? 0 }} onClose={() => setWhoOpen(false)} onSave={(travelers) => {
          update(travelers)
          setWhoOpen(false)
        }} />}
      </div>}
    </div>
  )
}
