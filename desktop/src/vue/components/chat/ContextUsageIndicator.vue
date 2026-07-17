<script setup lang="ts">
/**
 * v3.3 — ContextUsageIndicator
 *
 * Prefers server inspection estimate when available; falls back to
 * client-side char/message heuristics. Max defaults to 128K.
 */

import { ref, computed, watch } from 'vue'
import { sessionsApi } from '../../api/sessions'

interface ContextCategory {
  name: string
  tokens: number
}

const props = withDefaults(defineProps<{
  sessionId?: string
  chatState?: string
  messageCount?: number
  compact?: boolean
  maxTokens?: number
  totalContent?: string  // raw text of all messages for accurate estimate
}>(), {
  sessionId: '',
  chatState: 'idle',
  messageCount: 0,
  compact: false,
  maxTokens: 128000,
  totalContent: '',
})

const serverTokens = ref<number | null>(null)

async function refreshFromServer() {
  if (!props.sessionId) {
    serverTokens.value = null
    return
  }
  try {
    const data = await sessionsApi.getInspection(props.sessionId, {
      includeContext: true,
      timeout: 12_000,
    })
    const est =
      (data as any)?.context?.estimatedTokens ??
      (data as any)?.status?.estimatedTokens ??
      null
    serverTokens.value = typeof est === 'number' && est > 0 ? est : null
  } catch {
    /* keep local estimate */
  }
}

watch(
  () => [props.sessionId, props.messageCount, props.chatState] as const,
  ([, , state]) => {
    // Refresh after a turn finishes or on session switch
    if (state === 'idle' || state === undefined) {
      void refreshFromServer()
    }
  },
  { immediate: true },
)

// Live total tokens, recomputed when content changes
const totalTokens = computed(() => {
  if (serverTokens.value != null) return serverTokens.value
  if (props.totalContent && props.totalContent.length > 0) {
    // ~1 token per 1.6 characters for English; ~1 token per 1 character for Chinese
    // Mixed → ~1.3 chars/token average
    return Math.max(0, Math.round(props.totalContent.length / 1.3))
  }
  // Fallback: estimate from message count
  return Math.max(0, (props.messageCount || 0) * 600)
})

const percent = computed(() => {
  const t = totalTokens.value
  const m = props.maxTokens || 128000
  if (m <= 0) return 0
  return Math.max(0, Math.min(100, (t / m) * 100))
})

const formattedPercent = computed(() => `${percent.value.toFixed(1)}%`)

const circumference = 2 * Math.PI * 6 // r = 6
const dashOffset = computed(() => circumference * (1 - percent.value / 100))
</script>

<template>
  <div :class="['context-indicator', compact ? 'context-indicator--compact' : '']">
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" class="flex-shrink-0">
      <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5" opacity="0.2" fill="none"/>
      <circle
        cx="8" cy="8" r="6"
        :stroke="percent > 80 ? 'var(--color-error, #dc2626)' : percent > 50 ? 'var(--color-warning, #d97706)' : 'var(--color-brand, #7c3aed)'"
        stroke-width="1.5"
        fill="none"
        stroke-linecap="round"
        :stroke-dasharray="circumference"
        :stroke-dashoffset="dashOffset"
        transform="rotate(-90 8 8)"
      />
    </svg>
    <span v-if="!compact" class="context-indicator__pct">{{ formattedPercent }}</span>
  </div>
</template>

<style scoped>
.context-indicator {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.context-indicator__pct {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}
</style>
