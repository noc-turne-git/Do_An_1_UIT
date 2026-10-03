import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from './AppShell'
import { HomePage } from '../pages/HomePage'
import { ExplorePage } from '../pages/ExplorePage'
import { TripsPage } from '../pages/TripsPage'
import { TripPage } from '../pages/TripPage'
import { SavedPage } from '../pages/SavedPage'
import { ChatsPage } from '../pages/ChatsPage'
import { LandingPage } from '../pages/LandingPage'

export const router = createBrowserRouter([{ path: '/', element: <LandingPage /> }, {
  element: <AppShell />,
  children: [
    { path: '/home', element: <HomePage /> },
    { path: '/explore', element: <ExplorePage /> },
    { path: '/trips', element: <TripsPage /> },
    { path: '/trips/:tripId', element: <TripPage /> },
    { path: '/saved', element: <SavedPage /> },
    { path: '/chats', element: <ChatsPage /> },
  ],
}])
