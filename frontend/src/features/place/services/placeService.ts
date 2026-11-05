import type { Place } from '../types'

const image = (id: string) => `https://images.unsplash.com/${id}?auto=format&fit=crop&w=900&q=85`
const explore: Place[] = [
  { id: 'hon-chong', name: 'Hon Chong Promontory', rating: '4.8', category: 'Scenic viewpoint', location: 'Vinh Phuoc, Nha Trang', mentions: 'Mentioned by Linh and 8 others', image: image('photo-1500530855697-b586d89ba3ee') },
  { id: 'po-nagar', name: 'Po Nagar Cham Towers', rating: '4.7', category: 'Historic site', location: 'Vinh Phuoc, Nha Trang', mentions: 'Mentioned by Alex and 5 others', image: image('photo-1564013799919-ab600027ffc6') },
  { id: 'beach', name: 'Nha Trang Beach', rating: '4.9', category: 'Beach', location: 'Loc Tho, Nha Trang', mentions: 'Mentioned by 12 travelers', image: image('photo-1507525428034-b723cf961d3e') },
  { id: 'pagoda', name: 'Long Son Pagoda', rating: '4.6', category: 'Temple', location: 'Phuong Son, Nha Trang', mentions: 'Mentioned by Mai and 4 others', image: image('photo-1548013146-72479768bada') },
]
const saved: Place[] = [
  { id: 'market', name: 'Cho Cu Ton That Dam', rating: '4.1', category: 'Attractions', location: 'Phu Huu, Ho Chi Minh City', image: image('photo-1555396273-367ea4eb4db5') },
  { id: 'yersin', name: 'Yersin Park', rating: '4.3', category: 'Attractions', location: 'Da Lat, Lam Dong', image: image('photo-1507525428034-b723cf961d3e') },
]
export const placeService = {
  async explore() { return explore },
  async saved() { return saved },
}
