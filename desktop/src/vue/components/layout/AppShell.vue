<script setup lang="ts">
// v3.0 — AppShell (Vue 3, React-equivalent layout)
// Mirrors desktop/src/components/layout/AppShell.tsx EXACTLY:
//   - Top: macOS traffic-light spacer + brand badge
//   - Below: Sidebar (left, collapsible) + main content area
//   - Inside main: optional TabBar on top, content below
//   - Bottom: H5 connection error / content router / error view
// No Tabstrip on top — that was the Vue version's "extra" that React doesn't have.

import { ref, onMounted, onUnmounted, computed } from 'vue'
import Sidebar from './Sidebar.vue'
import ContentRouter from './ContentRouter.vue'
import StartupErrorView from './StartupErrorView.vue'
import CommandPalette from '../command/CommandPalette.vue'
import { useSessionStore } from '../../stores/sessionStore'
import { useTabStore } from '../../stores/tabs'
import { useChatStore } from '../../stores/chatStore'
import { useTranslation } from '../../i18n'

const ready = ref(false)
const paletteOpen = ref(false)

// Listen for ⌘K toggle event from CommandPalette
onMounted(() => {
  window.addEventListener('madcop:command-palette-toggle', () => {
    paletteOpen.value = !paletteOpen.value
  })
})
const startupError = ref<string | null>(null)
const sidebarOpen = ref(true)

onMounted(() => {
  // Backend health check (silent — don't block app on transient failures)
  fetch('/api/health')
    .then(() => { ready.value = true })
    .catch(() => { /* backend may be slow or unreachable, don't block the app */ })
    .finally(() => { ready.value = true })
  
  // Auto-create initial session tab so user sees ActiveSession (with ChatInput),
  // not EmptySession (which has a different composer layout)
  const sessionStore = useSessionStore()
  const tabStore = useTabStore()
  const chatStore = useChatStore()
  const t = useTranslation()
  
  if (!tabStore.activeTabId && sessionStore.sessions.length === 0) {
    sessionStore.createSession().then((id: string) => {
      tabStore.openTab(id, t('sidebar.newSession'))
      chatStore.connectToSession(id)
    })
  }
})

function toggleSidebar() { sidebarOpen.value = !sidebarOpen.value }
</script>

<template>
  <!-- Startup error -->
  <StartupErrorView v-if="startupError" :error="startupError!" />

  <!-- Main shell — matches React AppShell structure -->
  <div v-else class="h-screen w-screen flex flex-col overflow-hidden bg-[var(--color-surface)]">
    <!-- Body: Sidebar + Content (no separate TitleBar — sidebar handles macOS padding) -->
    <div class="flex flex-1 min-h-0 overflow-hidden">
      <!-- Sidebar -->
      <aside
        v-if="sidebarOpen"
        class="border-r border-[var(--color-border)] bg-[var(--color-surface-sidebar)] flex flex-col flex-shrink-0"
        style="width: var(--sidebar-width, 280px);"
      >
        <Sidebar />
      </aside>

      <!-- Main content area -->
      <main class="flex-1 flex flex-col min-w-0 overflow-hidden">
        <ContentRouter />
      </main>
    </div>

    <!-- ⌘K Command Palette -->
    <CommandPalette :open="paletteOpen" @close="paletteOpen = false" />
  </div>
</template>