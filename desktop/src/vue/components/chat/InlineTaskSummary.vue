<script setup lang="ts">
// v3.0 — Inline task summary (Vue 3)
// Compact one-line summary of a completed task inside a chat message.
defineProps<{
  text: string
  status?: 'ok' | 'error' | 'pending'
}>()
</script>

<template>
  <div :class="['task-summary', `task-summary--${status || 'ok'}`]">
    <span class="task-summary__glyph">
      {{ status === 'error' ? '✕' : status === 'pending' ? '⋯' : '✓' }}
    </span>
    <span class="task-summary__text">{{ text }}</span>
  </div>
</template>

<style scoped>
.task-summary {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px;
  font-size: 12px;
  border: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-raised);
  color: var(--madcop-ink-body);
}
.task-summary--ok      { border-color: var(--madcop-success); }
.task-summary--error   { border-color: var(--madcop-danger); }
.task-summary--pending { border-color: var(--madcop-warn); }
.task-summary__glyph { font-family: 'Geist Mono', monospace; }
.task-summary--ok .task-summary__glyph      { color: var(--madcop-success); }
.task-summary--error .task-summary__glyph   { color: var(--madcop-danger); }
.task-summary--pending .task-summary__glyph { color: var(--madcop-warn); }
</style>
