import { defineStore } from 'pinia'

/**
 * Pinia mirror of stores/providerStore.ts
 * AI model providers management.
 */

export type ProviderInfo = {
  id: string
  name: string
  description: string
  apiKey?: string
  baseUrl?: string
  model?: string
  enabled: boolean
}

export const useProviderStore = defineStore('provider', {
  state: () => ({
    providers: [
      { id: 'openai', name: 'OpenAI', description: 'GPT-4o and friends', enabled: true },
      { id: 'anthropic', name: 'Anthropic', description: 'Claude models', enabled: true },
      { id: 'deepseek', name: 'DeepSeek', description: 'DeepSeek-chat', enabled: true },
      { id: 'zhipu', name: 'Zhipu GLM', description: 'GLM-4 models', enabled: true },
    ] as ProviderInfo[],
    providerOrder: ['openai', 'anthropic', 'deepseek', 'zhipu'],
    activeId: 'openai' as string | null,
    hasLoadedProviders: false,
    isLoading: false,
    error: null as string | null,
  }),

  actions: {
    async fetchProviders() {
      this.isLoading = true
      this.error = null
      try {
        this.hasLoadedProviders = true
      } catch (err) {
        this.error = (err as Error).message
      }
      this.isLoading = false
    },
    setActiveProvider(id: string | null) {
      this.activeId = id
    },
  },
})
