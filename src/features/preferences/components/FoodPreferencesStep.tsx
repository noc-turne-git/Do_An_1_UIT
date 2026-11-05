import { useEffect, useRef } from 'react'
import { Beer, Coffee, Croissant, Globe, Leaf, Signpost, Sparkles, Store, Utensils, Users } from 'lucide-react'

const restaurants = [
  { label: 'Fine dining & gourmet', icon: Utensils },
  { label: 'Local street food', icon: Signpost },
  { label: 'Cafes/bistros', icon: Coffee },
  { label: 'Family restaurants', icon: Users },
  { label: 'Vegetarian / vegan eateries', icon: Leaf },
  { label: 'Food trucks', icon: Utensils },
  { label: 'Ethnic cuisine', icon: Globe },
  { label: 'Farm-to-table', icon: Store },
  { label: 'Fast casual', icon: Utensils },
  { label: 'Pub / tavern food', icon: Beer },
  { label: 'Bakeries', icon: Croissant },
  { label: 'Coffee shops', icon: Coffee },
  { label: 'Other', icon: null },
] as const

const restrictions = ['Gluten-free', 'Dairy-free', 'Vegetarian', 'Vegan', 'Pescatarian', 'Halal', 'Kosher', 'Other']

export type FoodPreferences = {
  restaurants: string[]
  restaurantOther: string
  dietaryRestrictions: string[]
  dietaryOther: string
}

export function FoodPreferencesStep({ value, onChange }: { value: FoodPreferences; onChange: (value: FoodPreferences) => void }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => { headingRef.current?.focus() }, [])

  function toggle(group: 'restaurants' | 'dietaryRestrictions', option: string) {
    onChange({ ...value, [group]: value[group].includes(option) ? value[group].filter((item) => item !== option) : [...value[group], option] })
  }

  return <div className="personality-content next-trip-content accommodation-content food-preferences-content">
    <div className="onboarding-logo" aria-hidden="true"><Sparkles size={30} fill="currentColor" /></div>
    <h1 id="onboarding-title" tabIndex={-1} ref={headingRef}>Share a bit about your food preferences</h1>
    <fieldset className="travel-style-group">
      <legend>What kinds of restaurants do you like?</legend>
      <div className="travel-style-options food-restaurant-options">
        {restaurants.map(({ label, icon: Icon }) => <label className="travel-style-option" key={label}>
          <input type="checkbox" checked={value.restaurants.includes(label)} onChange={() => toggle('restaurants', label)} />
          <span>{Icon && <Icon size={17} aria-hidden="true" />}{label}</span>
        </label>)}
      </div>
      {value.restaurants.includes('Other') && <input className="travel-style-other" aria-label="Other restaurant preferences" placeholder="Tell us more" maxLength={500} value={value.restaurantOther} onChange={(event) => onChange({ ...value, restaurantOther: event.target.value })} />}
    </fieldset>
    <fieldset className="travel-style-group">
      <legend>Do you have any dietary restrictions I should know about?</legend>
      <div className="travel-style-options food-dietary-options">
        {restrictions.map((restriction) => <label className="travel-style-option" key={restriction}>
          <input type="checkbox" checked={value.dietaryRestrictions.includes(restriction)} onChange={() => toggle('dietaryRestrictions', restriction)} />
          <span>{restriction}</span>
        </label>)}
      </div>
      {value.dietaryRestrictions.includes('Other') && <input className="travel-style-other" aria-label="Other dietary restrictions" placeholder="Tell us more" maxLength={500} value={value.dietaryOther} onChange={(event) => onChange({ ...value, dietaryOther: event.target.value })} />}
    </fieldset>
  </div>
}
