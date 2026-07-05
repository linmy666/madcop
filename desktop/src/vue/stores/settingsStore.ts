import { defineStore } from 'pinia'

/**
 * Pinia mirror of stores/settingsStore.ts
 * Current model, settings, themes, output style.
 */

export type ModelInfo = {
  id: string
  name: string
  provider?: string
}

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    permissionMode: 'default' as string,
    currentModel: null as ModelInfo | null,
    effortLevel: 'max' as string,
    thinkingEnabled: true,
    autoDreamEnabled: false,
    availableModels: [] as ModelInfo[],
    activeProviderName: null as string | null,
    locale: 'en' as string,
    chatSendBehavior: 'enter' as string,
    outputStyle: 'Learning' as string,
    // Desktop terminal settings
    desktopTerminal: {
      shellPath: '/bin/bash',
      fontSize: 13,
      lineSpacing: 1.5,
      showScrollbar: true,
      enableSuggestion: true,
    },
  }),

  actions: {
    setCurrentModel(model: ModelInfo) {
      this.currentModel = model
    },
    setEffortLevel(level: string) {
      this.effortLevel = level
    },
    setPermissionMode(mode: string) {
      this.permissionMode = mode
    },
    setLocale(locale: string) {
      this.locale = locale
    },
    setDesktopTerminal(patch: Partial<typeof this.desktopTerminal>) {
      Object.assign(this.desktopTerminal, patch)
    },
    setChatSendBehavior(behavior: string) {
      this.chatSendBehavior = behavior
    },
  },
})
