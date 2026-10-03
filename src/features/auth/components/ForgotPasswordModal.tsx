import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { useAuthStore } from '../store/useAuthStore'

export function ForgotPasswordModal({ initialEmail, onClose, onBack }: { initialEmail: string; onClose: () => void; onBack: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [email, setEmail] = useState(initialEmail)
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  useEffect(() => {
    const dialog = dialogRef.current
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog?.showModal()
    return () => { dialog?.close(); document.body.style.overflow = overflow }
  }, [])
  const inputClass = 'h-11 w-full rounded-full border border-neutral-300 px-4 text-black focus:outline-2 focus:outline-neutral-500'
  return <dialog ref={dialogRef} onCancel={onClose} aria-labelledby="forgot-title" className="fixed inset-0 m-auto max-h-[calc(100dvh-24px)] w-[calc(100vw-24px)] max-w-[480px] overflow-y-auto rounded-[22px] border-0 bg-white p-8 text-black shadow-2xl backdrop:bg-black/65 backdrop:backdrop-blur-sm">
    <button type="button" aria-label="Close password reset" onClick={onClose} className="absolute right-4 top-4 cursor-pointer rounded-full p-2 hover:bg-neutral-100"><X size={20} /></button>
    <h1 id="forgot-title" className="mb-3 pr-8 text-2xl font-semibold">Forgot password?</h1>
    {success ? <p role="status" className="mb-5">Password updated. You can log in with your new password.</p> : <>
      <p className="mb-5 text-sm text-neutral-600">For this demo, reset your mock account password here. No email is sent.</p>
      <form className="grid gap-3" onChange={() => setError('')} onSubmit={(event) => {
        event.preventDefault()
        if (password !== confirm) { setError('Passwords do not match.'); return }
        try {
          useAuthStore.getState().resetPassword(email, password)
          setPassword(''); setConfirm(''); setSuccess(true)
        } catch (error) { setError(error instanceof Error ? error.message : 'Could not reset password.') }
      }}>
        <label className="grid gap-1 text-sm">Email<input autoFocus type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} className={inputClass} /></label>
        <label className="grid gap-1 text-sm">New password<input type="password" autoComplete="new-password" required value={password} onChange={(event) => setPassword(event.target.value)} className={inputClass} /></label>
        <label className="grid gap-1 text-sm">Confirm password<input type="password" autoComplete="new-password" required value={confirm} onChange={(event) => setConfirm(event.target.value)} className={inputClass} /></label>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        <button type="submit" className="mt-2 cursor-pointer rounded-full bg-black py-3 font-semibold text-white hover:bg-neutral-800">Reset password</button>
      </form>
    </>}
    <button type="button" onClick={onBack} className="mt-5 w-full cursor-pointer text-sm font-semibold underline underline-offset-4">Back to log in</button>
  </dialog>
}
