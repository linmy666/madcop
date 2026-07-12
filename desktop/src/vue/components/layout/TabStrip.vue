<script setup lang="ts">
/**
 * TabStrip — multi-session tab management bar.
 * Re-implements the React TabBar's core UX in Vue 3:
 *   - Horizontal tab strip with close buttons
 *   - Active tab highlight
 *   - Green dot on running sessions
 *   - Drag-to-reorder (basic)
 *   - Context menu: close / close others / close all
 *   - "New chat" button at the end
 */

import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useTabStore, type Tab } from '../../stores/tabStore'
import { useChatStore } from '../../stores/chatStore'
import { useSessionStore } from '../../stores/sessionStore'
import { useTranslation } from '../../i18n'

const tabStore = useTabStore()
const chatStore = useChatStore()
const sessionStore = useSessionStore()
const t = useTranslation()

// ─── Computed ──────────────────────────────────────────────────────────

const sessions = computed(() => sessionStore.sessions ?? [])

function tabTitle(tab: Tab): string {
  // Prefer the sessionStore title (set by chatStore after the first
  // message). Fallback to the chatStore's per-session title which is
  // derived from the first user message but may not be in sessionStore
  // for older sessions. Final fallback is the tab's own title.
  if (tab.title && tab.title !== 'New Session' && tab.title !== '新对话') return tab.title
  const session = sessions.value.find((s: any) => s.id === tab.sessionId)
  if (session?.title && session.title !== '新对话') return session.title
  const chatTitle = (chatStore as any).sessions?.[tab.sessionId]?.title
  if (chatTitle && chatTitle !== '新对话' && chatTitle !== 'New Session') return chatTitle
  return tab.title || '新对话'
}

function tabSubtitle(tab: Tab): string {
  if (tab.type === 'session') return ''
  if (tab.type === 'settings') return '设置'
  if (tab.type === 'workflows') return 'Agent'
  if (tab.type === 'knowledge') return '知识库'
  return tab.type
}

function isSessionRunning(tab: Tab): boolean {
  if (tab.type !== 'session') return false
  const state = chatStore.sessions[tab.sessionId]?.chatState
  return state !== 'idle' && state !== undefined
}

function isModified(tab: Tab): boolean {
  // Session tabs don't have "modified" state
  return false
}

// ─── Visibility ────────────────────────────────────────────────────────

const visible = computed(() => tabStore.tabs.length > 0)
const allTabs = computed(() => tabStore.tabs)

// ─── Tab actions ───────────────────────────────────────────────────────

function selectTab(tab: Tab) {
  tabStore.setActiveTab(tab.sessionId)
}

function closeTab(tab: Tab, e: MouseEvent) {
  e.stopPropagation()
  tabStore.closeTab(tab.sessionId)
  // Also disconnect the session
  chatStore.disconnectSession(tab.sessionId)
  // Sync: remove from sidebar workspace list so closing a tab
  // also removes its entry from the left panel.
  if (!tab.sessionId.startsWith('__')) {
    void sessionStore.deleteSession(tab.sessionId)
  }
}

function newSession() {
  // v3.0: use the session store's createSession which now also
  // asks the backend to create a session, returning a backend
  // id that's needed for history loading.
  void sessionStore.createSession(
    localStorage.getItem('madcop_workspace_dir') || undefined
  ).then((id) => {
    tabStore.openTab(id, '新对话')
    chatStore.connectToSession(id)
  })
}

// ─── Drag reorder ──────────────────────────────────────────────────────

const dragTabId = ref<string | null>(null)
const dragOverTabId = ref<string | null>(null)

function onDragStart(e: DragEvent, tab: Tab) {
  dragTabId.value = tab.sessionId
  e.dataTransfer?.setData('text/plain', tab.sessionId)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}

function onDragOver(e: DragEvent, tab: Tab) {
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
  dragOverTabId.value = tab.sessionId
}

function onDrop(e: DragEvent, targetTab: Tab) {
  e.preventDefault()
  const fromId = e.dataTransfer?.getData('text/plain')
  const toId = targetTab.sessionId
  if (!fromId || fromId === toId) {
    dragTabId.value = null
    dragOverTabId.value = null
    return
  }
  const fromIdx = tabStore.tabs.findIndex((t) => t.sessionId === fromId)
  const toIdx = tabStore.tabs.findIndex((t) => t.sessionId === toId)
  if (fromIdx >= 0 && toIdx >= 0) tabStore.moveTab(fromIdx, toIdx)
  dragTabId.value = null
  dragOverTabId.value = null
}

function onDragEnd() {
  dragTabId.value = null
  dragOverTabId.value = null
}

// ─── Context menu ──────────────────────────────────────────────────────

const contextMenu = ref<{ x: number; y: number; tab: Tab } | null>(null)

function onContextMenu(e: MouseEvent, tab: Tab) {
  e.preventDefault()
  contextMenu.value = { x: e.clientX, y: e.clientY, tab }
}

function closeOthers(tab: Tab) {
  const others = tabStore.tabs.filter((t) => t.sessionId !== tab.sessionId)
  for (const t of others) {
    tabStore.closeTab(t.sessionId)
    chatStore.disconnectSession(t.sessionId)
    if (!t.sessionId.startsWith('__')) void sessionStore.deleteSession(t.sessionId)
  }
  contextMenu.value = null
}

