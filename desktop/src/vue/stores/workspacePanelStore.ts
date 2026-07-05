import { defineStore } from 'pinia'

// ─── Constants ───────────────────────────────────────────────────────

export const WORKSPACE_PANEL_DEFAULT_WIDTH = 860
export const WORKSPACE_PANEL_MIN_WIDTH = 640
export const WORKSPACE_PANEL_MAX_WIDTH = 1120

export type WorkspacePanelView = 'changed' | 'all'
export type WorkbenchMode = 'workspace' | 'browser'
export type WorkspacePreviewKind = 'file' | 'diff'
export type WorkspacePreviewCloseScope = 'current' | 'others' | 'left' | 'right' | 'all'

export type WorkspaceFileStatus =
  | 'modified'
  | 'added'
  | 'deleted'
  | 'renamed'
  | 'untracked'
  | 'copied'
  | 'type_changed'
  | 'unknown'

export interface WorkspaceChangedFile {
  path: string
  oldPath?: string
  status: WorkspaceFileStatus
  additions: number
  deletions: number
}

export interface WorkspaceTreeEntry {
  name: string
  path: string
  isDirectory: boolean
}

export interface WorkspaceTreeResult {
  state: 'ok' | 'missing' | 'error'
  entries: WorkspaceTreeEntry[]
  error?: string
}

export interface WorkspaceStatusResult {
  state: 'ok' | 'missing_workdir' | 'not_git_repo' | 'error'
  workDir?: string
  repoName?: string
  changedFiles: WorkspaceChangedFile[]
  error?: string
}

export interface WorkspaceReadFileResult {
  state: 'ok' | 'missing' | 'too_large' | 'binary' | 'error'
  content?: string
  language?: string
  mimeType?: string
  size?: number
  error?: string
}

export interface WorkspaceDiffResult {
  state: 'ok' | 'missing' | 'error'
  diff?: string
  error?: string
}

export type WorkspacePreviewState = 'loading' | WorkspaceReadFileResult['state'] | WorkspaceDiffResult['state']

export interface WorkspacePreviewTab {
  id: string
  path: string
  kind: WorkspacePreviewKind
  title: string
  language?: string
  content?: string
  dataUrl?: string
  mimeType?: string
  previewType?: 'text' | 'image'
  diff?: string
  state?: WorkspacePreviewState
  error?: string
  size?: number
}

export interface WorkspacePanelSessionState {
  isOpen: boolean
  activeView: WorkspacePanelView
  hasUserSelectedView?: boolean
}

// ─── Helpers ─────────────────────────────────────────────────────────

function clampWorkspacePanelWidth(width: number): number {
  if (!Number.isFinite(width)) return WORKSPACE_PANEL_DEFAULT_WIDTH
  const rounded = Math.round(width)
  return Math.min(WORKSPACE_PANEL_MAX_WIDTH, Math.max(WORKSPACE_PANEL_MIN_WIDTH, rounded))
}

const DEFAULT_PANEL_STATE: WorkspacePanelSessionState = {
  isOpen: false,
  activeView: 'changed',
}

const DEFAULT_WORKBENCH_MODE: WorkbenchMode = 'workspace'

function getSessionPanelState(panelBySession: Record<string, WorkspacePanelSessionState | undefined>, sessionId: string): WorkspacePanelSessionState {
  return panelBySession[sessionId] ?? DEFAULT_PANEL_STATE
}

function makeTreeKey(sessionId: string, path: string): string {
  return `${sessionId}::${path}`
}

export function getWorkspacePreviewTabId(path: string, kind: WorkspacePreviewKind): string {
  return `${kind}:${path}`
}

function makePreviewKey(sessionId: string, tabId: string): string {
  return `${sessionId}::${tabId}`
}

function getPathTitle(path: string): string {
  if (!path) return 'Workspace'
  const segments = path.split('/').filter(Boolean)
  return segments[segments.length - 1] ?? path
}

function removeRecordKey<T>(record: Record<string, T>, key: string): Record<string, T> {
  if (!(key in record)) return record
  const { [key]: _removed, ...rest } = record as Record<string, T>
  return rest
}

