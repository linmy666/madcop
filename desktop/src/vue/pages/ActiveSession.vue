<!--
  v3.0 — ActiveSession (Vue 3 SFC)
  Full translation of src/pages/ActiveSession.tsx (614 lines).
  Active session page — shows current chat session with active tab,
  workspace panel, terminal panel, session header, and task bar.
-->
<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, type Ref } from 'vue'
import { useTranslation } from '../i18n'
import {
  SCHEDULED_TAB_ID,
  SETTINGS_TAB_ID,
  TERMINAL_TAB_PREFIX,
  TRACE_TAB_PREFIX,
  WORKBENCH_TAB_PREFIX,
  useTabStore,
  type TabType,
} from '../stores/tabs'
import { useSessionStore } from '../stores/sessionStore'
import { useChatStore } from '../stores/chatStore'
import { useCLITaskStore } from '../stores/cliTaskStore'
import { useTeamStore } from '../stores/teamStore'
import { useWorkspacePanelStore } from '../stores/workspacePanelStore'
import {
  TERMINAL_PANEL_DEFAULT_HEIGHT,
  TERMINAL_PANEL_MAX_HEIGHT,
  TERMINAL_PANEL_MIN_HEIGHT,
  useTerminalPanelStore,
} from '../stores/terminalPanelStore'
import MessageList from '../components/chat/MessageList.vue'
import ChatInput from '../components/chat/ChatInput.vue'
import DirectChatButton from '../components/chat/DirectChatButton.vue'
import ComputerUsePermissionModal from '../components/chat/ComputerUsePermissionModal.vue'
import ClarificationPanel from '../components/chat/ClarificationPanel.vue'
import SessionTaskBar from '../components/chat/SessionTaskBar.vue'
import MadCopLoader from '../components/common/MadCopLoader.vue'
import WorkbenchPanel from '../components/workbench/WorkbenchPanel.vue'
import TeamStatusBar from '../components/teams/TeamStatusBar.vue'
import TerminalSettings from './TerminalSettings.vue'
import type { ChatPermission } from '~/stores/permissionStore'
import type { SessionListItem } from '../types/session'
import type { ActiveGoalState } from '../types/chat'
import { useMobileViewport } from '../hooks/useMobileViewport'
import { isDesktopRuntime } from '../lib/desktopRuntime'
import { formatTokenCount } from '../lib/formatTokenCount'

// ── Constants ────────────────────────────────────────────────────────────────
const TASK_POLL_INTERVAL_MS = 1000
const WORKSPACE_RESIZE_STEP = 32
const TERMINAL_RESIZE_STEP = 24
const CHAT_COLUMN_WITH_WORKSPACE_CLASS =
  'min-w-[320px] flex-1 border-r border-[var(--color-border)] bg-[var(--color-surface)]'

// ── Helper function (pure) ───────────────────────────────────────────────────
function isSessionTabState(activeTabId: string | null, activeTabType: TabType | null | undefined): boolean {
  if (!activeTabId) return false
  if (activeTabType === 'session') return true
  if (activeTabType) return false
  return (
    activeTabId !== SETTINGS_TAB_ID &&
    activeTabId !== SCHEDULED_TAB_ID &&
    !activeTabId.startsWith(TERMINAL_TAB_PREFIX) &&
    !activeTabId.startsWith(TRACE_TAB_PREFIX) &&
    !activeTabId.startsWith(WORKBENCH_TAB_PREFIX)
  )
}

function getSessionTerminalCwd(session: SessionListItem | undefined): string | undefined {
  if (!session) return undefined
  if (session.workDir && session.workDirExists !== false) return session.workDir
  return session.projectPath || undefined
}

// ── Sub-component: ActiveGoalStrip ───────────────────────────────────────────
// Rendered inline via template below for Vue 3 SFC compatibility

// ── Sub-component: WorkspaceResizeHandle ─────────────────────────────────────
// Rendered inline via template below

// ── Sub-component: TerminalResizeHandle ──────────────────────────────────────
// Rendered inline via template below

// ── Stores ───────────────────────────────────────────────────────────────────
const tabStore = useTabStore()
const sessionStore = useSessionStore()
const chatStore = useChatStore()
const cliTaskStore = useCLITaskStore()
const teamStore = useTeamStore()
const workspacePanelStore = useWorkspacePanelStore()
const terminalPanelStore = useTerminalPanelStore()

