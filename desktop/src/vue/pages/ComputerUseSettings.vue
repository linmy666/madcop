<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  computerUseApi,
  type ComputerUseStatus,
  type SetupResult,
  type InstalledApp,
  type AuthorizedApp,
} from '../api/computerUse'
import { useTranslation } from '../i18n'
import { getDesktopHost } from '../lib/desktopHost'

type CheckState = 'loading' | 'ready' | 'error'

const PYTHON_DOWNLOAD_URLS: Record<string, string> = {
  darwin: 'https://www.python.org/downloads/macos/',
  win32: 'https://www.python.org/downloads/windows/',
}

const t = useTranslation()

// ─── Reactive state ───────────────────────────────────────────────
const status = ref<ComputerUseStatus | null>(null)
const checkState = ref<CheckState>('loading')
const setupRunning = ref(false)
const setupResult = ref<SetupResult | null>(null)

// App authorization
const installedApps = ref<InstalledApp[]>([])
const authorizedBundleIds = ref<Set<string>>(new Set())
const authorizedApps = ref<AuthorizedApp[]>([])
const appsLoading = ref(false)
const appsSaved = ref(false)
const searchQuery = ref('')

const computerUseEnabled = ref(true)
const clipboardAccess = ref(true)
const systemKeys = ref(true)
const pythonPathDraft = ref('')
const pythonPathSaved = ref('')
const pythonPathSaving = ref(false)
const pythonPathMessage = ref<string | null>(null)

// Stale-request guard (replaces useRef(0))
const configMutationSeq = ref(0)

// ─── Fetch functions ──────────────────────────────────────────────
async function fetchStatus() {
  checkState.value = 'loading'
  try {
    const s = await computerUseApi.getStatus()
    status.value = s
    checkState.value = 'ready'
  } catch {
    checkState.value = 'error'
  }
}

function applyConfig(
  configResult: ReturnType<typeof computerUseApi.getAuthorizedApps> extends Promise<infer R> ? R : never,
  requestSeq = configMutationSeq.value,
) {
  if (requestSeq !== configMutationSeq.value) return
  computerUseEnabled.value = configResult.enabled
  authorizedApps.value = configResult.authorizedApps
  authorizedBundleIds.value = new Set(configResult.authorizedApps.map((a: AuthorizedApp) => a.bundleId))
  clipboardAccess.value = configResult.grantFlags.clipboardRead
  systemKeys.value = configResult.grantFlags.systemKeyCombos
  pythonPathDraft.value = configResult.pythonPath ?? ''
  pythonPathSaved.value = configResult.pythonPath ?? ''
}

async function fetchConfig() {
  const requestSeq = configMutationSeq.value
  try {
    applyConfig(await computerUseApi.getAuthorizedApps(), requestSeq)
  } catch {
    // API not ready
  }
}

async function fetchApps() {
  const requestSeq = configMutationSeq.value
  appsLoading.value = true
  try {
    const [appsResult, configResult] = await Promise.all([
      computerUseApi.getInstalledApps(),
      computerUseApi.getAuthorizedApps(),
    ])
    installedApps.value = appsResult.apps
    applyConfig(configResult, requestSeq)
  } catch {
    // API not ready
  } finally {
    appsLoading.value = false
  }
}

// ─── Lifecycle ────────────────────────────────────────────────────
onMounted(() => {
  fetchStatus()
  fetchConfig()
})

// Derived
const envReady = computed(
  () => status.value?.venv.created && status.value?.dependencies.installed,
)

watch(envReady, (ready) => {
  if (ready) fetchApps()
})

// ─── Handlers ─────────────────────────────────────────────────────
async function handleSetup() {
  setupRunning.value = true
  setupResult.value = null
  try {
    const result = await computerUseApi.runSetup()
    setupResult.value = result
    await fetchStatus()
    if (result.success) await fetchApps()
  } catch {
    setupResult.value = {
      success: false,
      steps: [{ name: 'error', ok: false, message: 'Request failed' }],
    }
  } finally {
    setupRunning.value = false
  }
}

