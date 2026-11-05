import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
const { updateUser, logout, navigate } = vi.hoisted(() => ({ updateUser: vi.fn(), logout: vi.fn(), navigate: vi.fn() }))
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }))
vi.mock('../src/lib/supabase', () => ({ requireSupabase: () => ({ auth: { updateUser } }) }))
vi.mock('../src/features/auth/store/useAuthStore', () => ({ useAuthStore: Object.assign((selector: (state: { recovery: boolean }) => unknown) => selector({ recovery: true }), { setState: vi.fn(), getState: () => ({ logout }) }) }))
import { PasswordRecoveryModal } from '../src/features/auth/components/PasswordRecoveryModal'
beforeEach(() => {
  updateUser.mockReset()
  logout.mockReset().mockResolvedValue(undefined)
  navigate.mockReset()
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
})
afterEach(cleanup)
it('signs out the recovery session and opens login after updating the password', async () => {
  updateUser.mockResolvedValue({ error: null })
  window.history.replaceState({}, '', '/reset-password')
  render(<PasswordRecoveryModal />)
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'new-secret123' } })
  fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'new-secret123' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save password' }))
  await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith('/', { replace: true, state: { loginOpen: true, passwordUpdated: true } }))
  expect(updateUser).toHaveBeenCalledWith({ password: 'new-secret123' })
  expect(logout).toHaveBeenCalledOnce()
})
it('rejects mismatched passwords before calling Supabase', async () => {
  render(<PasswordRecoveryModal />)
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'new-secret123' } })
  fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'different123' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save password' }))
  expect((await screen.findByRole('alert')).textContent).toBe('Passwords do not match.')
  expect(updateUser).not.toHaveBeenCalled()
  expect(navigate).not.toHaveBeenCalled()
})

it('keeps the form open when updating the password fails', async () => {
  updateUser.mockResolvedValue({ error: new Error('Could not update password.') })
  render(<PasswordRecoveryModal />)
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'new-secret123' } })
  fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'new-secret123' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save password' }))
  expect((await screen.findByRole('alert')).textContent).toBe('Could not update password.')
  expect(logout).not.toHaveBeenCalled()
  expect(navigate).not.toHaveBeenCalled()
})