const t = useTranslation()

// ── Reactive state ───────────────────────────────────────────────────────────
const isMobileLayout = computed(() => useMobileViewport() && !isDesktopRuntime())

const activeTabId = computed(() => tabStore.activeTabId)
const activeTabType = computed<TabType | null>(() => {
  if (!activeTabId.value) return null
  return tabStore.tabs.find((tab: any) => tab.sessionId === activeTabId.value)?.type ?? null
})

// v3.0: when the active tab changes to a session that hasn't been
// hydrated yet, load its message history from the backend. Without
// this, switching to a saved session showed only the welcome state.
watch(activeTabId, async (newId, oldId) => {
  if (!newId || newId === oldId) return
  if (!isSessionTabState(newId, activeTabType.value)) return
  const existing = chatStore.sessions[newId]
  if (existing?.historyStatus === 'ready' && (existing?.messages?.length ?? 0) > 0) return
  void chatStore.loadHistory(newId)
}, { immediate: true })

const sessions = computed(() => sessionStore.sessions)
const sessionState = computed(() => {
  if (!activeTabId.value) return undefined
  return chatStore.sessions[activeTabId.value]
})
const pendingComputerUsePermission = computed(() => sessionState.value?.pendingComputerUsePermission ?? null)

const trackedTaskSessionId = computed(() => cliTaskStore.sessionId)
const hasIncompleteTasks = computed(() => cliTaskStore.tasks.some((task: any) => task.status !== 'completed'))
const hasRunningTasks = computed(() => cliTaskStore.tasks.some((task: any) => task.status === 'in_progress'))
const chatState = computed(() => sessionState.value?.chatState ?? 'idle')
const tokenUsage = computed(() => sessionState.value?.tokenUsage ?? { input_tokens: 0, output_tokens: 0 })
const hasRunningBackgroundTasks = computed(() =>
  Object.values(sessionState.value?.backgroundAgentTasks ?? {}).some((task: any) => task.status === 'running')
)

const session = computed(() => sessions.value.find((s: any) => s.id === activeTabId.value))
const memberInfo = computed(() => {
  if (!activeTabId.value) return null
  return teamStore.getMemberBySessionId(activeTabId.value)
})
const activeTeam = computed(() => teamStore.activeTeam)
const isMemberSession = computed(() => !!memberInfo.value)

const showWorkbench = computed(() => {
  if (!activeTabId.value || isMemberSession.value || isMobileLayout.value) return false
  if (!isSessionTabState(activeTabId.value, activeTabType.value)) return false
  return workspacePanelStore.isPanelOpen(activeTabId.value!)
})
const showRightPanel = computed(() => showWorkbench.value)
const rightPanelWidth = computed(() => workspacePanelStore.width)

const showTerminalPanel = computed(() => {
  if (!activeTabId.value || isMemberSession.value || isMobileLayout.value) return false
  if (!isSessionTabState(activeTabId.value, activeTabType.value)) return false
  return terminalPanelStore.isPanelOpen(activeTabId.value!)
})
const terminalPanelRuntimeId = computed(() => {
  if (!activeTabId.value || isMemberSession.value || isMobileLayout.value) return undefined
  if (!isSessionTabState(activeTabId.value, activeTabType.value)) return undefined
  // Guard against store not yet initialized (HMR / race conditions)
  return terminalPanelStore?.panelBySession?.[activeTabId.value!]?.runtimeId
})
const terminalPanelHeight = computed(() => terminalPanelStore.height)

// ── Tab state ref (used by resize handles) ──────────────────────────────────
const workspaceDragState = ref<{ startX: number; startWidth: number } | null>(null)
const terminalDragState = ref<{ startY: number; startHeight: number } | null>(null)

// ── Lifecycle: connect to session ────────────────────────────────────────────
watch(
  () => [activeTabId.value, isMemberSession.value],
  () => {
    if (activeTabId.value && !isMemberSession.value) {
      chatStore.connectToSession(activeTabId.value)
    }
  },
  { immediate: true }
)

// ── Lifecycle: task polling ──────────────────────────────────────────────────
let taskPollTimer: ReturnType<typeof setInterval> | null = null

