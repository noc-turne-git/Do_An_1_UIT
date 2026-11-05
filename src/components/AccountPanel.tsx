import { useEffect, useRef, useState } from 'react'
import { UserRound } from 'lucide-react'
import { useAuthStore } from '../features/auth/store/useAuthStore'
import { useNavigate } from 'react-router-dom'

const groups = [
  ['Update my assistant', 'Account settings', 'Personalization'],
  ['Give feedback', 'Privacy policy', 'Terms of service'],
  ['Log in'],
]

export function AccountPanel({ onClose, onLogin, onSetupAssistant, onAccountSettings, onPersonalization }: { onClose: () => void; onLogin: () => void; onSetupAssistant: () => void; onAccountSettings: () => void; onPersonalization: () => void }) {
  const [error, setError] = useState('')
  const panelRef = useRef<HTMLElement>(null)
  const user = useAuthStore((state) => state.user)
  const profilePhoto = useAuthStore((state) => state.user ? (typeof state.preferences.profilePhoto === 'string' && state.preferences.profilePhoto.trim()) || state.user.avatarUrl || '' : '')
  const navigate = useNavigate()
  const actions: Record<string, () => void> = { 'Log in': onLogin, 'Log out': async () => { try { await useAuthStore.getState().logout(); onClose(); navigate('/', { replace: true }) } catch { setError('Could not log out. Please try again.') } }, 'Update my assistant': onSetupAssistant, 'Account settings': onAccountSettings, Personalization: onPersonalization }

  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null
    panelRef.current?.focus()
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
        trigger?.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <section
      ref={panelRef}
      id="account-panel"
      role="dialog"
      aria-label="Account"
      tabIndex={-1}
      className="fixed bottom-16 left-[66px] z-40 max-h-[calc(100dvh-80px)] w-[260px] max-w-[calc(100vw-78px)] overflow-y-auto rounded-xl border border-neutral-800 bg-[#191919] p-2.5 text-neutral-200 shadow-2xl outline-none"
    >
      <button type="button" disabled className="flex w-full items-center gap-3 px-3 py-2 text-left">
        <span className="grid h-12 w-12 shrink-0 place-items-center overflow-hidden rounded-full bg-[#500d30] text-pink-200">
          {profilePhoto ? <img src={profilePhoto} alt="Your profile" className="h-full w-full object-cover" /> : <UserRound className="h-5 w-5" strokeWidth={1.8} />}
        </span>
        <span className="flex-1">
          <strong className="block text-base font-semibold">{user ? `${user.firstName} ${user.lastName}`.trim() || user.email || 'Traveler' : 'Traveler'}</strong>
        </span>
      </button>
      {error && <p role="alert" className="p-3 text-sm text-red-600">{error}</p>}
      {groups.map((items, index) => (
        <div key={index} className="mt-2 border-t border-neutral-800 pt-2">
          {items.map((item) => {
            const label = item === 'Log in' && user ? 'Log out' : item
            return (
            <button key={label} type="button" disabled={!actions[label]} onClick={actions[label]} className="block w-full rounded-lg px-3 py-2 text-left text-base font-medium enabled:cursor-pointer enabled:hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white">
              {label}
            </button>
            )
          })}
        </div>
      ))}
    </section>
  )
}
