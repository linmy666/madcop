<script setup lang="ts">
// v3.0 — MadCop Tabstrip (Vue 3)
// Full translation of React TabBar.tsx (620 lines) — zero simplification.
// Includes: drag-and-drop reorder, context menu, running indicators,
// toolbar icon buttons, window controls, close-all confirmation dialog.

import {
  ref,
  computed,
  onMounted,
  onUnmounted,
  watch,
  nextTick,
  h,
  type VNode,
} from 'vue'
import { defineComponent } from 'vue'

// ─── Store imports ─────────────────────────────────────────────────
// From src/vue/components/layout/ → ../../stores/
import {
  useTabStore,
  SCHEDULED_TAB_ID,
  SETTINGS_TAB_ID,
  TERMINAL_TAB_PREFIX,
  TRACE_LIST_TAB_ID,
  TRACE_TAB_PREFIX,
  WORKBENCH_TAB_PREFIX,
  type Tab,
} from '../../stores/tabs'
import { useChatStore } from '../../stores/chatStore'
import { useSessionStore } from '../../stores/sessionStore'
import { useSettingsStore } from '../../stores/settingsStore'

// React zustand stores (workspacePanelStore, terminalPanelStore)
// imported from the React path — zustand works in Vue.
import { useWorkspacePanelStore } from '../../../stores/workspacePanelStore'
import { useTerminalPanelStore } from '../../../stores/terminalPanelStore'

// ─── i18n ──────────────────────────────────────────────────────────
import { translate, type Locale } from '../../../i18n'

// ─── Desktop host ──────────────────────────────────────────────────
import { getDesktopHost } from '../../../lib/desktopHost'

// ─── Shared types ──────────────────────────────────────────────────
import type { SessionListItem } from '../../../types/session'

// ─── Constants ─────────────────────────────────────────────────────
const TAB_WIDTH = 180
const DRAG_START_THRESHOLD = 4
const desktopHost = getDesktopHost()
const isDesktopRuntime = desktopHost.isDesktop
const isWindows = typeof navigator !== 'undefined' && /Win/.test(navigator.platform)
const showWindowControls = isWindows && desktopHost.capabilities?.windowControls

// ─── Helper functions (mirroring React TabBar) ─────────────────────
function isSessionTab(tab: Tab | null): boolean {
  if (!tab) return false
  const tabType = (tab as Partial<Tab>).type
  if (tabType === 'session') return true
  if (tabType) return false
  return isSessionTabId(tab.sessionId)
}

function isSessionTabId(tabId: string | null): boolean {
  if (!tabId) return false
  return (
    tabId !== SETTINGS_TAB_ID &&
    tabId !== SCHEDULED_TAB_ID &&
    tabId !== TRACE_LIST_TAB_ID &&
    !tabId.startsWith(TERMINAL_TAB_PREFIX) &&
    !tabId.startsWith(TRACE_TAB_PREFIX) &&
    !tabId.startsWith(WORKBENCH_TAB_PREFIX)
  )
}

// ─── Store access ──────────────────────────────────────────────────
const tabStore = useTabStore()
const chatStore = useChatStore()
const sessionStore = useSessionStore()
const settingsStore = useSettingsStore()

// ─── Local state ───────────────────────────────────────────────────
const scrollRef = ref<HTMLDivElement | null>(null)
const canScrollLeft = ref(false)
const canScrollRight = ref(false)
const contextMenu = ref<{ sessionId: string; x: number; y: number } | null>(null)
const pendingCloseRequest = ref<{ tabs: Tab[]; runningSessionIds: string[] } | null>(null)
const dragOverIndex = ref<number | null>(null)
const draggingSessionId = ref<string | null>(null)
const dragOffsetX = ref(0)
const dragIndexRef = ref<number | null>(null)
const pendingDragRef = ref<{ index: number; startX: number; startY: number } | null>(null)
const suppressClickRef = ref(false)
const tabRefs = ref(new Map<string, HTMLDivElement | null>())

// ─── Computed ──────────────────────────────────────────────────────
const tabs = computed(() => tabStore.tabs)
const activeTabId = computed(() => tabStore.activeTabId)