function setupTaskPolling() {
  // Clear existing timer
  if (taskPollTimer) {
    clearInterval(taskPollTimer)
    taskPollTimer = null
  }

  if (!activeTabId.value || isMemberSession.value) return

  const shouldPollTasks =
    chatState.value !== 'idle' ||
    (trackedTaskSessionId.value === activeTabId.value && hasIncompleteTasks.value)

  if (!shouldPollTasks) return

  void cliTaskStore.fetchSessionTasks(activeTabId.value)

  taskPollTimer = setInterval(() => {
    if (!activeTabId.value) return
    void cliTaskStore.fetchSessionTasks(activeTabId.value)
  }, TASK_POLL_INTERVAL_MS)
}

watch(
  () => [activeTabId.value, isMemberSession.value, chatState.value, trackedTaskSessionId.value, hasIncompleteTasks.value],
  setupTaskPolling,
  { immediate: true }
)

onBeforeUnmount(() => {
  if (taskPollTimer) {
    clearInterval(taskPollTimer)
    taskPollTimer = null
  }
})

// ── Computed values for main template ────────────────────────────────────────
const messages = computed(() => sessionState.value?.messages ?? [])
const streamingText = computed(() => sessionState.value?.streamingText ?? '')
const activeGoal = computed(() => sessionState.value?.activeGoal ?? null)

const isEmpty = computed(() =>
  messages.value.length === 0 &&
  !streamingText.value &&
  (session.value?.messageCount ?? 0) === 0
)

const compactEmptyHero = computed(() => isEmpty.value && showTerminalPanel.value)

const isHistoryLoading = computed(() =>
  !isMemberSession.value &&
  (session.value?.messageCount ?? 0) > 0 &&
  messages.value.length === 0 &&
  sessionState.value?.historyStatus === 'loading'
)

const historyError = computed(() => {
  if (
    !isMemberSession.value &&
    (session.value?.messageCount ?? 0) > 0 &&
    messages.value.length === 0 &&
    sessionState.value?.historyStatus === 'error'
  ) {
    return sessionState.value.historyError || t('session.historyLoadFailed')
  }
  return null
})

const visibleMessageCount = computed(() =>
  messages.value.length > 0 ? messages.value.length : session.value?.messageCount ?? 0
)

const isActive = computed(() =>
  chatState.value !== 'idle' ||
  (trackedTaskSessionId.value === activeTabId.value && hasRunningTasks.value) ||
  hasRunningBackgroundTasks.value
)

const totalTokens = computed(() => tokenUsage.value.input_tokens + tokenUsage.value.output_tokens)

const lastUpdated = computed(() => {
  if (!session.value?.modifiedAt) return ''
  const diff = Date.now() - new Date(session.value.modifiedAt).getTime()
  if (diff < 60000) return t('session.timeJustNow')
  if (diff < 3600000) return t('session.timeMinutes', { n: Math.floor(diff / 60000) })
  if (diff < 86400000) return t('session.timeHours', { n: Math.floor(diff / 3600000) })
  return t('session.timeDays', { n: Math.floor(diff / 86400000) })
})

// ── ActiveGoalStrip render helper ────────────────────────────────────────────
function renderActiveGoalStrip(goal: ActiveGoalState | null | undefined, isRunning: boolean, compact: boolean) {
  if (!goal || goal.action === 'completed') return null
  const objective = goal.objective ?? goal.message
  if (!objective) return null

  const statusLabel = isRunning
    ? t('chat.activeGoal.running')
    : goal.status === 'paused'
    ? t('chat.activeGoal.paused')
    : t('chat.activeGoal.active')

  const metaItems = [
    goal.budget ? t('chat.activeGoal.budget', { value: goal.budget }) : null,
    goal.elapsed ? t('chat.activeGoal.elapsed', { value: goal.elapsed }) : null,
    goal.continuations ? t('chat.activeGoal.continuations', { value: goal.continuations }) : null,
  ].filter((v): v is string => v !== null)

  return { objective, statusLabel, metaItems, compact }
}

// ── WorkspaceResizeHandle methods ────────────────────────────────────────────
const wsDragStateRef = ref<{ startX: number; startWidth: number } | null>(null)

function setupWorkspaceDrag() {
  if (!workspaceDragState.value) return

  const handlePointerMove = (event: PointerEvent) => {
    const current = wsDragStateRef.value
    if (!current) return
    workspacePanelStore.setWidth(current.startWidth + current.startX - event.clientX)
  }

  const handlePointerUp = () => {
    workspaceDragState.value = null
    wsDragStateRef.value = null
  }

  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', handlePointerUp)
  window.addEventListener('pointercancel', handlePointerUp)

  return () => {
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    window.removeEventListener('pointermove', handlePointerMove)
    window.removeEventListener('pointerup', handlePointerUp)
    window.removeEventListener('pointercancel', handlePointerUp)
  }
}

