import { useState } from 'react'
import { getImageUrl } from './ideaData'
import type { Idea } from './ideaTypes'
import { Upload, X } from 'lucide-react'

export function Modal({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-[70] grid place-items-center overflow-y-auto bg-black/45 p-4"
      onMouseDown={onClose}
    >
      <div onMouseDown={(event) => event.stopPropagation()}>{children}</div>
    </div>
  )
}

type IdeaFormProps = {
  mode: 'add' | 'edit'
  name: string
  type: string
  price: string
  currency: string
  image: string
  onNameChange: (value: string) => void
  onTypeChange: (value: string) => void
  onPriceChange: (value: string) => void
  onCurrencyChange: (value: string) => void
  onImageChange: (value: string) => void
  onSave: () => void
  onClose: () => void
}

export function IdeaForm({ mode, name, type, price, currency, image, onNameChange, onTypeChange, onPriceChange, onCurrencyChange, onImageChange, onSave, onClose }: IdeaFormProps) {
  const [imageError, setImageError] = useState('')
  const [uploading, setUploading] = useState(false)
  const isEdit = mode === 'edit'
  const fieldClass = 'mt-2 w-full rounded-xl border border-neutral-300 bg-white px-4 py-3 font-normal focus:border-black focus:outline-none'

  function uploadImage(file?: File) {
    if (!file) return
    if (!file.type.startsWith('image/')) { setImageError('Please select an image.'); return }
    setImageError('')
    setUploading(true)
    const reader = new FileReader()
    reader.onload = () => { onImageChange(String(reader.result)); setUploading(false) }
    reader.onerror = () => { setImageError('Could not read this image. Please try again.'); setUploading(false) }
    reader.readAsDataURL(file)
  }

  return (
    <section role="dialog" aria-modal="true" aria-labelledby="idea-form-title" className="flex max-h-[calc(100dvh-32px)] w-[min(640px,calc(100vw-32px))] flex-col overflow-hidden rounded-[22px] bg-white shadow-2xl">
      <header className="relative shrink-0 border-b border-neutral-200 px-12 py-6 text-center">
        <button type="button" aria-label="Close" onClick={onClose} className="absolute cursor-pointer right-6 top-6"><X size={20} /></button>
        <h3 id="idea-form-title" className="text-2xl font-semibold">{isEdit ? 'Edit details' : 'Add an idea'}</h3>
      </header>
      <div className="min-h-0 space-y-5 overflow-y-auto px-6 py-6 sm:px-8">
        <label className="block text-sm font-medium">Place
          <input autoFocus value={name} onChange={(event) => onNameChange(event.target.value)} placeholder="Place or activity name" className={fieldClass} />
        </label>
        <label className="block text-sm font-medium">Type
          <input value={type} onChange={(event) => onTypeChange(event.target.value)} placeholder="e.g. Attraction" className={fieldClass} />
        </label>
        <div className="grid grid-cols-[minmax(0,1fr)_110px] gap-3">
          <label className="block text-sm font-medium">Price
            <input type="number" min="0" step="any" value={price} onChange={(event) => onPriceChange(event.target.value)} placeholder="0" className={fieldClass} />
          </label>
          <label className="block text-sm font-medium">Currency
            <select value={currency} onChange={(event) => onCurrencyChange(event.target.value)} className={fieldClass}>
              {['VND', 'USD', 'EUR', 'JPY', 'KRW', 'THB', 'SGD', 'AUD', 'GBP', 'CNY', 'TWD', 'MYR'].map((code) => <option key={code}>{code}</option>)}
            </select>
          </label>
        </div>
        <div>
          <p className="text-sm font-medium">Photo</p>
          {image && <div className="relative mt-2"><img src={getImageUrl(image)} alt="Idea preview" className="h-40 w-full rounded-xl object-cover" /><button type="button" aria-label="Remove photo" onClick={() => onImageChange('')} className="absolute right-2 top-2 rounded-full bg-white p-2 shadow"><X size={16} /></button></div>}
          <label className="mt-3 flex cursor-pointer items-center justify-center gap-2 rounded-xl border-2 border-dashed border-neutral-300 px-4 py-5 text-sm text-neutral-600 hover:bg-neutral-50">
            <Upload size={20} />{uploading ? 'Loading photo...' : image ? 'Replace photo' : 'Upload photo'}
            <input type="file" accept="image/*" disabled={uploading} onChange={(event) => { uploadImage(event.target.files?.[0]); event.target.value = '' }} className="sr-only" />
          </label>
          {imageError && <p role="alert" className="mt-2 text-sm text-red-600">{imageError}</p>}
        </div>
      </div>
      <footer className="flex shrink-0 justify-end gap-3 border-t border-neutral-200 px-6 py-4">
        <button type="button" onClick={onClose} className="rounded-full border border-neutral-200 px-5 py-2.5 text-sm font-medium">Cancel</button>
        <button type="button" onClick={onSave} disabled={!name.trim() || uploading || (price !== '' && (!Number.isFinite(Number(price)) || Number(price) < 0))} className="rounded-full bg-black px-7 py-2.5 font-semibold text-white disabled:opacity-40">{isEdit ? 'Update' : 'Add idea'}</button>
      </footer>
    </section>
  )
}
export function DetailsModal({ idea, onClose, onAddToItinerary }: { idea: Idea; onClose: () => void; onAddToItinerary: () => void }) {
  return (
    <section role="dialog" aria-modal="true" className="w-full max-w-md space-y-4 rounded-2xl bg-white p-6 shadow-2xl">
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-semibold">Idea details</h3>
        <button aria-label="Close" onClick={onClose}><X size={20} /></button>
      </div>
      <img src={getImageUrl(idea.image)} alt="" className="h-48 w-full rounded-xl object-cover" />
      <h4 className="font-semibold">{idea.name}</h4>
      <p className="text-sm text-neutral-500">{idea.type}</p>
      {idea.price !== undefined && <p className="text-sm font-medium">{idea.price.toLocaleString()} {idea.currency ?? 'VND'}</p>}
      <button onClick={onAddToItinerary} className="w-full rounded-full bg-neutral-950 py-3 text-sm font-semibold text-white">Add to itinerary</button>
    </section>
  )
}

