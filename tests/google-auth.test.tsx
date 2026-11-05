import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
const { getSession } = vi.hoisted(() => ({ getSession: vi.fn() }))
vi.mock('../src/lib/supabase', () => ({ requireSupabase: () => ({ auth: { getSession } }) }))
import { AuthCallbackPage } from '../src/pages/AuthCallbackPage'

beforeEach(() => {
  getSession.mockReset()
  window.history.replaceState({}, '', '/auth/callback')
})
afterEach(() => {
  cleanup()
  window.history.replaceState({}, '', '/')
})
function openCallback() {
  render(<MemoryRouter initialEntries={['/auth/callback']}><Routes>
    <Route path="/auth/callback" element={<AuthCallbackPage />} />
    <Route path="/home" element={<p>Signed in home</p>} />
  </Routes></MemoryRouter>)
}
it('waits for the SDK session before navigating home and clears the callback URL', async () => {
  window.history.replaceState({}, '', '/auth/callback#access_token=example')
  getSession.mockResolvedValue({ data: { session: { user: { id: 'google-user' } } }, error: null })
  openCallback()
  await waitFor(() => expect(screen.getByText('Signed in home')).toBeTruthy())
  expect(window.location.hash).toBe('')
})
it('displays provider cancellation even if an older session exists', async () => {
  window.history.replaceState({}, '', '/auth/callback#error=access_denied&error_description=User+cancelled')
  getSession.mockResolvedValue({ data: { session: { user: { id: 'old-user' } } }, error: null })
  openCallback()
  await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('User cancelled'))
  expect(screen.queryByText('Signed in home')).toBeNull()
  expect(window.location.hash).toBe('')
})
it('offers a return link when no session was created', async () => {
  getSession.mockResolvedValue({ data: { session: null }, error: null })
  openCallback()
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('not completed'))
  expect(screen.getByRole('link', { name: 'Return to Travelio' }).getAttribute('href')).toBe('/')
})