function toggleApp(app: InstalledApp) {
  configMutationSeq.value += 1
  const newSet = new Set(authorizedBundleIds.value)
  let newAuthorized = [...authorizedApps.value]
  if (newSet.has(app.bundleId)) {
    newSet.delete(app.bundleId)
    newAuthorized = newAuthorized.filter((a: AuthorizedApp) => a.bundleId !== app.bundleId)
  } else {
    newSet.add(app.bundleId)
    newAuthorized.push({
      bundleId: app.bundleId,
      displayName: app.displayName,
      authorizedAt: new Date().toISOString(),
    })
  }
  authorizedBundleIds.value = newSet
  authorizedApps.value = newAuthorized

  // Auto-save
  computerUseApi.setAuthorizedApps({
    authorizedApps: newAuthorized,
    grantFlags: {
      clipboardRead: clipboardAccess.value,
      clipboardWrite: clipboardAccess.value,
      systemKeyCombos: systemKeys.value,
    },
  }).then(() => {
    appsSaved.value = true
    setTimeout(() => (appsSaved.value = false), 1500)
  })
}

function toggleFlag(flag: 'clipboard' | 'systemKeys', value: boolean) {
  configMutationSeq.value += 1
  if (flag === 'clipboard') clipboardAccess.value = value
  else systemKeys.value = value

  computerUseApi.setAuthorizedApps({
    authorizedApps: authorizedApps.value,
    grantFlags: {
      clipboardRead: flag === 'clipboard' ? value : clipboardAccess.value,
      clipboardWrite: flag === 'clipboard' ? value : clipboardAccess.value,
      systemKeyCombos: flag === 'systemKeys' ? value : systemKeys.value,
    },
  })
}

function toggleComputerUseEnabled(value: boolean) {
  configMutationSeq.value += 1
  computerUseEnabled.value = value
  computerUseApi.setAuthorizedApps({ enabled: value }).then(() => {
    appsSaved.value = true
    setTimeout(() => (appsSaved.value = false), 1500)
  })
}

async function savePythonPath(value = pythonPathDraft.value) {
  configMutationSeq.value += 1
  const normalized = value.trim()
  pythonPathSaving.value = true
  pythonPathMessage.value = null
  try {
    await computerUseApi.setAuthorizedApps({ pythonPath: normalized || null })
    pythonPathDraft.value = normalized
    pythonPathSaved.value = normalized
    pythonPathMessage.value = t('settings.computerUse.pythonPathSaved')
    await fetchStatus()
  } catch {
    pythonPathMessage.value = t('settings.computerUse.pythonPathSaveFailed')
  } finally {
    pythonPathSaving.value = false
  }
}

async function choosePythonPath() {
  const host = getDesktopHost()
  if (!host.capabilities.dialogs) {
    pythonPathMessage.value = t('settings.computerUse.pythonPathDialogFailed')
    return
  }
  try {
    const selected = await host.dialogs.open({
      multiple: false,
      directory: false,
      title: t('settings.computerUse.pythonPathDialogTitle'),
    })
    const selectedPath = Array.isArray(selected) ? selected[0] : selected
    if (typeof selectedPath === 'string' && selectedPath.trim()) {
      pythonPathDraft.value = selectedPath
      await savePythonPath(selectedPath)
    }
  } catch {
    pythonPathMessage.value = t('settings.computerUse.pythonPathDialogFailed')
  }
}

// ─── Derived / computed ───────────────────────────────────────────
const allReady = computed(
  () =>
    status.value?.supported &&
    status.value?.python.installed &&
    status.value?.venv.created &&
    status.value?.dependencies.installed,
)

const accessibilityNeedsAttention = computed(
  () => status.value?.permissions.accessibility === false,
)
const screenRecordingNeedsAttention = computed(
  () => status.value?.permissions.screenRecording === false,
)
const screenRecordingReady = computed(
  () => (status.value ? status.value.permissions.screenRecording !== false : null),
)

const pythonDownloadUrl = computed(() =>
  status.value
    ? PYTHON_DOWNLOAD_URLS[status.value.platform] ?? 'https://www.python.org/downloads/'
    : 'https://www.python.org/downloads/',
)

const pythonPathDirty = computed(
  () => pythonPathDraft.value.trim() !== pythonPathSaved.value,
)

