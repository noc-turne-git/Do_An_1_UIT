import { useQuery } from '@tanstack/react-query'
import { placeService } from '../services/placeService'
export function useExplorePlaces() { return useQuery({ queryKey: ['places', 'explore'], queryFn: placeService.explore }) }
export function useSavedPlaces() { return useQuery({ queryKey: ['places', 'saved'], queryFn: placeService.saved }) }
