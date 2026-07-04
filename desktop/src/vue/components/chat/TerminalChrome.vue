<script setup lang="ts">
// v3.0 — TerminalChrome (Vue 3)
// Direct translation — same macOS traffic lights, same Tailwind classes.
defineProps<{ title?: string }>()
</script>

<template>
  <div class="overflow-hidden rounded-2xl border border-[var(--color-outline-variant)]/20 bg-[var(--color-surface-dim)]">
    <div class="flex items-center gap-2 border-b border-[var(--color-terminal-border)] bg-[var(--color-terminal-header)] px-3 py-2">
      <div class="flex gap-1.5">
        <div class="w-2.5 h-2.5 rounded-full bg-[var(--color-terminal-danger)]" />
        <div class="w-2.5 h-2.5 rounded-full bg-[var(--color-terminal-warning)]" />
        <div class="w-2.5 h-2.5 rounded-full bg-[var(--color-terminal-accent)]" />
      </div>
      <span v-if="title" class="ml-2 truncate font-[var(--font-mono)] text-[10px] text-[var(--color-terminal-muted)]">
        {{ title }}
      </span>
    </div>
    <div class="bg-[var(--color-terminal-bg)] text-[var(--color-terminal-fg)]">
      <slot />
    </div>
  </div>
</template>
