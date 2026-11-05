import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
const { register } = vi.hoisted(() => ({ register: vi.fn() }))
vi.mock('../src/features/auth/store/useAuthStore', () => ({ useAuthStore: { getState: () => ({ register }) } }))
import { RegisterModal } from '../src/features/auth/components/RegisterModal'
beforeEach(() => {
  register.mockReset()
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
afterEach(cleanup)
function submit() {
  const back = vi.fn()
  render(<MemoryRouter><RegisterModal initialEmail="test@example.com" onClose={vi.fn()} onBackToLogin={back} /></MemoryRouter>)
  fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'secret123' } })
  fireEvent.change(screen.getByPlaceholderText('Confirm password'), { target: { value: 'secret123' } })
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
  return back
}
it('shows a dedicated email confirmation view after successful registration', async () => {
  register.mockResolvedValue(false)
  const back = submit()
  await waitFor(() => expect(screen.getByRole('heading', { name: 'Check your email' })).toBeTruthy())
  expect(screen.getByRole('status').textContent).toContain('test@example.com')
  expect(screen.getByRole('status').className).not.toContain('text-red')
  expect(screen.queryByPlaceholderText('Password')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Back to log in' }))
  expect(back).toHaveBeenCalledOnce()
})
it('keeps actual registration errors on the form', async () => {
  register.mockRejectedValue(new Error('Signup failed'))
  submit()
  await waitFor(() => expect(screen.getByText('Signup failed')).toBeTruthy())
  expect(screen.getByPlaceholderText('Password')).toBeTruthy()
  expect(screen.queryByRole('heading', { name: 'Check your email' })).toBeNull()
})
