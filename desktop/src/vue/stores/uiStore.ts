import { defineStore } from 'pinia'

/**
 * Pinia mirror of stores/uiStore.ts
 * Theme, sidebar state, modals, toasts.
 */

const THEME_STORAGE_KEY = 'madcop-agent-theme'

function getStoredTheme(): 'light' | 'dark' {
  if (typeof localStorage === 'undefined') return 'dark'
  try { return (localStorage.getItem(THEME_STORAGE_KEY) as 'light' | 'dark') ?? 'dark' }
  catch { return 'dark' }
}

let toastCounter = 0

export const useUIStore = defineStore('ui', {
  state: () => ({
    theme: getStoredTheme() as 'light' | 'dark',
    sidebarOpen: true,
    activeView: 'code' as 'code' | 'browser' | 'workspace',
    pendingSettingsTab: null as string | null,
    pendingMemoryPath: null as string | null,
    activeModal: null as string | null,
    toasts: [] as Array<{ id: string; message: string; type: 'info' | 'success' | 'error' }>,
  }),

  actions: {
    setTheme(theme: 'light' | 'dark') {
      this.theme = theme
      try { localStorage.setItem(THEME_STORAGE_KEY, theme) } catch { /* noop */ }
    },
    setSidebarOpen(open: boolean) {
      this.sidebarOpen = open
    },
    setActiveView(view: 'code' | 'browser' | 'workspace') {
      this.activeView = view
    },
    setPendingSettingsTab(tab: string | null) {
      this.pendingSettingsTab = tab
    },
    setActiveModal(modal: string | null) {
      this.activeModal = modal
    },
    showToast(message: string, type: 'info' | 'success' | 'error' = 'info') {
      const id = `toast-${++toastCounter}`
      this.toasts.push({ id, message, type })
      setTimeout(() => {
        this.toasts = this.toasts.filter(t => t.id !== id)
      }, 4000)
    },
    removeToast(id: string) {
      this.toasts = this.toasts.filter(t => t.id !== id)
    },
  },
})
