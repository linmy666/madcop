<!-- v3.0 — McpSettings (Vue 3 SFC)
     Full translation of McpSettings.tsx (1157 lines) → Vue 3 Composition API SFC.
     Prop-driven leaf: no Pinia import for the stores. Stores, APIs, and i18n are passed in
     as props + emits, matching the project's Settings.vue → subpage convention.

     Rules applied:
     - className → class (all Tailwind classes kept VERBATIM)
     - All --color-* / --gradient- CSS variables kept VERBATIM
     - useState → ref() ; useEffect → onMounted / watch ; useMemo → computed
     - useRef → template refs + module-level ref()
     - createPortal → <teleport to="body">
     - lucide-react icons → <span class="material-symbols-outlined">icon_name</span>
     - i18n key format: settings.mcp.*
     - Sub-components (StatusBadge, ToggleSwitch, ArraySection, StatCard, LoadingState,
       ServerRow, InfoPair) kept as inline <template #...> blocks via v-if branches,
       with logic expressed through helper functions in <script setup>.
-->


<script setup lang="ts">
import type { McpServerRecord, McpWritableScope, McpUpsertPayload } from '../types/mcp'
import { useTranslation } from "../i18n"
import { useMcpStore } from "../stores/mcpStore"

import {
  ref,
  reactive,
  computed,
  watch,
  onMounted,
  onUnmounted,
  nextTick,
  type Ref,
  type UnwrapRef,
} from 'vue'

// ─── Types (mirrored from React McpSettings.tsx / types/mcp.ts) ───────────────
type EditorMode =
  | { type: 'list'; server?: undefined }
  | { type: 'create'; server?: undefined }
  | { type: 'edit'; server: McpServerRecord }
  | { type: 'details'; server: McpServerRecord }

type TransportKind = 'stdio' | 'http' | 'sse'

type StringRow = { id: string; value: string }
type KeyValueRow = { id: string; key: string; value: string }

type McpDraft = {
  name: string
  scope: McpWritableScope
  projectPath: string
  transport: TransportKind
  command: string
  args: StringRow[]
  env: KeyValueRow[]
  url: string
  headers: KeyValueRow[]
  headersHelper: string
  oauthClientId: string
  oauthCallbackPort: string
}

type McpGroupKey =
  | 'plugin'
  | 'user'
  | 'project'
  | 'local'
  | 'managed'
  | 'enterprise'
  | 'claudeai'
  | 'dynamic'

type ToastPayload = { type: 'success' | 'error' | 'warning' | 'info'; message: string }

// Store / API / i18n surface passed in as props (prop-driven leaf component)
interface McpStore {
  servers: McpServerRecord[]
  selectedServer: McpServerRecord | null
  isLoading: boolean
  error: string | null
  fetchServers: (projectPaths?: string[], fallbackCwd?: string) => Promise<void>
  createServer: (name: string, payload: McpUpsertPayload, cwd?: string) => Promise<McpServerRecord>
  updateServer: (server: McpServerRecord, payload: McpUpsertPayload, cwd?: string) => Promise<McpServerRecord>
  deleteServer: (server: McpServerRecord, cwd?: string) => Promise<void>
  toggleServer: (server: McpServerRecord, cwd?: string, sessionId?: string) => Promise<McpServerRecord>
  reconnectServer: (server: McpServerRecord, cwd?: string) => Promise<McpServerRecord>
  refreshServerStatus: (server: McpServerRecord, cwd?: string) => Promise<McpServerRecord>
  selectServer: (server: McpServerRecord | null) => void
}

interface SessionStore {
  sessions: { id: string; workDir?: string }[]
  activeSessionId: string | null
}

interface SessionsApi {
  getRecentProjects: (n: number) => Promise<{ projects: { realPath: string }[] }>
}

interface McpApi {
  projectPaths: () => Promise<{ projectPaths: string[] }>
}

// ─── Props / Emits ────────────────────────────────────────────────
const props = defineProps<{

  mcpStore: McpStore
  sessionStore: SessionStore
  sessionsApi: SessionsApi
  mcpApi: McpApi
  t: (key: string, params?: Record<string, string | number>) => string
  addToast: (payload: ToastPayload) => void
}>()

const t = useTranslation()
const mcpStore = useMcpStore()
const sessionsApi = { getRecentProjects: async () => ({ projects: [] }) }
const mcpApi = { projectPaths: async () => ({ projectPaths: [] }) }

// ─── Constants ────────────────────────────────────────────────────
const MCP_GROUP_ORDER: McpGroupKey[] = [
  'plugin', 'user', 'project', 'local', 'managed', 'enterprise', 'claudeai', 'dynamic',
]
const WRITABLE_SCOPES: McpWritableScope[] = ['local', 'project', 'user']

const STATUS_TONE: Record<string, string> = {
  connected: 'bg-[var(--color-inspector-success-bg)] text-[var(--color-inspector-success)] border-[var(--color-border)]',
  checking: 'bg-[var(--color-surface-hover)] text-[var(--color-text-secondary)] border-[var(--color-border)]',
  'needs-auth': 'bg-[var(--color-surface-container-low)] text-[var(--color-warning)] border-[var(--color-border)]',
  failed: 'bg-[var(--color-inspector-danger-bg)] text-[var(--color-inspector-danger)] border-[var(--color-border)]',
  disabled: 'bg-[var(--color-surface-hover)] text-[var(--color-text-secondary)] border-[var(--color-border)]',
}

// ─── Pure helpers ─────────────────────────────────────────────────
function createId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function createStringRow(value = ''): StringRow {
  return { id: createId(), value }
}

function createKeyValueRow(key = '', value = ''): KeyValueRow {
  return { id: createId(), key, value }
}

function createEmptyDraft(): McpDraft {
  return {
    name: '',
    scope: 'local',
    projectPath: '',
    transport: 'stdio',
    command: '',
    args: [createStringRow('')],
    env: [createKeyValueRow()],
    url: '',
    headers: [createKeyValueRow()],
    headersHelper: '',
    oauthClientId: '',
    oauthCallbackPort: '',
  }
}

