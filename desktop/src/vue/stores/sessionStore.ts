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
      // v3.0: Don't replace local sessions with backend sessions.
      // Each side has a different session id scheme (local uses
      // `session-...`, backend uses UUIDs) and a different message
      // store. Trying to merge them caused the sidebar to switch the
      // active tab to an id that no longer existed in the tab list,
      // leaving the user on a blank chat. The pragmatic fix is to
      // keep them separate: local sessions own local tabs and
      // localStorage-persisted history, backend sessions are kept
      // for cross-device sync but aren't shown in the sidebar UI yet.
      // If the local list is empty (first run, cleared storage), seed
      // with a default so the chat input still works.
      if (this.sessions.length === 0) {
        this.sessions = [
          {
            id: 'default', title: '新对话',
            createdAt: new Date().toISOString(), modifiedAt: new Date().toISOString(),
            messageCount: 0, projectPath: '', workDir: null, projectRoot: null, workDirExists: true,
          },
        ]
        this.activeSessionId = this.sessions[0]?.id || null
        saveToStorage(this.sessions)
      }
      this.isLoading = false
    },
    async createSession(_workDir?: string, _options?: any): Promise<string> {
      // v3.0: keep using a local id (`session-...`) so the sidebar,
      // tab list, and localStorage message map stay in sync. We don't
      // call the backend here because mixing the two id schemes
      // caused the sidebar to point at sessions the tabs couldn't
      // open. The backend still records the chat in its own session
      // store when messages are streamed to it; we just don't rely on
      // the backend id on the client.
      const id = `session-${Date.now()}`
      const now = new Date().toISOString()
      const session: SessionListItem = {
        id, title: '新对话',
        createdAt: now, modifiedAt: now,
        messageCount: 0, projectPath: _workDir || '', workDir: _workDir || null, projectRoot: _workDir || null, workDirExists: true,
      }
      this.sessions.unshift(session)
      this.activeSessionId = id
      saveToStorage(this.sessions)
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
    },
    async deleteSessions(ids: string[]) {
      this.sessions = this.sessions.filter(s => !ids.includes(s.id))
      this.selectedSessionIds = this.selectedSessionIds.filter(sid => !ids.includes(sid))
      if (ids.includes(this.activeSessionId || '')) {
        this.activeSessionId = this.sessions[0]?.id || null
      }
      saveToStorage(this.sessions)
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
    },
    updateSessionPermissionMode(_id: string, _mode: string) {},
    setActiveSession(id: string | null) {
      this.activeSessionId = id
    },
  },
})
