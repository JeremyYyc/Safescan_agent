import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

// https://vite.dev/config/
const envDir = fileURLToPath(new URL('..', import.meta.url))
export default defineConfig(({ mode }) => ({
  envDir,
  envPrefix: [],
  // Exact allowlist: even VITE_API_BASE_SECRET must not enter the bundle.
  define: {
    'import.meta.env.VITE_API_BASE': JSON.stringify(loadEnv(mode, envDir, 'VITE_API_BASE').VITE_API_BASE || ''),
  },
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
}))
