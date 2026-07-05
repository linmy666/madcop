<!--
  v3.0 — TraceSession (Vue 3 SFC)
  Full translation of src/pages/TraceSession.tsx (496 lines).
  Trace viewer with polling, split layout, diagnosis banner, error/retry states.
  Props-driven: sessionId, standalone, pollIntervalMs.
-->
<script setup lang="ts">
import {
  ref,
  computed,
  onMounted,
  onBeforeUnmount,
  watch,
} from 'vue'
import { sessionsApi } from '../../api/sessions'
import { useSessionStore } from '../stores/sessionStore'
import { useTranslation, formatTokenCount } from '../../i18n'
import { buildTraceViewModel, type TraceSpan, type TraceViewModel } from '../../lib/traceViewModel'
import { getDesktopHost } from '../../lib/desktopHost'
import { buildTraceWindowUrl } from '../../lib/traceLaunch'
import { formatClockTime, formatDurationMs } from '../../lib/trace/formatters'
import type { MessageEntry } from '../../types/session'
import type { TraceSession as TraceSessionData } from '../../types/trace'
import TraceTree from '../components/trace/TraceTree.vue'
import TraceDetail from '../trace/TraceDetail.vue'
import TraceSplitLayout from '../components/trace/TraceSplitLayout.vue'
import { iconForSpanKind, statusBadge } from '../trace/TraceBadges'

const TRACE_POLL_INTERVAL_MS = 1500

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; trace: TraceSessionData; messages: MessageEntry[] }

const props = withDefaults(defineProps<{
  sessionId: string
  standalone?: boolean
  pollIntervalMs?: number
}>(), {
  standalone: false,
  pollIntervalMs: TRACE_POLL_INTERVAL_MS,
})

const t = useTranslation()
const sessionStore = useSessionStore()

const state = ref<LoadState>({ status: 'loading' })
const selectedId = ref<string | null>(null)
const refreshNonce = ref(0)
const lastLoadedAt = ref<string | null>(null)
const refreshing = ref(false)
const clockNowMs = ref(Date.now())
const snapshotSignature = ref<string | null>(null)
const lastSpanId = ref<string | null>(null)
const pollingTimer = ref<ReturnType<typeof setInterval> | null>(null)
const clockTimer = ref<ReturnType<typeof setInterval> | null>(null)

function refresh() {
  refreshNonce.value++
}

function openWindow() {
  const host = getDesktopHost()
  if (host.trace) {
    host.trace.openWindow(props.sessionId)
    return
  }
  window.open(buildTraceWindowUrl(props.sessionId), '_blank', 'noopener,noreferrer')
}

const readyState = computed(() =>
  state.value.status === 'ready' ? state.value : null,
)

const viewModel = computed<TraceViewModel | null>(() => {
  if (!readyState.value) return null
  return buildTraceViewModel(readyState.value.trace, readyState.value.messages, {
    now: new Date(clockNowMs.value).toISOString(),
  })
})

function traceSnapshotSignature(trace: TraceSessionData, messages: MessageEntry[]): string {
  return JSON.stringify({
    summary: trace.summary,
    calls: trace.calls.map((call) => ({
      id: call.id,
      status: call.status,
      completedAt: call.completedAt,
      durationMs: call.durationMs,
      usage: call.usage,
      responseStatus: call.response?.status,
      requestSha256: call.request.body.sha256,
      responseSha256: call.response?.body.sha256,
      error: call.error
        ? { name: call.error.name, message: call.error.message, code: call.error.code }
        : null,
    })),
    events: (trace.events ?? []).map((event) => ({
      id: event.id,
      timestamp: event.timestamp,
      phase: event.phase,
      severity: event.severity,
      callId: event.callId,
      message: event.message,
    })),
    messages: messages.map((message) => ({
      id: message.id,
      type: message.type,
      timestamp: message.timestamp,
      content: message.content,
    })),
  })
}

