import { useEffect, useRef, useState } from 'react'
import { Eye, EyeOff, X } from 'lucide-react'
import { OnboardingModal } from '../../preferences/components/OnboardingModal'
import { useAuthStore } from '../store/useAuthStore'

type RegisterModalProps = {
  initialEmail: string
  onClose: () => void
  onBackToLogin: () => void
}

export function RegisterModal({
  initialEmail,
  onClose,
  onBackToLogin,
}: RegisterModalProps) {
  const [email, setEmail] = useState(initialEmail)
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)

  const [submitted, setSubmitted] = useState(false)
  const [notice, setNotice] = useState('')
  const [onboardingOpen, setOnboardingOpen] = useState(false)

  const dialogRef = useRef<HTMLDialogElement>(null)
  const confirmPasswordRef = useRef<HTMLInputElement>(null)

  const passwordMismatch =
    submitted && password !== confirmPassword

  const socialButtonClass =
    'flex h-10 min-w-0 items-center justify-center gap-2 whitespace-nowrap rounded-full ' +
    'border border-neutral-300 bg-white px-3 py-2 text-xs font-semibold text-black ' +
    'transition-all duration-200 ' +
    'hover:border-neutral-500 hover:bg-neutral-100 hover:shadow-md hover:scale-[1.02] ' +
    'active:scale-[0.98]'

  const privacyButtonClass =
    'cursor-pointer font-semibold underline underline-offset-2 hover:font-bold'

  useEffect(() => {
    if (onboardingOpen) return

    const dialog = dialogRef.current
    const previousOverflow = document.body.style.overflow

    document.body.style.overflow = 'hidden'
    dialog?.showModal()

    return () => {
      dialog?.close()
      document.body.style.overflow = previousOverflow
    }
  }, [onboardingOpen])

  function unavailable(provider: string) {
    setNotice(
      `${provider} sign-in is not available yet. Please try again later.`
    )
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()

    setSubmitted(true)
    setNotice('')

    if (password !== confirmPassword) {
      confirmPasswordRef.current?.focus()
      return
    }

    try {
      useAuthStore.getState().register(email, password)
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not register. Please try again.')
      return
    }
    setPassword('')
    setConfirmPassword('')
    setOnboardingOpen(true)
  }

  if (onboardingOpen) {
    return (
      <OnboardingModal
        email={email.trim()}
        onClose={onClose}
      />
    )
  }

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="register-title"
      onCancel={onClose}
      onClick={(event) => {
        if (event.target !== event.currentTarget) return

        const bounds = event.currentTarget.getBoundingClientRect()

        if (
          event.clientX < bounds.left ||
          event.clientX > bounds.right ||
          event.clientY < bounds.top ||
          event.clientY > bounds.bottom
        ) {
          onClose()
        }
      }}
      className="
        fixed top-1/2 left-1/2 right-auto bottom-auto m-0
        -translate-x-1/2 -translate-y-1/2
        max-h-[calc(100dvh-24px)]
        w-[calc(100%_-_24px)] max-w-[480px]
        overflow-hidden
        rounded-[22px]
        border border-black/5
        bg-white
        p-0
        text-black
        shadow-2xl
        backdrop:bg-black/65
        backdrop:backdrop-blur-sm
      "
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="Close authentication"
        className="
          absolute top-4 right-5
          grid h-9 w-9 place-items-center
          cursor-pointer rounded-full
          text-black
          transition-colors duration-200
          hover:bg-black/5
          focus-visible:outline-2
          focus-visible:outline-black
        "
      >
        <X className="h-5 w-5" />
      </button>

      <div className="px-5 py-5 sm:px-8 sm:py-6 [@media(max-height:600px)]:py-3">
        <h1
          id="register-title"
          className="
            mt-2 mb-2
            text-[25px] leading-tight
            font-semibold tracking-tight
            text-black
            sm:text-[30px]
          "
        >
          Create an account 👋
        </h1>

        <p className="mb-3 text-sm text-neutral-600">
          Signing up for Travelio is fast and free.
        </p>

        <form onSubmit={handleSubmit}>
          <label
            htmlFor="register-email"
            className="sr-only"
          >
            Email
          </label>

          <input
            autoFocus
            id="register-email"
            name="email"
            type="email"
            autoComplete="email"
            placeholder="Email"
            required
            value={email}
            onChange={(event) =>
              setEmail(event.target.value)
            }
            className="
              mb-3 h-10 w-full
              rounded-full
              border border-neutral-300
              bg-transparent
              px-4
              text-base text-black
              outline-none
              placeholder:text-neutral-500
              placeholder:opacity-100
              focus:border-neutral-400
              focus:ring-0
            "
          />

          <label
            htmlFor="register-password"
            className="sr-only"
          >
            Password
          </label>

          <div className="relative">
            <input
              id="register-password"
              name="password"
              type={showPassword ? 'text' : 'password'}
              autoComplete="new-password"
              placeholder="Password"
              required
              value={password}
              onChange={(event) => {
                setPassword(event.target.value)
                if (submitted) {
                  setSubmitted(false)
                }
              }}
              className="
                h-10 w-full
                rounded-full
                border border-neutral-300
                bg-transparent
                pr-12 pl-4
                text-base text-black
                outline-none
                placeholder:text-neutral-500
                focus:border-neutral-400
                focus:ring-2
                focus:ring-neutral-400/20
              "
            />

            <button
              type="button"
              aria-label={
                showPassword
                  ? 'Hide password'
                  : 'Show password'
              }
              aria-pressed={showPassword}
              onClick={() =>
                setShowPassword((visible) => !visible)
              }
              className="
                absolute top-1 right-2
                grid h-8 w-8 place-items-center
                cursor-pointer rounded-full
                text-neutral-400
                transition-colors
                hover:text-neutral-600
                focus-visible:outline-2
                focus-visible:outline-current
              "
            >
              {showPassword ? (
                <EyeOff className="h-5 w-5" />
              ) : (
                <Eye className="h-5 w-5" />
              )}
            </button>
          </div>

          <label
            htmlFor="register-confirm-password"
            className="sr-only"
          >
            Confirm password
          </label>

          <div className="relative mt-3">
            <input
              ref={confirmPasswordRef}
              id="register-confirm-password"
              name="confirmPassword"
              type={
                showConfirmPassword
                  ? 'text'
                  : 'password'
              }
              autoComplete="new-password"
              placeholder="Confirm password"
              required
              value={confirmPassword}
              onChange={(event) => {
                setConfirmPassword(event.target.value)

                if (submitted) {
                  setSubmitted(false)
                }
              }}
              aria-invalid={passwordMismatch}
              aria-describedby={
                passwordMismatch
                  ? 'password-mismatch'
                  : undefined
              }
              className="
                h-10 w-full
                rounded-full
                border border-neutral-300
                bg-transparent
                pr-12 pl-4
                text-base text-black
                outline-none
                placeholder:text-neutral-500
                focus:border-neutral-400
                focus:ring-2
                focus:ring-neutral-400/20
                aria-invalid:border-red-500
              "
            />

            <button
              type="button"
              aria-label={
                showConfirmPassword
                  ? 'Hide confirm password'
                  : 'Show confirm password'
              }
              aria-pressed={showConfirmPassword}
              onClick={() =>
                setShowConfirmPassword(
                  (visible) => !visible
                )
              }
              className="
                absolute top-1 right-2
                grid h-8 w-8 place-items-center
                cursor-pointer rounded-full
                text-neutral-400
                transition-colors
                hover:text-neutral-600
                focus-visible:outline-2
                focus-visible:outline-current
              "
            >
              {showConfirmPassword ? (
                <EyeOff className="h-5 w-5" />
              ) : (
                <Eye className="h-5 w-5" />
              )}
            </button>
          </div>

          {passwordMismatch && (
            <p
              id="password-mismatch"
              role="alert"
              className="mt-2 text-sm text-red-500"
            >
              Passwords do not match.
            </p>
          )}

          <button
            type="submit"
            className="
              mt-3 mb-3
              h-11 w-full
              cursor-pointer
              rounded-full
              bg-black
              text-base font-semibold text-white
              shadow-lg
              transition-all duration-200
              hover:scale-[1.01]
              hover:bg-neutral-800
              hover:shadow-xl
              active:scale-[0.99]
              focus-visible:outline-2
              focus-visible:outline-offset-4
              focus-visible:outline-black
            "
          >
            Continue
          </button>
        </form>

        <p className="mb-3 text-center text-sm text-black">
          Already have an account?{' '}
          <button
            type="button"
            onClick={onBackToLogin}
            className="
              ml-2 inline-block
              cursor-pointer
              font-semibold
              underline underline-offset-4
              transition-transform duration-200
              hover:scale-110
            "
          >
            Log in
          </button>
        </p>

        <div className="mb-3 flex items-center gap-3 text-sm text-black">
          <span className="h-px flex-1 bg-neutral-800" />

          <span>or</span>

          <span className="h-px flex-1 bg-neutral-800" />
        </div>

        <div className="mb-3 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => unavailable('Google')}
            className={socialButtonClass}
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              className="h-5 w-5 shrink-0"
            >
              <path
                fill="#4285F4"
                d="M21.6 12.23c0-.71-.06-1.39-.18-2.05H12v3.88h5.38a4.6 4.6 0 0 1-2 3.02v2.51h3.24c1.9-1.75 2.98-4.33 2.98-7.36Z"
              />
              <path
                fill="#34A853"
                d="M12 22c2.7 0 4.96-.9 6.62-2.41l-3.24-2.51c-.9.6-2.05.96-3.38.96-2.6 0-4.8-1.76-5.59-4.12H3.06v2.59A10 10 0 0 0 12 22Z"
              />
              <path
                fill="#FBBC05"
                d="M6.41 13.92a6 6 0 0 1 0-3.84V7.49H3.06a10 10 0 0 0 0 9.02l3.35-2.59Z"
              />
              <path
                fill="#EA4335"
                d="M12 5.96c1.47 0 2.79.5 3.82 1.49l2.87-2.87A9.6 9.6 0 0 0 12 2a10 10 0 0 0-8.94 5.49l3.35 2.59A5.99 5.99 0 0 1 12 5.96Z"
              />
            </svg>

            <span>Google</span>
          </button>

          <button
            type="button"
            onClick={() => unavailable('Apple')}
            className={socialButtonClass}
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              fill="currentColor"
              className="h-6 w-6 shrink-0"
            >
              <path d="M17.05 12.54c.03 3.25 2.85 4.33 2.88 4.34-.02.08-.45 1.54-1.49 3.05-.9 1.3-1.83 2.6-3.3 2.63-1.45.03-1.92-.85-3.58-.85-1.65 0-2.17.82-3.54.88-1.42.05-2.5-1.41-3.4-2.71-1.85-2.67-3.27-7.56-1.37-10.86a5.27 5.27 0 0 1 4.45-2.7c1.39-.03 2.7.94 3.55.94.85 0 2.44-1.16 4.11-.99.7.03 2.67.28 3.94 2.14-.1.06-2.35 1.37-2.25 4.13ZM14.33 4.5c.75-.91 1.25-2.18 1.11-3.45-1.08.04-2.4.72-3.18 1.63-.7.8-1.31 2.08-1.15 3.3 1.2.1 2.43-.61 3.22-1.48Z" />
            </svg>

            <span>Apple</span>
          </button>
        </div>

        {notice && (
          <p
            role="status"
            className="mb-3 text-center text-sm text-red-500"
          >
            {notice}
          </p>
        )}

        <p className="text-center text-xs leading-5 text-neutral-500">
          By continuing, you agree to Travelio’s{' '}
          <span className={privacyButtonClass}>
            Terms of Service
          </span>{' '}
          and acknowledge you’ve read our{' '}
          <span className={privacyButtonClass}>
            Privacy Policy
          </span>
          .
        </p>
      </div>
    </dialog>
  )
}
