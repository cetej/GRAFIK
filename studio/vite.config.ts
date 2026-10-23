import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// GRAFIK Studio (G2).
// /api goes to GRAFIK Engine on :8300, so the browser never needs CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    // IPv4: Command Center checks the port on 127.0.0.1; vite would otherwise bind only [::1]
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8300' },
  },
})
