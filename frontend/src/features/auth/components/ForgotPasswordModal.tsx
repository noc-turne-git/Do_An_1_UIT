import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { useAuthStore } from '../store/useAuthStore'

export function ForgotPasswordModal({ initialEmail, onClose }: { initialEmail: string; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [email, setEmail] = useState(initialEmail)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [remaining, setRemaining] = useState(0)
  const [resent, setResent] = useState(false)
  const resendAt = useRef(0)
  useEffect(() => {
    if (!success) return
    const timer = window.setInterval(() => {
      setRemaining(Math.max(0, Math.ceil((resendAt.current - Date.now()) / 1000)))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [success])
  async function sendEmail() {
    if (busy || Date.now() < resendAt.current) return
    setBusy(true)
    setError('')
    setResent(false)
    try {
      await useAuthStore.getState().resetPassword(email)
      setResent(success)
      setSuccess(true)
      resendAt.current = Date.now() + 60_000
      setRemaining(60)
    } catch (error) { setError(error instanceof Error ? error.message : 'Không thể gửi email. Vui lòng thử lại.') }
    finally { setBusy(false) }
  }
  useEffect(() => {
    const dialog = dialogRef.current
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog?.showModal()
    return () => { dialog?.close(); document.body.style.overflow = overflow }
  }, [])
  return <dialog ref={dialogRef} onCancel={onClose} aria-labelledby="forgot-title" className="fixed inset-0 m-auto max-h-[calc(100dvh-24px)] w-[calc(100vw-24px)] max-w-[480px] overflow-y-auto rounded-[22px] border-0 bg-white p-8 text-black shadow-2xl backdrop:bg-black/65 backdrop:backdrop-blur-sm">
    <button type="button" aria-label="Close password reset" onClick={onClose} className="absolute right-4 top-4 cursor-pointer rounded-full p-2 hover:bg-neutral-100"><X size={20} /></button>
    <h1 id="forgot-title" className="mb-3 pr-8 text-2xl font-semibold tracking-tight">{success ? 'Check your email' : 'Forgot password?'}</h1>
    {success ? <>
    <div role="status" className="space-y-3 text-sm leading-6 text-neutral-600">
      <p>Đã gửi email. Vui lòng kiểm tra hộp thư để đặt lại mật khẩu.</p>
      <p className="break-all font-medium text-black">{email.trim()}</p>
    </div>
    <div className="mt-6 border-t border-neutral-100 pt-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-neutral-500">Chưa nhận được email?</span>
        <button type="button" disabled={busy || remaining > 0} onClick={() => { void sendEmail() }} className="cursor-pointer font-semibold text-black underline-offset-4 hover:underline disabled:cursor-not-allowed disabled:text-neutral-400">{busy ? 'Đang gửi...' : remaining > 0 ? `Gửi lại sau ${remaining}s` : 'Gửi lại'}</button>
      </div>
      <p className="mt-2 text-xs leading-5 text-neutral-500">Bạn nhớ kiểm tra cả thư mục Spam nhé.</p>
      {resent && <p role="status" className="mt-3 text-sm text-emerald-700">Đã gửi lại email. Vui lòng kiểm tra hộp thư.</p>}
      {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
    </div>
    </> : <>
      <p className="mb-5 text-sm leading-6 text-neutral-600">Enter your email to receive a password reset link.</p>
      <form className="grid gap-3" onChange={() => setError('')} onSubmit={async (event) => {
        event.preventDefault()
        await sendEmail()
      }}>
        <label className="grid gap-2 text-sm font-medium">Email<input autoFocus type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} className="h-11 w-full rounded-full border border-neutral-300 px-4 text-black focus:outline-2 focus:outline-neutral-500" /></label>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        <button type="submit" disabled={busy} className="mt-2 cursor-pointer rounded-full bg-black py-3 font-semibold text-white hover:bg-neutral-800 disabled:opacity-50">{busy ? 'Sending...' : 'Send reset link'}</button>
      </form>
    </>}
  </dialog>
}
