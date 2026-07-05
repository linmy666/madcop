<script setup lang="ts">
// v3.0 — HookPreviewCard (Vue 3)
// Direct translation of HookPreviewCard component from PluginDetail.tsx
defineProps<{
  event: string
  matcher?: string
  actions: string[]
}>()
</script>

<template>
  <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
    <div class="flex items-center gap-2 flex-wrap">
      <span class="text-sm font-semibold text-[var(--color-text-primary)] break-all">{{ event }}</span>
      <span v-if="matcher" class="rounded-full bg-[var(--color-surface-container-high)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-text-tertiary)] break-all">
        {{ matcher }}
      </span>
    </div>
    <div class="mt-2 flex flex-wrap gap-2">
      <span
        v-for="action in actions"
        :key="action"
        class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-2.5 py-1 text-[11px] text-[var(--color-text-secondary)] break-all"
      >
        {{ action }}
      </span>
    </div>
  </div>
</template>