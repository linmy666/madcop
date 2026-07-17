import { defineStore } from 'pinia'
import { getApiUrl } from '../api/client'

/**
 * Provider store — mirrors the backend /api/settings providers list.
 *
 * Previously this was a hardcoded 4-item stub (openai/anthropic/deepseek/
 * zhipu) whose fetchProviders() was a no-op. Now it loads the real
 * provider list from the backend so any component using
 * useProviderStore().providers sees what's actually configured.
 */

export type ProviderInfo = {
  id: string
  name: string
  description: string
  apiKey?: string
  baseUrl?: string
  model?: string
  enabled: boolean
  hasKey?: boolean
  temperature?: number
  maxTokens?: number
}

export const useProviderStore = defineStore('provider', {
  state: () => ({
    providers: [] as ProviderInfo[],
    providerOrder: [] as string[],
    activeId: null as string | null,
    hasLoadedProviders: false,
    isLoading: false,
    error: null as string | null,
  }),

  actions: {
    async fetchProviders() {
      this.isLoading = true
      this.error = null
      try {
        const res = await fetch(getApiUrl('/api/settings'))
        if (!res.ok) {
          this.error = `加载供应商失败: ${res.status}`
          return
        }
        const data = await res.json()
        this.activeId = data.active_provider || null
        this.providers = (data.providers || []).map((p: any) => ({
          id: p.provider_id,
          name: p.label || p.provider_id,
          description: p.notes || '',
          apiKey: p.api_key_masked || '',
          baseUrl: p.base_url || '',
          model: p.model || '',
          enabled: p.has_key !== false,
          hasKey: p.has_key,
          temperature: p.temperature,
          maxTokens: p.max_tokens,
        }))
        this.providerOrder = this.providers.map((p) => p.id)
        this.hasLoadedProviders = true
      } catch (err: any) {
        this.error = err?.message || '网络错误'
      } finally {
        this.isLoading = false
      }
    },
    setActiveProvider(id: string | null) {
      this.activeId = id
    },
  },
})
