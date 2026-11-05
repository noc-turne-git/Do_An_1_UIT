import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
const { save } = vi.hoisted(() => ({ save: vi.fn() }))
vi.mock('../src/features/auth/store/useAuthStore', () => ({ useAuthStore: { getState: () => ({ savePreferences: save }) } }))
// Exercise the real wizard navigation and persistence with small step inputs.
vi.mock('../src/features/preferences/components/PersonalityStep', () => ({ PersonalityStep: () => <p>Personality</p> }))
vi.mock('../src/features/preferences/components/NextTripStep', () => ({ NextTripStep: ({ onChange }: { onChange: (value: unknown) => void }) => <button type="button" onClick={() => onChange({ hasTrip: false })}>No upcoming trip</button> }))
vi.mock('../src/features/preferences/components/PlacesStep', () => ({ PlacesStep: () => <p>Places</p> }))
vi.mock('../src/features/preferences/components/TravelStyleStep', () => ({ TravelStyleStep: ({ onChange }: { onChange: (value: unknown) => void }) => <button type="button" onClick={() => onChange({ companions: ['Solo'], budget: 'Budget', splurges: ['Food'], other: '' })}>Choose style</button> }))
vi.mock('../src/features/preferences/components/AccommodationStep', () => ({ AccommodationStep: ({ onChange }: { onChange: (value: unknown) => void }) => <button type="button" onClick={() => onChange({ styles: ['Hotel'], loyaltyPrograms: ['None'], styleOther: '', loyaltyOther: '' })}>Choose hotel</button> }))
vi.mock('../src/features/preferences/components/FoodPreferencesStep', () => ({ FoodPreferencesStep: ({ onChange }: { onChange: (value: unknown) => void }) => <button type="button" onClick={() => onChange({ restaurants: ['Local'], dietaryRestrictions: ['None'], restaurantOther: '', dietaryOther: '' })}>Choose food</button> }))
vi.mock('../src/features/preferences/components/WrappingUpStep', () => ({ WrappingUpStep: ({ onChange }: { onChange: (value: unknown) => void }) => <button type="button" onClick={() => onChange({ activities: ['Walking'], other: '', notes: 'Quiet places' })}>Choose activities</button> }))
import { OnboardingModal } from '../src/features/preferences/components/OnboardingModal'
beforeEach(() => {
  save.mockReset(); save.mockResolvedValue(undefined)
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
  HTMLElement.prototype.scrollTo = vi.fn()
})
afterEach(cleanup)
function open() {
  const close = vi.fn()
  render(<MemoryRouter><OnboardingModal onClose={close} /></MemoryRouter>)
  fireEvent.change(screen.getByPlaceholderText('First name'), { target: { value: 'Mai' } })
  fireEvent.change(screen.getByPlaceholderText('Last name'), { target: { value: 'Tran' } })
  fireEvent.change(screen.getByPlaceholderText('City'), { target: { value: 'HCM' } })
  return close
}
function lastStep() {
  open()
  const next = () => fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  next(); next()
  fireEvent.click(screen.getByText('No upcoming trip')); next(); next()
  fireEvent.click(screen.getByText('Choose style')); next()
  fireEvent.click(screen.getByText('Choose hotel')); next()
  fireEvent.click(screen.getByText('Choose food')); next()
  fireEvent.click(screen.getByText('Choose activities'))
}
it('does not save when moving forward/back or closing', () => {
  const close = open()
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  fireEvent.click(screen.getByRole('button', { name: 'Back to previous step' }))
  fireEvent.click(screen.getByRole('button', { name: 'Close onboarding' }))
  expect(close).toHaveBeenCalledOnce()
  expect(save).not.toHaveBeenCalled()
})
it('saves exactly once at the final step and waits for success', async () => {
  lastStep()
  expect(save).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(screen.getByText(/all set\./)).toBeTruthy())
  expect(save).toHaveBeenCalledOnce()
  expect(save).toHaveBeenCalledWith(expect.objectContaining({ firstName: 'Mai', city: 'HCM', onboardingComplete: true, nextTrip: { hasTrip: false } }))
})
it('keeps the final step and allows retry after a save error', async () => {
  save.mockRejectedValueOnce(new Error('Connection failed'))
  lastStep()
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(screen.getByText('Connection failed')).toBeTruthy())
  expect(screen.queryByText(/all set\./)).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(screen.getByText(/all set\./)).toBeTruthy())
  expect(save).toHaveBeenCalledTimes(2)
})

it('does not save even if the final step is filled and then closed', () => {
  lastStep()
  fireEvent.click(screen.getByRole('button', { name: 'Close onboarding' }))
  expect(save).not.toHaveBeenCalled()
})
it('blocks repeated submissions while the save is in flight', async () => {
  let resolve: () => void = () => {}
  save.mockReturnValue(new Promise<void>((done) => { resolve = done }))
  lastStep()
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  fireEvent.click(screen.getByRole('button', { name: 'Saving...' }))
  expect(save).toHaveBeenCalledOnce()
  resolve()
  await waitFor(() => expect(screen.getByText(/all set\./)).toBeTruthy())
})
