<script lang="ts">
// Sub-components defined first (mirrors React TerminalHelpHint / StatusPill)
// These use defineComponent so they can be referenced in the main template.
import { defineComponent, ref, computed, watch, onMounted } from 'vue'
import { useTranslation } from '../../i18n'

export const TerminalHelpHint = defineComponent({
  props: {
    compact: { type: Boolean, default: false },
  },
  setup() {
    const t = useTranslation()
    const open = ref(false)

    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') open.value = false
    }

    return { t, open, onKey }
  },
  render() {
    const { h } = (window as any).__VUE_GLOBALS__ || {}
    const createVNode = (window as any).__VUE_GLOBALS__?.createVNode
    const createTextVNode = (window as any).__VUE_GLOBALS__?.createTextVNode
    // Use Vue's h() from runtime - we'll import properly
    return null // placeholder; see actual render below
  },
})
</script>

<script setup lang="ts">
// v3.0 — TerminalSettings (Vue 3 SFC translation from React TerminalSettings.tsx 798 lines)
// Direct translation of src/pages/TerminalSettings.tsx
//
// Manages the desktop terminal panel: xterm.js runtime lifecycle, shell preferences
// (startup shell + custom path), Bash path override, copy/paste shortcuts, and status pill.

import {
  ref,
  computed,
  watch,
  onMounted,
  onUnmounted,
  shallowRef,
  nextTick,
  defineComponent,
  h,
} from 'vue'

import { useSettingsStore } from '../stores/settingsStore'
import { useTranslation, type TranslationKey } from '../../i18n'
import { terminalApi } from '../../api/terminal'
import Dropdown from '../components/shared/Dropdown.vue'
import Input from '../components/shared/Input.vue'
import Button from '../components/shared/Button.vue'
import type { DesktopTerminalStartupShell } from '../../types/settings'
import { getDesktopHost } from '../../lib/desktopHost'
import {
  attachTerminalRuntime,
  createLocalTerminalRuntimeId,
  destroyTerminalRuntime,
  getTerminalRuntime,
  subscribeTerminalRuntime,
  updateTerminalRuntime,
  type TerminalRuntime,
  type TerminalStatus,
} from '../../lib/terminalRuntime'

// ─── i18n status label mapping ──────────────────────────────

const STATUS_LABEL_KEYS: Record<TerminalStatus, TranslationKey> = {
  idle: 'settings.terminal.status.idle',
  starting: 'settings.terminal.status.starting',
  running: 'settings.terminal.status.running',
  exited: 'settings.terminal.status.exited',
  error: 'settings.terminal.status.error',
  unavailable: 'settings.terminal.status.unavailable',
}

// ─── Pure helpers ────────────────────────────────────────────

function findScrollableAncestor(element: HTMLElement, deltaY: number): HTMLElement | null {
  let parent = element.parentElement
  while (parent) {
    const style = window.getComputedStyle(parent)
    const canScrollY = style.overflowY === 'auto' || style.overflowY === 'scroll'
    if (canScrollY && parent.scrollHeight > parent.clientHeight) {
      const maxScrollTop = parent.scrollHeight - parent.clientHeight
      const canMove = deltaY < 0 ? parent.scrollTop > 0 : parent.scrollTop < maxScrollTop
      if (canMove) return parent
    }
    parent = parent.parentElement
  }
  return null
}

// ─── Props ──────────────────────────────────────────────────

const props = withDefaults(defineProps<{
  active?: boolean
  cwd?: string
  onNewTerminal?: () => void
  onOpenInTab?: () => void
  onClose?: () => void
  testId?: string
  workspace?: boolean
  docked?: boolean
  showPreferences?: boolean
  runtimeId?: string
  preserveOnUnmount?: boolean
}>(), {
  active: true,
  testId: 'settings-terminal-host',
  workspace: false,
  docked: false,
  showPreferences: false,
  preserveOnUnmount: false,
})

// ─── Store / i18n ──────────────────────────────────────────

const settingsStore = useSettingsStore()
const t = useTranslation()

const desktopTerminal = computed(() => settingsStore.desktopTerminal)

// ─── Local runtime identity ─────────────────────────────────

const localRuntimeIdRef = ref<string | null>(null)
const runtimeRef = shallowRef<TerminalRuntime | null>(null)

