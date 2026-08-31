import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  envDir: fileURLToPath(new URL('..', import.meta.url)),
  envPrefix: ['VITE_API_BASE'],
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000', '/uploads': 'http://localhost:8000' } },
})
