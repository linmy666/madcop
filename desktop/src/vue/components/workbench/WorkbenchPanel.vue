<script setup lang="ts">
/**
 * WorkbenchPanel — Full Vue 3 port of components/workbench/WorkbenchPanel.tsx (121 lines)
 * Unified right-side "Workbench" panel with file/workspace and browser mode switch.
 *
 * Uses Pinia stores (workspacePanelStore, tabStore) from Vue stores.
 * Since Vue has no browserPanelStore yet, ensureBlankBrowser is a noop.
 *
 * Translations:
 *   lucide-react (FolderOpen/Globe/Maximize2/X) → material-symbols-outlined icons
 *   zustand → Pinia stores (useWorkspacePanelStore, useTabStore)
 *   All Tailwind classes and --color-* variables preserved VERBATIM
 */

import { computed } from 'vue'
import { useTranslation } from '../../i18n'
import {
  useWorkspacePanelStore,
  type WorkbenchMode,
} from '../../stores/workspacePanelStore'
import { useTabStore } from '../../stores/tabs'

export interface WorkbenchPanelProps {
  sessionId: string
  variant?: 'panel' | 'tab'
  onClose?: () => void
}

const props = withDefaults(defineProps<WorkbenchPanelProps>(), {
  variant: 'panel',
})

const t = useTranslation()
const workspacePanel = useWorkspacePanelStore()
const tabStore = useTabStore()

// ─── Mode from store ────────────────────────────────────────────
const mode = computed(() => workspacePanel.getMode(props.sessionId))

function setMode(modeVal: WorkbenchMode) {
  workspacePanel.setMode(props.sessionId, modeVal)
}

// ─── Helpers ────────────────────────────────────────────────────
const isTabVariant = computed(() => props.variant === 'tab')

// Browser panel store not yet ported to Vue — no-op
function ensureBlankBrowser(_sessionId: string) {
  // In React: useBrowserPanelStore().ensureBlank(sessionId)
  // Vue: browserPanelStore does not exist yet; browser mode just toggles the view
}

function handleModeSelect(nextMode: WorkbenchMode) {
  if (nextMode === 'browser') {
    ensureBlankBrowser(props.sessionId)
  }
  setMode(nextMode)
}

function handleExpand() {
  tabStore.openWorkbenchTab(props.sessionId, t('workbench.tabTitle'))
}

function handleClose() {
  if (props.onClose) {
    props.onClose()
    return
  }
  workspacePanel.closePanel(props.sessionId)
}

// ─── Mode items ─────────────────────────────────────────────────
const MODE_ITEMS = [
  {
    mode: 'workspace' as const,
    labelKey: 'workbench.modeWorkspace' as const,
    icon: 'folder_open',
  },
  {
    mode: 'browser' as const,
    labelKey: 'workbench.modeBrowser' as const,
    icon: 'public',
  },
]
</script>

<template>
  <div class="flex h-full min-h-0 w-full flex-col bg-[var(--color-surface)]">
    <!-- Mode bar -->
    <div class="flex h-10 shrink-0 items-center gap-2 border-b border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] px-2.5">
      <div
        role="tablist"
        :aria-label="t('workbench.modeSwitch')"
        class="inline-flex items-center gap-0.5 rounded-[8px] border border-[var(--color-border)] bg-[var(--color-surface)] p-0.5"
      >
        <button
          v-for="item in MODE_ITEMS"
          :key="item.mode"
          type="button"
          role="tab"
          :aria-selected="mode === item.mode"
          @click="handleModeSelect(item.mode)"
          :class="[
            'inline-flex h-7 items-center gap-1.5 rounded-[6px] px-2.5 text-[12px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/35',
            mode === item.mode
              ? 'bg-[var(--color-surface-selected)] text-[var(--color-text-primary)] shadow-[inset_0_0_0_1px_var(--color-border-focus)]'
              : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]'
          ]"
        >
          <span class="material-symbols-outlined text-[15px] shrink-0" aria-hidden="true">{{ item.icon }}</span>
          <span>{{ t(item.labelKey) }}</span>
        </button>
      </div>

      <div class="ml-auto flex shrink-0 items-center gap-1">
        <button
          v-if="!isTabVariant"
          type="button"
          :aria-label="t('workbench.expand')"
          :title="t('workbench.expand')"
          @click="handleExpand"
          class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-[7px] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/35"
        >
          <span class="material-symbols-outlined text-[15px]" aria-hidden="true">open_in_full</span>
        </button>
        <button
          type="button"
          :aria-label="t('workbench.close')"
          @click="handleClose"
          class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-[7px] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/35"
        >
          <span class="material-symbols-outlined text-[16px]" aria-hidden="true">close</span>
        </button>
      </div>
    </div>

    <!-- Panel content -->
    <div class="flex min-h-0 flex-1 flex-col">
      <!-- Browser surface -->
      <template v-if="mode === 'browser'">
        <slot name="browser" :session-id="sessionId" />
      </template>
      <!-- Workspace panel -->
      <template v-else>
        <slot name="workspace" :session-id="sessionId" :embedded="true" :force-visible="isTabVariant" />
      </template>
    </div>
  </div>
</template>
