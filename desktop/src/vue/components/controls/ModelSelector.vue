<script setup lang="ts">
defineProps<{ compact?: boolean; disabled?: boolean; runtimeKey?: string }>()
</script>
<template>
  <div class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-[var(--radius-md)] bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-secondary)]">
    <span class="material-symbols-outlined text-[14px]">tune</span>
    <span>GLM-5.2</span>
  </div>
</template>
