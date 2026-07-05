<script setup lang="ts">
/**
 * TraceDetail — Vue 3 port of components/trace/TraceDetail.tsx
 * Detail view for a selected trace span. Uses SessionOverview for default view.
 * Prop-driven: parent passes span, viewModel, sessionId, onSelect.
 */

export interface TraceSpan {
  id: string
  kind: string
  title: string
  status: string
  durationMs?: number
  timestamp: number
  completedAt?: number
  toolName?: string
  call?: { model?: string; provider?: { name: string }; usage?: any; request: any; response?: any; startedAt: number }
  toolUseId?: string
  event?: { phase: string; severity: string; message?: string; metadata?: Record<string, any> }
}

export interface TraceDetailProps {
  span: TraceSpan
  viewModel: any
  sessionId: string
}

const props = defineProps<TraceDetailProps>()
const emit = defineEmits<{ select: [spanId: string] }>()

const { icon: iconKind, color: iconColor } = iconForSpanKind(props.span.kind, props.span.status)

function iconForSpanKind(kind: string, status: string): { icon: string; color: string } {
  if (kind === 'llm') return { icon: 'sparkle', color: 'var(--color-brand)' }
  if (kind === 'tool') return { icon: 'build', color: 'var(--color-warning)' }
  if (kind === 'turn') return { icon: 'call_split', color: 'var(--color-text-tertiary)' }
  if (kind === 'session') return { icon: 'radio', color: 'var(--color-text-tertiary)' }
  if (kind === 'event') return status === 'error' ? { icon: 'warning', color: 'var(--color-error)' } : { icon: 'radio_button_unchecked', color: 'var(--color-text-tertiary)' }
  return { icon: 'description', color: 'var(--color-text-tertiary)' }
}
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col" data-testid="trace-detail">
    <div class="shrink-0 border-b border-[var(--color-border)] px-4 py-2.5">
      <div class="flex min-w-0 items-center gap-2">
        <span class="material-symbols-outlined text-[14px]" :style="{ color: iconColor }">{{ iconKind }}</span>
        <h2 class="min-w-0 truncate text-sm font-semibold text-[var(--color-text-primary)]">{{ span.title }}</h2>
        <span :class="['inline-flex shrink-0 items-center rounded-[var(--radius-sm)] px-1.5 py-0.5 text-[10px] font-semibold',
          statusBadgeClass(span.status)]">
          {{ pillLabel(span.status) }}
        </span>
      </div>
    </div>
    <div class="min-h-0 flex-1 overflow-y-auto">
      <slot :span="span" :view-model="viewModel" :session-id="sessionId" />
    </div>
  </div>
</template>

<script lang="ts">
// Simple status badge helper for template
const statusBadgeClass = (status: string) => {
  if (status === 'error') return 'bg-[var(--color-error)]/10 text-[var(--color-error)]'
  if (status === 'pending') return 'bg-[var(--color-warning)]/10 text-[var(--color-warning)]'
  return 'bg-[var(--color-success)]/10 text-[var(--color-success)]'
}
const pillLabel = (status: string) => {
  if (status === 'error') return 'Error'
  if (status === 'pending') return 'Pending'
  return 'OK'
}
</script>
