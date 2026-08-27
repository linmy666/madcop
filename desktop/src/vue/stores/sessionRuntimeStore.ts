export const DRAFT_RUNTIME_SELECTION_KEY = '__draft__'

import { defineStore } from 'pinia'

/**
 * Pinia mirror of stores/sessionRuntimeStore.ts
 * Manages per-session runtime selections (provider + model + effort level).
 */
export type RuntimeSelection = {
  providerId: string
  modelId: string
  effortLevel: string
  agentMode?: string
  workDir?: string | null
}

const STORAGE_KEY = 'madcop-agent-session-runtime'

function loadSelections(): Record<string, RuntimeSelection> {
  if (typeof localStorage === 'undefined') return {}
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, RuntimeSelection>
    if (!parsed || typeof parsed !== 'object') return {}
    // Sanitize legacy poison: old IntensitySlider builds persisted the
    // display placeholder '当前模型' as modelId. Feeding that back to
    // the LLM produced 'unknown model 当前模型 (2013)'. Drop the value
    // so the empty-model omission path takes over.
    for (const key of Object.keys(parsed)) {
      const sel: any = parsed[key]
      if (sel && (sel.modelId === '当前模型' || sel.modelId === '__placeholder__')) {
        sel.modelId = ''
      }
    }
    return parsed
  } catch { return {} }
}

function persistSelections(selections: Record<string, RuntimeSelection>) {
  if (typeof localStorage === 'undefined') return
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(selections)) } catch { /* noop */ }
}

export const useSessionRuntimeStore = defineStore('sessionRuntime', {
  state: () => ({ selections: loadSelections() as Record<string, RuntimeSelection> }),

  actions: {
    setSelection(key: string, selection: RuntimeSelection) {
      this.selections[key] = selection
      persistSelections(this.selections)
    },
    clearSelection(key: string) {
      delete this.selections[key]
      persistSelections(this.selections)
    },
    moveSelection(fromKey: string, toKey: string) {
      if (fromKey in this.selections) {
        this.selections[toKey] = this.selections[fromKey]
        delete this.selections[fromKey]
        persistSelections(this.selections)
      }
    },
  },
})
