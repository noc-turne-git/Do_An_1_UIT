import { initializeAuth } from './features/auth/store/useAuthStore'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './app/App'

const disposeAuth = initializeAuth()
if (import.meta.hot) import.meta.hot.dispose(disposeAuth)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