function initRuntime() {
  if (!localRuntimeIdRef.value) {
    localRuntimeIdRef.value = props.runtimeId ?? createLocalTerminalRuntimeId()
  }
  const effectiveRuntimeId = props.runtimeId ?? localRuntimeIdRef.value
  const existing = runtimeRef.value
  if (!existing || existing.id !== effectiveRuntimeId) {
    runtimeRef.value = getTerminalRuntime(
      effectiveRuntimeId,
      terminalApi.isAvailable() ? 'idle' : 'unavailable',
    )
  }
}
initRuntime()

// ─── Reactive state ────────────────────────────────────────

const runtimeUpdateTick = ref(0)

const runtime = computed<TerminalRuntime>(() => {
  initRuntime()
  return runtimeRef.value!
})

const status = computed(() => runtime.value.status)
const error = computed(() => runtime.value.error)
const shellInfo = computed(() => runtime.value.shellInfo)

const startupShell = ref<DesktopTerminalStartupShell>(
  desktopTerminal.value?.startupShell ?? 'system',
)
const customShellPath = ref(desktopTerminal.value?.customShellPath ?? '')
const preferencesError = ref<string | null>(null)
const preferencesSaved = ref(false)
const preferencesSaving = ref(false)

const isWindows = typeof navigator !== 'undefined' && /Win/i.test(navigator.platform || navigator.userAgent)

const shellItems = computed(() => [
  {
    value: 'system' as const,
    label: t('settings.terminal.shell.system'),
    description: t('settings.terminal.shell.systemDesc'),
  },
  {
    value: 'pwsh' as const,
    label: t('settings.terminal.shell.pwsh'),
    description: t('settings.terminal.shell.pwshDesc'),
  },
  {
    value: 'powershell' as const,
    label: t('settings.terminal.shell.powershell'),
    description: t('settings.terminal.shell.powershellDesc'),
  },
  {
    value: 'cmd' as const,
    label: t('settings.terminal.shell.cmd'),
    description: t('settings.terminal.shell.cmdDesc'),
  },
  {
    value: 'custom' as const,
    label: t('settings.terminal.shell.custom'),
    description: t('settings.terminal.shell.customDesc'),
  },
])

// ─── Host ref ──────────────────────────────────────────────

const hostRef = ref<HTMLDivElement | null>(null)

// ─── Resize ────────────────────────────────────────────────

function resizeSession() {
  const rt = runtime.value
  const terminal = rt.terminal
  const fit = rt.fit
  const sessionId = rt.nativeSessionId
  if (!terminal || !fit) return
  fit.fit()
  if (sessionId) {
    void terminalApi.resize(sessionId, terminal.cols, terminal.rows).catch(() => {})
  }
}

// ─── Start terminal ────────────────────────────────────────

