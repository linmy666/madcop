<script setup lang="ts">
// v3.0 — AppShell (Vue 3, React-equivalent layout)
// Mirrors desktop/src/components/layout/AppShell.tsx EXACTLY:
//   - Inside main: optional TabBar on top, content below
//   - Bottom: H5 connection error / content router / error view
// No Tabstrip on top — that was the Vue version's "extra" that React doesn't have.

import { ref, onMounted, onUnmounted, computed } from 'vue'
import Sidebar from './Sidebar.vue'
import ContentRouter from './ContentRouter.vue'
import StartupErrorView from './StartupErrorView.vue'
import CommandPalette from '../command/CommandPalette.vue'
import TabStrip from './TabStrip.vue'
import { useSessionStore } from '../../stores/sessionStore'
import { useTabStore } from '../../stores/tabs'
import { useChatStore } from '../../stores/chatStore'
import { useTranslation } from '../../i18n'
import { watch } from 'vue'

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

  // Mirror the current workspace dir to localStorage so the
  // sessionStore can attribute loaded sessions to it. This must run
  // synchronously (well, before any session is rendered) so the
  // sidebar doesn't briefly show "unknown".
  fetch('/api/workspace/dir')
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (data?.dir) {
        try { localStorage.setItem('madcop_workspace_dir', data.dir) } catch {}
      }
    })
    .catch(() => { /* ignore */ })

  // Auto-create initial session tab so user sees ActiveSession (with ChatInput),
  // not EmptySession (which has a different composer layout)
  const sessionStore = useSessionStore()
  const tabStore = useTabStore()
  const chatStore = useChatStore()
  const t = useTranslation()

  // Helper: ensure there's always an active tab
  function ensureActiveTab() {
    if (tabStore.activeTabId) return
    if (tabStore.tabs.length > 0) {
      // Adopt the most recent tab
      const last = tabStore.tabs[tabStore.tabs.length - 1]
      tabStore.setActiveTab(last.sessionId)
      chatStore.connectToSession(last.sessionId)
    } else if (sessionStore.sessions.length > 0) {
      // Open a tab for the first session
      const firstSession = sessionStore.sessions[0]
      tabStore.openTab(firstSession.id, firstSession.title || t('sidebar.newSession'))
      chatStore.connectToSession(firstSession.id)
    } else {
      // Create a brand new session tab
      sessionStore.createSession().then((id: string) => {
        tabStore.openTab(id, t('sidebar.newSession'))
        chatStore.connectToSession(id)
      })
    }
  }

  // Initial setup
  ensureActiveTab()

  // Reactively recreate tab when user closes the last one
  watch(() => tabStore.tabs.length, (newLen) => {
    if (newLen === 0) {
      // Small delay to let Vue update first, then re-create
      setTimeout(() => ensureActiveTab(), 50)
    }
  })
})

function toggleSidebar() { sidebarOpen.value = !sidebarOpen.value }
</script>

<template>
  <!-- Startup error -->
  <StartupErrorView v-if="startupError" :error="startupError!" />

  <!-- Main shell — matches React AppShell structure -->
  <div v-else class="fixed inset-0 flex flex-col overflow-hidden bg-[var(--color-surface)]">
    <!-- Body: Sidebar + TabStrip + Content -->
    <div class="flex flex-1 min-h-0 overflow-hidden w-full">
      <!-- Sidebar -->
      <aside
        v-if="sidebarOpen"
        class="border-r border-[var(--color-border)] bg-[var(--color-surface-sidebar)] flex flex-col flex-shrink-0"
        style="width: var(--sidebar-width, 280px);"
      >
        <Sidebar />
      </aside>

      <!-- Right side: TabStrip (top) + Main (bottom) -->
      <div class="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TabStrip style="width: 100%; flex-shrink: 0;" />
        <main class="flex-1 flex flex-col min-w-0 overflow-hidden">
          <ContentRouter />
        </main>
      </div>
    </div>

    <!-- ⌘K Command Palette -->
    <CommandPalette :open="paletteOpen" @close="paletteOpen = false" />
  </div>
</template>