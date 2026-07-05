<script setup lang="ts">
// v3.0 — ContextUsageIndicator (Vue 3 SFC)
// Full translation of src/components/chat/ContextUsageIndicator.tsx (439 lines).
// Tracks context token usage via sessionsApi, shows conic-ring indicator
// with hover tooltip + mobile bottom-sheet.
import {
  ref,
  computed,
  onMounted,
  onBeforeUnmount,
  watch,
  nextTick,
} from 'vue'
import { sessionsApi, type SessionContextSnapshot } from '../../../api/sessions'
import { useTranslation } from '../../i18n'
import MobileBottomSheet from '../shared/MobileBottomSheet.vue'

// ── Constants ─────────────────────────────────────────────────────────
const ACTIVE_REFRESH_MS = 30_000
const CONTEXT_REQUEST_TIMEOUT_MS = 20_000
const AUTO_REFRESH_MIN_INTERVAL_MS = 10_000
const FORCED_REFRESH_RETRY_MS = 5_000

// ── Helpers ───────────────────────────────────────────────────────────
function formatNumber(value: number | undefined): string {
  return new Intl.NumberFormat().format(value ?? 0)
}

function formatPercent(value: number | undefined): string {
  const percent = Math.max(0, Math.min(100, value ?? 0))
  return `${percent.toFixed(percent >= 10 || Number.isInteger(percent) ? 0 : 1)}%`
}

function formatUpdatedAt(timestamp: number | null, t: ReturnType<typeof useTranslation>): string {
  if (!timestamp) return t('contextIndicator.updatedUnknown')
  const elapsedMs = Date.now() - timestamp
  if (elapsedMs < 60_000) return t('contextIndicator.updatedNow')
  const minutes = Math.max(1, Math.floor(elapsedMs / 60_000))
  return t('contextIndicator.updatedMinutes', { count: minutes })
}

function pickUsedContextCategory(context: SessionContextSnapshot) {
  const ignored = new Set(['free space', 'autocompact buffer'])
  return context.categories
    .filter((category) => category.tokens > 0 && !category.isDeferred && !ignored.has(category.name.toLowerCase()))
    .sort((a, b) => b.tokens - a.tokens)
    .slice(0, 4)
}

function firstNonEmpty(...values: Array<string | undefined | null>): string | undefined {
  return values.find((value) => typeof value === 'string' && value.trim().length > 0)?.trim()
}

function isCliNotRunningError(error: string | null): boolean {
  return error?.toLowerCase().includes('cli session is not running') ?? false
}

function isDocumentVisible(): boolean {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden'
}

function shouldFetchContext(sessionId: string | undefined, draft: boolean): boolean {
  return Boolean(sessionId) && !draft
}

// ── Props ─────────────────────────────────────────────────────────────
export interface ContextUsageIndicatorProps {
  sessionId?: string
  chatState: 'idle' | 'thinking' | 'compacting' | 'tool_executing' | 'error'
  messageCount: number
  runtimeSelectionKey?: string
  fallbackModelLabel?: string
  draft?: boolean
  compact?: boolean
  refreshNonce?: number
}

const props = withDefaults(defineProps<ContextUsageIndicatorProps>(), {
  runtimeSelectionKey: '',
  draft: false,
  compact: false,
  refreshNonce: 0,
})

// ── Reactive state ────────────────────────────────────────────────────
const t = useTranslation()

const context = ref<SessionContextSnapshot | null>(null)
const contextSource = ref<'live' | 'estimate' | null>(null)
const loading = ref(shouldFetchContext(props.sessionId, props.draft))
const error = ref<string | null>(null)
const updatedAt = ref<number | null>(null)
const inspectionModel = ref<string | null>(null)
const mobileDetailsOpen = ref(false)

