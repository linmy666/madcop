<script setup lang="ts">
// v3.0 — Update banner (Vue 3)
// A simplified "update available" toast. Skips i18n / store / markdown
// dependencies that exist in the React version.
defineProps<{
  version?: string
  notes?: string
  show: boolean
}>()

const emit = defineEmits<{
  (e: 'install'): void
  (e: 'dismiss'): void
}>()
</script>

<template>
  <div v-if="show" class="madcop-update">
    <div class="madcop-update__panel">
      <p class="madcop-update__title">新版本 v{{ version }} 已就绪</p>
      <p v-if="notes" class="madcop-update__notes">{{ notes }}</p>
      <div class="madcop-update__actions">
        <button class="madcop-update__btn madcop-update__btn--primary" @click="emit('install')">
          安装并重启
        </button>
        <button class="madcop-update__btn" @click="emit('dismiss')">
          稍后
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.madcop-update {
  position: fixed; bottom: 16px; left: 50%;
  transform: translateX(-50%);
  z-index: 120;
  width: min(360px, calc(100vw - 32px));
}
.madcop-update__panel {
  padding: 12px;
  background: var(--madcop-panel-raised);
  border: 1.5px solid var(--madcop-line);
  border-radius: 6px;
  box-shadow: 0 4px 20px rgba(15, 23, 42, 0.08);
}
.madcop-update__title {
  font-size: 13px; font-weight: 500;
  color: var(--madcop-ink); margin: 0;
}
.madcop-update__notes {
  font-size: 11px; line-height: 1.5;
  color: var(--madcop-ink-body); margin: 4px 0 0;
  max-height: 100px; overflow-y: auto;
}
.madcop-update__actions {
  display: flex; gap: 6px; margin-top: 8px;
}
.madcop-update__btn {
  padding: 4px 10px;
  font-size: 11px; cursor: pointer;
  background: transparent; border: 1.5px solid var(--madcop-line);
  color: var(--madcop-ink-body);
}
.madcop-update__btn--primary {
  background: var(--madcop-accent);
  color: var(--madcop-accent-ink);
  border-color: var(--madcop-accent);
}
</style>
