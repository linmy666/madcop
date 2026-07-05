import type { ModelInfo } from '../../types/settings'

// PATCHED: no hardcoded Claude fallback.
// Users must add their own provider in Settings → 服务商.
export const OFFICIAL_DEFAULT_MODEL_ID = ''

export const OFFICIAL_MODELS: ModelInfo[] = []
