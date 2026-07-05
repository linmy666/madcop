import { defineStore } from 'pinia'

export type UpdateProxyMode = 'system' | 'manual'

export type UpdateProxySettings = {
  mode: UpdateProxyMode
  url: string
}

/**
 * Pinia mirror of stores/settingsStore.ts
 * Current model, settings, themes, output style.
 */

/**
 * Pinia mirror of stores/settingsStore.ts
 * Current model, settings, themes, output style.
 * H5Access state added for Phase 2 translation.
 */

export type ModelInfo = {
  id: string
  name: string
  provider?: string
}

export type H5AccessSettings = {
  enabled: boolean
  token: string | null
  tokenPreview: string | null
  allowedOrigins: string[]
  publicBaseUrl: string | null
  fixedPort: number | null
  disconnectGraceSeconds: number | null
}

export type H5HostStaleness = 'ok' | 'unreachable' | 'proxy' | 'unset'

export type H5AccessDiagnostics = {
  storedHostStaleness: H5HostStaleness
  storedPublicBaseUrl: string | null
  effectivePublicBaseUrl: string | null
  suggestedHost: string | null
  localInterfaceHosts: string[]
  activePort?: number
}

const DEFAULT_H5_ACCESS_SETTINGS: H5AccessSettings = {
  enabled: false,
  token: null,
  tokenPreview: null,
  allowedOrigins: [],
  publicBaseUrl: null,
  fixedPort: null,
  disconnectGraceSeconds: null,
}

const DEFAULT_UPDATE_PROXY_SETTINGS: UpdateProxySettings = {
  mode: 'system',
  url: '',
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
    // H5Access state
    h5Access: DEFAULT_H5_ACCESS_SETTINGS as H5AccessSettings,
    h5AccessDiagnostics: null as H5AccessDiagnostics | null,
    h5AccessError: null as string | null,
    // Update proxy settings
    updateProxy: DEFAULT_UPDATE_PROXY_SETTINGS as UpdateProxySettings,
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

    // ── H5Access actions ──────────────────────────────────────
    async enableH5Access(): Promise<string> {
      // Stub: in production would call API
      this.h5AccessError = null
      try {
        // Simulate API call
        await new Promise((resolve) => setTimeout(resolve, 100))
        const token = 'h5_' + Math.random().toString(36).slice(2, 22)
        this.h5Access = { ...this.h5Access, enabled: true, token, tokenPreview: token.slice(0, 8) + '...' }
        return token
      } catch (e) {
        this.h5AccessError = e instanceof Error ? e.message : 'Failed to enable H5 access'
        throw e
      }
    },

    async disableH5Access(): Promise<void> {
      this.h5AccessError = null
      try {
        await new Promise((resolve) => setTimeout(resolve, 100))
        this.h5Access = { ...this.h5Access, enabled: false, token: null, tokenPreview: null }
      } catch (e) {
        this.h5AccessError = e instanceof Error ? e.message : 'Failed to disable H5 access'
        throw e
      }
    },

    async regenerateH5AccessToken(): Promise<string> {
      this.h5AccessError = null
      try {
        await new Promise((resolve) => setTimeout(resolve, 100))
        const token = 'h5_' + Math.random().toString(36).slice(2, 22)
        this.h5Access = { ...this.h5Access, token, tokenPreview: token.slice(0, 8) + '...' }
        return token
      } catch (e) {
        this.h5AccessError = e instanceof Error ? e.message : 'Failed to regenerate token'
        throw e
      }
    },

    async updateH5AccessSettings(input: {
      allowedOrigins?: string[]
      publicBaseUrl?: string | null
      fixedPort?: number | null
      disconnectGraceSeconds?: number | null
    }): Promise<void> {
      this.h5AccessError = null
      try {
        await new Promise((resolve) => setTimeout(resolve, 100))
        this.h5Access = { ...this.h5Access, ...input }
      } catch (e) {
        this.h5AccessError = e instanceof Error ? e.message : 'Failed to update H5 access settings'
        throw e
      }
    },

    fetchH5Access(): Promise<void> {
      // Stub: in production would fetch from API
      return Promise.resolve()
    },

    setUpdateProxy(settings: UpdateProxySettings): void {
      this.updateProxy = {
        mode: settings.mode,
        url: settings.url.trim(),
      }
    },
  },
})
