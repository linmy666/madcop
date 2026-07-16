<script setup lang="ts">
/**
 * v3.2 — ModelSelector (Vue 3)
 *
 * Fetches configured providers, and for each provider with API key,
 * also fetches its /api/models endpoint to get the real available model list.
 *
 * - Click outside to close dropdown
 * - Shows context window (auto-fetched or manually overridden)
 * - Persists manual context override in localStorage per model
 */

import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { getApiUrl, getBaseUrl } from '../../api/client'

interface Provider {
  provider_id: string
  label: string
  model: string
  has_key: boolean
  base_url?: string
  api_key?: string
  context_length?: number | null
}

interface ModelInfo {
  id: string
  label: string
  provider_id: string
  provider_label: string
  context_window?: number
  pricing?: { prompt?: string; completion?: string }
}

const props = defineProps<{
  compact?: boolean
  disabled?: boolean
  selectedModel?: string
}>()

const emit = defineEmits<{
  'update:selectedModel': [model: string]
}>()

const open = ref(false)
const providers = ref<Provider[]>([])
const allModels = ref<ModelInfo[]>([])
const loading = ref(false)
const currentLabel = ref('选择模型')
const currentContextWindow = ref<number | null>(null)
const loadError = ref<string | null>(null)

// Manual context override (per model)
const CONTEXT_OVERRIDES_KEY = 'madcop_context_overrides'
function loadContextOverrides(): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(CONTEXT_OVERRIDES_KEY) || '{}')
  } catch {
    return {}
  }
}
function saveContextOverride(modelId: string, value: number) {
  const overrides = loadContextOverrides()
  overrides[modelId] = value
  localStorage.setItem(CONTEXT_OVERRIDES_KEY, JSON.stringify(overrides))
}

async function loadAll() {
  loading.value = true
  loadError.value = null
  try {
    // 1. Load providers
    const res = await fetch(getApiUrl('/api/settings'))
    if (!res.ok) {
      loadError.value = `后端返回 ${res.status}，请确认后端已启动 (${getBaseUrl()})`
      return
    }
    const data = await res.json()
    const allProviders: Provider[] = data.providers || []
    providers.value = allProviders.filter((p) => p.model && p.has_key)

    // 2. Fetch all models (auto-fetched from provider's /v1/models)
    let allData: any = { models: [] }
    try {
      const modelsRes = await fetch(getApiUrl('/api/models'))
      if (!modelsRes.ok) {
        loadError.value = `模型列表接口返回 ${modelsRes.status}`
        return
      }
      if (modelsRes.ok) allData = await modelsRes.json()
    } catch (e: any) {
      loadError.value = `无法连接后端: ${e?.message || '网络错误'}`
      return
    }

    const overrides = loadContextOverrides()
    const models: ModelInfo[] = []
    const seen = new Set<string>()

    for (const m of allData.models || []) {
      const id = m.id
      if (!id || seen.has(id)) continue
      seen.add(id)
      const context =
        overrides[id] ??
        m.context_window ??
        m.context ??
        null
      models.push({
        id,
        label: m.name || id,
        provider_id: m.providerId || '',
        provider_label: m.providerName || m.providerId || '',
        context_window: typeof context === 'number' && context > 0 ? context : null,
      })
    }
    allModels.value = models

    // 4. Set current label + context
    const activeId = data.active_provider
    const active = allProviders.find((p) => p.provider_id === activeId)
    if (active?.model) {
      const found = allModels.value.find((m) => m.id === active.model)
      if (found) {
        currentLabel.value = found.label
        currentContextWindow.value = found.context_window ?? null
      } else {
        currentLabel.value = active.model
        currentContextWindow.value = overrides[active.model] ?? active.context_length ?? null
      }
    } else if (props.selectedModel) {
      const found = allModels.value.find((m) => m.id === props.selectedModel)
      if (found) {
        currentLabel.value = found.label
        currentContextWindow.value = found.context_window ?? null
      }
    }
  } catch (e: any) {
    loadError.value = `加载失败: ${e?.message || '未知错误'}`
  } finally {
    loading.value = false
  }
}

function pick(model: ModelInfo) {
  currentLabel.value = model.label
  currentContextWindow.value = model.context_window ?? null
  emit('update:selectedModel', model.id)
  open.value = false
  editingContext.value = false
}

