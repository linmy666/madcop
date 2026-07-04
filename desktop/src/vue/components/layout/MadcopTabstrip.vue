<script setup lang="ts">
// v3.0 — MadCop Tabstrip (Vue 3)
// Horizontal list of open surfaces (chat, design, workflow, trace).

export type MadcopTabKind = 'chat' | 'design' | 'workflow' | 'trace'
export interface MadcopTab {
  id: string; kind: MadcopTabKind; title: string; dirty?: boolean; busy?: boolean
}

const props = defineProps<{ tabs: MadcopTab[]; active: string | null }>()
const emit = defineEmits<{
  (e: 'select', id: string): void
  (e: 'close',  id: string): void
}>()
</script>

<template>
  <div v-if="tabs.length === 0" class="madcop-tabstrip__empty">— 无打开的标签 —</div>
  <div v-else class="madcop-tabstrip">
    <div
      v-for="tab in tabs" :key="tab.id"
      :class="['madcop-tabstrip__tab', { 'madcop-tabstrip__tab--active': active === tab.id }]"
      @click="emit('select', tab.id)"
    >
      <span class="madcop-tabstrip__kind">{{ tab.kind }}</span>
      <span class="madcop-tabstrip__title">{{ tab.title }}</span>
      <span v-if="tab.busy" class="madcop-tabstrip__busy" />
      <span v-if="tab.dirty" class="madcop-tabstrip__dirty">●</span>
      <button class="madcop-tabstrip__close" @click.stop="emit('close', tab.id)">×</button>
    </div>
  </div>
</template>

<style scoped>
.madcop-tabstrip {
  width: 100%; height: 100%;
  display: flex; align-items: stretch;
  overflow-x: auto; overflow-y: hidden;
}
.madcop-tabstrip__empty {
  width: 100%; height: 100%;
  display: flex; align-items: center; padding: 0 16px;
  color: var(--madcop-ink-muted); font-size: 12px;
  font-family: 'Geist Mono', monospace;
}
.madcop-tabstrip__tab {
  display: flex; align-items: center; gap: 8px;
  padding: 0 12px; border-right: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-raised);
  color: var(--madcop-ink-body);
  cursor: pointer; position: relative; font-size: 13px;
  min-width: 120px; max-width: 220px;
  border-bottom: 2px solid transparent;
}
.madcop-tabstrip__tab--active {
  background: var(--madcop-panel);
  color: var(--madcop-ink);
  border-bottom-color: var(--madcop-accent);
}
.madcop-tabstrip__kind  { font-size: 10px; font-family: 'Geist Mono', monospace; color: var(--madcop-ink-muted); text-transform: uppercase; letter-spacing: 0.02em; }
.madcop-tabstrip__tab--active .madcop-tabstrip__kind { color: var(--madcop-accent); }
.madcop-tabstrip__title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 400; }
.madcop-tabstrip__tab--active .madcop-tabstrip__title { font-weight: 500; }
.madcop-tabstrip__busy  { width: 6px; height: 6px; border-radius: 50%; background: var(--madcop-warn); animation: madcop-blink 1s infinite; }
.madcop-tabstrip__dirty { color: var(--madcop-warn); font-size: 10px; }
.madcop-tabstrip__close { background: transparent; border: none; cursor: pointer; color: var(--madcop-ink-muted); font-size: 14px; padding: 0; line-height: 1; }
@keyframes madcop-blink { 50% { opacity: 0.3; } }
</style>
