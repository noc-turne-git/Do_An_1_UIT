import { Modal } from '../../../components/Modal'
import { TripBudgetFields } from './TripBudgetFields'
import { TripTravelerFields } from './TripTravelerFields'
import { TripWhenFields } from './TripWhenFields'
import { TripWhereFields } from './TripWhereFields'
import type { TripField, TripFieldChanges } from './tripFieldModalTypes'

type Props = {
  field: TripField | null
  destination: string
  when: string
  budget: string
  travelerCount: number
  onClose: () => void
  onSave: (values: TripFieldChanges) => void
}

export function TripFieldModals({
  field,
  destination,
  when,
  budget,
  travelerCount,
  onClose,
  onSave,
}: Props) {
  if (!field) return null

  return (
    <Modal open onClose={onClose} className={field === 'When' ? 'sm:max-w-4xl sm:p-7' : field === 'Where' ? 'sm:max-w-2xl sm:p-7' : ''}>
      {field === 'Where' && <TripWhereFields destination={destination} onClose={onClose} onSave={(value) => onSave({ destination: value })} />}
      {field === 'When' && <TripWhenFields when={when} onClose={onClose} onSave={(value) => onSave({ when: value })} />}
      {field === 'Who' && <TripTravelerFields travelerCount={travelerCount} onClose={onClose} onSave={(value) => onSave({ travelers: value })} />}
      {field === 'Budget' && <TripBudgetFields budget={budget} onClose={onClose} onSave={(value) => onSave({ budget: value })} />}
    </Modal>
  )
}
