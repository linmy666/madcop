/**
 * Pinia mirror of stores/tabStore.ts — stubbed for PluginDetail page.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

export type TabType = 'session' | 'settings' | 'scheduled' | 'terminal' | 'trace' | 'traces' | 'workbench' | 'workflows' | 'design'

export type Tab = {
  sessionId: string
  title: string
  type?: TabType
  status: 'idle' | 'running' | 'error'
}

export const SETTINGS_TAB_ID = '__settings__'
export const SCHEDULED_TAB_ID = '__scheduled__'

export const useTabStore = defineStore('tab', () => {
  const tabs = ref<Tab[]>([])
  const activeTabId = ref<string | null>(null)

  function openTab(sessionId: string, title: string, type: TabType = 'session') {
    const existing = tabs.value.find((t: Tab) => t.sessionId === sessionId)
    if (existing) {
      existing.title = title
      if (!existing.type) existing.type = type
    } else {
      tabs.value.push({ sessionId, title, type, status: 'idle' })
    }
    activeTabId.value = sessionId
  }

  return { tabs, activeTabId, openTab }
})