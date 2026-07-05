<script setup lang="ts">
/**
 * MessageDetail — Vue 3 port of components/trace/detail/MessageDetail.tsx
 * Renders a trace message span: content blocks + raw JSON.
 * Prop-driven: parent passes a TraceSpan with .message.
 */
import { computed } from 'vue'
import { useTranslation } from '../../../i18n'
import type { TraceSpan } from '../../../lib/traceViewModel'
import { formatTraceJson } from '../../../lib/traceViewModel'
import type { NormalizedBlock, NormalizedMessage } from '../../../lib/trace/types'
import { normalizeContentBlock } from '../../../lib/trace/sse'
import CodeViewer from '../../components/chat/CodeViewer.vue'
import Section from './Section.vue'
import MessageBlocks from '../../trace/detail/MessageBlocks.vue'

const props = defineProps<{
  span: TraceSpan
}>()

const t = useTranslation()

// ── useMemo equivalent: normalizeMessageEntry ─────────────────────────
// Caches the normalized message (same dependency as React useMemo)
const normalized = computed(() => {
  const message = props.span.message
  if (!message) return null
  return normalizeMessageEntry(message)
})

const message = computed(() => props.span.message)

function normalizeMessageEntry(msg: TraceSpan['message']): NormalizedMessage | null {
  if (!msg) return null
  const role: NormalizedMessage['role'] =
    msg.type === 'assistant' || msg.type === 'tool_use'
      ? 'assistant'
      : msg.type === 'system'
        ? 'system'
        : msg.type === 'tool_result'
          ? 'tool'
          : 'user'
  const content = msg.content
  if (typeof content === 'string') {
    return { role, content: [{ type: 'text', text: content }] }
  }
  if (Array.isArray(content)) {
    const blocks = content
      .map((block) => normalizeContentBlock(block))
      .filter((block): block is NormalizedBlock => block !== null)
    return { role, content: blocks }
  }
  return { role, content: [] }
}
</script>

<template>
  <div v-if="message && normalized" data-testid="trace-message-detail">
    <Section section-key="message.content" :title="t('trace.section.content')" :default-open="true">
      <MessageBlocks
        v-if="normalized.content.length > 0"
        :message="normalized"
      />
      <div v-else class="rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] px-3 py-3 text-xs text-[var(--color-text-tertiary)]">
        {{ t('trace.noData') }}
      </div>
    </Section>
    <Section section-key="message.raw" :title="t('trace.section.raw')">
      <CodeViewer :code="formatTraceJson(message.content)" language="json" :max-lines="48" show-line-numbers />
    </Section>
  </div>
</template>