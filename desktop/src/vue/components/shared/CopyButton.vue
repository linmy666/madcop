<script setup lang="ts">
// v3.0 — CopyButton (Vue 3)
// Direct translation of CopyButton.tsx — same logic, Vue reactivity.
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
  } catch {
    copied.value = false
  }
}
</script>

<template>
  <button
    type="button"
    :class="$props.class"
    :aria-label="copied ? copiedLabel : label"
    :title="copied ? copiedLabel : label"
    @click="handleCopy"
  >
    <slot :copied="copied" :label="copied ? copiedLabel : label">
      {{ copied ? copiedLabel : label }}
    </slot>
  </button>
</template>
