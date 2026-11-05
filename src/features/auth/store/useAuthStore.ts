import { create } from 'zustand'
import type { Session } from '@supabase/supabase-js'
import { requireGoogleProvider, requireSupabase, supabase } from '../../../lib/supabase'

type User = { id: string; role: 'traveler'; email: string; firstName: string; lastName: string; avatarUrl?: string }
type Preferences = Record<string, unknown>
type AuthState = {
  user: User | null
  preferences: Preferences
  ready: boolean
  profileError: string
  recovery: boolean
  login: (email: string, password: string) => Promise<void>
  loginWithGoogle: () => Promise<void>
  register: (email: string, password: string) => Promise<boolean>
  resetPassword: (email: string) => Promise<void>
  savePreferences: (preferences: Preferences) => Promise<void>
  logout: () => Promise<void>
}
function sessionUser(session: Session): User {
  const metadata = session.user.user_metadata ?? {}
  const text = (value: unknown) => typeof value === 'string' ? value.trim() : ''
  const firstName = text(metadata.given_name) || text(metadata.first_name)
  const lastName = text(metadata.family_name) || text(metadata.last_name)
  const fullName = text(metadata.full_name) || text(metadata.name)
  const avatarUrl = text(metadata.avatar_url) || text(metadata.picture)
  return { id: session.user.id, email: session.user.email ?? '', role: 'traveler',
    firstName: firstName || (lastName ? '' : fullName), lastName, avatarUrl }
}
export const useAuthStore = create<AuthState>((set, get) => ({
  user: null, preferences: {}, ready: !supabase, profileError: '', recovery: false,
  loginWithGoogle: async () => {
    await requireGoogleProvider()
    const { error } = await requireSupabase().auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: window.location.origin + '/auth/callback',
        queryParams: { prompt: 'select_account' },
      },
    })
    if (error) throw error
  },
  login: async (email, password) => {
    const { data, error } = await requireSupabase().auth.signInWithPassword({ email: email.trim().toLowerCase(), password })
    if (error) throw error
    await loadProfile(data.session)
  },
  register: async (email, password) => {
    const { data, error } = await requireSupabase().auth.signUp({ email: email.trim().toLowerCase(), password,
      options: { emailRedirectTo: window.location.origin + '/home' } })
    if (error) throw error
    if (data.session) await loadProfile(data.session)
    return Boolean(data.session)
  },
  resetPassword: async (email) => {
    const { error } = await requireSupabase().auth.resetPasswordForEmail(email.trim().toLowerCase(), { redirectTo: window.location.origin + '/reset-password' })
    if (error) throw error
  },
  savePreferences: async (changes) => {
    const user = get().user
    if (!user) throw new Error('Please log in before saving your preferences.')
    const client = requireSupabase()
    const { data: current, error: readError } = await client.from('profiles').select('preferences, first_name, last_name').eq('id', user.id).single()
    if (readError) throw readError
    const preferences = { ...current.preferences, ...changes }
    const hasSavedName = Boolean(current.first_name?.trim() || current.last_name?.trim())
    const firstName = typeof changes.firstName === 'string' ? changes.firstName.trim() : hasSavedName ? current.first_name ?? '' : user.firstName
    const lastName = typeof changes.lastName === 'string' ? changes.lastName.trim() : hasSavedName ? current.last_name ?? '' : user.lastName
    delete preferences.firstName
    delete preferences.lastName
    delete preferences.email
    const { data: saved, error } = await client.from('profiles').update({ preferences, first_name: firstName, last_name: lastName, full_name: `${firstName} ${lastName}`.trim() })
      .eq('id', user.id).select('preferences, first_name, last_name').single()
    if (error) throw error
    if (!saved) throw new Error('Your profile could not be saved. Please try again.')
    const savedPreferences: Preferences = { ...saved.preferences }
    delete savedPreferences.firstName
    delete savedPreferences.lastName
    delete savedPreferences.email
    if (get().user?.id === user.id) set({ preferences: savedPreferences, user: { ...user, firstName: saved.first_name ?? '', lastName: saved.last_name ?? '' }, profileError: '' })
  },
  logout: async () => {
    const { error } = await requireSupabase().auth.signOut()
    if (error) throw error
    set({ user: null, preferences: {}, recovery: false, profileError: '' })
  },
}))
let profileRequest = 0
async function loadProfile(session: Session | null) {
  const request = ++profileRequest
  if (!session) {
    useAuthStore.setState({ user: null, preferences: {}, ready: true, recovery: false, profileError: '' })
    return
  }
  if (useAuthStore.getState().user?.id !== session.user.id) useAuthStore.setState({ user: sessionUser(session), preferences: {}, ready: false })
  const { data, error } = await requireSupabase().from('profiles').select('preferences, first_name, last_name').eq('id', session.user.id).single()
  if (request !== profileRequest || useAuthStore.getState().user?.id !== session.user.id) return
  const preferences: Preferences = data?.preferences ?? {}
  delete preferences.firstName
  delete preferences.lastName
  delete preferences.email
  const user = sessionUser(session)
  // Saved profile names take priority; older Google profiles may have empty name columns.
  const hasSavedName = Boolean(data?.first_name?.trim() || data?.last_name?.trim())
  useAuthStore.setState({
    user: hasSavedName ? { ...user, firstName: data?.first_name ?? '', lastName: data?.last_name ?? '' } : user,
    preferences, ready: true, profileError: error ? 'Could not load your profile. Please sign in again to retry.' : '',
  })
}
export function initializeAuth() {
  localStorage.removeItem('travel-mock-auth')
  localStorage.removeItem('travel-profile-draft')
  if (!supabase) return () => {}
  const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
    if (event === 'PASSWORD_RECOVERY' && window.location.pathname === '/reset-password') useAuthStore.setState({ recovery: true })
    // Database calls run outside the auth callback lock.
    setTimeout(() => { void loadProfile(session) }, 0)
  })
  return () => subscription.unsubscribe()
}
