<template>
  <div v-if="clarifications.length > 0" class="clarify-hints">
    <div class="clarify-hints__title">
      <span class="material-symbols-outlined text-[14px]" style="fontVariationSettings: 'wght' 400">help</span>
      <span>{{ titleText }}</span>
      <button
        type="button"
        class="clarify-hints__dismiss"
        @click="$emit('dismiss')"
        :aria-label="'关闭'"
      >×</button>
    </div>

    <div v-for="c in clarifications" :key="c.slot" class="clarify-hints__group">
      <span class="clarify-hints__question">{{ c.question }}</span>
      <div class="clarify-hints__options">
        <button
          v-for="opt in c.options"
          :key="opt"
          type="button"
          class="clarify-hints__chip"
          @click="$emit('pick', { slot: c.slot, value: opt })"
        >{{ opt }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Clarification } from '../../lib/clarify'

const props = defineProps<{
  clarifications: Clarification[]
}>()

defineEmits<{
  pick: [{ slot: string; value: string }]
  dismiss: []
}>()

const titleText = computed(() => {
  if (props.clarifications.length === 1) return '需要 1 项信息'
  return `需要 ${props.clarifications.length} 项信息`
})
</script>

<style scoped>
.clarify-hints {
  background: var(--color-surface-container-low, #f5f5f7);
  border: 1px solid var(--color-border, rgba(0,0,0,0.1));
  border-radius: 10px;
  padding: 8px 12px;
  margin-bottom: 6px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  animation: clarify-slide-down 200ms ease-out;
}
@keyframes clarify-slide-down {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}

.clarify-hints__title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--color-text-tertiary, rgba(0,0,0,0.55));
  font-weight: 500;
}
.clarify-hints__dismiss {
  margin-left: auto;
  background: transparent;
  border: none;
  color: var(--color-text-tertiary);
  font-size: 16px;
  line-height: 1;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.1s;
}
.clarify-hints__dismiss:hover {
  background: var(--color-surface-container, rgba(0,0,0,0.05));
  color: var(--color-text-primary);
}

.clarify-hints__group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.clarify-hints__question {
  font-size: 12px;
  color: var(--color-text-secondary);
  font-weight: 500;
  flex-shrink: 0;
}
.clarify-hints__options {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.clarify-hints__chip {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, rgba(0,0,0,0.1));
  border-radius: 14px;
  padding: 3px 10px;
  font-size: 12px;
  color: var(--color-text-primary);
  cursor: pointer;
  transition: all 0.1s;
}
.clarify-hints__chip:hover {
  background: var(--color-brand, #7c3aed);
  border-color: var(--color-brand, #7c3aed);
  color: white;
}
</style>
