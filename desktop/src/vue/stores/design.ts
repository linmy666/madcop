/** Design system store (stub — full implementation in future) */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface DesignSystem {
  id: string
  name: string
  gddRefs: string[]
}

export interface DesignEntity {
  id: string
  name: string
  systemId: string
  type: string
}

export const useDesignStore = defineStore('design', () => {
  const systems = ref<DesignSystem[]>([])
  const entities = ref<DesignEntity[]>([])
  const gddRefs = ref<string[]>([])

  function addSystem(data: { name: string; gddRefs?: string[] }) {
    systems.value.push({ id: Date.now().toString(), name: data.name, gddRefs: data.gddRefs || [] })
  }

  function deleteSystem(systemId: string) {
    const idx = systems.value.findIndex(s => s.id === systemId)
    if (idx >= 0) systems.value.splice(idx, 1)
  }

  function addEntity(systemId: string, data: { name: string; type: string }) {
    entities.value.push({ id: Date.now().toString(), name: data.name, systemId, type: data.type })
  }

  function deleteEntity(_systemId: string, entityId: string) {
    const idx = entities.value.findIndex(e => e.id === entityId)
    if (idx >= 0) entities.value.splice(idx, 1)
  }

  function addGDDRef(systemId: string, gddRef: string) {
    const system = systems.value.find(s => s.id === systemId)
    if (system) {
      system.gddRefs.push(gddRef)
    }
    gddRefs.value.push(gddRef)
  }

  function updateSystem(_systemId: string, _updates: Record<string, unknown>) {}

  function updateEntity(_systemId: string, _entityId: string, _updates: Record<string, unknown>) {}

  function moveEntity(_systemId: string, _entityId: string, _newSystemId: string) {}

  function save() {}

  function load() {}

  return { systems, entities, gddRefs, addSystem, deleteSystem, addEntity, deleteEntity, addGDDRef, updateSystem, updateEntity, moveEntity, save, load }
})