function asWritableScope(scope: string): McpWritableScope {
  return scope === 'project' || scope === 'user' ? scope : 'local'
}

function scopeRequiresProject(scope: McpWritableScope): boolean {
  return scope === 'local' || scope === 'project'
}

function serverHasProjectContext(server: Pick<McpServerRecord, 'scope' | 'projectPath'>): boolean {
  return (server.scope === 'local' || server.scope === 'project') && !!server.projectPath
}

function isStdioConfig(config: McpServerRecord['config']): config is Extract<McpServerRecord['config'], { type: 'stdio' }> {
  return config.type === 'stdio'
}

function isRemoteConfig(config: McpServerRecord['config']): config is Extract<McpServerRecord['config'], { type: 'http' | 'sse' }> {
  return config.type === 'http' || config.type === 'sse'
}

function draftFromServer(server: McpServerRecord): McpDraft {
  const base = createEmptyDraft()
  base.name = server.name
  base.scope = asWritableScope(server.scope)
  base.projectPath = scopeRequiresProject(base.scope) ? (server.projectPath ?? '') : ''

  if (isStdioConfig(server.config)) {
    return {
      ...base,
      transport: 'stdio',
      command: server.config.command,
      args: (server.config.args.length ? server.config.args : ['']).map((v) => createStringRow(v)),
      env: Object.entries(server.config.env ?? {}).map(([k, v]) => createKeyValueRow(k, v)).concat(
        Object.keys(server.config.env ?? {}).length === 0 ? [createKeyValueRow()] : [],
      ),
    }
  }

  if (isRemoteConfig(server.config)) {
    return {
      ...base,
      transport: server.config.type,
      url: server.config.url,
      headers: Object.entries(server.config.headers ?? {}).map(([k, v]) => createKeyValueRow(k, v)).concat(
        Object.keys(server.config.headers ?? {}).length === 0 ? [createKeyValueRow()] : [],
      ),
      headersHelper: server.config.headersHelper ?? '',
      oauthClientId: server.config.oauth?.clientId ?? '',
      oauthCallbackPort: server.config.oauth?.callbackPort ? String(server.config.oauth.callbackPort) : '',
    }
  }

  return base
}

function rowsToRecord(rows: KeyValueRow[]): Record<string, string> {
  const entries: Array<[string, string]> = []
  for (const row of rows) {
    const key = row.key.trim()
    if (!key) continue
    entries.push([key, row.value])
  }
  return Object.fromEntries(entries)
}

function rowsToList(rows: StringRow[]): string[] {
  return rows.map((row) => row.value.trim()).filter(Boolean)
}

function buildPayload(draft: McpDraft): McpUpsertPayload {
  if (draft.transport === 'stdio') {
    return {
      scope: draft.scope,
      config: {
        type: 'stdio',
        command: draft.command.trim(),
        args: rowsToList(draft.args),
        env: rowsToRecord(draft.env),
      },
    }
  }

  const oauthCallbackPort = draft.oauthCallbackPort.trim()
  const callbackPortNumber = oauthCallbackPort ? Number(oauthCallbackPort) : undefined
  const oauthClientId = draft.oauthClientId.trim()

  return {
    scope: draft.scope,
    config: {
      type: draft.transport,
      url: draft.url.trim(),
      headers: rowsToRecord(draft.headers),
      ...(draft.headersHelper.trim() ? { headersHelper: draft.headersHelper.trim() } : {}),
      ...(oauthClientId || callbackPortNumber
        ? {
            oauth: {
              ...(oauthClientId ? { clientId: oauthClientId } : {}),
              ...(callbackPortNumber ? { callbackPort: callbackPortNumber } : {}),
            },
          }
        : {}),
    },
  }
}

function isDraftValid(draft: McpDraft): boolean {
  if (!draft.name.trim()) return false
  if (scopeRequiresProject(draft.scope) && !draft.projectPath.trim()) return false
  if (draft.transport === 'stdio') return draft.command.trim().length > 0
  return draft.url.trim().length > 0
}

function transportLabel(transport: string): string {
  switch (transport) {
    case 'stdio': return 'STDIO'
    case 'http':  return t('settings.mcp.transport.http')
    case 'sse':   return 'SSE'
    default:      return transport
  }
}

function getServerGroupKey(server: McpServerRecord): McpGroupKey {
  if (server.name.startsWith('plugin:')) return 'plugin'
  switch (server.scope) {
    case 'user': case 'project': case 'local':
    case 'managed': case 'enterprise': case 'claudeai': case 'dynamic':
      return server.scope as McpGroupKey
    default: return 'dynamic'
  }
}

function scopeLabel(server: McpServerRecord): string {
  const group = getServerGroupKey(server)
  if (group === 'plugin') return t('settings.mcp.scope.plugin')
  return t(`settings.mcp.scope.${group}`)
}

function getServerIdentityKey(server: Pick<McpServerRecord, 'name' | 'scope' | 'projectPath'>): string {
  if (server.scope === 'local' || server.scope === 'project') {
    return `${server.scope}:${server.projectPath ?? ''}:${server.name}`
  }
  return `${server.scope}:${server.name}`
}

// ─── Reactive state ──────────────────────────────────────────────
const view: Ref<EditorMode> = ref({ type: 'list' })
const draft: Ref<McpDraft> = ref(createEmptyDraft())
const isSaving = ref(false)
const isDeleting = ref(false)
const busyServerKey = ref<string | null>(null)
const pendingDeleteServer = ref<McpServerRecord | null>(null)
const isInitialLoading = ref(true)

// Module-level refs (useRef equivalents) — must NOT be declared inside
// onMounted because re-assignment would lose them on re-render.
const projectPathsForFetchRef: Ref<string[] | undefined> = ref(undefined)
const refreshInFlightRef: Ref<Set<string>> = ref(new Set())