const sessionTabIds = computed(() =>
  tabs.value.filter((tab) => isSessionTab(tab)).map((tab) => tab.sessionId),
)

const activeChatSessionIds = computed(() =>
  sessionTabIds.value.filter(
    (sessionId) => chatStore.sessions[sessionId]?.chatState !== 'idle',
  ),
)

const activeTab = computed(() =>
  tabs.value.find((tab) => tab.sessionId === activeTabId.value) ?? null,
)

const isActiveSessionTab = computed(() =>
  isSessionTab(activeTab.value) || isSessionTabId(activeTabId.value),
)

const activeSession = computed(() =>
  activeTabId.value
    ? sessionStore.sessions.find((s: SessionListItem) => s.id === activeTabId.value)
    : undefined,
)

const openProjectPath = computed(() => {
  if (isActiveSessionTab.value && activeSession.value?.workDirExists !== false) {
    return activeSession.value?.workDir ?? null
  }
  return null
})

const isWorkbenchOpen = computed(() => {
  if (activeTabId.value && isActiveSessionTab.value) {
    return useWorkspacePanelStore.getState().isPanelOpen(activeTabId.value)
  }
  return false
})

const workbenchMode = computed(() => {
  if (activeTabId.value && isActiveSessionTab.value) {
    return useWorkspacePanelStore.getState().getMode(activeTabId.value)
  }
  return 'workspace'
})

const isWorkspacePanelOpen = computed(() =>
  isWorkbenchOpen.value && workbenchMode.value === 'workspace',
)

const isTerminalPanelOpen = computed(() => {
  if (activeTabId.value && isActiveSessionTab.value) {
    return useTerminalPanelStore.getState().isPanelOpen(activeTabId.value)
  }
  return false
})

// Running session IDs with stale-state guard (mirrors React useMemo)
const runningSessionIds = computed(() => {
  const ids = new Set<string>()
  for (const tab of tabs.value) {
    if (isSessionTab(tab) && tab.status === 'running') ids.add(tab.sessionId)
  }
  for (const sessionId of activeChatSessionIds.value) {
    ids.add(sessionId)
  }

  // v2.6.3.1: Stale-state guard
  const now = Date.now()
  for (const sessionId of [...ids]) {
    const session = sessionStore.sessions.find(
      (s: SessionListItem) => s.id === sessionId,
    )
    const lastModified = session?.modifiedAt
    if (lastModified) {
      const updated = new Date(lastModified).getTime()
      if (Number.isFinite(updated) && now - updated > 60_000) {
        ids.delete(sessionId)
      }
    }
  }

  return ids
})

// ─── Translation function ──────────────────────────────────────────
const locale = computed(() => settingsStore.locale ?? 'en')
function t(key: string, params?: Record<string, string | number>): string {
  return translate(locale.value as Locale, key as any, params)
}

// ─── Scroll state ──────────────────────────────────────────────────
function updateScrollState() {
  const el = scrollRef.value
  if (!el) return
  canScrollLeft.value = el.scrollLeft > 0
  canScrollRight.value = el.scrollLeft + el.clientWidth < el.scrollWidth - 1
}

let resizeObserver: ResizeObserver | null = null

function setupScrollObserver() {
  const el = scrollRef.value
  if (!el) return

  if (resizeObserver) resizeObserver.disconnect()

  updateScrollState()
  el.addEventListener('scroll', updateScrollState)

  resizeObserver = new ResizeObserver(updateScrollState)
  resizeObserver.observe(el)
}

// ─── Actions ───────────────────────────────────────────────────────
function setActiveTab(id: string) {
  tabStore.setActiveTab(id)
}

function closeTab(id: string) {
  tabStore.closeTab(id)
}

function scroll(direction: 'left' | 'right') {
  const el = scrollRef.value
  if (!el) return
  el.scrollBy({
    left: direction === 'left' ? -TAB_WIDTH : TAB_WIDTH,
    behavior: 'smooth',
  })
}

function closeTabWithCleanup(tab: Tab) {
  if (isSessionTab(tab)) {
    useWorkspacePanelStore.getState().clearSession(tab.sessionId)
    useTerminalPanelStore.getState().clearSession(tab.sessionId)
  }
  closeTab(tab.sessionId)
}

