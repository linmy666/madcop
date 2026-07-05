<script setup lang="ts">
/**
 * SessionOverview — Vue 3 port of components/trace/detail/SessionOverview.tsx
 * Overview stats and child span list for a trace span.
 * Prop-driven: parent passes span, viewModel, onSelect.
 * TraceBadge helpers (TypeIcon, StatusGlyph) rendered as span icons.
 */

export interface SpanType {
  kind: string
  status: string
  durationMs?: number
  call?: { model?: string }
  toolName?: string
  title: string
  message?: { type: string }
}

export interface SessionOverviewProps {
  span: SpanType & { childIds?: string[] }
  viewModel: { spansById: Map<string, SpanType> }
}

const props = defineProps<SessionOverviewProps>()

const children = computed(() => {
  if (!props.span.childIds) return []
  return props.span.childIds
    .map((id) => props.viewModel.spansById.get(id))
    .filter((child): child is SpanType => !!child)
})

const stats = computed(() => ({
  llmCalls: children.value.filter((c) => c.kind === 'llm').length,
  toolCalls: children.value.filter((c) => c.kind === 'tool').length,
  errors: children.value.filter((c) => c.status === 'error').length,
  wallDurationMs: props.span.durationMs,
  models: [...new Set(children.value.filter((c) => c.kind === 'llm').map((c) => c.call?.model || '').filter(Boolean))],
}))

function iconForSpan(span: SpanType): string {
  if (span.kind === 'llm') return 'sparkle'
  if (span.kind === 'tool') return 'build'
  if (span.kind === 'turn') return 'call_split'
  if (span.kind === 'session') return 'radio'
  if (span.status === 'error') return 'warning'
  return 'radio_button_unchecked'
}

function statusIcon(span: SpanType): string | null {
  if (span.status === 'error') return 'error'
  if (span.status === 'pending') return 'schedule'
  return null
}

function displayTitle(span: SpanType): string {
  if (span.kind === 'message' && span.message) return span.message.type
  if (span.kind === 'llm') return span.call?.model || span.title
  if (span.kind === 'tool') return span.toolName || span.title
  if (span.kind === 'turn') return span.title || 'Turn'
  return span.title
}

function formatDuration(ms?: number): string {
  if (ms == null) return '--'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}
</script>

<template>
  <div class="px-4 py-3" data-testid="trace-overview">
    <div class="grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-3">
      <Stat label="LLM Calls" :value="stats.llmCalls" />
      <Stat label="Tool Calls" :value="stats.toolCalls" />
      <Stat label="Errors" :value="stats.errors" :tone="stats.errors > 0 ? 'danger' : 'default'" />
      <Stat label="Wall Time" :value="formatDuration(stats.wallDurationMs)" />
      <Stat label="Models" :value="stats.models.length > 0 ? stats.models.join(', ') : '--'" />
    </div>

    <div v-if="children.length > 0" class="mt-4">
      <div class="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]">
        Child Spans
      </div>
      <div class="divide-y divide-[var(--color-border)]/60">
        <button v-for="child in children" :key="child.id" type="button"
          class="flex h-[34px] w-full items-center gap-2 text-left transition-colors hover:bg-[var(--color-surface-container-low)]">
          <span class="material-symbols-outlined text-[14px] text-[var(--color-brand)] shrink-0">{{ iconForSpan(child) }}</span>
          <span class="min-w-0 flex-1 truncate text-xs font-semibold text-[var(--color-text-secondary)]">{{ displayTitle(child) }}</span>
          <span v-if="child.durationMs" class="shrink-0 font-mono text-[10px] text-[var(--color-text-tertiary)]">{{ formatDuration(child.durationMs) }}</span>
          <span v-if="statusIcon(child)" class="material-symbols-outlined text-[13px] text-[var(--color-error)] shrink-0">{{ statusIcon(child) }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

