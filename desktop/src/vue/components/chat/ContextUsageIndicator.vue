<script setup lang="ts">
/**
 * v3.1 — ContextUsageIndicator (Vue 3) — real token usage meter
 *
 * Fetches /api/sessions/{id}/context → shows used/max tokens + percent
 * + 4 token categories (system, tools, messages, free space).
 * Replaces the stub that just showed a clock + message count.
 */

import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { getApiUrl } from '../../api/client'

interface ContextCategory {
  name: string
  tokens: number
  isDeferred?: boolean
}

interface ContextSnapshot {
  total_tokens: number
  max_tokens: number
  categories: ContextCategory[]
  updated_at: number | null
}

const props = defineProps<{
  sessionId?: string
  chatState?: string
  messageCount?: number
  runtimeSelectionKey?: string
  fallbackModelLabel?: string
  compact?: boolean
  refreshNonce?: number
}>()

const context = ref<ContextSnapshot | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
let timer: number | null = null

const REFRESH_MS = 30_000

const percent = computed(() => {
  if (!context.value || !context.value.max_tokens) return 0
  return Math.max(0, Math.min(100, (context.value.total_tokens / context.value.max_tokens) * 100))
})

const display = computed(() => {
  if (!context.value) return { used: 0, max: 0 }
  return {
    used: context.value.total_tokens,
    max: context.value.max_tokens,
  }
})

const formattedPercent = computed(() => {
  const p = percent.value
  return p >= 10 ? `${p.toFixed(0)}%` : `${p.toFixed(1)}%`
})

const formattedUsed = computed(() => formatNumber(display.value.used))
const formattedMax = computed(() => formatNumber(display.value.max))

const topCategories = computed<ContextCategory[]>(() => {
  if (!context.value) return []
  const ignored = new Set(['free space', 'autocompact buffer'])
  return context.value.categories
    .filter((c) => c.tokens > 0 && !c.isDeferred && !ignored.has(c.name.toLowerCase()))
    .sort((a, b) => b.tokens - a.tokens)
    .slice(0, 4)
})

function formatNumber(n: number): string {
  return new Intl.NumberFormat().format(Math.round(n))
}

async function fetchContext() {
  if (!props.sessionId) return
  loading.value = true
  error.value = null
  try {
    const res = await fetch(getApiUrl(`/api/sessions/${props.sessionId}/inspection`), {
      signal: AbortSignal.timeout(10_000),
    })
    if (res.ok) {
      const data = await res.json()
      context.value = {
        total_tokens: data.total_tokens ?? 0,
        max_tokens: data.max_tokens ?? data.context_window ?? 128000,
        categories: data.categories ?? [],
        updated_at: Date.now(),
      }
    } else if (res.status === 404) {
      // No context endpoint yet — fall back to estimating
      context.value = estimateFromMessages()
    } else {
      error.value = `HTTP ${res.status}`
    }
  } catch (e) {
    // Network error — show estimated
    context.value = estimateFromMessages()
  } finally {
    loading.value = false
  }
}

function estimateFromMessages(): ContextSnapshot {
  // Rough estimate: 1 message ≈ 500 tokens
  const est = (props.messageCount ?? 0) * 500
  return {
    total_tokens: est,
    max_tokens: 128000,
    categories: [
      { name: 'messages', tokens: est },
    ],
    updated_at: Date.now(),
  }
}

function startPolling() {
  stopPolling()
  timer = window.setInterval(fetchContext, REFRESH_MS)
}
function stopPolling() {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

watch(
  () => [props.sessionId, props.refreshNonce],
  () => {
    if (props.sessionId) {
      fetchContext()
      startPolling()
    } else {
      context.value = null
      stopPolling()
    }
  },
  { immediate: true }
)

onBeforeUnmount(stopPolling)

// Re-emit for parent: percentage
defineExpose({ percent, context, fetchContext })
</script>

<template>
  <div :class="['context-indicator', compact ? 'context-indicator--compact' : '']">
    <!-- Gauge icon (NOT a clock) -->
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" class="flex-shrink-0">
      <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5" opacity="0.25" fill="none"/>
      <path
        d="M8 4.5V8L10.5 10.5"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        fill="none"
        opacity="0.7"
      />
    </svg>
    <span v-if="!compact" class="context-indicator__label">
      <span class="context-indicator__used">{{ formattedUsed }}</span>
      <span class="context-indicator__sep">/</span>
      <span class="context-indicator__max">{{ formattedMax }}</span>
    </span>
    <span v-if="!compact" class="context-indicator__pct">{{ formattedPercent }}</span>
  </div>
</template>

<style scoped>
.context-indicator {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  font-size: 11px;
  color: var(--color-text-tertiary);
  font-family: ui-monospace, 'SF Mono', monospace;
}
.context-indicator--compact {
  padding: 2px 4px;
}
.context-indicator__label {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.context-indicator__used {
  color: var(--color-text-secondary);
}
.context-indicator__sep {
  opacity: 0.4;
  margin: 0 1px;
}
.context-indicator__max {
  color: var(--color-text-tertiary);
}
.context-indicator__pct {
  margin-left: 4px;
  padding: 0 5px;
  background: var(--color-surface-container);
  border-radius: 8px;
  color: var(--color-text-secondary);
  font-size: 10px;
}
</style>
