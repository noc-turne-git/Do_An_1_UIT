import { beforeEach, expect, it, vi } from 'vitest'
const mock = vi.hoisted(() => {
  const single = vi.fn()
  const eq = vi.fn()
  const select = vi.fn()
  const update = vi.fn()
  const from = vi.fn()
  return { single, eq, select, update, from, auth: { signInWithOAuth: vi.fn(), signInWithPassword: vi.fn(), signUp: vi.fn(), resetPasswordForEmail: vi.fn(), signOut: vi.fn(), onAuthStateChange: vi.fn() } }
})
vi.mock('../src/lib/supabase', () => ({ supabase: mock, requireSupabase: () => mock, requireGoogleProvider: vi.fn().mockResolvedValue(undefined) }))
import { requireGoogleProvider } from '../src/lib/supabase'
import { initializeAuth, useAuthStore } from '../src/features/auth/store/useAuthStore'
const session = { user: { id: 'user-1', email: 'test@example.com' } }
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(requireGoogleProvider).mockResolvedValue(undefined)
  useAuthStore.setState({ user: null, preferences: {}, ready: false, recovery: false, profileError: '' })
  mock.from.mockReturnValue(mock); mock.select.mockReturnValue(mock); mock.eq.mockReturnValue(mock); mock.update.mockReturnValue(mock)
  mock.single.mockResolvedValue({ data: { preferences: { longTermMemory: false }, first_name: 'Mai', last_name: 'Tran' }, error: null })
})
it('logs in using Supabase and loads the real profile', async () => {
  mock.auth.signInWithPassword.mockResolvedValue({ data: { session }, error: null })
  await useAuthStore.getState().login(' TEST@example.com ', 'secret')
  expect(mock.auth.signInWithPassword).toHaveBeenCalledWith({ email: 'test@example.com', password: 'secret' })
  expect(useAuthStore.getState().user?.firstName).toBe('Mai')
  expect(mock.update).not.toHaveBeenCalled()
})
it.each([null, '', '   '])('uses the Google display name for empty profile names (%s)', async (empty) => {
  const googleSession = { user: { ...session.user, user_metadata: { full_name: 'Nguyễn Minh Anh' } } }
  mock.auth.signInWithPassword.mockResolvedValue({ data: { session: googleSession }, error: null })
  mock.single.mockResolvedValue({ data: { preferences: {}, first_name: empty, last_name: empty }, error: null })
  await useAuthStore.getState().login('test@example.com', 'secret')
  expect(useAuthStore.getState().user).toMatchObject({ firstName: 'Nguyễn Minh Anh', lastName: '' })
})
it('keeps the saved profile name instead of replacing it with the Google name', async () => {
  mock.auth.signInWithPassword.mockResolvedValue({ data: { session: { user: { ...session.user, user_metadata: { full_name: 'Google Name' } } } }, error: null })
  await useAuthStore.getState().login('test@example.com', 'secret')
  expect(useAuthStore.getState().user).toMatchObject({ firstName: 'Mai', lastName: 'Tran' })
})
it.each(['avatar_url', 'picture'])('loads the Google photo from %s without replacing a custom photo', async (field) => {
  mock.auth.signInWithPassword.mockResolvedValue({ data: { session: { user: { ...session.user,
    user_metadata: { [field]: 'https://lh3.googleusercontent.com/avatar' } } } }, error: null })
  mock.single.mockResolvedValue({ data: { preferences: { profilePhoto: 'custom-photo' }, first_name: 'Mai', last_name: 'Tran' }, error: null })
  await useAuthStore.getState().login('test@example.com', 'secret')
  expect(useAuthStore.getState().user?.avatarUrl).toBe('https://lh3.googleusercontent.com/avatar')
  expect(useAuthStore.getState().preferences.profilePhoto).toBe('custom-photo')
})
it('restores the Google name from an OAuth session with empty profile names', async () => {
  mock.single.mockResolvedValue({ data: { preferences: {}, first_name: null, last_name: null }, error: null })
  mock.auth.onAuthStateChange.mockImplementation((callback) => {
    callback('SIGNED_IN', { user: { ...session.user, user_metadata: { given_name: 'Minh Anh', family_name: 'Nguyễn' } } })
    return { data: { subscription: { unsubscribe: vi.fn() } } }
  })
  const dispose = initializeAuth()
  await vi.waitFor(() => expect(useAuthStore.getState().ready).toBe(true))
  expect(useAuthStore.getState().user).toMatchObject({ firstName: 'Minh Anh', lastName: 'Nguyễn' })
  dispose()
})
it('starts Google OAuth without writing a profile or inventing a session', async () => {
  mock.auth.signInWithOAuth.mockResolvedValue({ data: { url: 'https://accounts.google.com' }, error: null })
  await useAuthStore.getState().loginWithGoogle()
  expect(mock.auth.signInWithOAuth).toHaveBeenCalledWith({ provider: 'google', options: {
    redirectTo: window.location.origin + '/auth/callback', queryParams: { prompt: 'select_account' },
  } })
  expect(mock.from).not.toHaveBeenCalled()
  expect(useAuthStore.getState().user).toBeNull()
})
it('keeps the user in the app when the Google provider is disabled', async () => {
  vi.mocked(requireGoogleProvider).mockRejectedValue(new Error('Google chưa được bật'))
  await expect(useAuthStore.getState().loginWithGoogle()).rejects.toThrow('Google chưa được bật')
  expect(mock.auth.signInWithOAuth).not.toHaveBeenCalled()
})
it('propagates Google OAuth errors for the modal to display', async () => {
  mock.auth.signInWithOAuth.mockResolvedValue({ data: {}, error: new Error('Google provider is disabled') })
  await expect(useAuthStore.getState().loginWithGoogle()).rejects.toThrow('Google provider is disabled')
  expect(useAuthStore.getState().user).toBeNull()
})
it('registration requiring email confirmation performs no profile writes', async () => {
  mock.auth.signUp.mockResolvedValue({ data: { session: null }, error: null })
  expect(await useAuthStore.getState().register('test@example.com', 'secret')).toBe(false)
  expect(mock.from).not.toHaveBeenCalled()
  expect(useAuthStore.getState().user).toBeNull()
})
it('propagates invalid login instead of creating a mock user', async () => {
  mock.auth.signInWithPassword.mockResolvedValue({ data: {}, error: new Error('Invalid credentials') })
  await expect(useAuthStore.getState().login('x@y.com', 'bad')).rejects.toThrow('Invalid credentials')
  expect(useAuthStore.getState().user).toBeNull()
})
it('merges preferences and updates only the signed in profile', async () => {
  useAuthStore.setState({ user: { id: 'user-1', role: 'traveler', email: 'test@example.com', firstName: 'Mai', lastName: 'Tran' } })
  mock.single.mockResolvedValueOnce({ data: { preferences: { longTermMemory: false }, first_name: 'Mai', last_name: 'Tran' }, error: null })
    .mockResolvedValueOnce({ data: { preferences: { longTermMemory: false, city: 'HCM', onboardingComplete: true }, first_name: 'Mai', last_name: 'Tran' }, error: null })
  await useAuthStore.getState().savePreferences({ city: 'HCM', onboardingComplete: true })
  expect(mock.update).toHaveBeenCalledWith({ preferences: { longTermMemory: false, city: 'HCM', onboardingComplete: true }, first_name: 'Mai', last_name: 'Tran', full_name: 'Mai Tran' })
  expect(mock.eq).toHaveBeenCalledWith('id', 'user-1')
  expect(useAuthStore.getState().preferences.city).toBe('HCM')
})
it('preserves existing state on database failure', async () => {
  useAuthStore.setState({ user: { id: 'user-1', role: 'traveler', email: 'test@example.com', firstName: 'Mai', lastName: 'Tran' }, preferences: { city: 'Old' } })
  mock.single.mockResolvedValueOnce({ data: { preferences: {} }, error: null }).mockResolvedValueOnce({ data: null, error: new Error('Database unavailable') })
  await expect(useAuthStore.getState().savePreferences({ city: 'New' })).rejects.toThrow('Database unavailable')
  expect(useAuthStore.getState().preferences.city).toBe('Old')
})
it('rejects unauthenticated saves', async () => {
  await expect(useAuthStore.getState().savePreferences({ city: 'HCM' })).rejects.toThrow('Please log in')
  expect(mock.from).not.toHaveBeenCalled()
})
it('clears user and preferences on successful logout', async () => {
  mock.auth.signOut.mockResolvedValue({ error: null })
  useAuthStore.setState({ preferences: { city: 'HCM' } })
  await useAuthStore.getState().logout()
  expect(useAuthStore.getState().preferences).toEqual({})
  expect(useAuthStore.getState().user).toBeNull()
})
it('restores a session and removes old mock credentials', async () => {
  localStorage.setItem('travel-mock-auth', 'mock-passwords')
  const unsubscribe = vi.fn()
  mock.auth.onAuthStateChange.mockImplementation((callback) => {
    callback('INITIAL_SESSION', session)
    return { data: { subscription: { unsubscribe } } }
  })
  const dispose = initializeAuth()
  await vi.waitFor(() => expect(useAuthStore.getState().ready).toBe(true))
  expect(useAuthStore.getState().user?.id).toBe('user-1')
  expect(localStorage.getItem('travel-mock-auth')).toBeNull()
  dispose(); expect(unsubscribe).toHaveBeenCalled()
})

