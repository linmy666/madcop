<script setup lang="ts">
// v3.0 — LlmCallDetail (Vue 3)
// Direct translation of components/trace/detail/LlmCallDetail.tsx — same detail UI, same Tailwind classes.
import { computed, onMounted, onUnmounted, ref, watch, type Component } from 'vue'
import { useTranslation } from '../../../i18n'
import type { TraceBodySnapshot, TraceCallRecord } from '../../../types/trace'
import type { TraceSpan } from '../../../lib/traceViewModel'
import { formatTraceJson } from '../../../lib/traceViewModel'
import { fetchTraceCallDetail } from '../../../lib/trace/callCache'
import { parseTraceRequestBody, parseTraceResponseBody } from五级/lib/trace/requestParse'
import type { NormalizedMessage } from五级/lib/trace/types'
import { formatBytes } from五级/lib/formatBytes'
import CodeViewer from '../../chat/CodeViewer.vue'
import CopyButton from '../shared/CopyButton.vue'
import Section from './Section.vue'
import MessageBlocks from './MessageBlocks.vue'

const MESSAGE_FOLD_THRESHOLD = 20
const MESSAGE_HEAD_COUNT = 2
const MESSAGE_TAIL_COUNT = 6

export function isAbortedTraceCall(call: TraceCallRecord): boolean {
  if (call.metadata?.aborted === true) return true
  const name = call.error?.name
  return name === 'AbortError' || name === 'TimeoutError'
}

function stringifyParam(value: unknown): string {
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value) ?? 'null'
  } catch {
    return String(value)
  }
}

// ── Main component props/state ─────────────────────────────────────────────

const props = defineProps<{
  sessionId: string
  span: TraceSpan
}>()

const t = useTranslation()

const call = computed(() => props.span.call ?? null)
const callId = computed(() => call.value?.id ?? null)
const isTerminal = computed(() => props.span.status !== 'pending')

const detail = ref<TraceCallRecord | null>(null)
const fetchFailed = ref(false)
const fetchKeyRef = ref<string | null>(null)

async function fetchDetail() {
  if (!callId.value || !isTerminal.value) return
  const key = `${props.sessionId}:${callId.value}`
  if (fetchKeyRef.value === key) return
  fetchKeyRef.value = key
  try {
    const full = await fetchTraceCallDetail(props.sessionId, callId.value!)
    if (fetchKeyRef.value !== key) return
    if (full) {
      detail.value = full
      fetchFailed.value = false
    } else {
      fetchFailed.value = true
    }
  } catch {
    if (fetchKeyRef.value === key) fetchFailed.value = true
  }
}

onMounted(() => {
  fetchDetail()
})

let prevTerminal = isTerminal.value
watch(isTerminal, (v) => {
  if (v && !prevTerminal) fetchDetail()
  prevTerminal = v
})

onUnmounted(() => {
  // cleanup if needed
})

const effectiveCall = computed(() => {
  if (!call.value) return null
  if (detail.value && detail.value.id === callId.value) return detail.value
  return call.value
})

const parsed = computed(() => {
  const ec = effectiveCall.value
  if (!ec) return { request: null, response: null }
  return {
    request: ec.request.body.preview
      ? parseTraceRequestBody(ec.request.body.preview, ec.source)
      : null,
    response: ec.response?.body.preview
      ? parseTraceResponseBody(ec.response.body.preview, ec.source)
      : null,
  }
})

const loadingDetail = computed(() => {
  return isTerminal.value && (!detail.value || detail.value.id !== callId.value) && !fetchFailed.value
})

const requestParseFailed = computed(() => {
  const ec = effectiveCall.value
  if (!ec) return false
  return Boolean(ec.request.body.preview) && parsed.value.request === null
})

const responseParseFailed = computed(() => {
  const ec = effectiveCall.value
  if (!ec) return false
  return Boolean(ec.response?.body.preview) &&
    (parsed.value.response === null || parsed.value.response.message === null)
})

