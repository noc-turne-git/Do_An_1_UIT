export type Stop = {
  id: string
  day: number
  name: string
  start: string
  end: string
  distance: string
  image: string
}

export const initialStops: Stop[] = [
  {
    id: 'lake',
    day: 1,
    name: 'Xuan Huong Lake',
    start: '09:00',
    end: '10:30',
    distance: '8.95 km',
    image: 'photo-1470770841072-f978cf4d019e',
  },
  {
    id: 'park',
    day: 1,
    name: 'Yersin Park',
    start: '11:00',
    end: '12:00',
    distance: '2.4 km',
    image: 'photo-1500530855697-b586d89ba3ee',
  },
  {
    id: 'mountain',
    day: 2,
    name: 'Langbiang Mountain',
    start: '09:30',
    end: '12:30',
    distance: '12.1 km',
    image: 'photo-1464822759023-fed622ff2c3b',
  },
  {
    id: 'garden',
    day: 2,
    name: 'Dalat Flower Garden',
    start: '14:00',
    end: '16:00',
    distance: '5.6 km',
    image: 'photo-1490750967868-88aa4486c946',
  },
  {
    id: 'waterfall',
    day: 3,
    name: 'Datanla Waterfall',
    start: '10:00',
    end: '13:00',
    distance: '7.3 km',
    image: 'photo-1470770841072-f978cf4d019e',
  },
  {
    id: 'market',
    day: 3,
    name: 'Night Market',
    start: '18:00',
    end: '20:00',
    distance: '3.2 km',
    image: 'photo-1517248135467-4c7edcad34c4',
  },
  {
    id: 'coffee',
    day: 4,
    name: 'Cloud Garden Coffee',
    start: '09:00',
    end: '10:30',
    distance: '4.1 km',
    image: 'photo-1445116572660-236099ec97a0',
  },
  {
    id: 'last-day',
    day: 4,
    name: 'Last day in Da Lat',
    start: '12:00',
    end: '14:00',
    distance: '',
    image: 'photo-1500530855697-b586d89ba3ee',
  },
]

export type PlaceSuggestion = {
  name: string
  type: string
  image: string
}

export const suggestions: PlaceSuggestion[] = [
  {
    name: 'Lam Vien Square',
    type: 'Attraction',
    image: 'photo-1519608487953-e999c86e7455',
  },
  {
    name: 'Dalat Flower Plateau',
    type: 'Nature',
    image: 'photo-1490750967868-88aa4486c946',
  },
  {
    name: 'Tui Mo To Coffee & Garden',
    type: 'Cafe & Panoramic View',
    image: 'photo-1445116572660-236099ec97a0',
  },
  {
    name: 'Langbiang Peak Trek',
    type: 'Outdoors & Hiking',
    image: 'photo-1464822759023-fed622ff2c3b',
  },
  {
    name: 'Datanla Waterfall',
    type: 'Nature',
    image: 'photo-1470770841072-f978cf4d019e',
  },
  {
    name: 'Da Lat Night Market',
    type: 'Food & drink',
    image: 'photo-1517248135467-4c7edcad34c4',
  },
]

export const imageUrl = (id: string) =>
  `https://images.unsplash.com/${id}?auto=format&fit=crop&w=500&q=80`

