<script setup lang="ts">
// v3.0 — StatusBar (Vue 3)
// Direct translation of StatusBar.tsx — same Tailwind classes.
// Uses props instead of zustand stores (Vue version will use Pinia).
defineProps<{
  projectName?: string
  modelLabel?: string
}>()
</script>

<template>
  <div
    class="h-[var(--statusbar-height)] flex items-center justify-between px-4 border-t border-[var(--color-border)] bg-[var(--color-surface-sidebar)] select-none text-[11px]"
  >
    <div class="flex items-center gap-3">
      <span v-if="projectName" class="text-[var(--color-text-secondary)] font-[var(--font-mono)]">{{ projectName }}</span>
    </div>
    <div class="flex items-center gap-4">
      <span v-if="modelLabel" class="text-[var(--color-text-tertiary)] font-[var(--font-mono)]">{{ modelLabel }}</span>
    </div>
  </div>
</template>
