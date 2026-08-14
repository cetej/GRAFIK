import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// No StrictMode: it double-invokes effects in dev, which would generate the
// layers twice and skew the benchmark. This is a perf spike, not app shell code.
createRoot(document.getElementById('root')!).render(<App />)
