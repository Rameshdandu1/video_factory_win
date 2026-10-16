import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const developmentHostname = process.env.VIDEO_FACTORY_DEV_HOSTNAME?.trim()

if (
  developmentHostname !== undefined &&
  !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.ts\.net$/.test(
    developmentHostname,
  )
) {
  throw new Error('VIDEO_FACTORY_DEV_HOSTNAME must be one exact Tailscale ts.net hostname')
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    ...(developmentHostname === undefined ? {} : { allowedHosts: [developmentHostname] }),
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: true,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: true,
    restoreMocks: true,
    clearMocks: true,
  },
})
