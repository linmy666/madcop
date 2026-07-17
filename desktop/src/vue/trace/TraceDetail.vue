<script setup lang="ts">
/**
 * TraceDetail — Vue 3 port of components/trace/TraceDetail.tsx
 * Detail view for a selected trace span. Uses SessionOverview for default view.
 * Prop-driven: parent passes span, viewModel, sessionId, onSelect.
 * Renders TypeIcon, StatusPill, HeaderChips + DetailBody (LlmCallDetail/ToolDetail/
 * MessageDetail/EventDetail/SessionOverview) based on span.kind.
 */
import { useTranslation } from '../i18n'
import type { TraceSpan, TraceViewModel } from '../lib/traceViewModel'
import { formatTraceJson } from '../lib/traceViewModel'
import { formatClockTime, formatDurationMs, formatTokenCount, formatUsageBrief } from '../lib/trace/formatters'
import { formatBytes } from '../lib/formatBytes'
import CodeViewer from '../components/chat/CodeViewer.vue'
import { spanDisplayTitle, traceEventPhaseLabel, MetaChip, StatusPill, TypeIcon } from './TraceBadges.vue'
import Section from '../components/trace/detail/Section.vue'
import LlmCallDetail from '../components/trace/detail/LlmCallDetail.vue'
import ToolDetail from '../components/trace/detail/ToolDetail.vue'
import MessageDetail from '../components/trace/detail/MessageDetail.vue'
import SessionOverview from '../components/trace/detail/SessionOverview.vue'

const props = defineProps<{
  span: TraceSpan
  viewModel: TraceViewModel
  sessionId: string
}>()

const emit = defineEmits<{
  select: [spanId: string]
}>()

const t = useTranslation()

// ── Helpers ───────────────────────────────────────────────────────────
function durationLabelForSpan(span: TraceSpan): string {
  if (span.status === 'pending') return t('trace.elapsed')
  if (span.kind === 'session' || span.kind === 'turn') return t('trace.wallTime')
  return t('trace.duration')
}

function usageTooltip(usage: NonNullable<TraceSpan['tokenUsage']>): string {
  const parts = [
    `in ${formatTokenCount(usage.inputTokens)}`,
    `out ${formatTokenCount(usage.outputTokens)}`,
  ]
  if (usage.cacheReadInputTokens !== undefined) {
    parts.push(`cache read ${formatTokenCount(usage.cacheReadInputTokens)}`)
  }
  if (usage.cacheCreationInputTokens !== undefined) {
    parts.push(`cache write ${formatTokenCount(usage.cacheCreationInputTokens)}`)
  }
  return parts.join(' · ')
}

// ── Computed values ───────────────────────────────────────────────────
const displayTitle = spanDisplayTitle(props.span, t)
const call = props.span.call ?? null
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col" data-testid="trace-detail">
    <!-- Header -->
    <div class="shrink-0 border-b border-[var(--color-border)] px-4 py-2.5">
      <div class="flex min-w-0 items-center gap-2">
        <TypeIcon :span="span" />
        <h2 class="min-w-0 truncate text-sm font-semibold text-[var(--color-text-primary)]">
          {{ displayTitle }}
        </h2>
        <StatusPill :status="span.status" />
      </div>
      <div class="mt-1 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
        <HeaderChips :span="span" :t="t" :call="call" />
      </div>
    </div>

    <!-- Detail body -->
    <div class="min-h-0 flex-1 overflow-y-auto">
      <DetailBody :span="span" :view-model="viewModel" :session-id="sessionId" @select="(id) => emit('select', id)" />
    </div>
  </div>
</template>

<script lang="ts">
// ── Sub-components (defined in non-setup script for import/export) ────
import type { Component } from 'vue'
import { computed } from 'vue'
import { useTranslation } from '../i18n'
import type { TraceSpan, TraceViewModel } from '../lib/traceViewModel'
import { formatTraceJson } from '../lib/traceViewModel'
import { formatClockTime, formatDurationMs } from '../lib/trace/formatters'
import CodeViewer from '../components/chat/CodeViewer.vue'
import { MetaChip, StatusPill, TypeIcon, spanDisplayTitle, traceEventPhaseLabel } from './TraceBadges.vue'
import Section from '../components/trace/detail/Section.vue'
import LlmCallDetail from '../components/trace/detail/LlmCallDetail.vue'
import ToolDetail from '../components/trace/detail/ToolDetail.vue'
import MessageDetail from '../components/trace/detail/MessageDetail.vue'
import SessionOverview from '../components/trace/detail/SessionOverview.vue'

