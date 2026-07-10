// v3.0 — Vue 3 build config
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
  build: {
    outDir: 'dist-vue',
    emptyOutDir: true,
    target: ['es2021', 'safari15'],
    chunkSizeWarningLimit: 2200,
    // Disable minification — the minifier mangles Vue's `ref` function
    // to `k` and creates collisions with local variables also named `k`.
    // Disabling minification keeps the build larger but readable and crash-free.
    minify: false,
    rollupOptions: {
      input: 'index.html',
      onwarn(warning, warn) {
        if (warning.code === 'INEFFECTIVE_DYNAMIC_IMPORT') return
        warn(warning)
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
})
