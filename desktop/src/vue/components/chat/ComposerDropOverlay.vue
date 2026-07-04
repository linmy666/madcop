<script setup lang="ts">
// v3.0 — Composer drop overlay (Vue 3)
// Shown when a file is dragged over the chat composer area.
defineProps<{
  title: string
  description: string
  testId?: string
}>()
</script>

<template>
  <div
    :data-testid="testId"
    class="composer-drop-overlay"
    aria-hidden="true"
  >
    <div class="composer-drop-overlay__card">
      <span class="composer-drop-overlay__icon">↑</span>
      <span class="composer-drop-overlay__text">
        <span class="composer-drop-overlay__title">{{ title }}</span>
        <span class="composer-drop-overlay__desc">{{ description }}</span>
      </span>
    </div>
  </div>
</template>

<style scoped>
.composer-drop-overlay {
  position: absolute; inset: 0; z-index: 40;
  display: flex; align-items: center; justify-content: center;
  padding: 16px;
  background: rgba(248, 250, 252, 0.88);
  border: 1.5px solid var(--madcop-accent);
  border-radius: inherit;
  pointer-events: none;
  backdrop-filter: blur(2px);
}
.composer-drop-overlay__card {
  display: flex; align-items: center; gap: 12px;
  max-width: 280px; padding: 12px 16px;
  border: 1.5px solid var(--madcop-accent);
  background: var(--madcop-panel-raised);
  text-align: left;
}
.composer-drop-overlay__icon {
  display: flex; width: 36px; height: 36px; flex-shrink: 0;
  align-items: center; justify-content: center;
  background: var(--madcop-accent-subtle);
  color: var(--madcop-accent);
  border-radius: 50%;
  font-size: 18px; font-weight: 700;
}
.composer-drop-overlay__text { display: flex; flex-direction: column; min-width: 0; }
.composer-drop-overlay__title { font-size: 13px; font-weight: 600; color: var(--madcop-ink); line-height: 1.4; }
.composer-drop-overlay__desc  { font-size: 11px; color: var(--madcop-ink-muted); line-height: 1.4; }
</style>
