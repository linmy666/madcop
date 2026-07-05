<script setup lang="ts">
defineProps<{ children?: string }>()
</script>

<template>
  <span class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]">
    <slot></slot>
  </span>
</template>