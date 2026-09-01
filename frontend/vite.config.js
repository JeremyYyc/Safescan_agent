import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

// https://vite.dev/config/
const envDir = fileURLToPath(new URL('..', import.meta.url))
export default defineConfig({
  envDir,
  envPrefix: [],
  plugins: [react()],
  // Browser uses gateway even in development; HMR traverses its WebSocket proxy.
  server: { host: '0.0.0.0', port: 80, strictPort: true, hmr: { path: '/vite-hmr' } },
})