function isTraceSessionData(value: unknown): value is TraceSessionData {
  return (
    !!value &&
    typeof value === 'object' &&
    'sessionId' in value &&
    'summary' in value &&
    Array.isArray((value as { calls?: unknown }).calls)
  )
}

async function load(silent: boolean) {
  if (!silent) state.value = { status: 'loading' }
  if (silent) refreshing.value = true
  try {
    const [trace, messageResponse] = await Promise.all([
      sessionsApi.getTrace(props.sessionId),
      sessionsApi.getMessages(props.sessionId).catch(() => ({ messages: [] })),
    ])
    if (!isTraceSessionData(trace)) {
      throw new Error(t('trace.snapshotEmpty'))
    }
    const signature = traceSnapshotSignature(trace, messageResponse.messages)
    if (silent && snapshotSignature.value === signature) return
    snapshotSignature.value = signature
    state.value = { status: 'ready', trace, messages: messageResponse.messages }
    clockNowMs.value = Date.now()
    lastLoadedAt.value = new Date().toISOString()
  } catch (error) {
    if (!silent) {
      state.value = {
        status: 'error',
        message: error instanceof Error ? error.message : String(error),
      }
    }
  } finally {
    refreshing.value = false
  }
}

function startPolling() {
  stopPolling()
  pollingTimer.value = setInterval(() => {
    void load(true)
  }, props.pollIntervalMs)
}