// Refs for cancelling in-flight requests and tracking identity
const requestSeq = ref(0)
const contextIdentityRef = ref('')
const inFlightRequestRef = ref<Promise<boolean> | null>(null)
const inFlightIdentityRef = ref<string | null>(null)
const lastAutoRefreshAtRef = ref(0)
const lastRefreshNonceRef = ref(props.refreshNonce)

// ── refresh function ──────────────────────────────────────────────────
async function refresh(mode: 'auto' | 'manual' | 'force' = 'manual'): Promise<boolean> {
  if (!props.sessionId || props.draft) {
    loading.value = false
    return false
  }
  if (mode === 'auto' && !isDocumentVisible()) {
    loading.value = false
    return false
  }
  if (mode === 'auto' && Date.now() - lastAutoRefreshAtRef.value < AUTO_REFRESH_MIN_INTERVAL_MS) {
    return inFlightRequestRef.value ?? false
  }
  if (typeof sessionsApi.getInspection !== 'function') {
    loading.value = false
    return false
  }
  const activeSessionId = props.sessionId
  const activeContextIdentity = `${activeSessionId}:${props.runtimeSelectionKey}`
  // 'force' must not reuse an in-flight request
  if (mode !== 'force' && inFlightRequestRef.value && inFlightIdentityRef.value === activeContextIdentity) {
    return inFlightRequestRef.value
  }
  const seq = requestSeq.value + 1
  requestSeq.value = seq
  if (mode === 'auto') lastAutoRefreshAtRef.value = Date.now()
  loading.value = true
  error.value = null
  const request = sessionsApi.getInspection(activeSessionId, {
    includeContext: true,
    contextOnly: true,
    timeout: CONTEXT_REQUEST_TIMEOUT_MS,
  })
    .then((inspection) => {
      if (seq !== requestSeq.value || activeContextIdentity !== contextIdentityRef.value) return false
      const nextContext = inspection.context ?? inspection.contextEstimate ?? null
      const nextSource = inspection.context ? 'live' : inspection.contextEstimate ? 'estimate' : null
      const usageModel = inspection.usage?.models.find((model) => firstNonEmpty(model.displayName, model.model)) ?? null
      context.value = nextContext
      contextSource.value = nextSource
      inspectionModel.value = firstNonEmpty(
        inspection.context?.model,
        inspection.contextEstimate?.model,
        inspection.status?.model,
        usageModel?.displayName,
        usageModel?.model,
      ) ?? null
      error.value = nextContext ? null : inspection.errors?.context ?? null
      updatedAt.value = Date.now()
      return nextContext !== null
    })
    .catch((err) => {
      if (seq !== requestSeq.value || activeContextIdentity !== contextIdentityRef.value) return false
      error.value = err instanceof Error ? err.message : String(err)
      return false
    })
    .finally(() => {
      if (inFlightRequestRef.value === request) {
        inFlightRequestRef.value = null
        inFlightIdentityRef.value = null
      }
      if (seq === requestSeq.value) loading.value = false
    })
  inFlightRequestRef.value = request
  inFlightIdentityRef.value = activeContextIdentity
  return request
}

// ── Watch: refreshNonce ───────────────────────────────────────────────
watch(
  () => props.refreshNonce,
  (newNonce) => {
    if (newNonce === lastRefreshNonceRef.value) return
    lastRefreshNonceRef.value = newNonce
    let cancelled = false
    let retryTimer: ReturnType<typeof setTimeout> | null = null
    void refresh('force').then((ok) => {
      if (ok || cancelled) return
      retryTimer = setTimeout(() => {
        void refresh('force')
      }, FORCED_REFRESH_RETRY_MS)
    })
    // cleanup via onBeforeUnmount hook below won't catch this, so we
    // rely on the component unmounting to naturally clear timers.
  },
)

