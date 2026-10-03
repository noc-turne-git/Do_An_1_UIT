import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type MockUser = { id: string; role: 'traveler'; email: string; password: string; firstName: string; lastName: string }
// Local mock credentials for testing only.
export const mockUsers: MockUser[] = [
  { id: 'traveler-1', role: 'traveler', email: 'minh@example.com', password: 'Travel123!', firstName: 'Minh', lastName: 'Nguyen' },
  { id: 'traveler-2', role: 'traveler', email: 'linh@example.com', password: 'Travel123!', firstName: 'Linh', lastName: 'Tran' },
]
type AuthState = {
  users: MockUser[]
  user: Omit<MockUser, 'password'> | null
  login: (email: string, password: string) => void
  register: (email: string, password: string) => void
  resetPassword: (email: string, password: string) => void
  updateName: (firstName: string, lastName: string) => void
  logout: () => void
}
function publicUser(user: MockUser) {
  return { id: user.id, role: user.role, email: user.email, firstName: user.firstName, lastName: user.lastName }
}
export const useAuthStore = create<AuthState>()(persist((set, get) => ({
  users: mockUsers,
  user: null,
  login: (email, password) => {
    const user = get().users.find((item) => item.email === email.trim().toLowerCase() && item.password === password)
    if (!user) throw new Error('Incorrect email or password.')
    const profile = localStorage.getItem(`travel-mock-profile:${user.id}`)
    localStorage.setItem('travel-profile-draft', profile ?? JSON.stringify({ email: user.email, firstName: user.firstName, lastName: user.lastName }))
    set({ user: publicUser(user) })
  },
  register: (email, password) => {
    const normalizedEmail = email.trim().toLowerCase()
    if (get().users.some((user) => user.email === normalizedEmail)) throw new Error('This email is already registered. Please log in.')
    if (!password.trim()) throw new Error('Please enter a password.')
    const user: MockUser = { id: crypto.randomUUID(), role: 'traveler', email: normalizedEmail, password, firstName: normalizedEmail.split('@')[0], lastName: '' }
    localStorage.setItem('travel-profile-draft', JSON.stringify({ email: user.email, firstName: user.firstName, lastName: '' }))
    set({ users: [...get().users, user], user: publicUser(user) })
  },
  updateName: (firstName, lastName) => {
    const user = get().user
    if (!user) return
    set({ user: { ...user, firstName, lastName }, users: get().users.map((item) => item.id === user.id ? { ...item, firstName, lastName } : item) })
  },
  resetPassword: (email, password) => {
    const normalizedEmail = email.trim().toLowerCase()
    if (!get().users.some((user) => user.email === normalizedEmail)) throw new Error('No account found with this email.')
    if (!password.trim()) throw new Error('Please enter a new password.')
    set({ users: get().users.map((user) => user.email === normalizedEmail ? { ...user, password } : user) })
  },
  logout: () => {
    const user = get().user
    const profile = localStorage.getItem('travel-profile-draft')
    if (user && profile) localStorage.setItem(`travel-mock-profile:${user.id}`, profile)
    localStorage.removeItem('travel-profile-draft')
    set({ user: null })
  },
}), { name: 'travel-mock-auth' }))
