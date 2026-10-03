import { useEffect, useRef, useState } from 'react'
import { Pencil, Plus, Trash2, X } from 'lucide-react'

type Profile = Record<string, unknown>
function readProfile(): Profile {
  try {
    const value: unknown = JSON.parse(localStorage.getItem('travel-profile-draft') ?? '{}')
    return value && typeof value === 'object' && !Array.isArray(value) ? value as Profile : {}
  } catch { return {} }
}
function text(value: unknown) { return typeof value === 'string' ? value.trim() : '' }
function object(value: unknown): Profile { return value && typeof value === 'object' && !Array.isArray(value) ? value as Profile : {} }
function list(value: unknown) { return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [] }

export function PersonalizationModal({ onClose }: { onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [profile, setProfile] = useState(readProfile)
  const [notice, setNotice] = useState('')
  const [editing, setEditing] = useState<{ group: string; index: number } | null>(null)
  const [draft, setDraft] = useState('')
  const travel = object(profile.travelStyle)
  const accommodation = object(profile.accommodation)
  const food = object(profile.foodPreferences)
  const wrapping = object(profile.wrappingUp)
  const memory = profile.longTermMemory !== false
  const personality = ['neutral', 'casual', 'professional'].includes(text(profile.personality)) ? text(profile.personality) : 'neutral'
  const groups = [
    { title: 'Identity', icon: '🏡', rows: [text(profile.city) && `Home base: ${text(profile.city)}`, text(profile.firstName) && `Name: ${text(profile.firstName)}`] },
    { title: 'Travel party', icon: '👥', rows: list(travel.companions).map((item) => `Travel party: ${item === 'Solo' ? 'Usually travels solo.' : item === 'Couple' ? 'Usually travels with partner.' : item === 'Family' ? 'Usually travels as a family.' : `Usually travels with ${item.toLowerCase()}.`}`) },
    { title: 'Accommodation', icon: '🧳', rows: [list(accommodation.styles).length && `Type: ${list(accommodation.styles).join('; ')}`, text(accommodation.styleOther), list(accommodation.loyaltyPrograms).length && `Loyalty programs: ${list(accommodation.loyaltyPrograms).join('; ')}`, text(accommodation.loyaltyOther)] },
    { title: 'Budget', icon: '💜', rows: [text(travel.budget) && `Budget philosophy: ${text(travel.budget)}${list(travel.splurges).length ? ` · Sometimes splurges on: ${list(travel.splurges).join(', ')}` : ''}`, text(travel.other)] },
    { title: 'Food', icon: '🍴', rows: [list(food.restaurants).length && `Dining style: ${list(food.restaurants).join('; ')}`, text(food.restaurantOther), list(food.dietaryRestrictions).length && `Dietary restrictions: ${list(food.dietaryRestrictions).join('; ')}`, text(food.dietaryOther)] },
    { title: 'Interests', icon: '✨', rows: [list(wrapping.activities).length && `Weekend activities: ${list(wrapping.activities).join('; ')}`, text(wrapping.other), text(wrapping.notes), text(profile.assistantNotes)] },
  ]

  useEffect(() => {
    const dialog = dialogRef.current
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog?.showModal()
    return () => { dialog?.close(); document.body.style.overflow = previousOverflow }
  }, [])

  function save(changes: Profile) {
    try {
      const next = { ...readProfile(), ...changes }
      localStorage.setItem('travel-profile-draft', JSON.stringify(next))
      setProfile(next)
      setNotice('Changes saved.')
      return true
    } catch { setNotice('Your settings could not be saved. Please try again.'); return false }
  }

  function saveEntries(group: string, entries: string[]) {
    const savedMemories = object(readProfile().personalizationMemories)
    if (save({ personalizationMemories: { ...savedMemories, [group]: entries } })) {
      setEditing(null)
      setDraft('')
    }
  }

  function startEditing(group: string, index: number, value = '') {
    setEditing({ group, index })
    setDraft(value)
    setNotice('')
  }

  return <dialog ref={dialogRef} aria-labelledby="personalization-title" onCancel={onClose} className="fixed inset-0 m-auto max-h-[calc(100dvh-24px)] w-[calc(100vw-24px)] max-w-[590px] overflow-y-auto rounded-[22px] border border-[#282828] bg-[#111] p-6 text-neutral-200 shadow-2xl backdrop:bg-black/70 backdrop:backdrop-blur-sm sm:p-8">
    <button type="button" aria-label="Close personalization" onClick={onClose} className="absolute right-4 top-4 grid h-8 w-8 cursor-pointer place-items-center rounded-full hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white"><X size={20} /></button>
    <h1 id="personalization-title" className="mb-7 text-base font-semibold">Personalization</h1>
    <section className="border-b border-neutral-800 py-6"><label htmlFor="communication-style" className="text-sm font-semibold">Communication style</label><p className="mb-3 mt-1 text-xs text-neutral-400">Choose how you would like Travelio to communicate with you</p><select id="communication-style" value={personality} onChange={(event) => save({ personality: event.target.value })} className="h-9 w-52 max-w-full rounded-full border border-neutral-700 bg-[#111] px-3 text-xs outline-none focus:border-white cursor-pointer"><option value="neutral">Neutral</option><option value="casual">Casual</option><option value="professional">Professional</option></select></section>
    <section className="pt-6"><div className="flex items-start justify-between gap-5"><div><h2 id="memory-label" className="text-sm font-semibold">Long-term memory</h2><p id="memory-description" className="mt-1 max-w-[390px] text-xs leading-relaxed text-neutral-400">Let Travelio remember your preferences and past trips to personalize future conversations. When off, Travelio won’t use or save anything it learns about you.</p></div><button type="button" role="switch" aria-checked={memory} aria-labelledby="memory-label" aria-describedby="memory-description" onClick={() => save({ longTermMemory: !memory })} className={`mt-1 flex h-5 w-10 shrink-0 cursor-pointer items-center rounded-full p-0.5 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white ${memory ? 'justify-end bg-white' : 'justify-start bg-neutral-600'}`}><span className="h-4 w-4 rounded-full bg-[#111]" /></button></div>
      <div className="mt-6 space-y-5">{groups.map(({ title, icon, rows }) => {
        const savedRows = object(profile.personalizationMemories)[title]
        const entries = Array.isArray(savedRows) ? list(savedRows) : rows.filter((row): row is string => typeof row === 'string' && Boolean(row))
        const editor = (index: number) => <form className="mt-3 border-t border-neutral-700 pt-3" onSubmit={(event) => {
          event.preventDefault()
          if (!draft.trim()) return
          const next = [...entries]
          if (index === -1) next.push(draft.trim())
          else next[index] = draft.trim()
          saveEntries(title, next)
        }}>
          <label htmlFor="memory-edit" className="mb-2 block text-xs">{index === -1 ? 'Tell Travelio what you would like it to remember:' : 'Tell Travelio how to update this memory:'}</label>
          <textarea id="memory-edit" autoFocus value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={'e.g. “Actually I live in Dallas now”'} maxLength={2000} className="block min-h-28 w-full resize-y rounded-[20px] border border-neutral-300 bg-[#111] px-4 py-3 text-sm text-neutral-200 outline-none placeholder:text-neutral-500 focus:ring-2 focus:ring-white/20" />
          <div className="mt-3 flex items-center gap-4">
            <button type="submit" disabled={!draft.trim()} className="h-9 rounded-full bg-white px-6 text-sm text-black enabled:cursor-pointer enabled:hover:bg-neutral-200 disabled:cursor-not-allowed disabled:bg-[#595959] focus-visible:outline-2 focus-visible:outline-white">Save</button>
            <button type="button" onClick={() => { setEditing(null); setDraft('') }} className="cursor-pointer rounded px-2 py-2 text-sm font-semibold hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white">Cancel</button>
            {index !== -1 && <button type="button" aria-label={`Delete memory: ${entries[index]}`} onClick={() => saveEntries(title, entries.filter((_, rowIndex) => rowIndex !== index))} className="ml-auto grid h-9 w-9 cursor-pointer place-items-center rounded-full hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white"><Trash2 size={16} /></button>}
          </div>
        </form>
        return <section key={title}>
          <div className="mb-2 flex items-center justify-between"><h3 className="text-xs font-semibold">{title}</h3><button type="button" aria-label={`Add ${title.toLowerCase()} memory`} onClick={() => startEditing(title, -1)} className="flex cursor-pointer items-center gap-1 rounded px-2 py-1 text-xs text-neutral-400 hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-white"><Plus size={13} />Add</button></div>
          {entries.length ? <div className="space-y-1.5">{entries.map((row, index) => <div key={index} className="group rounded-xl border border-neutral-800 bg-[#1a1a1a] px-3 py-2 text-xs leading-relaxed hover:border-neutral-500">
            <div className="flex items-center gap-2"><span aria-hidden="true">{icon}</span><p className="min-w-0 break-words">{row}</p><button type="button" aria-label={`Edit memory: ${row}`} aria-expanded={editing?.group === title && editing.index === index} onClick={() => startEditing(title, index, row)} className="ml-auto grid h-7 w-7 shrink-0 cursor-pointer place-items-center rounded opacity-100 hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"><Pencil size={14} /></button></div>
            {editing?.group === title && editing.index === index && editor(index)}
          </div>)}</div> : <p className="text-xs text-neutral-500">No preferences saved yet.</p>}
          {editing?.group === title && editing.index === -1 && <div className="mt-2 rounded-xl border border-neutral-800 bg-[#1a1a1a] px-3 pb-3">{editor(-1)}</div>}
        </section>
      })}</div>
    </section>
    {notice && <p role="status" className="mt-5 text-xs text-neutral-400">{notice}</p>}
  </dialog>
}
