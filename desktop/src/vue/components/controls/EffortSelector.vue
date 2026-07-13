<script setup lang="ts">
/**
 * EffortSelector — per-session reasoning-intensity picker.
 *
 * Writes the chosen level into the session runtime selection
 * (useSessionRuntimeStore), which the chat store forwards to the backend
 * as `effort`. The backend only applies it to models that actually support
 * reasoning intensity (OpenAI o-series / GPT-5); other providers silently
 * ignore it.
 */
import { computed } from 'vue'
import { useSessionRuntimeStore } from '../../stores/sessionRuntimeStore'

const props = defineProps<{
  selectionKey: string
  compact?: boolean
  disabled?: boolean
}>()

const runtimeStore = useSessionRuntimeStore()

const LEVELS: { value: string; label: string }[] = [
  { value: 'auto', label: '自动推理' },
  { value: 'low', label: '低强度' },
  { value: 'medium', label: '中强度' },
  { value: 'high', label: '高强度' },
  { value: 'max', label: '最高强度' },
]

const current = computed<string>(() => {
  return runtimeStore.selections[props.selectionKey]?.effortLevel ?? 'auto'
})

function onChange(e: Event) {
  if (props.disabled) return
  const val = (e.target as HTMLSelectElement).value
  const cur = runtimeStore.selections[props.selectionKey]
  runtimeStore.setSelection(props.selectionKey, {
    providerId: cur?.providerId ?? 'official',
    modelId: cur?.modelId ?? '',
    effortLevel: val,
    workDir: cur?.workDir ?? null,
  })
}
</script>

<template>
  <div class="effort-selector" :class="{ 'effort-selector--compact': compact, 'effort-selector--disabled': disabled }">
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" class="effort-selector__icon">
      <path d="M8 1.5l1.7 3.6 3.8.5-2.8 2.7.7 3.8L8 10.8 4.6 12.6l.7-3.8L2.5 5.6l3.8-.5L8 1.5z"
        stroke="currentColor" stroke-width="1.2" stroke-linejoin="round" fill="none" />
    </svg>
    <select
      class="effort-selector__select"
      :value="current"
      :disabled="disabled"
      @change="onChange"
      data-testid="effort-selector"
      aria-label="推理强度"
    >
      <option v-for="lv in LEVELS" :key="lv.value" :value="lv.value">{{ lv.label }}</option>
    </select>
  </div>
</template>

<style scoped>
.effort-selector {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 6px 3px 8px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-secondary);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.1s, color 0.1s, border-color 0.1s;
}
.effort-selector:hover {
  background: var(--color-surface-container);
  color: var(--color-text-primary);
  border-color: var(--color-border-focus, var(--color-text-tertiary));
}
.effort-selector--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.effort-selector__icon {
  opacity: 0.7;
  flex-shrink: 0;
}
.effort-selector__select {
  appearance: none;
  -webkit-appearance: none;
  background: transparent;
  border: none;
  outline: none;
  color: inherit;
  font-size: 12px;
  font-family: inherit;
  cursor: inherit;
  padding-right: 2px;
}
.effort-selector__select:focus {
  outline: none;
}
.effort-selector__select option {
  color: var(--color-text-primary);
  background: var(--color-surface);
}
</style>
