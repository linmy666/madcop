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

export type { ModelInfo } from '../types/settings'

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

/**
 * Persistence (P0-3): the settings store has no pinia-plugin-persistedstate,
 * so we persist a curated subset of user-facing preferences to localStorage
 * manually — matching the pattern used by uiStore (theme) and tabStore.
 *
 * Only user preferences are persisted; derived/server-state fields
 * (availableModels, activeProviderName, h5Access*) are re-fetched on load.
 */
const SETTINGS_STORAGE_KEY = 'madcop-agent-settings'

/** P2-NS — default state for the Proactive Observer.
 *  If the user has already picked a workspace (madcop_workspace_dir),
 *  enable the observer + file/terminal watching so the
 *  "open MadCop and it works" experience matches the resume claim.
 *  Otherwise default to opt-in (everything off) so we don't fire
 *  out of the blue at first-time users. */
function _initialProactiveState(): { enabled: boolean; observeFiles: boolean; observeTerminal: boolean } {
  try {
    if (typeof localStorage !== 'undefined' && localStorage.getItem('madcop_workspace_dir')) {
      return { enabled: true, observeFiles: true, observeTerminal: true }
    }
  } catch { /* SSR / restricted storage */ }
  return { enabled: false, observeFiles: false, observeTerminal: false }
}

const PERSIST_KEYS = [
  'permissionMode',
  'currentModel',
  'effortLevel',
  'thinkingEnabled',
  'autoDreamEnabled',
  'locale',
  'chatSendBehavior',
  'outputStyle',
  'desktopTerminal',
  'proactive',
] as const

function loadPersistedSettings(): Record<string, unknown> {
  try {
    const raw = localStorage.getItem(SETTINGS_STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

/** Merge persisted values into the default state (defensive: only known keys). */
function initPersistedState(): Record<string, unknown> {
  const persisted = loadPersistedSettings()
  const out: Record<string, unknown> = {}
  for (const k of PERSIST_KEYS) {
    if (k in persisted) out[k] = persisted[k]
  }
  return out
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
    /** True once /api/settings has answered (even on error) — gates the
     *  empty-state hero so it never flashes the setup CTA prematurely. */
    settingsLoaded: false,
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
    // P2-NS — Proactive Observer: auto-on if user already picked a workspace.
    // First-time users still see opt-in (default off) so we don't fire
    // out of the blue. Once they've selected a project folder
    // (madcop_workspace_dir is set), enable both file + terminal watching
    // so the "open MadCop and it works" experience matches the resume.
    proactive: _initialProactiveState() as { enabled: boolean; observeFiles: boolean; observeTerminal: boolean },
    // P0-3 — restore persisted user preferences over the defaults above.
    ...initPersistedState(),
  }),

  actions: {
    /** P0-3 — persist the curated preference subset to localStorage. */
    _persist() {
      try {
        const snapshot: Record<string, unknown> = {}
        for (const k of PERSIST_KEYS) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          snapshot[k] = (this as any)[k]
        }
        localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(snapshot))
      } catch {
        /* quota / disabled — ignore */
      }
    },
    setCurrentModel(model: ModelInfo) {
      this.currentModel = model
      this._persist()
    },
    setEffortLevel(level: string) {
      this.effortLevel = level
      this._persist()
    },
    setPermissionMode(mode: string) {
      this.permissionMode = mode
      this._persist()
    },
    setLocale(locale: string) {
      this.locale = locale
      // v4 fix: actually update the i18n module's translation table
      // so all useTranslation() calls pick up the new locale.
      import('../i18n').then(({ setLocale: i18nSetLocale }) => {
        i18nSetLocale(locale as any)
      })
      this._persist()
    },
    setDesktopTerminal(patch: Partial<typeof this.desktopTerminal>) {
      Object.assign(this.desktopTerminal, patch)
      this._persist()
    },
    setChatSendBehavior(behavior: string) {
      this.chatSendBehavior = behavior
      this._persist()
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
              providerId: p.provider_id,
              providerName: p.label || p.provider_id,
            } as ModelInfo)
          }
        }
        this.availableModels = models
        const active = providers.find((p: any) => p.provider_id === data?.active_provider)
        if (active?.model) {
          this.currentModel = {
            id: `${active.provider_id}:${active.model}`,
            name: active.model,
            providerId: active.provider_id,
            providerName: active.label || active.provider_id,
          } as ModelInfo
        }
        // Marks the backend fetch as done — the empty-state hero uses this
        // to avoid flashing 「先配置一个 AI 模型供应商」 while the request
        // is still in flight (the app IS configured).
        this.settingsLoaded = true
      } catch {
        /* keep local state */
        this.settingsLoaded = true
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
    /** Sprint 5 — toggle the proactive observer on/off + per-source. */
    setProactive(settings: { enabled?: boolean; observeFiles?: boolean; observeTerminal?: boolean }): void {
      if (typeof settings.enabled === 'boolean') this.proactive.enabled = settings.enabled
      if (typeof settings.observeFiles === 'boolean') this.proactive.observeFiles = settings.observeFiles
      if (typeof settings.observeTerminal === 'boolean') this.proactive.observeTerminal = settings.observeTerminal
      this._persist()
    },
  },
})
