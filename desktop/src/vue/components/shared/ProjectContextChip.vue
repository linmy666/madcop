<script setup lang="ts">
// v3.0 — ProjectContextChip (Vue 3)
// Direct translation — same Tailwind classes, same GitHub SVG icon.
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  workDir?: string | null
  repoName?: string | null
  branch?: string | null
  sourceWorkDir?: string | null
  isWorktree?: boolean
  worktreeSlug?: string | null
  worktreePath?: string | null
  compact?: boolean
}>(), {
  isWorktree: false,
  compact: false,
})

function basename(p?: string | null): string {
  return p?.split('/').filter(Boolean).pop() || ''
}

const labelRoot = computed(() => props.isWorktree ? (props.sourceWorkDir || props.workDir) : props.workDir)
const label = computed(() => {
  if (props.branch) return props.repoName || basename(labelRoot.value)
  return basename(labelRoot.value) || props.repoName || ''
})
const worktreeName = computed(() => props.worktreeSlug || basename(props.worktreePath) || 'isolated')
const showBranch = computed(() => Boolean(props.branch) && !props.isWorktree)
const title = computed(() => [
  label.value,
  props.branch ? `branch: ${props.branch}` : null,
  props.isWorktree ? `worktree: ${worktreeName.value}` : null,
  props.worktreePath ? `worktree cwd: ${props.worktreePath}` : null,
  props.workDir ? `cwd: ${props.workDir}` : null,
].filter(Boolean).join('\n'))
</script>

<template>
  <div
    v-if="label"
    :title="title"
    :class="[
      'inline-flex max-w-full items-center rounded-full border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] text-[var(--color-text-secondary)]',
      compact ? 'gap-1.5 px-3 py-1.5 text-xs' : 'gap-2 px-4 py-2 text-sm',
    ]"
  >
    <svg v-if="showBranch" :width="compact ? 15 : 18" :height="compact ? 15 : 18" viewBox="0 0 16 16" fill="currentColor" class="shrink-0 text-[var(--color-text-secondary)]">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
    <span v-else class="material-symbols-outlined text-[var(--color-text-secondary)]" :style="{ fontSize: compact ? '15px' : '18px' }">folder</span>
    <span class="truncate font-medium text-[var(--color-text-primary)]">{{ label }}</span>
    <template v-if="showBranch">
      <span class="text-[var(--color-text-tertiary)]">|</span>
      <span class="truncate">{{ branch }}</span>
    </template>
    <template v-if="isWorktree">
      <span class="text-[var(--color-text-tertiary)]">|</span>
      <span class="shrink-0 rounded-full border border-[var(--color-border)] px-1.5 py-0.5 text-[10px] font-medium uppercase leading-none text-[var(--color-text-tertiary)]">worktree</span>
    </template>
  </div>
</template>
