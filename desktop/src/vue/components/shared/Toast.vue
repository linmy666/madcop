<script setup lang="ts">
// v3.0 — Toast container (Vue 3)
// Standalone version: the parent passes a list of toasts and a
// remove handler. Avoids hard-coupling to the React zustand UI store;
// a future migration to Pinia will swap the props for a composable.

defineProps<{
  toasts: Array<{
    id: string
    type: 'success' | 'error' | 'warning' | 'info'
    message: string
  }>
}>()

const emit = defineEmits<{ (e: 'remove', id: string): void }>()
</script>

<template>
  <div v-if="toasts.length > 0" class="madcop-toast-container">
    <div
      v-for="t in toasts" :key="t.id"
      :class="['madcop-toast', `madcop-toast--${t.type}`]"
    >
      <span class="madcop-toast__msg">{{ t.message }}</span>
      <button class="madcop-toast__close" @click="emit('remove', t.id)">×</button>
    </div>
  </div>
</template>

<style scoped>
.madcop-toast-container {
  position: fixed; bottom: 16px; right: 16px; z-index: 100;
  display: flex; flex-direction: column; gap: 8px;
  max-width: 360px;
}
.madcop-toast {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 12px 16px;
  background: var(--madcop-panel-raised);
  border: 1.5px solid var(--madcop-line);
  border-left-width: 4px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
  font-size: 13px;
  color: var(--madcop-ink);
  animation: madcop-toast-in 200ms ease-out;
}
.madcop-toast--success { border-left-color: var(--madcop-success); }
.madcop-toast--error   { border-left-color: var(--madcop-danger); }
.madcop-toast--warning { border-left-color: var(--madcop-warn); }
.madcop-toast--info    { border-left-color: var(--madcop-accent); }
.madcop-toast__close {
  background: transparent; border: none; cursor: pointer;
  color: var(--madcop-ink-muted); font-size: 16px; line-height: 1; padding: 0;
}
.madcop-toast__close:hover { color: var(--madcop-ink); }
@keyframes madcop-toast-in {
  from { transform: translateX(20px); opacity: 0; }
  to   { transform: translateX(0); opacity: 1; }
}
</style>
