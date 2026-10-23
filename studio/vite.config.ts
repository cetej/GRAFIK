import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// GRAFIK Studio (G2). The old v1 editor keeps :5173 until it is archived (decision 2026-10-23).
// /api goes to GRAFIK Engine on :8300, so the browser never needs CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8300' },
  },
})