function getRunningSessionIds(targetTabs: Tab[]): string[] {
  const chatSessions = chatStore.sessions
  return targetTabs
    .filter((tab) => isSessionTab(tab))
    .filter((tab) => {
      const sessionState = chatSessions[tab.sessionId]
      return !!sessionState && sessionState.chatState !== 'idle'
    })
    .map((tab) => tab.sessionId)
}

function closeTabsWithPolicy(
  targetTabs: Tab[],
  runningSessionIds_: string[],
  stopRunning: boolean,
) {
  const runningSessionSet = new Set(runningSessionIds_)

  for (const tab of targetTabs) {
    if (isSessionTab(tab)) {
      const isRunning = runningSessionSet.has(tab.sessionId)
      if (isRunning && stopRunning) {
        chatStore.stopGeneration(tab.sessionId)
      }
      if (!isRunning || stopRunning) {
        chatStore.disconnectSession(tab.sessionId)
      }
    }
    closeTabWithCleanup(tab)
  }
}

function requestCloseTabs(targetTabs: Tab[]) {
  if (targetTabs.length === 0) return
  const runningSessionIds_ = getRunningSessionIds(targetTabs)

  if (runningSessionIds_.length > 0) {
    pendingCloseRequest.value = { tabs: targetTabs, runningSessionIds: runningSessionIds_ }
    return
  }

  closeTabsWithPolicy(targetTabs, [], false)
}

function handleClose(sessionId: string) {
  const tab = tabs.value.find((t) => t.sessionId === sessionId)
  if (!tab) return
  requestCloseTabs([tab])
}

function handleContextMenu(e: MouseEvent, sessionId: string) {
  e.preventDefault()
  contextMenu.value = { sessionId, x: e.clientX, y: e.clientY }
}

function handleCloseOthers(sessionId: string) {
  contextMenu.value = null
  const otherTabs = tabs.value.filter((t) => t.sessionId !== sessionId)
  requestCloseTabs(otherTabs)
}

function handleCloseLeft(sessionId: string) {
  contextMenu.value = null
  const idx = tabs.value.findIndex((t) => t.sessionId === sessionId)
  const leftTabs = tabs.value.slice(0, idx)
  requestCloseTabs(leftTabs)
}

function handleCloseRight(sessionId: string) {
  contextMenu.value = null
  const idx = tabs.value.findIndex((t) => t.sessionId === sessionId)
  const rightTabs = tabs.value.slice(idx + 1)
  requestCloseTabs(rightTabs)
}

function handleCloseAll() {
  contextMenu.value = null
  requestCloseTabs(tabs.value)
}

// ─── Drag & Drop ───────────────────────────────────────────────────
function getTargetIndexFromClientX(clientX: number): number | null {
  for (let index = 0; index < tabs.value.length; index++) {
    const tab = tabs.value[index]
    if (!tab) continue
    const el = tabRefs.value.get(tab.sessionId)
    if (!el) continue
    const rect = el.getBoundingClientRect()
    if (clientX < rect.left + rect.width / 2) return index
  }
  return tabs.value.length > 0 ? tabs.value.length - 1 : null
}

function finalizeDrag(targetIndex: number | null) {
  if (
    dragIndexRef.value !== null &&
    targetIndex !== null &&
    dragIndexRef.value !== targetIndex
  ) {
    tabStore.moveTab(dragIndexRef.value, targetIndex)
  }
  dragIndexRef.value = null
  pendingDragRef.value = null
  draggingSessionId.value = null
  dragOffsetX.value = 0
  dragOverIndex.value = null
}

function handlePointerMove(event: MouseEvent) {
  const pending = pendingDragRef.value
  if (!pending) return

  const deltaX = Math.abs(event.clientX - pending.startX)
  const deltaY = Math.abs(event.clientY - pending.startY)

  if (dragIndexRef.value === null) {
    if (Math.max(deltaX, deltaY) < DRAG_START_THRESHOLD) return
    dragIndexRef.value = pending.index
    suppressClickRef.value = true
    draggingSessionId.value = tabs.value[pending.index]?.sessionId ?? null
  }

  dragOffsetX.value = event.clientX - pending.startX

  const targetIndex = getTargetIndexFromClientX(event.clientX)
  if (targetIndex === null || targetIndex === dragIndexRef.value) {
    dragOverIndex.value = null
    return
  }

  dragOverIndex.value = targetIndex
}

