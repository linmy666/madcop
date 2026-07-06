<script setup lang="ts">
/**
 * v3.1 — ModelSelector (Vue 3) — wired to /api/settings/providers
 *
 * Real implementation: fetches configured models from settings,
 * shows them in a dropdown, emits selection back to parent.
 */

import { ref, onMounted } from 'vue'
import { getApiUrl } from '../../api/client'

interface Provider {
  provider_id: string
  label: string
  model: string
  has_key: boolean
  is_active?: boolean
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
const loading = ref(false)
const currentLabel = ref('选择模型')

async function loadProviders() {
  loading.value = true
  try {
    const res = await fetch(getApiUrl('/api/settings'))
    if (res.ok) {
      const data = await res.json()
      const allProviders: Provider[] = data.providers || []
      providers.value = allProviders.filter((p) => p.model && p.has_key)
      // Find current
      const activeId = data.active_provider
      const active = allProviders.find((p) => p.provider_id === activeId)
      if (active?.model) {
        currentLabel.value = active.model
      } else if (props.selectedModel) {
        const found = providers.value.find((p) => p.model === props.selectedModel)
        if (found) currentLabel.value = found.model
      }
    }
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

function pick(provider: Provider) {
  currentLabel.value = provider.model
  emit('update:selectedModel', provider.model)
  open.value = false
}

function toggle() {
  if (props.disabled) return
  if (!open.value) loadProviders()
  open.value = !open.value
}

onMounted(loadProviders)
</script>

<template>
  <div style="position: relative;">
    <button
      type="button"
      @click="toggle"
      :disabled="disabled"
      :class="['model-selector', disabled ? 'model-selector--disabled' : '']"
    >
      <!-- Custom chip icon -->
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" class="flex-shrink-0">
        <rect x="2" y="2" width="5" height="5" rx="1" fill="currentColor" opacity="0.7"/>
        <rect x="9" y="2" width="5" height="5" rx="1" fill="currentColor" opacity="0.35"/>
        <rect x="2" y="9" width="5" height="5" rx="1" fill="currentColor" opacity="0.35"/>
        <rect x="9" y="9" width="5" height="5" rx="1" fill="currentColor" opacity="0.7"/>
      </svg>
      <span class="model-selector__label">{{ currentLabel }}</span>
      <svg width="9" height="9" viewBox="0 0 12 12" fill="none" class="model-selector__chevron">
        <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </button>

    <!-- Dropdown -->
    <div v-if="open" class="model-selector__dropdown">
      <div v-if="loading" class="model-selector__empty">加载中…</div>
      <div v-else-if="providers.length === 0" class="model-selector__empty">
        还没有配置模型
        <div style="font-size: 10px; margin-top: 4px; opacity: 0.7;">在「设置 → 模型供应商」中添加</div>
      </div>
      <button
        v-for="p in providers"
        :key="p.provider_id"
        @click="pick(p)"
        :class="['model-selector__item', currentLabel === p.model ? 'model-selector__item--active' : '']"
      >
        <div class="model-selector__item-name">{{ p.label }}</div>
        <div class="model-selector__item-model">{{ p.model }}</div>
      </button>
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
  transition: background 0.1s, color 0.1s;
}
.model-selector:hover { background: var(--color-surface-container); color: var(--color-text-primary); }
.model-selector--disabled { opacity: 0.5; cursor: not-allowed; }
.model-selector__label {
  white-space: nowrap;
  font-family: ui-monospace, 'SF Mono', monospace;
  font-size: 11px;
}
.model-selector__chevron { opacity: 0.5; }

.model-selector__dropdown {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  min-width: 240px;
  max-height: 320px;
  overflow-y: auto;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 6px;
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
.model-selector__item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 8px 10px;
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  color: var(--color-text-primary);
}
.model-selector__item:hover { background: var(--color-surface-container); }
.model-selector__item--active { background: color-mix(in srgb, var(--color-brand) 8%, transparent); }
.model-selector__item-name {
  font-size: 12px;
  font-weight: 500;
  margin-bottom: 2px;
}
.model-selector__item-model {
  font-size: 10px;
  color: var(--color-text-tertiary);
  font-family: ui-monospace, 'SF Mono', monospace;
}
</style>