it('opens recovery mode from the Supabase recovery redirect event', async () => {
  window.history.replaceState({}, '', '/reset-password')
  mock.auth.onAuthStateChange.mockImplementation((callback) => {
    callback('PASSWORD_RECOVERY', session)
    return { data: { subscription: { unsubscribe: vi.fn() } } }
  })
  const dispose = initializeAuth()
  await vi.waitFor(() => expect(useAuthStore.getState().ready).toBe(true))
  expect(useAuthStore.getState().recovery).toBe(true)
  dispose()
  window.history.replaceState({}, '', '/')
})
it('does not open recovery in the original tab when an auth event is received', async () => {
  window.history.replaceState({}, '', '/')
  mock.auth.onAuthStateChange.mockImplementation((callback) => {
    callback('PASSWORD_RECOVERY', session)
    return { data: { subscription: { unsubscribe: vi.fn() } } }
  })
  const dispose = initializeAuth()
  await vi.waitFor(() => expect(useAuthStore.getState().ready).toBe(true))
  expect(useAuthStore.getState().recovery).toBe(false)
  dispose()
})
it('sends recovery links to the dedicated reset route', async () => {
  mock.auth.resetPasswordForEmail.mockResolvedValue({ error: null })
  await useAuthStore.getState().resetPassword(' TEST@example.com ')
  expect(mock.auth.resetPasswordForEmail).toHaveBeenCalledWith('test@example.com', { redirectTo: window.location.origin + '/reset-password' })
})
it('registration with an immediate session loads preferences without writing them', async () => {
  mock.auth.signUp.mockResolvedValue({ data: { session }, error: null })
  expect(await useAuthStore.getState().register('test@example.com', 'secret')).toBe(true)
  expect(useAuthStore.getState().user?.id).toBe('user-1')
  expect(mock.update).not.toHaveBeenCalled()
})