async function startTerminal() {
  if (!terminalApi.isAvailable()) {
    updateTerminalRuntime(runtime.value, { status: 'unavailable' })
    return
  }

  const host = hostRef.value
  if (!host) return

  const rt = runtime.value
  updateTerminalRuntime(rt, { error: null, status: 'starting', shellInfo: null })

  const existing = rt.nativeSessionId
  if (existing) {
    await terminalApi.kill(existing).catch(() => {})
    rt.nativeSessionId = null
  }
  rt.dataDisposable?.dispose()
  rt.dataDisposable = null
  rt.unlisteners.forEach((unlisten) => unlisten())
  rt.unlisteners = []

  rt.terminal?.dispose()
  rt.terminal = null
  rt.fit = null
  host.innerHTML = ''

  const [{ Terminal }, { FitAddon }] = await Promise.all([
    import('@xterm/xterm'),
    import('@xterm/addon-fit'),
  ])

  const terminal = new Terminal({
    cursorBlink: true,
    convertEol: false,
    fontFamily: "var(--font-mono), 'SFMono-Regular', Consolas, monospace",
    fontSize: 12,
    lineHeight: 1.25,
    scrollback: 4000,
    theme: {
      background: '#121212',
      foreground: '#d7d2d0',
      cursor: '#ffb59f',
      selectionBackground: '#5f4a40',
      black: '#1f1f1f',
      red: '#ff6d67',
      green: '#7ef18a',
      yellow: '#f8c55f',
      blue: '#77a8ff',
      magenta: '#d699ff',
      cyan: '#61d6d6',
      white: '#d7d2d0',
      brightBlack: '#8f8683',
      brightRed: '#ff8a85',
      brightGreen: '#9ff7a7',
      brightYellow: '#ffdd7a',
      brightBlue: '#a6c5ff',
      brightMagenta: '#e3b8ff',
      brightCyan: '#8ceeee',
      brightWhite: '#ffffff',
    },
  })
  const fit = new FitAddon()
  terminal.loadAddon(fit)
  terminal.open(host)
  updateTerminalRuntime(rt, { terminal, fit })
  fit.fit()

  const outputUnlisten = await terminalApi.onOutput((payload) => {
    if (payload.session_id === rt.nativeSessionId) {
      terminal.write(payload.data)
    }
  })
  const exitUnlisten = await terminalApi.onExit((payload) => {
    if (payload.session_id !== rt.nativeSessionId) return
    updateTerminalRuntime(rt, { status: 'exited' })
    const signal = payload.signal ? `, ${payload.signal}` : ''
    terminal.writeln(`\r\n[process exited: ${payload.code}${signal}]`)
    updateTerminalRuntime(rt, { nativeSessionId: null })
  })
  rt.unlisteners = [outputUnlisten, exitUnlisten]

  rt.dataDisposable = terminal.onData((data) => {
    const sessionId = rt.nativeSessionId
    if (sessionId) {
      void terminalApi.write(sessionId, data).catch((err) => {
        updateTerminalRuntime(rt, {
          error: err instanceof Error ? err.message : String(err),
          status: 'error',
        })
      })
    }
  })

  try {
    const result = await terminalApi.spawn({
      cols: terminal.cols,
      rows: terminal.rows,
      ...(props.cwd ? { cwd: props.cwd } : {}),
    })
    updateTerminalRuntime(rt, {
      nativeSessionId: result.session_id,
      shellInfo: { shell: result.shell, cwd: result.cwd },
      status: 'running',
    })
    resizeSession()
  } catch (err) {
    outputUnlisten()
    exitUnlisten()
    terminal.dispose()
    updateTerminalRuntime(rt, {
      terminal: null,
      fit: null,
      error: err instanceof Error ? err.message : String(err),
      status: 'error',
    })
  }
}

// ─── Lifecycle subscriptions ───────────────────────────────

let subscribeDisposed = false

onMounted(() => {
  subscribeTerminalRuntime(runtime.value, () => {
    if (!subscribeDisposed) runtimeUpdateTick.value++
  })
})

watch(
  () => desktopTerminal.value,
  (val) => {
    startupShell.value = val?.startupShell ?? 'system'
    customShellPath.value = val?.customShellPath ?? ''
  },
  { deep: true },
)

let preferencesSavedTimer: ReturnVal<typeof setTimeout> | null = null
function clearPreferencesSavedTimer() {
  if (preferencesSavedTimer) { clearTimeout(preferencesSavedTimer); preferencesSavedTimer = null }
}
watch(preferencesSaved, (saved) => {
  if (!saved) return
  clearPreferencesSavedTimer()
  preferencesSavedTimer = setTimeout(() => { preferencesSaved.value = false }, 2500)
})

let resizeObserver: ResizeObserver | null = null

function setupTerminalLifecycle() {
  if (!terminalApi.isAvailable()) return
  const rt = runtime.value
  if (rt.terminal) {
    if (hostRef.value) attachTerminalRuntime(rt, hostRef.value)
    resizeSession()
  } else {
    void startTerminal()
  }
  if (resizeObserver) resizeObserver.disconnect()
  resizeObserver = new ResizeObserver(() => resizeSession())
  if (hostRef.value) resizeObserver.observe(hostRef.value)
}

onMounted(() => setupTerminalLifecycle())

onUnmounted(() => {
  subscribeDisposed = true
  clearPreferencesSavedTimer()
  if (resizeObserver) { resizeObserver.disconnect(); resizeObserver = null }
  if (!props.preserveOnUnmount) { destroyTerminalRuntime(runtime.value.id) }
})

watch(() => props.active, (active) => {
  if (active) nextTick(() => resizeSession())
})

// ─── Actions ───────────────────────────────────────────────