const pythonDetail = computed(() => {
  if (!status.value) return ''
  if (status.value.python.installed) {
    return `${t('settings.computerUse.pythonFound')} — ${status.value.python.version} (${status.value.python.path})`
  }
  if (status.value.python.source === 'custom') {
    return `${t('settings.computerUse.pythonCustomInvalid')} — ${status.value.python.path}${status.value.python.error ? `: ${status.value.python.error}` : ''}`
  }
  return t('settings.computerUse.pythonNotFound')
})

const filteredApps = computed(() => {
  if (!searchQuery.value) return installedApps.value
  const q = searchQuery.value.toLowerCase()
  return installedApps.value.filter(
    (a: InstalledApp) =>
      a.displayName.toLowerCase().includes(q) || a.bundleId.toLowerCase().includes(q),
  )
})

const sortedApps = computed(() => {
  return [...filteredApps.value].sort((a, b) => {
    const aAuth = authorizedBundleIds.value.has(a.bundleId) ? 0 : 1
    const bAuth = authorizedBundleIds.value.has(b.bundleId) ? 0 : 1
    if (aAuth !== bAuth) return aAuth - bAuth
    return a.displayName.localeCompare(b.displayName)
  })
})
</script>

<template>
  <div class="max-w-2xl space-y-6">
    <!-- Title -->
    <div>
      <div class="flex items-center justify-between gap-4">
        <h2 class="text-lg font-semibold text-[var(--color-text-primary)]">
          {{ t('settings.computerUse.title') }}
        </h2>
        <label
          class="flex items-center gap-2 text-sm text-[var(--color-text-secondary)] cursor-pointer"
        >
          <input
            type="checkbox"
            :checked="computerUseEnabled"
            @change="toggleComputerUseEnabled(($event.target as HTMLInputElement).checked)"
            class="rounded border-[var(--color-border)] accent-[var(--color-brand)]"
          />
          {{ t('settings.computerUse.enabledToggle') }}
        </label>
      </div>
      <p class="mt-1 text-sm text-[var(--color-text-secondary)]">
        {{ t('settings.computerUse.description') }}
      </p>
    </div>

    <div
      v-if="!computerUseEnabled"
      class="px-4 py-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30 text-sm text-yellow-700"
    >
      {{ t('settings.computerUse.disabledHint') }}
    </div>

    <!-- Loading / Error states -->
    <div
      v-if="checkState === 'loading'"
      class="py-8 text-center text-sm text-[var(--color-text-tertiary)]"
    >
      {{ t('common.loading') }}
    </div>

    <div
      v-else-if="checkState === 'error'"
      class="py-8 text-center text-sm text-red-400"
    >
      Failed to check status.
      <button @click="fetchStatus" class="ml-2 underline">
        {{ t('common.retry') }}
      </button>
    </div>

    <!-- Status content -->
    <template v-else-if="status">
      <div
        v-if="!status.supported"
        class="px-4 py-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30 text-sm text-yellow-600"
      >
        {{ t('settings.computerUse.notSupported') }}
      </div>

      <!-- Status checks -->
      <div class="space-y-2">
        <StatusRow
          :label="t('settings.computerUse.python')"
          :ok="status.python.installed"
          :detail="pythonDetail"
        />
        <StatusRow
          :label="t('settings.computerUse.venv')"
          :ok="status.venv.created"
          :detail="
            status.venv.created
              ? `${t('settings.computerUse.venvReady')} — ${status.venv.path}`
              : t('settings.computerUse.venvNotReady')
          "
        />
        <StatusRow
          :label="t('settings.computerUse.deps')"
          :ok="status.dependencies.installed"
          :detail="
            status.dependencies.installed
              ? t('settings.computerUse.depsReady')
              : t('settings.computerUse.depsNotReady')
          "
        />
      </div>

      <!-- Python path field -->
      <div
        class="space-y-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-4"
      >
        <label
          for="computer-use-python-path"
          class="block text-sm font-medium text-[var(--color-text-primary)]"
        >
          {{ t('settings.computerUse.pythonPathLabel') }}
        </label>
        <div class="flex flex-wrap gap-2">
          <input
            id="computer-use-python-path"
            type="text"
            :value="pythonPathDraft"
            @input="
              pythonPathDraft = ($event.target as HTMLInputElement).value;
              pythonPathMessage = null
            "
            :placeholder="t('settings.computerUse.pythonPathPlaceholder')"
            class="min-w-[220px] flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container)] px-3 py-2 font-mono text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] focus:border-[var(--color-brand)] focus:outline-none"
          />
          <button
            @click="choosePythonPath"
            :disabled="pythonPathSaving"
            class="flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-2 text-xs font-medium text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] disabled:opacity-50"
          >
            <span class="material-symbols-outlined text-[16px]">folder_open</span>
            {{ t('settings.computerUse.pythonPathBrowse') }}
          </button>
          <button
            @click="savePythonPath()"
            :disabled="pythonPathSaving || !pythonPathDirty"
            class="flex items-center gap-1.5 rounded-lg bg-[var(--color-brand)] px-3 py-2 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
          >
            <span class="material-symbols-outlined text-[16px]">
              {{ pythonPathSaving ? 'hourglass_empty' : 'save' }}
            </span>
            {{ t('settings.computerUse.pythonPathSave') }}
          </button>
          <button
            v-if="pythonPathSaved"
            @click="savePythonPath('')"
            :disabled="pythonPathSaving"
            class="flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-2 text-xs font-medium text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] disabled:opacity-50"
          >
            <span class="material-symbols-outlined text-[16px]">restart_alt</span>
            {{ t('settings.computerUse.pythonPathAuto') }}
          </button>
        </div>
        <p class="text-xs text-[var(--color-text-tertiary)]">
          {{ pythonPathMessage ?? t('settings.computerUse.pythonPathHint') }}
        </p>
      </div>

      <!-- macOS Permissions — only shown on darwin -->
      <template v-if="envReady && status.platform === 'darwin'">
        <StatusRow
          :label="t('settings.computerUse.accessibility')"
          :ok="status.permissions.accessibility ?? null"
          :detail="
            status.permissions.accessibility === null
              ? t('settings.computerUse.permUnknown')
              : status.permissions.accessibility
                ? t('settings.computerUse.permGranted')
                : t('settings.computerUse.permDenied')
          "
        />
        <StatusRow
          :label="t('settings.computerUse.screenRecording')"
          :ok="screenRecordingReady"
          :detail="
            status.permissions.screenRecording === true
              ? t('settings.computerUse.permGranted')
              : status.permissions.screenRecording === false
                ? t('settings.computerUse.permDenied')
                : t('settings.computerUse.permScreenRecordingUnknownSoft')
          "
        />
        <div
          v-if="accessibilityNeedsAttention || screenRecordingNeedsAttention"
          class="flex flex-col gap-2 px-4 py-3 rounded-lg bg-yellow-500/5 border border-yellow-500/20"
        >
          <p class="text-xs text-[var(--color-text-tertiary)]">
            {{ t('settings.computerUse.permRestartHint') }}
          </p>
          <div class="flex gap-2">
            <button
              v-if="accessibilityNeedsAttention"
              @click="
                () =>
                  computerUseApi.openSettings('Privacy_Accessibility')
              "
              class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-[var(--color-text-accent)] border border-[var(--color-border)] rounded-lg hover:bg-[var(--color-surface-hover)]"
            >
              <span class="material-symbols-outlined text-[14px]">open_in_new</span>
              {{ t('settings.computerUse.openAccessibility') }}
            </button>
            <button
              v-if="screenRecordingNeedsAttention"
              @click="
                () =>
                  computerUseApi.openSettings('Privacy_ScreenCapture')
              "
              class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-[var(--color-text-accent)] border border-[var(--color-border)] rounded-lg hover:bg-[var(--color-surface-hover)]"
            >
              <span class="material-symbols-outlined text-[14px]">open_in_new</span>
              {{ t('settings.computerUse.openScreenRecording') }}
            </button>
          </div>
        </div>
      </template>

      <!-- All ready banner -->
      <div
        v-if="
          allReady &&
          (status.platform !== 'darwin' ||
            (status.permissions.accessibility && screenRecordingReady))
        "
        class="px-4 py-3 rounded-lg bg-green-500/10 border border-green-500/30 text-sm text-green-600 flex items-center gap-2"
      >
        <span
          class="material-symbols-outlined text-[18px]"
          style="fontVariationSettings: 'FILL' 1"
        >
          verified
        </span>
        {{ t('settings.computerUse.allReady') }}
      </div>

      <!-- Setup result -->
      <div
        v-if="setupResult"
        :class="`rounded-lg border p-4 space-y-2 ${setupResult.success ? 'bg-green-500/5 border-green-500/30' : 'bg-red-500/5 border-red-500/30'}`"
      >
        <div
          :class="`text-sm font-medium ${setupResult.success ? 'text-green-600' : 'text-red-400'}`"
        >
          {{ setupResult.success ? t('settings.computerUse.setupSuccess') : t('settings.computerUse.setupFail') }}
        </div>
        <div
          v-for="(step, i) in setupResult.steps"
          :key="i"
          class="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]"
        >
          <StatusIcon :ok="step.ok" />
          <span>{{ step.message }}</span>
        </div>
      </div>

      <!-- Action buttons -->
      <div class="flex gap-3">
        <button
          v-if="!status.python.installed"
          @click="
            () =>
              getDesktopHost()
                .shell.open(pythonDownloadUrl)
                .catch(() => window.open(pythonDownloadUrl, '_blank', 'noopener,noreferrer'))
          "
          class="flex items-center gap-2 px-5 py-2.5 bg-[var(--color-brand)] text-white text-sm font-semibold rounded-lg hover:opacity-90 transition-opacity"
        >
          <span class="material-symbols-outlined text-[18px]">open_in_new</span>
          {{ t('settings.computerUse.downloadPython') }}
        </button>
        <button
          v-if="!envReady && status.python.installed"
          @click="handleSetup"
          :disabled="setupRunning"
          class="flex items-center gap-2 px-5 py-2.5 bg-[var(--color-brand)] text-white text-sm font-semibold rounded-lg hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          <span class="material-symbols-outlined text-[18px]">
            {{ setupRunning ? 'hourglass_empty' : 'download' }}
          </span>
          {{ setupRunning ? t('settings.computerUse.setupRunning') : t('settings.computerUse.setupBtn') }}
        </button>
        <button
          @click="fetchStatus"
          class="flex items-center gap-2 px-4 py-2.5 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] border border-[var(--color-border)] rounded-lg hover:bg-[var(--color-surface-hover)] transition-colors"
        >
          <span class="material-symbols-outlined text-[18px]">refresh</span>
          {{ t('settings.computerUse.recheckBtn') }}
        </button>
      </div>

      <!-- ─── App Authorization Section ─── -->
      <div v-if="envReady" class="space-y-4 pt-4 border-t border-[var(--color-border)]">
        <div>
          <h3
            class="text-base font-semibold text-[var(--color-text-primary)] flex items-center gap-2"
          >
            {{ t('settings.computerUse.appsTitle') }}
            <span
              v-if="appsSaved"
              class="text-xs font-normal text-green-500 flex items-center gap-1"
            >
              <span
                class="material-symbols-outlined text-[14px]"
                style="fontVariationSettings: 'FILL' 1"
              >
                check
              </span>
              {{ t('settings.computerUse.appsSaved') }}
            </span>
          </h3>
          <p class="mt-1 text-sm text-[var(--color-text-secondary)]">
            {{ t('settings.computerUse.appsDescription') }}
          </p>
        </div>

        <!-- Grant flags -->
        <div class="flex gap-4">
          <label
            class="flex items-center gap-2 text-sm text-[var(--color-text-secondary)] cursor-pointer"
          >
            <input
              type="checkbox"
              :checked="clipboardAccess"
              @change="toggleFlag('clipboard', ($event.target as HTMLInputElement).checked)"
              class="rounded border-[var(--color-border)] accent-[var(--color-brand)]"
            />
            {{ t('settings.computerUse.flagClipboard') }}
          </label>
          <label
            class="flex items-center gap-2 text-sm text-[var(--color-text-secondary)] cursor-pointer"
          >
            <input
              type="checkbox"
              :checked="systemKeys"
              @change="toggleFlag('systemKeys', ($event.target as HTMLInputElement).checked)"
              class="rounded border-[var(--color-border)] accent-[var(--color-brand)]"
            />
            {{ t('settings.computerUse.flagSystemKeys') }}
          </label>
        </div>

        <!-- Search -->
        <div class="relative">
          <span
            class="material-symbols-outlined text-[18px] text-[var(--color-text-tertiary)] absolute left-3 top-1/2 -translate-y-1/2"
          >
            search
          </span>
          <input
            type="text"
            :value="searchQuery"
            @input="searchQuery = ($event.target as HTMLInputElement).value"
            :placeholder="t('settings.computerUse.appsSearch')"
            class="w-full pl-9 pr-4 py-2 text-sm bg-[var(--color-surface-container-low)] border border-[var(--color-border)] rounded-lg text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] focus:outline-none focus:border-[var(--color-brand)]"
          />
        </div>

        <!-- App list -->
        <div
          v-if="appsLoading"
          class="py-6 text-center text-sm text-[var(--color-text-tertiary)]"
        >
          {{ t('settings.computerUse.appsLoading') }}
        </div>
        <div
          v-else-if="installedApps.length === 0"
          class="py-6 text-center text-sm text-[var(--color-text-tertiary)]"
        >
          {{ t('settings.computerUse.appsEmpty') }}
        </div>
        <div
          v-else
          class="max-h-[400px] overflow-y-auto rounded-lg border border-[var(--color-border)]"
        >
          <button
            v-for="app in sortedApps"
            :key="app.bundleId"
            @click="toggleApp(app)"
            :class="`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-[var(--color-surface-hover)] border-b border-[var(--color-border)] last:border-b-0 ${
              authorizedBundleIds.has(app.bundleId) ? 'bg-[var(--color-brand)]/5' : ''
            }`"
          >
            <div
              :class="`w-5 h-5 rounded flex items-center justify-center flex-shrink-0 border ${
                authorizedBundleIds.has(app.bundleId)
                  ? 'bg-[var(--color-brand)] border-[var(--color-brand)]'
                  : 'border-[var(--color-border)]'
              }`"
            >
              <span
                v-if="authorizedBundleIds.has(app.bundleId)"
                class="material-symbols-outlined text-[14px] text-white"
                style="fontVariationSettings: 'FILL' 1"
              >
                check
              </span>
            </div>
            <div class="flex-1 min-w-0">
              <div
                class="text-sm font-medium text-[var(--color-text-primary)] truncate"
              >
                {{ app.displayName }}
              </div>
              <div
                class="text-[11px] text-[var(--color-text-tertiary)] truncate font-mono"
              >
                {{ app.bundleId }}
              </div>
            </div>
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script lang="ts">
// Keep the local sub-components inline as sibling script blocks
import { defineComponent } from 'vue'

export const StatusIcon = defineComponent({
  props: {
    ok: { type: Boolean as () => boolean | null, required: true },
  },
  setup(props) {
    return () => {
      if (props.ok === null) {
        return (
          <span class="material-symbols-outlined text-[18px] text-[var(--color-text-tertiary)]">
            help
          </span>
        )
      }
      return props.ok
        ? (
            <span
              class="material-symbols-outlined text-[18px] text-green-500"
              style={{ fontVariationSettings: "'FILL' 1" }}
            >
              check_circle
            </span>
          )
        : (
            <span
              class="material-symbols-outlined text-[18px] text-red-400"
              style={{ fontVariationSettings: "'FILL' 1" }}
            >
              cancel
            </span>
          )
    }
  },
})

export const StatusRow = defineComponent({
  props: {
    label: { type: String, required: true },
    ok: { type: Boolean as () => boolean | null, required: true },
    detail: { type: String, required: true },
  },
  setup(props) {
    return () => (
      <div class="flex items-center gap-3 py-2.5 px-4 rounded-lg bg-[var(--color-surface-container-low)]">
        <StatusIcon ok={props.ok} />
        <div class="flex-1 min-w-0">
          <span class="text-sm font-medium text-[var(--color-text-primary)]">{props.label}</span>
          <span class="ml-2 text-xs text-[var(--color-text-tertiary)]">{props.detail}</span>
        </div>
      </div>
    )
  },
})
</script>
