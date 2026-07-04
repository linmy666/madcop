<script setup lang="ts">
// v3.0 — InlineTaskSummary (Vue 3)
// Direct translation of InlineTaskSummary.tsx — same Tailwind classes.
defineProps<{
  text: string
  status?: 'ok' | 'error' | 'pending'
}>()
</script>

<template>
  <div
    :class="[
      'inline-flex items-center gap-1.5 rounded-[var(--radius-md)] px-2.5 py-1 text-xs font-medium',
      status === 'error'
        ? 'bg-[var(--color-error-container)] text-[var(--color-on-error-container)]'
        : status === 'pending'
        ? 'bg-[var(--color-warning-container)] text-[var(--color-warning)]'
        : 'bg-[var(--color-success-container)] text-[var(--color-success)]',
    ]"
  >
    <span class="material-symbols-outlined text-[14px]">
      {{ status === 'error' ? 'error' : status === 'pending' ? 'pending' : 'check_circle' }}
    </span>
    {{ text }}
  </div>
</template>
