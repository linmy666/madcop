// v3.0 — TerminalPanelStore (Vue 3 Pinia)
// State for the per-session terminal panel UI (open/closed, height, runtime).
//
// P1-6/P2-11: the previous `panels` Map keyed by tabId was dead — every
// consumer (ActiveSession.vue) actually reads `panelBySession[tabId]` and
// `height`. The old API also conflated two different ID namespaces:
//   - `terminalApi.session_id` (number) = node-pty backend session ID,
//     returned by `spawn()` and used to write/resize/kill.
//   - the panel `runtimeId` (string) = the renderer-side TerminalRuntime
//     identifier we attach a PTY to (also known as a tabId).
// These never collide, so we keep them typed as number/string and just
// stop pretending `terminalPanelStore.sessionId` was one of them.
import { defineStore } from 'pinia'

export interface PanelEntry {
  runtimeId: string
}

export interface TerminalPanelState {
  /** Map of tabId -> attached runtime id. */
  panelBySession: Record<string, PanelEntry>
  /** Current panel height in px (resizable). */
  height: number
}

export const TERMINAL_PANEL_DEFAULT_HEIGHT = 240
export const TERMINAL_PANEL_MAX_HEIGHT = 600
export const TERMINAL_PANEL_MIN_HEIGHT = 120

export const useTerminalPanelStore = defineStore('terminalPanel', {
  state: (): TerminalPanelState => ({
    panelBySession: {},
    height: TERMINAL_PANEL_DEFAULT_HEIGHT,
  }),
  actions: {
    /** Open (or refresh) the terminal panel for `tabId` with the given
     *  renderer-side `runtimeId`. Idempotent — re-opening updates the
     *  attached runtime without resetting the height. */
    openPanel(tabId: string, runtimeId: string): void {
      this.panelBySession[tabId] = { runtimeId }
    },
    closePanel(tabId: string): void {
      delete this.panelBySession[tabId]
    },
    /** Drop the runtime attachment (e.g. on tab switch) but keep the
     *  panel open so height is preserved. */
    detachRuntime(tabId: string): void {
      if (this.panelBySession[tabId]) {
        delete this.panelBySession[tabId]
      }
    },
    setHeight(px: number): void {
      const clamped = Math.min(
        TERMINAL_PANEL_MAX_HEIGHT,
        Math.max(TERMINAL_PANEL_MIN_HEIGHT, Math.round(px)),
      )
      this.height = clamped
    },
  },
})