function clearTerminal() {
  runtime.value.terminal?.clear()
}

function handleTerminalWheelCapture(event: WheelEvent) {
  const host = hostRef.value
  if (!host || host.contains(document.activeElement as Node)) return
  const target = event.currentTarget as HTMLElement
  const scroller = findScrollableAncestor(target, event.deltaY)
  if (!scroller) return
  event.preventDefault()
  event.stopPropagation()
  scroller.scrollBy({ top: event.deltaY, left: event.deltaX })
}

async function savePreferences() {
  preferencesError.value = null
  preferencesSaved.value = false

  const trimmedPath = customShellPath.value.trim()
  if (startupShell.value === 'custom') {
    if (!trimmedPath) {
      preferencesError.value = t('settings.terminal.customPathRequired')
      return
    }
    if (!/^[A-Za-z]:[\\\/]/.test(trimmedPath)) {
      preferencesError.value = t('settings.terminal.customPathAbsolute')
      return
    }
  }

  preferencesSaving.value = true
  try {
    await settingsStore.setDesktopTerminal({
      startupShell: startupShell.value,
      customShellPath: trimmedPath,
    })
    preferencesSaved.value = true
  } catch (err) {
    preferencesError.value = err instanceof Error ? err.message : String(err)
  } finally {
    preferencesSaving.value = false
  }
}

// ─── Bash path state (mirrors BashPathSettings) ─────────────

const bashPath = ref<string | null>(null)
const bashSaving = ref(false)
const bashSaved = ref(false)
const bashInvalid = ref(false)

onMounted(() => {
  if (!terminalApi.isAvailable()) return
  void terminalApi.getBashPath().then((p: string | null) => { bashPath.value = p }).catch(() => {})
})

async function handleBashSave() {
  const trimmed = bashPath.value?.trim() || null
  bashSaving.value = true
  bashInvalid.value = false
  bashSaved.value = false
  try {
    await terminalApi.setBashPath(trimmed)
    bashPath.value = trimmed
    bashSaved.value = true
    setTimeout(() => { bashSaved.value = false }, 2000)
  } catch {
    bashInvalid.value = true
  } finally {
    bashSaving.value = false
  }
}

async function handleBashReset() {
  bashSaving.value = true
  bashSaved.value = false
  bashInvalid.value = false
  try {
    await terminalApi.setBashPath(null)
    bashPath.value = null
    bashSaved.value = true
    setTimeout(() => { bashSaved.value = false }, 2000)
  } catch {
    // ignore
  } finally {
    bashSaving.value = false
  }
}

async function handleBashBrowse() {
  if (!terminalApi.isAvailable()) return
  const host = getDesktopHost()
  if (!host.capabilities.dialogs) return
  try {
    const selected = await host.dialogs.open({
      title: t('settings.terminal.bashPathLabel'),
      multiple: false,
      filters: [{
        name: 'Bash Executable',
        extensions: ['exe', '', 'bat', 'cmd', 'ps1'],
      }],
    })
    if (selected && typeof selected === 'string') {
      bashPath.value = selected
      bashInvalid.value = false
    }
  } catch {
    // user cancelled
  }
}
</script>

