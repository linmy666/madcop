<script setup lang="ts">
/** Sprint 3 — Microphone button for voice input. */
import { useVoiceMode } from '../../composables/useVoiceMode'

const props = defineProps<{
  onTranscript?: (text: string) => void
}>()
const emit = defineEmits<{ (e: 'transcript', text: string): void }>()

const { isListening, supported, start, stop } = useVoiceMode()

function toggle() {
  if (isListening.value) {
    const text = stop()
    if (text) {
      emit('transcript', text)
      props.onTranscript?.(text)
    }
  } else {
    start()
  }
}
</script>

<template>
  <button
    v-if="supported"
    type="button"
    :title="isListening ? '点击停止录音' : '点击开始语音输入'"
    :class="[
      'flex h-9 w-9 items-center justify-center rounded-full transition-all',
      isListening
        ? 'bg-red-500 text-white animate-pulse'
        : 'bg-[var(--color-surface-container)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-container-high)]',
    ]"
    @click="toggle"
  >
    <span class="material-symbols-outlined text-[18px]">
      {{ isListening ? 'mic' : 'mic_none' }}
    </span>
  </button>
</template>
