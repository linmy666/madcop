<script setup lang="ts">
/**
 * TraceList — Vue 3 port of pages/TraceList.tsx
 * List of trace sessions with filtering and selection.
 * Prop-driven: parent passes traces, filters, onSelect.
 */

export interface TraceSummary {
  id: string
  title: string
  status: string
  startedAt: number
  durationMs?: number
  sessionId: string
}

export interface TraceListProps {
  traces: TraceSummary[]
  selectedId?: string
  isLoading?: boolean
}

const props = withDefaults(defineProps<TraceListProps>(), {
  isLoading: false,
})

const emit = defineEmits<{ select: [traceId: string] }>()

function formatDuration(ms?: number): string {
  if (ms == null) return '--'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleString()
}
</script>

<template>
  <div class="flex flex-col min-h-0">
    <div class="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)]">
      <h2 class="text-sm font-semibold text-[var(--color-text-primary)]">Trace Sessions</h2>
      <div class="flex items-center gap-2 text-xs text-[var(--color-text-tertiary)]">
        <span>{{ traces.length }} sessions</span>
        <span v-if="isLoading" class="animate-spin w-3 h-3 border border-[var(--color-brand)] border-t-transparent rounded-full" />
      </div>
    </div>
    <div class="flex-1 overflow-y-auto">
      <div v-if="traces.length === 0" class="flex items-center justify-center py-12 text-xs text-[var(--color-text-tertiary)]">
        No traces found
      </div>
      <div v-else class="divide-y divide-[var(--color-border)]/50">
        <div v-for="trace in traces" :key="trace.id"
          @click="emit('select', trace.id)"
          :class="['flex items-center gap-3 px-4 py-2.5 cursor-pointer transition-colors',
            selectedId === trace.id ? 'bg-[var(--color-surface-container)]' : 'hover:bg-[var(--color-surface-hover)]']">
          <span :class="['w-2 h-2 rounded-full shrink-0', trace.status === 'error' ? 'bg-[var(--color-error)]' : trace.status === 'running' ? 'bg-[var(--color-warning)]' : 'bg-[var(--color-success)]']" />
          <div class="min-w-0 flex-1">
            <div class="truncate text-xs font-medium text-[var(--color-text-primary)]">{{ trace.title }}</div>
            <div class="text-[10px] text-[var(--color-text-tertiary)]">{{ formatTime(trace.startedAt) }}</div>
          </div>
          <span class="shrink-0 font-mono text-[10px] text-[var(--color-text-tertiary)]">{{ formatDuration(trace.durationMs) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
