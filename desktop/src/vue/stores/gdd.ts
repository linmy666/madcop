/** GDD reference store (stub — full implementation in future) */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface GDDRef {
  systemId: string
  ref: string
}

export const useGDDStore = defineStore('gdd', () => {
  const gddRefs = ref<GDDRef[]>([])

  function addGDDRef(systemId: string, ref: string) {
    gddRefs.value.push({ systemId, ref })
  }

  function removeGDDRef(idx: number) {
    gddRefs.value.splice(idx, 1)
  }

  return { gddRefs, addGDDRef, removeGDDRef }
})
