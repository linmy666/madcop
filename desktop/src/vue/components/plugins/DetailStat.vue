<script setup lang="ts">
// v3.0 — DetailStat (Vue 3)
// Direct translation of DetailStat component from PluginDetail.tsx
defineProps<{
  label: string
  value: string
  icon: string
}>()
</script>

<template>
  <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3">
    <div class="flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-[var(--color-text-tertiary)]">
      <span class="material-symbols-outlined text-[14px]">{{ icon }}</span>
      <span>{{ label }}</span>
    </div>
    <div class="mt-2 text-base font-semibold text-[var(--color-text-primary)] break-all">
      {{ value }}
    </div>
  </div>
</template>