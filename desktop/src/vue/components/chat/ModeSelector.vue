<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { getApiUrl } from '../../api/client'

/**
 * ModeSelector — Vue 3 port of components/chat/ModeSelector.tsx
 *
 * v3.2: Click outside to close, dynamically disable multi-agent modes
 * when the user has fewer than 2 configured models.
 */

export interface AgentMode {
  id: string
  name: string
  description: string
  category: string
  icon: string
  node_count: number
  requires_models?: number  // min models needed (default 1)
}

export interface ModeSelectorProps {
  currentMode: string
}

const props = defineProps<ModeSelectorProps>()
const emit = defineEmits<{ modeChange: [modeId: string] }>()

const modes = ref<AgentMode[]>([])
const open = ref(false)
const rootRef = ref<HTMLDivElement | null>(null)
const availableModelCount = ref(1)  // detected from /api/models

async function loadModes() {
  try {
    const r = await fetch(getApiUrl('/api/workflows/modes'))
    const d = await r.json()
    if (Array.isArray(d.modes)) modes.value = d.modes
  } catch {
    modes.value = [{ id: 'react', name: 'ReAct 推理', description: '默认模式', category: 'basic', icon: '🧠', node_count: 2 }]
  }

  // Detect how many distinct models are available
  try {
    const r = await fetch(getApiUrl('/api/models'))
    const d = await r.json()
    const models = d.models || []
    const providers = new Set<string>()
    for (const m of models) {
      if (m.providerId) providers.add(m.providerId)
    }
    availableModelCount.value = Math.max(1, providers.size)
  } catch {
    availableModelCount.value = 1
  }
}

function clickOutside(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

onMounted(() => {
  loadModes()
  document.addEventListener('mousedown', clickOutside)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', clickOutside)
})

const current = computed(() => modes.value.find((m) => m.id === props.currentMode))
const categories = ['basic', 'multi_agent', 'advanced']
const categoryLabels: Record<string, string> = { basic: '基础', multi_agent: '多 Agent', advanced: '高级' }

function modeIcon(m: AgentMode): string {
  return ({ single_agent: '1', sequential: '→', parallel: '∥', loop: '↻', review_critique: '✓', iterative_refine: '↑', coordinator: '◎', hierarchical: '⊞', swarm: '∞', react: '◉', human_in_loop: '◎' }[m.id] ?? '⚙')
}

// Multi-agent modes need ≥2 distinct providers/models
const multiAgentRequires: Record<string, number> = {
  sequential: 2,
  parallel: 2,
  review_critique: 2,
  coordinator: 2,
  hierarchical: 3,
  swarm: 3,
}

function isModeDisabled(m: AgentMode): boolean {
  if (m.category === 'multi_agent') {
    const required = m.requires_models ?? multiAgentRequires[m.id] ?? 2
    return availableModelCount.value < required
  }
  return false
}

function disabledReason(m: AgentMode): string {
  if (!isModeDisabled(m)) return ''
  const required = m.requires_models ?? multiAgentRequires[m.id] ?? 2
  return `需要 ${required} 个不同供应商的模型（当前有 ${availableModelCount.value} 个）`
}
</script>

<template>
  <div ref="rootRef" class="mode-selector">
    <button
      @click="open = !open"
      class="mode-selector__trigger"
      :title="current?.description || '选择模式'"
    >
      <span class="mode-selector__chev">▾</span>
      <span class="mode-selector__name">{{ current?.name || 'ReAct' }}</span>
      <span class="mode-selector__chev">▾</span>
    </button>

    <div v-if="open" class="mode-selector__dropdown">
      <div v-for="cat in categories" :key="cat">
        <div class="mode-selector__cat-header">
          {{ categoryLabels[cat] }}
          <span v-if="cat === 'multi_agent'" class="mode-selector__cat-hint">
            · 需要 ≥2 个模型
          </span>
        </div>
        <button
          v-for="m in modes.filter(mode => mode.category === cat)"
          :key="m.id"
          @click="() => { if (!isModeDisabled(m)) { emit('modeChange', m.id); open = false } }"
          :disabled="isModeDisabled(m)"
          :class="['mode-selector__item', m.id === props.currentMode ? 'mode-selector__item--active' : '', isModeDisabled(m) ? 'mode-selector__item--disabled' : '']"
          :title="isModeDisabled(m) ? disabledReason(m) : m.description"
        >
          <span class="mode-selector__icon">{{ modeIcon(m) }}</span>
          <div class="mode-selector__text">
            <div class="mode-selector__name-line">
              <span class="mode-selector__item-name">{{ m.name }}</span>
              <span v-if="isModeDisabled(m)" class="mode-selector__lock">🔒</span>
            </div>
            <div class="mode-selector__item-desc">{{ m.description }}</div>
          </div>
          <span v-if="m.id === props.currentMode" class="mode-selector__check">✓</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mode-selector {
  position: relative;
  display: inline-block;
}
.mode-selector__trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.1s, color 0.1s;
}
.mode-selector__trigger:hover {
  background: var(--color-surface-container);
  color: var(--color-text-primary);
}
.mode-selector__chev { font-size: 9px; opacity: 0.6; }
.mode-selector__name { font-weight: 500; }

.mode-selector__dropdown {
  position: absolute;
  bottom: calc(100% + 4px);
  left: 0;
  margin-bottom: 4px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  max-height: 400px;
  overflow-y: auto;
  min-width: 280px;
  z-index: 100;
  padding-bottom: 4px;
}
.mode-selector__cat-header {
  padding: 8px 12px 4px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--color-text-tertiary);
  border-bottom: 1px solid var(--color-border);
  position: sticky;
  top: 0;
  background: var(--color-surface);
  z-index: 1;
}
.mode-selector__cat-hint {
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
  font-size: 9px;
  color: var(--color-text-tertiary);
  opacity: 0.7;
}
.mode-selector__item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 12px;
  width: 100%;
  background: transparent;
  border: none;
  color: var(--color-text-primary);
  cursor: pointer;
  text-align: left;
  border-bottom: 1px solid var(--color-border);
  transition: background 0.1s;
}
.mode-selector__item:hover:not(.mode-selector__item--disabled) {
  background: var(--color-surface-container);
}
.mode-selector__item--active {
  background: var(--color-surface-container-lowest);
}
.mode-selector__item--disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.mode-selector__icon {
  font-size: 16px;
  flex-shrink: 0;
  font-family: ui-monospace, 'SF Mono', monospace;
  width: 20px;
  text-align: center;
}
.mode-selector__text { flex: 1; min-width: 0; }
.mode-selector__name-line {
  display: flex;
  align-items: center;
  gap: 6px;
}
.mode-selector__item-name {
  font-size: 13px;
  font-weight: 600;
}
.mode-selector__lock {
  font-size: 10px;
  opacity: 0.7;
}
.mode-selector__item-desc {
  font-size: 11px;
  color: var(--color-text-tertiary);
  white-space: normal;
  margin-top: 2px;
  line-height: 1.4;
}
.mode-selector__check {
  font-size: 14px;
  color: var(--color-brand);
  flex-shrink: 0;
}
</style>
