// v3.0 — MadCop unified tab store (Pinia)
// Replaces both tabStore.ts (stub) and tabs.ts (zustand-style).
// All Vue components import from THIS file.

import { defineStore } from 'pinia'
import { ref } from 'vue'

// ─── Constants ─────────────────────────────────────────────────────

export const SETTINGS_TAB_ID = '__settings__'
export const SCHEDULED_TAB_ID = '__scheduled__'
export const TRACE_LIST_TAB_ID = '__traces__'
export const TERMINAL_TAB_PREFIX = '__terminal__'
export const TRACE_TAB_PREFIX = '__trace__'
export const WORKBENCH_TAB_PREFIX = '__workbench__'

// ─── Types ─────────────────────────────────────────────────────────

export type TabType = 'session' | 'settings' | 'scheduled' | 'terminal' | 'trace' | 'traces' | 'workbench' | 'workflows' | 'design' | 'agents' | 'knowledge' | 'skill-builder' | 'usage-stats' | 'arena'

export interface Tab {
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

const TAB_STORAGE_KEY = 'madcop_tabs'
const ACTIVE_TAB_STORAGE_KEY = 'madcop_active_tab'

function loadTabs(): Tab[] {
  try {
    const raw = localStorage.getItem(TAB_STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {}
  return []
}

function loadActiveTabId(): string | null {
  try {
    return localStorage.getItem(ACTIVE_TAB_STORAGE_KEY)
  } catch {
    return null
  }
}

export function saveTabs(tabs: Tab[]) {
  try {
    // Only persist session-type tabs (skip system tabs)
    const persistable = tabs.filter((t) => t.type === 'session')
    localStorage.setItem(TAB_STORAGE_KEY, JSON.stringify(persistable))
  } catch {}
}

function saveActiveTabId(id: string | null) {
  try {
    if (id) localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, id)
    else localStorage.removeItem(ACTIVE_TAB_STORAGE_KEY)
  } catch {}
}

export const useTabStore = defineStore('madcop-tabs', () => {
  const tabs = ref<Tab[]>(loadTabs())
  const activeTabId = ref<string | null>(loadActiveTabId())

  function openTab(sessionId: string, title: string, type: TabType = 'session') {
    // If tab already exists, activate it
    const existing = tabs.value.find((t) => t.sessionId === sessionId)
    if (existing) {
      existing.title = title
      activeTabId.value = sessionId
      saveActiveTabId(activeTabId.value)
      return
    }
    tabs.value.push({ sessionId, title, type, status: 'idle' })
    activeTabId.value = sessionId
    saveTabs(tabs.value)
    saveActiveTabId(activeTabId.value)
  }

  function setActiveTab(id: string | null) {
    activeTabId.value = id
    saveActiveTabId(id)
  }

  function closeTab(id: string) {
    const idx = tabs.value.findIndex((t) => t.sessionId === id)
    if (idx === -1) return
    tabs.value.splice(idx, 1)
    if (activeTabId.value === id) {
      const next = tabs.value[tabs.value.length - 1]
      activeTabId.value = next?.sessionId ?? null
    }
    saveTabs(tabs.value)
    saveActiveTabId(activeTabId.value)
  }

  function openTerminalTab(cwd?: string, terminalRuntimeId?: string) {
    const id = `${TERMINAL_TAB_PREFIX}-${Date.now()}`
    tabs.value.push({
      sessionId: id,
      title: 'Terminal',
      type: 'terminal',
      status: 'idle',
      terminalCwd: cwd,
      terminalRuntimeId,
    })
    activeTabId.value = id
  }

  function moveTab(fromIndex: number, toIndex: number) {
    if (fromIndex < 0 || fromIndex >= tabs.value.length) return
    if (toIndex < 0 || toIndex >= tabs.value.length) return
    const [moved] = tabs.value.splice(fromIndex, 1)
    tabs.value.splice(toIndex, 0, moved)
  }

  // ─── Sidebar nav-item helpers (open specific tab by type) ───
  function openWorkflowsTab() {
    openTab('__workflows__', '工作流', 'workflows' as TabType)
  }
  function openDesignTab() {
    openTab('__design__', '设计工具', 'design' as TabType)
  }
  function openAgentHubTab() {
    openTab('__agent_hub__', 'Agent 中心', 'workflows' as TabType)
  }
  function openKnowledgeTab() {
    openTab('__knowledge__', '知识库', 'workflows' as TabType)
  }
  function openSkillBuilderTab() {
    openTab('__skill_builder__', '技能构建器', 'skill-builder' as TabType)
  }
  function openUsageStatsTab() {
    openTab('__usage_stats__', '用量统计', 'usage-stats' as TabType)
  }
  function openArenaTab() {
    openTab('__arena__', 'Arena', 'arena' as TabType)
  }

  return {
    tabs,
    activeTabId,
    openTab,
    setActiveTab,
    closeTab,
    openTerminalTab,
    moveTab,
    openWorkflowsTab,
    openDesignTab,
    openAgentHubTab,
    openKnowledgeTab,
    openSkillBuilderTab,
    openUsageStatsTab,
    openArenaTab,
  }
})
