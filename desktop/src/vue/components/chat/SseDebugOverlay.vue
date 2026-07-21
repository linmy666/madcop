<script setup lang="ts">
/**
 * SseDebugOverlay — visible SSE event log so users without DevTools
 * can see what events the chat backend actually delivered.
 *
 * Mounted at the top of the chat area (above MessageList) when
 * `window.__madcopSseDebug` is truthy OR when the session has any
 * debugSSELog entries. The overlay is collapsible and non-modal so
 * it never blocks the user from sending another message.
 *
 * The goal: when "the chat didn't reply" happens again, the user
 * can read off the event list (or its absence) without needing to
 * open DevTools.
 */
import { computed, ref } from 'vue'
import { useChatStore } from '../../stores/chatStore'

const props = defineProps<{ sessionId: string }>()
const chatStore = useChatStore()
const collapsed = ref(false)

const entries = computed(() => {
  const s = (chatStore as any).sessions?.[props.sessionId]
  return (s?.debugSSELog ?? []) as { t: number; type: string; id?: number; preview?: string }[]
})

const visible = computed(() => entries.value.length > 0)

function ts(e: { t: number }) {
  const d = new Date(e.t)
  return d.toLocaleTimeString('en-GB', { hour12: false }) + '.' + String(d.getMilliseconds()).padStart(3, '0')
}

function typeClass(t: string) {
  if (t === 'text') return 'sse-t-text'
  if (t === 'done') return 'sse-t-done'
  if (t === 'error' || t === 'HTTP_ERROR' || t === 'NETWORK_ERROR') return 'sse-t-err'
  if (t === 'ABORT' || t === 'NO_READER') return 'sse-t-warn'
  if (t === 'tool' || t === 'tool_result') return 'sse-t-tool'
  return 'sse-t-misc'
}

function clearLog() {
  const s = (chatStore as any).sessions?.[props.sessionId]
  if (s) s.debugSSELog = []
}
</script>

<template>
  <div v-if="visible" class="sse-overlay" role="region" aria-label="SSE 调试日志">
    <header class="sse-overlay__header" @click="collapsed = !collapsed">
      <div class="sse-overlay__title">
        <span class="material-symbols-outlined text-[16px]">bug_report</span>
        <span>SSE 事件 ({{ entries.length }})</span>
        <span v-if="collapsed" class="sse-overlay__hint">点击展开</span>
      </div>
      <div class="sse-overlay__actions">
        <button type="button" class="sse-overlay__btn" @click.stop="clearLog">清空</button>
        <button type="button" class="sse-overlay__btn" @click.stop="collapsed = !collapsed">
          {{ collapsed ? '▼' : '▲' }}
        </button>
      </div>
    </header>
    <div v-if="!collapsed" class="sse-overlay__body">
      <div v-if="entries.length === 0" class="sse-overlay__empty">
        尚未收到任何 SSE 事件 — fetch 还没发出或后端还没回复。
      </div>
      <ul v-else class="sse-overlay__list">
        <li v-for="(e, i) in entries" :key="i" class="sse-overlay__row">
          <span class="sse-overlay__ts">{{ ts(e) }}</span>
          <span class="sse-overlay__type" :class="typeClass(e.type)">{{ e.type }}</span>
          <span v-if="e.id !== undefined" class="sse-overlay__id">#{{ e.id }}</span>
          <span v-if="e.preview" class="sse-overlay__prev">{{ e.preview }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.sse-overlay {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e5e5e7);
  border-radius: 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  color: var(--color-text-primary, #111);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  overflow: hidden;
}
.sse-overlay__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  background: color-mix(in srgb, var(--color-brand, #7c3aed) 8%, var(--color-surface));
  cursor: pointer;
  user-select: none;
}
.sse-overlay__title {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--color-brand, #7c3aed);
  font-weight: 600;
}
.sse-overlay__hint {
  font-weight: 400;
  color: var(--color-text-tertiary, #888);
  font-size: 10px;
}
.sse-overlay__actions {
  display: flex;
  gap: 4px;
}
.sse-overlay__btn {
  background: transparent;
  border: 1px solid var(--color-border, #e5e5e7);
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 10px;
  cursor: pointer;
  color: var(--color-text-secondary, #555);
}
.sse-overlay__btn:hover {
  background: var(--color-surface-hover, #f0f0f2);
}
.sse-overlay__body {
  max-height: 220px;
  overflow-y: auto;
  padding: 4px 0;
}
.sse-overlay__empty {
  padding: 12px;
  color: var(--color-text-tertiary, #888);
  font-style: italic;
}
.sse-overlay__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.sse-overlay__row {
  display: grid;
  grid-template-columns: 90px 80px 36px 1fr;
  gap: 6px;
  padding: 2px 10px;
  align-items: baseline;
  border-bottom: 1px dashed color-mix(in srgb, var(--color-border) 50%, transparent);
}
.sse-overlay__row:hover {
  background: var(--color-surface-hover, #f5f5f7);
}
.sse-overlay__ts {
  color: var(--color-text-tertiary, #888);
  font-size: 10px;
}
.sse-overlay__type {
  font-weight: 600;
  text-align: center;
  padding: 0 4px;
  border-radius: 4px;
}
.sse-t-text { background: color-mix(in srgb, #22c55e 18%, transparent); color: #166534; }
.sse-t-done { background: color-mix(in srgb, #3b82f6 18%, transparent); color: #1d4ed8; }
.sse-t-err { background: color-mix(in srgb, #ef4444 18%, transparent); color: #b91c1c; }
.sse-t-warn { background: color-mix(in srgb, #f59e0b 18%, transparent); color: #b45309; }
.sse-t-tool { background: color-mix(in srgb, #8b5cf6 18%, transparent); color: #6d28d9; }
.sse-t-misc { background: var(--color-surface-container-low, #f5f5f7); color: var(--color-text-secondary, #555); }
.sse-overlay__id {
  color: var(--color-text-tertiary, #888);
  font-size: 10px;
}
.sse-overlay__prev {
  color: var(--color-text-secondary, #444);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>