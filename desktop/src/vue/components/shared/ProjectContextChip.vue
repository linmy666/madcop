<script setup lang="ts">
// v3.0 — Project context chip (Vue 3)
// Compact pill showing current working directory / repo / branch.
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  workDir?: string | null
  repoName?: string | null
  branch?: string | null
  isWorktree?: boolean
  compact?: boolean
}>(), {
  isWorktree: false,
  compact: false,
})

const basename = (p?: string | null) => p?.split('/').filter(Boolean).pop() || ''

const label = computed(() => {
  if (props.branch) return props.repoName || basename(props.workDir)
  return basename(props.workDir) || props.repoName || ''
})
</script>

<template>
  <div
    v-if="label"
    :class="['madcop-chip', { 'madcop-chip--compact': compact }]"
    :title="[label, props.branch ? `branch: ${props.branch}` : null, props.isWorktree ? 'worktree' : null, props.workDir ? `cwd: ${props.workDir}` : null].filter(Boolean).join('\\n')"
  >
    <span v-if="props.branch && !props.isWorktree" class="madcop-chip__icon">⎇</span>
    <span v-else class="madcop-chip__icon">▣</span>
    <span class="madcop-chip__label">{{ label }}</span>
    <span v-if="props.branch && !props.isWorktree" class="madcop-chip__sep">|</span>
    <span v-if="props.branch && !props.isWorktree" class="madcop-chip__branch">{{ props.branch }}</span>
    <span v-if="props.isWorktree" class="madcop-chip__sep">|</span>
    <span v-if="props.isWorktree" class="madcop-chip__worktree">worktree</span>
  </div>
</template>

<style scoped>
.madcop-chip {
  display: inline-flex; align-items: center; gap: 8px;
  max-width: 100%;
  padding: 4px 12px;
  border: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-raised);
  font-size: 12px;
  color: var(--madcop-ink-body);
  font-family: 'Geist Mono', monospace;
}
.madcop-chip--compact { padding: 3px 10px; font-size: 11px; gap: 6px; }
.madcop-chip__icon { font-size: 14px; }
.madcop-chip__label { font-weight: 500; color: var(--madcop-ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.madcop-chip__sep   { color: var(--madcop-ink-subtle); }
.madcop-chip__branch { color: var(--madcop-ink-body); overflow: hidden; text-overflow: ellipsis; }
.madcop-chip__worktree {
  padding: 1px 6px;
  border: 1.5px solid var(--madcop-line);
  border-radius: 999px;
  font-size: 9px; text-transform: uppercase;
  color: var(--madcop-ink-subtle);
}
</style>