<template>
  <div
    :class="[
      'flex h-full flex-col overflow-hidden',
      docked
        ? 'min-h-0 bg-[var(--color-surface-container-lowest)] px-3 py-1.5'
        : workspace
          ? 'min-h-0 bg-[var(--color-surface)] px-5 py-4'
          : 'min-h-[min(720px,calc(100vh-8rem))]',
    ]"
  >
    <!-- ── Toolbar ─────────────────────────────────────────── -->
    <div
      data-testid="settings-terminal-toolbar"
      :class="[
        docked ? 'mb-1.5 min-h-8' : 'mb-2 min-h-9',
        'flex min-w-0 flex-wrap items-center gap-2',
      ]"
    >
      <div class="flex min-w-0 flex-1 items-center gap-2">
        <span
          class="h-2.5 w-2.5 shrink-0 rounded-full bg-[var(--color-terminal-danger)]"
          aria-hidden="true"
        />
        <span
          class="h-2.5 w-2.5 shrink-0 rounded-full bg-[var(--color-terminal-warning)]"
          aria-hidden="true"
        />
        <span
          class="h-2.5 w-2.5 shrink-0 rounded-full bg-[var(--color-terminal-accent)]"
          aria-hidden="true"
        />
        <h2
          :class="[
            docked ? 'text-[13px]' : 'text-sm',
            'shrink-0 font-semibold text-[var(--color-text-primary)]',
          ]"
        >
          {{ t('settings.terminal.title') }}
        </h2>
        <TerminalHelpHintInline :compact="docked" />
        <TerminalStatusPillInline
          :status="status"
          :label="t(STATUS_LABEL_KEYS[status] as TranslationKey)"
          :compact="docked"
        />
        <div
          v-if="shellInfo"
          class="flex min-w-0 items-center gap-1.5 text-xs text-[var(--color-text-tertiary)]"
        >
          <span class="shrink-0 font-mono">{{ shellInfo.shell }}</span>
          <span class="shrink-0 text-[var(--color-border)]">/</span>
          <span class="min-w-0 truncate font-mono">{{ shellInfo.cwd }}</span>
        </div>
      </div>

      <div class="flex shrink-0 items-center gap-1.5">
        <button
          v-if="onOpenInTab"
          type="button"
          @click="() => onOpenInTab && onOpenInTab()"
          class="inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] px-2.5 text-xs font-medium text-[var(--color-text-secondary)] transition-colors hover:bg>[var(--color-surface-hover)] hover:text>[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring>[var(--color-border-focus)]"
        >
          <span class="material-symbols-outlined text-[16px]">open_in_new</span>
          {{ t('terminal.openInTab') }}
        </button>
        <button
          v-if="onNewTerminal"
          type="button"
          @click="() => onNewTerminal && onNewTerminal()"
          class="inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-md)] border border>[var(--color-border)] px-2.5 text-xs font-medium text>[var(--color-text-secondary)] transition-colors hover:bg>[var(--color-surface-hover)] hover:text>[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring>[var(--color-border-focus)]"
        >
          <span class="material-symbols-outlined text-[16px]">add</span>
          {{ t('terminal.newTab') }}
        </button>
        <button
          type="button"
          @click="clearTerminal"
          :disabled="!runtime.terminal"
          class="inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-md)] border border>[var(--color-border)] px-2.5 text-xs font-medium text>[var(--color-text-secondary)] transition-colors hover:bg>[var(--color-surface-hover)] hover:text>[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring>[var(--color-border-focus)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          <span class="material-symbols-outlined text-[16px]">mop</span>
          {{ t('settings.terminal.clear') }}
        </button>
        <button
          type="button"
          @click="() => void startTerminal()"
          class="inline-flex h-8 items-center gap-1.5 rounded>[var(--radius-md)] bg>[var(--color-text-primary)] px-2.5 text-xs font-medium text>[var(--color-surface)] transition-colors hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring>[var(--color-border-focus)]"
        >
          <span class="material-symbols-outlined text>[16px]">restart_alt</span>
          {{ t('settings.terminal.restart') }}
        </button>
        <button
          v-if="onClose"
          type="button"
          @click="() => onClose && onClose()"
          :aria-label="t('terminal.closePanel')"
          class="inline-flex h-8 w-8 items-center justify-center rounded>[var(--radius-md)] text>[var(--color-text-tertiary)] transition-colors hover:text>[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring>[var(--color-border-focus)]"
        >
          <span class="material-symbols-outlined text>[17px]">close</span>
        </button>
      </div>
    </div>

    <!-- ── Error banner ────────────────────────────────────── -->
    <div
      v-if="error"
      class="mb-3 rounded>[var(--radius-md)] border border>[var(--color-error)]/20 bg>[var(--color-error)]/10 px-3 py-2 text-sm text>[var(--color-error)]"
    >
      {{ error }}
    </div>

    <!-- ── Windows shell preferences ───────────────────────── -->
    <template v-if="showPreferences && isWindows">
      <div class="mb-4 rounded>[var(--radius-lg)] border border>[var(--color-border)] bg>[var(--color-surface-container-low)] p-4">
        <div class="flex flex-col gap-3">
          <div>
            <h3 class="text-sm font-semibold text>[var(--color-text-primary)]">
              {{ t('settings.terminal.preferencesTitle') }}
            </h3>
            <p class="mt-1 text-sm text>[var(--color-text-secondary)]">
              {{ t('settings.terminal.preferencesBody') }}
            </p>
          </div>

          <div class="flex flex-col gap-2">
            <span class="text-sm font-medium text>[var(--color-text-primary)]">
              {{ t('settings.terminal.startupShell') }}
            </span>
            <Dropdown
              :items="shellItems"
              :model-value="startupShell"
              class="w-full"
              @update:model-value="(v: string) => {
                startupShell = v as DesktopTerminalStartupShell
                preferencesError = null
                preferencesSaved = false
              }"
            >
              <template #trigger>
                <button
                  type="button"
                  class="flex h-10 w-full items-center justify-between rounded>[var(--radius-md)] border border>[var(--color-border)] bg>[var(--color-surface)] px-3 text-sm text>[var(--color-text-primary)]"
                >
                  <span>
                    {{ shellItems.find((item: any) => item.value === startupShell)?.label ?? startupShell }}
                  </span>
                  <span class="material-symbols-outlined text>[18px] text>[var(--color-text-tertiary)]">expand_more</span>
                </button>
              </template>
            </Dropdown>
          </div>

          <Input
            v-if="startupShell === 'custom'"
            :label="t('settings.terminal.customPath')"
            :placeholder="t('settings.terminal.customPathPlaceholder')"
            :model-value="customShellPath"
            @update:model-value="customShellPath = $event"
            :error="preferencesError ?? undefined"
          />

          <p
            v-if="preferencesError && startupShell !== 'custom'"
            class="text-xs text>[var(--color-error)]"
          >
            {{ preferencesError }}
          </p>

          <div class="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              size="sm"
              :loading="preferencesSaving"
              @click="() => void savePreferences()"
            >
              {{ t('settings.terminal.saveShell') }}
            </Button>
            <span v-if="preferencesSaved" class="text-xs text>[var(--color-text-secondary)]">
              {{ t('settings.terminal.saveShellSuccess') }}
            </span>
          </div>
        </div>
      </div>

      <div class="mb-3 rounded>[var(--radius-md)] border border>[var(--color-border)] bg>[var(--color-surface-container-low)] px-4 py-3">
        <label class="mb-1.5 block text-sm font-medium text>[var(--color-text-primary)]">
          {{ t('settings.terminal.bashPathLabel') }}
        </label>
        <p class="mb-2 text-xs text>[var(--color-text-tertiary)]">
          {{ t('settings.terminal.bashPathDescription') }}
        </p>
        <div class="flex gap-2">
          <input
            type="text"
            :value="bashPath || ''"
            :placeholder="t('settings.terminal.bashPathLabel')"
            class="flex-1 rounded>[var(--radius-sm)] border border>[var(--color-border)] bg>[var(--color-surface)] px-3 py-1.5 text-sm font-mono text>[var(--color-text-primary)] outline-none placeholder:text>[var(--color-text-tertiary)] focus:border>[var(--color-border-focus)]"
            @input="(e: Event) => { bashPath = (e.target as HTMLInputElement).value; bashInvalid = false; bashSaved = false }"
          />
          <button
            type="button"
            @click="() => void handleBashBrowse()"
            class="inline-flex h-8 items-center gap-1 rounded>[var(--radius-sm)] border border>[var(--color-border)] px-3 text-xs font-medium text>[var(--color-text-secondary)] transition-colors hover:bg>[var(--color-surface-hover)]"
          >
            <span class="material-symbols-outlined text>[16px]">folder_open</span>
          </button>
          <button
            type="button"
            @click="() => void handleBashSave()"
            :disabled="bashSaving"
            class="inline-flex h-8 items-center gap-1 rounded>[var(--radius-sm)] bg>[var(--color-text-primary)] px-3 text-xs font-medium text>[var(--color-surface)] transition-colors hover:opacity-90 disabled:opacity-50"
          >
            {{ bashSaved ? t('settings.terminal.bashPathSaved') : t('settings.terminal.bashPathSave') }}
          </button>
          <button
            type="button"
            @click="() => void handleBashReset()"
            :disabled="bashSaving || bashPath === null"
            class="inline-flex h-8 items-center gap-1 rounded>[var(--radius-sm)] border border>[var(--color-border)] px-3 text-xs font-medium text>[var(--color-text-secondary)] transition-colors hover:bg>[var(--color-surface-hover)] disabled:opacity-50"
          >
            {{ t('settings.terminal.bashPathReset') }}
          </button>
        </div>
        <p v-if="bashInvalid" class="mt-1.5 text-xs text>[var(--color-error)]">
          {{ t('settings.terminal.bashPathInvalid') }}
        </p>
      </div>
    </template>

    <!-- ── Terminal unavailable ────────────────────────────── -->
    <div
      v-if="status === 'unavailable'"
      class="flex flex-1 items-center justify-center rounded>[var(--radius-lg)] border border-dashed border>[var(--color-border)] bg>[var(--color-surface-container-low)] p-8 text-center"
    >
      <div>
        <span
          class="material-symbols-outlined mb-3 block text>[32px] text>[var(--color-text-tertiary)]"
        >
          desktop_windows
        </span>
        <p class="text-sm font-medium text>[var(--color-text-primary)]">
          {{ t('settings.terminal.unavailableTitle') }}
        </p>
        <p class="mt-1 text-sm text>[var(--color-text-tertiary)]">
          {{ t('settings.terminal.unavailableBody') }}
        </p>
      </div>
    </div>

    <!-- ── Terminal frame ──────────────────────────────────── -->
    <div
      v-else
      data-testid="settings-terminal-frame"
      @keydown.capture="handleTerminalKeyDownCapture"
      @wheel.capture="handleTerminalWheelCapture"
      class="min-h-0 flex-1 overflow-hidden rounded>[var(--radius-sm)] border border>[var(--color-terminal-border)] bg>[var(--color-terminal-bg)] shadow>[var(--shadow-dropdown)]"
    >
      <div
        ref="hostRef"
        :data-testid="testId"
        class="settings-terminal-host h-full w-full overflow-hidden px-2 pb-2 pt-1.5"
      />
    </div>
  </div>