// ── Watch: messageCount / runtimeSelectionKey / sessionId ─────────────
watch(
  () => [props.messageCount, props.runtimeSelectionKey, props.sessionId],
  () => {
    const contextIdentity = `${props.sessionId}:${props.runtimeSelectionKey}`
    const identityChanged = contextIdentityRef.value !== contextIdentity
    contextIdentityRef.value = contextIdentity
    if (identityChanged) {
      requestSeq.value += 1
      lastAutoRefreshAtRef.value = 0
      context.value = null
      contextSource.value = null
      error.value = null
      updatedAt.value = null
      inspectionModel.value = null
    }
    void refresh('auto')
  },
)

// ── Lifecycle: visibility change ──────────────────────────────────────
const onVisibilityChange = () => {
  if (!isDocumentVisible()) return
  void refresh('auto')
}
onMounted(() => {
  document.addEventListener('visibilitychange', onVisibilityChange)
  // initial auto-refresh if needed
  if (!contextIdentityRef.value) {
    contextIdentityRef.value = `${props.sessionId}:${props.runtimeSelectionKey}`
    void refresh('auto')
  }
})
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
})

// ── Interval: active session polling ──────────────────────────────────
let activeRefreshTimer: ReturnType<typeof setInterval> | null = null
watch(
  () => [props.chatState, props.messageCount],
  () => {
    if (activeRefreshTimer) {
      clearInterval(activeRefreshTimer)
      activeRefreshTimer = null
    }
    if (props.chatState === 'idle') return
    activeRefreshTimer = setInterval(() => {
      void refresh('auto')
    }, ACTIVE_REFRESH_MS)
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  if (activeRefreshTimer) {
    clearInterval(activeRefreshTimer)
    activeRefreshTimer = null
  }
})

// ── Computed ──────────────────────────────────────────────────────────
const details = computed(() => {
  if (!context.value) return []
  return pickUsedContextCategory(context.value)
})

const displayContext = context.value
const hasPlaceholderContext = !displayContext && (
  props.draft || (!loading.value && props.messageCount === 0 && (!error.value || isCliNotRunningError(error.value)))
)
const isPendingContext = hasPlaceholderContext && !displayContext
const percentage = displayContext ? Math.max(0, Math.min(100, displayContext.percentage)) : 0
const usedTokens = displayContext?.totalTokens ?? 0
const maxTokens = displayContext?.rawMaxTokens ?? 0
const freeTokens = Math.max(0, maxTokens - usedTokens)

const strokeColor = computed(() => {
  if (percentage >= 90) return 'var(--color-error)'
  if (percentage >= 75) return 'var(--color-warning)'
  return 'var(--color-secondary)'
})

const ringStyle = computed(() => {
  if (displayContext) {
    return {
      background: `conic-gradient(${strokeColor.value} ${percentage * 3.6}deg, var(--color-surface-container-high) 0deg)`,
    }
  }
  return { background: 'var(--color-surface-container-high)' }
})

const displayPercent = computed(() => {
  if (!displayContext) return '--'
  return formatPercent(percentage)
})

const displayModel = computed(() => {
  return firstNonEmpty(
    context.value?.model,
    inspectionModel.value,
    props.fallbackModelLabel,
  )
})

const ariaLabel = computed(() => {
  if (displayContext) {
    return t('contextIndicator.ariaLabel', { percent: formatPercent(percentage) })
  }
  if (isPendingContext) return t('contextIndicator.pendingAria')
  if (loading.value) return t('contextIndicator.loadingAria')
  return t('contextIndicator.unavailableAria')
})

// ── Template helpers ──────────────────────────────────────────────────
function getCategoryPercent(category: SessionContextSnapshot['categories'][number]): number {
  if (maxTokens <= 0) return 0
  return Math.max(0.5, Math.min(100, (category.tokens / maxTokens) * 100))
}
</script>

