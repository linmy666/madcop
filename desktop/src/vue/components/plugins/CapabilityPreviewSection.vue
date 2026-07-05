<script setup lang="ts">
// v3.0 — CapabilityPreviewSection (Vue 3)
// Direct translation of CapabilityPreviewSection component from PluginDetail.tsx
withDefaults(
  defineProps<{
    title: string
    count: number
    emptyLabel: string
    hint?: string
  }>(),
  {
    hint: undefined,
  }
)
</script>

<template>
  <section class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] overflow-hidden">
    <div class="flex items-center justify-between gap-3 border-b border-[var(--color-border)] px-4 py-3">
      <div class="text-sm font-semibold text-[var(--color-text-primary)]">{{ title }}</div>
      <div class="text-[11px] text-[var(--color-text-tertiary)]">{{ count }}</div>
    </div>
    <div class="p-4">
      <div v-if="hint && count > 0" class="mb-3 text-xs text-[var(--color-text-tertiary)]">
        {{ hint }}
      </div>
      <div v-if="count > 0">
        <slot />
      </div>
      <div v-else class="text-xs text-[var(--color-text-tertiary)]">{{ emptyLabel }}</div>
    </div>
  </section>
</template>