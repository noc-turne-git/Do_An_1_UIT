import { useEffect, useRef } from 'react'
import { Banknote, BedDouble, Building, ConciergeBell, Landmark, Leaf, Search, Sparkles, Star, Tent } from 'lucide-react'

const styles = [
  { label: 'Luxury hotels', icon: ConciergeBell },
  { label: 'Boutique hotels', icon: Star },
  { label: 'Bed & breakfasts', icon: Search },
  { label: 'Budget-friendly hotels', icon: Banknote },
  { label: 'Hostels', icon: Building },
  { label: 'Campgrounds', icon: Tent },
  { label: 'Eco-lodges', icon: Leaf },
  { label: 'Inns', icon: Landmark },
  { label: 'Resorts', icon: ConciergeBell },
  { label: 'Motels', icon: Building },
  { label: 'Short-term rentals', icon: BedDouble },
  { label: 'Other', icon: null },
] as const

const programs = ['Marriott Bonvoy', 'Hilton Honors', 'World of Hyatt', 'IHG One Rewards', 'Wyndham Rewards', 'Choice Privileges', 'Accor Live Limitless (ALL)', 'Best Western Rewards', 'GHA Discovery', 'Other']

export type AccommodationPreferences = {
  styles: string[]
  styleOther: string
  loyaltyPrograms: string[]
  loyaltyOther: string
}

export function AccommodationStep({ value, onChange }: { value: AccommodationPreferences; onChange: (value: AccommodationPreferences) => void }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => { headingRef.current?.focus() }, [])

  function toggle(group: 'styles' | 'loyaltyPrograms', option: string) {
    onChange({ ...value, [group]: value[group].includes(option) ? value[group].filter((item) => item !== option) : [...value[group], option] })
  }

  return <div className="personality-content next-trip-content accommodation-content">
    <div className="onboarding-logo" aria-hidden="true"><Sparkles size={30} fill="currentColor" /></div>
    <h1 id="onboarding-title" tabIndex={-1} ref={headingRef}>Let’s go a little deeper on how you stay.</h1>
    <fieldset className="travel-style-group">
      <legend>What’s your usual accommodation style?</legend>
      <div className="travel-style-options accommodation-style-options">
        {styles.map(({ label, icon: Icon }) => <label className="travel-style-option" key={label}>
          <input type="checkbox" checked={value.styles.includes(label)} onChange={() => toggle('styles', label)} />
          <span>{Icon && <Icon size={17} aria-hidden="true" />}{label}</span>
        </label>)}
      </div>
      {value.styles.includes('Other') && <input className="travel-style-other" aria-label="Other accommodation style" placeholder="Tell us more" maxLength={500} value={value.styleOther} onChange={(event) => onChange({ ...value, styleOther: event.target.value })} />}
    </fieldset>
    <fieldset className="travel-style-group">
      <legend>Are you a member of any loyalty programs?</legend>
      <div className="travel-style-options accommodation-loyalty-options">
        {programs.map((program) => <label className="travel-style-option" key={program}>
          <input type="checkbox" checked={value.loyaltyPrograms.includes(program)} onChange={() => toggle('loyaltyPrograms', program)} />
          <span>{program}</span>
        </label>)}
      </div>
      {value.loyaltyPrograms.includes('Other') && <input className="travel-style-other" aria-label="Other loyalty programs" placeholder="Tell us more" maxLength={500} value={value.loyaltyOther} onChange={(event) => onChange({ ...value, loyaltyOther: event.target.value })} />}
    </fieldset>
  </div>
}
