<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { getApiUrl } from '../../api/client'

/**
 * ModeSelector — Vue 3 port of components/chat/ModeSelector.tsx
 * Dropdown for choosing Agent design pattern (12 Google Cloud modes).
 * Only depends on fetch (no stores). Self-contained.
 */

export interface AgentMode {
  id: string
  name: string
  description: string
  category: string
  icon: string
  node_count: number
}

export interface ModeSelectorProps {
  currentMode: string
}

const props = defineProps<ModeSelectorProps>()
const emit = defineEmits<{ modeChange: [modeId: string] }>()

const modes = ref<AgentMode[]>([])
const open = ref(false)
const rootRef = ref<HTMLDivElement | null>(null)

onMounted(() => {
  fetch(getApiUrl('/api/workflows/modes'))
    .then((r) => r.json())
    .then((d) => { if (Array.isArray(d.modes)) modes.value = d.modes })
    .catch(() => {
      modes.value = [{ id: 'react', name: 'ReAct 推理', description: '默认模式', category: 'basic', icon: '🧠', node_count: 2 }]
    })

  const handler = (e: MouseEvent) => {
    if (rootRef.value && !rootRef.value.contains(e.target as Node)) open.value = false
  }
  document.addEventListener('mousedown', handler)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', () => {})
})

const current = computed(() => modes.value.find((m) => m.id === props.currentMode))
const categories = ['basic', 'multi_agent', 'advanced']
const categoryLabels: Record<string, string> = { basic: '基础', multi_agent: '多 Agent', advanced: '高级' }

function modeIcon(m: AgentMode): string {
  return ({ single_agent: '1', sequential: '→', parallel: '∥', loop: '↻', review_critique: '✓', iterative_refine: '↑', coordinator: '◎', hierarchical: '⊞', swarm: '∞', react: '◉', human_in_loop: '◎' }[m.id] ?? '⚙')
}
</script>

<template>
  <div ref="rootRef" style="position: relative;">
    <button
      @click="open = !open"
      style="display: flex; align-items: center; gap: 4px; padding: 4px 8px; background: transparent; border: 1px solid var(--color-border); border-radius: 4px; color: var(--color-text-secondary); font-size: 12px; cursor: pointer; white-space: nowrap;"
      :title="current?.description || '选择模式'"
    >
      <span style="font-size: 9px; opacity: 0.6;">▾</span>
      <span>{{ current?.name || 'ReAct' }}</span>
      <span style="font-size: 9px; opacity: 0.6;">▾</span>
    </button>

    <div v-if="open" style="position: absolute; bottom: 100%; left: 0; margin-bottom: 4px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.15); max-height: 400px; overflow-y: auto; min-width: 280px; z-index: 100;">
      <div v-for="cat in categories" :key="cat">
        <div style="padding: 6px 12px; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: var(--color-text-tertiary); border-bottom: 1px solid var(--color-border);">
          {{ categoryLabels[cat] }}
        </div>
        <button
          v-for="m in modes.filter(mode => mode.category === cat)"
          :key="m.id"
          @click="() => { emit('modeChange', m.id); open = false; }"
          :style="{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '8px 12px', width: '100%', background: m.id === props.currentMode ? 'var(--color-surface-hover)' : 'transparent', border: 'none', borderBottom: '1px solid var(--color-border)', color: 'var(--color-text-primary)', cursor: 'pointer', textAlign: 'left' }"
          @mouseenter="($event.target as HTMLElement).style.background = 'var(--color-surface-hover)'"
          @mouseleave="($event.target as HTMLElement).style.background = m.id === props.currentMode ? 'var(--color-surface-hover)' : 'transparent'"
        >
          <span style="font-size: 16px; flex-shrink: 0;">{{ modeIcon(m) }}</span>
          <div style="flex: 1; min-width: 0;">
            <div style="font-size: 13px; font-weight: 600;">{{ m.name }}</div>
            <div style="font-size: 11px; color: var(--color-text-tertiary); white-space: normal;">{{ m.description }}</div>
          </div>
          <span v-if="m.id === props.currentMode" style="font-size: 14px; color: var(--color-brand);">✓</span>
        </button>
      </div>
    </div>
  </div>
</template>