const legacyFallback = computed(() => {
  return !loadingDetail.value && (requestParseFailed.value || (isTerminal.value && !call.value?.error && responseParseFailed.value))
})

const paramEntries = computed(() => {
  const params = parsed.value.request?.params ?? {}
  return Object.entries(params)
})

</script>

<template>
  <div data-testid="trace-llm-detail" v-if="call && effectiveCall">
    <div
      v-if="loadingDetail"
      class="progress-indeterminate-track h-0.5 bg-[var(--color-surface-container)]"
      data-testid="trace-detail-loading"
    />
    <div
      v-if="fetchFailed"
      class="mx-4 mt-3 rounded-[var(--radius-md)] border border-[var(--color-warning)]/30 bg-[var(--color-warning-container)]/30 px-3 py-1.5 text-[11px] text-[var(--color-text-secondary)]"
    >
      {{ t('trace.detail.fetchFailed') }}
    </div>
    <div
      v-if="legacyFallback"
      class="mx-4 mt-3 rounded-[var(--radius-md)] border border-[var(--color-warning)]/30 bg-[var(--color-warning-container)]/30 px-3 py-1.5 text-[11px] text-[var(--color-text-secondary)]"
    >
      {{ t('trace.detail.legacyTruncated') }}
    </div>

    <Section section-key="llm.response" :title="t('trace.section.response')" :default-open="true">
      <ResponseContent
        :call="effectiveCall as TraceCallRecord"
        :pending="!isTerminal"
        :parsed-message="parsed.response?.message ?? null"
        :stop-reason="parsed.response?.stopReason"
      />
    </Section>

    <Section
      v-if="parsed.request && parsed.request.messages.length > 0"
      section-key="llm.messages"
      :title="t('trace.section.messages')"
      :badge="parsed.request.messages.length"
      :default-open="true"
    >
      <MessageList :messages="parsed.request.messages" />
    </Section>

    <Section
      v-if="parsed.request?.system"
      section-key="llm.systemPrompt"
      :title="t('trace.section.systemPrompt')"
      :badge="t('trace.detail.chars', { count: parsed.request.system.length })"
    >
      <template #actions>
        <CopyButton
          :text="parsed.request.system"
          :copied-label="t('common.copied')"
          class="rounded-[var(--radius-sm)] border border-[var(--color-border)] px-1.5 py-0.5 text-[10px] text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text-primary)]"
        />
      </template>
      <pre class="max-h-[400px] overflow-y-auto whitespace-pre-wrap break-words text-[11px] leading-5 text-[var(--color-text-secondary)]">
        {{ parsed.request.system }}
      </pre>
    </Section>

    <Section
      v-if="parsed.request && parsed.request.tools.length > 0"
      section-key="llm.tools"
      :title="t('trace.section.tools')"
      :badge="parsed.request.tools.length"
    >
      <ToolDefinitions :tools="parsed.request.tools" />
    </Section>

    <Section
      v-if="paramEntries.length > 0"
      section-key="llm.parameters"
      :title="t('trace.section.parameters')"
      :badge="paramEntries.length"
    >
      <dl class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-[11px]">
        <ParamRow v-for="[key, value] in paramEntries" :key="key" :name="key" :value="value" />
      </dl>
    </Section>

    <Section section-key="llm.raw" :title="t('trace.section.raw')" :default-open="legacyFallback">
      <RawBodies :call="effectiveCall as TraceCallRecord" />
    </Section>
  </div>
</template>

<!-- ── Sub-components (defined in same script block as exported const) ───── -->