function handlePointerUp() {
  finalizeDrag(dragOverIndex.value)
}

function handleTabMouseDown(event: MouseEvent, index: number) {
  if ((event as any).button !== 0) return
  pendingDragRef.value = {
    index,
    startX: event.clientX,
    startY: event.clientY,
  }
}

function handleTabClick(sessionId: string) {
  if (suppressClickRef.value) {
    suppressClickRef.value = false
    return
  }
  setActiveTab(sessionId)
}

// ─── Lifecycle ─────────────────────────────────────────────────────
onMounted(() => {
  window.addEventListener('mousemove', handlePointerMove)
  window.addEventListener('mouseup', handlePointerUp)

  // Close context menu on any click
  document.addEventListener('click', () => {
    contextMenu.value = null
  })

  setupScrollObserver()
})

onUnmounted(() => {
  window.removeEventListener('mousemove', handlePointerMove)
  window.removeEventListener('mouseup', handlePointerUp)
  if (resizeObserver) resizeObserver.disconnect()
})

// Re-setup scroll observer when tabs change
watch(
  () => tabs.value.length,
  () => {
    nextTick(() => {
      setupScrollObserver()
      // Scroll active tab into view
      if (activeTabId.value) {
        const activeTabEl = tabRefs.value.get(activeTabId.value)
        if (activeTabEl) {
          activeTabEl.scrollIntoView({
            block: 'nearest',
            inline: 'nearest',
            behavior: 'smooth',
          })
          window.requestAnimationFrame(updateScrollState)
        }
      }
    })
  },
)

// Watch for dragging cursor changes
watch(draggingSessionId, (id) => {
  if (id) {
    document.body.style.cursor = 'grabbing'
  } else {
    document.body.style.cursor = ''
  }
})

// ─── Terminal toggle action ────────────────────────────────────────
function handleTerminalToggle() {
  if (activeTabId.value && isActiveSessionTab.value) {
    useTerminalPanelStore.getState().togglePanel(activeTabId.value)
    return
  }
  useTabStore.getState().openTerminalTab()
}

// ─── Workspace toggle action ───────────────────────────────────────
function handleWorkspaceToggle() {
  if (!isActiveSessionTab.value || !activeTabId.value) return
  const workbench = useWorkspacePanelStore.getState()
  if (workbench.isPanelOpen(activeTabId.value) && workbench.getMode(activeTabId.value) === 'workspace') {
    workbench.closePanel(activeTabId.value)
  } else {
    workbench.setMode(activeTabId.value, 'workspace')
    workbench.openPanel(activeTabId.value)
  }
}

