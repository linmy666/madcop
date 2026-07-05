import { defineStore } from 'pinia'

/**
 * Pinia mirror of stores/mcpStore.ts — stubbed for PluginDetail page.
 */

export type McpServerRecord = {
  name: string
  scope: string
  projectPath?: string
  transport: string
  summary: string
}

export const useMcpStore = defineStore('mcp', {
  state: () => ({
    servers: [] as McpServerRecord[],
    selectedServer: null as McpServerRecord | null,
    isLoading: false,
    error: null as string | null,
  }),

  actions: {
    async fetchServers(_projectPaths?: string[], _fallbackCwd?: string) {
      this.isLoading = true
      this.error = null
      try {
        await new Promise((resolve) => setTimeout(resolve, 200))
      } catch (err) {
        this.error = err instanceof Error ? err.message : 'Failed to load MCP servers'
      } finally {
        this.isLoading = false
      }
    },
    selectServer(server: McpServerRecord | null) {
      this.selectedServer = server
    },
    getState() {
      return { servers: this.servers, selectedServer: this.selectedServer }
    },
  },
})