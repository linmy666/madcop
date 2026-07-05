<!-- v3.0 — DiagnosticsSettings (Vue 3 SFC)
     Full translation of DiagnosticsSettings.tsx (277 lines) → Vue 3 Composition API SFC.

     Rules applied:
     - className → class (all Tailwind classes kept VERBATIM)
     - All --color-* CSS variables kept VERBATIM
     - useState → ref() ; useEffect → onMounted ; useMemo → computed
     - lucide-react icons → <span class="material-symbols-outlined">icon_name</span>
     - createPortal → <teleport to="body"> (not used; ConfirmDialog handles it)
     - Self-contained leaf: uses useTranslation(), useUIStore(), diagnosticsApi directly
       (matches the parent Settings.vue render pattern: <DiagnosticsSettings /> no props)
     - i18n key format: settings.diagnostics.*
     - Sub-components (Metric, EventRow) rendered as inline helpers with
       <template> v-for and helper functions in <script setup>
     - Pure helpers (formatDetails, formatEventForCopy) kept as standalone functions
-->

<script setup lang="ts">
import type { DiagnosticEvent, DiagnosticsStatus } from '../../api/diagnostics'
import { diagnosticsApi } from '../../api/diagnostics'
import { formatBytes } from '../../lib/formatBytes'
import { copyTextToClipboard } from '../../components/chat/clipboard'
import { useTranslation } from '../../i18n'
import { useUIStore } from '../stores/uiStore'
import Button from '../components/shared/Button.vue'
import DoctorPanel from '../components/doctor/DoctorPanel.vue'
import ConfirmDialog from '../components/shared/ConfirmDialog.vue'

import {
  ref,
  computed,
  onMounted,
  onUnmounted,
} from 'vue'

// ─── Pure helpers (extracted from React) ───────────────────────

function formatDetails(details: unknown): string {
  if (details === null || details === undefined) return ''
  if (typeof details === 'string') return details
  try {
    return JSON.stringify(details, null, 2)
  } catch {
    return String(details)
  }
}

function formatEventForCopy(event: DiagnosticEvent): string {
  const header = `[${event.timestamp}] ${event.severity.toUpperCase()} ${event.type}${event.sessionId ? ` session=${event.sessionId}` : ''}`
  const details = formatDetails(event.details)
  if (!details) return `${header}: ${event.summary}`
  return `${header}: ${event.summary}\nDetails:\n${details}`
}

// ─── Reactive state ──────────────────────────────────────────

const t = useTranslation()
const addToast = useUIStore((s) => s.addToast)

const status = ref<DiagnosticsStatus | null>(null)
const events = ref<DiagnosticEvent[]>([])
const isLoading = ref(true)
const isExporting = ref(false)
const isClearing = ref(false)
const clearConfirmOpen = ref(false)
const lastExportPath = ref<string | null>(null)

// ─── Computed (useMemo → computed) ───────────────────────────

const recentErrorSummary = computed(() => {
  return events.value
    .filter((event) => event.severity === 'error' || event.severity === 'warn')
    .slice(0, 20)
    .map(formatEventForCopy)
    .join('\n')
})

// ─── Load function (useCallback → plain function) ─────────────

let loadCancelled = false

async function load() {
  loadCancelled = false
  isLoading.value = true
  try {
    const [nextStatus, eventResult] = await Promise.all([
      diagnosticsApi.getStatus(),
      diagnosticsApi.getEvents(100),
    ])
    if (loadCancelled) return
    status.value = nextStatus
    events.value = eventResult.events
  } catch (error) {
    if (loadCancelled) return
    addToast({
      type: 'error',
      message: error instanceof Error ? error.message : t('settings.diagnostics.loadFailed'),
    })
  } finally {
    if (!loadCancelled) isLoading.value = false
  }
}

// ─── Lifecycle ───────────────────────────────────────────────

onMounted(() => {
  void load()
})

onUnmounted(() => {
  loadCancelled = true
})

// ─── Handlers ────────────────────────────────────────────────

async function handleOpenDir() {
  try {
    await diagnosticsApi.openLogDir()
  } catch (error) {
    addToast({
      type: 'error',
      message: error instanceof Error ? error.message : t('settings.diagnostics.openFailed'),
    })
  }
}