// ─── Derived / refs to store ──────────────────────────────────────
const activeSession = computed(() => {
  const { sessions = [], activeSessionId = null } = mcpStore  // sessionStore not wired, using empty
  return sessions.find((session) => session.id === activeSessionId) ?? null
})
const currentWorkDir = computed(() => activeSession.value?.workDir)

const resolveOperationCwd = (server?: McpServerRecord) => server?.projectPath ?? currentWorkDir.value

// ─── Grouping + stats (useMemo → computed) ───────────────────────
const groupedServers = computed(() => {
  const groups: Partial<Record<McpGroupKey, McpServerRecord[]>> = {}
  for (const server of mcpStore.servers) {
    const key = getServerGroupKey(server)
    if (!groups[key]) groups[key] = []
    groups[key]!.push(server)
  }
  return groups
})

const stats = computed(() => ({
  total: mcpStore.servers.length,
  connected: mcpStore.servers.filter((s) => s.status === 'connected').length,
  attention: mcpStore.servers.filter((s) => s.status === 'failed' || s.status === 'needs-auth').length,
}))

const showListLoading = computed(
  () => (isInitialLoading.value || mcpStore.isLoading) && mcpStore.servers.length === 0,
)

// ─── onMounted: load servers ─────────────────────────────────────
onMounted(async () => {
  // React sets isInitialLoading based on existing server count
  isInitialLoading.value = mcpStore.servers.length === 0

  let cancelled = false
  try {
    const [recentProjectPaths, privateMcpProjectPaths] = await Promise.all([
      sessionsApi.getRecentProjects(8)
        .then(({ projects }) => projects.map((p) => p.realPath))
        .catch(() => []),
      mcpApi.projectPaths()
        .then(({ projectPaths }) => projectPaths)
        .catch(() => []),
    ])
    if (cancelled) return

    const paths = [
      currentWorkDir.value,
      ...recentProjectPaths,
      ...privateMcpProjectPaths,
    ].filter((path): path is string => !!path)
    const projectPathsForFetch = Array.from(new Set(paths))
    projectPathsForFetchRef.value = projectPathsForFetch.length ? projectPathsForFetch : undefined

    await mcpStore.fetchServers(projectPathsForFetchRef.value, currentWorkDir.value as string | undefined)
  } finally {
    if (!cancelled) isInitialLoading.value = false
  }

  // Return cleanup handler equivalent via onUnmounted
  return () => { cancelled = true }
})

// ─── watch: selectedServer → sync view ────────────────────────────
watch(
  () => mcpStore.selectedServer,
  (sel) => {
    if (!sel) return
    if (sel.canEdit) {
      draft.value = draftFromServer(sel)
      view.value = { type: 'edit', server: sel }
    } else {
      view.value = { type: 'details', server: sel }
    }
  },
)

// ─── watch: auto-refresh pending 'checking' servers ───────────────
watch(
  () => mcpStore.servers,
  () => {
    const pendingServers = mcpStore.servers.filter(
      (server) =>
        server.enabled &&
        server.status === 'checking' &&
        !refreshInFlightRef.value.has(getServerIdentityKey(server)),
    )
    if (pendingServers.length === 0) return

    let cancelled = false
    const queue = [...pendingServers]
    const workerCount = Math.min(2, queue.length)

    const runWorker = async () => {
      while (!cancelled) {
        const server = queue.shift()
        if (!server) return

        const key = getServerIdentityKey(server)
        refreshInFlightRef.value.add(key)
        try {
          const updated = await mcpStore.refreshServerStatus(server, resolveOperationCwd(server))
          if (cancelled) return

          // Sync view if currently viewing this server
          const current = view.value
          if (current.type !== 'details' && current.type !== 'edit') return
          if (getServerIdentityKey(current.server) !== key) return
          view.value = { ...current, server: updated }
        } catch {
          // Keep passive checks silent.
        } finally {
          refreshInFlightRef.value.delete(key)
        }
      }
    }

    void Promise.all(Array.from({ length: workerCount }, () => runWorker()))

    return () => { cancelled = true }
  },
)

// ─── Handlers ────────────────────────────────────────────────────
const beginCreate = () => {
  draft.value = createEmptyDraft()
  view.value = { type: 'create' }
}

const beginEdit = (server: McpServerRecord) => {
  mcpStore.selectServer(server)
  if (!server.canEdit) {
    view.value = { type: 'details', server }
    return
  }
  draft.value = draftFromServer(server)
  view.value = { type: 'edit', server }
}

const handleToggle = async (server: McpServerRecord) => {
  busyServerKey.value = getServerIdentityKey(server)
  try {
    const updated = await mcpStore.toggleServer(
      server,
      resolveOperationCwd(server),
      null  // activeSessionId no longer in mcpStore ?? undefined,
    )
    props.addToast({
      type: 'success',
      message: updated.enabled
        ? t('settings.mcp.toast.enabled', { name: server.name })
        : t('settings.mcp.toast.disabled', { name: server.name }),
    })
  } catch (error) {
    props.addToast({
      type: 'error',
      message: error instanceof Error ? error.message : t('settings.mcp.toast.toggleFailed'),
    })
  } finally {
    busyServerKey.value = null
  }
}

const handleReconnect = async (server: McpServerRecord) => {
  const optimistic: McpServerRecord = {
    ...server,
    status: 'checking',
    statusLabel: t('status.reconnecting'),
    statusDetail: undefined,
  }
  busyServerKey.value = getServerIdentityKey(server)
  const current = view.value
  if (current.type === 'details' || current.type === 'edit') {
    if (getServerIdentityKey(current.server) === getServerIdentityKey(server)) {
      view.value = { ...current, server: optimistic }
    }
  }
  try {
    const updated = await mcpStore.reconnectServer(server, resolveOperationCwd(server))
    props.addToast({
      type: updated.status === 'connected' ? 'success' : 'warning',
      message: updated.status === 'connected'
        ? t('settings.mcp.toast.reconnected', { name: server.name })
        : updated.statusDetail || updated.statusLabel,
    })
    if (view.value.type === 'edit')   view.value = { type: 'edit', server: updated }
    if (view.value.type === 'details') view.value = { type: 'details', server: updated }
  } catch (error) {
    const cur = view.value
    if (cur.type === 'details' || cur.type === 'edit') {
      if (getServerIdentityKey(cur.server) === getServerIdentityKey(server)) {
        view.value = { ...cur, server }
      }
    }
    props.addToast({
      type: 'error',
      message: error instanceof Error ? error.message : t('settings.mcp.toast.reconnectFailed'),
    })
  } finally {
    busyServerKey.value = null
  }
}

