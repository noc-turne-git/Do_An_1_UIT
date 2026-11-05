import { useEffect, useRef } from 'react'
import { Sparkles } from 'lucide-react'

const companions = ['Solo', 'Couple', 'Family', 'Friends'] as const
const budgets = ['$ On a budget', '$$ Sensibly priced', '$$$ Upscale', '$$$$ Luxury'] as const
const splurges = ['Stay', 'Restaurants', 'Experiences', 'Other'] as const

export type TravelStylePreferences = {
  companions: string[]
  budget: string
  splurges: string[]
  other: string
}

export function TravelStyleStep({ value, onChange }: { value: TravelStylePreferences; onChange: (value: TravelStylePreferences) => void }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => { headingRef.current?.focus() }, [])

  function toggle(group: 'companions' | 'splurges', option: string) {
    onChange({ ...value, [group]: value[group].includes(option) ? value[group].filter((item) => item !== option) : [...value[group], option] })
  }

  return <div className="personality-content next-trip-content travel-style-content">
    <div className="onboarding-logo" aria-hidden="true"><Sparkles size={30} fill="currentColor" /></div>
    <h1 id="onboarding-title" tabIndex={-1} ref={headingRef}>Tell me a bit about your travel style.</h1>
    <p className="travel-style-intro">Share what’s important to you when traveling.</p>
    <fieldset className="travel-style-group">
      <legend>Who do you usually travel with?</legend>
      <div className="travel-style-options">
        {companions.map((option) => <label className="travel-style-option" key={option}>
          <input type="checkbox" checked={value.companions.includes(option)} onChange={() => toggle('companions', option)} />
          <span>{option}</span>
        </label>)}
      </div>
    </fieldset>
    <fieldset className="travel-style-group">
      <legend>What best describes your typical travel budget?</legend>
      <div className="travel-style-options">
        {budgets.map((option) => <label className="travel-style-option" key={option}>
          <input type="radio" name="travel-budget" value={option} checked={value.budget === option} onChange={() => onChange({ ...value, budget: option })} />
          <span>{option}</span>
        </label>)}
      </div>
    </fieldset>
    <fieldset className="travel-style-group">
      <legend>What types of things do you sometimes splurge on?</legend>
      <div className="travel-style-options">
        {splurges.map((option) => <label className="travel-style-option" key={option}>
          <input type="checkbox" checked={value.splurges.includes(option)} onChange={() => toggle('splurges', option)} />
          <span>{option}</span>
        </label>)}
      </div>
      {value.splurges.includes('Other') && <input className="travel-style-other" aria-label="Tell us more about what you splurge on" placeholder="Tell us more" maxLength={500} value={value.other} onChange={(event) => onChange({ ...value, other: event.target.value })} />}
    </fieldset>
  </div>
}