<script lang="ts">
// ResponseContent
export const ResponseContent: Component = {
  name: 'ResponseContent',
  props: {
    call: Object as () => TraceCallRecord,
    pending: Boolean,
    parsedMessage: Object as () => NormalizedMessage | null,
    stopReason: String as () => string | undefined,
  },
  setup(props) {
    const t = useTranslation()
    return {
      t,
      isAborted: isAbortedTraceCall(props.call),
    }
  },
  template: `
    <div v-if="props.call.error" class="rounded-[var(--radius-md)] border border-[var(--color-error)]/25 bg-[var(--color-error-container)]/40 px-3 py-2" data-testid="trace-call-error">
      <div class="flex min-w-0 items-center gap-2">
        <div class="text-xs font-semibold text-[var(--color-error)]">{{ props.call.error.name }}</div>
        <span v-if="isAborted" class="inline-flex shrink-0 items-center rounded-[var(--radius-sm)] bg-[var(--color-error)]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-error)]" data-testid="trace-call-aborted-badge">
          {{ t('trace.status.aborted') }}
        </span>
      </div>
      <div class="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">{{ props.call.error.message }}</div>
      <div v-if="isAborted" class="mt-1 text-[11px] leading-4 text-[var(--color-text-tertiary)]">
        {{ t('trace.detail.aborted') }}
      </div>
      <details v-if="props.call.error.stack" class="mt-1.5">
        <summary class="cursor-pointer text-[10px] uppercase tracking-[0.08em] text-[var(--color-text-tertiary)]">stack</summary>
        <pre class="mt-1 max-h-[240px] overflow-y-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-4 text-[var(--color-text-tertiary)]">{{ props.call.error.stack }}</pre>
      </details>
    </div>
    <div v-else-if="props.pending" class="flex items-center gap-2 rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] px-3 py-3 text-xs text-[var(--color-text-tertiary)]">
      <span class="material-symbols-outlined animate-spin" style="fontVariationSettings: 'FILL' 0; font-size: 13px; line-height: 13px;">progress_activity</span>
      {{ t('trace.detail.streaming') }}
    </div>
    <div v-else-if="!props.parsedMessage" class="rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] px-3 py-3 text-xs text-[var(--color-text-tertiary)]">
      {{ props.call.response ? t('trace.detail.legacyTruncated') : t('trace.noResponse') }}
    </div>
    <div v-else class="flex flex-col gap-2">
      <MessageBlocks :message="props.parsedMessage as NormalizedMessage" />
      <div v-if="props.stopReason">
        <MetaChip :label="t('trace.detail.stopReason')" :value="props.stopReason" />
      </div>
    </div>
  `,
}

// MessageList
export const MessageList: Component = {
  name: 'MessageList',
  props: {
    messages: Array as () => NormalizedMessage[],
  },
  setup() {
    const showAll = ref(false)
    return { showAll }
  },
  template: `
    <div class="flex flex-col gap-2">
      <template v-if="showAll || props.messages.length <= 20">
        <MessageBlocks v-for="(msg, i) in props.messages" :key="i" :message="msg" />
      </template>
      <template v-else>
        <MessageBlocks v-for="(msg, i) in props.messages.slice(0, 2)" :key="'head-' + i" :message="msg" />
        <button
          type="button"
          @click="showAll = true"
          class="rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] px-3 py-1.5 text-[11px] text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text-primary)] active:scale-[0.98]"
        >
          Show {{ props.messages.length - 2 - 6 }} earlier messages
        </button>
        <MessageBlocks v-for="(msg, i) in props.messages.slice(props.messages.length - 6)" :key="'tail-' + i" :message="msg" />
      </template>
    </div>
  `,
}

// ToolDefinitions
export const ToolDefinitions: Component = {
  name: 'ToolDefinitions',
  props: {
    tools: Array as () => Array<{ name: string; description?: string; schema?: unknown }>,
  },
  setup() {
    const expanded = ref<string | null>(null)
    return { expanded, formatTraceJson }
  },
  computed: {
    active(): { name: string; description?: string; schema?: unknown } | undefined {
      return this.props.tools.find((tool: { name: string; description?: string; schema?: unknown }) => tool.name === this.expanded)
    },
  },
  template: `
    <div>
      <div class="flex flex-wrap gap-1">
        <button
          v-for="tool in props.tools"
          :key="tool.name"
          type="button"
          @click="expanded = expanded === tool.name ? null : tool.name"
          :aria-pressed="expanded === tool.name"
          :title="tool.description || undefined"
          :class="[
            'rounded-[var(--radius-sm)] border px-1.5 py-0.5 font-mono text-[10px] transition-colors',
            expanded === tool.name
              ? 'border-[var(--color-border-focus)] text-[var(--color-text-primary)]'
              : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
          ]"
        >
          {{ tool.name }}
        </button>
      </div>
      <div v-if="active" class="mt-2">
        <p v-if="active.description" class="mb-1.5 text-[11px] leading-5 text-[var(--color-text-secondary)]">{{ active.description }}</p>
        <CodeViewer :code="formatTraceJson(active.schema ?? null)" language="json" />
      </div>
    </div>
  `,
}

