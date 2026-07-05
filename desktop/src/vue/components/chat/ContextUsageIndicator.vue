<script setup lang="ts">
// v3.0 — ContextUsageIndicator (Vue 3) — MadCop custom design
// Shows token usage with a custom circular gauge instead of Material Symbols
defineProps<{
  messageCount?: number
  modelLabel?: string
  compact?: boolean
}>()
</script>

<template>
  <div class="inline-flex items-center gap-1.5 px-2 py-1 text-[10px] text-[var(--color-text-tertiary)]">
    <!-- Custom gauge icon -->
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" class="flex-shrink-0">
      <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.2" opacity="0.25"/>
      <path d="M8 4V8L10.5 10" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" opacity="0.7"/>
    </svg>
    <span v-if="!compact">{{ messageCount ?? 0 }} 条</span>
  </div>
</template>