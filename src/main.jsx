import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { ThemeProvider } from './themes/ThemeContext.jsx'
import { ToastProvider } from './components/ui.jsx'
import AuthGate from './components/AuthGate.jsx'
import { FeaturesProvider } from './lib/features.jsx'
import { startAutoUpdate } from './lib/autoUpdate.js'

startAutoUpdate()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ThemeProvider>
      <ToastProvider>
        <AuthGate>
          <FeaturesProvider>
            <App />
          </FeaturesProvider>
        </AuthGate>
      </ToastProvider>
    </ThemeProvider>
  </StrictMode>,
)