async function handleExport() {
  isExporting.value = true
  try {
    const { bundle } = await diagnosticsApi.exportBundle()
    lastExportPath.value = bundle.path
    addToast({
      type: 'success',
      message: t('settings.diagnostics.exported', { file: bundle.fileName }),
    })
    await load()
  } catch (error) {
    addToast({
      type: 'error',
      message: error instanceof Error ? error.message : t('settings.diagnostics.exportFailed'),
    })
  } finally {
    isExporting.value = false
  }
}

async function handleCopySummary() {
  const text = recentErrorSummary.value || t('settings.diagnostics.noRecentErrors')
  const copied = await copyTextToClipboard(text)
  if (copied) {
    addToast({ type: 'success', message: t('settings.diagnostics.summaryCopied') })
    return
  }
  addToast({ type: 'error', message: t('settings.diagnostics.copyFailed') })
}

async function handleClear() {
  isClearing.value = true
  try {
    await diagnosticsApi.clear()
    events.value = []
    status.value = await diagnosticsApi.getStatus()
    lastExportPath.value = null
    clearConfirmOpen.value = false
    addToast({ type: 'success', message: t('settings.diagnostics.cleared') })
  } catch (error) {
    addToast({
      type: 'error',
      message: error instanceof Error ? error.message : t('settings.diagnostics.clearFailed'),
    })
  } finally {
    isClearing.value = false
  }
}

function onCloseConfirm() {
  if (!isClearing.value) clearConfirmOpen.value = false
}

// ─── Severity class helper (used in EventRow) ─────────────────

function getSeverityClass(severity: string): string {
  if (severity === 'error') return 'text-[var(--color-error)]'
  if (severity === 'warn') return 'text-[var(--color-warning)]'
  return 'text-[var(--color-text-tertiary)]'
}
</script>

