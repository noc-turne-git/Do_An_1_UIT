import type { Trip } from '../types'

const trips: Trip[] = [
  { id: 'dalat', name: 'Da Lat Adventure', destination: 'Da Lat, Vietnam', duration: '4 days in Dec', when: 'Dec 12 – 16', budget: '$1,200', cover: 'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=1200&q=85', travelers: ['AL', 'MK', 'JT', 'RS'], chats: [
    { id: 'main', name: 'Da Lat trip planning', updated: 'Updated today', main: true, messages: [{ from: 'AI', text: 'Your itinerary has lots of stops but no transport booked between Da Lat and TP.HCM on Day 4. Want help lining up a ride back and timing it with your last activities?' }] },
    { id: 'food', name: 'Food and coffee spots', updated: 'Updated yesterday', messages: [{ from: 'You', text: 'Let’s find a few local coffee shops.' }, { from: 'AI', text: 'I’ve gathered a few well-loved cafés around the city center.' }] },
    { id: 'packing', name: 'Packing ideas', updated: 'Updated Sep 18', messages: [{ from: 'You', text: 'What should we bring for the weather?' }, { from: 'AI', text: 'Bring a light jacket for the cool evenings.' }] },
  ] },
  { id: 'kyoto', name: 'Kyoto in Spring', destination: 'Kyoto, Japan', duration: '6 days in Apr', when: 'Apr 4 – 10', budget: '$2,400', cover: 'https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?w=1200&q=85', travelers: ['AL', 'MK'], chats: [{ id: 'main', name: 'Kyoto planning', updated: 'Updated Sep 20', main: true, messages: [{ from: 'AI', text: 'Your trip plan is coming together. You can review your ideas in the workspace.' }] }] },
  { id: 'lisbon', name: 'Lisbon Long Weekend', destination: 'Lisbon, Portugal', duration: '3 days in Jun', when: 'Jun 14 – 17', budget: '$1,600', cover: 'https://images.unsplash.com/photo-1555881400-74d7acaacd8b?w=1200&q=85', travelers: ['AL', 'MK', 'JT'], chats: [{ id: 'main', name: 'Lisbon trip', updated: 'Updated Sep 16', main: true, messages: [{ from: 'AI', text: 'Your Lisbon plans are ready to explore.' }] }] },
]

export const tripService = {
  async list() { return trips },
  async get(id: string) { return trips.find((trip) => trip.id === id) },
  async update(id: string, changes: Partial<Pick<Trip, 'destination' | 'when' | 'budget' | 'travelers'>>) {
    const index = trips.findIndex((trip) => trip.id === id)
    if (index < 0) throw new Error('Trip not found')
    trips[index] = { ...trips[index], ...changes }
    if (changes.when !== undefined) trips[index].duration = changes.when
    return trips[index]
  },
  async addChat(id: string, firstMessage = '') {
    const trip = trips.find((item) => item.id === id)
    if (!trip) throw new Error('Trip not found')
    const text = firstMessage.trim()
    const chat = {
      id: `chat-${Date.now()}`,
      name: text ? text.slice(0, 36) : 'New chat',
      updated: 'Updated just now',
      messages: text
        ? [{ from: 'You' as const, text }, { from: 'AI' as const, text: 'Let�s plan something great. I can help you with that.' }]
        : [{ from: 'AI' as const, text: 'Let�s plan something great. What would you like to explore?' }],
    }
    trip.chats.push(chat)
    return trip
  },
  async create(input: Pick<Trip, 'name' | 'destination' | 'when'> & { budget?: string; travelers?: number; prompt?: string }) {
    const trip: Trip = { id: `trip-${Date.now()}`, ...input, duration: input.when || 'Dates to be decided', budget: 'Any budget', cover: 'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=1200&q=85', travelers: ['AL'], chats: [{ id: 'main', name: `${input.name} planning`, updated: 'Updated just now', main: true, messages: [{ from: 'AI', text: 'Let’s start planning your trip. What would you like to do first?' }] }] }
    trip.budget = input.budget ?? trip.budget
    trip.travelers = Array.from({ length: Math.max(1, Math.min(20, input.travelers ?? 1)) }, (_, index) => index === 0 ? 'AL' : `T${index + 1}`)
    if (input.prompt?.trim()) trip.chats[0].messages[0] = { from: 'You', text: input.prompt.trim() }
    trips.unshift(trip)
    return trip
  },
}
