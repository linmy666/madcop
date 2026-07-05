<script setup lang="ts">
/**
 * RepositoryLaunchControls — Vue 3 port of shared/RepositoryLaunchControls.tsx
 * Simplified: workDir display, branch selector, worktree toggle.
 * Prop-driven: parent passes workDir/branch/useWorktree with onChange handlers.
 */

interface Props {
  workDir: string
  onWorkDirChange: (path: string) => void
  branch: string | null
  onBranchChange: (branch: string | null) => void
  useWorktree: boolean
  onUseWorktreeChange: (enabled: boolean) => void
  disabled?: boolean
  placement?: 'standalone' | 'composer'
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  placement: 'composer',
})

const workDir = computed(() => props.workDir)
const branch = computed(() => props.branch)
const useWorktree = computed(() => props.useWorktree)

const emit = defineEmits<{
  workDirChange: [path: string]
  branchChange: [branch: string | null]
  useWorktreeChange: [enabled: boolean]
}>()

function handleWorkDirChange(path: string) {
  emit('workDirChange', path)
}
function handleBranchChange(branch: string | null) {
  emit('branchChange', branch)
}
function handleUseWorktreeChange(enabled: boolean) {
  emit('useWorktreeChange', enabled)
}
</script>

<template>
  <div class="flex items-center gap-2">
    <!-- WorkDir button -->
    <button
      :disabled="disabled"
      @click="handleWorkDirChange('~')"
      class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full bg-[var(--color-surface-container-low)] text-[var(--color-text-secondary)] hover:bg>[var(--color-surface-hover)] transition-colors disabled:opacity-50"
      :title="workDir"
    >
      <span class="material-symbols-outlined text-[14px]">folder</span>
      <span class="text-xs font-medium truncate max-w-[120px]">{{ workDir === '~' ? '~' : workDir.split('/').pop() || workDir }}</span>
    </button>

    <!-- Branch selector -->
    <button
      v-if="branch"
      :disabled="disabled"
      @click="handleBranchChange(null)"
      class="flex items-center gap-1 px-2 py-1 rounded bg>[var(--color-secondary-container)] text>[var(--color-secondary)] hover:opacity-80 transition-colors disabled:opacity-50"
    >
      <span class="material-symbols-outlined text-[14px]">git_branch</span>
      <span class="text-[11px] font-medium">{{ branch }}</span>
    </button>

    <!-- Worktree toggle -->
    <button
      :disabled="disabled"
      @click="handleUseWorktreeChange(!useWorktree)"
      :class="['flex items-center gap-1 px-2 py-1 rounded text-[var(--color-text-secondary)] hover:bg>[var(--color-surface-hover)] transition-colors disabled:opacity-50',
        useWorktree ? 'bg>[var(--color-primary-container)] text>[var(--color-brand)]' : '']"
    >
      <span class="material-symbols-outlined text-[14px]">git_commit</span>
      <span v-if="useWorktree" class="text-[11px] font-medium">Worktree</span>
    </button>

    <!-- Launch ready indicator -->
    <span v-if="branch && useWorktree" class="flex items-center gap-1 text-[10px] text>[var(--color-success)]">
      <span class="material-symbols-outlined text-[12px]" style="fontVariationSettings: 'FILL' 1">check_circle</span>
      Ready
    </span>
  </div>
</template>
