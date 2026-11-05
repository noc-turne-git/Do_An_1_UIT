import { useEffect, useRef } from 'react'
import { Sparkles } from 'lucide-react'

const activities = ['Outdoors', 'Live music', 'Art & museums', 'Bars & nightlife', 'Sports games', 'Fitness', 'Shopping', 'Movies & theater', 'Comedy shows', 'Wellness & spa', 'Other']

export type WrappingUpPreferences = {
  activities: string[]
  other: string
  notes: string
}

export function WrappingUpStep({ value, onChange }: { value: WrappingUpPreferences; onChange: (value: WrappingUpPreferences) => void }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => { headingRef.current?.focus() }, [])

  function toggle(activity: string) {
    onChange({ ...value, activities: value.activities.includes(activity) ? value.activities.filter((item) => item !== activity) : [...value.activities, activity] })
  }

  return <div className="personality-content next-trip-content accommodation-content wrapping-up-content">
    <div className="onboarding-logo" aria-hidden="true"><Sparkles size={30} fill="currentColor" /></div>
    <h1 id="onboarding-title" tabIndex={-1} ref={headingRef}>Wrapping up</h1>
    <fieldset className="travel-style-group">
      <legend>How do you like to have fun on the weekends?</legend>
      <div className="travel-style-options wrapping-up-options">
        {activities.map((activity) => <label className="travel-style-option" key={activity}>
          <input type="checkbox" checked={value.activities.includes(activity)} onChange={() => toggle(activity)} />
          <span>{activity}</span>
        </label>)}
      </div>
      {value.activities.includes('Other') && <input className="travel-style-other" aria-label="Other weekend activities" placeholder="Tell us more" maxLength={500} value={value.other} onChange={(event) => onChange({ ...value, other: event.target.value })} />}
    </fieldset>
    <label className="wrapping-up-notes" htmlFor="wrapping-up-notes">
      Anything to clarify or final things I should know as your personal travel assistant?
      <textarea id="wrapping-up-notes" rows={4} maxLength={2000} value={value.notes} onChange={(event) => onChange({ ...value, notes: event.target.value })} />
    </label>
  </div>
}
