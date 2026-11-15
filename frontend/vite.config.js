import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Las llamadas a /api se reenvían al backend FastAPI (así no hay problemas de CORS)
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