// HeaderChips — renders the metadata chips in the header
export const HeaderChips: Component = {
  name: 'HeaderChips',
  props: {
    span: Object as () => TraceSpan,
    t: Function as () => ReturnType<typeof useTranslation>,
    call: Object as () => TraceSpan['call'] | null,
  },
  setup(props) {
    return { formatDurationMs, formatUsageBrief, formatBytes, formatClockTime, usageTooltip }
  },
  template: `
    <template v-if="props.call">
      <template v-if="props.call.model">
        <MetaChip :label="props.t('trace.model')" :value="props.call.model" />
      </template>
      <template v-if="props.call.provider?.name">
        <MetaChip :label="props.t('trace.provider')" :value="props.call.provider.name" />
      </template>
      <template v-if="props.span.durationMs !== undefined">
        <MetaChip
          :label="props.span.status === 'pending' ? props.t('trace.elapsed') : props.t('trace.duration')"
          :value="formatDurationMs(props.span.durationMs!)"
        />
      </template>
      <template v-if="props.call.usage">
        <MetaChip
          :label="props.t('trace.tokens')"
          :value="formatUsageBrief(props.call.usage)"
          :title="usageTooltip(props.call.usage)"
        />
      </template>
      <MetaChip :label="props.t('trace.request')" :value="formatBytes(props.call.request.body.bytes)" />
      <template v-if="props.call.response">
        <MetaChip :label="props.t('trace.response')" :value="formatBytes(props.call.response.body.bytes)" />
        <MetaChip
          :label="props.t('trace.status')"
          :value="String(props.call.response.status)"
          :tone="props.call.response.status >= 400 ? 'danger' : 'default'"
        />
      </template>
      <MetaChip :label="props.t('trace.started')" :value="formatClockTime(props.call.startedAt)" />
      <template v-if="props.span.completedAt">
        <MetaChip :label="props.t('trace.completed')" :value="formatClockTime(props.span.completedAt!)" />
      </template>
    </template>
    <template v-else>
      <template v-if="props.span.toolUseId">
        <MetaChip :label="props.t('trace.detail.toolUseId')" :value="props.span.toolUseId!" />
      </template>
      <template v-if="props.span.durationMs !== undefined">
        <MetaChip
          :label="durationLabelForSpan(props.span, props.t)"
          :value="formatDurationMs(props.span.durationMs!)"
        />
      </template>
      <MetaChip :label="props.t('trace.started')" :value="formatClockTime(props.span.timestamp)" />
      <template v-if="props.span.completedAt">
        <MetaChip :label="props.t('trace.completed')" :value="formatClockTime(props.span.completedAt!)" />
      </template>
    </template>
  `,
}

// Duration label helper for the non-call branch of HeaderChips
function durationLabelForSpan(span: TraceSpan, t: ReturnType<typeof useTranslation>): string {
  if (span.status === 'pending') return t('trace.elapsed')
  if (span.kind === 'session' || span.kind === 'turn') return t('trace.wallTime')
  return t('trace.duration')
}

// Usage tooltip helper
function usageTooltip(usage: NonNullable<TraceSpan['tokenUsage']>): string {
  const parts = [
    `in ${formatTokenCount(usage.inputTokens)}`,
    `out ${formatTokenCount(usage.outputTokens)}`,
  ]
  if (usage.cacheReadInputTokens !== undefined) {
    parts.push(`cache read ${formatTokenCount(usage.cacheReadInputTokens)}`)
  }
  if (usage.cacheCreationInputTokens !== undefined) {
    parts.push(`cache write ${formatTokenCount(usage.cacheCreationInputTokens)}`)
  }
  return parts.join(' · ')
}

// DetailBody — routes to the correct detail component based on span.kind
export const DetailBody: Component = {
  name: 'DetailBody',
  props: {
    span: Object as () => TraceSpan,
    viewModel: Object as () => TraceViewModel,
    sessionId: String,
  },
  emits: ['select'],
  setup(props) {
    return { props }
  },
  template: `
    <template v-if="props.span.kind === 'llm'">
      <LlmCallDetail :session-id="props.sessionId" :span="props.span" />
    </template>
    <template v-else-if="props.span.kind === 'tool' || props.span.kind === 'tool_result'">
      <ToolDetail :span="props.span" />
    </template>
    <template v-else-if="props.span.kind === 'message'">
      <MessageDetail :span="props.span" />
    </template>
    <template v-else-if="props.span.kind === 'event'">
      <EventDetail :span="props.span" />
    </template>
    <template v-else>
      <SessionOverview :span="props.span" :view-model="props.viewModel" @select="(id: string) => $emit('select', id)" />
    </template>
  `,
}

// EventDetail — renders event phase/severity/message + metadata
export const EventDetail: Component = {
  name: 'EventDetail',
  props: {
    span: Object as () => TraceSpan,
  },
  setup() {
    const t = useTranslation()
    return { t, formatTraceJson }
  },
  template: `
    <div data-testid="trace-event-detail">
      <Section section-key="event.detail" :title="t('trace.section.event')" :default-open="true">
        <dl class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-[11px]">
          <dt class="text-[var(--color-text-tertiary)]">{{ t('trace.detail.phase') }}</dt>
          <dd class="min-w-0 truncate font-mono text-[var(--color-text-secondary)]">
            {{ traceEventPhaseLabel(props.span.event!.phase, t) }}
          </dd>
          <dt class="text-[var(--color-text-tertiary)]">{{ t('trace.detail.severity') }}</dt>
          <dd :class="[
            'min-w-0 truncate font-mono',
            props.span.event!.severity === 'error' ? 'text-[var(--color-error)]' : 'text-[var(--color-text-secondary)]'
          ]">
            {{ props.span.event!.severity }}
          </dd>
          <template v-if="props.span.event!.message">
            <dt class="text-[var(--color-text-tertiary)]">{{ t('trace.detail.message') }}</dt>
            <dd class="min-w-0 whitespace-pre-wrap break-words text-[var(--color-text-secondary)]">
              {{ props.span.event!.message }}
            </dd>
          </template>
        </dl>
      </Section>
      <Section v-if="props.span.event && Object.keys(props.span.event.metadata || {}).length > 0" section-key="event.metadata" :title="t('trace.section.metadata')" :default-open="true">
        <CodeViewer :code="formatTraceJson(props.span.event!.metadata)" language="json" :max-lines="32" show-line-numbers />
      </Section>
    </div>
  `,
}
</script>