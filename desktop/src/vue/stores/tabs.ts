// v3.0 — MadCop tabs store (Pinia)
// Mirrors the React useTabStore (zustand-style). The Vue 3 world
// uses Pinia; this is the single source of truth for the tab list
// shown in the top tab strip.

import { defineStore } from 'pinia'
import { ref } from 'vue'

export type MadcopTabKind = 'chat' | 'design' | 'workflow' | 'trace'

export interface MadcopTab {
  id: string
  kind: MadcopTabKind
  title: string
  dirty?: boolean
  busy?: boolean
}

let counter = 0
function newId() {
  counter += 1
  return `t${Date.now()}${counter}`
}

export const useTabs = defineStore('madcop-tabs', () => {
  const tabs = ref<MadcopTab[]>([])
  const activeTabId = ref<string | null>(null)

  function open(opts: { kind: MadcopTabKind; title: string }) {
    const t: MadcopTab = { id: newId(), kind: opts.kind, title: opts.title }
    tabs.value.push(t)
    activeTabId.value = t.id
  }

  function select(id: string) { activeTabId.value = id }
  function close(id: string) {
    tabs.value = tabs.value.filter((t) => t.id !== id)
    if (activeTabId.value === id) {
      activeTabId.value = tabs.value[tabs.value.length - 1]?.id ?? null
    }
  }
  function closeAll() { tabs.value = []; activeTabId.value = null }

  return { tabs, activeTabId, open, select, close, closeAll }
})
