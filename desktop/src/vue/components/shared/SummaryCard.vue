<script setup lang="ts">
defineProps<{
  label: string
  value: string
  icon?: string
  className?: string
}>()
</script>

<template>
  <div :class="`rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3 min-w-0 ${className || ''}`">
    <div class="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-tertiary)] min-w-0">
      <span v-if="icon" class="material-symbols-outlined text-[14px] flex-shrink-0">{{ icon }}</span>
      <span class="truncate">{{ label }}</span>
    </div>
    <div class="mt-2 text-lg font-semibold text-[var(--color-text-primary)] truncate">
      {{ value }}
    </div>
  </div>
</template>