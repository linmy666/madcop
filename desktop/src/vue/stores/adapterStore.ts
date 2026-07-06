// v3.0 — AdapterStore stub
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAdapterStore = defineStore('adapter', () => {
  const adapters = ref<any[]>([])
  const loading = ref(false)
  
  async function fetchAdapters() {
    loading.value = true
    try {
      const res = await fetch('/api/adapters')
      if (res.ok) adapters.value = await res.json()
    } catch {}
    loading.value = false
  }
  
  return { adapters, loading, fetchAdapters }
})