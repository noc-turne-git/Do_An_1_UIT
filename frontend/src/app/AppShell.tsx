import { OnboardingModal } from '../features/preferences/components/OnboardingModal'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  BellRing,
  Heart,
  MessageCircle,
  PlaneTakeoff,
  Search,
  UserRound,
} from 'lucide-react'
import { AccountPanel } from '../components/AccountPanel'
import { useEffect, useState } from 'react'
import { LoginModal } from '../features/auth/components/LoginModal'
import { AssistantSetupModal } from '../features/auth/components/AssistantSetupModal'
import { AccountSettingsModal } from '../features/auth/components/AccountSettingsModal'
import { PersonalizationModal } from '../features/auth/components/PersonalizationModal'
import { ChatsOverlay, NotificationsPanel, useShellStore } from '../features/chat'
import { useAuthStore } from '../features/auth/store/useAuthStore'

const nav = [
  { to: '/trips', label: 'Trips', icon: PlaneTakeoff },
  { to: '/explore', label: 'Explore places', icon: Search },
  { to: '/saved', label: 'Saved places', icon: Heart },
]

function OnboardingPrompt() {
  const [initiallyComplete] = useState(() => useAuthStore.getState().preferences.onboardingComplete === true)
  const [dismissed, setDismissed] = useState(false)
  return initiallyComplete || dismissed ? null : <OnboardingModal onClose={() => setDismissed(true)} />
}

function ProfileSavedNotice({ onDismiss }: { onDismiss: () => void }) {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, 4000)
    return () => window.clearTimeout(timer)
  }, [onDismiss])
  return <div role="status" className="fixed bottom-6 left-1/2 z-50 flex w-max max-w-[calc(100vw-32px)] -translate-x-1/2 items-center gap-4 rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-3 text-sm font-medium text-emerald-900 shadow-lg">
    Profile updated successfully.
    <button type="button" aria-label="Dismiss notification" onClick={onDismiss} className="cursor-pointer rounded px-2 py-1 hover:bg-emerald-100">×</button>
  </div>
}

