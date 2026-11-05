import { useEffect, useRef, useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'
import { requireSupabase } from '../../../lib/supabase'

export function PasswordRecoveryModal() {
  const navigate = useNavigate()
  const recovery = useAuthStore((state) => state.recovery)
  const dialog = useRef<HTMLDialogElement>(null)
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (recovery) dialog.current?.showModal() }, [recovery])
  if (!recovery) return null
  return <dialog ref={dialog} onCancel={() => useAuthStore.setState({ recovery: false })} className="fixed inset-0 m-auto w-[min(440px,95vw)] rounded-2xl bg-white p-8 shadow-2xl backdrop:bg-black/30">
    <h1 className="mb-4 text-xl font-semibold">Set a new password</h1>
    <form className="grid gap-3" onSubmit={async (event) => {
      event.preventDefault()
      if (busy) return
      if (password !== confirm) { setNotice('Passwords do not match.'); return }
      setBusy(true)
      try {
        const { error } = await requireSupabase().auth.updateUser({ password })
        if (error) throw error
        setPassword(''); setConfirm(''); setShowPassword(false); setShowConfirm(false)
        await useAuthStore.getState().logout()
        navigate('/', { replace: true, state: { loginOpen: true, passwordUpdated: true } })
      } catch (error) { setNotice(error instanceof Error ? error.message : 'Could not update password.') }
      finally { setBusy(false) }
    }}>
      <div>
        <label htmlFor="recovery-password">New password</label>
        <div className="relative">
          <input id="recovery-password" className="w-full rounded border p-2 pr-12" required minLength={6} type={showPassword ? 'text' : 'password'} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} />
          <button type="button" aria-label={showPassword ? 'Hide new password' : 'Show new password'} aria-pressed={showPassword} onClick={() => setShowPassword((visible) => !visible)} className="absolute right-1 top-1/2 grid h-9 w-9 -translate-y-1/2 cursor-pointer place-items-center rounded text-neutral-500 hover:bg-neutral-100 hover:text-black focus-visible:outline-2 focus-visible:outline-black">
            {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
          </button>
        </div>
      </div>
      <div>
        <label htmlFor="recovery-confirm">Confirm password</label>
        <div className="relative">
          <input id="recovery-confirm" className="w-full rounded border p-2 pr-12" required type={showConfirm ? 'text' : 'password'} autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} />
          <button type="button" aria-label={showConfirm ? 'Hide confirm password' : 'Show confirm password'} aria-pressed={showConfirm} onClick={() => setShowConfirm((visible) => !visible)} className="absolute right-1 top-1/2 grid h-9 w-9 -translate-y-1/2 cursor-pointer place-items-center rounded text-neutral-500 hover:bg-neutral-100 hover:text-black focus-visible:outline-2 focus-visible:outline-black">
            {showConfirm ? <EyeOff size={20} /> : <Eye size={20} />}
          </button>
        </div>
      </div>
      {notice && <p role="alert">{notice}</p>}
      <button disabled={busy} className="rounded-full bg-black p-3 text-white">{busy ? 'Saving...' : 'Save password'}</button>
    </form>
  </dialog>
}
