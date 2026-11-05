import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PasswordRecoveryModal } from '../features/auth/components/PasswordRecoveryModal'
import { useAuthStore } from '../features/auth/store/useAuthStore'
import { requireSupabase } from '../lib/supabase'
import { LandingPage } from './LandingPage'

export function ResetPasswordPage() {
  const recovery = useAuthStore((state) => state.recovery)
  const [checked, setChecked] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    // Wait for the SDK to process the email URL before judging the recovery link.
    async function checkLink() {
      try {
        const { error } = await requireSupabase().auth.getSession()
        if (error && active) setError('Could not verify this reset link. Please request a new email.')
      } catch {
        if (active) setError('Could not verify this reset link. Please request a new email.')
      } finally { if (active) setChecked(true) }
    }
    void checkLink()
    return () => { active = false }
  }, [])
  return <>
    <LandingPage />
    {!recovery && <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-6">
      <section className="w-full max-w-[440px] rounded-2xl bg-white p-8 text-center text-neutral-900 shadow-2xl">
        <h1 className="text-xl font-semibold">Reset your password</h1>
        <p role="status" className="mt-4 text-sm leading-6 text-neutral-600">{error || (checked ? 'This reset link is invalid or has expired. Please request a new password reset email.' : 'Checking your reset link...')}</p>
        {checked && <Link to="/" className="mt-5 inline-block underline">Return to Travelio</Link>}
      </section>
    </div>
    }
    <PasswordRecoveryModal />
  </>
}
