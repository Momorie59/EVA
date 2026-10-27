import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// En dev, on imite les routes de Caddy : l'interface appelle la même origine
// et Vite relaie vers EVA CORE / EVA VOICE.
const core = process.env.EVA_CORE_DEV_URL || 'http://localhost:8000'
const voice = process.env.EVA_VOICE_DEV_URL || 'http://localhost:8100'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/ws/chat': { target: core, ws: true, changeOrigin: true },
      '/api': { target: core, changeOrigin: true },
      '/voice': { target: voice, changeOrigin: true, rewrite: (p) => p.replace(/^\/voice/, '') },
    },
  },
})
