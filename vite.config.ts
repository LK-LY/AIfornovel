import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 5173,
    host: '127.0.0.1',
    allowedHosts: ['127.0.0.1', 'localhost'],
    cors: false,
    fs: {
      // Local source materials are not web assets, even in development mode.
      deny: ['.env', '.env.*', '**/*.{crt,pem}', '**/.git/**', '**/*.txt', '**/*.TXT', '**/private-data/**', '**/private-benchmarks/**', '**/private-reports/**', '**/.venv/**', '**/backend/**'],
    },
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } },
  },
  preview: { host: '127.0.0.1' },
})
