export type TripMessage = { from: 'You' | 'AI'; text: string }
export type TripChat = { id: string; name: string; updated: string; main?: boolean; messages: TripMessage[] }
export type Trip = {
  id: string; name: string; destination: string; duration: string; when: string; budget: string
  cover: string; travelers: string[]; chats: TripChat[]
}
