<script setup lang="ts">
/**
 * ToolDetail — Vue 3 port of components/trace/detail/ToolDetail.tsx
 * Renders a tool/tool_result span: input JSON, output results, meta grid.
 * Prop-driven: parent passes a TraceSpan with kind 'tool' or 'tool_result'.
 */
import { useTranslation } from '../../../i18n'
import type { TraceSpan } from '../../../lib/traceViewModel'
import { formatTraceJson } from '../../../lib/traceViewModel'
import { formatClockTime, formatDurationMs } from '../../../lib/trace/formatters'
import CodeViewer from '../../chat/CodeViewer.vue'
import Section from './Section.vue'

const props = defineProps<{
  span: TraceSpan
}>()

const t = useTranslation()

const outputs = collectOutputs(props.span)
const pending = props.span.status === 'pending'

function collectOutputs(span: TraceSpan): unknown[] {
  if (span.output === undefined) return []
  if (Array.isArray(span.output)) return span.output
  return [span.output]
}

function extractPlainText(content: unknown): string | null {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    const parts: string[] = []
    for (const item of content) {
      if (typeof item === 'string') {
        parts.push(item)
        continue
      }
      if (item && typeof item === 'object' && typeof (item as { text?: unknown }).text === 'string') {
        parts.push((item as { text: string }).text)
        continue
      }
      return null
    }
    return parts.join('\n')
  }
  return null
}
</script>

<template>
  <div data-testid="trace-tool-detail">
    <!-- Input section -->
    <Section
      v-if="span.input !== undefined"
      section-key="tool.input"
      :title="t('trace.section.input')"
      :default-open="true"
    >
      <CodeViewer :code="formatTraceJson(span.input!)" language="json" :max-lines="32" show-line-numbers />
    </Section>

    <!-- Result section -->
    <Section section-key="tool.result" :title="t('trace.section.result')" :default-open="true">
      <!-- Pending -->
      <div
        v-if="pending"
        class="rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] px-3 py-3 text-xs text-[var(--color-text-tertiary)]"
      >
        {{ t('trace.waitingForResult') }}
      </div>
      <!-- Has outputs -->
      <div v-else-if="outputs.length > 0" class="flex flex-col gap-2">
        <OutputView v-for="(output, index) in outputs" :key="index" :value="output" />
      </div>
      <!-- No data -->
      <div
        v-else
        class="rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] px-3 py-3 text-xs text-[var(--color-text-tertiary)]"
      >
        {{ t('trace.noData') }}
      </div>
    </Section>

    <!-- Meta section -->
    <Section section-key="tool.meta" :title="t('trace.section.meta')">
      <dl class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-[11px]">
        <template v-if="span.toolUseId">
          <MetaRow :label="t('trace.detail.toolUseId')" :value="span.toolUseId!" />
        </template>
        <MetaRow
          :label="t('trace.status')"
          :value="span.status === 'error' ? t('trace.status.error') : span.status === 'pending' ? t('trace.status.pending') : t('trace.status.ok')"
        />
        <MetaRow :label="t('trace.started')" :value="formatClockTime(span.timestamp)" />
        <template v-if="span.completedAt">
          <MetaRow :label="t('trace.completed')" :value="formatClockTime(span.completedAt!)" />
        </template>
        <template v-if="span.durationMs !== undefined">
          <MetaRow
            :label="span.status === 'pending' ? t('trace.elapsed') : t('trace.duration')"
            :value="formatDurationMs(span.durationMs!)"
          />
        </template>
      </dl>
    </Section>
  </div>
</template>

<script lang="ts">
// ── Sub-components ───────────────────────────────────────────────────
import type { Component } from 'vue'
import { formatTraceJson } from '../../../lib/traceViewModel'

// MetaRow — dt/dd pair for meta grid
export const MetaRow: Component = {
  name: 'MetaRow',
  props: {
    label: String,
    value: String,
  },
  template: `
    <>
      <dt class="text-[var(--color-text-tertiary)]">{{ label }}</dt>
      <dd class="min-w-0 truncate font-mono text-[var(--color-text-secondary)]">{{ value }}</dd>
    </>
  `,
}

// OutputView — renders a single tool output (plain text or JSON)
export const OutputView: Component = {
  name: 'OutputView',
  props: {
    value: null as unknown as () => unknown,
  },
  setup(props) {
    const text = extractPlainText(props.value)
    return { text }
  },
  template: `
    <TextResult v-if="text !== null && text.trim()" :text="text" />
    <CodeViewer v-else :code="formatTraceJson(value)" language="json" :max-lines="32" show-line-numbers />
  `,
}

// TextResult — plain text output in pre
export const TextResult: Component = {
  name: 'TextResult',
  props: {
    text: String,
  },
  template: `
    <pre class="max-h-[400px] overflow-y-auto whitespace-pre-wrap break-words rounded-[var(--radius-sm)] bg-[var(--color-surface-container-low)] px-2 py-1.5 font-mono text-[11px] leading-5 text-[var(--color-text-secondary)]">
{{ props.text }}
    </pre>
  `,
}

function extractPlainText(content: unknown): string | null {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    const parts: string[] = []
    for (const item of content) {
      if (typeof item === 'string') {
        parts.push(item)
        continue
      }
      if (item && typeof item === 'object' && typeof (item as { text?: unknown }).text === 'string') {
        parts.push((item as { text: string }).text)
        continue
      }
      return null
    }
    return parts.join('\n')
  }
  return null
}
</script>