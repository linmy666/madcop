<script setup lang="ts">
import { computed, ref } from 'vue'

/**
 * DiffViewer — Vue 3 port of components/chat/DiffViewer.tsx
 *
 * Shows code diff with file path, +N/-N badges, copy button.
 * Uses slot for diff rendering. No react-diff-viewer-continued dependency.
 * prop-driven: parent passes filePath, oldString, newString.
 *
 * v3.7.7 — supports maxLines collapse so large file writes/edits
 * don't take over the chat. When the new content exceeds maxLines,
 * only the first maxLines lines show, followed by an ellipsis and
 * an expand button.
 */

export interface DiffViewerProps {
  filePath: string
  oldString: string
  newString: string
  /** v3.7.7 — collapse threshold. 0 = no collapse. Default 8. */
  maxLines?: number
}

const props = withDefaults(defineProps<DiffViewerProps>(), {
  maxLines: 8,
})

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

// v3.7.7 — collapse logic. The "content" we collapse is newString
// (the post-edit / post-write body). oldString for edits is usually
// short, but for Write it's empty — so we drive the collapse off
// whichever is longer.
const collapsedBody = ref<string | null>(null)
const expanded = ref(false)
const fullBody = computed(() => {
  // Prefer newString (the actual file content for Write, the new
  // version for Edit). Fall back to oldString.
  return (props.newString || props.oldString || '')
})
const allLines = computed(() => fullBody.value.split('\n'))
const isTruncated = computed(() =>
  !expanded.value
  && props.maxLines > 0
  && allLines.value.length > props.maxLines
)
const visibleBody = computed(() =>
  isTruncated.value
    ? allLines.value.slice(0, props.maxLines).join('\n')
    : fullBody.value
)
const hiddenCount = computed(() =>
  isTruncated.value ? allLines.value.length - props.maxLines : 0
)
function toggleExpanded() { expanded.value = !expanded.value }

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

    <!-- v3.7.7 — collapsible body. When isTruncated, we render only
         visibleBody and an ellipsis + expand button below. -->
    <div class="max-h-[400px] overflow-auto">
      <slot :old="oldString" :new="visibleBody" :file-path="filePath">
        <pre class="m-0 overflow-x-auto p-3 font-[var(--font-mono)] text-[12px] leading-relaxed text-[var(--color-text-primary)]">{{ visibleBody }}</pre>
      </slot>
    </div>
    <div v-if="isTruncated" class="diff-ellipsis" aria-hidden="true"></div>
    <button
      v-if="isTruncated || expanded"
      type="button"
      @click="toggleExpanded"
      class="w-full border-t border-[var(--color-outline-variant)]/40 bg-[var(--color-surface-container)] py-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-container-high)] hover:text-[var(--color-text-primary)]"
    >
      {{ expanded ? '收起代码' : `展开剩余 ${hiddenCount} 行` }}
    </button>
  </div>
</template>

<style scoped>
.diff-ellipsis {
  text-align: center;
  font-size: 16px;
  letter-spacing: 4px;
  color: var(--color-text-tertiary, #999);
  background: var(--color-surface-container, #f5f5f7);
  padding: 2px 0;
  user-select: none;
  line-height: 1;
}
.diff-ellipsis::before { content: '· · ·'; }
</style>
