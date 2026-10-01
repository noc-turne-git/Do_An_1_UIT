import { create } from 'zustand'

type PlaceCollectionState = { savedIds: string[]; toggleSaved: (id: string) => void }
export const usePlaceCollection = create<PlaceCollectionState>((set) => ({
  savedIds: ['market', 'yersin'],
  toggleSaved: (id) => set((state) => ({ savedIds: state.savedIds.includes(id) ? state.savedIds.filter((item) => item !== id) : [...state.savedIds, id] })),
}))
