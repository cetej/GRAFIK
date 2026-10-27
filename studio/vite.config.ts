import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// GRAFIK Studio (G2).
// /api goes to GRAFIK Engine on :8300, so the browser never needs CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    // IPv4: Command Center checks the port on 127.0.0.1; vite would otherwise bind only [::1]
    host: '127.0.0.1',
    port: Number(process.env.GRAFIK_STUDIO_PORT ?? 5174),   // a worktree checks its build on another port
    strictPort: true,
    proxy: { '/api': process.env.GRAFIK_ENGINE_URL ?? 'http://127.0.0.1:8300' },
  },
})