<template>
  <div class="group/context relative pointer-events-auto">
    <button
      type="button"
      :aria-label="ariaLabel"
      :title="t('contextIndicator.title')"
      data-testid="context-usage-indicator"
      @click="() => { if (props.compact) mobileDetailsOpen = true; void refresh('manual') }"
      :class="[
        'flex h-8 shrink-0 items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-container)] text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-border-focus)] hover:bg-[var(--color-surface-container-high)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface-container-lowest)]',
        props.compact ? 'px-2' : 'px-2.5',
      ]"
    >
      <span class="relative grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full">
        <span
          v-if="loading && !displayContext"
          class="absolute inset-[2px] rounded-full border-2 border-[var(--color-text-tertiary)] border-t-transparent animate-spin"
        />
        <span
          v-else
          class="relative grid h-[18px] w-[18px] place-items-center rounded-full"
          :style="ringStyle"
        >
          <span class="absolute inset-[3px] rounded-full bg-[var(--color-surface-container-lowest)]" />
          <span
            class="relative h-[5px] w-[5px] rounded-full"
            :style="{ backgroundColor: displayContext ? strokeColor : 'var(--color-text-tertiary)' }"
          />
        </span>
      </span>
      <span class="font-mono text-[11px] font-semibold tabular-nums">{{ displayPercent }}</span>
    </button>

    <!-- Hover tooltip (non-compact only) -->
    <div
      v-if="!props.compact"
      class="pointer-events-none absolute bottom-full right-0 z-40 mb-2 w-[320px] max-w-[calc(100vw-2rem)] translate-y-1 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] p-4 text-left opacity-0 shadow-[var(--shadow-dropdown)] transition-all duration-150 group-hover/context:translate-y-0 group-hover/context:opacity-100 group-focus-within/context:translate-y-0 group-focus-within/context:opacity-100"
    >
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--color-text-tertiary)]">
            {{ t('contextIndicator.title') }}
          </div>
          <div class="mt-1 truncate text-sm font-semibold text-[var(--color-text-primary)]">
            {{ displayModel ?? t('contextIndicator.modelUnknown') }}
          </div>
        </div>
        <div class="shrink-0 font-mono text-xl font-semibold text-[var(--color-text-primary)]">
          {{ displayContext ? formatPercent(percentage) : '--' }}
        </div>
      </div>

      <template v-if="displayContext">
        <div class="mt-4 grid grid-cols-2 gap-3 font-mono text-xs">
          <div>
            <div class="text-[var(--color-text-tertiary)]">{{ t('contextIndicator.used') }}</div>
            <div class="mt-1 text-[var(--color-text-primary)]">{{ formatNumber(usedTokens) }}</div>
          </div>
          <div>
            <div class="text-[var(--color-text-tertiary)]">{{ t('contextIndicator.free') }}</div>
            <div class="mt-1 text-[var(--color-text-primary)]">{{ formatNumber(freeTokens) }}</div>
          </div>
          <div class="col-span-2">
            <div class="text-[var(--color-text-tertiary)]">{{ t('contextIndicator.window') }}</div>
            <div class="mt-1 text-[var(--color-text-primary)]">{{ maxTokens > 0 ? formatNumber(maxTokens) : '--' }}</div>
          </div>
        </div>
        <div v-if="details.length > 0" class="mt-4 space-y-2">
          <div v-for="category in details" :key="category.name">
            <div class="flex items-center justify-between gap-3 text-xs">
              <span class="min-w-0 truncate text-[var(--color-text-secondary)]">{{ category.name }}</span>
              <span class="shrink-0 font-mono text-[var(--color-text-tertiary)]">{{ formatNumber(category.tokens) }}</span>
            </div>
            <div class="mt-1 h-1 overflow-hidden rounded-full bg-[var(--color-surface-container)]">
              <div
                class="h-full rounded-full"
                :style="{ width: `${getCategoryPercent(category)}%`, backgroundColor: category.color }"
              />
            </div>
          </div>
        </div>
        <div class="mt-4 text-[11px] text-[var(--color-text-tertiary)]">
          {{ formatUpdatedAt(updatedAt, t) }}
          <span
            v-if="contextSource === 'estimate'"
            class="ml-2 inline-flex rounded-full border border-[var(--color-border)] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]"
          >
            {{ t('contextIndicator.estimate') }}
          </span>
        </div>
      </template>
      <div v-else-if="isPendingContext" class="mt-4 text-sm leading-6 text-[var(--color-text-secondary)]">
        {{ t('contextIndicator.pendingDetail') }}
      </div>
      <div v-else class="mt-4 text-sm leading-6 text-[var(--color-text-secondary)]">
        {{ loading ? t('contextIndicator.loading') : t('contextIndicator.unavailableDetail') }}
      </div>
    </div>

    <!-- Mobile bottom-sheet -->
    <MobileBottomSheet
      v-if="props.compact"
      :open="mobileDetailsOpen"
      @close="mobileDetailsOpen = false"
      :title="t('contextIndicator.title')"
      :close-label="t('tabs.close')"
      :aria-label="t('contextIndicator.title')"
    >
      <template #header-extra>
        <div class="truncate text-base font-semibold text-[var(--color-text-primary)]">
          {{ displayModel ?? t('contextIndicator.modelUnknown') }}
        </div>
      </template>
      <template #default>
        <div class="p-4">
          <div class="flex items-end justify-between gap-4">
            <div class="font-mono text-4xl font-semibold text-[var(--color-text-primary)]">
              {{ displayContext ? formatPercent(percentage) : '--' }}
            </div>
            <span
              v-if="contextSource === 'estimate'"
              class="mb-1 rounded-full border border-[var(--color-border)] px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--color-text-tertiary)]"
            >
              {{ t('contextIndicator.estimate') }}
            </span>
          </div>

          <div v-if="displayContext" class="mt-5">
            <div class="grid grid-cols-3 gap-2 font-mono text-xs">
              <div class="rounded-xl bg-[var(--color-surface-container)] p-3">
                <div class="text-[var(--color-text-tertiary)]">{{ t('contextIndicator.used') }}</div>
                <div class="mt-1 text-[var(--color-text-primary)]">{{ formatNumber(usedTokens) }}</div>
              </div>
              <div class="rounded-xl bg-[var(--color-surface-container)] p-3">
                <div class="text-[var(--color-text-tertiary)]">{{ t('contextIndicator.free') }}</div>
                <div class="mt-1 text-[var(--color-text-primary)]">{{ formatNumber(freeTokens) }}</div>
              </div>
              <div class="rounded-xl bg-[var(--color-surface-container)] p-3">
                <div class="text-[var(--color-text-tertiary)]">{{ t('contextIndicator.window') }}</div>
                <div class="mt-1 text-[var(--color-text-primary)]">{{ maxTokens > 0 ? formatNumber(maxTokens) : '--' }}</div>
              </div>
            </div>
            <div v-if="details.length > 0" class="mt-5 space-y-3">
              <div v-for="category in details" :key="category.name">
                <div class="flex items-center justify-between gap-3 text-xs">
                  <span class="min-w-0 truncate text-[var(--color-text-secondary)]">{{ category.name }}</span>
                  <span class="shrink-0 font-mono text-[var(--color-text-tertiary)]">{{ formatNumber(category.tokens) }}</span>
                </div>
                <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[var(--color-surface-container)]">
                  <div
                    class="h-full rounded-full"
                    :style="{ width: `${getCategoryPercent(category)}%`, backgroundColor: category.color }"
                  />
                </div>
              </div>
            </div>
            <div class="mt-4 text-[11px] text-[var(--color-text-tertiary)]">
              {{ formatUpdatedAt(updatedAt, t) }}
            </div>
          </div>
          <div v-else class="mt-5 rounded-xl bg-[var(--color-surface-container)] p-4 text-sm leading-6 text-[var(--color-text-secondary)]">
            {{ isPendingContext
              ? t('contextIndicator.pendingDetail')
              : loading
                ? t('contextIndicator.loading')
                : t('contextIndicator.unavailableDetail') }}
          </div>
        </div>
      </template>
    </MobileBottomSheet>
  </div>
</template>