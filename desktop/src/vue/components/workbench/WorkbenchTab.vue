<script setup lang="ts">
// v3.0 — WorkbenchTab (Vue 3)
// Full translation of WorkbenchTab.tsx — same Tailwind classes,
// wired into workspacePanelStore / browserPanelStore.
import { onMounted, watch } from 'vue'
import { useWorkspacePanelStore } from '../../stores/workspacePanelStore'
import WorkbenchPanel from '../workbench/WorkbenchPanel.vue'

const props = defineProps<{ tabId: string; sessionId: string }>()
const emit = defineEmits<{
  (e: 'close'): void
}>()

const wsStore = useWorkspacePanelStore()

// Close the parent tab via the emit event (mirrors React's
// useTabStore().closeTab(tabId)).
function onClose() {
  emit('close')
}

// useEffect([mode, sessionId]) — when mode becomes 'browser', ensure blank
// browser panel. browserPanelStore is optional in the Vue build; guarded.
function ensureBrowserBlank(id: string) {
  try {
    // eslint-disable-next-line @typescript-eslint/no-unsafe-call, @typescript-eslint/no-var-requires
    const browserPanelStore = require('../../stores/browserPanelStore').useBrowserPanelStore
    if (browserPanelStore && typeof browserPanelStore === 'function') {
      const store = browserPanelStore.getState
        ? browserPanelStore.getState()
        : browserPanelStore()
      if (store && typeof store.ensureBlank === 'function') {
        store.ensureBlank(id)
      }
    }
  } catch {
    /* browserPanelStore not available — skip */
  }
}

const mode = wsStore.getMode(props.sessionId)

onMounted(() => {
  if (mode === 'browser') {
    ensureBrowserBlank(props.sessionId)
  }
})

// Watch for mode changes and sessionId changes (mirrors React useEffect deps)
watch(
  () => [mode, props.sessionId] as [string, string],
  (vals) => {
    if (vals[0] === 'browser') {
      ensureBrowserBlank(vals[1])
    }
  },
)
</script>

<template>
  <div data-testid="workbench-tab" class="flex min-h-0 flex-1 flex-col bg-[var(--color-surface)]">
    <WorkbenchPanel :session-id="sessionId" variant="tab" @close="onClose" />
  </div>
</template>
