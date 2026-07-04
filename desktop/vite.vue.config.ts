// v3.0 — Vue 3 parallel build config.
//
// This file does NOT replace the React app. It exists to verify the
// Vue 3 SFCs compile cleanly under our toolchain. The Electron
// shell still loads dist/index.html (React) by default.
//
// To preview the Vue build: `vite build --config vite.vue.config.ts`
// then load dist-vue/index.html in any browser.

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  base: './',
  plugins: [vue()],
  build: {
    outDir: 'dist-vue',
    emptyOutDir: true,
    target: ['es2021', 'safari15'],
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      input: 'vue-preview.html',
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
