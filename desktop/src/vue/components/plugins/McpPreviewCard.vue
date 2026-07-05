<script setup lang="ts">
// v3.0 — McpPreviewCard (Vue 3)
// Direct translation of McpPreviewCard component from PluginDetail.tsx
withDefaults(
  defineProps<{
    name: string
    transport: string
    summary: string
    disabled?: boolean
  }>(),
  {
    disabled: false,
  }
)

defineEmits<{
  (e: 'click'): void
}>()
</script>

<template>
  <button
    type="button"
    @click="$emit('click')"
    :disabled="disabled"
    class="group rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-left transition-colors hover:border-[var(--color-border-focus)] hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)] disabled:cursor-default disabled:opacity-70 disabled:hover:border-[var(--color-border)] disabled:hover:bg-[var(--color-surface)]"
  >
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-sm font-semibold text-[var(--color-text-primary)] break-all">{{ name }}</span>
          <span class="rounded-full bg-[var(--color-surface-container-high)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]">
            {{ transport }}
          </span>
        </div>
        <div class="mt-2 text-xs leading-5 text-[var(--color-text-secondary)] break-all">{{ summary }}</div>
      </div>
      <span class="material-symbols-outlined text-[18px] text-[var(--color-text-tertiary)] transition-transform group-hover:translate-x-0.5">
        chevron_right
      </span>
    </div>
  </button>
</template>