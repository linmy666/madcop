// v3.0 — MadCop tabs store (Pinia)
// Mirrors the React useTabStore (zustand). The Vue 3 world uses Pinia;
// this is the single source of truth for the tab list shown in the top tab strip.
//
// Shape aligned with src/stores/tabStore.ts (360 lines) for P0 component compat.

import { defineStore } from 'pinia'

// ─── Constants (exported for ChatInput import) ─────────────────────

export const SETTINGS_TAB_ID = '__settings__'
export const SCHEDULED_TAB_ID = '__scheduled__'
export const TRACE_LIST_TAB_ID = '__traces__'
export const TERMINAL_TAB_PREFIX = '__terminal__'
export const TRACE_TAB_PREFIX = '__trace__'
export const WORKBENCH_TAB_PREFIX = '__workbench__'

// ─── Types ─────────────────────────────────────────────────────────

export type TabType = 'session' | 'settings' | 'scheduled' | 'terminal' | 'trace' | 'traces' | 'workbench' | 'workflows' | 'design'

export type Tab = {
  sessionId: string
  title: string
  type: TabType
  status: 'idle' | 'running' | 'error'
  terminalCwd?: string
  terminalRuntimeId?: string
  traceSessionId?: string
  workbenchSessionId?: string
}

// ─── Store ─────────────────────────────────────────────────────────

const TAB_STORAGE_KEY = 'madcop-agent-open-tabs'

function loadTabs(): Tab[] {
  if (typeof localStorage === 'undefined') return []
  try {
    const raw = localStorage.getItem(TAB_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as Array<{ sessionId: string; title: string; type?: TabType; traceSessionId?: string }>
    return parsed.map((p) => ({
      sessionId: p.sessionId,
      title: p.title,
      type: (p.type ?? 'session') as TabType,
      status: 'idle' as const,
      traceSessionId: p.traceSessionId,
    }))
  } catch { return [] }
}

function persistTabs(tabs: Tab[]) {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(TAB_STORAGE_KEY, JSON.stringify(
      tabs.map(t => ({ sessionId: t.sessionId, title: t.title, type: t.type, traceSessionId: t.traceSessionId })),
    ))
  } catch { /* noop */ }
}

let counter = 0
function newId() { counter += 1; return `t${Date.now()}${counter}` }

