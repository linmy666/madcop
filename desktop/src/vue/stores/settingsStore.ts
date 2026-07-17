import { defineStore } from 'pinia'
import { getApiUrl } from '../api/client'

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

    /** Load providers/models from GET /api/settings into store. */
    async loadFromBackend(): Promise<void> {
      try {
        const res = await fetch(getApiUrl('/api/settings'))
        if (!res.ok) return
        const data = await res.json()
        const providers = data?.providers || []
        this.activeProviderName = data?.active_provider || null
        const models: ModelInfo[] = []
        for (const p of providers) {
          if (p.model) {
            models.push({
              id: `${p.provider_id}:${p.model}`,
              name: p.model,
              provider: p.label || p.provider_id,
            })
          }
        }
        this.availableModels = models
        const active = providers.find((p: any) => p.provider_id === data?.active_provider)
        if (active?.model) {
          this.currentModel = {
            id: `${active.provider_id}:${active.model}`,
            name: active.model,
            provider: active.label || active.provider_id,
          }
        }
      } catch {
        /* keep local state */
      }
    },

    // ── H5Access actions ──────────────────────────────────────
    async enableH5Access(): Promise<string> {
      this.h5AccessError = null
      try {
        const res = await fetch(getApiUrl('/api/h5-access/enable'), { method: 'POST' })
        if (res.ok) {
          const data = await res.json()
          const token = data?.token || data?.accessToken
          if (token) {
            this.h5Access = {
              ...this.h5Access,
              enabled: true,
              token,
              tokenPreview: String(token).slice(0, 8) + '...',
            }
            return token
          }
        }
        // Fallback local token if endpoint missing
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
        await fetch(getApiUrl('/api/h5-access/disable'), { method: 'POST' }).catch(() => null)
        this.h5Access = { ...this.h5Access, enabled: false, token: null, tokenPreview: null }
      } catch (e) {
        this.h5AccessError = e instanceof Error ? e.message : 'Failed to disable H5 access'
        throw e
      }
    },

    async regenerateH5AccessToken(): Promise<string> {
      this.h5AccessError = null
      try {
        const res = await fetch(getApiUrl('/api/h5-access/regenerate'), { method: 'POST' })
        if (res.ok) {
          const data = await res.json()
          if (data?.token) {
            this.h5Access = {
              ...this.h5Access,
              token: data.token,
              tokenPreview: String(data.token).slice(0, 8) + '...',
            }
            return data.token
          }
        }
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
        await fetch(getApiUrl('/api/h5-access'), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(input),
        }).catch(() => null)
        this.h5Access = { ...this.h5Access, ...input }
      } catch (e) {
        this.h5AccessError = e instanceof Error ? e.message : 'Failed to update H5 access settings'
        throw e
      }
    },

    async fetchH5Access(): Promise<void> {
      try {
        const res = await fetch(getApiUrl('/api/h5-access'))
        if (!res.ok) return
        const data = await res.json()
        if (data && typeof data === 'object') {
          this.h5Access = { ...this.h5Access, ...data }
        }
      } catch {
        /* keep defaults */
      }
    },

    setUpdateProxy(settings: UpdateProxySettings): void {
      this.updateProxy = {
        mode: settings.mode,
        url: settings.url.trim(),
      }
    },
  },
})
