// v3.0 — Vue 3 dev-server config
// Used by `bun run electron:dev` so the Electron window serves Vue, not React.
// Differs from vite.vue.config.ts (production build) only in:
//   - target entry: vue-dev.html (referring to /src/vue/main.ts) instead of build output
//   - server.port + strictPort so the Electron waitForRenderer can ping it
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  base: './',
  define: {
    'import.meta.env.VITE_DESKTOP_SERVER_URL': JSON.stringify('http://127.0.0.1:8765'),
  },
  plugins: [vue(), tailwindcss()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: false,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
})