watch(workspaceDragState, (val) => {
  if (val) {
    wsDragStateRef.value = val
  }
})

watch(
  () => workspaceDragState.value,
  () => {
    if (workspaceDragState.value) {
      setupWorkspaceDrag()
    }
  }
)

// ── TerminalResizeHandle methods ─────────────────────────────────────────────
const termDragStateRef = ref<{ startY: number; startHeight: number } | null>(null)

function setupTerminalDrag() {
  if (!terminalDragState.value) return

  const handlePointerMove = (event: PointerEvent) => {
    const current = termDragStateRef.value
    if (!current) return
    terminalPanelStore.setHeight(current.startHeight + current.startY - event.clientY)
  }

  const handlePointerUp = () => {
    terminalDragState.value = null
    termDragStateRef.value = null
  }

  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', handlePointerUp)
  window.addEventListener('pointercancel', handlePointerUp)

  return () => {
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    window.removeEventListener('pointermove', handlePointerMove)
    window.removeEventListener('pointerup', handlePointerUp)
    window.removeEventListener('pointercancel', handlePointerUp)
  }
}

watch(terminalDragState, (val) => {
  if (val) {
    termDragStateRef.value = val
  }
})

watch(
  () => terminalDragState.value,
  () => {
    if (terminalDragState.value) {
      setupTerminalDrag()
    }
  }
)

// ── Workspace resize keyboard handler ────────────────────────────────────────
function handleWorkspaceKeyDown(event: KeyboardEvent) {
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    workspacePanelStore.setWidth(workspacePanelStore.width + WORKSPACE_RESIZE_STEP)
  }
  if (event.key === 'ArrowRight') {
    event.preventDefault()
    workspacePanelStore.setWidth(workspacePanelStore.width - WORKSPACE_RESIZE_STEP)
  }
}

// ── Terminal resize keyboard handler ─────────────────────────────────────────
function handleTerminalKeyDown(event: KeyboardEvent) {
  if (event.key === 'ArrowUp') {
    event.preventDefault()
    terminalPanelStore.setHeight(terminalPanelStore.height + TERMINAL_RESIZE_STEP)
  }
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    terminalPanelStore.setHeight(terminalPanelStore.height - TERMINAL_RESIZE_STEP)
  }
  if (event.key === 'Home') {
    event.preventDefault()
    terminalPanelStore.setHeight(TERMINAL_PANEL_MIN_HEIGHT)
  }
  if (event.key === 'End') {
    event.preventDefault()
    terminalPanelStore.setHeight(TERMINAL_PANEL_MAX_HEIGHT)
  }
}

// ── Terminal double-click handler ────────────────────────────────────────────
function handleTerminalDoubleClick() {
  terminalPanelStore.setHeight(TERMINAL_PANEL_DEFAULT_HEIGHT)
}

// ── Terminal open-in-tab handler ─────────────────────────────────────────────
function openTerminalInTab() {
  terminalPanelStore.closePanel(activeTabId.value!)
  tabStore.openTerminalTab(getSessionTerminalCwd(session.value), terminalPanelRuntimeId.value!)
  terminalPanelStore.detachRuntime(activeTabId.value!)
}
</script>

