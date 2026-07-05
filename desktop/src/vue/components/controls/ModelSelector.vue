<script setup lang="ts">
// v3.0 — ModelSelector (Vue 3) — MadCop custom design
// Uses a custom SVG chip icon instead of Material Symbols
defineProps<{ compact?: boolean; disabled?: boolean; runtimeKey?: string }>()
</script>

<template>
  <div
    class="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)] bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-secondary)] cursor-pointer hover:bg-[var(--color-surface-hover)] transition-colors"
    :class="{ 'opacity-50 pointer-events-none': disabled }"
  >
    <!-- Custom chip icon (not Material Symbols) -->
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" class="flex-shrink-0">
      <rect x="2" y="2" width="5" height="5" rx="1" fill="currentColor" opacity="0.8"/>
      <rect x="9" y="2" width="5" height="5" rx="1" fill="currentColor" opacity="0.4"/>
      <rect x="2" y="9" width="5" height="5" rx="1" fill="currentColor" opacity="0.4"/>
      <rect x="9" y="9" width="5" height="5" rx="1" fill="currentColor" opacity="0.8"/>
    </svg>
    <span>GLM-5.2</span>
    <svg width="10" height="10" viewBox="0 0 12 12" fill="none" class="opacity-50">
      <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </div>
</template>