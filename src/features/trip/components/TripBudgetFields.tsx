import { useEffect, useState } from 'react'
import { actionClass, budgetOptions, closeClass, type Budget } from './tripFieldModalTypes'

type Props = { budget: string; onClose: () => void; onSave: (budget: string) => void }

export function TripBudgetFields({ budget, onClose, onSave }: Props) {
  const [draft, setDraft] = useState<Budget>('any')
  useEffect(() => setDraft(budgetOptions.find((item) => item.label === budget || item.symbols === budget)?.id ?? 'any'), [budget])

  return <div className="space-y-5">
    <div className="flex items-center justify-between"><button onClick={onClose} className={closeClass} aria-label="Close">×</button><div className="text-center"><h2 className="text-xl font-semibold">Budget</h2><p className="text-sm text-neutral-500">Select your budget range</p></div><span className="w-9" /></div>
    <div role="radiogroup" aria-label="Budget range" className="space-y-1">{budgetOptions.map((option) => <button type="button" key={option.id} role="radio" aria-checked={draft === option.id} onClick={() => setDraft(option.id)} className="flex w-full items-center gap-4 rounded-xl p-4 text-left hover:bg-neutral-50"><span className={`grid h-5 w-5 place-items-center rounded-full border ${draft === option.id ? 'border-neutral-950' : 'border-neutral-300'}`}>{draft === option.id && <span className="h-2.5 w-2.5 rounded-full bg-neutral-950" />}</span><span className="flex flex-1 items-center justify-between"><strong className="text-sm">{option.label}</strong>{option.symbols && <span className="text-sm text-neutral-500">{option.symbols}</span>}</span></button>)}</div>
    <div className="flex justify-end"><button onClick={() => onSave(budgetOptions.find((item) => item.id === draft)?.label ?? 'Any budget')} className={actionClass}>Update</button></div>
  </div>
}