// ─── Child Component: TabItem ──────────────────────────────────────
const TabItem = defineComponent({
  name: 'TabItem',
  props: {
    tab: { type: Object as () => Tab, required: true },
    isRunning: { type: Boolean, default: false },
    isActive: { type: Boolean, default: false },
    isDragOver: { type: Boolean, default: false },
    isDragging: { type: Boolean, default: false },
    dragOffsetX: { type: Number, default: 0 },
    runningLabel: { type: String, default: '' },
  },
  emits: ['click', 'close', 'contextmenu', 'moused'],
  setup(props, { emit }) {
    return () => {
      const cls = [
        'tab-bar-interactive group relative flex min-h-11 flex-shrink-0 items-center gap-1.5 px-3',
        props.isDragging ? 'z-20 cursor-grabbing' : 'cursor-grab',
        'transition-[background-color,box-shadow,opacity,transform] duration-150 ease-out',
        props.isActive
          ? 'bg-[var(--color-surface)] shadow-[inset_0_-4px_0_var(--color-brand)] ring-2 ring-[var(--color-brand)]/30'
          : 'bg-transparent hover:bg-[var(--color-surface-hover)]',
        props.isDragging
          ? 'opacity-95 shadow-[0_10px_24px_rgba(0,0,0,0.18)] ring-1 ring-[var(--color-border)]'
          : '',
        props.isDragOver
          ? 'before:absolute before:left-0 before:top-[4px] before:bottom-[4px] before:w-[3px] before:bg-[var(--color-brand)] before:rounded-full before:shadow-[0_0_0_1px_rgba(255,255,255,0.25)]'
          : '',
      ].filter(Boolean).join(' ')

      const style: Record<string, any> = {
        width: TAB_WIDTH,
        maxWidth: TAB_WIDTH,
      }
      if (props.isDragging) {
        style.transform = `translateX(${props.dragOffsetX}px) scale(1.02)`
      }

      const titleCls = [
        'flex-1 truncate text-xs',
        props.isActive
          ? 'text-[var(--color-text-primary)] font-medium'
          : 'text-[var(--color-text-secondary)]',
      ].join(' ')

      const children: VNode[] = []

      // Running indicator
      if (props.tab.type === 'session' && props.isRunning) {
        children.push(
          h('span', {
            class: 'h-1.5 w-1.5 flex-shrink-0 rounded-full bg-[var(--color-success)] animate-pulse',
            'aria-label': props.runningLabel,
            title: props.runningLabel,
          }),
        )
      }

      // Error indicator
      if (props.tab.type === 'session' && props.tab.status === 'error') {
        children.push(
          h('span', {
            class: 'w-1.5 h-1.5 rounded-full bg-[var(--color-error)] flex-shrink-0',
          }),
        )
      }

      // Settings icon
      if (props.tab.type === 'settings') {
        children.push(
          h('span', {
            class: 'material-symbols-outlined text-[14px] flex-shrink-0 text-[var(--color-text-tertiary)]',
          }, 'settings'),
        )
      }

      // Scheduled icon
      if (props.tab.type === 'scheduled') {
        children.push(
          h('span', {
            class: 'material-symbols-outlined text-[14px] flex-shrink-0 text-[var(--color-text-tertiary)]',
          }, 'schedule'),
        )
      }

      // Terminal icon
      if (props.tab.type === 'terminal') {
        children.push(
          h('span', {
            class: 'material-symbols-outlined text-[14px] flex-shrink-0 text-[var(--color-text-tertiary)]',
          }, 'terminal'),
        )
      }

      // Workbench icon
      if (props.tab.type === 'workbench') {
        children.push(
          h('span', {
            class: 'material-symbols-outlined text-[14px] flex-shrink-0 text-[var(--color-text-tertiary)]',
          }, 'view_sidebar'),
        )
      }

      // Title
      children.push(
        h('span', { class: titleCls }, props.tab.title || 'Untitled'),
      )

      // Close button
      children.push(
        h(
          'button',
          {
            type: 'button',
            'aria-label': `Close ${props.tab.title || 'Untitled'}`,
            class:
              'flex-shrink-0 -mr-0.5 inline-flex h-3 w-3 items-center justify-center bg-transparent p-0 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-[opacity,color] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] focus-visible:outline-none',
            onMouseDown: (e: MouseEvent) => e.stopPropagation(),
            onClick: (e: MouseEvent) => {
              e.stopPropagation()
              emit('close')
            },
          },
          [
            h('span', { class: 'material-symbols-outlined text-[11px] leading-none' }, 'close'),
          ],
        ),
      )

      return h(
        'div',
        {
          'data-dragging': props.isDragging ? 'true' : 'false',
          class: cls,
          style,
          onClick: () => emit('click'),
          onMouseDown: (e: MouseEvent) => emit('moused', e),
          onContextMenu: (e: MouseEvent) => emit('contextmenu', e),
        },
        children,
      )
    }
  },
})

// ─── Child Component: ToolbarIconButton ────────────────────────────
const ToolbarIconButton = defineComponent({
  name: 'ToolbarIconButton',
  props: {
    icon: { type: String, required: true },
    label: { type: String, required: true },
    active: { type: Boolean, default: false },
  },
  emits: ['click'],
  setup(props, { emit }) {
    return () => {
      const cls = [
        'inline-flex h-8 w-8 items-center justify-center rounded-[10px] transition-colors focus-visible:outlinenone focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)]',
        props.active
          ? 'bg-[var(--color-surface-hover)] text-[var(--color-text-primary)]'
          : 'text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]',
      ].join(' ')

      return h(
        'button',
        {
          type: 'button',
          'aria-label': props.label,
          title: props.label,
          'data-active': props.active ? 'true' : 'false',
          class: cls,
          onClick: () => emit('click'),
          innerHTML: props.icon,
        },
      )
    }
  },
})