function closeAll() {
  const ids = tabStore.tabs.map((t) => t.sessionId)
  for (const id of ids) {
    tabStore.closeTab(id)
    chatStore.disconnectSession(id)
    if (!id.startsWith('__')) void sessionStore.deleteSession(id)
  }
  contextMenu.value = null
}

function closeContextMenu() {
  contextMenu.value = null
}

onMounted(() => window.addEventListener('click', closeContextMenu))
onBeforeUnmount(() => window.removeEventListener('click', closeContextMenu))
</script>

<template>
  <div
    v-if="visible"
    class="tab-strip w-full"
    style="width: 100%; flex-shrink: 0; background: var(--color-surface);"
    @dragover.prevent
  >
    <!-- Tab list -->
    <div class="tab-list">
      <div
        v-for="tab in allTabs"
        :key="tab.sessionId"
        :draggable="true"
        @dragstart="onDragStart($event, tab)"
        @dragover="onDragOver($event, tab)"
        @drop="onDrop($event, tab)"
        @dragend="onDragEnd"
        @click="selectTab(tab)"
        @contextmenu="onContextMenu($event, tab)"
        :class="[
          'tab-item',
          tabStore.activeTabId === tab.sessionId ? 'tab-item--active' : '',
          isSessionRunning(tab) ? 'tab-item--running' : '',
          dragOverTabId === tab.sessionId ? 'tab-item--drag-over' : '',
        ]"
      >
        <!-- Session indicator dot -->
        <span
          v-if="isSessionRunning(tab)"
          class="tab-dot"
        ></span>

        <!-- Icon for special tabs -->
        <svg
          v-if="tab.type === 'settings'"
          class="tab-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"
        ><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>

        <!-- Tab title -->
        <span class="tab-title">{{ tabTitle(tab) }}</span>

        <!-- Modified indicator -->
        <span v-if="isModified(tab)" class="tab-modified">•</span>

        <!-- Close button -->
        <button
          class="tab-close"
          @click="closeTab(tab, $event)"
          :aria-label="`关闭 ${tabTitle(tab)}`"
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>

      <!-- New session button -->
      <button class="tab-new" @click="newSession" title="新对话">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
      </button>
    </div>

    <!-- Context menu -->
    <Teleport to="body">
      <div
        v-if="contextMenu"
        class="tab-context-menu"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click.stop
      >
        <button class="tab-context-item" @click="contextMenu = null; tabStore.closeTab(contextMenu.tab.sessionId)">关闭此标签</button>
        <button class="tab-context-item" @click="closeOthers(contextMenu.tab)">关闭其他标签</button>
        <button class="tab-context-item" @click="closeAll">关闭全部</button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.tab-strip {
  display: flex;
  align-items: center;
  height: 36px;
  width: 100%;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
  overflow: hidden;
}

.tab-list {
  display: flex;
  align-items: center;
  gap: 0;
  height: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  flex: 1 1 auto;
  min-width: 0;
  scrollbar-width: none;
}

.tab-item {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 100%;
  padding: 0 10px;
  font-size: 12px;
  color: var(--color-text-secondary);
  cursor: pointer;
  border-right: 1px solid var(--color-border-separator);
  white-space: nowrap;
  user-select: none;
  transition: background 0.1s, color 0.1s;
  min-width: 0;
  flex-shrink: 0;
  max-width: 200px;
}

.tab-item:hover {
  background: var(--color-surface-container);
  color: var(--color-text-primary);
}

.tab-item--active {
  background: var(--color-surface-container-lowest);
  color: var(--color-text-primary);
  border-bottom: 2px solid var(--color-brand);
}

.tab-item--running .tab-dot {
  display: inline-block;
}

.tab-item--drag-over {
  border-left: 2px solid var(--color-brand);
}

.tab-dot {
  display: none;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-success);
  flex-shrink: 0;
}

.tab-icon {
  flex-shrink: 0;
  opacity: 0.6;
}

.tab-title {
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
  font-size: 12px;
  font-weight: 500;
}

.tab-modified {
  color: var(--color-text-tertiary);
  font-size: 16px;
  line-height: 1;
}

.tab-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 3px;
  background: transparent;
  border: none;
  color: var(--color-text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.1s, background 0.1s;
  flex-shrink: 0;
  padding: 0;
}

.tab-item:hover .tab-close {
  opacity: 0.6;
}

.tab-close:hover {
  opacity: 1 !important;
  background: var(--color-surface-container);
}

.tab-new {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 0 12px;
  background: transparent;
  border: none;
  border-right: 1px solid var(--color-border-separator);
  color: var(--color-text-tertiary);
  cursor: pointer;
  flex-shrink: 0;
  transition: color 0.1s;
}

.tab-new:hover {
  color: var(--color-text-primary);
}

/* Context menu */
.tab-context-menu {
  position: fixed;
  z-index: 9999;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  padding: 4px;
  min-width: 140px;
}

.tab-context-item {
  display: block;
  width: 100%;
  padding: 7px 12px;
  background: transparent;
  border: none;
  color: var(--color-text-primary);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  border-radius: 3px;
}

.tab-context-item:hover {
  background: var(--color-surface-container);
}
</style>