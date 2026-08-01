<script setup lang="ts">
/**
 * Sprint 4 — CreationProgress: a 4-phase pipeline pill shown while the
 * "创作" (create) agent mode runs its search→fetch→outline→write flow.
 *
 * Phase is derived from the live session state, not from explicit SSE
 * events, so it works without any backend protocol changes:
 *   1 search  — activeToolName === 'web_search'
 *   2 fetch   — activeToolName === 'web_fetch'
 *   3 outline — busy, no tool, streaming text still empty
 *   4 write   — streaming text has started
 *
 * Only renders when the active session is in 'create' mode.
 */
import { computed } from 'vue'
import { useChatStore } from '../../stores/chatStore'
import { useTabStore } from '../../stores/tabs'
import { useSessionRuntimeStore } from '../../stores/sessionRuntimeStore'

const props = defineProps<{
  sessionId?: string | null
}>()

const chatStore = useChatStore()
const tabStore = useTabStore()
const runtimeStore = useSessionRuntimeStore()

const activeTabId = computed(() => props.sessionId || tabStore.activeTabId)
const sessionState = computed(() => (activeTabId.value ? chatStore.sessions[activeTabId.value] : undefined))

const isCreateMode = computed(() => {
  const key = activeTabId.value
  if (!key) return false
  return runtimeStore.selections[key]?.agentMode === 'create'
})

const PHASES = [
  { key: 'search', icon: 'travel_explore', label: '检索' },
  { key: 'fetch', icon: 'description', label: '抓取' },
  { key: 'outline', icon: 'list_alt', label: '大纲' },
  { key: 'write', icon: 'edit_note', label: '撰写' },
] as const

const busy = computed(() => {
  const s = sessionState.value
  if (!s) return false
  return s.chatState !== 'idle' && s.chatState !== 'error'
})

// search=phase0, fetch=phase1, outline=phase2, write=phase3.
const currentPhase = computed(() => {
  const s = sessionState.value
  if (!s || !busy.value) return -1
  const tool = s.activeToolName ?? ''
  const streaming = (s.streamingText ?? '').trim().length > 0
  if (streaming) return 3
  if (tool === 'web_fetch') return 1
  if (tool === 'web_search') return 0
  return 2
})

const show = computed(() => isCreateMode.value && currentPhase.value >= 0)
</script>

<template>
  <div v-if="show" class="cp-root" role="status" aria-live="polite">
    <div
      v-for="(phase, i) in PHASES"
      :key="phase.key"
      class="cp-phase"
      :class="{
        'cp-phase--done': currentPhase > i,
        'cp-phase--active': currentPhase === i,
      }"
    >
      <span class="material-symbols-outlined cp-icon">{{ phase.icon }}</span>
      <span class="cp-label">{{ phase.label }}</span>
      <span v-if="currentPhase === i" class="cp-dots">
        <span></span><span></span><span></span>
      </span>
      <span v-else-if="currentPhase > i" class="material-symbols-outlined cp-check">check_circle</span>
    </div>
  </div>
</template>

<style scoped>
.cp-root {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  margin: 4px 0;
  background: var(--color-primary-container);
  border: 1px solid var(--color-primary);
  border-radius: 999px;
  font-size: 12px;
  color: var(--color-on-primary-container);
  max-width: 100%;
  overflow-x: auto;
}
.cp-phase {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  border-radius: 999px;
  white-space: nowrap;
  opacity: 0.45;
  transition: opacity 200ms, background 200ms;
}
.cp-phase--active {
  opacity: 1;
  background: var(--color-surface);
  color: var(--color-primary);
  font-weight: 600;
}
.cp-phase--done {
  opacity: 0.8;
  text-decoration: line-through;
  text-decoration-color: rgba(0, 0, 0, 0.25);
}
.cp-icon {
  font-size: 15px;
}
.cp-label {
  font-size: 12px;
}
.cp-check {
  font-size: 13px;
}
.cp-dots {
  display: inline-flex;
  gap: 2px;
}
.cp-dots span {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: currentColor;
  animation: cp-bounce 1.2s infinite ease-in-out both;
}
.cp-dots span:nth-child(2) {
  animation-delay: 0.15s;
}
.cp-dots span:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes cp-bounce {
  0%, 80%, 100% {
    transform: scale(0.6);
    opacity: 0.4;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}
</style>
