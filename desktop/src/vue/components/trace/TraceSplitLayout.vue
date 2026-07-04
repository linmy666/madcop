<script setup lang="ts">
// v3.0 — TraceSplitLayout (Vue 3)
// Resizable split layout with drag handle. Same Tailwind classes.
import { ref, onUnmounted } from 'vue'

const STORAGE_KEY = 'trace.treeWidth'
const DEFAULT_WIDTH = 380
const MIN_WIDTH = 280
const MAX_WIDTH = 560

function clampWidth(w: number): number {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(w)))
}

function readStoredWidth(): number {
  try {
    const s = localStorage.getItem(STORAGE_KEY)
    const p = s === null ? NaN : parseInt(s, 10)
    return isFinite(p) ? clampWidth(p) : DEFAULT_WIDTH
  } catch { return DEFAULT_WIDTH }
}

const width = ref(readStoredWidth())
let drag: { startX: number; startWidth: number } | null = null

function onMove(e: MouseEvent) {
  if (!drag) return
  width.value = clampWidth(drag.startWidth + (e.clientX - drag.startX))
}
function onUp() {
  if (!drag) return
  drag = null
  try { localStorage.setItem(STORAGE_KEY, String(width.value)) } catch {}
  document.body.style.removeProperty('cursor')
  document.body.style.removeProperty('user-select')
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('mouseup', onUp)
}

function onDown(e: MouseEvent) {
  drag = { startX: e.clientX, startWidth: width.value }
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

onUnmounted(() => {
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('mouseup', onUp)
})
</script>

<template>
  <div class="flex h-full min-h-0 flex-1 overflow-hidden">
    <div
      class="flex flex-col overflow-hidden border-r border-[var(--color-border)] bg-[var(--color-surface-container-low)]"
      :style="{ width: width + 'px', flexShrink: 0 }"
    >
      <slot name="tree" />
    </div>
    <div
      class="w-[3px] cursor-col-resize bg-[var(--color-border)] transition-colors hover:bg-[var(--color-brand)]"
      @mousedown="onDown"
    />
    <div class="flex flex-1 flex-col overflow-hidden bg-[var(--color-surface)]">
      <slot name="detail" />
    </div>
  </div>
</template>