function toggle() {
  if (props.disabled) return
  if (!open.value) loadAll()
  open.value = !open.value
  editingContext.value = false
}

// Click outside to close
const rootRef = ref<HTMLElement | null>(null)
function handleClickOutside(e: MouseEvent) {
  if (!open.value) return
  const target = e.target as Node
  if (rootRef.value && !rootRef.value.contains(target)) {
    open.value = false
    editingContext.value = false
  }
}
onMounted(() => {
  document.addEventListener('mousedown', handleClickOutside)
  loadAll()
})
onUnmounted(() => {
  document.removeEventListener('mousedown', handleClickOutside)
})

// Manual context override
const editingContext = ref(false)
const contextDraft = ref('')

function startEditContext() {
  contextDraft.value = String(currentContextWindow.value ?? 128000)
  editingContext.value = true
  nextTick(() => {
    const input = document.getElementById('model-context-input')
    if (input) (input as HTMLInputElement).focus()
  })
}

function applyContextOverride() {
  const num = parseInt(contextDraft.value, 10)
  if (isNaN(num) || num < 1000) {
    editingContext.value = false
    return
  }
  // Find the current model id
  const current = allModels.value.find((m) => m.label === currentLabel.value)
  const modelId = current?.id || props.selectedModel || currentLabel.value
  saveContextOverride(modelId, num)
  currentContextWindow.value = num
  // Update the model in the list too
  if (current) current.context_window = num
  editingContext.value = false
}

