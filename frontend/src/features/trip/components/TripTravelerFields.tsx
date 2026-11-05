import { useEffect, useState } from 'react'
import { actionClass, closeClass, type Party } from './tripFieldModalTypes'

type Props = {
  travelerCount: number
  onClose: () => void
  onSave: (travelers: number) => void
}

const partyFields = [
  { key: 'adults', title: 'Adults', subtitle: 'Ages 13 or above', min: 1 },
  { key: 'children', title: 'Children', subtitle: 'Ages 2–12', min: 0 },
  { key: 'infants', title: 'Infants', subtitle: 'Under 2', min: 0 },
  { key: 'pets', title: 'Pets', subtitle: 'Bringing a service animal?', min: 0 },
] as const

export function TripTravelerFields({
  travelerCount,
  onClose,
  onSave,
}: Props) {
  const [party, setParty] = useState<Party>({
    adults: Math.max(1, travelerCount),
    children: 0,
    infants: 0,
    pets: 0,
  })

  useEffect(() => {
    setParty({
      adults: Math.max(1, travelerCount),
      children: 0,
      infants: 0,
      pets: 0,
    })
  }, [travelerCount])

  const totalTravelers = party.adults + party.children

  const updateNumber = (
    key: keyof Party,
    value: string,
    min: number,
  ) => {
    if (value === '') {
      setParty((current) => ({
        ...current,
        [key]: 0,
      }))
      return
    }

    const number = Number(value)

    if (Number.isNaN(number)) return

    setParty((current) => ({
      ...current,
      [key]: Math.max(min, Math.floor(number)),
    }))
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <button
          onClick={onClose}
          className={closeClass}
          aria-label="Close"
        >
          ×
        </button>

        <div className="text-center">
          <h2 className="text-xl font-semibold">Who</h2>
          <p className="text-sm text-neutral-500">
            {totalTravelers}{' '}
            {totalTravelers === 1 ? 'traveler' : 'travelers'}
          </p>
        </div>

        <span className="w-9" />
      </div>

      <div>
        {partyFields.map(({ key, title, subtitle, min }) => (
          <div
            key={key}
            className="flex items-center justify-between border-b border-neutral-100 py-4"
          >
            <div>
              <strong className="block text-sm">{title}</strong>
              <small className="text-neutral-500">{subtitle}</small>
            </div>

            <div className="flex items-center gap-4">
              <button
                aria-label={`Remove ${title.toLowerCase()}`}
                disabled={party[key] <= min}
                onClick={() =>
                  setParty((value) => ({
                    ...value,
                    [key]: Math.max(min, value[key] - 1),
                  }))
                }
                className="h-9 w-9 rounded-full border disabled:opacity-35"
              >
                −
              </button>

              <input
                type="number"
                min={min}
                value={party[key]}
                onChange={(e) =>
                  updateNumber(key, e.target.value, min)
                }
                className="w-10 bg-transparent text-center text-sm outline-none"
                aria-label={`${title} count`}
              />

              <button
                aria-label={`Add ${title.toLowerCase()}`}
                onClick={() =>
                  setParty((value) => ({
                    ...value,
                    [key]: value[key] + 1,
                  }))
                }
                className="h-9 w-9 rounded-full border"
              >
                +
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="flex justify-end">
        <button
          onClick={() => onSave(Math.max(1, totalTravelers))}
          className={actionClass}
        >
          Update
        </button>
      </div>
    </div>
  )
}