it('stores names in dedicated columns and removes legacy identity preferences', async () => {
  useAuthStore.setState({ user: { id: 'user-1', role: 'traveler', email: 'test@example.com', firstName: 'Mai', lastName: 'Tran' } })
  mock.single.mockResolvedValueOnce({ data: { preferences: { firstName: 'Legacy', lastName: 'Old', email: 'old@example.com', city: 'HCM' }, first_name: 'Mai', last_name: 'Tran' }, error: null })
    .mockResolvedValueOnce({ data: { preferences: { city: 'HCM', personality: 'casual' }, first_name: 'An', last_name: 'Nguyen' }, error: null })
  await useAuthStore.getState().savePreferences({ firstName: ' An ', lastName: ' Nguyen ', email: 'ignored@example.com', personality: 'casual' })
  expect(mock.update).toHaveBeenCalledWith({ first_name: 'An', last_name: 'Nguyen', full_name: 'An Nguyen', preferences: { city: 'HCM', personality: 'casual' } })
  expect(useAuthStore.getState().user?.firstName).toBe('An')
  expect(useAuthStore.getState().preferences).toEqual({ city: 'HCM', personality: 'casual' })
})

it('uses the database response after updating account information', async () => {
  useAuthStore.setState({ user: { id: 'user-1', role: 'traveler', email: 'test@example.com', firstName: 'Mai', lastName: 'Tran' } })
  mock.single.mockResolvedValueOnce({ data: { preferences: { longTermMemory: false }, first_name: 'Mai', last_name: 'Tran' }, error: null })
    .mockResolvedValueOnce({ data: { preferences: { longTermMemory: false, website: 'https://example.com', city: 'Da Nang', profilePhoto: 'data:image/png;base64,photo' }, first_name: 'An', last_name: 'Nguyen' }, error: null })
  await useAuthStore.getState().savePreferences({ firstName: ' An ', lastName: ' Nguyen ', website: 'https://example.com', city: 'Da Nang', profilePhoto: 'data:image/png;base64,photo' })
  expect(mock.update).toHaveBeenCalledWith({ first_name: 'An', last_name: 'Nguyen', full_name: 'An Nguyen', preferences: { longTermMemory: false, website: 'https://example.com', city: 'Da Nang', profilePhoto: 'data:image/png;base64,photo' } })
  expect(mock.select).toHaveBeenLastCalledWith('preferences, first_name, last_name')
  expect(useAuthStore.getState().user).toMatchObject({ firstName: 'An', lastName: 'Nguyen', email: 'test@example.com' })
  expect(useAuthStore.getState().preferences.city).toBe('Da Nang')
})
