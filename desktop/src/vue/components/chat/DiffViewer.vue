<script setup lang="ts">
import { computed } from 'vue'

/**
 * DiffViewer — Vue 3 port of components/chat/DiffViewer.tsx
 *
 * Shows code diff with file path, +N/-N badges, copy button.
 * Uses slot for diff rendering. No react-diff-viewer-continued dependency.
 * prop-driven: parent passes filePath, oldString, newString.
 */

export interface DiffViewerProps {
  filePath: string
  oldString: string
  newString: string
}

const props = defineProps<DiffViewerProps>()

const additions = computed(() => {
  const oldLines = props.oldString.split('\n')
  const newLines = props.newString.split('\n')
  return newLines.filter((l, i) => l !== (oldLines[i] ?? null)).length
})

const deletions = computed(() => {
  const oldLines = props.oldString.split('\n')
  const newLines = props.newString.split('\n')
  return oldLines.filter((l, i) => l !== (newLines[i] ?? null)).length
})

function copyDiffPath() {
  const text = `--- ${props.filePath}\n+++ ${props.filePath}`
  navigator.clipboard?.writeText(text).catch(() => {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  })
}
</script>

<template>
  <div class="overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)]/50 bg-[var(--color-surface-container-low)]">
    <div class="flex items-center justify-between border-b border-[var(--color-outline-variant)]/40 bg-[var(--color-surface-container)] px-3 py-1.5">
      <div class="min-w-0">
        <div class="truncate font-[var(--font-mono)] text-[11px] text-[var(--color-text-tertiary)]">
          {{ filePath }}
        </div>
        <div class="mt-1 flex items-center gap-2 text-[10px] uppercase tracking-[0.14em]">
          <span class="rounded-full bg-[var(--color-diff-added-bg)] px-2 py-0.5 text-[var(--color-diff-added-text)]">+{{ additions }}</span>
          <span class="rounded-full bg-[var(--color-diff-removed-bg)] px-2 py-0.5 text-[var(--color-diff-removed-text)]">-{{ deletions }}</span>
        </div>
      </div>
      <button type="button" @click="copyDiffPath" aria-label="Copy path"
        class="rounded-md border border-[var(--color-outline-variant)]/40 bg-[var(--color-surface-container-lowest)] px-2 py-1 text-[11px] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-container-high)] hover:text-[var(--color-text-primary)]">
        <span class="material-symbols-outlined text-[13px] mr-1">content_copy</span>
        Copy path
      </button>
    </div>

    <div class="max-h-[400px] overflow-auto">
      <slot :old="oldString" :new="newString" :file-path="filePath">
        <pre class="m-0 overflow-x-auto p-3 font-[var(--font-mono)] text-[12px] leading-relaxed text-[var(--color-text-primary)]">{{ oldString }}</pre>
      </slot>
    </div>
  </div>
</template>