// ParamRow
export const ParamRow: Component = {
  name: 'ParamRow',
  props: {
    name: String,
    value: null as unknown as () => unknown,
  },
  setup() {
    return { stringifyParam }
  },
  template: `
    <>
      <dt class="font-mono text-[var(--color-text-tertiary)]">{{ name }}</dt>
      <dd class="min-w-0 truncate font-mono text-[var(--color-text-secondary)]" :title="stringifyParam(props.value)">{{ stringifyParam(props.value) }}</dd>
    </>
  `,
}

// RawBodies
export const RawBodies: Component = {
  name: 'RawBodies',
  props: {
    call: Object as () => TraceCallRecord,
  },
  setup() {
    const t = useTranslation()
    return { t }
  },
  template: `
    <div class="flex flex-col gap-3">
      <RawBody :title="t('trace.requestBody')" :body="props.call.request.body" :max-lines="80" />
      <RawHeaders :title="t('trace.requestHeaders')" :headers="props.call.request.headers" />
      <template v-if="props.call.response">
        <RawBody :title="t('trace.responseBody')" :body="props.call.response.body" :max-lines="80" />
        <RawHeaders :title="t('trace.responseHeaders')" :headers="props.call.response.headers" />
      </template>
    </div>
  `,
}

// RawBody
export const RawBody: Component = {
  name: 'RawBody',
  props: {
    title: String,
    body: Object as () => TraceBodySnapshot,
    maxLines: Number,
  },
  setup() {
    const t = useTranslation()
    return { t, formatBytes, formatTraceJson }
  },
  computed: {
    code(): string | null {
      const body = this.props.body
      if (!body.preview) return null
      return body.contentType === 'json' ? formatTraceJson(body.preview) : body.preview
    },
  },
  template: `
    <div>
      <div class="mb-1 flex items-center justify-between gap-2">
        <span class="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--color-text-tertiary)]">{{ title }}</span>
        <span class="font-mono text-[10px] text-[var(--color-text-tertiary)]">
          {{ formatBytes(props.body.bytes) }}{{ props.body.truncated ? ' · ' + t('trace.truncatedShort') : '' }}
        </span>
      </div>
      <CodeViewer v-if="code" :code="code" :language="props.body.contentType === 'json' ? 'json' : 'text'" />
      <div v-else class="rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] px-3 py-2 text-[11px] text-[var(--color-text-tertiary)]">
        {{ t('trace.noData') }}
      </div>
    </div>
  `,
}

// RawHeaders
export const RawHeaders: Component = {
  name: 'RawHeaders',
  props: {
    title: String,
    headers: Object as () => Record<string, string>,
  },
  setup() {
    return { formatTraceJson }
  },
  template: `
    <div>
      <div class="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--color-text-tertiary)]">{{ title }}</div>
      <CodeViewer :code="formatTraceJson(props.headers)" language="json" />
    </div>
  `,
}

// MetaChip
export const MetaChip: Component = {
  name: 'MetaChip',
  props: {
    label: String,
    value: String,
  },
  template: `
    <span class="inline-flex items-center gap-1 rounded-[var(--radius-sm)] border border-[var(--color-border)] px-1.5 py-0.5 text-[10px] font-mono text-[var(--color-text-tertiary)]">
      <span class="text-[var(--color-text-secondary)]">{{ label }}:</span>
      <span class="text-[var(--color-text-primary)]">{{ value }}</span>
    </span>
  `,
}
</script>