export const useTabStore = defineStore('madcop-tabs', {
  state: () => ({
    tabs: loadTabs() as Tab[],
    activeTabId: null as string | null,
  }),

  actions: {
    openTab(sessionId: string, title: string, type: TabType = 'session') {
      // Close existing tab for this session first (session tabs are unique)
      this.tabs = this.tabs.filter(t => t.sessionId !== sessionId || t.type !== 'session')
      const t: Tab = { sessionId, title, type, status: 'idle' }
      this.tabs.push(t)
      this.activeTabId = t.sessionId
      persistTabs(this.tabs)
    },

    setActiveTab(id: string | null) {
      this.activeTabId = id
    },

    closeTab(id: string) {
      this.tabs = this.tabs.filter(t => t.sessionId !== id)
      if (this.activeTabId === id) {
        this.activeTabId = this.tabs[this.tabs.length - 1]?.sessionId ?? null
      }
      persistTabs(this.tabs)
    },

    closeAll() {
      this.tabs = []
      this.activeTabId = null
      persistTabs(this.tabs)
    },

    updateTabTitle(sessionId: string, title: string) {
      const t = this.tabs.find(t => t.sessionId === sessionId)
      if (t) t.title = title
      persistTabs(this.tabs)
    },

    updateTabStatus(sessionId: string, status: 'idle' | 'running' | 'error') {
      const t = this.tabs.find(t => t.sessionId === sessionId)
      if (t) t.status = status
    },

    openSettingsTab() {
      const existing = this.tabs.find(t => t.sessionId === SETTINGS_TAB_ID)
      if (existing) {
        this.activeTabId = SETTINGS_TAB_ID
        return
      }
      const t: Tab = { sessionId: SETTINGS_TAB_ID, title: 'Settings', type: 'settings', status: 'idle' }
      this.tabs.push(t)
      this.activeTabId = SETTINGS_TAB_ID
    },

    openTracesTab(title?: string) {
      const existing = this.tabs.find(t => t.sessionId === TRACE_LIST_TAB_ID)
      if (existing) {
        this.activeTabId = TRACE_LIST_TAB_ID
        return existing.sessionId
      }
      const t: Tab = { sessionId: TRACE_LIST_TAB_ID, title: title ?? 'Trace Sessions', type: 'traces', status: 'idle' }
      this.tabs.push(t)
      this.activeTabId = t.sessionId
      return t.sessionId
    },

    openTraceTab(sessionId: string, title?: string) {
      const tabId = `${TRACE_TAB_PREFIX}${sessionId}`
      const existing = this.tabs.find(t => t.sessionId === tabId)
      if (existing) {
        this.activeTabId = tabId
        return tabId
      }
      const t: Tab = { sessionId: tabId, title: title ?? 'Trace', type: 'trace', status: 'idle', traceSessionId: sessionId }
      this.tabs.push(t)
      this.activeTabId = t.sessionId
      return t.sessionId
    },

    openTerminalTab(cwd?: string, terminalRuntimeId?: string) {
      const tabId = `${TERMINAL_TAB_PREFIX}${Date.now()}`
      const t: Tab = { sessionId: tabId, title: cwd ?? 'Terminal', type: 'terminal', status: 'idle', terminalCwd: cwd, terminalRuntimeId }
      this.tabs.push(t)
      this.activeTabId = t.sessionId
      return t.sessionId
    },

    openWorkbenchTab(sessionId: string, title?: string) {
      const tabId = `${WORKBENCH_TAB_PREFIX}${sessionId}`
      const existing = this.tabs.find(t => t.sessionId === tabId)
      if (existing) {
        this.activeTabId = tabId
        return tabId
      }
      const t: Tab = { sessionId: tabId, title: title ?? 'Workbench', type: 'workbench', status: 'idle', workbenchSessionId: sessionId }
      this.tabs.push(t)
      this.activeTabId = t.sessionId
      return t.sessionId
    },

    openWorkflowTab() {
      const t: Tab = { sessionId: 'workflows', title: 'Workflows', type: 'workflows', status: 'idle' }
      this.tabs = this.tabs.filter(x => x.sessionId !== 'workflows')
      this.tabs.push(t)
      this.activeTabId = t.sessionId
    },

    openDesignTab() {
      const t: Tab = { sessionId: 'design', title: 'Design', type: 'design', status: 'idle' }
      this.tabs = this.tabs.filter(x => x.sessionId !== 'design')
      this.tabs.push(t)
      this.activeTabId = t.sessionId
    },

    moveTab(fromIndex: number, toIndex: number) {
      if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0 ||
          fromIndex >= this.tabs.length || toIndex >= this.tabs.length) return
      const [moved] = this.tabs.splice(fromIndex, 1)
      this.tabs.splice(toIndex, 0, moved)
      persistTabs(this.tabs)
    },
  },
})

// ─── Backward compat: App.vue imports `useTabs` with the old tab shape ──
// The old Vue App.vue uses { id, kind, title, dirty, busy } tabs.
// `useTabStore` above uses the React shape { sessionId, type, title, status }.
// For the Vue shell (App.vue, MadcopTabstrip, etc.) we provide a thin
// `useTabs` wrapper that maps the React shape to the old Vue shape.
// New P0 components should use `useTabStore` directly.

export const useTabs = defineStore('madcop-tabs-vue-shell', {
  state: () => ({
    tabs: [] as Array<{ id: string; kind: string; title: string; dirty?: boolean; busy?: boolean }>,
    activeTabId: null as string | null,
  }),

  actions: {
    open(opts: { kind: string; title: string }) {
      const t = { id: `t${Date.now()}`, kind: opts.kind, title: opts.title }
      this.tabs.push(t)
      this.activeTabId = t.id
    },
    select(id: string) { this.activeTabId = id },
    close(id: string) {
      this.tabs = this.tabs.filter(t => t.id !== id)
      if (this.activeTabId === id) {
        this.activeTabId = this.tabs[this.tabs.length - 1]?.id ?? null
      }
    },
    closeAll() { this.tabs = []; this.activeTabId = null },
  },
})