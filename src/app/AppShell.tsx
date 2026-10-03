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
import { useState } from 'react'
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

export function AppShell() {
  const [loginOpen, setLoginOpen] = useState(false)
  const [assistantSetupOpen, setAssistantSetupOpen] = useState(false)
  const [accountSettingsOpen, setAccountSettingsOpen] = useState(false)
  const [personalizationOpen, setPersonalizationOpen] = useState(false)
  const { panel, togglePanel, closePanel } = useShellStore()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const isChatPage = /^\/chats?(\/|$)/.test(pathname)
  const user = useAuthStore((state) => state.user)

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
          <UserRound className="h-5 w-5" strokeWidth={1.8} />
        </button>
      </aside>

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
        if (user) setAssistantSetupOpen(true)
        else setLoginOpen(true)
      }} onAccountSettings={() => {
        closePanel()
        if (user) setAccountSettingsOpen(true)
        else setLoginOpen(true)
      }} onPersonalization={() => {
        closePanel()
        if (user) setPersonalizationOpen(true)
        else setLoginOpen(true)
      }} />}
      {user && personalizationOpen && <PersonalizationModal onClose={() => {
        setPersonalizationOpen(false)
        document.querySelector<HTMLButtonElement>('button[aria-label="Account"]')?.focus()
      }} />}
      {user && accountSettingsOpen && <AccountSettingsModal onClose={() => {
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
