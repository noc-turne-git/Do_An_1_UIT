import { useEffect, useRef, useState } from 'react'
import { ChevronLeft, Sparkles, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { PersonalityStep } from './PersonalityStep'
import type { Personality } from './PersonalityStep'
import { NextTripStep } from './NextTripStep'
import type { NextTripPreferences } from './NextTripStep'
import { PlacesStep } from './PlacesStep'
import type { PlacePreferences } from './PlacesStep'
import { TravelStyleStep } from './TravelStyleStep'
import type { TravelStylePreferences } from './TravelStyleStep'
import { AccommodationStep } from './AccommodationStep'
import type { AccommodationPreferences } from './AccommodationStep'
import { FoodPreferencesStep } from './FoodPreferencesStep'
import type { FoodPreferences } from './FoodPreferencesStep'
import { WrappingUpStep } from './WrappingUpStep'
import type { WrappingUpPreferences } from './WrappingUpStep'
import './OnboardingModal.css'
import { useAuthStore } from '../../auth/store/useAuthStore'

export function OnboardingModal({ email, onClose }: { email: string; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const navigate = useNavigate()
  const [allSet, setAllSet] = useState(false)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [city, setCity] = useState('')
  const [step, setStep] = useState<'basics' | 'personality' | 'trip' | 'places' | 'style' | 'accommodation' | 'food' | 'wrapping'>('basics')
  const [wrappingUp, setWrappingUp] = useState<WrappingUpPreferences>({ activities: [], other: '', notes: '' })
  const [foodPreferences, setFoodPreferences] = useState<FoodPreferences>({ restaurants: [], restaurantOther: '', dietaryRestrictions: [], dietaryOther: '' })
  const [accommodation, setAccommodation] = useState<AccommodationPreferences>({ styles: [], styleOther: '', loyaltyPrograms: [], loyaltyOther: '' })
  const [travelStyle, setTravelStyle] = useState<TravelStylePreferences>({ companions: [], budget: '', splurges: [], other: '' })
  const [places, setPlaces] = useState<PlacePreferences>({ visited: [], wishlist: [] })
  const [nextTrip, setNextTrip] = useState<NextTripPreferences>({ hasTrip: null, description: '', destination: '', startDate: '', endDate: '', adults: 0, children: 0 })
  const [personality, setPersonality] = useState<Personality>('neutral')
  const [notice, setNotice] = useState('')
  const [failedImages, setFailedImages] = useState<Record<string, boolean>>({})
  const complete = Boolean(firstName.trim() && lastName.trim() && city.trim())
  const canContinue = complete
    && (step !== 'style' || Boolean(travelStyle.companions.length && travelStyle.budget && travelStyle.splurges.length))
    && (step !== 'trip' || (nextTrip.hasTrip === false || (nextTrip.hasTrip === true
      && Boolean(nextTrip.destination.trim() || nextTrip.description.trim())
      && (!nextTrip.startDate || !nextTrip.endDate || nextTrip.endDate >= nextTrip.startDate))))
    && (step !== 'accommodation' || (accommodation.styles.length > 0
      && accommodation.loyaltyPrograms.length > 0
      && (!accommodation.styles.includes('Other') || Boolean(accommodation.styleOther.trim()))
      && (!accommodation.loyaltyPrograms.includes('Other') || Boolean(accommodation.loyaltyOther.trim()))))
    && (step !== 'food' || (foodPreferences.restaurants.length > 0
      && foodPreferences.dietaryRestrictions.length > 0
      && (!foodPreferences.restaurants.includes('Other') || Boolean(foodPreferences.restaurantOther.trim()))
      && (!foodPreferences.dietaryRestrictions.includes('Other') || Boolean(foodPreferences.dietaryOther.trim()))))
    && (step !== 'wrapping' || (wrappingUp.activities.length > 0
      && (!wrappingUp.activities.includes('Other') || Boolean(wrappingUp.other.trim()))))
  const stepLabel = { basics: 'The basics', personality: 'Personality', trip: 'Your next trip', places: 'Favorite places you’ve been', style: 'Travel style', accommodation: 'Accommodation', food: 'Food preferences', wrapping: 'Wrapping up' }[step]

  useEffect(() => {
    const dialog = dialogRef.current
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog?.showModal()
    return () => {
      dialog?.close()
      document.body.style.overflow = previousOverflow
    }
  }, [])

  function finishOnboarding() {
    onClose()
    navigate('/home')
  }

  if (allSet) return (
    <dialog ref={dialogRef} className="onboarding-modal" aria-labelledby="onboarding-title" onCancel={finishOnboarding}>
      <button type="button" className="onboarding-close" aria-label="Close onboarding" onClick={finishOnboarding}><X size={22} /></button>
      <div className="onboarding-layout onboarding-complete">
        <div className="onboarding-complete-content">
          <div className="onboarding-logo" aria-hidden="true"><Sparkles size={30} fill="currentColor" /></div>
          <div className="onboarding-complete-message">
            <h1 id="onboarding-title">You’re all set.</h1>
            <p>I’ll use what you’ve shared to make future recommendations more personal, and I’ll keep learning as you use Travelio.<br />Let’s get started!</p>
            <button type="button" autoFocus onClick={finishOnboarding}>Let’s go</button>
          </div>
        </div>
        <div className="onboarding-art onboarding-art-pool" aria-hidden="true">
          {!failedImages.complete && <img src="https://images.unsplash.com/photo-1509600110300-21b9d5fedeb7?auto=format&fit=crop&w=1600&q=85" alt="" onError={() => setFailedImages((failed) => ({ ...failed, complete: true }))} />}
        </div>
      </div>
    </dialog>
  )

  return (
    <dialog ref={dialogRef} className="onboarding-modal" aria-labelledby="onboarding-title" onCancel={onClose}>
      <button type="button" className="onboarding-close" aria-label="Close onboarding" onClick={onClose}><X size={22} /></button>
      <div className={`onboarding-layout ${step === 'personality' ? 'onboarding-personality' : step === 'trip' || step === 'places' || step === 'style' || step === 'accommodation' || step === 'food' || step === 'wrapping' ? 'onboarding-next-trip' : ''}`}>
        <form className="onboarding-form" onChange={() => setNotice('')} onSubmit={(event) => {
          event.preventDefault()
          if (!canContinue) return
          try {
            localStorage.setItem('travel-profile-draft', JSON.stringify({ email, firstName: firstName.trim(), lastName: lastName.trim(), city: city.trim(), personality, places, onboardingComplete: step === 'wrapping', wrappingUp: { ...wrappingUp, other: wrappingUp.activities.includes('Other') ? wrappingUp.other.trim() : '', notes: wrappingUp.notes.trim() }, foodPreferences: { ...foodPreferences, restaurantOther: foodPreferences.restaurants.includes('Other') ? foodPreferences.restaurantOther.trim() : '', dietaryOther: foodPreferences.dietaryRestrictions.includes('Other') ? foodPreferences.dietaryOther.trim() : '' }, accommodation: { ...accommodation, styleOther: accommodation.styles.includes('Other') ? accommodation.styleOther.trim() : '', loyaltyOther: accommodation.loyaltyPrograms.includes('Other') ? accommodation.loyaltyOther.trim() : '' }, travelStyle: { ...travelStyle, other: travelStyle.splurges.includes('Other') ? travelStyle.other.trim() : '' }, nextTrip: nextTrip.hasTrip === true ? nextTrip : { hasTrip: nextTrip.hasTrip } }))
            if (step === 'basics') {
              setNotice('')
              setStep('personality')
              dialogRef.current?.scrollTo(0, 0)
            } else if (step === 'personality') {
              setNotice('')
              setStep('trip')
              dialogRef.current?.scrollTo(0, 0)
            } else if (step === 'trip') {
              setNotice('')
              setStep('places')
              dialogRef.current?.scrollTo(0, 0)
            } else if (step === 'places') {
              setNotice('')
              setStep('style')
              dialogRef.current?.scrollTo(0, 0)
            } else if (step === 'style') {
              setNotice('')
              setStep('accommodation')
              dialogRef.current?.scrollTo(0, 0)
            } else if (step === 'accommodation') {
              setNotice('')
              setStep('food')
              dialogRef.current?.scrollTo(0, 0)
            } else if (step === 'food') {
              setNotice('')
              setStep('wrapping')
              dialogRef.current?.scrollTo(0, 0)
            } else {
              useAuthStore.getState().updateName(firstName.trim(), lastName.trim())
              setAllSet(true)
              dialogRef.current?.scrollTo(0, 0)
            }
          } catch {
            setNotice('Your details could not be saved. Please try again.')
          }
        }}>
          {step === 'wrapping' ? <WrappingUpStep value={wrappingUp} onChange={(value) => { setWrappingUp(value); setNotice('') }} /> : step === 'food' ? <FoodPreferencesStep value={foodPreferences} onChange={(value) => { setFoodPreferences(value); setNotice('') }} /> : step === 'accommodation' ? <AccommodationStep value={accommodation} onChange={(value) => { setAccommodation(value); setNotice('') }} /> : step === 'style' ? <TravelStyleStep value={travelStyle} onChange={(value) => { setTravelStyle(value); setNotice('') }} /> : step === 'places' ? <PlacesStep value={places} onChange={(value) => { setPlaces(value); setNotice('') }} /> : step === 'trip' ? <NextTripStep value={nextTrip} onChange={(value) => { setNextTrip(value); setNotice('') }} /> : step === 'personality' ? <PersonalityStep value={personality} onChange={setPersonality} /> : <div className="onboarding-content">
            <div className="onboarding-logo" aria-hidden="true"><Sparkles size={30} fill="currentColor" /></div>
            <h1 id="onboarding-title">Hi, I’m your travel assistant.</h1>
            <p className="onboarding-intro">I’d love to learn how you like to travel. I’ll remember what matters to you and build on it over time, so every recommendation, plan, and trip feels more like you. First, the basics.</p>
            <fieldset>
              <legend>What’s your name?</legend>
              <div className="onboarding-name-fields">
                <label><span className="sr-only">First name</span><input autoFocus name="givenName" autoComplete="given-name" placeholder="First name" required value={firstName} onChange={(event) => setFirstName(event.target.value)} /></label>
                <label><span className="sr-only">Last name</span><input name="familyName" autoComplete="family-name" placeholder="Last name" required value={lastName} onChange={(event) => setLastName(event.target.value)} /></label>
              </div>
            </fieldset>
            <label className="onboarding-city">Where do you live?<input name="city" autoComplete="address-level2" placeholder="City" required value={city} onChange={(event) => setCity(event.target.value)} /></label>
          </div>}
          <footer className="onboarding-footer">
            <div className="onboarding-progress" aria-label={`Onboarding: ${stepLabel}`}><span style={{ width: step === 'basics' ? '10%' : step === 'personality' ? '20%' : step === 'trip' ? '30%' : step === 'places' ? '40%' : step === 'style' ? '60%' : step === 'accommodation' ? '70%' : step === 'food' ? '80%' : '90%' }} /></div>
            {notice && <p role="status" className="onboarding-notice">{notice}</p>}
            <div className="onboarding-actions">
              {step !== 'basics' ? <div className="onboarding-step-label"><button type="button" className="onboarding-back" aria-label="Back to previous step" onClick={() => { setStep(step === 'wrapping' ? 'food' : step === 'food' ? 'accommodation' : step === 'accommodation' ? 'style' : step === 'style' ? 'places' : step === 'places' ? 'trip' : step === 'trip' ? 'personality' : 'basics'); setNotice(''); dialogRef.current?.scrollTo(0, 0) }}><ChevronLeft size={22} /></button><span>{stepLabel}</span></div> : <span>The basics</span>}
              <button type="submit" disabled={!canContinue}>{step === 'wrapping' ? 'Done' : 'Next'}</button>
            </div>
          </footer>
        </form>
        <div className={`onboarding-art ${step === 'style' || step === 'food' ? 'onboarding-art-pool' : step === 'personality' ? 'onboarding-art-ocean' : ''}`} aria-hidden="true">
          {!failedImages[step] && <img key={step} src={step === 'basics'
            ? 'https://images.unsplash.com/photo-1509316785289-025f5b846b35?auto=format&fit=crop&w=1600&q=85'
            : step === 'personality' ? 'https://images.unsplash.com/photo-1519985397845-b6f5188870af?auto=format&fit=crop&w=1600&q=85'
              : step === 'food' ? 'https://images.unsplash.com/photo-1576013551627-0cc20b96c2a7?auto=format&fit=crop&w=1600&q=85'
                : step === 'accommodation' || step === 'wrapping' ? 'https://images.unsplash.com/photo-1473448912268-2022ce9509d8?auto=format&fit=crop&w=1600&q=85'
                  : step === 'style' ? 'https://images.unsplash.com/photo-1509600110300-21b9d5fedeb7?auto=format&fit=crop&w=1600&q=85'
                    : step === 'places' ? 'https://images.unsplash.com/photo-1663670187287-f32c9676ff8e?auto=format&fit=crop&w=1600&q=85'
                      : 'https://images.unsplash.com/photo-1603109108961-621f59ad567e?auto=format&fit=crop&w=1600&q=85'} alt="" onError={() => setFailedImages((failed) => ({ ...failed, [step]: true }))} />}
        </div>
      </div>
    </dialog>
  )
}
