import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// When running inside Docker Compose, VITE_API_PROXY_TARGET=http://go-proxy:9000
// For local dev outside Docker: VITE_API_PROXY_TARGET=http://localhost:9000
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET || 'http://go-proxy:9000',
        changeOrigin: true,
      },
    },
  },
})
