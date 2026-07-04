<script setup lang="ts">
// v3.0 — ClarificationPanel (Vue 3)
// Direct translation — same inline styles, same logic.
import { ref, computed } from 'vue'

const props = defineProps<{
  question: string
  options: string[]
  allowFreeText?: boolean
  toolUseId?: string
}>()

const emit = defineEmits<{ (e: 'choose', choice: string, toolUseId?: string): void }>()

const customText = ref('')
const submitted = ref(false)

const visible = computed(() => !submitted.value)

function handleChoice(choice: string) {
  submitted.value = true
  emit('choose', choice, props.toolUseId)
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && customText.value.trim()) handleChoice(customText.value.trim())
}
</script>

<template>
  <div
    v-if="visible"
    style="display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 20px 24px; border-radius: 12px; background: var(--color-surface-container-low); border: 1px solid var(--color-border); max-width: 480px; margin: 16px auto;"
  >
    <div style="font-size: 15px; font-weight: 600; color: var(--color-text-primary);">
      {{ question }}
    </div>
    <div style="display: flex; flex-wrap: wrap; gap: 8px; justify-content: center;">
      <button
        v-for="opt in options" :key="opt"
        @click="handleChoice(opt)"
        style="padding: 8px 18px; border-radius: 8px; border: 1px solid var(--color-border); background: var(--color-surface); color: var(--color-text-primary); font-size: 14px; cursor: pointer; font-weight: 500;"
        @mouseenter="($event.target as HTMLElement).style.background = 'var(--color-surface-hover)'"
        @mouseleave="($event.target as HTMLElement).style.background = 'var(--color-surface)'"
      >{{ opt }}</button>
    </div>
    <div v-if="allowFreeText" style="display: flex; gap: 8px; width: 100%; margin-top: 4px;">
      <input
        type="text"
        v-model="customText"
        placeholder="输入你的回答..."
        @keydown="onKey"
        style="flex: 1; padding: 8px 12px; border-radius: 8px; border: 1px solid var(--color-border); background: var(--color-surface); color: var(--color-text-primary); font-size: 14px; outline: none;"
      />
      <button
        @click="customText.trim() && handleChoice(customText.trim())"
        :disabled="!customText.trim()"
        :style="{
          padding: '8px 16px', borderRadius: '8px', border: 'none',
          background: customText.trim() ? 'var(--color-brand)' : 'var(--color-border)',
          color: '#fff', fontSize: '14px',
          cursor: customText.trim() ? 'pointer' : 'default', fontWeight: 600,
        }"
      >发送</button>
    </div>
  </div>
</template>