// ─── Child Component: WindowControls ───────────────────────────────
const WindowControls = defineComponent({
  name: 'WindowControls',
  setup() {
    const maximized = ref(false)
    const win = ref<any>(null)

    const runWindowAction = (action: () => Promise<void>) => {
      void action().catch((error: any) => {
        console.error('Window control action failed', error)
      })
    }

    if (showWindowControls) {
      win.value = getDesktopHost().window
      void getDesktopHost().window
        .isMaximized()
        .then((next: boolean) => {
          maximized.value = next
        })
        .catch(() => {})
    }

    return () => {
      if (!showWindowControls || !win.value) return null

      return h(
        'div',
        { class: 'flex items-stretch flex-shrink-0 -my-px' },
        [
          // Minimize
          h(
            'button',
            {
              onClick: () => runWindowAction(() => win.value.minimize()),
              'aria-label': 'Minimize window',
              class: 'w-[46px] h-full flex items-center justify-center text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] transition-colors',
            },
            [
              h(
                'svg',
                { width: '10', height: '1', viewBox: '0 0 10 1' },
                [h('rect', { width: '10', height: '1', fill: 'currentColor' })],
              ),
            ],
          ),
          // Maximize / Restore
          h(
            'button',
            {
              onClick: () => runWindowAction(() => win.value.toggleMaximize()),
              'aria-label': maximized.value ? 'Restore window' : 'Maximize window',
              class: 'w-[46px] h-full flex items-center justify-center text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] transition-colors',
            },
            maximized.value
              ? [
                  h(
                    'svg',
                    {
                      width: '10',
                      height: '10',
                      viewBox: '0 0 10 10',
                      fill: 'none',
                      stroke: 'currentColor',
                      'stroke-width': '1',
                    },
                    [
                      h('rect', { x: '0', y: '3', width: '7', height: '7' }),
                      h('polyline', { points: '3,3 3,0 10,0 10,7 7,7' }),
                    ],
                  ),
                ]
              : [
                  h(
                    'svg',
                    {
                      width: '10',
                      height: '10',
                      viewBox: '0 0 10 10',
                      fill: 'none',
                      stroke: 'currentColor',
                      'stroke-width': '1',
                    },
                    [h('rect', { x: '0.5', y: '0.5', width: '9', height: '9' })],
                  ),
                ],
          ),
          // Close
          h(
            'button',
            {
              onClick: () => runWindowAction(() => win.value.close()),
              'aria-label': 'Close window',
              class:
                'w-[46px] h-full flex items-center justify-center text-[var(--color-text-secondary)] hover:bg-[var(--color-window-close-hover)] hover:text-white transition-colors',
            },
            [
              h(
                'svg',
                {
                  width: '10',
                  height: '10',
                  viewBox: '0 0 10 10',
                  fill: 'none',
                  stroke: 'currentColor',
                  'stroke-width': '1.2',
                },
                [
                  h('line', { x1: '0', y1: '0', x2: '10', y2: '10' }),
                  h('line', { x1: '10', y1: '0', x2: '0', y2: '10' }),
                ],
              ),
            ],
          ),
        ],
      )
    }
  },
})

// ─── Child Component: OpenProjectMenu ──────────────────────────────
const OpenProjectMenu = defineComponent({
  name: 'OpenProjectMenu',
  props: {
    path: { type: String as () => string | null, default: null },
  },
  setup(props) {
    const menuOpen = ref(false)

    return () => {
      return h(
        'div',
        { class: 'relative' },
        [
          h(
            'button',
            {
              type: 'button',
              'aria-label': 'Open project menu',
              title: 'Open project',
              class:
                'inline-flex h-8 w-8 items-center justify-center rounded-[10px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)] text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]',
              onClick: () => { menuOpen.value = !menuOpen.value },
              innerHTML:
                '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11l2-6h2l2.5 7L13 14l3-8 2 10h6" /></svg>',
            },
          ),
          menuOpen.value
            ? h(
                'div',
                {
                  class:
                    'absolute right-0 top-10 z-50 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-md)] py-1 min-w-[160px] shadow-lg',
                },
                [
                  h(
                    'button',
                    {
                      class:
                        'w-full px-3 py-1.5 text-xs text-left text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)]',
                      onClick: () => {
                        menuOpen.value = false
                      },
                    },
                    'Open Containing Folder',
                  ),
                ],
              )
            : null,
        ],
      )
    }
  },
})
</script>