</template>

<!-- ─── TerminalHelpHint (render-function child component) ─── -->
<script lang="ts">
import { defineComponent, ref, computed } from 'vue'
import { useTranslation } from '../../i18n'
import { h as hFn } from 'vue'

export const TerminalHelpHintInline = defineComponent({
  props: {
    compact: { type: Boolean, default: false },
  },
  setup() {
    const t = useTranslation()
    const open = ref(false)

    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') open.value = false
    }

    const id = 'terminal-help-tooltip-' + Math.random().toString(36).slice(2, 8)

    return { t, open, onKey, id }
  },
  render(this: { t: (key: string) => string; open: boolean; compact: boolean; onKey: (e: KeyboardEvent) => void; id: string }) {
    const iconClasses = this.compact ? 'h-3.5 w-3.5' : 'h-4 w-4'
    const btnSizeClasses = this.compact ? 'h-6 w-6' : 'h-7 w-7'
    const tooltipVisibility = this.open ? 'visible opacity-100' : 'invisible opacity-0'
    const tooltip = `absolute left-0 top-full z-30 mt-2 w-[min(340px,calc(100vw-3rem))] rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-container-high)] px-3 py-2 text-left text-xs leading-5 text-[var(--color-text-secondary)] shadow-[var(--shadow-dropdown)] transition-opacity group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100`

    return hFn(
      'span',
      { class: 'group relative inline-flex shrink-0' },
      [
        hFn(
          'button',
          {
            type: 'button',
            'aria-label': this.t('settings.terminal.infoLabel'),
            'aria-describedby': this.id,
            'aria-expanded': this.open,
            onClick: () => { (this as any).open = !(this as any).open },
            onKeydown: (e: KeyboardEvent) => this.onKey(e),
            class: [
              btnSizeClasses,
              'inline-flex items-center justify-center rounded-full text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)]',
            ],
          },
          hFn('span', {
            class: 'material-symbols-outlined ' + iconClasses,
            'aria-hidden': 'true',
          }, 'info'),
        ),
        hFn(
          'span',
          {
            id: this.id,
            role: 'tooltip',
            class: tooltipVisibility + ' ' + tooltip,
          },
          this.t('settings.terminal.description'),
        ),
      ],
    )
  },
})
</script>

