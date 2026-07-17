// Adapter store — IM channel adapters (WeChat / DingTalk / WhatsApp stubs on API).
import { defineStore } from 'pinia'
import { getApiUrl } from '../api/client'

export type AdapterRecord = {
  id?: string
  platform?: string
  name?: string
  status?: string
  [key: string]: unknown
}

export const useAdapterStore = defineStore('adapter', {
  state: () => ({
    adapters: [] as AdapterRecord[],
    loading: false,
    error: null as string | null,
  }),
  actions: {
    async fetchAdapters() {
      this.loading = true
      this.error = null
      try {
        const res = await fetch(getApiUrl('/api/adapters'))
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        this.adapters = Array.isArray(data?.adapters)
          ? data.adapters
          : Array.isArray(data)
            ? data
            : []
      } catch (e: any) {
        this.error = e?.message || String(e)
        this.adapters = []
      } finally {
        this.loading = false
      }
    },
  },
})
