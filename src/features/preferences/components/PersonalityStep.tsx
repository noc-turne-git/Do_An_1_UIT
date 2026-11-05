import { useEffect, useRef } from 'react'
import { Sparkles } from 'lucide-react'

const personalities = [
  { value: 'casual', label: 'Casual', description: 'Playful, treats planning as fun.' },
  { value: 'neutral', label: 'Neutral', description: 'Clear, organized, helpful. Opinionated when asked, skips flattery.' },
  { value: 'professional', label: 'Professional', description: 'Competent and efficient. Warm but not familiar.' },
] as const

export type Personality = typeof personalities[number]['value']

export function PersonalityStep({ value, onChange }: { value: Personality; onChange: (value: Personality) => void }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => { headingRef.current?.focus() }, [])

  return (
    <div className="personality-content">
      <div className="onboarding-logo" aria-hidden="true"><Sparkles size={30} fill="currentColor" /></div>
      <h1 id="onboarding-title" ref={headingRef} tabIndex={-1}>Before we dive in, how would you like our conversations to sound?</h1>
      <fieldset className="personality-options">
        <legend>Personality</legend>
        {personalities.map((personality) => (
          <label key={personality.value} className="personality-option">
            <input type="radio" name="personality" value={personality.value} checked={value === personality.value} onChange={() => onChange(personality.value)} />
            <span className="personality-card"><strong>{personality.label}</strong><span>{personality.description}</span></span>
          </label>
        ))}
      </fieldset>
    </div>
  )
}
