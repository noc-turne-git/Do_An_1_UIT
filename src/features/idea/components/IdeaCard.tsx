import { Ellipsis, Heart } from 'lucide-react'
import { IDEA_DURATIONS, IDEA_RATINGS, getImageUrl, getIdeaTag, IDEA_ACTIONS } from './ideaData'
import type { Idea, IdeaAction } from './ideaTypes'

type IdeaCardProps = {
  idea: Idea
  index: number
  liked: boolean
  menuOpen: boolean
  onViewDetails: () => void
  onToggleLike: () => void
  onToggleMenu: () => void
  onAction: (action: IdeaAction) => void
}

function IdeaActionMenu({ onAction }: { onAction: (action: IdeaAction) => void }) {
  return (
    <div className="absolute right-3 top-14 z-10 w-52 rounded-xl border border-neutral-100 bg-white p-1 text-sm shadow-xl">
      {IDEA_ACTIONS.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          onClick={() => onAction(id)}
          className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left hover:bg-neutral-50 ${id === 'delete' ? 'text-red-600' : ''}`}
        >
          <Icon size={16} />
          {label}
        </button>
      ))}
    </div>
  )
}

export function IdeaCard({
  idea,
  index,
  liked,
  menuOpen,
  onViewDetails,
  onToggleLike,
  onToggleMenu,
  onAction,
}: IdeaCardProps) {
  return (
    <article className="group relative overflow-visible rounded-2xl border border-neutral-200 bg-white">
      <button
        aria-label={`View ${idea.name} details`}
        onClick={onViewDetails}
        className="relative block w-full overflow-hidden rounded-t-2xl text-left"
      >
        <img src={getImageUrl(idea.image)} alt="" className="h-48 w-full object-cover transition duration-300 group-hover:scale-[1.02]" />
        <span className="absolute left-3 top-3 rounded-full bg-neutral-950/75 px-3 py-1 text-xs font-medium text-white">
          {getIdeaTag(idea.type)}
        </span>
      </button>

      <div className="absolute right-3 top-3 z-[1] flex gap-2 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
        <button
          aria-label={`${liked ? 'Unsave' : 'Save'} ${idea.name}`}
          onClick={onToggleLike}
          className={`grid h-9 w-9 place-items-center rounded-full border bg-white/95 shadow-sm ${liked ? 'text-rose-600' : 'text-neutral-700'}`}
        >
          <Heart size={17} fill={liked ? 'currentColor' : 'none'} />
        </button>
        <button
          aria-label={`More actions for ${idea.name}`}
          onClick={onToggleMenu}
          className="grid h-9 w-9 place-items-center rounded-full border bg-white/95 text-neutral-700 shadow-sm"
        >
          <Ellipsis size={18} />
        </button>
      </div>

      <div className="p-4">
        <h3 className="truncate font-semibold">{idea.name}</h3>
        <p className="mt-1 text-sm text-neutral-500">{idea.type}</p>
        <div className="mt-4 flex items-center justify-between border-t border-neutral-100 pt-3 text-xs text-neutral-500">
          <span>◷ {IDEA_DURATIONS[index % IDEA_DURATIONS.length]}</span>
          <span className="font-semibold text-amber-600">★ {IDEA_RATINGS[index % IDEA_RATINGS.length]}</span>
        </div>
      </div>

      {menuOpen && <IdeaActionMenu onAction={onAction} />}
    </article>
  )
}
