export type Idea = {
  name: string
  type: string
  image: string
  price?: number
  currency?: string
}

export type IdeaDialog = 'add' | 'edit' | 'details' | 'itinerary' | null

export type IdeaAction = 'itinerary' | 'edit' | 'details' | 'delete'

export type IdeaBoardProps = {
  initialIdeas?: Idea[]
  onAddToItinerary: (name: string) => void
}