function formatContext(n: number | null | undefined): string {
  if (n === null || n === undefined) return '?'
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(0)}K`
  return String(n)
}

watch(() => props.selectedModel, (val) => {
  if (val) {
    const found = allModels.value.find((m) => m.id === val)
    if (found) {
      currentLabel.value = found.label
      currentContextWindow.value = found.context_window ?? null
    }
  }
})
</script>

<template>
  <div ref="rootRef" style="position: relative;">
    <button
      type="button"
      @click="toggle"
      :disabled="disabled"
      :class="['model-selector', disabled ? 'model-selector--disabled' : '', open ? 'model-selector--active' : '']"
      data-testid="model-selector-trigger"
    >
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" class="flex-shrink-0">
        <rect x="2" y="2" width="5" height="5" rx="1" fill="currentColor" opacity="0.7"/>
        <rect x="9" y="2" width="5" height="5" rx="1" fill="currentColor" opacity="0.35"/>
        <rect x="2" y="9" width="5" height="5" rx="1" fill="currentColor" opacity="0.35"/>
        <rect x="9" y="9" width="5" height="5" rx="1" fill="currentColor" opacity="0.7"/>
      </svg>
      <span class="model-selector__label">{{ currentLabel }}</span>
      <span v-if="currentContextWindow" class="model-selector__context">
        {{ formatContext(currentContextWindow) }}
      </span>
      <svg width="9" height="9" viewBox="0 0 12 12" fill="none" class="model-selector__chevron">
        <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </button>

    <div v-if="open" class="model-selector__dropdown" data-testid="model-selector-dropdown">
      <div v-if="loading" class="model-selector__empty">加载模型列表…</div>
      <div v-else-if="loadError" class="model-selector__empty model-selector__error">
        <div style="font-size: 13px; margin-bottom: 6px;">⚠ {{ loadError }}</div>
        <button @click="loadAll()" class="model-selector__retry-btn">重试</button>
        <div style="font-size: 10px; margin-top: 8px; opacity: 0.7;">提示：确认后端运行在 {{ getBaseUrl() }}</div>
      </div>
      <div v-else-if="allModels.length === 0" class="model-selector__empty">
        还没有可用的模型
        <div style="font-size: 10px; margin-top: 4px; opacity: 0.7;">在「设置 → 模型供应商」中添加</div>
      </div>
      <template v-else>
        <div v-for="m in allModels" :key="`${m.provider_id}-${m.id}`" class="model-selector__group">
          <div class="model-selector__provider-header">{{ m.provider_label }}</div>
          <button
            @click="pick(m)"
            :class="['model-selector__item', currentLabel === m.label ? 'model-selector__item--active' : '']"
          >
            <div class="model-selector__item-row">
              <span class="model-selector__item-name">{{ m.label }}</span>
              <span v-if="m.context_window" class="model-selector__item-ctx">
                {{ formatContext(m.context_window) }}
              </span>
            </div>
            <div class="model-selector__item-id">{{ m.id }}</div>
          </button>
        </div>
      </template>

      <!-- Context override -->
      <div class="model-selector__context-row" v-if="!editingContext">
        <span class="model-selector__context-label">当前上下文窗口:</span>
        <span class="model-selector__context-value">{{ formatContext(currentContextWindow) }}</span>
        <button class="model-selector__context-btn" @click="startEditContext">调整</button>
      </div>
      <div class="model-selector__context-edit" v-else>
        <input
          id="model-context-input"
          v-model="contextDraft"
          type="number"
          min="1000"
          step="1000"
          class="model-selector__context-input"
          @keydown.enter="applyContextOverride"
          @keydown.esc="editingContext = false"
        />
        <button class="model-selector__context-apply" @click="applyContextOverride">保存</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.model-selector {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-secondary);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.1s, color 0.1s, border-color 0.1s;
}
.model-selector:hover {
  background: var(--color-surface-container);
  color: var(--color-text-primary);
  border-color: var(--color-border-focus, var(--color-text-tertiary));
}
.model-selector--active {
  border-color: var(--color-brand);
  color: var(--color-text-primary);
}
.model-selector--disabled { opacity: 0.5; cursor: not-allowed; }
.model-selector__label {
  white-space: nowrap;
  font-family: var(--font-mono);
  font-size: 11px;
}
.model-selector__context {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 0 4px;
  background: var(--color-surface-container);
  border-radius: 4px;
  color: var(--color-text-tertiary);
}
.model-selector__chevron { opacity: 0.5; }

.model-selector__dropdown {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  min-width: 280px;
  max-width: 360px;
  max-height: 380px;
  overflow-y: auto;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  z-index: 100;
  padding: 4px;
}
.model-selector__empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.model-selector__error {
  color: var(--color-error);
}
.model-selector__retry-btn {
  margin-top: 8px;
  padding: 6px 16px;
  background: var(--color-brand);
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
}
.model-selector__retry-btn:hover { opacity: 0.9; }
.model-selector__group {
  padding: 4px 0;
}
.model-selector__provider-header {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--color-text-tertiary);
  padding: 4px 10px 2px;
}
.model-selector__item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 6px 10px;
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  color: var(--color-text-primary);
}
.model-selector__item:hover { background: var(--color-surface-container); }
.model-selector__item--active {
  background: color-mix(in srgb, var(--color-brand) 8%, transparent);
}
.model-selector__item-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.model-selector__item-name {
  font-size: 12px;
  font-weight: 500;
}
.model-selector__item-ctx {
  font-size: 10px;
  padding: 1px 5px;
  background: var(--color-surface-container);
  border-radius: 4px;
  color: var(--color-text-tertiary);
  font-family: var(--font-mono);
}
.model-selector__item-id {
  font-size: 10px;
  color: var(--color-text-tertiary);
  font-family: var(--font-mono);
  margin-top: 2px;
}

.model-selector__context-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-top: 1px solid var(--color-border);
  margin-top: 4px;
  font-size: 11px;
}
.model-selector__context-label {
  color: var(--color-text-tertiary);
}
.model-selector__context-value {
  font-family: var(--font-mono);
  color: var(--color-text-primary);
  font-weight: 500;
}
.model-selector__context-btn {
  margin-left: auto;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 10px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.1s;
}
.model-selector__context-btn:hover {
  background: var(--color-surface-container);
  color: var(--color-text-primary);
}

.model-selector__context-edit {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-top: 1px solid var(--color-border);
  margin-top: 4px;
}
.model-selector__context-input {
  flex: 1;
  background: var(--color-surface-container);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 3px 6px;
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--color-text-primary);
  outline: none;
}
.model-selector__context-input:focus {
  border-color: var(--color-brand);
}
.model-selector__context-apply {
  background: var(--color-brand);
  border: none;
  border-radius: 4px;
  padding: 3px 10px;
  font-size: 11px;
  color: white;
  cursor: pointer;
}
.model-selector__context-apply:hover {
  opacity: 0.9;
}
</style>
