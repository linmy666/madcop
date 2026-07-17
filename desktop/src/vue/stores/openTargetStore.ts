// v3.0 — Pinia openTargetStore (mirrors React zustand useOpenTargetStore)
// Minimal: only ensureTargets() and openTarget() needed by Sidebar.
import { defineStore } from 'pinia'
import { openTargetsApi, type OpenTarget } from '../api/openTargets'

const CLIENT_CACHE_TTL_MS = 60_000

type OpenTargetState = {
  targets: OpenTarget[]
  platform: string | null
  lastSuccessfulTargetId: string | null
  loading: boolean
  fetchedAt: number
}

export const useOpenTargetStore = defineStore('openTarget', {
  state: (): OpenTargetState => ({
    targets: [],
    platform: null,
    lastSuccessfulTargetId: null,
    loading: false,
    fetchedAt: 0,
  }),

  actions: {
    async ensureTargets() {
      if (this.loading) return
      if (this.fetchedAt > 0 && Date.now() - this.fetchedAt < CLIENT_CACHE_TTL_MS) return
      await this.refreshTargets()
    },

    async refreshTargets() {
      this.loading = true
      try {
        const result = await openTargetsApi.list()
        this.targets = result.targets
        this.platform = result.platform
        this.fetchedAt = Date.now()
      } catch {
        // ignore
      } finally {
        this.loading = false
      }
    },

    async openTarget(targetId: string, path: string) {
      try {
        await openTargetsApi.open(targetId, path)
        this.lastSuccessfulTargetId = targetId
      } catch {
        // ignore
      }
    },
  },
})
