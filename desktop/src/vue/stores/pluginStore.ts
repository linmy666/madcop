import { defineStore } from 'pinia'
import { getApiUrl } from '../api/client'
import type { PluginDetail, PluginReloadSummary, PluginScope, PluginSummary } from '../../types/plugin'

/**
 * Pinia plugin store — wired to /api/plugins.
 */

type PluginActionTarget = {
  id: string
  scope?: PluginScope
}

async function pluginsAction(
  action: string,
  body: Record<string, unknown> = {},
): Promise<any> {
  const res = await fetch(getApiUrl(`/api/plugins/${action}`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`plugins/${action} HTTP ${res.status}`)
  return res.json().catch(() => ({}))
}

function normalizePlugin(raw: any): PluginSummary {
  return {
    id: raw?.id || raw?.name || 'unknown',
    name: raw?.name || raw?.id || 'unknown',
    version: raw?.version || '0.0.0',
    enabled: raw?.enabled !== false,
    description: raw?.description || '',
    scope: raw?.scope,
    hasErrors: Boolean(raw?.hasErrors || raw?.errors),
    path: raw?.path,
    ...raw,
  } as PluginSummary
}

export const usePluginStore = defineStore('plugin', {
  state: () => ({
    plugins: [] as PluginSummary[],
    marketplaces: [] as any[],
    summary: null as any | null,
    selectedPlugin: null as PluginDetail | null,
    lastReloadSummary: null as PluginReloadSummary | null,
    isLoading: false,
    isDetailLoading: false,
    isApplying: false,
    error: null as string | null,
  }),

  actions: {
    async fetchPlugins(_cwd?: string) {
      this.isLoading = true
      this.error = null
      try {
        const res = await fetch(getApiUrl('/api/plugins'))
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        const list = Array.isArray(data?.plugins) ? data.plugins : []
        this.plugins = list.map(normalizePlugin)
        this.summary = {
          total: this.plugins.length,
          enabled: this.plugins.filter((p) => p.enabled).length,
          attention: this.plugins.filter((p: any) => p.hasErrors).length,
          marketplaces: Array.isArray(data?.marketplaces) ? data.marketplaces.length : 0,
        }
        this.marketplaces = data?.marketplaces || []
      } catch (e: any) {
        this.error = e.message
        this.plugins = []
      } finally {
        this.isLoading = false
      }
    },
    selectPlugin(plugin: PluginDetail | null) {
      this.selectedPlugin = plugin
    },
    clearSelection() {
      this.selectedPlugin = null
    },

    async enablePlugin(id: string, scope?: PluginScope, _cwd?: string, _sessionId?: string): Promise<string> {
      this.isApplying = true
      try {
        await pluginsAction('enable', { id, name: id, scope })
        await this.fetchPlugins()
        return 'Plugin enabled'
      } finally {
        this.isApplying = false
      }
    },

    async disablePlugin(id: string, scope?: PluginScope, _cwd?: string, _sessionId?: string): Promise<string> {
      this.isApplying = true
      try {
        await pluginsAction('disable', { id, name: id, scope })
        await this.fetchPlugins()
        return 'Plugin disabled'
      } finally {
        this.isApplying = false
      }
    },

    async updatePlugin(id: string, scope?: PluginScope, _cwd?: string, _sessionId?: string): Promise<string> {
      this.isApplying = true
      try {
        await pluginsAction('update', { id, name: id, scope })
        await this.fetchPlugins()
        return 'Plugin updated'
      } finally {
        this.isApplying = false
      }
    },

    async uninstallPlugin(id: string, scope?: PluginScope, _keepData = false, _cwd?: string, _sessionId?: string): Promise<string> {
      this.isApplying = true
      try {
        await pluginsAction('uninstall', { id, name: id, scope })
        this.selectedPlugin = null
        await this.fetchPlugins()
        return 'Plugin uninstalled'
      } finally {
        this.isApplying = false
      }
    },

    async reloadPlugins(_cwd?: string, _sessionId?: string): Promise<PluginReloadSummary> {
      this.isApplying = true
      try {
        const data = await pluginsAction('reload', {})
        const summary: PluginReloadSummary = {
          enabled: data?.enabled ?? this.plugins.filter((p) => p.enabled).length,
          disabled: data?.disabled ?? this.plugins.filter((p) => !p.enabled).length,
          skills: data?.skills ?? 0,
          agents: data?.agents ?? 0,
          hooks: data?.hooks ?? 0,
          mcpServers: data?.mcpServers ?? 0,
          lspServers: data?.lspServers ?? 0,
          errors: data?.errors ?? 0,
        }
        this.lastReloadSummary = summary
        await this.fetchPlugins()
        return summary
      } finally {
        this.isApplying = false
      }
    },

    async fetchPluginDetail(id: string, _cwd?: string) {
      this.isDetailLoading = true
      this.error = null
      try {
        const q = new URLSearchParams({ name: id })
        const res = await fetch(getApiUrl(`/api/plugins/detail?${q}`))
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        this.selectedPlugin = {
          id: data?.id || id,
          name: data?.manifest?.name || data?.id || id,
          ...data,
          ...data?.manifest,
        } as PluginDetail
        return this.selectedPlugin
      } catch (e: any) {
        this.error = e.message
        return null
      } finally {
        this.isDetailLoading = false
      }
    },
  },
})
