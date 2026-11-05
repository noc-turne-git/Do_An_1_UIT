import { useEffect, useRef, useState } from 'react'
import { UserRound, X } from 'lucide-react'
import { useAuthStore } from '../store/useAuthStore'

function readProfile(): Record<string, unknown> {
  const { user, preferences } = useAuthStore.getState()
  return { ...preferences, firstName: user?.firstName ?? '', lastName: user?.lastName ?? '' }
}

export function AccountSettingsModal({ onClose, onSaved }: { onClose: () => void; onSaved?: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const photoRef = useRef<HTMLInputElement>(null)
  const email = useAuthStore((state) => state.user?.email ?? '')
  const googlePhoto = useAuthStore((state) => state.user?.avatarUrl ?? '')
  const [fields, setFields] = useState(() => {
    const profile = readProfile()
    const text = (key: string) => typeof profile[key] === 'string' ? profile[key] as string : ''
    return { firstName: text('firstName'), lastName: text('lastName'), website: text('website'), city: text('city'), profilePhoto: text('profilePhoto') }
  })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const inputClass = 'h-10 w-full rounded-full border border-[#393939] bg-transparent px-4 text-sm text-neutral-200 outline-none placeholder:text-neutral-500 focus:border-neutral-200 focus:ring-2 focus:ring-white/10'

  useEffect(() => {
    const dialog = dialogRef.current
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog?.showModal()
    return () => { dialog?.close(); document.body.style.overflow = previousOverflow }
  }, [])

  function update(key: keyof typeof fields, value: string) {
    setFields((previous) => ({ ...previous, [key]: value }))
    setError('')
  }

  return <dialog ref={dialogRef} aria-labelledby="account-settings-title" onCancel={onClose} className="fixed inset-0 m-auto max-h-[calc(100dvh-24px)] w-[calc(100vw-24px)] max-w-[440px] overflow-y-auto rounded-[22px] border border-[#282828] bg-[#111] p-6 text-neutral-200 shadow-2xl backdrop:bg-black/70 backdrop:backdrop-blur-sm sm:p-7">
    <button type="button" aria-label="Close account settings" onClick={onClose} className="absolute right-4 top-4 grid h-8 w-8 cursor-pointer place-items-center rounded-full hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white"><X size={20} /></button>
    <h1 id="account-settings-title" className="mb-4 text-base font-semibold">Profile</h1>
    <form aria-busy={saving} onSubmit={async (event) => {
      event.preventDefault()
      if (saving) return
      setError('')
      setSaving(true)
      try {
        await useAuthStore.getState().savePreferences({ ...fields, firstName: fields.firstName.trim(), lastName: fields.lastName.trim(), website: fields.website.trim(), city: fields.city.trim() })
        onSaved?.()
        onClose()
      } catch (error) { setError(error instanceof Error ? error.message : 'Your profile could not be saved. Please try again.') }
      finally { setSaving(false) }
    }}>
      <div className="mb-4 flex items-center gap-3">
        <span className="grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-full bg-[#500d30] text-pink-200">{fields.profilePhoto || googlePhoto ? <img src={fields.profilePhoto || googlePhoto} alt="Your profile" className="h-full w-full object-cover" /> : <UserRound size={22} />}</span>
        <div className="min-w-0"><strong className="block truncate text-sm">{fields.firstName || email || 'Traveler'}</strong><button type="button" onClick={() => photoRef.current?.click()} className="cursor-pointer text-xs text-neutral-400 hover:text-white focus-visible:outline-2 focus-visible:outline-white">Change profile photo</button></div>
        <input ref={photoRef} type="file" accept="image/png,image/jpeg,image/webp" aria-label="Choose profile photo" className="hidden" onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = ''
          if (!file) return
          if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 2 * 1024 * 1024) { setError('Choose a PNG, JPEG, or WebP photo smaller than 2 MB.'); return }
          const reader = new FileReader()
          reader.onload = () => { if (typeof reader.result === 'string') update('profilePhoto', reader.result) }
          reader.onerror = () => setError('The photo could not be read. Please try again.')
          reader.readAsDataURL(file)
        }} />
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-3 [&>label]:min-w-0 [&>label:nth-child(n+3)]:col-span-2">
        <label className="grid gap-2 text-xs font-semibold">First name<input autoFocus autoComplete="given-name" maxLength={100} value={fields.firstName} onChange={(event) => update('firstName', event.target.value)} className={inputClass} /></label>
        <label className="grid gap-2 text-xs font-semibold">Last name<input autoComplete="family-name" maxLength={100} value={fields.lastName} onChange={(event) => update('lastName', event.target.value)} className={inputClass} /></label>
        <label className="grid gap-2 text-xs font-semibold">Email<input type="email" autoComplete="email" value={email} readOnly aria-readonly="true" className={`${inputClass} border-neutral-800 bg-white/5 text-neutral-400`} /></label>
        <label className="grid gap-2 text-xs font-semibold">Website<input type="url" autoComplete="url" placeholder="https://example.com" maxLength={500} value={fields.website} onChange={(event) => update('website', event.target.value)} className={inputClass} /></label>
        <label htmlFor="account-location" className="grid gap-2 text-xs font-semibold">Location<span className="relative"><input id="account-location" autoComplete="address-level2" maxLength={200} value={fields.city} onChange={(event) => update('city', event.target.value)} className={`${inputClass} pr-11`} />{fields.city && <button type="button" aria-label="Clear location" onClick={() => update('city', '')} className="absolute right-3 top-1/2 grid h-6 w-6 -translate-y-1/2 cursor-pointer place-items-center rounded-full bg-neutral-800 text-neutral-400 hover:text-white"><X size={13} /></button>}</span></label>
      </div>
      {error && <p role="alert" className="mt-4 text-sm text-red-300">{error}</p>}
      <footer className="mt-4 flex justify-end"><button type="submit" disabled={saving} className="h-10 min-w-28 cursor-pointer rounded-full bg-white px-6 text-sm font-medium text-black hover:bg-neutral-200 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white">{saving ? 'Updating...' : 'Update'}</button></footer>
    </form>
  </dialog>
}
