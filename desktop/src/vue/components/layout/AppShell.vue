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
import Toast from '../shared/Toast.vue'
import ProactiveToast from '../chat/ProactiveToast.vue'
import { useProactive } from '../../composables/useProactive'

// Sprint 5 — start the proactive observer coordinator (subscribes to
// IPC events + pushes config to main). Safe to call at setup time.
const _proactive = useProactive()
import { useSessionStore } from '../../stores/sessionStore'
import { useTabStore } from '../../stores/tabs'
import { useChatStore } from '../../stores/chatStore'
import { useUIStore } from '../../stores/uiStore'
import { useTranslation } from '../../i18n'

// Sprint 5 — when the user "采纳" a proactive suggestion, push it into
// the active chat session's composer as a prefill.
const _chatStoreForProactive = useChatStore()
function onProactiveAdopt(suggestion: string) {
  const sid = tabStore.activeTabId
  if (sid) {
    _chatStoreForProactive.queueComposerPrefill(sid, { text: suggestion, mode: 'append' })
  }
}
void _proactive
void _chatStoreForProactive
import { watch } from 'vue'

const ready = ref(false)
const paletteOpen = ref(false)
const uiStore = useUIStore()
const tabStore = useTabStore()

// v4 — Hide the horizontal tab strip when the active route is a chat
// session. The sidebar's session list is the single source of truth
// for switching between sessions; on a session page the strip was
// duplicating that. Special/non-session tabs (settings, workflows,
// knowledge, etc.) still get the strip because the sidebar doesn't
// expose them as session entries.
const showTabStrip = computed(() => {
  if (!tabStore.activeTabId) return false
  const tab = tabStore.tabs.find((tb: any) => tb.sessionId === tabStore.activeTabId)
  return tab?.type !== 'session'
})

// Listen for ⌘K toggle event from CommandPalette
const _onPaletteToggle = () => {
  paletteOpen.value = !paletteOpen.value
}
onMounted(() => {
  window.addEventListener('madcop:command-palette-toggle', _onPaletteToggle)
})

// Global keyboard shortcuts (Cursor/Claude Code parity):
//   ⌘/Ctrl+B  → toggle sidebar
//   Esc       → close command palette / panels
//   ⌘/Ctrl+N  → new chat
// Don't interfere with typing — skip when the target is an input,
// textarea, or contenteditable element (except for Esc).
const _isTypingTarget = (el: EventTarget | null) => {
  if (!(el instanceof HTMLElement)) return false
  const tag = el.tagName.toLowerCase()
  return tag === 'input' || tag === 'textarea' || el.isContentEditable
}

function _handleGlobalKeydown(e: KeyboardEvent) {
  const mod = e.metaKey || e.ctrlKey
  // Esc — always works, even in inputs (closes palette/panels).
  if (e.key === 'Escape') {
    if (paletteOpen.value) {
      paletteOpen.value = false
      e.preventDefault()
      return
    }
    // Dispatch a global esc event so panels (workbench, plan sidebar)
    // can close themselves.
    window.dispatchEvent(new CustomEvent('madcop:global-escape'))
    return
  }
  // Shortcuts below are blocked while typing in inputs.
  if (_isTypingTarget(e.target)) return
  if (mod && e.key.toLowerCase() === 'b') {
    e.preventDefault()
    sidebarOpen.value = !sidebarOpen.value
    return
  }
  if (mod && e.key.toLowerCase() === 'n') {
    e.preventDefault()
    // Trigger new-session via the session store.
    try {
      const sessionStore = useSessionStore()
      sessionStore.createSession()
    } catch {}
    return
  }
  // ⌘/Ctrl+Shift+F — global chat search (⌘K is owned by CommandPalette).
  if (mod && e.shiftKey && e.key.toLowerCase() === 'f') {
    e.preventDefault()
    uiStore.openModal('globalSearch')
    return
  }
}

onMounted(() => {
  window.addEventListener('keydown', _handleGlobalKeydown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', _handleGlobalKeydown)
  window.removeEventListener('madcop:command-palette-toggle', _onPaletteToggle)
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

      <!-- Right side: TabStrip (top, non-session routes only) + Main (bottom) -->
      <div class="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TabStrip v-if="showTabStrip" style="width: 100%; flex-shrink: 0;" />
        <main class="flex-1 flex flex-col min-w-0 overflow-hidden">
          <ContentRouter />
        </main>
      </div>
    </div>

    <!-- ⌘K Command Palette -->
    <CommandPalette :open="paletteOpen" @close="paletteOpen = false" />

    <!-- Toast notifications (mounted once globally so showToast() is visible) -->
    <Toast :toasts="uiStore.toasts" @remove="uiStore.removeToast" />

    <!-- Sprint 5 — Proactive Observer toast (file/terminal nudges) -->
    <ProactiveToast @adopt="onProactiveAdopt" />
  </div>
</template>