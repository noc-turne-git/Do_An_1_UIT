import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { requireSupabase } from '../lib/supabase'

export function AuthCallbackPage() {
  const navigate = useNavigate()
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    async function finishSignIn() {
      try {
        const params = new URLSearchParams(window.location.hash.slice(1))
        const query = new URLSearchParams(window.location.search)
        const providerError = params.get('error_description') || query.get('error_description')
          || params.get('error') || query.get('error')
        // Remove callback credentials/errors from browser history after the SDK has read them.
        const { data, error: sessionError } = await requireSupabase().auth.getSession()
        if (!active) return
        window.history.replaceState(window.history.state, '', window.location.pathname)
        if (providerError) throw new Error(providerError)
        if (sessionError) throw sessionError
        if (!data.session) throw new Error('Google sign-in was not completed. Please try again.')
        navigate('/home', { replace: true })
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : 'Could not sign in with Google. Please try again.')
      }
    }
    void finishSignIn()
    return () => { active = false }
  }, [navigate])

  return <main className="grid min-h-dvh place-items-center bg-neutral-50 p-6 text-neutral-900">
    <section className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow-lg">
      <h1 className="text-xl font-semibold">Sign in with Google</h1>
      <p role={error ? 'alert' : 'status'} className="mt-4 text-sm">{error || 'Completing your sign-in...'}</p>
      {error && <Link to="/" className="mt-5 inline-block underline">Return to Travelio</Link>}
    </section>
  </main>
}
