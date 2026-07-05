<script setup lang="ts">
import { ref } from 'vue'

/**
 * WorkbenchPanel — Vue 3 port of components/workbench/WorkbenchPanel.tsx
 * Unified right-side panel with file/workspace and browser mode switch.
 * Prop-driven: parent passes sessionId, variant, onClose.
 * Mode is controlled via ref (no store).
 */

export type WorkbenchMode = 'workspace' | 'browser'

export interface WorkbenchPanelProps {
  sessionId: string
  variant?: 'panel' | 'tab'
}

const props = withDefaults(defineProps<WorkbenchPanelProps>(), {
  variant: 'panel',
})

const emit = defineEmits<{
  close: []
  modeChange: [mode: WorkbenchMode]
}>()

const mode = ref<WorkbenchMode>('workspace')
const isTabVariant = props.variant === 'tab'

function handleModeSelect(nextMode: WorkbenchMode) {
  mode.value = nextMode
  emit('modeChange', nextMode)
}

function handleExpand() {
  emit('close')
}
</script>

<template>
  <div class="flex h-full min-h-0 w-full flex-col bg-[var(--color-surface)]">
    <div class="flex h-10 shrink-0 items-center gap-2 border-b border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] px-2.5">
      <div role="tablist" class="inline-flex items-center gap-0.5 rounded-[8px] border border-[var(--color-border)] bg-[var(--color-surface)] p-0.5">
        <button v-for="m in ['workspace', 'browser'] as const" :key="m"
          type="button" role="tab" @click="handleModeSelect(m)"
          :aria-selected="mode === m"
          :class="['inline-flex h-7 items-center gap-1.5 rounded-[6px] px-2.5 text-[12px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/35',
            mode === m ? 'bg-[var(--color-surface-selected)] text-[var(--color-text-primary)] shadow-[inset_0_0_0_1px_var(--color-border-focus)]' : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]']">
          <span class="material-symbols-outlined text-[15px] shrink-0" aria-hidden="true">{{ m === 'workspace' ? 'folder_open' : 'public' }}</span>
          <span>{{ m === 'workspace' ? 'Workspace' : 'Browser' }}</span>
        </button>
      </div>

      <div class="ml-auto flex shrink-0 items-center gap-1">
        <button v-if="!isTabVariant" type="button" @click="handleExpand"
          aria-label="Expand" class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-[7px] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/35">
          <span class="material-symbols-outlined text-[15px]" aria-hidden="true">open_in_full</span>
        </button>
        <button type="button" @click="emit('close')"
          aria-label="Close" class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-[7px] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/35">
          <span class="material-symbols-outlined text-[16px]" aria-hidden="true">close</span>
        </button>
      </div>
    </div>

    <div class="flex min-h-0 flex-1 flex-col">
      <slot :mode="mode" :session-id="sessionId" />
    </div>
  </div>
</template>