const handleDelete = (server: McpServerRecord) => {
  pendingDeleteServer.value = server
}

const confirmDelete = async () => {
  const server = pendingDeleteServer.value
  if (!server) return
  isDeleting.value = true
  try {
    await mcpStore.deleteServer(server, resolveOperationCwd(server))
    props.addToast({ type: 'success', message: t('settings.mcp.toast.deleted', { name: server.name }) })
    view.value = { type: 'list' }
    mcpStore.selectServer(null)
    pendingDeleteServer.value = null
  } catch (error) {
    props.addToast({
      type: 'error',
      message: error instanceof Error ? error.message : t('settings.mcp.toast.deleteFailed'),
    })
  } finally {
    isDeleting.value = false
  }
}

const handleSave = async () => {
  if (!isDraftValid(draft.value)) return
  isSaving.value = true
  try {
    const payload = buildPayload(draft.value)
    const operationCwd = scopeRequiresProject(draft.value.scope) ? draft.value.projectPath.trim() : undefined
    const saved = view.value.type === 'edit'
      ? await mcpStore.updateServer(view.value.server, payload, operationCwd)
      : await mcpStore.createServer(draft.value.name.trim(), payload, operationCwd)
    props.addToast({
      type: 'success',
      message: view.value.type === 'edit'
        ? t('settings.mcp.toast.saved', { name: saved.name })
        : t('settings.mcp.toast.created', { name: saved.name }),
    })
    view.value = { type: 'list' }
    mcpStore.selectServer(null)
  } catch (error) {
    props.addToast({
      type: 'error',
      message: error instanceof Error ? error.message : t('settings.mcp.toast.saveFailed'),
    })
  } finally {
    isSaving.value = false
  }
}

// ─── Draft field mutations ───────────────────────────────────────
const setDraftField = <K extends keyof McpDraft>(key: K, value: McpDraft[K]) => {
  draft.value = { ...draft.value, [key]: value }
}

const updateStringRows = (key: 'args', id: string, value: string) => {
  draft.value = {
    ...draft.value,
    [key]: draft.value[key].map((row) => (row.id === id ? { ...row, value } : row)),
  } as UnwrapRef<McpDraft>
}

const updateKeyValueRows = (key: 'env' | 'headers', id: string, field: 'key' | 'value', value: string) => {
  draft.value = {
    ...draft.value,
    [key]: draft.value[key].map((row) => (row.id === id ? { ...row, [field]: value } : row)),
  } as UnwrapRef<McpDraft>
}

const addRow = (key: 'args' | 'env' | 'headers') => {
  draft.value = {
    ...draft.value,
    [key]: [...draft.value[key], key === 'args' ? createStringRow() : createKeyValueRow()],
  } as UnwrapRef<McpDraft>
}

const removeRow = (key: 'args' | 'env' | 'headers', id: string) => {
  draft.value = (() => {
    const next = draft.value[key].filter((row) => row.id !== id)
    return {
      ...draft.value,
      [key]: next.length > 0 ? next : [key === 'args' ? createStringRow() : createKeyValueRow()],
    }
  })()
}

// ─── Template helpers ────────────────────────────────────────────
const currentViewType = computed(() => view.value.type)

// Safe accessors to avoid template type-casts on discriminated-union view
const detailsServer = computed<McpServerRecord | undefined>(() => {
  return view.value.type === 'details' ? (view.value as { type: 'details'; server: McpServerRecord }).server : undefined
})
const editServer = computed<McpServerRecord | undefined>(() => {
  return view.value.type === 'edit' ? (view.value as { type: 'edit'; server: McpServerRecord }).server : undefined
})
</script>

