<script setup lang="ts">
/**
 * ThinkingDepthSection — lives at the bottom of the ModelSelector
 * popover. Replaces the standalone composer IntensitySlider: thinking
 * depth is a property of the model call, so it belongs inside model
 * selection. Maps the 5 reasoning-effort levels to 6 named stages.
 *
 * Stage → effort mapping (2 stages share each effort except the ends):
 *   极速→low · 快速→low · 标准→auto · 深入→high · 深度→high · 极致→max
 */
import { computed } from 'vue'
import { useTranslation } from '../../i18n'
import { useSessionRuntimeStore } from '../../stores/sessionRuntimeStore'
import { useSettingsStore } from '../../stores/settingsStore'

const props = defineProps<{
  selectionKey: string
  selectedModel?: string
}>()

const t = useTranslation()
const runtimeStore = useSessionRuntimeStore()
const settingsStore = useSettingsStore()

const STAGES = [
  { key: '极速', label: '极速', effort: 'low', hint: '直出答案，最快响应' },
  { key: '快速', label: '快速', effort: 'low', hint: '少量思考，低延迟' },
  { key: '标准', label: '标准', effort: 'auto', hint: '日常工作档' },
  { key: '深入', label: '深入', effort: 'high', hint: '复杂问题，多步推理' },
  { key: '深度', label: '深度', effort: 'high', hint: '长链路推理，充分验证' },
  { key: '极致', label: '极致', effort: 'max', hint: '全力推理，不计耗时' },
] as const

const EFFORT_LABELS: Record<string, string> = {
  auto: '自动', low: '低', medium: '中', high: '高', max: '极高',
}

const currentEffort = computed(
  () => runtimeStore.selections[props.selectionKey]?.effortLevel ?? 'auto',
)

const currentIndex = computed(() => {
  const eff = currentEffort.value
  const exact = STAGES.findIndex((s) => s.effort === eff)
  return exact === -1 ? 2 : exact
})

const activeStage = computed(() => STAGES[currentIndex.value])

function pick(stage: typeof STAGES[number]) {
  const cur = runtimeStore.selections[props.selectionKey]
  runtimeStore.setSelection(props.selectionKey, {
    providerId: cur?.providerId ?? settingsStore.activeProviderName ?? 'official',
    modelId: cur?.modelId ?? props.selectedModel ?? '',
    effortLevel: stage.effort,
    agentMode: cur?.agentMode,
    workDir: cur?.workDir ?? null,
  })
}
</script>

<template>
  <div class="tds" data-testid="thinking-depth-section">
    <div class="tds__head">
      <span class="tds__title">{{ t('intensity.title', '思考深度') }}</span>
      <span class="tds__combo">{{ activeStage.label }} · {{ EFFORT_LABELS[activeStage.effort] }}推理</span>
    </div>
    <div class="tds__grid">
      <button
        v-for="(s, i) in STAGES" :key="s.key"
        type="button"
        class="tds__chip"
        :class="{ 'tds__chip--active': i === currentIndex }"
        :title="s.hint"
        @click="pick(s)"
      >
        {{ s.label }}
      </button>
    </div>
    <div class="tds__hint">{{ activeStage.hint }}</div>
  </div>
</template>

<style scoped>
.tds {
  border-top: 1px solid var(--color-border);
  margin-top: 4px;
  padding: 10px 8px 6px;
  user-select: none;
}
.tds__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.tds__title {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
}
.tds__combo {
  font-size: 10.5px;
  color: var(--color-text-tertiary);
  font-family: var(--font-mono, ui-monospace, monospace);
}
.tds__grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 4px;
}
.tds__chip {
  padding: 5px 0;
  font-size: 11px;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 120ms;
}
.tds__chip:hover {
  border-color: var(--color-text-tertiary);
  color: var(--color-text-primary);
}
.tds__chip--active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--color-on-primary, #fff);
  font-weight: 600;
}
.tds__hint {
  margin-top: 8px;
  font-size: 10.5px;
  color: var(--color-text-tertiary);
}
</style>
