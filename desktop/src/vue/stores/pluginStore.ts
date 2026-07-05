import { defineStore } from 'pinia'
import type { PluginDetail, PluginReloadSummary, PluginScope, PluginSummary } from '../../types/plugin'

/**
 * Pinia mirror of stores/pluginStore.ts — extended for PluginDetail page.
 * Includes full detail state, applying flags, and all mutation actions (stubbed).
 */

type PluginActionTarget = {
  id: string
  scope?: PluginScope
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
        await new Promise((resolve) => setTimeout(resolve, 200))
      } catch (e: any) {
        this.error = e.message
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

    async enablePlugin(_id: string, _scope?: PluginScope, _cwd?: string, _sessionId?: string): Promise<string> {
      this.isApplying = true
      try {
        await new Promise((resolve) => setTimeout(resolve, 400))
        return 'Plugin enabled'
      } catch (err) {
        this.isApplying = false
        throw err
      } finally {
        this.isApplying = false
      }
    },

    async disablePlugin(_id: string, _scope?: PluginScope, _cwd?: string, _sessionId?: string): Promise<string> {
      this.isApplying = true
      try {
        await new Promise((resolve) => setTimeout(resolve, 400))
        return 'Plugin disabled'
      } catch (err) {
        this.isApplying = false
        throw err
      } finally {
        this.isApplying = false
      }
    },

    async updatePlugin(_id: string, _scope?: PluginScope, _cwd?: string, _sessionId?: string): Promise<string> {
      this.isApplying = true
      try {
        await new Promise((resolve) => setTimeout(resolve, 600))
        return 'Plugin updated'
      } catch (err) {
        this.isApplying = false
        throw err
      } finally {
        this.isApplying = false
      }
    },

    async uninstallPlugin(_id: string, _scope?: PluginScope, _keepData = false, _cwd?: string, _sessionId?: string): Promise<string> {
      this.isApplying = true
      try {
        await new Promise((resolve) => setTimeout(resolve, 800))
        this.selectedPlugin = null
        return 'Plugin uninstalled'
      } catch (err) {
        this.isApplying = false
        throw err
      } finally {
        this.isApplying = false
      }
    },

    async reloadPlugins(_cwd?: string, _sessionId?: string): Promise<PluginReloadSummary> {
      this.isApplying = true
      try {
        await new Promise((resolve) => setTimeout(resolve, 500))
        const summary: PluginReloadSummary = {
          enabled: 1,
          disabled: 0,
          skills: 0,
          agents: 0,
          hooks: 0,
          mcpServers: 0,
          lspServers: 0,
          errors: 0,
        }
        this.lastReloadSummary = summary
        return summary
      } catch (err) {
        this.isApplying = false
        throw err
      } finally {
        this.isApplying = false
      }
    },
  },
})