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
    // IM channel credentials + pairing state. Defaults to {} so every
    // `config.xxx?.yyy` access in AdapterSettings is safe before the
    // fetch resolves (an undefined config crashed the whole page).
    config: {} as Record<string, any>,
  }),
  actions: {
    async fetchConfig() {
      try {
        const res = await fetch(getApiUrl('/api/adapters/config'))
        if (!res.ok) return
        const data = await res.json()
        this.config = data?.config && typeof data.config === 'object' ? data.config : {}
      } catch { /* offline — keep previous config */ }
    },

    async updateConfig(patch: Record<string, unknown>) {
      const res = await fetch(getApiUrl('/api/adapters/config'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (data?.config) this.config = data.config
    },

    async generatePairingCode(): Promise<string | null> {
      const res = await fetch(getApiUrl('/api/adapters/pairing'), { method: 'POST' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      await this.fetchConfig()
      return data?.code ?? null
    },

    async removePairedUser(platform: string, userId: string | number) {
      await fetch(getApiUrl('/api/adapters/paired-users/remove'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ platform, userId }),
      })
    },

    async startWechatLogin() {
      const res = await fetch(getApiUrl('/api/adapters/wechat/login/start'), { method: 'POST' })
      return res.json()
    },

    async pollWechatLogin(sessionKey: string) {
      const res = await fetch(getApiUrl(`/api/adapters/wechat/login/poll?sessionKey=${encodeURIComponent(sessionKey)}`))
      const data = await res.json()
      return {
        connected: data?.status === 'confirmed',
        status: data?.status as string | undefined,
        message: (data?.message as string | undefined) ?? '',
      }
    },

    async unbindWechatAccount() {
      await fetch(getApiUrl('/api/adapters/wechat/unbind'), { method: 'POST' })
    },

    async startWhatsAppLogin() {
      const res = await fetch(getApiUrl('/api/adapters/whatsapp/login/start'), { method: 'POST' })
      return res.json()
    },

    async pollWhatsAppLogin(sessionKey: string) {
      const res = await fetch(getApiUrl(`/api/adapters/whatsapp/login/poll?sessionKey=${encodeURIComponent(sessionKey)}`))
      const data = await res.json()
      return {
        connected: data?.status === 'confirmed',
        status: data?.status as string | undefined,
        message: (data?.message as string | undefined) ?? '',
        qrDataUrl: (data?.qrDataUrl as string | undefined) ?? undefined,
      }
    },

    async unbindWhatsAppAccount() {
      await fetch(getApiUrl('/api/adapters/whatsapp/unbind'), { method: 'POST' })
    },

    async beginDingtalkRegistration() {
      const res = await fetch(getApiUrl('/api/adapters/dingtalk/registration/begin'), { method: 'POST' })
      return res.json()
    },

    async pollDingtalkRegistration(deviceCode: string) {
      const res = await fetch(getApiUrl(`/api/adapters/dingtalk/registration/poll?deviceCode=${encodeURIComponent(deviceCode)}`))
      return res.json()
    },

    async unbindDingtalkBot() {
      await fetch(getApiUrl('/api/adapters/dingtalk/unbind'), { method: 'POST' })
    },

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
