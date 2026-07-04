<script setup lang="ts">
// v3.0 — WindowControls (Vue 3)
// Direct translation — same SVG icons, same Tailwind classes.
// macOS traffic lights are handled by the OS; this is Windows-only.
import { ref, onMounted, onUnmounted } from 'vue'

const isWindows = typeof navigator !== 'undefined' && /Win/.test(navigator.platform)
const showControls = isWindows  // simplified — no desktopHost bridge in Vue

const maximized = ref(false)
const visible = ref(showControls)

function minimize() {}
function toggleMaximize() { maximized.value = !maximized.value }
function close() {}
</script>

<template>
  <div v-if="visible" data-testid="window-controls" class="flex items-stretch flex-shrink-0 -my-px">
    <button
      @click="minimize"
      aria-label="Minimize window"
      class="w-[46px] h-full flex items-center justify-center text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] transition-colors"
    >
      <svg width="10" height="1" viewBox="0 0 10 1"><rect width="10" height="1" fill="currentColor" /></svg>
    </button>
    <button
      @click="toggleMaximize"
      :aria-label="maximized ? 'Restore window' : 'Maximize window'"
      class="w-[46px] h-full flex items-center justify-center text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] transition-colors"
    >
      <svg v-if="maximized" width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1">
        <rect x="0" y="3" width="7" height="7" />
        <polyline points="3,3 3,0 10,0 10,7 7,7" />
      </svg>
      <svg v-else width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1">
        <rect x="0.5" y="0.5" width="9" height="9" />
      </svg>
    </button>
    <button
      @click="close"
      aria-label="Close window"
      class="w-[46px] h-full flex items-center justify-center text-[var(--color-text-secondary)] hover:bg-[var(--color-window-close-hover)] hover:text-white transition-colors"
    >
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.2">
        <line x1="0" y1="0" x2="10" y2="10" />
        <line x1="10" y1="0" x2="0" y2="10" />
      </svg>
    </button>
  </div>
</template>