function stopPolling() {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

function startClock() {
  stopClock()
  if (viewModel.value && viewModel.value.diagnosis.pendingModelCalls > 0) {
    clockTimer.value = setInterval(() => {
      clockNowMs.value = Date.now()
    }, 1000)
  }
}

function stopClock() {
  if (clockTimer.value) {
    clearInterval(clockTimer.value)
    clockTimer.value = null
  }
}

function resetSelection() {
  selectedId.value = null
  lastSpanId.value = null
  snapshotSignature.value = null
}

onMounted(() => {
  resetSelection()
  void load(false)
  startPolling()
})

onBeforeUnmount(() => {
  stopPolling()
  stopClock()
})

// Reload when sessionId or refreshNonce changes
watch([() => props.sessionId, refreshNonce], () => {
  resetSelection()
  stopPolling()
  void load(false)
  startPolling()
}, { immediate: false })

// Auto-select last span (follow live tail)
watch(viewModel, (vm) => {
  if (!vm) return
  const lastSpanIdVal = vm.orderedSpanIds.at(-1) ?? null
  const current = selectedId.value
  if (current && current === lastSpanId.value && lastSpanIdVal && current !== lastSpanIdVal) {
    lastSpanId.value = lastSpanIdVal
    selectedId.value = lastSpanIdVal
    return
  }
  lastSpanId.value = lastSpanIdVal
  if (current && vm.spansById.has(current)) return
  selectedId.value = vm.rootId
})

// Start/stop live clock based on pending calls
watch(
  () => viewModel.value?.diagnosis,
  (diagnosis) => {
    if (diagnosis && diagnosis.pendingModelCalls > 0) {
      startClock()
    } else {
      stopClock()
    }
  },
)

const sessionTitle = computed(() => {
  return sessionStore.sessions.find((session) => session.id === props.sessionId)?.title
})

const resolvedTitle = computed(() => {
  if (state.value.status !== 'ready') return sessionTitle.value ?? t('session.untitled')
  return sessionTitle.value ?? state.value.trace.session?.title ?? t('session.untitled')
})

const activeSpan = computed<TraceSpan | null>(() => {
  if (!viewModel.value) return null
  const selected = selectedId.value ? viewModel.value.spansById.get(selectedId.value) : undefined
  return selected ?? viewModel.value.spansById.get(viewModel.value.rootId) ?? viewModel.value.spans[0] ?? null
})

const hasTraceContent = computed(() => {
  if (state.value.status !== 'ready') return false
  const { trace, messages } = state.value
  return trace.calls.length > 0 || (trace.events?.length ?? 0) > 0 || messages.length > 0
})

function onSelect(spanId: string) {
  selectedId.value = spanId
}

function diagnosisReasonLabel(reason: TraceViewModel['diagnosis']['reason']): string {
  switch (reason) {
    case 'model_error': return t('trace.diagnosis.modelError')
    case 'tool_error': return t('trace.diagnosis.toolError')
    case 'event_error': return t('trace.diagnosis.eventError')
    case 'pending_model': return t('trace.diagnosis.pendingModel')
    case 'pending_tool': return t('trace.diagnosis.pendingTool')
    case 'waiting_for_agent': return t('trace.diagnosis.waitingForAgent')
    case 'empty': return t('trace.diagnosis.empty')
    default: return t('trace.diagnosis.healthy')
  }
}

function spanDisplayTitle(span: TraceSpan): string {
  if (span.kind === 'llm') return span.title || t('trace.kind.llm')
  if (span.kind === 'tool') return span.title || t('trace.kind.tool')
  if (span.kind === 'tool_result') return span.title || t('trace.kind.toolResult')
  if (span.kind === 'turn') return span.title || t('trace.kind.turn')
  if (span.kind === 'session') return span.title || t('trace.kind.session')
  if (span.kind === 'event') return span.title || t('trace.kind.event')
  if (span.kind === 'message') return span.title || t('trace.kind.message')
  return span.title || ''
}

async function copySessionId() {
  try {
    await navigator.clipboard.writeText(props.sessionId)
  } catch {
    // clipboard not available
  }
}

const summary = computed(() => {
  if (state.value.status !== 'ready') return null
  return state.value.trace.summary
})

const diagnosisStatus = computed(() => viewModel.value?.diagnosis.status)

// Evidence spans for diagnosis banner
const evidenceSpans = computed<TraceSpan[]>(() => {
  if (!viewModel.value) return []
  const { diagnosis } = viewModel.value
  if (diagnosis.status !== 'attention' && diagnosis.status !== 'blocked') return []
  return diagnosis.evidenceSpanIds
    .map((spanId) => viewModel.value!.spansById.get(spanId))
    .filter((s): s is TraceSpan => !!s)
    .slice(0, 3)
})
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col bg-[var(--color-surface)] text-[var(--color-text-primary)]">
    <!-- ─── Loading ───────────────────────────────────────────── -->
    <template v-if="state.status === 'loading'">
      <!-- Header -->
      <header class="flex shrink-0 items-center justify-between gap-3 px-4 py-2.5" data-testid="trace-header">
        <div class="flex min-w-0 items-center gap-2.5">
          <span class="material-symbols-outlined shrink-0 text-[var(--color-text-tertiary)] text-base">radio</span>
          <div class="min-w-0">
            <div class="flex min-w-0 items-center gap-2">
              <h1 class="min-w-0 truncate text-sm font-semibold tracking-tight text-[var(--color-text-primary)]">
                {{ sessionTitle || t('session.untitled') }}
              </h1>
              <span class="inline-flex items-center gap-1 rounded-[var(--radius-sm)] border border-[var(--color-success)]/25 bg-[var(--color-success)]/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-success)]">
                <span class="h-1.5 w-1.5 rounded-full bg-[var(--color-success)] animate-pulse" aria-hidden="true" />
                <span class="material-symbols-outlined text-sm" style="fontVariationSettings: 'FILL' 1">radio</span>
                Live
              </span>
            </div>
            <div class="mt-0.5 flex min-w-0 items-center gap-2 font-mono text-[10px] text-[var(--color-text-tertiary)]">
              <span class="max-w-[280px] truncate">{{ sessionId }}</span>
              <span v-if="lastLoadedAt" class="shrink-0">
                {{ t('trace.updatedAt') }} {{ formatClockTime(lastLoadedAt) }}
              </span>
            </div>
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            aria-label="{{ t('trace.copySessionId') }}"
            title="{{ t('trace.copySessionId') }}"
            @click="copySessionId"
            class="inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-border-focus)] hover:text-[var(--color-text-primary)] active:scale-[0.98]"
          >
            <span class="material-symbols-outlined text-base">content_copy</span>
          </button>
          <button
            type="button"
            aria-label="{{ t('trace.refresh') }}"
            title="{{ t('trace.refresh') }}"
            @click="refresh"
            class="inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-border-focus)] hover:text-[var(--color-text-primary)] active:scale-[0.98]"
          >
            <span :class="['material-symbols-outlined text-base', refreshing ? 'animate-spin' : '']">refresh</span>
          </button>
          <button
            v-if="!standalone"
            type="button"
            aria-label="{{ t('trace.openWindow') }}"
            title="{{ t('trace.openWindow') }}"
            @click="openWindow"
            class="inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-border-focus)] hover:text-[var(--color-text-primary)] active:scale-[0.98]"
          >
            <span class="material-symbols-outlined text-base">open_in_new</span>
          </button>
        </div>
      </header>
      <!-- Skeleton -->
      <div class="flex min-h-0 flex-1 flex-col border-t border-[var(--color-border)] lg:flex-row" data-testid="trace-skeleton">
        <div class="shrink-0 border-b border-[var(--color-border)] p-3 lg:w-[380px] lg:border-b-0 lg:border-r">
          <div class="h-7 animate-pulse rounded-[var(--radius-md)] bg-[var(--color-surface-container)]" />
          <div class="mt-3 space-y-1.5">
            <div
              v-for="(_, index) in 10"
              :key="index"
              class="h-[34px] animate-pulse rounded-[var(--radius-sm)] bg-[var(--color-surface-container)]"
            />
          </div>
        </div>
        <div class="min-w-0 flex-1 p-4">
          <div class="h-5 w-64 animate-pulse rounded bg-[var(--color-surface-container)]" />
          <div class="mt-2 h-3 w-96 animate-pulse rounded bg-[var(--color-surface-container)]" />
          <div class="mt-5 space-y-3">
            <div
              v-for="(_, index) in 4"
              :key="index"
              class="h-24 animate-pulse rounded-[var(--radius-md)] bg-[var(--color-surface-container)]"
            />
          </div>
        </div>
      </div>
    </template>

    <!-- ─── Error ─────────────────────────────────────────────── -->
    <template v-else-if="state.status === 'error'">
      <!-- Header (same as loading) -->
      <header class="flex shrink-0 items-center justify-between gap-3 px-4 py-2.5" data-testid="trace-header">
        <div class="flex min-w-0 items-center gap-2.5">
          <span class="material-symbols-outlined shrink-0 text-[var(--color-text-tertiary)] text-base">radio</span>
          <div class="min-w-0">
            <div class="flex min-w-0 items-center gap-2">
              <h1 class="min-w-0 truncate text-sm font-semibold tracking-tight text-[var(--color-text-primary)]">
                {{ sessionTitle || t('session.untitled') }}
              </h1>
              <span class="inline-flex items-center gap-1 rounded-[var(--radius-sm)] border border-[var(--color-success)]/25 bg-[var(--color-success)]/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-success)]">
                <span class="h-1.5 w-1.5 rounded-full bg-[var(--color-success)] animate-pulse" aria-hidden="true" />
                <span class="material-symbols-outlined text-sm" style="fontVariationSettings: 'FILL' 1">radio</span>
                Live
              </span>
            </div>
            <div class="mt-0.5 flex min-w-0 items-center gap-2 font-mono text-[10px] text-[var(--color-text-tertiary)]">
              <span class="max-w-[280px] truncate">{{ sessionId }}</span>
              <span v-if="lastLoadedAt" class="shrink-0">
                {{ t('trace.updatedAt') }} {{ formatClockTime(lastLoadedAt) }}
              </span>
            </div>
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            aria-label="{{ t('trace.copySessionId') }}"
            title="{{ t('trace.copySessionId') }}"
            @click="copySessionId"
            class="inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-border-focus)] hover:text-[var(--color-text-primary)] active:scale-[0.98]"
          >
            <span class="material-symbols-outlined text-base">content_copy</span>
          </button>
          <button
            type="button"
            aria-label="{{ t('trace.refresh') }}"
            title="{{ t('trace.refresh') }}"
            @click="refresh"
            class="inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-border-focus)] hover:text-[var(--color-text-primary)] active:scale-[0.98]"
          >
            <span :class="['material-symbols-outlined text-base', refreshing ? 'animate-spin' : '']">refresh</span>
          </button>
          <button
            v-if="!standalone"
            type="button"
            aria-label="{{ t('trace.openWindow') }}"
            title="{{ t('trace.openWindow') }}"
            @click="openWindow"
            class="inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-border-focus)] hover:text-[var(--color-text-primary)] active:scale-[0.98]"
          >
            <span class="material-symbols-outlined text-base">open_in_new</span>
          </button>
        </div>
      </header>
      <!-- Error content -->
      <div class="flex flex-1 items-center justify-center p-8">
        <div class="max-w-md border-t border-[var(--color-error)]/30 pt-5">
          <div class="flex items-center gap-2 text-sm font-semibold text-[var(--color-error)]">
            <span class="material-symbols-outlined text-base">warning</span>
            {{ t('trace.loadFailed') }}
          </div>
          <p class="mt-2 text-sm text-[var(--color-text-secondary)]">{{ state.message }}</p>
          <button
            type="button"
            @click="refresh"
            class="mt-4 inline-flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold text-[var(--color-text-primary)] transition-transform active:scale-[0.98]"
          >
            <span class="material-symbols-outlined text-base">refresh</span>
            {{ t('common.retry') }}
          </button>
        </div>
      </div>
    </template>

    <!-- ─── Ready ─────────────────────────────────────────────── -->
    <template v-else>
      <!-- Header with summary -->
      <header class="flex shrink-0 items-center justify-between gap-3 px-4 py-2.5" data-testid="trace-header">
        <div class="flex min-w-0 items-center gap-2.5">
          <span class="material-symbols-outlined shrink-0 text-[var(--color-text-tertiary)] text-base">radio</span>
          <div class="min-w-0">
            <div class="flex min-w-0 items-center gap-2">
              <h1 class="min-w-0 truncate text-sm font-semibold tracking-tight text-[var(--color-text-primary)]">
                {{ resolvedTitle }}
              </h1>
              <span class="inline-flex items-center gap-1 rounded-[var(--radius-sm)] border border-[var(--color-success)]/25 bg-[var(--color-success)]/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-success)]">
                <span class="h-1.5 w-1.5 rounded-full bg-[var(--color-success)] animate-pulse" aria-hidden="true" />
                <span class="material-symbols-outlined text-sm" style="fontVariationSettings: 'FILL' 1">radio</span>
                Live
              </span>
              <span
                v-if="diagnosisStatus"
                :class="[
                  'h-1.5 w-1.5 shrink-0 rounded-full',
                  diagnosisStatus === 'blocked'
                    ? 'bg-[var(--color-error)]'
                    : diagnosisStatus === 'attention'
                    ? 'bg-[var(--color-warning)]'
                    : 'bg-[var(--color-success)]',
                ]"
                aria-hidden="true"
              />
            </div>
            <div class="mt-0.5 flex min-w-0 items-center gap-2 font-mono text-[10px] text-[var(--color-text-tertiary)]">
              <span class="max-w-[280px] truncate">{{ sessionId }}</span>
              <span v-if="lastLoadedAt" class="shrink-0">
                {{ t('trace.updatedAt') }} {{ formatClockTime(lastLoadedAt) }}
              </span>
            </div>
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-3">
          <!-- Summary chips -->
          <div v-if="summary" class="hidden items-center gap-3 md:flex">
            <span class="inline-flex items-baseline gap-1.5">
              <span class="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)]">{{ t('trace.apiCalls') }}</span>
              <span class="font-mono text-[13px] text-[var(--color-text-primary)]">{{ String(summary.apiCalls) }}</span>
            </span>
            <span v-if="summary.failedCalls > 0" class="inline-flex items-baseline gap-1.5">
              <span class="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)]">{{ t('trace.failedCalls') }}</span>
              <span class="font-mono text-[13px] text-[var(--color-error)]">{{ String(summary.failedCalls) }}</span>
            </span>
            <span class="inline-flex items-baseline gap-1.5">
              <span class="text-[10px] font密封圈 uppercase tracking-wide text-[var(--color-text-tertiary)]">{{ t('trace.modelTime') }}</span>
              <span class="font-mono text-[13px] text-[var(--color-text-primary)]">{{ formatDurationMs(summary.totalDurationMs) }}</span>
            </span>
            <span class="inline-flex items-baseline gap-1.5">
              <span class="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)]">{{ t('trace.tokens') }}</span>
              <span class="font-mono text-[13px] text-[var(--color-text-primary)]">{{ formatTokenCount(summary.totalInputTokens + summary.totalOutputTokens) }}</span>
            </span>
            <span v-if="summary.models.length > 0" class="inline-flex items-baseline gap-1.5">
              <span class="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)]">{{ t('trace.models') }}</span>
              <span class="font-mono text-[13px] text-[var(--color-text-primary)]">
                {{ summary.models.map((m: any) => `${m.model} x${m.calls}`).join(', ') }}
              </span>
            </span>
          </div>
          <!-- Actions -->
          <div class="flex items-center gap-1.5">
            <button
              type="button"
              :aria-label="t('trace.copySessionId')"
              :title="t('trace.copySessionId')"
              @click="copySessionId"
              class="inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-border-focus)] hover:text-[var(--color-text-primary)] active:scale-[0.98]"
            >
              <span class="material-symbols-outlined text-base">content_copy</span>
            </button>
            <button
              type="button"
              :aria-label="t('trace.refresh')"
              :title="t('trace.refresh')"
              @click="refresh"
              class="inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-border-focus)] hover:text-[var(--color-text-primary)] active:scale>[0.98]"
            >
              <span :class="['material-symbols-outlined text-base', refreshing ? 'animate-spin' : '']">refresh</span>
            </button>
            <button
              v-if="!standalone"
              type="button"
              :aria-label="t('trace.openWindow')"
              :title="t('trace.openWindow')"
              @click="openWindow"
              class="inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] text-[var(--color-text-secondary)] transition-colors hover:border>[var(--color-border-focus)] hover:text>[var(--color-text-primary)] active:scale>[0.98]"
            >
              <span class="material-symbols-outlined text-base">open_in_new</span>
            </button>
          </div>
        </div>
      </header>

      <!-- Diagnosis banner -->
      <section
        v-if="viewModel && (viewModel.diagnosis.status === 'attention' || viewModel.diagnosis.status === 'blocked')"
        :class="[
          'flex shrink-0 items-center gap-2 border-t px-4 py-1.5',
          viewModel.diagnosis.status === 'blocked'
            ? 'border-[var(--color-error)]/30 bg-[var(--color-error-container)]/30'
            : 'border-[var(--color-warning)]/30 bg-[var(--color-warning-container)]/25',
        ]"
        data-testid="trace-diagnosis"
      >
        <span
          :class="[
            'inline-flex items-center gap-1 rounded>[var(--radius-sm)] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
            viewModel.diagnosis.status === 'blocked'
              ? 'border border-[var(--color-error)]/25 bg-[var(--color-error)]/10 text-[var(--color-error)]'
              : 'border border>[var(--color-warning)]/25 bg>[var(--color-warning)]/10 text>[var(--color-warning)]',
          ]"
        >
          <span class="material-symbols-outlined text-sm">
            {{ viewModel.diagnosis.status === 'blocked' ? 'error' : 'pending' }}
          </span>
          {{ viewModel.diagnosis.status === 'blocked' ? 'error' : 'pending' }}
        </span>
        <span class="min-w-0 truncate text-xs font-semibold text>[var(--color-text-primary)]">
          {{ diagnosisReasonLabel(viewModel.diagnosis.reason) }}
        </span>
        <button
          v-if="viewModel.diagnosis.focusSpanId && viewModel.spansById.has(viewModel.diagnosis.focusSpanId!)"
          type="button"
          @click="onSelect(viewModel.diagnosis.focusSpanId!)"
          class="shrink-0 rounded>[var(--radius-sm)] border border>[var(--color-border)] bg>[var(--color-surface)] px-2 py-0.5 text-[11px] text>[var(--color-text-secondary)] transition-colors hover:border>[var(--color-border-focus)] hover:text>[var(--color-text-primary)] active:scale>[0.98]"
        >
          {{ t('trace.focus') }}
        </button>
        <div class="ml-auto flex min-w-0 items-center justify-end gap-1.5 overflow-hidden">
          <button
            v-for="span in evidenceSpans"
            :key="span.id"
            type="button"
            @click="onSelect(span.id)"
            class="inline-flex max-w>[200px] items-center gap-1.5 rounded>[var(--radius-sm)] border border>[var(--color-border)] bg>[var(--color-surface)] px-2 py-0.5 text>[11px] text>[var(--color-text-secondary)] transition-colors hover:border>[var(--color-border-focus)] hover:text>[var(--color-text-primary)] active:scale>[0.98]"
          >
            <span
              :class="[
                'material-symbols-outlined text-sm',
                iconForSpanKind(span.kind, span.status).color === 'var(--color-error)'
                  ? 'text-[var(--color-error)]'
                  : iconForSpanKind(span.kind, span.status).color === 'var(--color-warning)'
                  ? 'text-[var(--color-warning)]'
                  : 'text>[var(--color-text-tertiary)]',
              ]"
            >
              {{ iconForSpanKind(span.kind, span.status).icon }}
            </span>
            <span class="truncate">{{ spanDisplayTitle(span) }}</span>
          </button>
        </div>
      </section>

      <!-- Trace split layout -->
      <div
        v-if="hasTraceContent && activeSpan && viewModel"
        class="flex min-h-0 flex-1 flex-col border-t border>[var(--color-border)]"
      >
        <TraceSplitLayout
          :tree="
            <TraceTree
              :view-model=\"viewModel!\"
              :selected-id=\"activeSpan!.id\"
              @select=\"onSelect\"
            />
          "
          :detail="
            <TraceDetail
              :span=\"activeSpan!\"
              :view-model=\"viewModel!\"
              :session-id=\"sessionId\"
              @select=\"onSelect\"
            />
          "
        />
      </div>

      <!-- Empty trace -->
      <div
        v-else
        class="flex flex-1 items-center justify-center border-t border>[var(--color-border)] p-8"
      >
        <div class="max-w-sm rounded>[var(--radius-md)] border border-dashed border>[var(--color-border)] px-6 py-8 text-center">
          <span class="material-symbols-outlined text>[var(--color-text-tertiary)] text-2xl mx-auto">radio</span>
          <h2 class="mt-3 text-sm font-semibold text>[var(--color-text-primary)]">
            {{ t('trace.emptyTitle') }}
          </h2>
          <p class="mt-2 text-sm leading-6 text>[var(--color-text-secondary)]">
            {{ t('trace.emptyBody') }}
          </p>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* Tailwind-only styling — no scoped CSS rules needed */
</style>
