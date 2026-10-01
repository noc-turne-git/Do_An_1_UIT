import { CalendarPlus, MapPin, Pencil, Trash2 } from 'lucide-react'
import type { Idea } from './ideaTypes'

export const INITIAL_IDEAS: Idea[] = [
  { name: 'Lam Vien Square', type: 'Attraction', image: 'photo-1519608487953-e999c86e7455' },
  { name: 'Dalat Flower Plateau', type: 'Nature', image: 'photo-1490750967868-88aa4486c946' },
  { name: 'Tui Mo To Coffee & Garden', type: 'Cafe & Panoramic View', image: 'photo-1445116572660-236099ec97a0' },
  { name: 'Langbiang Peak Trek', type: 'Outdoors & Hiking', image: 'photo-1464822759023-fed622ff2c3b' },
]

export const IDEA_DURATIONS = ['1–2 hours', 'Half day', '1–2 hours', '4–5 hours']
export const IDEA_RATINGS = ['4.7', '4.9', '4.8', '4.9']

export const IDEA_ACTIONS = [
  { id: 'itinerary', label: 'Add to itinerary', icon: CalendarPlus },
  { id: 'edit', label: 'Edit details', icon: Pencil },
  { id: 'details', label: 'View details', icon: MapPin },
  { id: 'delete', label: 'Delete', icon: Trash2 },
] as const

export const getImageUrl = (image: string) =>
  `https://images.unsplash.com/${image}?auto=format&fit=crop&w=900&q=85`

export const getIdeaTag = (type: string) => type.split(' & ')[0]