<!-- ─── TerminalStatusPill (render-function child component) ── -->
<script lang="ts">
export const TerminalStatusPillInline = defineComponent({
  props: {
    status: {
      type: String as () => 'idle' | 'starting' | 'running' | 'exited' | 'error' | 'unavailable',
      required: true,
    },
    label: { type: String, required: true },
    compact: { type: Boolean, default: false },
  },
  setup() {
    const color = computed(() => {
      const s = (this as any).status as string
      if (s === 'running') return 'bg-[var(--color-success)]'
      if (s === 'error') return 'bg-[var(--color-error)]'
      if (s === 'starting') return 'bg-[var(--color-warning)]'
      return 'bg-[var(--color-text-tertiary)]'
    })
    return { color }
  },
  render(this: { label: string; compact: boolean; color: string }) {
    const sizeClasses = this.compact ? 'h-5 px-2 text-[10px]' : 'h-6 px-2.5 text-[11px]'
    const pill = 'inline-flex shrink-0 items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-container-low)] font-medium text-[var(--color-text-secondary)]'

    return hFn(
      'span',
      { class: sizeClasses + ' ' + pill },
      [
        hFn('span', { class: 'h-1.5 w-1.5 rounded-full ' + this.color }),
        this.label,
      ],
    )
  },
})
</script>

