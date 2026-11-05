import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
const { resetPassword } = vi.hoisted(() => ({ resetPassword: vi.fn() }))
vi.mock('../src/features/auth/store/useAuthStore', () => ({ useAuthStore: { getState: () => ({ resetPassword }) } }))
import { ForgotPasswordModal } from '../src/features/auth/components/ForgotPasswordModal'
beforeEach(() => {
  resetPassword.mockReset().mockResolvedValue(undefined)
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
afterEach(() => { cleanup(); vi.useRealTimers() })
it('keeps the original dialog at the email-sent notice without an OTP form', async () => {
  const onClose = vi.fn()
  render(<ForgotPasswordModal initialEmail="test@example.com" onClose={onClose} />)
  fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }))
  expect((await screen.findByRole('status')).textContent).toContain('Đã gửi email. Vui lòng kiểm tra hộp thư để đặt lại mật khẩu.')
  expect(resetPassword).toHaveBeenCalledWith('test@example.com')
  expect(screen.queryByLabelText('Reset code')).toBeNull()
  expect(onClose).not.toHaveBeenCalled()
})
it('keeps send errors on the email form for retry', async () => {
  resetPassword.mockRejectedValue(new Error('Please try again later'))
  render(<ForgotPasswordModal initialEmail="test@example.com" onClose={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }))
  expect((await screen.findByRole('alert')).textContent).toBe('Please try again later')
  expect(screen.getByLabelText('Email')).toBeTruthy()
})
it('waits sixty seconds before resending and keeps the original notice', async () => {
  vi.useFakeTimers()
  const onClose = vi.fn()
  render(<ForgotPasswordModal initialEmail="test@example.com" onClose={onClose} />)
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Send reset link' })) })
  expect(screen.getByRole('button', { name: 'Gửi lại sau 60s' })).toHaveProperty('disabled', true)
  await act(async () => { vi.advanceTimersByTime(60_000) })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Gửi lại' })) })
  expect(resetPassword).toHaveBeenCalledTimes(2)
  expect(resetPassword).toHaveBeenLastCalledWith('test@example.com')
  expect(screen.getByText('Đã gửi lại email. Vui lòng kiểm tra hộp thư.')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Gửi lại sau 60s' })).toHaveProperty('disabled', true)
  expect(onClose).not.toHaveBeenCalled()
})
it('shows resend errors and allows retry without closing the sent notice', async () => {
  vi.useFakeTimers()
  render(<ForgotPasswordModal initialEmail="test@example.com" onClose={vi.fn()} />)
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Send reset link' })) })
  await act(async () => { vi.advanceTimersByTime(60_000) })
  resetPassword.mockRejectedValueOnce(new Error('Email rate limit exceeded'))
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Gửi lại' })) })
  expect(screen.getByRole('alert').textContent).toBe('Email rate limit exceeded')
  expect(screen.getByRole('button', { name: 'Gửi lại' })).toHaveProperty('disabled', false)
  expect(screen.getByText('Đã gửi email. Vui lòng kiểm tra hộp thư để đặt lại mật khẩu.')).toBeTruthy()
})