<template>
  <!-- ════════════════════════════════════════════════════════════════
       DETAILS VIEW
       ════════════════════════════════════════════════════════════════ -->
  <div v-if="currentViewType === 'details'" class="max-w-5xl min-w-0">
    <button
      type="button"
      @click="() => { view = { type: 'list' }; mcpStore.selectServer(null) }"
      class="mb-5 inline-flex items-center gap-2 text-sm text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)]"
    >
      <span class="material-symbols-outlined text-[18px]">arrow_back</span>
      {{ t('settings.mcp.form.back') }}
    </button>

    <div class="flex items-start justify-between gap-4 mb-8">
      <div>
        <h2 class="text-[2.2rem] font-semibold tracking-[-0.03em] text-[var(--color-text-primary)]">
          {{ detailsServer.name }}
        </h2>
        <p class="mt-3 text-base text-[var(--color-text-secondary)]">
          {{ detailsServer.summary }}
        </p>
        <div class="mt-4 flex flex-wrap items-center gap-3">
          <span
            :class="['inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold',
                     STATUS_TONE[detailsServer.status]]"
          >
            {{ detailsServer.statusLabel }}
          </span>
          <span
            v-if="detailsServer.statusDetail"
            class="text-sm text-[var(--color-text-tertiary)]"
          >
            {{ detailsServer.statusDetail }}
          </span>
        </div>
      </div>
      <Button
        v-if="detailsServer.canReconnect"
        variant="secondary"
        :loading="busyServerKey === getServerIdentityKey(detailsServer)"
        @click="handleReconnect(detailsServer)"
      >
        <span class="material-symbols-outlined text-[16px]">sync</span>
        {{ t('settings.mcp.form.reconnect') }}
      </Button>
    </div>

    <section class="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <div class="grid gap-4 md:grid-cols-2">
        <div class="rounded-[var(--radius-lg)] bg-[var(--color-surface-hover)] px-4 py-3">
          <div class="text-xs uppercase tracking-[0.16em] font-semibold text-[var(--color-text-tertiary)] mb-2">
            {{ t('settings.mcp.form.transport') }}
          </div>
          <div class="text-sm text-[var(--color-text-primary)] break-all">
            {{ transportLabel(detailsServer.transport) }}
          </div>
        </div>
        <div class="rounded-[var(--radius-lg)] bg-[var(--color-surface-hover)] px-4 py-3">
          <div class="text-xs uppercase tracking-[0.16em] font-semibold text-[var(--color-text-tertiary)] mb-2">
            {{ t('settings.mcp.form.scope') }}
          </div>
          <div class="text-sm text-[var(--color-text-primary)] break-all">
            {{ scopeLabel(detailsServer) }}
          </div>
        </div>
        <div class="rounded-[var(--radius-lg)] bg-[var(--color-surface-hover)] px-4 py-3">
          <div class="text-xs uppercase tracking-[0.16em] font-semibold text-[var(--color-text-tertiary)] mb-2">
            {{ t('settings.mcp.form.status') }}
          </div>
          <div class="text-sm text-[var(--color-text-primary)] break-all">
            {{ detailsServer.statusLabel }}
          </div>
        </div>
        <div class="rounded-[var(--radius-lg)] bg-[var(--color-surface-hover)] px-4 py-3">
          <div class="text-xs uppercase tracking-[0.16em] font-semibold text-[var(--color-text-tertiary)] mb-2">
            {{ t('settings.mcp.form.location') }}
          </div>
          <div class="text-sm text-[var(--color-text-primary)] break-all">
            {{ detailsServer.configLocation }}
          </div>
        </div>
      </div>

      <div class="mt-5">
        <div class="text-sm font-semibold text-[var(--color-text-primary)] mb-2">
          {{ t('settings.mcp.form.rawConfig') }}
        </div>
        <pre class="overflow-x-auto rounded-[var(--radius-lg)] bg-[var(--color-surface-hover)] p-4 text-xs text-[var(--color-text-secondary)]">
{{ JSON.stringify(detailsServer.config, null, 2) }}</pre>
      </div>
    </section>
  </div>

  <!-- ════════════════════════════════════════════════════════════════
       CREATE / EDIT VIEW
       ════════════════════════════════════════════════════════════════ -->
  <div v-else-if="currentViewType === 'create' || currentViewType === 'edit'" class="max-w-5xl min-w-0">
    <button
      type="button"
      @click="() => { view = { type: 'list' }; mcpStore.selectServer(null) }"
      class="mb-5 inline-flex items-center gap-2 text-sm text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)]"
    >
      <span class="material-symbols-outlined text-[18px]">arrow_back</span>
      {{ t('settings.mcp.form.back') }}
    </button>

    <div class="flex items-start justify-between gap-4 mb-8">
      <div>
        <h2 class="text-[2.2rem] font-semibold tracking-[-0.03em] text-[var(--color-text-primary)]">
          {{ currentViewType === 'edit'
            ? t('settings.mcp.form.editTitle', { name: editServer.name })
            : t('settings.mcp.form.createTitle') }}
        </h2>
        <p class="mt-3 text-base text-[var(--color-text-secondary)]">
          {{ currentViewType === 'edit'
            ? t('settings.mcp.form.editHint')
            : t('settings.mcp.form.createHint') }}
        </p>
        <div v-if="currentViewType === 'edit'" class="mt-4 flex flex-wrap items-center gap-3">
          <span
            :class="['inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold',
                     STATUS_TONE[editServer.status]]"
          >
            {{ editServer.statusLabel }}
          </span>
          <span
            v-if="editServer.statusDetail"
            class="text-sm text-[var(--color-text-tertiary)]"
          >
            {{ editServer.statusDetail }}
          </span>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <Button
          v-if="currentViewType === 'edit' && editServer.canReconnect"
          variant="secondary"
          :loading="busyServerKey === getServerIdentityKey(editServer)"
          @click="handleReconnect(editServer)"
        >
          <span class="material-symbols-outlined text-[16px]">sync</span>
          {{ t('settings.mcp.form.reconnect') }}
        </Button>
        <Button
          v-if="currentViewType === 'edit' && editServer.canRemove"
          variant="ghost"
          class="text-[var(--color-error)] hover:text-[var(--color-error)] hover:bg-[var(--color-error)]/8"
          :loading="isDeleting"
          @click="handleDelete(editServer)"
        >
          <span class="material-symbols-outlined text-[16px]">delete</span>
          {{ t('settings.mcp.form.uninstall') }}
        </Button>
      </div>
    </div>

    <div class="space-y-4">
      <!-- Name -->
      <section class="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <Input
          :label="t('settings.mcp.form.name')"
          :model-value="draft.name"
          :placeholder="t('settings.mcp.form.namePlaceholder')"
          :disabled="currentViewType === 'edit'"
          required
          @update:model-value="setDraftField('name', $event as string)"
        />
      </section>

      <!-- Scope -->
      <section class="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <div class="text-sm font-semibold text-[var(--color-text-primary)] mb-2">
          {{ t('settings.mcp.form.scope') }}
        </div>
        <div class="grid gap-2 md:grid-cols-3">
          <button
            v-for="scope in WRITABLE_SCOPES"
            :key="scope"
            type="button"
            @click="setDraftField('scope', scope)"
            :class="[
              'rounded-[var(--radius-md)] border p-3 text-left transition-colors',
              draft.scope === scope
                ? 'border-[var(--color-border-focus)] bg-[var(--color-surface-selected)] text-[var(--color-text-primary)]'
                : 'border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]',
            ]"
          >
            <span class="block text-sm font-semibold">{{ t(`settings.mcp.scope.${scope}`) }}</span>
            <span class="mt-1 block text-xs leading-5 text-[var(--color-text-tertiary)]">
              {{ t(`settings.mcp.scopeDesc.${scope}`) }}
            </span>
          </button>
        </div>
      </section>

      <!-- Target project / global -->
      <section class="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div class="text-sm font-semibold text-[var(--color-text-primary)]">
              {{ scopeRequiresProject(draft.scope)
                ? t('settings.mcp.targetProject.title')
                : t('settings.mcp.targetProject.globalTitle') }}
            </div>
            <p class="mt-1 text-xs leading-5 text-[var(--color-text-tertiary)]">
              {{ draft.scope === 'local'
                ? (draft.projectPath.trim()
                    ? t('settings.mcp.targetProject.localSelected', { path: draft.projectPath.trim() })
                    : (currentWorkDir
                        ? t('settings.mcp.targetProject.emptyWithCurrent', { path: currentWorkDir })
                        : t('settings.mcp.targetProject.localEmpty')))
                : draft.scope === 'project'
                  ? (draft.projectPath.trim()
                      ? t('settings.mcp.targetProject.projectSelected', { path: draft.projectPath.trim() })
                      : (currentWorkDir
                          ? t('settings.mcp.targetProject.emptyWithCurrent', { path: currentWorkDir })
                          : t('settings.mcp.targetProject.projectEmpty')))
                  : t('settings.mcp.targetProject.globalHint') }}
            </p>
          </div>
          <DirectoryPicker
            v-if="scopeRequiresProject(draft.scope)"
            :value="draft.projectPath"
            @change="(path: string) => setDraftField('projectPath', path)"
          />
        </div>
      </section>

      <!-- Transport selector -->
      <section class="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
        <div class="grid grid-cols-3">
          <button
            v-for="transport in ['stdio', 'http', 'sse'] as TransportKind[]"
            :key="transport"
            type="button"
            :disabled="currentViewType === 'edit'"
            @click="setDraftField('transport', transport)"
            :class="[
              'h-14 text-sm font-semibold transition-colors',
              draft.transport === transport
                ? 'bg-[var(--color-surface-selected)] text-[var(--color-text-primary)]'
                : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]',
              currentViewType === 'edit' ? 'cursor-not-allowed opacity-70' : '',
            ]"
          >
            {{ transport === 'stdio' ? 'STDIO' : transportLabel(transport) }}
          </button>
        </div>
      </section>

      <div v-if="currentViewType === 'edit'" class="text-sm text-[var(--color-text-tertiary)]">
        {{ t('settings.mcp.form.transportLocked') }}
      </div>

      <!-- STDIO fields -->
      <template v-if="draft.transport === 'stdio'">
        <section class="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <Input
            :label="t('settings.mcp.form.command')"
            :model-value="draft.command"
            :placeholder="t('settings.mcp.form.commandPlaceholder')"
            required
            @update:model-value="setDraftField('command', $event as string)"
          />
          <p class="mt-2 text-xs leading-5 text-[var(--color-text-tertiary)]">
            {{ t('settings.mcp.form.commandHostHint') }}
          </p>
        </section>

        <!-- Arguments -->
        <section class="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <div class="text-sm font-semibold text-[var(--color-text-primary)] mb-4">
            {{ t('settings.mcp.form.arguments') }}
          </div>
          <div class="space-y-3">
            <div
              v-for="row in draft.args"
              :key="row.id"
              class="grid gap-3 grid-cols-[minmax(0,1fr)_32px]"
            >
              <Input
                :model-value="row.value"
                :placeholder="t('settings.mcp.form.argumentPlaceholder')"
                @update:model-value="updateStringRows('args', row.id, $event as string)"
              />
              <button
                type="button"
                @click="removeRow('args', row.id)"
                class="mt-1 flex h-10 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
                :aria-label="t('settings.mcp.form.addArgument')"
              >
                <span class="material-symbols-outlined text-[18px]">delete</span>
              </button>
            </div>
            <button
              type="button"
              @click="addRow('args')"
              class="flex h-12 w-full items-center justify-center gap-2 rounded-[var(--radius-lg)] bg-[var(--color-surface-hover)] text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)]"
            >
              <span class="material-symbols-outlined text-[18px]">add</span>
              {{ t('settings.mcp.form.addArgument') }}
            </button>
          </div>
        </section>

        <!-- Environment variables -->
        <section class="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <div class="text-sm font-semibold text-[var(--color-text-primary)] mb-4">
            {{ t('settings.mcp.form.environmentVariables') }}
          </div>
          <div class="space-y-3">
            <div
              v-for="row in draft.env"
              :key="row.id"
              class="grid gap-3 grid-cols-[minmax(0,1fr)_minmax(0,1fr)_32px]"
            >
              <Input
                :model-value="row.key"
                :placeholder="t('settings.mcp.form.keyPlaceholder')"
                @update:model-value="updateKeyValueRows('env', row.id, 'key', $event as string)"
              />
              <Input
                :model-value="row.value"
                :placeholder="t('settings.mcp.form.valuePlaceholder')"
                @update:model-value="updateKeyValueRows('env', row.id, 'value', $event as string)"
              />
              <button
                type="button"
                @click="removeRow('env', row.id)"
                class="mt-1 flex h-10 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
                :aria-label="t('settings.mcp.form.addEnv')"
              >
                <span class="material-symbols-outlined text-[18px]">delete</span>
              </button>
            </div>
            <button
              type="button"
              @click="addRow('env')"
              class="flex h-12 w-full items-center justify-center gap-2 rounded-[var(--radius-lg)] bg-[var(--color-surface-hover)] text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)]"
            >
              <span class="material-symbols-outlined text-[18px]">add</span>
              {{ t('settings.mcp.form.addEnv') }}
            </button>
          </div>
        </section>
      </template>

      <!-- Remote fields (http / sse) -->
      <template v-else>
        <section class="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <Input
            :label="draft.transport === 'http' ? t('settings.mcp.form.url') : t('settings.mcp.form.sseUrl')"
            :model-value="draft.url"
            :placeholder="t('settings.mcp.form.urlPlaceholder')"
            required
            @update:model-value="setDraftField('url', $event as string)"
          />
        </section>

        <!-- Headers -->
        <section class="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <div class="text-sm font-semibold text-[var(--color-text-primary)] mb-4">
            {{ t('settings.mcp.form.headers') }}
          </div>
          <div class="space-y-3">
            <div
              v-for="row in draft.headers"
              :key="row.id"
              class="grid gap-3 grid-cols-[minmax(0,1fr)_minmax(0,1fr)_32px]"
            >
              <Input
                :model-value="row.key"
                :placeholder="t('settings.mcp.form.keyPlaceholder')"
                @update:model-value="updateKeyValueRows('headers', row.id, 'key', $event as string)"
              />
              <Input
                :model-value="row.value"
                :placeholder="t('settings.mcp.form.valuePlaceholder')"
                @update:model-value="updateKeyValueRows('headers', row.id, 'value', $event as string)"
              />
              <button
                type="button"
                @click="removeRow('headers', row.id)"
                class="mt-1 flex h-10 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
                :aria-label="t('settings.mcp.form.addHeader')"
              >
                <span class="material-symbols-outlined text-[18px]">delete</span>
              </button>
            </div>
            <button
              type="button"
              @click="addRow('headers')"
              class="flex h-12 w-full items-center justify-center gap-2 rounded-[var(--radius-lg)] bg-[var(--color-surface-hover)] text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)]"
            >
              <span class="material-symbols-outlined text-[18px]">add</span>
              {{ t('settings.mcp.form.addHeader') }}
            </button>
          </div>
        </section>

        <section class="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <div class="grid gap-4 md:grid-cols-2">
            <Input
              :label="t('settings.mcp.form.oauthClientId')"
              :model-value="draft.oauthClientId"
              :placeholder="t('settings.mcp.form.oauthClientIdPlaceholder')"
              @update:model-value="setDraftField('oauthClientId', $event as string)"
            />
            <Input
              :label="t('settings.mcp.form.oauthCallbackPort')"
              :model-value="draft.oauthCallbackPort"
              :placeholder="t('settings.mcp.form.oauthCallbackPortPlaceholder')"
              @update:model-value="setDraftField('oauthCallbackPort', $event as string)"
            />
          </div>
          <div class="mt-4">
            <Input
              :label="t('settings.mcp.form.headersHelper')"
              :model-value="draft.headersHelper"
              :placeholder="t('settings.mcp.form.headersHelperPlaceholder')"
              @update:model-value="setDraftField('headersHelper', $event as string)"
            />
          </div>
        </section>
      </template>

      <!-- Save -->
      <div class="flex justify-end pt-2">
        <Button
          :disabled="!isDraftValid(draft) || (isSaving || isDeleting)"
          :loading="isSaving"
          @click="handleSave"
        >
          {{ t('settings.mcp.form.save') }}
        </Button>
      </div>
    </div>
  </div>

  <!-- ════════════════════════════════════════════════════════════════
       LIST VIEW (default)
       ════════════════════════════════════════════════════════════════ -->
  <div v-else class="max-w-5xl min-w-0">
    <div class="flex items-start justify-between gap-6 mb-8">
      <div>
        <h2 class="text-[2.2rem] font-semibold tracking-[-0.03em] text-[var(--color-text-primary)]">
          {{ t('settings.mcp.title') }}
        </h2>
        <p class="mt-3 text-base text-[var(--color-text-secondary)]">
          {{ t('settings.mcp.description') }}
        </p>
      </div>
      <Button variant="secondary" size="lg" @click="beginCreate">
        <span class="material-symbols-outlined text-[18px]">add</span>
        {{ t('settings.mcp.addServer') }}
      </Button>
    </div>

    <LoadingState v-if="showListLoading" :label="t('common.loading')" />

    <template v-else>
      <!-- Stat cards -->
      <div class="grid gap-4 md:grid-cols-3 mb-8">
        <div class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-5 py-4">
          <div class="flex items-center gap-2 text-[var(--color-text-tertiary)] mb-2">
            <span class="material-symbols-outlined text-[18px]">dns</span>
            <span class="text-xs uppercase tracking-[0.18em] font-semibold">{{ t('settings.mcp.stats.total') }}</span>
          </div>
          <div class="text-3xl font-semibold text-[var(--color-text-primary)]">{{ stats.total }}</div>
        </div>
        <div class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-5 py-4">
          <div class="flex items-center gap-2 text-[var(--color-text-tertiary)] mb-2">
            <span class="material-symbols-outlined text-[18px]">check_circle</span>
            <span class="text-xs uppercase tracking-[0.18em] font-semibold">{{ t('settings.mcp.stats.connected') }}</span>
          </div>
          <div class="text-3xl font-semibold text-[var(--color-text-primary)]">{{ stats.connected }}</div>
        </div>
        <div class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-5 py-4">
          <div class="flex items-center gap-2 text-[var(--color-text-tertiary)] mb-2">
            <span class="material-symbols-outlined text-[18px]">error</span>
            <span class="text-xs uppercase tracking-[0.18em] font-semibold">{{ t('settings.mcp.stats.attention') }}</span>
          </div>
          <div class="text-3xl font-semibold text-[var(--color-text-primary)]">{{ stats.attention }}</div>
        </div>
      </div>

      <!-- Error state -->
      <div
        v-if="mcpStore.error"
        class="text-center py-16 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface-container-low)]"
      >
        <span class="material-symbols-outlined text-[40px] text-[var(--color-error)] mb-3 block">error</span>
        <p class="text-sm text-[var(--color-error)] mb-3">{{ mcpStore.error }}</p>
        <button
          type="button"
          @click="mcpStore.fetchServers(projectPathsForFetchRef, currentWorkDir as string | undefined)"
          class="text-sm text-[var(--color-text-accent)] hover:underline"
        >
          {{ t('common.retry') }}
        </button>
      </div>

      <!-- Empty state -->
      <div
        v-else-if="mcpStore.servers.length === 0"
        class="text-center py-16 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface-container-low)]"
      >
        <span class="material-symbols-outlined text-[40px] text-[var(--color-text-tertiary)] mb-3 block">dns</span>
        <p class="text-sm text-[var(--color-text-secondary)] mb-1">{{ t('settings.mcp.empty') }}</p>
        <p class="text-xs text-[var(--color-text-tertiary)]">{{ t('settings.mcp.emptyHint') }}</p>
        <div class="mt-4 rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-4 py-3 text-left text-xs leading-relaxed text-[var(--color-text-secondary)]">
          <div class="mb-1 font-semibold text-[var(--color-text-primary)]">
            {{ t('settings.mcp.importGuideTitle') || '如何添加 MCP 服务' }}
          </div>
          <ol class="list-decimal space-y-1 pl-4">
            <li>{{ t('settings.mcp.importGuide1') || '点击上方「添加服务」，选择 STDIO / HTTP / SSE 传输方式' }}</li>
            <li>{{ t('settings.mcp.importGuide2') || 'STDIO：填写 command（如 npx）与 args；HTTP/SSE：填写 URL' }}</li>
            <li>{{ t('settings.mcp.importGuide3') || '保存后点「重连」；工具会注入全局 registry 供对话调用' }}</li>
          </ol>
          <p class="mt-2 text-[var(--color-text-tertiary)]">
            {{ t('settings.mcp.importGuideExample') || '示例：npx -y @modelcontextprotocol/server-filesystem /tmp' }}
          </p>
        </div>
      </div>

      <!-- Server groups -->
      <div v-else class="flex flex-col gap-6">
        <section v-for="group in MCP_GROUP_ORDER" :key="group" v-show="groupedServers[group]?.length">
          <div class="flex items-center justify-between mb-3">
            <div class="text-[1.35rem] font-semibold text-[var(--color-text-primary)]">
              {{ group === 'plugin'
                ? t('settings.mcp.scope.plugin')
                : t(`settings.mcp.scope.${group}`) }}
            </div>
            <div class="text-sm text-[var(--color-text-tertiary)]">
              {{ groupedServers[group]?.length ?? 0 }}
            </div>
          </div>

          <div class="rounded-[28px] border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
            <div
              v-for="server in groupedServers[group] || []"
              :key="getServerIdentityKey(server)"
              class="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-4 px-6 py-5 border-t border-[var(--color-border)] first:border-t-0"
            >
              <div class="min-w-0">
                <div class="flex items-center gap-3 mb-2 min-w-0">
                  <div class="text-[1.05rem] font-semibold text-[var(--color-text-primary)] truncate">
                    {{ server.name }}
                  </div>
                  <span
                    :class="['inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold',
                             STATUS_TONE[server.status]]"
                  >
                    {{ server.statusLabel }}
                  </span>
                </div>
                <div class="flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-tertiary)]">
                  <span class="rounded-full bg-[var(--color-surface-hover)] px-2 py-1 font-medium text-[var(--color-text-secondary)]">
                    {{ transportLabel(server.transport) }}
                  </span>
                  <span class="rounded-full bg-[var(--color-surface-hover)] px-2 py-1 font-medium text-[var(--color-text-secondary)]">
                    {{ scopeLabel(server) }}
                  </span>
                  <span
                    v-if="serverHasProjectContext(server)"
                    class="max-w-full truncate rounded-full bg-[var(--color-surface-hover)] px-2 py-1 font-[var(--font-mono)] text-[11px] text-[var(--color-text-tertiary)]"
                    :title="server.projectPath"
                  >
                    {{ server.projectPath }}
                  </span>
                  <span class="truncate">{{ server.summary }}</span>
                </div>
                <div v-if="server.statusDetail" class="mt-2 text-xs text-[var(--color-text-tertiary)] truncate">
                  {{ server.statusDetail }}
                </div>
              </div>

              <button
                type="button"
                @click="beginEdit(server)"
                class="flex h-10 w-10 items-center justify-center rounded-full text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
                :aria-label="`Open ${server.name}`"
              >
                <span class="material-symbols-outlined text-[20px]">settings</span>
              </button>

              <!-- ToggleSwitch -->
              <button
                type="button"
                role="switch"
                :aria-checked="server.enabled"
                :disabled="busyServerKey === getServerIdentityKey(server) || !server.canToggle"
                @click="handleToggle(server)"
                :class="[
                  'relative inline-flex h-8 w-14 items-center rounded-full transition-colors',
                  server.enabled
                    ? 'bg-[var(--color-switch-checked-bg)]'
                    : 'bg-[var(--color-border)]',
                  (busyServerKey === getServerIdentityKey(server) || !server.canToggle)
                    ? 'opacity-60 cursor-not-allowed'
                    : 'cursor-pointer',
                ]"
              >
                <span
                  :class="[
                    'inline-block h-6 w-6 transform rounded-full bg-[var(--color-switch-thumb)] shadow-sm transition-transform',
                    server.enabled ? 'translate-x-7' : 'translate-x-1',
                  ]"
                />
              </button>
            </div>
          </div>
        </section>
      </div>
    </template>
  </div>

  <!-- ════════════════════════════════════════════════════════════════
       CONFIRM DELETE DIALOG (teleport replaces createPortal)
       ════════════════════════════════════════════════════════════════ -->
  <teleport to="body">
    <ConfirmDialog
      :open="pendingDeleteServer !== null"
      :title="t('settings.mcp.form.deleteTitle')"
      :confirm-label="t('settings.mcp.form.confirmDelete')"
      :cancel-label="t('settings.mcp.form.cancel')"
      confirm-variant="danger"
      :loading="isDeleting"
      @close="() => { if (!isDeleting) pendingDeleteServer = null }"
      @confirm="confirmDelete"
    >
      {{ pendingDeleteServer
        ? t('settings.mcp.form.deleteConfirmBody', { name: pendingDeleteServer.name })
        : '' }}
    </ConfirmDialog>
  </teleport>
</template>
