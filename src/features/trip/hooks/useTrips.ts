import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { tripService } from '../services/tripService'

export const tripKeys = { all: ['trips'] as const, detail: (id: string) => ['trips', id] as const }
export function useTrips() { return useQuery({ queryKey: tripKeys.all, queryFn: tripService.list }) }
export function useTrip(id: string) { return useQuery({ queryKey: tripKeys.detail(id), queryFn: () => tripService.get(id) }) }
export function useCreateTrip() {
  const client = useQueryClient()
  return useMutation({ mutationFn: tripService.create, onSuccess: (trip) => { client.setQueryData(tripKeys.all, (old: Awaited<ReturnType<typeof tripService.list>> | undefined) => [trip, ...(old ?? [])]); client.setQueryData(tripKeys.detail(trip.id), trip) } })
}
export function useUpdateTrip() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: Parameters<typeof tripService.update>[1] }) => tripService.update(id, changes),
    onSuccess: (trip) => {
      client.setQueryData(tripKeys.detail(trip.id), trip)
      client.setQueryData(tripKeys.all, (old: Awaited<ReturnType<typeof tripService.list>> | undefined) => old?.map((item) => item.id === trip.id ? trip : item))
    },
  })
}
export function useAddTripChat() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ tripId, firstMessage }: { tripId: string; firstMessage?: string }) => tripService.addChat(tripId, firstMessage),
    onSuccess: (trip) => {
      client.setQueryData(tripKeys.detail(trip.id), trip)
      client.setQueryData(tripKeys.all, (old: Awaited<ReturnType<typeof tripService.list>> | undefined) => old?.map((item) => item.id === trip.id ? trip : item))
    },
  })
}
