import { useEffect, useRef, useState } from 'react'
import { UserRound, X } from 'lucide-react'
import { useAuthStore } from '../store/useAuthStore'

function readProfile(): Record<string, unknown> {
  try {
    const value: unknown = JSON.parse(localStorage.getItem('travel-profile-draft') ?? '{}')
    return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
  } catch { return {} }
}

export function AccountSettingsModal({ onClose }: { onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const photoRef = useRef<HTMLInputElement>(null)
  const [fields, setFields] = useState(() => {
    const profile = readProfile()
    const text = (key: string) => typeof profile[key] === 'string' ? profile[key] as string : ''
    return { firstName: text('firstName'), lastName: text('lastName'), username: text('username'), website: text('website'), city: text('city'), profilePhoto: text('profilePhoto') }
  })
  const [error, setError] = useState('')
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
    <h1 id="account-settings-title" className="mb-7 text-base font-semibold">Profile</h1>
    <form onSubmit={(event) => {
      event.preventDefault()
      try {
        localStorage.setItem('travel-profile-draft', JSON.stringify({ ...readProfile(), ...fields, firstName: fields.firstName.trim(), lastName: fields.lastName.trim(), username: fields.username.trim().replace(/^@/, ''), website: fields.website.trim(), city: fields.city.trim() }))
        useAuthStore.getState().updateName(fields.firstName.trim(), fields.lastName.trim())
        onClose()
      } catch { setError('Your profile could not be saved. Please try again with a smaller photo.') }
    }}>
      <div className="mb-6 flex items-center gap-3">
        <span className="grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-full bg-[#500d30] text-pink-200">{fields.profilePhoto ? <img src={fields.profilePhoto} alt="Your profile" className="h-full w-full object-cover" /> : <UserRound size={22} />}</span>
        <div className="min-w-0"><strong className="block truncate text-sm">{fields.username ? `@${fields.username.replace(/^@/, '')}` : fields.firstName || 'Traveler'}</strong><button type="button" onClick={() => photoRef.current?.click()} className="cursor-pointer text-xs text-neutral-400 hover:text-white focus-visible:outline-2 focus-visible:outline-white">Change profile photo</button></div>
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
      <div className="grid gap-4">
        <label className="grid gap-2 text-xs font-semibold">First name<input autoFocus autoComplete="given-name" maxLength={100} value={fields.firstName} onChange={(event) => update('firstName', event.target.value)} className={inputClass} /></label>
        <label className="grid gap-2 text-xs font-semibold">Last name<input autoComplete="family-name" maxLength={100} value={fields.lastName} onChange={(event) => update('lastName', event.target.value)} className={inputClass} /></label>
        <label className="grid gap-2 text-xs font-semibold">Username<span className="relative"><span aria-hidden="true" className="absolute left-4 top-1/2 -translate-y-1/2 text-sm text-neutral-500">@</span><input autoComplete="username" maxLength={80} value={fields.username} onChange={(event) => update('username', event.target.value.replace(/^@/, ''))} className={`${inputClass} pl-8`} /></span></label>
        <label className="grid gap-2 text-xs font-semibold">Website<input type="url" autoComplete="url" placeholder="https://example.com" maxLength={500} value={fields.website} onChange={(event) => update('website', event.target.value)} className={inputClass} /></label>
        <label htmlFor="account-location" className="grid gap-2 text-xs font-semibold">Location<span className="relative"><input id="account-location" autoComplete="address-level2" maxLength={200} value={fields.city} onChange={(event) => update('city', event.target.value)} className={`${inputClass} pr-11`} />{fields.city && <button type="button" aria-label="Clear location" onClick={() => update('city', '')} className="absolute right-3 top-1/2 grid h-6 w-6 -translate-y-1/2 cursor-pointer place-items-center rounded-full bg-neutral-800 text-neutral-400 hover:text-white"><X size={13} /></button>}</span></label>
      </div>
      {error && <p role="alert" className="mt-4 text-sm text-red-300">{error}</p>}
      <footer className="mt-6 flex justify-end"><button type="submit" className="h-10 min-w-28 cursor-pointer rounded-full bg-white px-6 text-sm font-medium text-black hover:bg-neutral-200 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white">Update</button></footer>
    </form>
  </dialog>
}
