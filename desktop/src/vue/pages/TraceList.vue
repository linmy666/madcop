<!--
  v3.0 — TraceList (Vue 3 SFC)
  Full translation of src/pages/TraceList.tsx (433 lines).
  Trace session list with search, pagination, polling, summary chips.
-->
<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { tracesApi } from '../../api/traces'
import { SETTINGS_TAB_ID, useTabStore } from '../../stores/tabStore'
import { useUIStore } from '../../stores/uiStore'
import { useTranslation } from '../../i18n'
import { getDesktopHost } from '../../lib/desktopHost'
import type { TraceSessionList, TraceSessionListItem } from '../../types/trace'

const POLL_MS = 5_000
const PAGE_SIZE = 50
const SEARCH_DEBOUNCE_MS = 250
const MAX_MODEL_CHIPS = 2

type TraceListState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: TraceSessionList }

const t = useTranslation()

const state = ref<TraceListState>({ status: 'loading' })
const queryInput = ref('')
const query = ref('')
const isLoadingMore = ref(false)
const pollTimer = ref<ReturnType<typeof setInterval> | null>(null)

const host = computed(() => getDesktopHost())

// ── Debounced search input ──────────────────────────────────────────
let debounceTimer: ReturnType<typeof setTimeout> | null = null
watch(queryInput, (val) => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    query.value = val.trim()
  }, SEARCH_DEBOUNCE_MS)
})

// ── Load (initial + append + refresh) ───────────────────────────────
function loadTrace(options?: {
  append?: boolean
  limit?: number
  offset?: number
  silent?: boolean
}) {
  const append = options?.append === true
  const offset = options?.offset ?? 0
  const limit = options?.limit ?? PAGE_SIZE

  if (append) {
    isLoadingMore.value = true
  } else if (!options?.silent) {
    state.value = { status: 'loading' }
  }

  tracesApi
    .list({ limit, offset, query: query.value })
    .then((data) => {
      const prev = state.value
      if (!append || prev.status !== 'ready') {
        state.value = { status: 'ready', data }
      } else {
        state.value = {
          status: 'ready',
          data: {
            ...data,
            traces: [...prev.data.traces, ...data.traces],
          },
        }
      }
    })
    .catch((error) => {
      state.value = {
        status: 'error',
        message: error instanceof Error ? error.message : t('trace.list.loadFailed'),
      }
    })
    .finally(() => {
      if (append) isLoadingMore.value = false
    })
}

// ── Summary ─────────────────────────────────────────────────────────
const summary = computed(() => {
  if (state.value.status !== 'ready') return { apiCalls: 0, failedCalls: 0, models: 0 }
  const modelNames = new Set<string>()
  let apiCalls = 0
  let failedCalls = 0
  for (const item of state.value.data.traces) {
    apiCalls += item.summary.apiCalls
    failedCalls += item.summary.failedCalls
    for (const model of item.summary.models) modelNames.add(model.model)
  }
  return { apiCalls, failedCalls, models: modelNames.size }
})

// ── Lifecycle ───────────────────────────────────────────────────────
let initialLoadDone = false

onMounted(() => {
  loadTrace()
  initialLoadDone = true
})

watch(query, () => {
  if (initialLoadDone) loadTrace()
})

watch(
  () => state.value,
  (newState) => {
    if (pollTimer.value) {
      clearInterval(pollTimer.value)
      pollTimer.value = null
    }
    if (newState.status !== 'ready' || !newState.data.settings.enabled) return
    pollTimer.value = setInterval(() => {
      loadTrace({
        limit: Math.max(PAGE_SIZE, newState.data.traces.length),
        silent: true,
      })
    }, POLL_MS)
  },
  { deep: true },
)

onBeforeUnmount(() => {
  if (pollTimer.value) clearInterval(pollTimer.value)
  if (debounceTimer) clearTimeout(debounceTimer)
})

// ── Actions ─────────────────────────────────────────────────────────
function openTrace(sessionId: string, title: string) {
  useTabStore.getState().openTraceTab(sessionId, `${t('trace.title')}: ${title}`)
}

function openTraceSettings() {
  useUIStore.getState().setPendingSettingsTab('general')
  useTabStore.getState().openTab(SETTINGS_TAB_ID, t('sidebar.settings'), 'settings')
}

