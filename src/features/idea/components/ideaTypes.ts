export type Idea = {
  name: string
  type: string
  image: string
}

export type IdeaDialog = 'add' | 'edit' | 'details' | 'itinerary' | null

export type IdeaAction = 'itinerary' | 'edit' | 'details' | 'delete'

export type IdeaBoardProps = {
  onAddToItinerary: (name: string) => void
}
