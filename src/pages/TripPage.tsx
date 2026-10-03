import { TripDetailRedesign } from '../features/trip/components/TripDetailRedesign'
import { useParams } from 'react-router-dom'

export function TripPage() {
  const { tripId } = useParams()
  return <TripDetailRedesign key={tripId} />
}