function handleRowKeydown(e: KeyboardEvent, trace: TraceSessionListItem) {
  if (e.key !== 'Enter' && e.key !== ' ') return
  e.preventDefault()
  openTrace(trace.sessionId, trace.session?.title || t('session.untitled'))
}

function handleLoadMore() {
  if (state.value.status === 'ready') {
    loadTrace({ append: true, offset: state.value.data.traces.length, silent: true })
  }
}

// ── Helpers ─────────────────────────────────────────────────────────
/** `madcop-sonnet-4-5-20250929` -> `sonnet-4-5`; non-Claude ids pass through. */
function shortModelName(model: string): string {
  const short = model.replace(/^claude-/i, '').replace(/-\d{8}$/, '')
  return short || model
}

/** Compact count: 847 -> "847", 1234 -> "1.2k", 2345678 -> "2.3m". */
function formatCompact(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '0'
  if (value < 1000) return String(value)
  const scaled = value < 1_000_000 ? value / 1000 : value / 1_000_000
  const unit = value < 1_000_000 ? 'k' : 'm'
  const text = scaled >= 100 ? String(Math.round(scaled)) : scaled.toFixed(1).replace(/\.0$/, '')
  return `${text}${unit}`
}

function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return '-'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatUpdatedAt(value: string | null): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString()
}
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col bg-[var(--color-surface)]">
    <header class="shrink-0 border-b border-[var(--color-border)] px-5 py-4">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)]">
            <span class="material-symbols-outlined text-sm" aria-hidden="true">workflow</span>
            <span>{{ t('trace.list.eyebrow') }}</span>
          </div>
          <div class="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
            <h1 class="text-lg font-semibold tracking-tight text-[var(--color-text-primary)]">{{ t('trace.list.title') }}</h1>
            <span
              v-if="state.status === 'ready'"
              :class="[
                'rounded-[var(--radius-sm)] border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                state.data.settings.enabled
                  ? 'border-[var(--color-success)]/25 bg-[var(--color-success)]/10 text-[var(--color-success)]'
                  : 'border-[var(--color-border)] bg-[var(--color-surface-container-low)] text-[var(--color-text-tertiary)]'
              ]"
            >
              {{ state.data.settings.enabled ? t('trace.list.collecting') : t('trace.list.paused') }}
            </span>
            <span
              v-if="state.status === 'ready'"
              class="min-w-0 max-w-full truncate font-mono text-[11px] text-[var(--color-text-tertiary)]"
              :title="state.data.storageDir"
            >
              {{ state.data.storageDir }}
            </span>
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <button
            type="button"
            class="inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface-container)] px-3 text-xs font-medium text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-surface-hover)] active:scale-[0.98]"
            @click="openTraceSettings"
          >
            {{ t('trace.list.settings') }}
          </button>
          <button
            type="button"
            class="inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface-container)] px-3 text-xs font-medium text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-surface-hover)] active:scale-[0.98]"
            @click="loadTrace"
          >
            <span class="material-symbols-outlined text-sm" aria-hidden="true">refresh</span>
            {{ t('trace.refresh') }}
          </button>
        </div>
      </div>

      <!-- Meta chips -->
      <div class="mt-3 flex flex-wrap items-baseline gap-x-5 gap-y-1.5">
        <div class="flex items-baseline gap-1.5">
          <span class="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)]">{{ t('trace.list.sessions') }}</span>
          <span class="font-mono text-[13px] text-[var(--color-text-primary)]">{{ state.status === 'ready' ? String(state.data.total) : '-' }}</span>
        </div>
        <div class="flex items-baseline gap-1.5">
          <span class="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)]">{{ t('trace.apiCalls') }}</span>
          <span class="font-mono text-[13px] text-[var(--color-text-primary)]">{{ String(summary.apiCalls) }}</span>
        </div>
        <div class="flex items-baseline gap-1.5">
          <span class="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)]">{{ t('trace.failedCalls') }}</span>
          <span :class="['font-mono text-[13px]', summary.failedCalls > 0 ? 'text-[var(--color-error)]' : 'text-[var(--color-text-primary)]']">{{ String(summary.failedCalls) }}</span>
        </div>
        <div class="flex items-baseline gap-1.5">
          <span class="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)]">{{ t('trace.models') }}</span>
          <span class="font-mono text-[13px] text-[var(--color-text-primary)]">{{ String(summary.models) }}</span>
        </div>
      </div>
    </header>

    <div class="flex min-h-0 flex-1 flex-col">
      <!-- Search -->
      <div class="shrink-0 border-b border-[var(--color-border)] px-5 py-3">
        <div class="flex h-9 max-w-xl items-center rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-3 focus-within:border-[var(--color-border-focus)]">
          <span class="material-symbols-outlined text-sm shrink-0 text-[var(--color-text-tertiary)]" aria-hidden="true">search</span>
          <input
            :value="queryInput"
            @input="queryInput = ($event.target as HTMLInputElement).value"
            :placeholder="t('trace.list.searchPlaceholder')"
            class="min-w-0 flex-1 bg-transparent px-2 text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-tertiary)]"
          />
        </div>
      </div>

      <!-- Loading skeleton -->
      <div
        v-if="state.status === 'loading'"
        class="min-h-0 flex-1 overflow-hidden"
        role="status"
        :aria-label="t('common.loading')"
      >
        <div class="divide-y divide-[var(--color-border)]" aria-hidden="true">
          <div
            v-for="index in 6"
            :key="index"
            class="flex h-14 items-center gap-4 px-5"
          >
            <div class="min-w-0 flex-1">
              <div class="h-3 w-48 max-w-full animate-pulse rounded bg-[var(--color-surface-container-high)]" />
              <div class="mt-2 h-2.5 w-72 max-w-full animate-pulse rounded bg-[var(--color-surface-container-low)]" />
            </div>
            <div class="flex shrink-0 items-center gap-3">
              <div class="h-3 w-10 animate-pulse rounded bg-[var(--color-surface-container-high)]" />
              <div class="h-3 w-12 animate-pulse rounded bg-[var(--color-surface-container-high)]" />
              <div class="h-3 w-12 animate-pulse rounded bg-[var(--color-surface-container-high)]" />
            </div>
          </div>
        </div>
      </div>

      <!-- Error -->
      <div
        v-else-if="state.status === 'error'"
        class="m-5 rounded-[var(--radius-md)] border border-[var(--color-error)]/30 bg-[var(--color-error)]/5 p-4 text-sm text-[var(--color-error)]"
      >
        {{ state.message }}
      </div>

      <!-- Ready state -->
      <div
        v-else-if="state.status === 'ready' && state.data.traces.length === 0"
        class="flex flex-1 items-start justify-center px-6 py-10"
      >
        <div class="w-full max-w-md rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-6 py-12 text-center">
          <span class="material-symbols-outlined mx-auto text-2xl text-[var(--color-text-tertiary)]" aria-hidden="true">workflow</span>
          <h2 class="mt-3 text-sm font-semibold text-[var(--color-text-primary)]">{{ t('trace.list.emptyTitle') }}</h2>
          <p class="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{{ t('trace.list.emptyBody') }}</p>
        </div>
      </div>

      <div
        v-else-if="state.status === 'ready' && state.data.traces.length > 0"
        class="min-h-0 flex-1 overflow-y-auto"
      >
        <div class="divide-y divide-[var(--color-border)]" role="list">
          <div
            v-for="trace in state.data.traces"
            :key="trace.sessionId"
            :aria-label="trace.session?.title || t('session.untitled')"
            role="listitem"
            class="trace-list-row-cv group flex h-14 cursor-pointer items-center gap-4 px-5 transition-colors hover:bg-[var(--color-surface-hover)]"
          >
            <button
              type="button"
              @click="openTrace(trace.sessionId, trace.session?.title || t('session.untitled'))"
              @keydown="(e) => handleRowKeydown(e, trace)"
              class="flex min-w-0 flex-1 items-center gap-4 self-stretch bg-transparent p-0 text-left"
            >
              <div class="min-w-0 flex-1">
                <div class="flex min-w-0 items-center gap-2">
                  <span class="min-w-0 truncate text-sm font-semibold text-[var(--color-text-primary)]">
                    {{ trace.session?.title || t('session.untitled') }}
                  </span>
                  <span
                    v-for="model in trace.summary.models.slice(0, MAX_MODEL_CHIPS)"
                    :key="model.model"
                    :title="`${model.model} x${model.calls}`"
                    class="shrink-0 rounded-[var(--radius-sm)] bg-[var(--color-brand)]/10 px-1.5 py-0.5 font-mono text-[10px] leading-4 text-[var(--color-brand)]"
                  >
                    {{ shortModelName(model.model) }}
                  </span>
                  <span
                    v-if="trace.summary.models.length > MAX_MODEL_CHIPS"
                    class="shrink-0 rounded-[var(--radius-sm)] bg-[var(--color-surface-container-high)] px-1.5 py-0.5 font-mono text-[10px] leading-4 text-[var(--color-text-tertiary)]"
                  >
                    +{{ trace.summary.models.length - MAX_MODEL_CHIPS }}
                  </span>
                  <span
                    v-if="trace.summary.failedCalls > 0"
                    :title="t('trace.failedCalls')"
                    class="flex shrink-0 items-center gap-1"
                  >
                    <span class="h-1.5 w-1.5 rounded-full bg-[var(--color-error)]" aria-hidden="true" />
                    <span class="font-mono text-[10px] text-[var(--color-error)]">{{ trace.summary.failedCalls }}</span>
                  </span>
                </div>
                <div class="mt-1 flex min-w-0 items-center gap-1.5 text-[10px] text-[var(--color-text-tertiary)]">
                  <span class="shrink-0 font-mono">{{ trace.sessionId.slice(0, 8) }}</span>
                  <template v-if="trace.session?.projectPath">
                    <span aria-hidden="true">·</span>
                    <span class="truncate" :title="trace.session.projectPath">{{ trace.session.projectPath }}</span>
                  </template>
                  <span aria-hidden="true">·</span>
                  <span class="shrink-0 font-mono">{{ formatUpdatedAt(trace.summary.updatedAt ?? trace.fileUpdatedAt) }}</span>
                </div>
              </div>
              <div class="grid shrink-0 grid-cols-[3.5rem_4rem_4rem] items-center gap-3">
                <div class="text-right">
                  <div class="font-mono text-[11px] leading-4 text-[var(--color-text-primary)]">{{ trace.summary.apiCalls }}</div>
                  <div class="truncate text-[10px] uppercase leading-4 tracking-wide text-[var(--color-text-tertiary)]" :title="t('trace.apiCalls')">
                    {{ t('trace.apiCalls') }}
                  </div>
                </div>
                <div class="text-right">
                  <div class="font-mono text-[11px] leading-4 text-[var(--color-text-primary)]">{{ formatDuration(trace.summary.totalDurationMs) }}</div>
                  <div class="truncate text-[10px] uppercase leading-4 tracking-wide text-[var(--color-text-tertiary)]" :title="t('trace.modelTime')">
                    {{ t('trace.modelTime') }}
                  </div>
                </div>
                <div class="text-right">
                  <div class="font-mono text-[11px] leading-4 text-[var(--color-text-primary)]">{{ formatCompact(trace.summary.totalInputTokens + trace.summary.totalOutputTokens) }}</div>
                  <div class="truncate text-[10px] uppercase leading-4 tracking-wide text-[var(--color-text-tertiary)]" :title="t('trace.tokens')">
                    {{ t('trace.tokens') }}
                  </div>
                </div>
              </div>
            </button>
            <div class="flex w-[60px] shrink-0 items-center justify-end gap-1 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
              <button
                type="button"
                :aria-label="t('trace.open')"
                :title="t('trace.open')"
                class="flex h-7 w-7 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-container-high)] hover:text-[var(--color-text-primary)] active:scale-[0.98]"
                @click.stop="openTrace(trace.sessionId, trace.session?.title || t('session.untitled'))"
              >
                <span class="material-symbols-outlined text-sm" aria-hidden="true">workflow</span>
              </button>
              <button
                type="button"
                :aria-label="t('trace.openWindow')"
                :title="t('trace.openWindow')"
                class="flex h-7 w-7 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-container-high)] hover:text-[var(--color-text-primary)] active:scale-[0.98]"
                @click.stop="host.trace?.openWindow(trace.sessionId)"
              >
                <span class="material-symbols-outlined text-sm" aria-hidden="true">open_in_new</span>
              </button>
            </div>
          </div>
        </div>
        <div class="flex items-center justify-between border-t border-[var(--color-border)] px-5 py-3 text-xs text-[var(--color-text-tertiary)]">
          <span>{{ t('trace.list.loadedCount', { shown: state.data.traces.length, total: state.data.total }) }}</span>
          <button
            v-if="state.data.traces.length < state.data.total"
            type="button"
            :disabled="isLoadingMore"
            class="inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface-container)] px-3 text-xs font-medium text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-surface-hover)] active:scale-[0.98]"
            @click="handleLoadMore"
          >
            {{ isLoadingMore ? t('common.loading') : t('trace.list.loadMore') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
