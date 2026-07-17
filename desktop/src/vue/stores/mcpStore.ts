import { defineStore } from 'pinia'
import { mcpApi } from '../api/mcp'
import type { McpServerRecord as ApiMcpServerRecord, McpUpsertPayload } from '../../types/mcp'

/**
 * Pinia MCP store — wired to /api/mcp via vue/api (port 8765).
 */

export type McpServerRecord = ApiMcpServerRecord & {
  summary?: string
  transport?: string
  projectPath?: string | null
}

export const useMcpStore = defineStore('mcp', {
  state: () => ({
    servers: [] as McpServerRecord[],
    selectedServer: null as McpServerRecord | null,
    isLoading: false,
    error: null as string | null,
  }),

  actions: {
    async fetchServers(_projectPaths?: string[], fallbackCwd?: string) {
      this.isLoading = true
      this.error = null
      try {
        const data = await mcpApi.list(fallbackCwd)
        this.servers = (data?.servers || []) as McpServerRecord[]
      } catch (err) {
        this.error = err instanceof Error ? err.message : 'Failed to load MCP servers'
        this.servers = []
      } finally {
        this.isLoading = false
      }
    },
    selectServer(server: McpServerRecord | null) {
      this.selectedServer = server
    },
    async createServer(name: string, payload: McpUpsertPayload, cwd?: string) {
      const res = await mcpApi.create(name, payload, cwd)
      await this.fetchServers(undefined, cwd)
      return res
    },
    async updateServer(name: string, payload: McpUpsertPayload, cwd?: string) {
      const res = await mcpApi.update(name, payload, cwd)
      await this.fetchServers(undefined, cwd)
      return res
    },
    async removeServer(name: string, scope: string, cwd?: string) {
      await mcpApi.remove(name, scope, cwd)
      if (this.selectedServer?.name === name) this.selectedServer = null
      await this.fetchServers(undefined, cwd)
    },
    async toggleServer(name: string, cwd?: string, sessionId?: string) {
      const res = await mcpApi.toggle(name, cwd, sessionId)
      await this.fetchServers(undefined, cwd)
      return res
    },
    async reconnectServer(name: string, cwd?: string) {
      const res = await mcpApi.reconnect(name, cwd)
      await this.fetchServers(undefined, cwd)
      return res
    },
    async importFromJson(raw: string, scope: string = 'user', cwd?: string) {
      let config: Record<string, unknown>
      try {
        config = JSON.parse(raw) as Record<string, unknown>
      } catch {
        throw new Error('Invalid JSON')
      }
      const res = await mcpApi.importConfig(config, scope)
      if (!res?.ok && res?.error) {
        throw new Error(res.error)
      }
      await this.fetchServers(undefined, cwd)
      return res
    },
    getState() {
      return { servers: this.servers, selectedServer: this.selectedServer }
    },
  },
})