function stripSessionKeys<T>(record: Record<string, T>, sessionId: string): Record<string, T> {
  const prefix = `${sessionId}::`
  return Object.fromEntries(
    Object.entries(record).filter(([key]) => !key.startsWith(prefix)),
  ) as Record<string, T>
}

function invalidateSessionScopedRequests(store: Map<string, number>, sessionId: string): void {
  const prefix = `${sessionId}::`
  for (const key of store.keys()) {
    if (key.startsWith(prefix)) {
      store.set(key, (store.get(key) ?? 0) + 1)
    }
  }
}

function upsertPreviewTab(
  tabs: WorkspacePreviewTab[],
  tabId: string,
  update: WorkspacePreviewTab | ((current: WorkspacePreviewTab) => WorkspacePreviewTab),
): WorkspacePreviewTab[] {
  const index = tabs.findIndex((tab) => tab.id === tabId)
  if (index < 0) return tabs
  const current = tabs[index]!
  const next = typeof update === 'function' ? update(current) : update
  const nextTabs = [...tabs]
  nextTabs[index] = next
  return nextTabs
}

function nextRequestId(store: Map<string, number>, key: string): number {
  const requestId = (store.get(key) ?? 0) + 1
  store.set(key, requestId)
  return requestId
}

function isLatestRequest(store: Map<string, number>, key: string, requestId: number): boolean {
  return store.get(key) === requestId
}

// ─── Request ID tracking ─────────────────────────────────────────────

const statusRequestIds = new Map<string, number>()
const treeRequestIds = new Map<string, number>()
const previewRequestIds = new Map<string, number>()

// ─── API Layer ───────────────────────────────────────────────────────

async function getWorkspaceStatus(sessionId: string): Promise<WorkspaceStatusResult> {
  try {
    const res = await fetch(`/api/sessions/${sessionId}/workspace/status`)
    if (!res.ok) {
      throw new Error(`Workspace status request failed: ${res.status}`)
    }
    return res.json()
  } catch {
    return { state: 'error', changedFiles: [], error: 'Failed to load workspace status' }
  }
}

async function getWorkspaceTree(sessionId: string, path = ''): Promise<WorkspaceTreeResult> {
  try {
    const res = await fetch(`/api/sessions/${sessionId}/workspace/tree${path ? '/' + encodeURIComponent(path) : ''}`)
    if (!res.ok) {
      throw new Error(`Workspace tree request failed: ${res.status}`)
    }
    return res.json()
  } catch {
    return { state: 'error', entries: [], error: 'Failed to load workspace tree' }
  }
}

async function getWorkspaceFile(sessionId: string, path: string): Promise<WorkspaceReadFileResult> {
  try {
    const res = await fetch(`/api/sessions/${sessionId}/workspace/file/${encodeURIComponent(path)}`)
    if (!res.ok) {
      throw new Error(`Workspace file request failed: ${res.status}`)
    }
    return res.json()
  } catch {
    return { state: 'error', error: 'Failed to load workspace file' }
  }
}

async function getWorkspaceDiff(sessionId: string, path: string): Promise<WorkspaceDiffResult> {
  try {
    const res = await fetch(`/api/sessions/${sessionId}/workspace/diff/${encodeURIComponent(path)}`)
    if (!res.ok) {
      throw new Error(`Workspace diff request failed: ${res.status}`)
    }
    return res.json()
  } catch {
    return { state: 'error', error: 'Failed to load workspace diff' }
  }
}

// ─── Store ───────────────────────────────────────────────────────────

interface WorkspacePanelStoreState {
  panelBySession: Record<string, WorkspacePanelSessionState | undefined>
  modeBySession: Record<string, WorkbenchMode | undefined>
  width: number
  statusBySession: Record<string, WorkspaceStatusResult | undefined>
  expandedPathsBySession: Record<string, string[] | undefined>
  treeBySessionPath: Record<string, Record<string, WorkspaceTreeResult | undefined> | undefined>
  previewTabsBySession: Record<string, WorkspacePreviewTab[] | undefined>
  activePreviewTabIdBySession: Record<string, string | null | undefined>
  loading: {
    statusBySession: Record<string, boolean | undefined>
    treeBySessionPath: Record<string, boolean | undefined>
    previewByTabId: Record<string, boolean | undefined>
  }
  errors: {
    statusBySession: Record<string, string | null | undefined>
    treeBySessionPath: Record<string, string | null | undefined>
    previewByTabId: Record<string, string | null | undefined>
  }
}

