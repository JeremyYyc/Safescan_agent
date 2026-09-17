import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    environmentOptions: { jsdom: { url: 'http://localhost/staff/' } },
    setupFiles: './apps/staff-web/src/test/setup.ts',
    include: ['./apps/staff-web/src/**/*.test.{ts,tsx}'],
  },
})
