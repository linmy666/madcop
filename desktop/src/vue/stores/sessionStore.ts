import { defineStore } from 'pinia'
import { getApiUrl } from '../api/client'
import { useTabStore, saveTabs } from './tabStore'

/**
 * Pinia mirror of stores/sessionStore.ts
 * Session list management, creation, deletion, batch mode.
 */

export type SessionListItem = {
  id: string
  title: string
  createdAt: string
  modifiedAt: string
  messageCount: number
  projectPath: string
  workDir: string | null
  projectRoot: string | null
  workDirExists: boolean
  permissionMode?: string
}

const STORAGE_KEY = 'madcop_sessions'
const WORKSPACE_DIR_STORAGE_KEY = 'madcop_workspace_dir'

// Resolve the current workspace dir from (in order):
//   1. The sessionStorage/localStorage mirror that WorkspacePanel writes
//   2. A synchronous fetch to /api/workspace/dir via XHR (last resort)
// We prefer the local mirror because it's set on every workspace
// change and survives reloads.
function getCurrentWorkspaceDir(): string {
  try {
    const raw = localStorage.getItem(WORKSPACE_DIR_STORAGE_KEY)
    if (raw) return raw
  } catch {}
  return ''
}

export function loadFromStorage(): SessionListItem[] {
  // NOTE: We return raw parsed sessions here. Backfilling
  // projectRoot/workDir from the current workspace dir is done by
  // `backfillMissingProjectRoot()` which the store calls once on
  // init. Doing it in loadFromStorage would silently mutate storage
  // on every read, which led to data loss when the backfill raced
  // with the user's edits.
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as any[]
      return parsed.map((s) => ({
        id: s.id,
        title: s.title || '新对话',
        createdAt: s.createdAt || new Date().toISOString(),
        modifiedAt: s.modifiedAt || new Date().toISOString(),
        messageCount: s.messageCount ?? 0,
        projectPath: s.projectPath ?? '',
        workDir: s.workDir ?? null,
        projectRoot: s.projectRoot ?? null,
        workDirExists: s.workDirExists ?? true,
        permissionMode: s.permissionMode,
      })) as SessionListItem[]
    }
  } catch {}
  return []
}

// Backfill sessions that predate the projectRoot/workDir fields.
// In-memory only — caller decides whether to persist.
export function backfillMissingProjectRoot(
  sessions: SessionListItem[],
  fallbackWorkDir: string,
): { sessions: SessionListItem[]; changed: boolean } {
  let changed = false
  const result = sessions.map((s) => {
    if (s.projectRoot || s.workDir || s.projectPath) return s
    if (!fallbackWorkDir) return s
    changed = true
    return {
      ...s,
      projectPath: fallbackWorkDir,
      workDir: fallbackWorkDir,
      projectRoot: fallbackWorkDir,
    }
  })
  return { sessions: result, changed }
}

export function saveToStorage(sessions: SessionListItem[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions))
  } catch {}
}

// ── Backend session sync ──────────────────────────────────────────
// Sessions are also persisted to the backend, which stores them under
// the workspace directory (<workDir>/.madcop/...). localStorage stays a
// fast offline cache; the backend is the durable, portable copy that
// follows the project instead of living in opaque Electron LevelDB.
async function backendLoadSessions(workDir: string): Promise<SessionListItem[]> {
  try {
    const res = await fetch(getApiUrl(`/api/sessions?project=${encodeURIComponent(workDir)}`))
    if (!res.ok) return []
    const data = await res.json()
    const list = (data?.sessions as any[]) || []
    return list.map((s: any) => ({
      id: s.id,
      title: s.title || '新对话',
      createdAt: s.createdAt || new Date().toISOString(),
      modifiedAt: s.modifiedAt || new Date().toISOString(),
      messageCount: s.messageCount ?? 0,
      projectPath: s.projectPath ?? '',
      workDir: s.workDir ?? null,
      projectRoot: s.projectRoot ?? null,
      workDirExists: s.workDirExists ?? true,
      permissionMode: s.permissionMode,
    }))
  } catch {
    return []
  }
}

async function backendUpsertSession(s: SessionListItem) {
  try {
    await fetch(getApiUrl('/api/sessions'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: s.id,
        workDir: s.workDir || s.projectPath || s.projectRoot || '',
        title: s.title,
      }),
    })
  } catch {}
}

