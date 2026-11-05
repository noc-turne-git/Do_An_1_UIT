import { useEffect, useRef, useState } from 'react'
import { Eye, EyeOff, X } from 'lucide-react'
import { RegisterModal } from './RegisterModal'
import { useAuthStore } from '../store/useAuthStore'
import { useNavigate } from 'react-router-dom'
import { ForgotPasswordModal } from './ForgotPasswordModal'

export function LoginModal({ onClose, passwordUpdated = false }: { onClose: () => void; passwordUpdated?: boolean }) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [forgotOpen, setForgotOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [registerOpen, setRegisterOpen] = useState(false)
  const [notice, setNotice] = useState('')
  const dialogRef = useRef<HTMLDialogElement>(null)
  const socialButtonClass =
    "flex h-10 min-w-0 items-center justify-center gap-2 whitespace-nowrap rounded-full " +
    "border border-neutral-300 bg-white px-3 py-2 text-xs font-semibold text-black " +
    "transition-all duration-200 " +
    "hover:border-neutral-500 hover:bg-neutral-100 hover:shadow-md hover:scale-[1.02] " +
    "active:scale-[0.98]";
  const privacyButtonClass = 'font-semibold underline underline-offset-2 cursor-pointer hover:font-bold'
  useEffect(() => {
    if (registerOpen || forgotOpen) return
    const dialog = dialogRef.current
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog?.showModal()
    return () => {
      dialog?.close()
      document.body.style.overflow = previousOverflow
    }
  }, [registerOpen, forgotOpen])

  async function handleGoogleLogin() {
    if (busy) return
    setBusy(true)
    setNotice('')
    try {
      await useAuthStore.getState().loginWithGoogle()
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not sign in with Google. Please try again.')
      setBusy(false)
    }
  }

  if (registerOpen) {
    return <RegisterModal initialEmail={email.trim()} onClose={onClose} onBackToLogin={() => setRegisterOpen(false)} />
  }
  if (forgotOpen) return <ForgotPasswordModal initialEmail={email} onClose={onClose} />

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="login-title"
      onCancel={onClose}
      onClick={(event) => {
        if (event.target !== event.currentTarget) return
        const bounds = event.currentTarget.getBoundingClientRect()
        if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose()
      }}
      className="fixed top-1/2 left-1/2 right-auto bottom-auto m-0 -translate-x-1/2 -translate-y-1/2 max-h-[calc(100dvh-24px)] w-[calc(100%_-_24px)] max-w-[480px] overflow-hidden rounded-[22px] border border-white/5 bg-white p-0 text-[#ededed] shadow-2xl backdrop:bg-black/65 backdrop:backdrop-blur-sm"
    >
      <button type="button" onClick={onClose} aria-label="Close authentication" className="absolute right-5 top-4 grid h-9 w-9 cursor-pointer text-black place-items-center rounded-full hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white">
        <X className="h-5 w-5" />
      </button>
      <div className="px-5 py-5 sm:px-8 sm:py-6 [@media(max-height:600px)]:py-3">
        <h1 id="login-title" className="mt-2 mb-4 text-[26px] leading-tight font-semibold text-black tracking-tight sm:text-[30px]">Welcome to Travelio 👋</h1>
        {passwordUpdated && <p role="status" className="mb-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">Đã cập nhật mật khẩu thành công. Vui lòng đăng nhập bằng mật khẩu mới.</p>}
        <form onSubmit={async (event) => {
          event.preventDefault()
          if (busy) return
          setBusy(true)
          setNotice('')
          try {
            await useAuthStore.getState().login(email, password)
            onClose()
            navigate('/home', { replace: true })
          } catch (error) {
            setNotice(error instanceof Error ? error.message : 'Could not log in. Please try again.')
          } finally { setBusy(false) }
        }}>
          <label htmlFor="login-email" className="sr-only">Email</label>
          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoFocus
            id="login-email"
            name="email"
            type="email"
            autoComplete="email"
            placeholder="Email"
            required
            className="h-10 w-full rounded-full border border-neutral-300 bg-transparent px-4 text-base text-black outline-none placeholder:text-neutral-400 placeholder:opacity-60 focus:border-neutral-400 focus:ring-0" style={{
              color: '#000000',
              WebkitTextFillColor: '#000000',
            }} />
          <label htmlFor="login-password" className="sr-only">Password</label>
          <div className="relative mt-3">
            <input id="login-password" name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" placeholder="Password" required value={password} onChange={(event) => setPassword(event.target.value)} className="h-10 w-full rounded-full border border-neutral-300 bg-transparent pr-12 pl-4 text-base text-black outline-none placeholder:text-neutral-500 focus:border-neutral-400 focus:ring-2 focus:ring-neutral-400/20" />
            <button type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword} onClick={() => setShowPassword((visible) => !visible)} className="absolute top-0 right-2 mt-1 grid h-8 w-8 cursor-pointer place-items-center rounded-full text-neutral-400 hover:text-neutral-500 focus-visible:outline-2 focus-visible:outline-current">
              {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
            </button>
          </div>
          <button
            type="submit"
            disabled={busy}
            className="
              mt-3 mb-3 h-11 w-full rounded-full
              bg-black text-base font-semibold text-white
              shadow-lg
              transition-all duration-200
              hover:bg-neutral-800
              hover:shadow-xl
              hover:scale-[1.01]
              active:scale-[0.99]
              focus-visible:outline-2
              focus-visible:outline-offset-4
              focus-visible:outline-black
            "
            style={{ cursor: 'pointer' }}
          >
            {busy ? 'Logging in...' : 'Continue'}
          </button>
        </form>
        <div className="mb-3 text-right"><button type="button" className="cursor-pointer mb-5 text-[5px] font-semibold text-black" onClick={() => { setForgotOpen(true); setPassword(''); setNotice('') }}>Forgot password?</button></div>
        <p className="mb-3 text-center text-sm text-black">
          Don't have an account?{' '}
          <button
            type="button"
            className="ml-2 inline-block cursor-pointer font-semibold underline underline-offset-4 transition-transform duration-200 hover:scale-110"
            onClick={() => {
              setPassword('')
              setShowPassword(false)
              setNotice('')
              setRegisterOpen(true)
            }}
          >
            Register
          </button>
        </p>
        <div className="mb-3 text-black flex items-center gap-3 text-sm"><span className="h-px flex-1 bg-neutral-800" />or<span className="h-px flex-1 bg-neutral-800" /></div>
        <div className="mb-3 grid grid-cols-1 gap-2">
          <button type="button" disabled={busy} onClick={handleGoogleLogin} className={socialButtonClass} style={{ cursor: 'pointer' }}>
            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 shrink-0"><path fill="#4285F4" d="M21.6 12.23c0-.71-.06-1.39-.18-2.05H12v3.88h5.38a4.6 4.6 0 0 1-2 3.02v2.51h3.24c1.9-1.75 2.98-4.33 2.98-7.36Z" /><path fill="#34A853" d="M12 22c2.7 0 4.96-.9 6.62-2.41l-3.24-2.51c-.9.6-2.05.96-3.38.96-2.6 0-4.8-1.76-5.59-4.12H3.06v2.59A10 10 0 0 0 12 22Z" /><path fill="#FBBC05" d="M6.41 13.92a6 6 0 0 1 0-3.84V7.49H3.06a10 10 0 0 0 0 9.02l3.35-2.59Z" /><path fill="#EA4335" d="M12 5.96c1.47 0 2.79.5 3.82 1.49l2.87-2.87A9.6 9.6 0 0 0 12 2a10 10 0 0 0-8.94 5.49l3.35 2.59A5.99 5.99 0 0 1 12 5.96Z" /></svg>
            Google
          </button>
        </div>
        {notice && <p role="status" className="mb-3 text-center text-sm" style={{ color: 'red' }}>{notice}</p>}
        <p className="text-center text-xs leading-5 text-neutral-500">
          By continuing, you agree to Travelio's <span className={privacyButtonClass}>Terms of Service</span> and acknowledge you’ve read our <span className={privacyButtonClass}>Privacy Policy</span>.
        </p>
      </div>
    </dialog>
  )
}
