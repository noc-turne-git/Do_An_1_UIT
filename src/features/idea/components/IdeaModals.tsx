import { useState } from 'react'
import { getImageUrl } from './ideaData'
import type { Idea } from './ideaTypes'
import { MapPin, Upload, X, ChevronDown, ChevronRight, CalendarDays } from 'lucide-react'

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
  onNameChange: (value: string) => void
  onTypeChange: (value: string) => void
  onSave: () => void
  onClose: () => void
}

export function IdeaForm({ mode, name, type, onNameChange, onTypeChange, onSave, onClose }: IdeaFormProps) {
  const [moreDetails, setMoreDetails] = useState(false)
  const [startTime, setStartTime] = useState('10:00')
  const [isEditingStartTime, setIsEditingStartTime] = useState(false)
  const isEdit = mode === 'edit'

  return (
    <section role="dialog" aria-modal="true" className={`w-full ${isEdit ? 'max-w-2xl' : 'flex max-h-[calc(100vh-48px)] min-h-[620px] max-w-[880px] flex-col'} overflow-hidden rounded-[22px] bg-white shadow-2xl`}>
      <div className={`relative shrink-0 border-b border-neutral-200 text-center ${isEdit ? 'px-8 py-7' : 'flex h-[84px] items-center justify-center'}`}>
        <button aria-label="Close" onClick={onClose} className={`absolute ${isEdit ? 'left-7 top-7' : 'left-8 top-5 text-[27px] leading-none'}`}><X size={20} /></button>
        <h3 className="text-2xl font-semibold">{isEdit ? 'Edit details' : 'Add an idea'}</h3>
      </div>

      <div className={`${isEdit ? 'space-y-5 px-8 py-7' : 'min-h-0 flex-1 overflow-y-auto px-[30px] py-7'}`}>
        {!isEdit && <p className="mb-7 text-sm text-neutral-500">Add a place or activity you want to remember for your trip.</p>}
        <label className="block font-medium">
          {isEdit ? 'Title' : 'Place or activity name'}
          <input
            autoFocus
            value={name}
            onChange={(event) => onNameChange(event.target.value)}
            placeholder={isEdit ? undefined : 'Place or activity name'}
            className={`mt-2 w-full border border-neutral-300 px-4 font-normal ${isEdit ? 'rounded-full py-2.5' : 'h-[54px] rounded-xl'}`}
          />
        </label>

        {isEdit ? (
          <>
            <div>
              <p className="font-medium">Where</p>
              <p className="mt-2 flex items-center gap-3 text-sm"><MapPin size={18} className="text-neutral-500" />{name}</p>
              <input aria-label="Address" placeholder="Add an address" className="mt-3 w-full rounded-full border border-neutral-300 px-4 py-2.5" />
            </div>

            <div>
              <p className="font-medium">Media</p>
              <p className="mt-1 text-sm text-neutral-500">Photos, confirmation screenshots, QR codes, or PDFs</p>
              <button type="button" aria-label="Upload media" className="mt-3 grid h-20 w-20 place-items-center rounded-2xl border-2 border-dashed border-neutral-300 text-neutral-500">
                <Upload size={22} />
              </button>
            </div>

           <button 
              type="button" 
              onClick={() => setMoreDetails((open) => !open)} 
              className="flex items-center gap-2 rounded-full bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-700 transition-colors hover:bg-neutral-200"
            >
              {moreDetails ? <ChevronDown size={16} /> : <ChevronRight size={16} />} 
              More details
            </button>
            {moreDetails && (
            <div className="space-y-4 pt-2">
              {/* Type */}
              <label className="block text-sm font-medium text-neutral-700">
                Type
                <input 
                  value={type} 
                  onChange={(event) => onTypeChange(event.target.value)} 
                  placeholder="e.g. Attraction"
                  className="mt-1.5 w-full rounded-xl border border-neutral-300 p-3 text-base font-normal focus:border-black focus:outline-none" 
                />
              </label>

              {/* Website */}
              <label className="block text-sm font-medium text-neutral-700">
                Website
                <input 
                  placeholder="https://example.com" 
                  className="mt-1.5 w-full rounded-xl border border-neutral-300 p-3 text-base font-normal focus:border-black focus:outline-none" 
                />
              </label>

              {/* Price (Có thể chia 2 cột nhỏ cho Giá và Loại tiền tệ) */}
              <div className="grid grid-cols-3 gap-3">
                <label className="col-span-2 block text-sm font-medium text-neutral-700">
                  Price
                  <input 
                    type="number"
                    placeholder="0" 
                    className="mt-1.5 w-full rounded-xl border border-neutral-300 p-3 text-base font-normal focus:border-black focus:outline-none" 
                  />
                </label>
                <label className="block text-sm font-medium text-neutral-700">
                  Currency
                  <select className="mt-1.5 w-full rounded-xl border border-neutral-300 bg-white p-3 text-base font-normal focus:border-black focus:outline-none">
                    <option value="USD">USD ($ - Đô la Mỹ)</option>
                    <option value="VND">VND (₫ - Việt Nam Đồng)</option>
                    <option value="EUR">EUR (€ - Euro)</option>
                    <option value="JPY">JPY (¥ - Yên Nhật)</option>
                    <option value="KRW">KRW (₩ - Won Hàn Quốc)</option>
                    <option value="THB">THB (฿ - Baht Thái)</option>
                    <option value="SGD">SGD (S$ - Đô la Singapore)</option>
                    <option value="AUD">AUD (A$ - Đô la Úc)</option>
                    <option value="GBP">GBP (£ - Bảng Anh)</option>
                    <option value="CNY">CNY (¥ - Nhân dân tệ)</option>
                    <option value="TWD">TWD (NT$ - Đô la Đài Loan)</option>
                    <option value="MYR">MYR (RM - Ringgit Malaysia)</option>
                  </select>
                </label>
              </div>

              {/* Notes */}
              <label className="block text-sm font-medium text-neutral-700">
                Notes
                <textarea 
                  placeholder="Add any notes..." 
                  className="mt-1.5 w-full rounded-xl border border-neutral-300 p-3 text-base font-normal focus:border-black focus:outline-none" 
                  rows={3} 
                />
              </label>
            </div>
          )}
          </>
        ) : (
          <label className="block text-sm">
            Type
            <input value={type} onChange={(event) => onTypeChange(event.target.value)} placeholder="e.g. Attraction" className="mt-2 h-[54px] w-full rounded-xl border border-neutral-300 px-4" />
          </label>
        )}
      </div>

      {isEdit ? <div className="flex justify-end border-t border-neutral-100 px-8 py-5">
        <button onClick={onSave} disabled={!name.trim()} className="rounded-full bg-black px-7 py-3 font-semibold text-white disabled:opacity-40">
          {isEdit ? 'Update' : 'Add idea'}
        </button>
      </div> : <footer className="flex shrink-0 items-center justify-between gap-4 border-t border-neutral-200 bg-white px-[30px] py-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-neutral-100"><CalendarDays size={19} className="text-neutral-700" /></div>
          <div><p className="text-xs font-medium text-neutral-500">Start time</p><p className="mt-0.5 text-[15px] font-semibold text-neutral-900">{startTime}</p></div>
          {isEditingStartTime && <input autoFocus type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} onBlur={() => setIsEditingStartTime(false)} className="rounded-lg border border-neutral-300 px-3 py-2" />}
        </div>
        <div className="flex shrink-0 gap-2">
          <button onClick={onClose} className="rounded-full border border-neutral-200 px-5 py-2.5 text-sm font-medium hover:bg-neutral-50">Cancel</button>
          <button onClick={() => setIsEditingStartTime(true)} className="rounded-full border border-neutral-200 px-5 py-2.5 text-sm font-medium hover:bg-neutral-50">Change time</button>
          <button onClick={onSave} disabled={!name.trim()} className="rounded-full bg-black px-7 py-2.5 font-semibold text-white disabled:opacity-40">Add idea</button>
        </div>
      </footer>}
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
