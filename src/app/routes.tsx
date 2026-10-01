import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from './AppShell'
import { HomePage } from '../pages/HomePage'
import { ExplorePage } from '../pages/ExplorePage'
import { TripsPage } from '../pages/TripsPage'
import { TripPage } from '../pages/TripPage'
import { SavedPage } from '../pages/SavedPage'
import { ChatsPage } from '../pages/ChatsPage'

export const router = createBrowserRouter([{
  element: <AppShell />,
  children: [
    { path: '/', element: <HomePage /> },
    { path: '/explore', element: <ExplorePage /> },
    { path: '/trips', element: <TripsPage /> },
    { path: '/trips/:tripId', element: <TripPage /> },
    { path: '/saved', element: <SavedPage /> },
    { path: '/chats', element: <ChatsPage /> },
  ],
}])
