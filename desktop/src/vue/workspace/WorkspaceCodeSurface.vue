<script setup lang="ts">
/**
 * WorkspaceCodeSurface — Vue 3 port of components/workspace/WorkspaceCodeSurface.tsx
 * Displays file code diffs with line numbers, +/- highlighting.
 * No prism-react-renderer (React-only) — renders plain code with CSS-based styling.
 * Prop-driven.
 */

export interface WorkspaceCodeSurfaceProps {
  value: string
  path: string
  className?: string
  lineLimit?: number
}

const props = withDefaults(defineProps<WorkspaceCodeSurfaceProps>(), {
  className: 'min-h-0 flex-1 overflow-auto bg-[var(--color-code-bg)]',
  lineLimit: 2000,
})

const showAllLines = ref(false)
const lines = computed(() => props.value.split('\n'))
const visibleLines = computed(() => showAllLines.value ? lines.value : lines.value.slice(0, props.lineLimit))

function getLineClass(line: string): string {
  const isAdded = line.startsWith('+') && !line.startsWith('+++')
  const isRemoved = line.startsWith('-') && !line.startsWith('---')
  const isHunk = line.startsWith('@@')
  const isHeader = line.startsWith('diff --') || line.startsWith('--- ') || line.startsWith('+++ ')
  if (isAdded) return 'bg-[var(--color-diff-added-bg)]'
  if (isRemoved) return 'bg-[var(--color-diff-removed-bg)]'
  if (isHunk) return 'bg-[var(--color-diff-highlight-bg)]'
  return 'hover:bg-[var(--color-surface-hover)]'
}
</script>

<template>
  <div :class="className">
    <div class="relative min-w-max py-2">
      <pre data-workspace-code="" data-testid="workspace-code"
        class="m-0 font-[var(--font-mono)] text-[12px] leading-[1.55] text-[var(--color-code-fg)]">
        <div v-for="(line, idx) in visibleLines" :key="idx"
          :class="['grid min-w-full w-max grid-cols-[48px_18px_max-content] gap-2 px-3', getLineClass(line)]">
          <span class="select-none text-right text-[11px] text-[var(--color-text-tertiary)]">{{ idx + 1 }}</span>
          <span class="select-none text-center text-[var(--color-text-tertiary)]">
            {{ line.length > 0 ? (line.startsWith('+') && !line.startsWith('+++') ? '+' : (line.startsWith('-') && !line.startsWith('---') ? '-' : ' ')) : ' ' }}
          </span>
          <span class="whitespace-pre pr-6">{{ line.length > 0 ? line.slice(1) : ' ' }}</span>
        </div>
      </pre>
      <div v-if="lines.length > lineLimit" class="sticky bottom-0 flex items-center gap-3 border-t border-[var(--color-border)] bg-[var(--color-surface-glass)] px-3 py-2 text-xs text-[var(--color-text-tertiary)] backdrop-blur">
        <span>{{ showAllLines ? 'Showing all ' + lines.length + ' lines' : visibleLines.length + ' / ' + lines.length + ' lines' }}</span>
        <button type="button" @click="showAllLines = !showAllLines"
          class="ml-auto rounded-[6px] px-2 py-1 text-[12px] font-medium text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]">
          {{ showAllLines ? 'Collapse' : 'Show All' }}
        </button>
      </div>
    </div>
  </div>
</template>
