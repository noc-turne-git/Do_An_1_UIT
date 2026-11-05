export type TripField = 'Where' | 'When' | 'Who' | 'Budget'

export type TripFieldChanges = {
  destination?: string
  when?: string
  budget?: string
  travelers?: number
}

export type Party = {
  adults: number
  children: number
  infants: number
  pets: number
}

export type Budget = 'any' | 'budget' | 'sensibly' | 'upscale' | 'luxury'

export const budgetOptions: { id: Budget; symbols?: string; label: string }[] = [
  { id: 'any', label: 'Any budget' },
  { id: 'budget', symbols: '$', label: 'On a budget' },
  { id: 'sensibly', symbols: '$$', label: 'Sensibly priced' },
  { id: 'upscale', symbols: '$$$', label: 'Upscale' },
  { id: 'luxury', symbols: '$$$$', label: 'Luxury' },
]

export const fieldClass =
  'w-full rounded-xl border border-neutral-200 px-4 py-3 text-sm outline-none focus:border-neutral-500'

export const actionClass =
  'rounded-full bg-neutral-950 px-6 py-3 text-sm font-semibold text-white disabled:opacity-40'

export const closeClass =
  'grid h-9 w-9 place-items-center rounded-full text-4xl text-neutral-500 hover:bg-neutral-200'