<template>
  <!-- Early return guard: no active tab -->
  <div v-if="!activeTabId" />

  <div v-else class="flex-1 flex relative overflow-hidden bg-background text-on-surface">
    <div data-testid="active-session-content-row" class="flex min-h-0 min-w-0 flex-1">
      <!-- Chat column -->
      <div
        data-testid="active-session-chat-column"
        :class="showRightPanel ? CHAT_COLUMN_WITH_WORKSPACE_CLASS : isMobileLayout ? 'min-w-0 flex-1' : 'min-w-[360px] flex-1'"
        class="flex min-h-0 flex-col"
      >
        <!-- Member session header -->
        <div
          v-if="isMemberSession"
          class="w-full shrink-0 border-b border-[var(--color-border)] bg-[var(--color-surface-container)]"
        >
          <div class="mx-auto max-w-[860px] flex items-center justify-between gap-4 px-8 py-2">
            <div class="min-w-0">
              <div class="flex items-center gap-3">
                <span
                  v-if="memberInfo?.status === 'running'"
                  class="flex h-2 w-2 rounded-full bg-[var(--color-warning)] animate-pulse-dot"
                />
                <span
                  v-else-if="memberInfo?.status === 'completed'"
                  class="material-symbols-outlined text-[14px] text-[var(--color-success)]"
                  style="fontVariationSettings: 'FILL' 1"
                >check_circle</span>
                <span class="material-symbols-outlined text-[14px] text-[var(--color-text-tertiary)]">smart_toy</span>
                <span class="text-sm font-semibold text-[var(--color-text-primary)]">
                  {{ memberInfo?.role }}
                </span>
                <span v-if="activeTeam" class="text-[10px] text-[var(--color-text-tertiary)]">
                  @ {{ activeTeam.name }}
                </span>
              </div>
              <p class="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
                {{ t('teams.memberSessionHint') }}
              </p>
            </div>
            <button
              @click="activeTeam?.leadSessionId && tabStore.openTab(activeTeam.leadSessionId, t('teams.leader'), 'session')"
              :disabled="!activeTeam?.leadSessionId"
              class="flex shrink-0 items-center gap-1 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors disabled:opacity-50 disabled:hover:text-[var(--color-text-secondary)]"
            >
              <span class="material-symbols-outlined text-[14px]">arrow_back</span>
              {{ t('teams.backToLeader') }}
            </button>
          </div>
        </div>

        <!-- Empty state -->
        <div
          v-if="isEmpty"
          data-testid="empty-session-hero"
          :class="['relative flex min-h-0 flex-1 flex-col items-center justify-center overflow-hidden', compactEmptyHero ? 'pb-6' : 'pb-28']"
          class="w-full"
        >
          <!-- Subtle gradient background -->
          <div class="pointer-events-none absolute inset-0 bg-gradient-to-b from-[var(--color-surface)] via-transparent to-[var(--color-surface)] opacity-40" />

          <div class="relative z-10 flex max-w-md flex-col items-center text-center px-6">
            <!-- Member session empty -->
            <template v-if="isMemberSession">
              <span
                :class="['material-symbols-outlined mb-5 text-[var(--color-text-tertiary)]', compactEmptyHero ? 'text-[36px]' : 'text-[48px]']"
              >smart_toy</span>
              <p class="text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
                {{ memberInfo?.status === 'running' ? `${memberInfo.role} ${t('teams.working')}` : t('teams.noMessages') }}
              </p>
            </template>

            <!-- Normal session empty -->
            <template v-else>
              <MadCopLoader
                state="'ready'"
                :size="compactEmptyHero ? 120 : 160"
                class="mb-5"
              />
              <h1
                class="mb-2 text-[22px] font-bold tracking-tight text-[var(--color-text-primary)]"
                style="font-family: var(--font-headline)"
              >
                {{ t('empty.title') }}
              </h1>
              <p
                class="mx-auto max-w-xs text-[13px] leading-relaxed text-[var(--color-text-tertiary)]"
              >
                {{ t('empty.subtitle') }}
              </p>
            </template>
          </div>
        </div>

        <!-- Non-empty session content -->
        <template v-else>
          <!-- Session header (non-member, non-mobile) -->
          <div
            v-if="!isMemberSession && !isMobileLayout"
            :class="showRightPanel ? 'flex w-full items-center border-b border-[var(--color-border)]/60 bg-[var(--color-surface-container-lowest)]/50 px-4 py-2.5' : 'w-full border-b border-[var(--color-border)]/60 bg-[var(--color-surface-container-lowest)]/50 px-4 py-2.5'"
          >
            <div :class="showRightPanel ? 'min-w-0 flex-1' : 'mx-auto w-full max-w-[860px] min-w-0'">
              <div class="flex min-w-0 items-center gap-3">
                <h1
                  :class="showRightPanel
                    ? 'min-w-0 flex-1 truncate text-[14px] font-semibold text-[var(--color-text-primary)]'
                    : 'min-w-0 flex-1 text-[16px] font-semibold text-[var(--color-text-primary)]'"
                >
                  {{ session?.title || t('session.untitled') }}
                </h1>
              </div>
              <div
                :class="showRightPanel
                  ? 'mt-1 flex min-w-0 items-center gap-1.5 overflow-hidden whitespace-nowrap text-[10px] font-medium text-outline'
                  : 'flex items-center gap-2 text-[10px] text-outline font-medium mt-1'"
              >
                <span v-if="isActive" class="flex shrink-0 items-center gap-1">
                  <span class="w-1.5 h-1.5 rounded-full bg-[var(--color-success)] animate-pulse-dot" />
                  {{ t('session.active') }}
                </span>
                <template v-if="totalTokens > 0">
                  <span class="text-[var(--color-outline)]">·</span>
                  <span :title="t('common.tokens', { count: totalTokens.toLocaleString() })">
                    {{ t('common.tokens', { count: formatTokenCount(totalTokens) }) }}
                  </span>
                </template>
                <template v-if="lastUpdated">
                  <span class="shrink-0 text-[var(--color-outline)]">·</span>
                  <span class="truncate">{{ t('session.lastUpdated', { time: lastUpdated }) }}</span>
                </template>
                <template v-if="!showRightPanel && visibleMessageCount > 0">
                  <span class="text-[var(--color-outline)]">·</span>
                  <span>{{ t('session.messages', { count: visibleMessageCount }) }}</span>
                </template>
              </div>

              <!-- Workspace unavailable warning -->
              <div
                v-if="session?.workDirExists === false"
                class="mt-2 inline-flex max-w-full items-center gap-2 rounded-lg border border-[var(--color-error)]/20 bg-[var(--color-error)]/8 px-3 py-1.5 text-[11px] text-[var(--color-error)]"
              >
                <span class="material-symbols-outlined text-[14px]">warning</span>
                <span class="truncate">
                  {{ t('session.workspaceUnavailable', { dir: session.workDir || 'directory no longer exists' }) }}
                </span>
              </div>

              <!-- Active Goal Strip -->
              <div
                v-if="activeGoal && activeGoal.action !== 'completed'"
                data-testid="active-goal-strip"
                :class="['mt-2 flex max-w-full items-center gap-2 rounded-[8px] border border-[var(--color-memory-border)] bg-[var(--color-memory-surface)] px-2.5 py-1.5', showRightPanel ? 'text-[11px]' : 'text-[12px]']"
              >
                <span class="material-symbols-outlined shrink-0 text-[var(--color-memory-accent)]">target</span>
                <span class="shrink-0 font-semibold text-[var(--color-text-primary)]">
                  {{ t('chat.activeGoal.title') }}
                </span>
                <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-memory-accent)]" aria-hidden="true" />
                <span class="shrink-0 text-[var(--color-text-tertiary)]">
                  {{ isActive ? t('chat.activeGoal.running') : activeGoal.status === 'paused' ? t('chat.activeGoal.paused') : t('chat.activeGoal.active') }}
                </span>
                <span class="min-w-0 flex-1 truncate font-medium text-[var(--color-text-primary)]" :title="activeGoal.objective ?? activeGoal.message">
                  {{ activeGoal.objective ?? activeGoal.message }}
                </span>
                <span
                  v-if="activeGoal.budget || activeGoal.elapsed || activeGoal.continuations"
                  class="hidden shrink-0 items-center gap-1.5 text-[11px] text-[var(--color-text-tertiary)] lg:flex"
                >
                  <span v-if="activeGoal.budget" class="max-w-[140px] truncate">{{ t('chat.activeGoal.budget', { value: activeGoal.budget }) }}</span>
                  <span v-if="activeGoal.elapsed" class="max-w-[140px] truncate">{{ t('chat.activeGoal.elapsed', { value: activeGoal.elapsed }) }}</span>
                  <span v-if="activeGoal.continuations" class="max-w-[140px] truncate">{{ t('chat.activeGoal.continuations', { value: activeGoal.continuations }) }}</span>
                </span>
              </div>
            </div>
          </div>

          <!-- History loading -->
          <div
            v-if="isHistoryLoading"
            role="status"
            class="w-full flex flex-1 items-center justify-center p-8 text-sm text-[var(--color-text-secondary)]"
          >
            <span class="material-symbols-outlined mr-2 animate-spin text-[18px]">progress_activity</span>
            {{ t('common.loading') }}
          </div>

          <!-- History error -->
          <div
            v-else-if="historyError"
            role="alert"
            class="w-full flex flex-1 items-center justify-center p-8 text-sm text-[var(--color-error)]"
          >
            {{ historyError }}
          </div>

          <!-- Message list -->
          <template v-else>
            <div class="flex-1 min-h-0 w-full overflow-y-auto pt-6">
              <div class="mx-auto max-w-[820px] px-5">
                <MessageList :compact="showRightPanel" />
              </div>
            </div>
          </template>
        </template>

        <!-- Session task bar (non-member) -->
        <SessionTaskBar v-if="!isMemberSession" />

        <!-- Team status bar -->
        <TeamStatusBar />

        <!-- Chat input -->
        <ChatInput
          :variant="isEmpty && !isMemberSession && !showRightPanel ? 'hero' : 'default'"
          :compact="showRightPanel"
        />

        <!-- Terminal panel -->
        <div
          v-if="terminalPanelRuntimeId && activeTabId"
          data-testid="session-terminal-panel"
          :class="['flex min-h-0 shrink-0 flex-col border-t border-[var(--color-border)] bg-[var(--color-surface-container-lowest)]', !showTerminalPanel ? 'hidden' : '']"
          :style="{ height: showTerminalPanel ? terminalPanelHeight : 0 }"
        >
          <div
            v-if="showTerminalPanel"
            @pointerdown="terminalDragState = { startY: ($event as PointerEvent).clientY, startHeight: terminalPanelHeight }"
            @keydown="handleTerminalKeyDown"
            @dblclick="handleTerminalDoubleClick"
            role="separator"
            :aria-label="t('terminal.resizePanel')"
            aria-orientation="horizontal"
            :aria-valuemin="TERMINAL_PANEL_MIN_HEIGHT"
            :aria-valuemax="TERMINAL_PANEL_MAX_HEIGHT"
            :aria-valuenow="terminalPanelHeight"
            tabindex="0"
            data-testid="terminal-resize-handle"
            class="group flex h-2.5 shrink-0 cursor-row-resize items-center bg-[var(--color-surface)] outline-none focus-visible:bg-[var(--color-surface-container)]"
          >
            <div class="mx-3 h-px flex-1 rounded-full bg-[var(--color-border)] transition-colors group-hover:bg-[var(--color-border-focus)] group-focus-visible:bg-[var(--color-border-focus)]" />
          </div>
          <TerminalSettings
            :active="showTerminalPanel"
            docked
            :cwd="getSessionTerminalCwd(session)"
            :runtime-id="terminalPanelRuntimeId"
            preserve-on-unmount
            :test-id="`session-terminal-host-${activeTabId}`"
            @open-in-tab="openTerminalInTab"
            @close="terminalPanelStore.closePanel(activeTabId!)"
          />
        </div>
      </div>

      <!-- Workspace resize handle + Workbench panel -->
      <template v-if="showWorkbench">
        <div
          @pointerdown="workspaceDragState = { startX: ($event as PointerEvent).clientX, startWidth: rightPanelWidth }"
          @keydown="handleWorkspaceKeyDown"
          role="separator"
          :aria-label="t('workspace.resizePanel')"
          aria-orientation="vertical"
          :aria-valuenow="rightPanelWidth"
          tabindex="0"
          data-testid="workspace-resize-handle"
          class="group relative z-10 flex w-2 shrink-0 cursor-col-resize items-stretch justify-center bg-[var(--color-surface)] outline-none focus-visible:bg-[var(--color-surface-container)]"
        >
          <div class="my-3 w-px rounded-full bg-[var(--color-border)] transition-colors group-hover:bg-[var(--color-border-focus)] group-focus-visible:bg-[var(--color-border-focus)]" />
        </div>
        <aside
          data-testid="workbench-panel"
          class="flex h-full shrink-0 flex-col border-l border-[var(--color-border)] bg-[var(--color-surface)]"
          :style="{ width: rightPanelWidth, maxWidth: '62%', minWidth: 'min(420px, 54%)' }"
        >
          <WorkbenchPanel :session-id="activeTabId" />
        </aside>
      </template>
    </div>

    <!-- Computer use permission modal (non-member) -->
    <ComputerUsePermissionModal
      v-if="!isMemberSession && activeTabId"
      :session-id="activeTabId"
      :request="pendingComputerUsePermission?.request ?? null"
    />

    <!-- Clarification panel (non-member) -->
    <ClarificationPanel
      v-if="!isMemberSession && activeTabId"
      :session-id="activeTabId"
    />
  </div>
</template>


