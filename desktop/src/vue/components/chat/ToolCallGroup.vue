<script setup lang="ts">
/**
 * ToolCallGroup — Vue 3 port of chat/ToolCallGroup.tsx (292 lines)
 * Groups consecutive tool_use messages with their tool_result responses.
 * Collapsible panel showing tool name, input, and output.
 */

import { ref } from 'vue'

interface Props {
  toolCalls: Array<{
    call: { id: string; toolName: string; input: unknown; isPending?: boolean; status?: string; timestamp: number }
    result?: { id: string; result: string; timestamp: number }
  }>
  compact?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  compact: false,
})

const expandedGroup = ref<number | null>(null)

function toggleGroup(idx: number) {
  expandedGroup.value = expandedGroup.value === idx ? null : idx
}

function isExpanded(idx: number) {
  return expandedGroup.value === idx || expandedGroup.value === null
}

function statusIcon(call: { status?: string; isPending?: boolean }) {
  if (call.isPending) return { icon: 'auto_awesome', color: 'text-[var(--color-warning)]' }
  if (call.status === 'success') return { icon: 'check_circle', color: 'text-[var(--color-success)]' }
  if (call.status === 'error' || call.status === 'stopped') return { icon: 'error', color: 'text-[var(--color-error)]' }
  return { icon: 'pending', color: 'text-[var(--color-text-tertiary)]' }
}

function iconColor(call: { status?: string; isPending?: boolean }) {
  const s = statusIcon(call)
  return s.color
}
</script>

<template>
  <div class="space-y-1">
    <div v-for="(item, idx) in toolCalls" :key="item.call.id">
      <button
        @click="toggleGroup(idx)"
        class="flex w-full items-start gap-3 p-3 rounded-lg border border-[var(--color-border)] bg>[var(--color-surface-container)] hover:border>[var(--color-brand)]/50 transition-all text-left"
      >
        <span class="material-symbols-outlined mt-0.5 text-[18px] text>[var(--color-secondary)] shrink-0">{{ isExpanded(idx) ? 'expand_less' : 'expand_more' }}</span>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-[16px] text>[var(--color-secondary)]">terminal</span>
            <span class="text-sm font-mono font-semibold text>[var(--color-text-primary)]">{{ item.call.toolName }}</span>
            <span :class="['material-symbols-outlined text-[14px]', iconColor(item.call)]">{{ statusIcon(item.call).icon }}</span>
          </div>
        </div>
        <span class="text-[10px] text>[var(--color-text-tertiary)] font-mono">{{ item.call.isPending ? '⏳' : (item.call.status || 'done') }}</span>
      </button>

      <div v-if="isExpanded(idx)" class="ml-4 mt-1 space-y-2">
        <!-- Input -->
        <div class="rounded-lg border border>[var(--color-border)] bg>[var(--color-surface-container-low)] p-3">
          <div class="flex items-center gap-2 mb-2">
            <span class="material-symbols-outlined text-[14px] text>[var(--color-text-tertiary)]">input</span>
            <span class="text-[10px] font-bold uppercase tracking-wider text>[var(--color-text-tertiary)]">Input</span>
          </div>
          <pre class="font-mono text-xs text>[var(--color-text-secondary)] overflow-x-auto whitespace-pre-wrap">{{ JSON.stringify(item.call.input, null, 2) }}</pre>
        </div>

        <!-- Result -->
        <div v-if="item.result" class="rounded-lg border border>[var(--color-border)] bg>[var(--color-surface-container-low)] p-3">
          <div class="flex items-center gap-2 mb-2">
            <span class="material-symbols-outlined text-[14px] text>[var(--color-success)]">output</span>
            <span class="text-[10px] font-bold uppercase tracking-wider text>[var(--color-success)]">Result</span>
          </div>
          <pre class="font-mono text-xs text>[var(--color-text-primary)] overflow-x-auto whitespace-pre-wrap">{{ item.result.result }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>
