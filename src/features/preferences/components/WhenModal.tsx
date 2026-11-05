import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { CalendarDays, ChevronLeft, ChevronRight, Minus, Plus, X } from 'lucide-react'
import type { NextTripPreferences } from './NextTripStep'
import './WhenModal.css'

type Dates = Pick<NextTripPreferences, 'dateMode' | 'startDate' | 'endDate' | 'flexibleDays' | 'flexibleMonths'>
function dateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
function monthAt(base: Date, offset: number) { return new Date(base.getFullYear(), base.getMonth() + offset, 1) }

export function WhenModal({ value, onSave, onClose }: { value: Dates; onSave: (value: Dates) => void; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [today] = useState(() => new Date())
  const [mode, setMode] = useState(value.dateMode ?? 'dates')
  const [start, setStart] = useState(value.startDate)
  const [end, setEnd] = useState(value.endDate)
  const [month, setMonth] = useState(() => value.startDate ? new Date(`${value.startDate}T12:00:00`) : new Date())
  const [days, setDays] = useState(value.flexibleDays ?? 5)
  const [months, setMonths] = useState(value.flexibleMonths ?? [])
  const [monthOffset, setMonthOffset] = useState(0)
  useEffect(() => {
    const dialog = dialogRef.current
    dialog?.showModal()
    return () => dialog?.close()
  }, [])

  function selectDate(key: string) {
    if (!start || end) { setStart(key); setEnd('') }
    else if (key < start) { setStart(key); setEnd(start) }
    else setEnd(key)
  }

  return createPortal(
    <dialog ref={dialogRef} className="preferences-when-modal" aria-labelledby="when-title" onCancel={(event) => { event.preventDefault(); onClose() }} onClick={(event) => {
      if (event.target !== event.currentTarget) return
      const bounds = event.currentTarget.getBoundingClientRect()
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose()
    }}>
      <header>
        <button type="button" className="when-close" aria-label="Close When" onClick={onClose}><X size={20} /></button>
        <h2 id="when-title">When</h2>
        <div className="when-tabs" aria-label="Date selection mode">
          <button type="button" aria-pressed={mode === 'dates'} onClick={() => setMode('dates')}>Dates</button>
          <button type="button" aria-pressed={mode === 'flexible'} onClick={() => setMode('flexible')}>Flexible</button>
        </div>
      </header>
      <div className="when-body">
        {mode === 'dates' ? <>
          <div className="when-calendar-navigation">
            <button type="button" aria-label="Previous month" disabled={monthAt(month, 0) <= monthAt(today, 0)} onClick={() => setMonth(monthAt(month, -1))}><ChevronLeft size={22} /></button>
            <button type="button" aria-label="Next month" onClick={() => setMonth(monthAt(month, 1))}><ChevronRight size={22} /></button>
          </div>
          <div className="when-calendars">
            {[0, 1].map((offset) => {
              const current = monthAt(month, offset)
              const count = new Date(current.getFullYear(), current.getMonth() + 1, 0).getDate()
              return <section key={dateKey(current)} className="when-calendar" aria-label={current.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}>
                <h3>{current.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</h3>
                <div className="when-grid">
                  {['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'].map((day) => <span className="when-weekday" key={day}>{day}</span>)}
                  {Array.from({ length: current.getDay() }, (_, index) => <span key={`empty-${index}`} />)}
                  {Array.from({ length: count }, (_, index) => {
                    const date = new Date(current.getFullYear(), current.getMonth(), index + 1)
                    const key = dateKey(date)
                    const selected = key === start || key === end
                    return <button type="button" key={key} aria-label={date.toLocaleDateString('en-US', { dateStyle: 'full' })} aria-pressed={selected} disabled={key < dateKey(today)} className={`${selected ? 'when-selected' : ''} ${start && end && key > start && key < end ? 'when-in-range' : ''}`} onClick={() => selectDate(key)}>{index + 1}</button>
                  })}
                </div>
              </section>
            })}
          </div>
          <p className="when-selection" role="status">{start ? end ? `${start} – ${end}` : `${start} — Select an end date` : 'Select a start date and an end date'}</p>
        </> : <div className="when-flexible">
          <h3>How many days?</h3>
          <div className="when-duration">
            <button type="button" aria-label="Fewer days" disabled={days <= 1} onClick={() => setDays(days - 1)}><Minus size={20} /></button>
            <input aria-label="Number of days" type="number" min={1} max={365} value={days} onChange={(event) => setDays(Math.max(1, Math.min(365, Number(event.target.value) || 1)))} />
            <button type="button" aria-label="More days" disabled={days >= 365} onClick={() => setDays(days + 1)}><Plus size={20} /></button>
          </div>
          <h3>Travel anytime</h3>
          <div className="when-month-navigation"><button type="button" aria-label="Earlier months" disabled={!monthOffset} onClick={() => setMonthOffset(Math.max(0, monthOffset - 6))}><ChevronLeft size={20} /></button><button type="button" aria-label="Later months" onClick={() => setMonthOffset(monthOffset + 6)}><ChevronRight size={20} /></button></div>
          <div className="when-months">
            {Array.from({ length: 6 }, (_, index) => {
              const date = monthAt(today, monthOffset + index)
              const key = dateKey(date).slice(0, 7)
              return <button type="button" key={key} aria-pressed={months.includes(key)} onClick={() => setMonths((selected) => selected.includes(key) ? selected.filter((item) => item !== key) : [...selected, key].sort())}><CalendarDays size={24} /><strong>Tháng {date.getMonth() + 1}</strong><small>{date.getFullYear()}</small></button>
            })}
          </div>
          <p className="when-selection">{months.length ? `Selected: ${months.join(', ')}` : 'No month selected — travel anytime'}</p>
        </div>}
      </div>
      <footer><button type="button" className="when-update" disabled={mode === 'dates' && (!start || !end)} onClick={() => onSave({ dateMode: mode, startDate: mode === 'dates' ? start : '', endDate: mode === 'dates' ? end : '', flexibleDays: days, flexibleMonths: months })}>Update</button></footer>
    </dialog>, document.body,
  )
}
