import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  BellRing,
  Heart,
  MessageCircle,
  PlaneTakeoff,
  Search,
} from 'lucide-react'
import { ChatsOverlay, NotificationsPanel, useShellStore } from '../features/chat'

const nav = [
  { to: '/trips', label: 'Trips', icon: PlaneTakeoff },
  { to: '/explore', label: 'Explore places', icon: Search },
  { to: '/saved', label: 'Saved places', icon: Heart },
]

export function AppShell() {
  const { panel, togglePanel, closePanel } = useShellStore()
  const navigate = useNavigate()

  return (
    <div className="flex min-h-screen bg-white text-neutral-900">
      <aside className="relative z-30 flex w-[58px] shrink-0 flex-col items-center gap-3 border-r border-neutral-100 bg-white py-4">
        {/* Home */}
        <NavLink
          to="/"
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
          onClick={() => togglePanel('chats')}
          className={`group relative grid h-10 w-10 place-items-center rounded-xl transition-colors ${
            panel === 'chats'
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
          className={`group relative mt-1 grid h-10 w-10 place-items-center rounded-xl transition-colors ${
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

      {panel && (
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