const initialState = (): WorkspacePanelStoreState => ({
  panelBySession: {},
  modeBySession: {},
  width: WORKSPACE_PANEL_DEFAULT_WIDTH,
  statusBySession: {},
  expandedPathsBySession: {},
  treeBySessionPath: {},
  previewTabsBySession: {},
  activePreviewTabIdBySession: {},
  loading: { statusBySession: {}, treeBySessionPath: {}, previewByTabId: {} },
  errors: { statusBySession: {}, treeBySessionPath: {}, previewByTabId: {} },
})

export const useWorkspacePanelStore = defineStore('workspacePanel', {
  state: initialState,

  getters: {
    isPanelOpen: (state) => (sessionId: string) =>
      getSessionPanelState(state.panelBySession, sessionId).isOpen,

    getActiveView: (state) => (sessionId: string) =>
     getSessionPanelState(state.panelBySession, sessionId).activeView,

    getMode: (state) => (sessionId: string) =>
      state.modeBySession[sessionId] ?? DEFAULT_WORKBENCH_MODE,
  },

  actions: {
    setMode(sessionId: string, mode: WorkbenchMode) {
      this.modeBySession[sessionId] = mode
    },

    openPanel(sessionId: string) {
      const panel = getSessionPanelState(this.panelBySession, sessionId)
      this.panelBySession[sessionId] = { ...panel, isOpen: true }
    },

    closePanel(sessionId: string) {
      const panel = getSessionPanelState(this.panelBySession, sessionId)
      this.panelBySession[sessionId] = { ...panel, isOpen: false }
    },

    togglePanel(sessionId: string) {
      const panel = getSessionPanelState(this.panelBySession, sessionId)
      this.panelBySession[sessionId] = { ...panel, isOpen: !panel.isOpen }
    },

    setWidth(width: number) {
      this.width = clampWorkspacePanelWidth(width)
    },

    setActiveView(sessionId: string, view: WorkspacePanelView) {
      const panel = getSessionPanelState(this.panelBySession, sessionId)
      this.panelBySession[sessionId] = { ...panel, activeView: view, hasUserSelectedView: true }
    },

    async loadStatus(sessionId: string): Promise<void> {
      const requestId = nextRequestId(statusRequestIds, sessionId)

      this.loading.statusBySession[sessionId] = true
      this.errors.statusBySession[sessionId] = null

      try {
        const result = await getWorkspaceStatus(sessionId)
        if (!isLatestRequest(statusRequestIds, sessionId, requestId)) return

        const panel = getSessionPanelState(this.panelBySession, sessionId)
        const nextActiveView =
          !panel.hasUserSelectedView && result.state === 'ok'
            ? result.changedFiles.length > 0 ? 'changed' : 'all'
            : panel.activeView

        this.panelBySession[sessionId] = { ...panel, activeView: nextActiveView }
        this.statusBySession[sessionId] = result
        this.loading.statusBySession[sessionId] = false
        this.errors.statusBySession[sessionId] = result.error ?? null
      } catch (error) {
        if (!isLatestRequest(statusRequestIds, sessionId, requestId)) return
        this.loading.statusBySession[sessionId] = false
        this.errors.statusBySession[sessionId] = error instanceof Error ? error.message : 'Failed to load workspace status'
      }
    },

    async loadTree(sessionId: string, path = ''): Promise<void> {
      const treeKey = makeTreeKey(sessionId, path)
      const requestId = nextRequestId(treeRequestIds, treeKey)

      this.loading.treeBySessionPath[treeKey] = true
      this.errors.treeBySessionPath[treeKey] = null

      try {
        const result = await getWorkspaceTree(sessionId, path)
        if (!isLatestRequest(treeRequestIds, treeKey, requestId)) return

        const sessionTrees = this.treeBySessionPath[sessionId] ?? {}
        sessionTrees[path] = result
        this.treeBySessionPath[sessionId] = sessionTrees
        this.loading.treeBySessionPath[treeKey] = false
        this.errors.treeBySessionPath[treeKey] = result.error ?? null
      } catch (error) {
        if (!isLatestRequest(treeRequestIds, treeKey, requestId)) return
        this.loading.treeBySessionPath[treeKey] = false
        this.errors.treeBySessionPath[treeKey] = error instanceof Error ? error.message : 'Failed to load workspace tree'
      }
    },

    async toggleTreeNode(sessionId: string, path: string): Promise<void> {
      const expanded = this.expandedPathsBySession[sessionId] ?? []
      const index = expanded.indexOf(path)
      if (index >= 0) {
        this.expandedPathsBySession[sessionId] = expanded.filter((p) => p !== path)
      } else {
        this.expandedPathsBySession[sessionId] = [...expanded, path]
        // Load the tree for this newly expanded node
        void this.loadTree(sessionId, path)
      }
    },

    async openPreview(sessionId: string, path: string, kind: WorkspacePreviewKind): Promise<void> {
      const tabId = getWorkspacePreviewTabId(path, kind)
      const previewKey = makePreviewKey(sessionId, tabId)
      const requestId = nextRequestId(previewRequestIds, previewKey)

      let tabs = this.previewTabsBySession[sessionId] ?? []
      const existingIndex = tabs.findIndex((tab) => tab.id === tabId)

      // Update active tab id
      this.activePreviewTabIdBySession[sessionId] = tabId

      if (existingIndex >= 0) {
        // Tab already exists, refresh it
        const existingTab = tabs[existingIndex]!
        tabs[existingIndex] = {
          ...existingTab,
          state: 'loading',
          error: undefined,
          content: undefined,
          diff: undefined,
          dataUrl: undefined,
        }
      } else {
        // Create new tab
        const title = getPathTitle(path)
        tabs = [...tabs, {
          id: tabId,
          path,
          kind,
          title,
          state: 'loading',
        }]
      }
      this.previewTabsBySession[sessionId] = tabs
      this.loading.previewByTabId[previewKey] = true
      this.errors.previewByTabId[previewKey] = null

      try {
        let tabUpdate: Partial<WorkspacePreviewTab> = { state: 'ok' }

        if (kind === 'diff') {
          const result = await getWorkspaceDiff(sessionId, path)
          if (!isLatestRequest(previewRequestIds, previewKey, requestId)) return
          tabUpdate = {
            state: result.state,
            diff: result.diff,
            error: result.error,
            language: 'diff',
          }
        } else {
          const result = await getWorkspaceFile(sessionId, path)
          if (!isLatestRequest(previewRequestIds, previewKey, requestId)) return
          tabUpdate = {
            state: result.state,
            content: result.content,
            language: result.language,
            dataUrl: undefined,
            mimeType: result.mimeType,
            error: result.error,
            size: result.size,
            previewType: result.mimeType?.startsWith('image/') ? 'image' : 'text',
          }

          // If it's an image, try to get data URL
          if (result.mimeType?.startsWith('image/')) {
            try {
              const imgRes = await fetch(`/api/sessions/${sessionId}/workspace/file/${encodeURIComponent(path)}/data`)
              if (imgRes.ok) {
                const blob = await imgRes.blob()
                tabUpdate.dataUrl = await new Promise<string>((resolve) => {
                  const reader = new FileReader()
                  reader.onloadend = () => resolve(reader.result as string)
                  reader.readAsDataURL(blob)
                })
              }
            } catch {
              // Silently ignore data URL failures
            }
          }
        }

        if (isLatestRequest(previewRequestIds, previewKey, requestId)) {
          tabs = upsertPreviewTab(tabs, tabId, (current) => ({ ...current, ...tabUpdate }))
          this.previewTabsBySession[sessionId] = tabs
          this.loading.previewByTabId[previewKey] = false
          this.errors.previewByTabId[previewKey] = (tabUpdate as any).error ?? null
        }
      } catch (error) {
        if (!isLatestRequest(previewRequestIds, previewKey, requestId)) return
        tabs = upsertPreviewTab(tabs, tabId, (current) => ({
          ...current,
          state: 'error',
          error: error instanceof Error ? error.message : 'Failed to load preview',
        }))
        this.previewTabsBySession[sessionId] = tabs
        this.loading.previewByTabId[previewKey] = false
        this.errors.previewByTabId[previewKey] = error instanceof Error ? error.message : 'Failed to load preview'
      }
    },

    closePreview(sessionId: string, tabId: string) {
      const tabs = this.previewTabsBySession[sessionId] ?? []
      const index = tabs.findIndex((tab) => tab.id === tabId)
      if (index < 0) return

      const updatedTabs = tabs.filter((tab) => tab.id !== tabId)
      this.previewTabsBySession[sessionId] = updatedTabs

      // Update active tab
      const activeTabId = this.activePreviewTabIdBySession[sessionId]
      if (activeTabId === tabId) {
        this.activePreviewTabIdBySession[sessionId] = updatedTabs.length > 0 ? updatedTabs[updatedTabs.length - 1]!.id : null
      }

      // Invalidate preview loading/error for this tab
      const previewKey = makePreviewKey(sessionId, tabId)
      this.loading.previewByTabId = removeRecordKey(this.loading.previewByTabId, previewKey)
      this.errors.previewByTabId = removeRecordKey(this.errors.previewByTabId, previewKey)
    },

    closePreviewTabs(sessionId: string, tabId: string, scope: WorkspacePreviewCloseScope) {
      const tabs = this.previewTabsBySession[sessionId] ?? []
      const tabIndex = tabs.findIndex((tab) => tab.id === tabId)
      if (tabIndex < 0) return

      let tabsToClose: WorkspacePreviewTab[]
      switch (scope) {
        case 'current':
          tabsToClose = [tabs[tabIndex]!]
          break
        case 'others':
          tabsToClose = tabs.filter((_, i) => i !== tabIndex)
          break
        case 'left':
          tabsToClose = tabs.slice(0, tabIndex)
          break
        case 'right':
          tabsToClose = tabs.slice(tabIndex + 1)
          break
        case 'all':
          tabsToClose = tabs
          break
        default:
          return
      }

      for (const tab of tabsToClose) {
        this.closePreview(sessionId, tab.id)
      }
    },

    clearSession(sessionId: string) {
      this.panelBySession = stripSessionKeys(this.panelBySession, sessionId)
      this.modeBySession = stripSessionKeys(this.modeBySession, sessionId)
      this.statusBySession = stripSessionKeys(this.statusBySession, sessionId)
      this.expandedPathsBySession = stripSessionKeys(this.expandedPathsBySession, sessionId)
      this.treeBySessionPath = stripSessionKeys(this.treeBySessionPath, sessionId)
      this.previewTabsBySession = stripSessionKeys(this.previewTabsBySession, sessionId)
      this.activePreviewTabIdBySession = stripSessionKeys(this.activePreviewTabIdBySession, sessionId)
      this.loading.statusBySession = stripSessionKeys(this.loading.statusBySession, sessionId)
      this.loading.treeBySessionPath = stripSessionKeys(this.loading.treeBySessionPath, sessionId)
      this.loading.previewByTabId = stripSessionKeys(this.loading.previewByTabId, sessionId)
      this.errors.statusBySession = stripSessionKeys(this.errors.statusBySession, sessionId)
      this.errors.treeBySessionPath = stripSessionKeys(this.errors.treeBySessionPath, sessionId)
      this.errors.previewByTabId = stripSessionKeys(this.errors.previewByTabId, sessionId)
      invalidateSessionScopedRequests(statusRequestIds, sessionId)
      invalidateSessionScopedRequests(treeRequestIds, sessionId)
      invalidateSessionScopedRequests(previewRequestIds, sessionId)
    },

    resetSessionUi(sessionId: string) {
      const panel = getSessionPanelState(this.panelBySession, sessionId)
      this.panelBySession[sessionId] = { ...panel, isOpen: false, activeView: 'changed', hasUserSelectedView: false }
    },
  },
})