<template>
  <div
    data-testid="tab-bar"
    :data-desktop-drag-region="isDesktopRuntime ? true : undefined"
    class="flex min-h-11 items-stretch bg-[var(--color-surface-container)] select-none border-b border-[var(--color-border)]"
  >
    <!-- Left scroll button -->
    <button
      v-if="canScrollLeft"
      @click="scroll('left')"
      class="flex h-11 w-7 flex-shrink-0 items-center justify-center text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
    >
      <span class="material-symbols-outlined text-[16px]">chevron_left</span>
    </button>

    <!-- Scrollable tab region -->
    <div
      ref="scrollRef"
      data-testid="tab-bar-scroll-region"
      :data-desktop-drag-region="isDesktopRuntime ? true : undefined"
      class="flex-1 flex items-stretch overflow-x-hidden"
      @dragover.prevent
    >
      <TabItem
        v-for="(tab, index) in tabs"
        :key="tab.sessionId"
        :ref="(el: any) => {
          if (el && tabRefs) {
            tabRefs.set(tab.sessionId, el as HTMLDivElement)
          }
        }"
        :tab="tab"
        :is-running="runningSessionIds.has(tab.sessionId)"
        :is-active="tab.sessionId === activeTabId"
        :is-drag-over="dragOverIndex === index"
        :is-dragging="tab.sessionId === draggingSessionId"
        :drag-offset-x="tab.sessionId === draggingSessionId ? dragOffsetX : 0"
        :running-label="t('tabs.sessionRunning')"
        @click="handleTabClick(tab.sessionId)"
        @close="handleClose(tab.sessionId)"
        @contextmenu="(e: MouseEvent) => handleContextMenu(e, tab.sessionId)"
        @moused="(e: MouseEvent) => handleTabMouseDown(e, index)"
      />
    </div>

    <!-- Right-side toolbar -->
    <div class="flex shrink-0 items-center gap-1 border-l border-[var(--color-border)]/70 px-2">
      <!-- Open Project Menu (desktop + session tab) -->
      <OpenProjectMenu
        v-if="isDesktopRuntime && isActiveSessionTab"
        :path="openProjectPath"
      />

      <!-- Terminal button -->
      <ToolbarIconButton
        :icon="`<svg xmlns='http://www.w3.org/2000/svg' width='17' height='17' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.9' stroke-linecap='round' stroke-linejoin='round'><rect x='2' y='3' width='20' height='18' rx='2' /><path d='m8 10 4-4 4 4' /><path d='M12 12v8' /></svg>`"
        :label="t('tabs.openTerminal')"
        :active="isTerminalPanelOpen"
        @click="handleTerminalToggle"
      />

      <!-- Workspace button (session tab only) -->
      <ToolbarIconButton
        v-if="isActiveSessionTab && activeTabId"
        :icon="isWorkspacePanelOpen
          ? `<svg xmlns='http://www.w3.org/2000/svg' width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.9' stroke-linecap='round' stroke-linejoin='round'><path d='M3 11l2-6h2l2.5 7L13 14l3-8 2 10h6' /></svg>`
          : `<svg xmlns='http://www.w3.org/2000/svg' width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.9' stroke-linecap='round' stroke-linejoin='round'><path d='M3 11l2-6h2l2.5 7L13 14l3-8 2 10h6' /></svg>`"
        :label="isWorkspacePanelOpen ? t('tabs.hideWorkspace') : t('tabs.showWorkspace')"
        :active="isWorkspacePanelOpen"
        @click="handleWorkspaceToggle"
      />
    </div>

    <!-- Desktop drag gutter -->
    <div
      v-if="isDesktopRuntime"
      data-testid="tab-bar-drag-gutter"
      data-desktop-drag-region
      aria-hidden="true"
      :class="`min-h-11 flex-shrink-0 ${showWindowControls ? 'w-3' : 'w-4'}`"
    />

    <!-- Right scroll button -->
    <button
      v-if="canScrollRight"
      @click="scroll('right')"
      class="flex h-11 w-7 flex-shrink-0 items-center justify-center text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
    >
      <span class="material-symbols-outlined text-[16px]">chevron_right</span>
    </button>

    <!-- Window Controls (desktop only) -->
    <WindowControls v-if="showWindowControls" />

    <!-- Context Menu (portaled to body) -->
    <Teleport to="body">
      <div
        v-if="contextMenu"
        class="fixed z-50 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-md)] py-1 min-w-[160px]"
        :style="{
          left: contextMenu.x + 'px',
          top: contextMenu.y + 'px',
          boxShadow: 'var(--shadow-dropdown)',
        }"
      >
        <button
          @click="() => { handleClose(contextMenu.sessionId); contextMenu = null }"
          class="w-full px-3 py-1.5 text-xs text-left text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)]"
        >
          {{ t('tabs.close') }}
        </button>
        <button
          @click="handleCloseOthers(contextMenu.sessionId)"
          class="w-full px-3 py-1.5 text-xs text-left text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)]"
        >
          {{ t('tabs.closeOthers') }}
        </button>
        <button
          @click="handleCloseLeft(contextMenu.sessionId)"
          class="w-full px-3 py-1.5 text-xs text-left text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)]"
        >
          {{ t('tabs.closeLeft') }}
        </button>
        <button
          @click="handleCloseRight(contextMenu.sessionId)"
          class="w-full px-3 py-1.5 text-xs text-left text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)]"
        >
          {{ t('tabs.closeRight') }}
        </button>
        <div class="my-1 border-t border-[var(--color-border)]" />
        <button
          @click="handleCloseAll"
          class="w-full px-3 py-1.5 text-xs text-left text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)]"
        >
          {{ t('tabs.closeAll') }}
        </button>
      </div>
    </Teleport>

    <!-- Close Confirmation Dialog (ActionDialog) -->
    <Teleport to="body">
      <div
        v-if="pendingCloseRequest !== null"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      >
        <div
          class="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-md)] shadow-lg p-6 max-w-sm w-full"
        >
          <h3 class="text-sm font-medium text-[var(--color-text-primary)] mb-2">
            {{
              pendingCloseRequest && pendingCloseRequest.runningSessionIds.length > 1
                ? t('tabs.closeAllConfirmTitle')
                : t('tabs.closeConfirmTitle')
            }}
          </h3>
          <p class="text-sm leading-6 text-[var(--color-text-secondary)] mb-4">
            {{
              pendingCloseRequest && pendingCloseRequest.runningSessionIds.length > 1
                ? t('tabs.closeAllConfirmMessage', { count: pendingCloseRequest.runningSessionIds.length })
                : t('tabs.closeConfirmMessage')
            }}
          </p>
          <div class="flex justify-end gap-2">
            <button
              @click="() => { pendingCloseRequest = null }"
              class="px-3 py-1.5 text-xs rounded-[8px] text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)] transition-colors"
            >
              {{ t('common.cancel') }}
            </button>
            <button
              @click="() => {
                if (!pendingCloseRequest) return
                closeTabsWithPolicy(pendingCloseRequest.tabs, pendingCloseRequest.runningSessionIds, false)
                pendingCloseRequest = null
              }"
              class="px-3 py-1.5 text-xs rounded-[8px] text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)] transition-colors"
            >
              {{ t('tabs.closeConfirmKeep') }}
            </button>
            <button
              @click="() => {
                if (!pendingCloseRequest) return
                closeTabsWithPolicy(pendingCloseRequest.tabs, pendingCloseRequest.runningSessionIds, true)
                pendingCloseRequest = null
              }"
              class="px-3 py-1.5 text-xs rounded-[8px] text-red-500 hover:bg-red-500/10 transition-colors"
            >
              {{
                pendingCloseRequest && pendingCloseRequest.runningSessionIds.length > 1
                  ? t('tabs.closeAllConfirmStop')
                  : t('tabs.closeConfirmStop')
              }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.tab-bar-interactive {
  position: relative;
}
</style>
