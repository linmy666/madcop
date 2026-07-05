import { defineStore } from 'pinia'

export interface PluginDefinition {
  id: string
  name: string
  description: string
  enabled: boolean
  source: string
}

export const usePluginStore = defineStore('plugin', {
  state: () => ({
    plugins: [] as PluginDefinition[],
    selectedPlugin: null as PluginDefinition | null,
    isLoading: false,
    error: null as string | null,
  }),
  actions: {
    async fetchPlugins() {
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
    selectPlugin(plugin: PluginDefinition | null) {
      this.selectedPlugin = plugin
    },
  },
})