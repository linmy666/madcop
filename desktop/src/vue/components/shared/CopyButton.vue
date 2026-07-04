<script setup lang="ts">
// v3.0 — Copy button (Vue 3)
import { ref, watch, onUnmounted } from 'vue'

const props = withDefaults(defineProps<{
  text: string
  label?: string
  copiedLabel?: string
  class?: string
}>(), {
  label: 'Copy',
  copiedLabel: 'Copied',
})

const emit = defineEmits<{ (e: 'copy', ok: boolean): void }>()

const copied = ref(false)
let timer: number | null = null

watch(copied, (v) => {
  if (!v) return
  if (timer) clearTimeout(timer)
  timer = window.setTimeout(() => { copied.value = false }, 1500)
})

onUnmounted(() => { if (timer) clearTimeout(timer) })

async function handleCopy() {
  try {
    await navigator.clipboard.writeText(props.text)
    copied.value = true
    emit('copy', true)
  } catch {
    emit('copy', false)
  }
}
</script>

<template>
  <button
    type="button"
    :class="['madcop-copy-btn', $props.class, copied ? 'madcop-copy-btn--ok' : '']"
    :aria-label="copied ? copiedLabel : label"
    :title="copied ? copiedLabel : label"
    @click="handleCopy"
  >
    <slot :copied="copied" :label="copied ? copiedLabel : label">
      {{ copied ? copiedLabel : label }}
    </slot>
  </button>
</template>

<style scoped>
.madcop-copy-btn {
  background: transparent; border: none; cursor: pointer;
  font-size: 12px; color: var(--madcop-ink-muted);
  font-family: 'Geist Mono', monospace; padding: 0;
}
.madcop-copy-btn:hover { color: var(--madcop-ink); }
.madcop-copy-btn--ok { color: var(--madcop-success); }
</style>
