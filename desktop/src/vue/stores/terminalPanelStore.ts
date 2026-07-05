// v3.0 — TerminalPanelStore (Vue 3 Pinia)
// Stub for terminal panel state management.
import { defineStore } from 'pinia'

export interface TerminalPanelState {
  panels: Map<string, { isOpen: boolean; sessionId: string | null }>
}

export const TERMINAL_PANEL_DEFAULT_HEIGHT = 240
export const TERMINAL_PANEL_MAX_HEIGHT = 600
export const TERMINAL_PANEL_MIN_HEIGHT = 120

export const useTerminalPanelStore = defineStore('terminalPanel', {
  state: (): TerminalPanelState => ({
    panels: new Map(),
  }),
  actions: {
    isPanelOpen(tabId: string): boolean {
      return this.panels.get(tabId)?.isOpen ?? false
    },
    clearSession(tabId: string): void {
      this.panels.delete(tabId)
    },
    togglePanel(tabId: string): void {
      const panel = this.panels.get(tabId)
      if (panel) {
        panel.isOpen = !panel.isOpen
      } else {
        this.panels.set(tabId, { isOpen: true, sessionId: null })
      }
    },
    setPanel(tabId: string, sessionId: string | null): void {
      this.panels.set(tabId, { isOpen: true, sessionId })
    },
  },
})