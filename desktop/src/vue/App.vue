<script setup lang="ts">
// v3.0 — MadCop App.vue (Vue 3)
// Vue 3 Composition API. Replaces the React App.tsx with the same
// functionality: a top-level shell with sidebar + tab strip + main.
import { ref, computed, onMounted } from 'vue'
import MadcopShell from './components/layout/MadcopShell.vue'
import MadcopSidebar from './components/layout/MadcopSidebar.vue'
import type { MadcopSection } from './components/layout/MadcopSidebar.vue'
import MadcopTitlebar from './components/layout/MadcopTitlebar.vue'
import MadcopTabstrip from './components/layout/MadcopTabstrip.vue'
import MadcopStatusbar from './components/layout/MadcopStatusbar.vue'
import { useAppearance, type Appearance } from './composables/useAppearance'
import { useTabs } from './stores/tabs'
import { isDesktopRuntime, initializeDesktopServerUrl } from '../lib/desktopRuntime'

const section = ref<MadcopSection>('chat')
const { appearance, setAppearance } = useAppearance()
const tabsStore = useTabs()

const activeTab = computed(() =>
  tabsStore.tabs.find((t: any) => t.id === tabsStore.activeTabId) ?? null
)

const showEmpty = computed(() => !activeTab.value)
const showChat = computed(() => section.value === 'chat' && activeTab.value?.kind === 'chat')
const showDesign = computed(() => section.value === 'design' && activeTab.value?.kind === 'design')

// ── Bootstrap: H5 proxy init + settings load ──────────────────────────────────
onMounted(async () => {
  if (isDesktopRuntime) {
    try {
      await initializeDesktopServerUrl()
    } catch (err) {
      console.warn('[AppShell] H5 proxy init failed:', err)
    }
  }
})

function onSection(s: MadcopSection) {
  section.value = s
  if (s === 'design') {
    tabsStore.open({ kind: 'design', title: '设计工具' })
  } else if (s === 'chat' && !tabsStore.tabs.some((t: any) => t.kind === 'chat')) {
    tabsStore.open({ kind: 'chat', title: '新会话' })
  }
}

function onCommand(cmd: string) {
  if (cmd.startsWith('appearance:')) {
    const next = cmd.split(':')[1] as Appearance
    setAppearance(next)
  } else if (cmd === 'settings:open') {
    section.value = 'settings'
  } else {
    tabsStore.open({ kind: 'chat', title: cmd.slice(0, 16), dirty: true })
  }
}
</script>

<template>
  <MadcopShell
    :titlebar="true"
    :sidebar="true"
    :tabstrip="true"
    :statusbar="true"
  >
    <template #titlebar>
      <MadcopTitlebar project-name="无标题项目" @command="onCommand" />
    </template>
    <template #sidebar>
      <MadcopSidebar
        :active="section"
        @select="onSection"
      />
    </template>
    <template #tabstrip>
      <MadcopTabstrip
        :tabs="tabsStore.tabs"
        :active="tabsStore.activeTabId"
        @select="(id: string) => tabsStore.select(id)"
        @close="(id: string) => tabsStore.close(id)"
      />
    </template>
    <template #statusbar>
      <MadcopStatusbar />
    </template>

    <DesignPage v-if="showDesign" />
    <EmptyPage v-else-if="showEmpty" />
    <ChatPage v-else-if="showChat" />
    <EmptyPage v-else />
  </MadcopShell>
</template>

<script lang="ts">
import { defineAsyncComponent } from 'vue'
const DesignPage = defineAsyncComponent(() => import('./pages/DesignPage.vue'))
const EmptyPage = defineAsyncComponent(() => import('./pages/EmptyPage.vue'))
const ChatPage = defineAsyncComponent(() => import('./pages/ChatPage.vue'))
export default { components: { DesignPage, EmptyPage, ChatPage } }
</script>