async function backendPatchSession(id: string, patch: Record<string, any>) {
  try {
    await fetch(getApiUrl(`/api/sessions/${encodeURIComponent(id)}`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
  } catch {}
}

async function backendDeleteSession(id: string) {
  try {
    await fetch(getApiUrl(`/api/sessions/${encodeURIComponent(id)}`), { method: 'DELETE' })
  } catch {}
}

// ── Collapse duplicate empty sessions ────────────────────────────
// When "New Chat" is clicked repeatedly, multiple untitled zero-message
// sessions accumulate (each with a unique id).  This helper keeps at most
// one such session — the active one if it's already empty, otherwise the
// most-recently-modified.
const DEFAULT_TITLES = new Set(['新对话', 'New Session'])
function collapseEmptySessions(
  sessions: SessionListItem[],
  activeId: string | null,
): SessionListItem[] {
  const empties = sessions.filter(
    (s) => s.messageCount === 0 && DEFAULT_TITLES.has(s.title),
  )
  if (empties.length <= 1) return sessions
  const keepId =
    (activeId && empties.find((s) => s.id === activeId)?.id) ||
    empties
      .slice()
      .sort(
        (a, b) =>
          new Date(b.modifiedAt).getTime() - new Date(a.modifiedAt).getTime(),
      )[0].id
  return sessions.filter(
    (s) => !(DEFAULT_TITLES.has(s.title) && s.messageCount === 0 && s.id !== keepId),
  )
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    sessions: loadFromStorage() as SessionListItem[],
    activeSessionId: null as string | null,
    isLoading: false,
    error: null as string | null,
    isBatchMode: false,
    selectedSessionIds: [] as string[],
  }),

  actions: {
    async fetchSessions(_project?: string) {
      this.isLoading = true
      this.error = null
      const local = loadFromStorage()
      const wd = getCurrentWorkspaceDir()
      let backend: SessionListItem[] = []
      if (wd) backend = await backendLoadSessions(wd)

      // Scope local sessions to the current workspace so that sessions
      // created under a different project don't leak into this view.
      const localScoped = wd
        ? local.filter((s) => (s.workDir || s.projectRoot || s.projectPath) === wd)
        : local

      // Merge by id (local wins for fields like title).
      const byId = new Map<string, SessionListItem>()
      for (const s of localScoped) byId.set(s.id, s)
      for (const s of backend) {
        if (!byId.has(s.id)) byId.set(s.id, s)
      }
      let merged = [...byId.values()]

      // Collapse duplicate empty "新对话" sessions to a single one.
      merged = collapseEmptySessions(merged, this.activeSessionId)

      if (merged.length === 0) {
        merged = [
          {
            id: 'default', title: '新对话',
            createdAt: new Date().toISOString(), modifiedAt: new Date().toISOString(),
            messageCount: 0, projectPath: '', workDir: null, projectRoot: null, workDirExists: true,
          },
        ]
        this.activeSessionId = this.activeSessionId || merged[0]?.id || null
      }
      this.sessions = merged
      saveToStorage(this.sessions)
      this.isLoading = false
    },
    async createSession(_workDir?: string, _options?: any): Promise<string> {
      // Reuse an existing empty "新对话" session rather than spawning a
      // brand-new one every time "New Chat" is clicked.  This prevents the
      // tab bar and sidebar from filling up with duplicate empty entries.
      const existingEmpty = this.sessions.find(
        (s) => s.messageCount === 0 && DEFAULT_TITLES.has(s.title),
      )
      if (existingEmpty) {
        this.activeSessionId = existingEmpty.id
        return existingEmpty.id
      }

      const id = `session-${Date.now()}`
      const now = new Date().toISOString()
      const workDir = _workDir || getCurrentWorkspaceDir() || ''
      const session: SessionListItem = {
        id, title: '新对话',
        createdAt: now, modifiedAt: now,
        messageCount: 0, projectPath: workDir, workDir: workDir || null, projectRoot: workDir || null, workDirExists: true,
      }
      this.sessions.unshift(session)
      this.activeSessionId = id
      saveToStorage(this.sessions)
      backendUpsertSession(session)
      return id
    },
    async branchSession(_sourceSessionId: string, _targetMessageId: string, _options?: any): Promise<{ sessionId: string; title: string; workDir: string | null }> {
      return { sessionId: 'branch-1', title: 'Branched Session', workDir: null }
    },
    async deleteSession(id: string) {
      this.sessions = this.sessions.filter(s => s.id !== id)
      this.selectedSessionIds = this.selectedSessionIds.filter(sid => sid !== id)
      if (this.activeSessionId === id) this.activeSessionId = this.sessions[0]?.id || null
      saveToStorage(this.sessions)
      backendDeleteSession(id)
    },
    async deleteSessions(ids: string[]) {
      this.sessions = this.sessions.filter(s => !ids.includes(s.id))
      this.selectedSessionIds = this.selectedSessionIds.filter(sid => !ids.includes(sid))
      if (ids.includes(this.activeSessionId || '')) {
        this.activeSessionId = this.sessions[0]?.id || null
      }
      saveToStorage(this.sessions)
      for (const id of ids) backendDeleteSession(id)
    },
    enterBatchMode() { this.isBatchMode = true },
    exitBatchMode() { this.isBatchMode = false; this.selectedSessionIds = [] },
    toggleSessionSelected(id: string) {
      if (this.selectedSessionIds.includes(id)) {
        this.selectedSessionIds = this.selectedSessionIds.filter(sid => sid !== id)
      } else {
        this.selectedSessionIds.push(id)
      }
    },
    selectSessions(ids: string[]) {
      for (const id of ids) {
        if (!this.selectedSessionIds.includes(id)) this.selectedSessionIds.push(id)
      }
    },
    deselectSessions(ids: string[]) {
      this.selectedSessionIds = this.selectedSessionIds.filter(sid => !ids.includes(sid))
    },
    clearSessionSelection() { this.selectedSessionIds = [] },
    async renameSession(_id: string, title: string) {
      const s = this.sessions.find(s => s.id === _id)
      if (s) s.title = title
      // Also update the tab title so the TabStrip reflects the rename.
      try {
        const tabStore = useTabStore()
        const tab = tabStore.tabs.find((t) => t.sessionId === _id)
        if (tab) tab.title = title
        saveTabs(tabStore.tabs)
      } catch {}
      saveToStorage(this.sessions)
      backendPatchSession(_id, { title })
    },
    updateSessionTitle(id: string, title: string) {
      const s = this.sessions.find(s => s.id === id)
      if (s) s.title = title
      // Also update the tab title so the TabStrip reflects the new title.
      try {
        const tabStore = useTabStore()
        const tab = tabStore.tabs.find((t) => t.sessionId === id)
        if (tab) tab.title = title
        saveTabs(tabStore.tabs)
      } catch {}
      saveToStorage(this.sessions)
      backendPatchSession(id, { title })
    },
    updateSessionPermissionMode(_id: string, _mode: string) {},
    setActiveSession(id: string | null) {
      this.activeSessionId = id
    },
  },
})
