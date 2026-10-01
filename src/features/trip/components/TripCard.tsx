import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ImagePlus,
  MoreHorizontal,
  Share2,
  Trash2,
  Upload,
} from 'lucide-react'

import type { Trip } from '../types'

export function TripCard({ trip }: { trip: Trip }) {
  const [menu, setMenu] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleShare = async () => {
    setMenu(false)

    const url = `${window.location.origin}/trips/${trip.id}`

    if (navigator.share) {
      try {
        await navigator.share({
          title: trip.name,
          text: `Check out my trip to ${trip.destination}`,
          url,
        })
      } catch {
        // User cancelled the share dialog.
      }
    } else {
      try {
        await navigator.clipboard.writeText(url)
        alert('Trip link copied!')
      } catch {
        alert('Could not copy the trip link.')
      }
    }
  }

  const handleChangePhoto = () => {
    setMenu(false)
    fileInputRef.current?.click()
  }

  const handlePhotoSelected = (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0]

    if (!file) return

    // Temporary preview.
    // Replace this with your upload/update API later.
    const previewUrl = URL.createObjectURL(file)

    console.log('Selected trip photo:', file)
    console.log('Preview URL:', previewUrl)

    // Reset input so selecting the same file again still triggers onChange.
    event.target.value = ''
  }

  const handleDelete = () => {
    setMenu(false)

    const confirmed = window.confirm(
      `Delete "${trip.name}"?\n\nThis action cannot be undone.`,
    )

    if (!confirmed) return

    // Connect your delete-trip mutation here.
    console.log('Delete trip:', trip.id)
  }

  return (
    <article className="group relative aspect-[1.2] overflow-hidden rounded-2xl bg-neutral-200">
      {/* Cover */}
      <Link
        to={`/trips/${trip.id}`}
        className="absolute inset-0"
        aria-label={`Open ${trip.name}`}
      >
        <img
          src={trip.cover}
          alt=""
          className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.025]"
        />

        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-black/15" />
      </Link>

      {/* Options */}
      <button
        type="button"
        onClick={() => setMenu((value) => !value)}
        aria-label="Trip options"
        aria-expanded={menu}
        className={`
          absolute right-3 top-3 z-20
          grid h-9 w-9 place-items-center
          rounded-full
          bg-white/95
          text-neutral-800
          shadow-sm
          backdrop-blur
          transition-all duration-200
          hover:bg-white
          hover:shadow-md
          active:scale-95
          ${menu
            ? 'opacity-100'
            : 'opacity-0 group-hover:opacity-100 focus:opacity-100'}
        `}
      >
        <MoreHorizontal className="h-5 w-5" />
      </button>

      {/* Menu */}
      {menu && (
        <>
          {/* Invisible backdrop */}
          <button
            type="button"
            aria-label="Close menu"
            className="fixed inset-0 z-10 cursor-default"
            onClick={() => setMenu(false)}
          />

          <div
            className="
              absolute right-3 top-14 z-30
              w-48
              overflow-hidden
              rounded-2xl
              border border-neutral-200
              bg-white
              p-1.5
              shadow-[0_16px_40px_rgba(0,0,0,0.16)]
            "
          >
           {/* Share */}
            <button
              type="button"
              onClick={handleShare}
              className="
                flex w-full items-center gap-3
                rounded-xl
                px-3 py-2.5
                text-left text-sm
                font-medium text-neutral-700
                transition-colors
                hover:bg-neutral-100
                hover:text-neutral-950
              "
            >
              <Share2 className="h-4 w-4 shrink-0" />
              <span>Share trip</span>
            </button>

            {/* Change photo */}
            <button
              type="button"
              onClick={handleChangePhoto}
              className="
                flex w-full items-center gap-3
                rounded-xl
                px-3 py-2.5
                text-left text-sm
                font-medium text-neutral-700
                transition-colors
                hover:bg-neutral-100
                hover:text-neutral-950
              "
            >
              <ImagePlus className="h-4 w-4 shrink-0" />
              <span>Change photo</span>
            </button>

            <div className="my-1.5 h-px bg-neutral-100" />

            {/* Delete */}
            <button
              type="button"
              onClick={handleDelete}
              className="
                flex w-full items-center gap-3
                rounded-xl
                px-3 py-2.5
                text-left text-sm
                font-medium text-red-600
                transition-colors
                hover:bg-red-50
              "
            >
              <Trash2 className="h-4 w-4 shrink-0" />
              <span>Delete trip</span>
            </button>
          </div>
        </>
      )}

      {/* Hidden file picker */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handlePhotoSelected}
      />

      {/* Trip information */}
      <Link
        to={`/trips/${trip.id}`}
        className="
          absolute inset-x-0 bottom-0
          flex items-end justify-between
          gap-3
          p-4
          text-white
        "
      >
        <span className="min-w-0">
          <strong className="block truncate text-lg font-bold">
            {trip.name}
          </strong>

          <span className="block truncate text-sm text-white/90">
            {trip.destination}
          </span>

          <span className="mt-1 block text-xs text-white/75">
            {trip.duration}
          </span>
        </span>

        {/* Travelers */}
        <span className="flex shrink-0 -space-x-2">
          {trip.travelers.slice(0, 3).map((person) => (
            <i
              key={person}
              className="
                grid h-8 w-8 place-items-center
                rounded-full
                border-2 border-white
                bg-neutral-700
                text-[10px]
                not-italic
              "
            >
              {person}
            </i>
          ))}

          {trip.travelers.length > 3 && (
            <i
              className="
                grid h-8 w-8 place-items-center
                rounded-full
                border-2 border-white
                bg-neutral-900
                text-xs
                not-italic
              "
            >
              +{trip.travelers.length - 3}
            </i>
          )}
        </span>
      </Link>
    </article>
  )
}
