import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'

function readProfile(): Record<string, unknown> {
  try {
    const profile: unknown = JSON.parse(localStorage.getItem('travel-profile-draft') ?? '{}')
    return profile && typeof profile === 'object' && !Array.isArray(profile) ? profile as Record<string, unknown> : {}
  } catch {
    return {}
  }
}

export function AssistantSetupModal({ onClose }: { onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [profile] = useState(readProfile)
  const [notes, setNotes] = useState(typeof profile.assistantNotes === 'string' ? profile.assistantNotes : '')
  const [error, setError] = useState('')
  const firstName = typeof profile.firstName === 'string' ? profile.firstName.trim() : ''

  useEffect(() => {
    const dialog = dialogRef.current
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog?.showModal()
    return () => {
      dialog?.close()
      document.body.style.overflow = previousOverflow
    }
  }, [])

  return <dialog ref={dialogRef} aria-labelledby="assistant-setup-title" onCancel={onClose}
    className="fixed inset-0 m-auto max-h-[calc(100dvh-24px)] w-[calc(100vw-24px)] max-w-[696px] overflow-y-auto rounded-[24px] border border-[#242424] bg-[#111] p-6 text-[#ededed] shadow-2xl backdrop:bg-black/75 backdrop:backdrop-blur-sm sm:p-8">
    <button type="button" aria-label="Close assistant setup" onClick={onClose} className="absolute left-5 top-4 grid h-9 w-9 cursor-pointer place-items-center rounded-full hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white"><X size={22} /></button>
    <form onSubmit={(event) => {
      event.preventDefault()
      if (!notes.trim()) return
      try {
        localStorage.setItem('travel-profile-draft', JSON.stringify({ ...readProfile(), assistantNotes: notes.trim() }))
        onClose()
      } catch {
        setError('Your preferences could not be saved. Please try again.')
      }
    }}>
      <h1 id="assistant-setup-title" className="mx-auto mb-8 mt-1 max-w-[400px] px-5 text-center text-[24px] font-bold leading-[1.35] sm:text-[28px]">{firstName ? `Hey, ${firstName}.` : 'Hey there.'} What would you like me to know?</h1>
      <label htmlFor="assistant-setup-notes" className="sr-only">What would you like your assistant to know?</label>
      <textarea autoFocus id="assistant-setup-notes" placeholder="I prefer quiet hotels near public transit." value={notes} onChange={(event) => { setNotes(event.target.value); setError('') }} className="block h-36 min-h-36 w-full resize-y rounded-[22px] border border-[#ddd] bg-transparent px-4 py-3 text-base leading-relaxed text-[#ededed] outline-none placeholder:text-[#666] focus:ring-2 focus:ring-white/20 sm:text-lg" />
      {error && <p role="alert" className="mt-3 text-sm text-red-300">{error}</p>}
      <footer className="mt-10 flex justify-end sm:mt-[54px]"><button type="submit" disabled={!notes.trim()} className="h-[54px] min-w-[120px] rounded-full bg-white px-6 text-lg text-black enabled:cursor-pointer enabled:hover:bg-neutral-200 disabled:cursor-not-allowed disabled:bg-[#595959] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white">Update</button></footer>
    </form>
  </dialog>
}
