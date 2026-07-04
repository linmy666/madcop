<script setup lang="ts">
// v3.0 — Message action bar (Vue 3)
// Hover-revealed bar with copy + branch buttons and timestamp.
// Vue's @mouseenter / @mouseleave on the parent group triggers
// opacity transition (no need for CSS :hover pseudo-class on .group).
import { ref, computed } from 'vue'
import { CopyButton } from '../shared/CopyButton.vue'

const props = withDefaults(defineProps<{
  copyText?: string
  copyLabel?: string
  align?: 'start' | 'end'
  timestamp?: number
  branchLabel?: string
}>(), {
  copyLabel: '复制',
  align: 'start',
  branchLabel: '从这分支',
})

defineEmits<{ (e: 'branch'): void }>()

const hovered = ref(false)
const focused = ref(false)
const visible = computed(() => hovered.value || focused.value)
const hasCopy = computed(() => Boolean(props.copyText?.trim()))
const ts = computed(() => {
  if (typeof props.timestamp !== 'number') return ''
  return new Date(props.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
})
const tsFull = computed(() => {
  if (typeof props.timestamp !== 'number') return ''
  return new Date(props.timestamp).toLocaleString('zh-CN')
})
</script>

<template>
  <div
    v-if="hasCopy || $slots.default"
    :class="['madcop-action', `madcop-action--${align}`, { 'madcop-action--show': visible }]"
    @mouseenter="hovered = true"
    @mouseleave="hovered = false"
  >
    <div class="madcop-action__inner">
      <CopyButton
        v-if="hasCopy"
        :text="copyText!"
        :label="copyLabel"
        class="madcop-action__btn"
      />
      <button
        v-if="$slots.default"
        type="button"
        :title="branchLabel"
        :aria-label="branchLabel"
        @click="$emit('branch')"
        class="madcop-action__btn madcop-action__btn--icon"
      >⎇</button>
      <span v-if="ts" class="madcop-action__ts" :title="tsFull">{{ ts }}</span>
    </div>
  </div>
</template>

<style scoped>
.madcop-action {
  display: flex; width: 100%; height: 28px; margin-top: 4px;
  opacity: 0; pointer-events: none;
  transition: opacity 140ms;
}
.madcop-action--show { opacity: 1; pointer-events: auto; }
.madcop-action--end { justify-content: flex-end; }
.madcop-action--start { justify-content: flex-start; }
.madcop-action__inner { display: flex; align-items: center; gap: 6px; min-height: 28px; }
.madcop-action__btn {
  width: 28px; height: 28px;
  display: inline-flex; align-items: center; justify-content: center;
  border: 1.5px solid transparent; background: transparent;
  color: var(--madcop-ink-muted);
  font-size: 13px; cursor: pointer; border-radius: 50%;
  font-family: 'Geist Mono', monospace;
}
.madcop-action__btn:hover {
  border-color: var(--madcop-accent);
  background: var(--madcop-panel-sunken);
  color: var(--madcop-ink);
}
.madcop-action__ts {
  font-size: 11px; color: var(--madcop-ink-muted);
  margin-left: 4px; font-family: 'Geist Mono', monospace;
  font-variant-numeric: tabular-nums;
}
</style>
