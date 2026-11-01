import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { PanelBoundary } from './panels.tsx'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PanelBoundary what="GRAFIK Studio" note="Obnovte stránku (F5). Data v Engine zůstala beze změny.">
      <App />
    </PanelBoundary>
  </StrictMode>,
)
