<script setup lang="ts">
// v3.0 — ComposerDropOverlay (Vue 3)
// Direct translation — same Tailwind classes, same structure.
defineProps<{
  title: string
  description: string
  testId?: string
}>()
</script>

<template>
  <div
    :data-testid="testId"
    class="composer-drop-overlay pointer-events-none absolute inset-0 z-40 flex items-center justify-center rounded-[inherit] border border-[var(--color-brand)]/45 bg-[var(--color-surface-container-lowest)]/88 p-4 backdrop-blur-[2px]"
    aria-hidden="true"
  >
    <div class="flex max-w-[280px] items-center gap-3 rounded-[10px] border border-[var(--color-brand)]/30 bg-[var(--color-surface-container-low)] px-4 py-3 text-left shadow-[var(--shadow-dropdown)]">
      <span class="material-symbols-outlined flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--color-brand)]/12 text-[20px] text-[var(--color-brand)]">
        upload_file
      </span>
      <span class="min-w-0">
        <span class="block text-sm font-semibold leading-5 text-[var(--color-text-primary)]">{{ title }}</span>
        <span class="block text-xs leading-5 text-[var(--color-text-tertiary)]">{{ description }}</span>
      </span>
    </div>
  </div>
</template>
