import { api } from './client'
import type { ModelInfo } from '../../types/settings'

type ModelsResponse = { models: ModelInfo[]; provider: { id: string; name: string } | null }
type CurrentModelResponse = { model: ModelInfo }

// NOTE: reasoning intensity (effort) is now configured per-session in the
// composer (see EffortSelector.vue / sessionRuntimeStore) and sent on the
// POST /api/chat body's `effort` field. The old global getEffort/setEffort
// endpoints were never wired to anything and have been removed.
export const modelsApi = {
  list() {
    return api.get<ModelsResponse>('/api/models')
  },

  getCurrent() {
    return api.get<CurrentModelResponse>('/api/models/current')
  },

  setCurrent(modelId: string) {
    return api.put<{ ok: true; model: string }>('/api/models/current', { modelId })
  },
}