<template>
  <div class="max-w-4xl">
    <!-- Header -->
    <div class="flex items-start justify-between gap-4 mb-5">
      <div>
        <h2 class="text-base font-semibold text-[var(--color-text-primary)]">{{ t('settings.diagnostics.title') }}</h2>
        <p class="text-sm text-[var(--color-text-tertiary)] mt-0.5">{{ t('settings.diagnostics.description') }}</p>
      </div>
      <Button variant="secondary" size="sm" :loading="isLoading" @click="load">
        <template #icon>
          <span class="material-symbols-outlined text-[16px]">refresh</span>
        </template>
        {{ t('settings.diagnostics.refresh') }}
      </Button>
    </div>

    <!-- Metric grid -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
      <div class="border border-[var(--color-border)] rounded-lg px-3 py-2">
        <div class="text-xs text-[var(--color-text-tertiary)]">{{ t('settings.diagnostics.totalSize') }}</div>
        <div class="text-sm font-semibold text-[var(--color-text-primary)] mt-1">
          {{ status ? formatBytes(status.totalBytes) : '-' }}
        </div>
      </div>
      <div class="border border-[var(--color-border)] rounded-lg px-3 py-2">
        <div class="text-xs text-[var(--color-text-tertiary)]">{{ t('settings.diagnostics.events') }}</div>
        <div class="text-sm font-semibold text-[var(--color-text-primary)] mt-1">
          {{ status ? String(status.eventCount) : '-' }}
        </div>
      </div>
      <div class="border border-[var(--color-border)] rounded-lg px-3 py-2">
        <div class="text-xs text-[var(--color-text-tertiary)]">{{ t('settings.diagnostics.recentErrors') }}</div>
        <div class="text-sm font-semibold text-[var(--color-text-primary)] mt-1">
          {{ status ? String(status.recentErrorCount) : '-' }}
        </div>
      </div>
      <div class="border border-[var(--color-border)] rounded-lg px-3 py-2">
        <div class="text-xs text-[var(--color-text-tertiary)]">{{ t('settings.diagnostics.retention') }}</div>
        <div class="text-sm font-semibold text-[var(--color-text-primary)] mt-1">
          {{ status ? t('settings.diagnostics.retentionValue', { days: String(status.retentionDays), size: formatBytes(status.maxBytes) }) : '-' }}
        </div>
      </div>
    </div>

    <!-- DoctorPanel -->
    <div class="mb-5">
      <DoctorPanel />
    </div>

    <!-- Log directory box -->
    <div class="border border-[var(--color-border)] rounded-lg mb-5">
      <div class="px-4 py-3 border-b border-[var(--color-border)] flex items-center justify-between gap-3">
        <div>
          <div class="text-sm font-medium text-[var(--color-text-primary)]">{{ t('settings.diagnostics.logDirectory') }}</div>
          <div class="text-xs text-[var(--color-text-tertiary)] font-mono break-all mt-0.5">{{ status?.logDir ?? '-' }}</div>
        </div>
        <Button variant="secondary" size="sm" @click="handleOpenDir">
          <template #icon>
            <span class="material-symbols-outlined text-[16px]">folder_open</span>
          </template>
          {{ t('settings.diagnostics.openDirectory') }}
        </Button>
      </div>
      <div class="px-4 py-3 flex flex-wrap items-center gap-2">
        <Button size="sm" :loading="isExporting" @click="handleExport">
          <template #icon>
            <span class="material-symbols-outlined text-[16px]">archive</span>
          </template>
          {{ t('settings.diagnostics.exportBundle') }}
        </Button>
        <Button variant="secondary" size="sm" @click="handleCopySummary">
          <template #icon>
            <span class="material-symbols-outlined text-[16px]">content_copy</span>
          </template>
          {{ t('settings.diagnostics.copySummary') }}
        </Button>
        <Button variant="danger" size="sm" :loading="isClearing" @click="clearConfirmOpen = true">
          <template #icon>
            <span class="material-symbols-outlined text-[16px]">delete</span>
          </template>
          {{ t('settings.diagnostics.clearLogs') }}
        </Button>
        <span
          v-if="lastExportPath"
          class="text-xs text-[var(--color-text-tertiary)] font-mono break-all"
        >
          {{ lastExportPath }}
        </span>
      </div>
    </div>

    <!-- Recent events header -->
    <div class="mb-3">
      <h3 class="text-sm font-semibold text-[var(--color-text-primary)]">{{ t('settings.diagnostics.recentEvents') }}</h3>
      <p class="text-xs text-[var(--color-text-tertiary)] mt-0.5">{{ t('settings.diagnostics.privacyNote') }}</p>
    </div>

    <!-- Events list -->
    <div class="border border-[var(--color-border)] rounded-lg overflow-hidden">
      <div
        v-if="events.length === 0"
        class="px-4 py-8 text-sm text-[var(--color-text-tertiary)] text-center"
      >
        {{ isLoading ? t('common.loading') : t('settings.diagnostics.noEvents') }}
      </div>
      <div v-else class="divide-y divide-[var(--color-border)]">
        <div
          v-for="event in events"
          :key="event.id"
          class="px-4 py-3 grid grid-cols-[120px_92px_1fr] gap-3 items-start"
        >
          <div class="text-xs text-[var(--color-text-tertiary)] font-mono">
            {{ new Date(event.timestamp).toLocaleString() }}
          </div>
          <div :class="['text-xs font-semibold uppercase', getSeverityClass(event.severity)]">
            {{ event.severity }}
          </div>
          <div class="min-w-0">
            <div class="flex items-center gap-2 min-w-0">
              <span class="text-sm font-medium text-[var(--color-text-primary)] truncate">{{ event.type }}</span>
              <span
                v-if="event.sessionId"
                class="text-[11px] text-[var(--color-text-tertiary)] font-mono truncate"
              >
                {{ event.sessionId }}
              </span>
            </div>
            <div class="text-xs text-[var(--color-text-secondary)] mt-1 break-words">{{ event.summary }}</div>
            <details v-if="formatDetails(event.details)" class="mt-2">
              <summary class="cursor-pointer text-xs text-[var(--color-text-tertiary)] select-none">
                {{ t('settings.diagnostics.eventDetails') }}
              </summary>
              <pre class="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-2 text-[11px] leading-relaxed text-[var(--color-text-secondary)]">
{{ formatDetails(event.details) }}
              </pre>
            </details>
          </div>
        </div>
      </div>
    </div>

    <!-- ConfirmDialog -->
    <ConfirmDialog
      :open="clearConfirmOpen"
      :title="t('settings.diagnostics.clearLogs')"
      :confirm-label="t('settings.diagnostics.clearLogs')"
      :cancel-label="t('common.cancel')"
      :confirm-variant="'danger'"
      :loading="isClearing"
      @close="onCloseConfirm"
      @confirm="handleClear"
    >
      {{ t('settings.diagnostics.confirmClear') }}
    </ConfirmDialog>
  </div>
</template>