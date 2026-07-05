import { defineStore } from 'pinia'

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

export const useSessionStore = defineStore('session', {
  state: () => ({
    sessions: [] as SessionListItem[],
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
      try {
        this.sessions = [
          {
            id: 'default', title: 'New Session',
            createdAt: new Date().toISOString(), modifiedAt: new Date().toISOString(),
            messageCount: 0, projectPath: '', workDir: null, projectRoot: null, workDirExists: true,
          },
        ]
        this.activeSessionId = this.sessions[0]?.id || null
      } catch (err) {
        this.error = (err as Error).message
      }
      this.isLoading = false
    },
    async createSession(_workDir?: string, _options?: any): Promise<string> {
      const id = `session-${Date.now()}`
      const now = new Date().toISOString()
      const session: SessionListItem = {
        id, title: 'New Session',
        createdAt: now, modifiedAt: now,
        messageCount: 0, projectPath: '', workDir: null, projectRoot: null, workDirExists: true,
      }
      this.sessions.unshift(session)
      this.activeSessionId = id
      return id
    },
    async branchSession(_sourceSessionId: string, _targetMessageId: string, _options?: any): Promise<{ sessionId: string; title: string; workDir: string | null }> {
      return { sessionId: 'branch-1', title: 'Branched Session', workDir: null }
    },
    async deleteSession(id: string) {
      this.sessions = this.sessions.filter(s => s.id !== id)
      this.selectedSessionIds = this.selectedSessionIds.filter(sid => sid !== id)
      if (this.activeSessionId === id) this.activeSessionId = this.sessions[0]?.id || null
    },
    async deleteSessions(ids: string[]) {
      this.sessions = this.sessions.filter(s => !ids.includes(s.id))
      this.selectedSessionIds = this.selectedSessionIds.filter(sid => !ids.includes(sid))
      if (ids.includes(this.activeSessionId || '')) {
        this.activeSessionId = this.sessions[0]?.id || null
      }
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
    },
    updateSessionTitle(id: string, title: string) {
      const s = this.sessions.find(s => s.id === id)
      if (s) s.title = title
    },
    updateSessionPermissionMode(_id: string, _mode: string) {},
    setActiveSession(id: string | null) {
      this.activeSessionId = id
    },
  },
})