export function AppShell() {
  const ready = useAuthStore((state) => state.ready)
  const profileError = useAuthStore((state) => state.profileError)
  const recovery = useAuthStore((state) => state.recovery)
  const [loginOpen, setLoginOpen] = useState(false)
  const [assistantSetupOpen, setAssistantSetupOpen] = useState(false)
  const [accountSettingsOpen, setAccountSettingsOpen] = useState(false)
  const [profileSaved, setProfileSaved] = useState(false)
  const [personalizationOpen, setPersonalizationOpen] = useState(false)
  const { panel, togglePanel, closePanel } = useShellStore()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const isChatPage = /^\/chats?(\/|$)/.test(pathname)
  const user = useAuthStore((state) => state.user)
  const profilePhoto = useAuthStore((state) => state.user ? (typeof state.preferences.profilePhoto === 'string' && state.preferences.profilePhoto.trim()) || state.user.avatarUrl || '' : '')

  return (
    <div className="flex min-h-screen bg-white text-neutral-900">
      <aside className="sticky top-0 z-30 flex h-dvh w-[58px] shrink-0 flex-col items-center gap-3 border-r border-neutral-100 bg-white py-4">
        {/* Home */}
        <NavLink
          to="/home"
          onClick={closePanel}
          aria-label="Home"
          className="mb-5 grid h-9 w-9 place-items-center rounded-xl bg-neutral-900 text-white"
        >
          <span className="text-lg">✦</span>
        </NavLink>

        {/* Chats */}
        <button
          aria-label="Chats"
          aria-pressed={panel === 'chats'}
          aria-current={isChatPage ? 'page' : undefined}
          onClick={() => togglePanel('chats')}
          className={`group relative grid h-10 w-10 cursor-pointer place-items-center rounded-xl transition-colors ${
            panel === 'chats' || (isChatPage && !panel)
              ? 'bg-neutral-900 text-white'
              : 'text-neutral-400 hover:bg-neutral-200 hover:text-neutral-900'
          }`}
        >
          <MessageCircle className="h-5 w-5" strokeWidth={1.8} />

          <span className="pointer-events-none absolute left-12 whitespace-nowrap rounded-lg bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
            Chats
          </span>
        </button>

        {/* Navigation */}
        {nav.map((item) => {
          const Icon = item.icon

          return (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={closePanel}
              aria-label={item.label}
              className={({ isActive }) =>
                `group relative grid h-10 w-10 place-items-center rounded-xl transition-colors ${
                  isActive && !panel
                    ? 'bg-neutral-900 text-white'
                    : 'text-neutral-400 hover:bg-neutral-200 hover:text-neutral-900'
                }`
              }
            >
              <Icon className="h-5 w-5" strokeWidth={1.8} />

              <span className="pointer-events-none absolute left-12 whitespace-nowrap rounded-lg bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
                {item.label}
              </span>
            </NavLink>
          )
        })}

        {/* Notifications */}
        <button
          aria-label="Notifications"
          aria-pressed={panel === 'notifications'}
          onClick={() => togglePanel('notifications')}
          className={`group relative cursor-pointer mt-1 grid h-10 w-10 place-items-center rounded-xl transition-colors ${
            panel === 'notifications'
              ? 'bg-neutral-900 text-white'
              : 'text-neutral-400 hover:bg-neutral-200 hover:text-neutral-900'
          }`}
        >
          <BellRing className="h-5 w-5" strokeWidth={1.8} />

          <span className="pointer-events-none absolute left-12 whitespace-nowrap rounded-lg bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
            Notifications
          </span>
        </button>
        {/* Account */}
        <button
          type="button"
          aria-label="Account"
          aria-expanded={panel === 'account'}
          aria-controls={panel === 'account' ? 'account-panel' : undefined}
          aria-haspopup="dialog"
          onClick={() => togglePanel('account')}
          className={`mt-auto cursor-pointer grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#500d30] text-pink-200 transition-colors hover:bg-[#701343] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-pink-700 ${panel === 'account' ? 'ring-2 ring-pink-300 ring-offset-2' : ''}`}
        >
          {profilePhoto ? <img src={profilePhoto} alt="" className="h-full w-full rounded-full object-cover" /> : <UserRound className="h-5 w-5" strokeWidth={1.8} />}
        </button>
      </aside>

      {profileError && <p role="alert" className="fixed left-16 top-2 z-50 rounded bg-red-50 p-3 text-red-800">{profileError}</p>}
      {ready && user && !profileError && !recovery && (
        <OnboardingPrompt key={user.id} />
      )}
      <main className="min-w-0 flex-1">
        <Outlet />
      </main>

      {panel && (
        <div
          className="fixed inset-0 z-20"
          onClick={closePanel}
          aria-hidden="true"
        />
      )}

      {panel === 'account' && <AccountPanel onClose={closePanel} onLogin={() => {
        closePanel()
        setLoginOpen(true)
      }} onSetupAssistant={() => {
        closePanel()
        if (user && ready && !profileError) setAssistantSetupOpen(true)
        else setLoginOpen(true)
      }} onAccountSettings={() => {
        closePanel()
        if (user && ready && !profileError) setAccountSettingsOpen(true)
        else setLoginOpen(true)
      }} onPersonalization={() => {
        closePanel()
        if (user && ready && !profileError) setPersonalizationOpen(true)
        else setLoginOpen(true)
      }} />}
      {user && personalizationOpen && <PersonalizationModal onClose={() => {
        setPersonalizationOpen(false)
        document.querySelector<HTMLButtonElement>('button[aria-label="Account"]')?.focus()
      }} />}
      {user && profileSaved && <ProfileSavedNotice onDismiss={() => setProfileSaved(false)} />}
      {user && accountSettingsOpen && <AccountSettingsModal onSaved={() => setProfileSaved(true)} onClose={() => {
        setAccountSettingsOpen(false)
        document.querySelector<HTMLButtonElement>('button[aria-label="Account"]')?.focus()
      }} />}
      {user && assistantSetupOpen && <AssistantSetupModal onClose={() => {
        setAssistantSetupOpen(false)
        document.querySelector<HTMLButtonElement>('button[aria-label="Account"]')?.focus()
      }} />}
      {loginOpen && <LoginModal onClose={() => {
        setLoginOpen(false)
        document.querySelector<HTMLButtonElement>('button[aria-label="Account"]')?.focus()
      }} />}

      {panel && panel !== 'account' && (
        <section className="fixed bottom-0 left-[58px] top-0 z-30 w-[min(360px,calc(100vw-58px))] border-r border-neutral-200 bg-white shadow-xl">
          {panel === 'chats' ? (
            <ChatsOverlay
              onNavigate={(to) => {
                closePanel()
                navigate(to)
              }}
            />
          ) : (
            <NotificationsPanel
              onExplore={() => {
                closePanel()
                navigate('/explore')
              }}
            />
          )}
        </section>
      )}
    </div>
  )
}
