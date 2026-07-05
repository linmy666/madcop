<script setup lang="ts">
// v3.0 — CommandPreviewCard (Vue 3)
// Direct translation of CommandPreviewCard component from PluginDetail.tsx
defineProps<{
  name: string
  description: string
}>()
</script>

<template>
  <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
    <div class="text-sm font-semibold text-[var(--color-text-primary)] break-all">/{{ name }}</div>
    <div class="mt-2 text-xs leading-5 text-[var(--color-text-secondary)] break-words">{{ description }}</div>
  </div>
</template>