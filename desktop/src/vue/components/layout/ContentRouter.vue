<script setup lang="ts">
// v3.0 — ContentRouter (Vue 3)
// Full translation of ContentRouter.tsx — routes active tab type to the correct page.
// Uses defineAsyncComponent for lazy-loaded pages.
import { computed, onMounted, watch, defineAsyncComponent, type PropType } from 'vue'
import { useTabStore } from '../../stores/tabStore'

// Lazy-loaded page components
const EmptySession = defineAsyncComponent(() => import('../../pages/EmptySession.vue'))
const ActiveSession = defineAsyncComponent(() => import('../../pages/ActiveSession.vue'))
const Settings = defineAsyncComponent(() => import('../../pages/Settings.vue'))
const ScheduledTasks = defineAsyncComponent(() => import('../../pages/ScheduledTasks.vue'))
const TerminalSettings = defineAsyncComponent(() => import('../../pages/TerminalSettings.vue'))
const TraceList = defineAsyncComponent(() => import('../../pages/TraceList.vue'))
const TraceSession = defineAsyncComponent(() => import('../../pages/TraceSession.vue'))
const WorkflowsListPage = defineAsyncComponent(() => import('../../pages/WorkflowsListPage.vue'))
const AgentHub = defineAsyncComponent(() => import('../../pages/AgentHub.vue'))
const KnowledgeBase = defineAsyncComponent(() => import('../../pages/KnowledgeBase.vue'))
const DesignPage = defineAsyncComponent(() => import('../../pages/DesignPage.vue'))
const WorkbenchTab = defineAsyncComponent(() => import('../workbench/WorkbenchTab.vue'))

const props = defineProps<{
  // These can be passed in; if omitted the component reads from the store directly.
  activeTabId?: string | null
  activeTabType?: string | null
}>()

const tabStore = useTabStore()

const storeActiveTabId = computed(() => tabStore.activeTabId ?? null)
const storeTabs = computed(() => tabStore.tabs ?? [])

const activeTabId = computed(() => props.activeTabId ?? storeActiveTabId.value)
const tabs = computed(() => props.activeTabType ? storeTabs.value : storeTabs.value)

const activeTabType = computed(() => {
  if (props.activeTabType) return props.activeTabType
  const tab = tabs.value.find((t: { sessionId: string }) => t.sessionId === activeTabId.value)
  return tab?.type ?? null
})

const terminalTabs = computed(() => tabs.value.filter((t: { type: string }) => t.type === 'terminal'))

// previewBridge — close preview when leaving session/workbench tabs.
// Uses the original React lib; guarded for environments where it's absent.
function closePreviewIfNonSession() {
  if (activeTabType.value === 'session' || activeTabType.value === 'workbench') return
  // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access, @typescript-eslint/no-explicit-any
  const previewBridge = (window as any).__previewBridge
  if (previewBridge && typeof previewBridge.close === 'function') {
    try { previewBridge.close() } catch { /* ignore */ }
  }
}

// On mount + whenever activeTabType changes, run the cleanup that React's
// useEffect([activeTabType]) performs.
onMounted(() => { closePreviewIfNonSession() })
watch(activeTabType, () => { closePreviewIfNonSession() })

// Derived values for the page selection logic (mirrors ContentRouter.tsx lines 26–49)
const resolvedPage = computed(() => {
  if (!activeTabId.value || !activeTabType.value) {
    return { kind: 'empty' as const }
  }
  if (activeTabType.value === 'settings') {
    return { kind: 'settings' as const }
  }
  if (activeTabType.value === 'scheduled') {
    return { kind: 'scheduled' as const }
  }
  if (activeTabType.value === 'trace') {
    const traceTab = tabs.value.find((t: { sessionId: string }) => t.sessionId === activeTabId.value)
    const traceSessionId = (traceTab as any)?.traceSessionId ?? null
    return traceSessionId
      ? ({ kind: 'traceSession' as const, traceSessionId })
      : ({ kind: 'empty' as const })
  }
  if (activeTabType.value === 'traces') {
    return { kind: 'traces' as const }
  }
  if (activeTabType.value === 'workbench') {
    const wbTab = tabs.value.find((t: { sessionId: string }) => t.sessionId === activeTabId.value)
    const wbSessionId = (wbTab as any)?.workbenchSessionId ?? null
    return wbSessionId
      ? ({ kind: 'workbench' as const, sessionId: wbSessionId, tabId: activeTabId.value })
      : ({ kind: 'empty' as const })
  }
  if (activeTabType.value === 'workflows') {
    return { kind: 'workflows' as const }
  }
  if (activeTabType.value === 'design') {
    return { kind: 'design' as const }
  }
  if (activeTabType.value !== 'terminal') {
    return { kind: 'active' as const }
  }
  return { kind: 'none' as const }
})
</script>

<template>
  <div class="relative min-h-0 flex-1 overflow-hidden">
    <!-- Main page area (mirrors ContentRouter.tsx lines 51–57) -->
    <div
      v-if="resolvedPage.kind !== 'none'"
      class="absolute inset-0 z-10 flex min-h-0 flex-col overflow-hidden"
    >
      <EmptySession v-if="resolvedPage.kind === 'empty'" />
      <Settings v-else-if="resolvedPage.kind === 'settings'" />
      <ScheduledTasks v-else-if="resolvedPage.kind === 'scheduled'" />
      <TraceSession
        v-else-if="resolvedPage.kind === 'traceSession'"
        :session-id="resolvedPage.traceSessionId!"
      />
      <TraceList v-else-if="resolvedPage.kind === 'traces'" />
      <WorkbenchTab
        v-else-if="resolvedPage.kind === 'workbench'"
        :tab-id="resolvedPage.tabId!"
        :session-id="resolvedPage.sessionId!"
      />
      <WorkflowsListPage v-else-if="resolvedPage.kind === 'workflows'" />
      <DesignPage v-else-if="resolvedPage.kind === 'design'" />
      <AgentHub v-else-if="resolvedPage.kind === 'agents'" />
      <KnowledgeBase v-else-if="resolvedPage.kind === 'knowledge'" />
      <ActiveSession v-else-if="resolvedPage.kind === 'active'" />
    </div>

    <!-- Terminal tab overlays (mirrors ContentRouter.tsx lines 58–80) -->
    <template v-for="tab in terminalTabs" :key="tab.sessionId">
      <div
        :aria-hidden="!(activeTabType === 'terminal' && tab.sessionId === activeTabId)"
        :data-testid="`terminal-tab-panel-${tab.sessionId}`"
        :class="[
          'absolute inset-0 flex min-h-0 flex-col overflow-hidden',
          activeTabType === 'terminal' && tab.sessionId === activeTabId
            ? 'z-20 opacity-100'
            : 'pointer-events-none z-0 opacity-0',
        ]"
      >
        <TerminalSettings
          :active="tab.sessionId === activeTabId"
          :cwd="tab.terminalCwd"
          :runtime-id="tab.terminalRuntimeId ?? tab.sessionId"
          :test-id="`terminal-host-${tab.sessionId}`"
          workspace
        />
      </div>
    </template>
  </div>
</template>