<!-- ─── handleTerminalKeyDownCapture (mirrors React onKeyDownCapture) ─── -->
<script lang="ts">
import { getDesktopHost } from '../../lib/desktopHost'

export function handleTerminalKeyDownCapture(event: KeyboardEvent, runtime: { terminal: any }) {
  const terminal = runtime.terminal
  if (!terminal) return

  // copy
  if (isTerminalCopyShortcut(event as any, terminal as any)) {
    event.preventDefault()
    event.stopPropagation()
    void copyTerminalSelection(terminal as any).catch(() => {})
    return
  }

  // paste
  if (isTerminalPasteShortcut(event as any)) {
    event.preventDefault()
    event.stopPropagation()
    void pasteClipboardIntoTerminal(terminal as any).catch(() => {})
  }
}

function isApplePlatform() {
  if (typeof navigator === 'undefined') return false
  return /Mac|iPhone|iPad|iPod/i.test(navigator.platform)
}

function isWindowsPlatform() {
  if (typeof navigator === 'undefined') return false
  return /Win/i.test(navigator.platform || navigator.userAgent)
}

function normalizedKey(event: { key: string }) {
  return event.key.toLowerCase()
}

function isTerminalCopyShortcut(
  event: { altKey: boolean; ctrlKey: boolean; key: string; metaKey: boolean; shiftKey: boolean },
  terminal: { hasSelection: () => boolean },
) {
  if (event.altKey || !terminal.hasSelection()) return false
  const key = normalizedKey(event)
  if (isApplePlatform()) return event.metaKey && !event.ctrlKey && key === 'c'
  if (key === 'insert') return event.ctrlKey && !event.shiftKey && !event.metaKey
  if (isWindowsPlatform() && event.ctrlKey && !event.metaKey && !event.shiftKey && key === 'c') return true
  return event.ctrlKey && !event.metaKey && event.shiftKey && key === 'c'
}

function isTerminalPasteShortcut(
  event: { altKey: boolean; ctrlKey: boolean; key: string; metaKey: boolean; shiftKey: boolean },
) {
  if (event.altKey) return false
  const key = normalizedKey(event)
  if (isApplePlatform()) return event.metaKey && !event.ctrlKey && key === 'v'
  if (key === 'insert') return event.shiftKey && !event.ctrlKey && !event.metaKey
  if (isWindowsPlatform() && event.ctrlKey && !event.metaKey && !event.shiftKey && key === 'v') return true
  return event.ctrlKey && !event.metaKey && event.shiftKey && key === 'v'
}

async function copyTerminalSelection(terminal: { getSelection: () => string; focus: () => void }) {
  const text = terminal.getSelection()
  if (!text) return
  await getDesktopHost().clipboard.writeText(text)
  terminal.focus()
}

async function pasteClipboardIntoTerminal(terminal: { paste: (s: string) => void; focus: () => void }) {
  const text = await getDesktopHost().clipboard.readText()
  if (!text) return
  terminal.paste(text)
  terminal.focus()
}
</script>

<style scoped>
/* No additional styles — all Tailwind classes are verbatim from React */
</style>