type ItineraryModalProps = {
  idea: Idea
  day: string
  allDay: boolean
  onDayChange: (day: string) => void
  onAllDayChange: (value: boolean) => void
  onConfirm: () => void
  onClose: () => void
}

export function ItineraryModal({ idea, day, allDay, onDayChange, onAllDayChange, onConfirm, onClose }: ItineraryModalProps) {
  return (
    <section role="dialog" aria-modal="true" aria-labelledby="itinerary-title" className="w-[32rem] max-w-[calc(100vw-2rem)] shrink-0 rounded-[22px] bg-white shadow-2xl">
      <div className="relative border-b border-neutral-100 px-8 py-7 text-center">
        <button aria-label="Close" onClick={onClose} className="absolute left-6 top-6"><X size={20} /></button>
        <h3 id="itinerary-title" className="text-2xl font-semibold">Add to itinerary</h3>
        <p className="mt-1 text-sm">{idea.name}</p>
      </div>

      <div className="space-y-6 px-8 py-7">
        <label className="block text-center font-semibold">
          Which day?
          <select value={day} onChange={(event) => onDayChange(event.target.value)} className="mt-3 w-full rounded-full border border-neutral-300 bg-white px-4 py-3 text-left font-normal">
            <option>Day 1</option><option>Day 2</option><option>Day 3</option><option>Day 4</option>
          </select>
        </label>

        <div className="border-t border-neutral-200 pt-6">
          <div className="mb-6 flex justify-center gap-8">
            <label className="flex items-center gap-2 font-medium"><input type="radio" checked={!allDay} onChange={() => onAllDayChange(false)} />Time</label>
            <label className="flex items-center gap-2 font-medium"><input type="radio" checked={allDay} onChange={() => onAllDayChange(true)} />All day</label>
          </div>
          {!allDay && (
            <div className="flex min-h-12 flex-wrap items-center justify-center gap-3">
              <label className="flex items-center gap-2">Start<input type="time" defaultValue="10:00" className="rounded-full border px-3 py-2" /></label>
              <label className="flex items-center gap-2">End<input type="time" defaultValue="15:00" className="rounded-full border px-3 py-2" /></label>
            </div>
          )}
          {allDay && <div className="min-h-12" aria-hidden="true" />}
        </div>

        <button onClick={onConfirm} className="w-full rounded-full bg-black py-3.5 font-semibold text-white">Update</button>
      </div>
    </section>
  )
}
