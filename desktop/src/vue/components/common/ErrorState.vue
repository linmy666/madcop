<script setup lang="ts">
/**
 * ErrorState — shared error display with retry button (C-1).
 * Replaces ~100 generic "X 加载失败" strings with an actionable pattern:
 * message + optional retry. Reuses the sidebar's proven error pattern.
 */
defineProps<{
  message: string
  retryLabel?: string
}>()
const emit = defineEmits<{ (e: 'retry'): void }>()
</script>

<template>
  <div class="error-state">
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="error-state__icon">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
    <p class="error-state__msg">{{ message }}</p>
    <button v-if="retryLabel" class="error-state__retry" @click="emit('retry')">{{ retryLabel }}</button>
  </div>
</template>

<style scoped>
.error-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 32px 16px; text-align: center; gap: 8px;
}
.error-state__icon { color: var(--color-text-tertiary, #888); opacity: 0.6; }
.error-state__msg { font-size: 13px; color: var(--color-text-secondary, #aaa); max-width: 320px; line-height: 1.5; }
.error-state__retry {
  padding: 6px 16px; border-radius: 8px; font-size: 12px; font-weight: 500; cursor: pointer;
  background: var(--color-surface-container, rgba(255,255,255,0.05));
  border: 1px solid var(--color-border, rgba(255,255,255,0.1));
  color: var(--color-text-primary, #fff); transition: all .15s;
}
.error-state__retry:hover { border-color: var(--color-brand, #4a9eff); }
</style>
