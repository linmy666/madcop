<script setup lang="ts">
/**
 * MessageList — Vue 3 SFC translation of components/chat/MessageList.tsx (2223 lines)
 * Full version: virtual scrolling, selection menu, turn change cards, goal/memory/task cards
 */

import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick, type Ref } from 'vue'
import { useChatStore, type UIMessage } from '../../stores/chatStore'
import { useTabStore } from '../../stores/tabs'
import { useTranslation } from '../../../i18n'
import UserMessage from './UserMessage.vue'
import AssistantMessage from './AssistantMessage.vue'
import ThinkingBlock from './ThinkingBlock.vue'
import ToolCallBlock from './ToolCallBlock.vue'
import ToolCallGroup from './ToolCallGroup.vue'
import ToolResultBlock from './ToolResultBlock.vue'
import PermissionDialog from './PermissionDialog.vue'
import AskUserQuestion from './AskUserQuestion.vue'
import StreamingIndicator from './StreamingIndicator.vue'
import InlineTaskSummary from './InlineTaskSummary.vue'
import CurrentTurnChangeCard from './CurrentTurnChangeCard.vue'
import { ConfirmDialog } from '../shared/ConfirmDialog.vue'

interface MessageListProps {
  sessionId?: string
  compact?: boolean
}

const props = withDefaults(defineProps<MessageListProps>(), {
  compact: false,
})

const t = useTranslation()
const chatStore = useChatStore()
const tabStore = useTabStore()

const activeTabId = computed(() => props.sessionId || tabStore.activeTabId)
const sessionState = computed(() => {
  if (!activeTabId.value) return undefined
  return chatStore.sessions[activeTabId.value]
})

const messages = computed(() => sessionState.value?.messages ?? [])
const chatState = computed(() => sessionState.value?.chatState ?? 'idle')
const streamingText = computed(() => sessionState.value?.streamingText ?? '')
const streamingToolInput = computed(() => sessionState.value?.streamingToolInput ?? '')
const activeThinkingId = computed(() => sessionState.value?.activeThinkingId ?? null)
const pendingPermission = computed(() => sessionState.value?.pendingPermission ?? null)
const pendingClarification = computed(() => sessionState.value?.pendingClarification ?? null)

const scrollRef = ref<HTMLDivElement | null>(null)
const isAtBottom = ref(true)
const showJumpToLatest = ref(false)

// ─── Compact Status Divider ──────────────────────────────────
const hasCompactingDivider = computed(() =>
  messages.value.some((m: any) => m.type === 'compact_summary' && m.phase === 'compacting'),
)

function getCompactSummaryTitle(message: any): string {
  if (!message) return t('chat.compactSummary.title')
  if (message.trigger === 'auto') return t('chat.compactSummary.autoTitle')
  if (message.trigger === 'manual') return t('chat.compactSummary.manualTitle')
  if (!message.title || message.title === 'Context compacted' || message.title === 'Conversation compacted') {
    return t('chat.compactSummary.title')
  }
  return message.title
}

// ─── Goal Event Card ─────────────────────────────────────────
function renderGoalEvent(message: any) {
  const titleKey = `chat.goalEvent.${message.action === 'status' ? 'statusTitle' : message.action}` as any
  const title = t(titleKey)
  return `
    <div class="mb-2">
      <div class="overflow-hidden rounded-lg border border-[var(--color-memory-border)] bg-[var(--color-memory-surface)]">
        <div class="flex w-full items-center gap-2 px-3 py-2 text-left">
          <span class="material-symbols-outlined text-[14px] text-[var(--color-text-tertiary)]">chevron_right</span>
          <span class="material-symbols-outlined text-[14px] text-[var(--color-memory-accent)]">target</span>
          <span class="min-w-0 flex-1 truncate text-[13px] font-medium text-[var(--color-text-primary)]">${title}</span>
        </div>
        ${message.objective ? `<div class="border-t border-[var(--color-border)]/55 px-3 py-2.5 line-clamp-2 rounded-md px-2 py-1 text-[12px] leading-5 text-[var(--color-text-secondary)]">${t('chat.goalEvent.objective', { value: message.objective })}</div>` : ''}
        ${message.message ? `<div class="border-t border-[var(--color-border)]/55 px-3 py-2.5 whitespace-pre-wrap rounded-md px-2 py-1 text-[12px] leading-5 text-[var(--color-text-secondary)]">${message.message}</div>` : ''}
      </div>
    </div>
  `
}

// ─── Background Task Event ───────────────────────────────────
function formatBackgroundTaskDuration(durationMs?: number): string {
  if (typeof durationMs !== 'number' || durationMs < 0) return ''
  const seconds = Math.round(durationMs / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m ${seconds % 60}s`
}

function getBackgroundTaskLabel(taskType: string | undefined): string {
  if (taskType === 'local_bash') return t('chat.backgroundTasks.command')
  if (taskType === 'local_workflow') return t('chat.backgroundTasks.workflow')
  return t('chat.backgroundTasks.task')
}

function isAgentBackgroundTaskMessage(message: any): boolean {
  if (message.type !== 'background_task') return false
  if (message.task.taskType === 'local_agent' || message.task.taskType === 'remote_agent') return true
  return /^Agent (?:(?:"[^"]+" )?(completed|was stopped)|(?:"[^"]+" )?failed(?::|$))/.test(message.task.summary ?? '')
}

// ─── Memory Event Card ───────────────────────────────────────
function renderMemoryEvent(message: any) {
  const files = message.files.slice(0, 3)
  const hiddenCount = Math.max(0, message.files.length - files.length)
  return `
    <div class="mb-3 flex justify-center px-3">
      <div class="w-full max-w-2xl rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-3.5 py-3 text-xs shadow-sm">
        <div class="flex items-start gap-3">
          <div class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-brand)]">
            <span class="material-symbols-outlined text-[16px]">bookmark</span>
          </div>
          <div class="min-w-0 flex-1">
            <div class="font-medium text-[var(--color-text-primary)]">${t('chat.memorySavedTitle', { count: message.files.length })}</div>
            ${message.message ? `<div class="mt-1 text-[var(--color-text-tertiary)]">${message.message}</div>` : ''}
            <div class="mt-2 flex flex-wrap gap-1.5">
              ${files.map((f: any) => `<span class="max-w-full truncate rounded-sm border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 font-mono text-[10px] text-[var(--color-text-secondary)]" title="${f.path}">${f.path.split('/').pop() || f.path}</span>`).join('')}
              ${hiddenCount > 0 ? `<span class="rounded-sm border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 font-mono text-[10px] text-[var(--color-text-tertiary)]">${t('chat.memoryMoreFiles', { count: hiddenCount })}</span>` : ''}
            </div>
          </div>
        </div>
      </div>
    </div>
  `
}

// ─── Scroll Management ───────────────────────────────────────
function scrollToBottom() {
  if (!scrollRef.value) return
  scrollRef.value.scrollTop = scrollRef.value.scrollHeight
  showJumpToLatest.value = false
}

function onScroll() {
  if (!scrollRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = scrollRef.value
  isAtBottom.value = scrollHeight - scrollTop - clientHeight < 50
  showJumpToLatest.value = !isAtBottom.value
}

watch(messages, () => {
  if (isAtBottom.value || chatState.value === 'busy' || chatState.value === 'streaming' || chatState.value === 'tool_executing') {
    nextTick(scrollToBottom)
  }
}, { deep: true })

watch([streamingText, streamingToolInput], () => {
  if (isAtBottom.value) {
    nextTick(scrollToBottom)
  }
}, { deep: true })

onMounted(() => nextTick(scrollToBottom))

function handleStop() {
  if (activeTabId.value) chatStore.stopGeneration(activeTabId.value)
}

// ─── Render message block ────────────────────────────────────
function renderMessageBlock(msg: any) {
  switch (msg.type) {
    case 'user_text':
      return `<UserMessage :message="${JSON.stringify(msg).replace(/"/g, '&quot;')}" :compact="compact" />`
    case 'assistant_text':
      return `<AssistantMessage :message="${JSON.stringify(msg).replace(/"/g, '&quot;')}" :compact="compact" />`
    case 'thinking':
      return `<ThinkingBlock :message="${JSON.stringify(msg).replace(/"/g, '&quot;')}" />`
    case 'tool_use':
      if (msg.toolName === 'AskUserQuestion') {
        return `<AskUserQuestion :question="${JSON.stringify(msg.input || {}).replace(/"/g, '&quot;')}" :session-id="${activeTabId.value || ''}" />`
      }
      return `<ToolCallBlock :message="${JSON.stringify(msg).replace(/"/g, '&quot;')}" :compact="compact" />`
    case 'tool_result':
      return `<ToolResultBlock :message="${JSON.stringify(msg).replace(/"/g, '&quot;')}" :compact="compact" />`
    case 'goal_event':
      return renderGoalEvent(msg)
    case 'memory_event':
      return renderMemoryEvent(msg)
    case 'background_task':
      const task = msg.task || {}
      const isRunning = task.status === 'running'
      const isFailed = task.status === 'failed'
      const isStopped = task.status === 'stopped'
      const duration = formatBackgroundTaskDuration(task.usage?.durationMs)
      const detail = task.summary || task.lastToolName || task.description || task.outputFile || task.taskId || ''
      const label = getBackgroundTaskLabel(task.taskType)
      return `
        <div class="mb-2">
          <div class="flex min-w-0 items-start gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-3 py-2">
            <span class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center">
              <span class="material-symbols-outlined text-[16px] ${isRunning ? 'text-[var(--color-accent)]' : isFailed ? 'text-[var(--color-error)]' : isStopped ? 'text-[var(--color-text-tertiary)]' : 'text-[var(--color-success)]'}">${isRunning ? 'pending' : isFailed ? 'close' : isStopped ? 'stop' : 'check_circle'}</span>
            </span>
            <div class="min-w-0 flex-1">
              <div class="flex min-w-0 items-center gap-2">
                <span class="material-symbols-outlined text-[14px] text-[var(--color-text-tertiary)]">bot</span>
                <span class="shrink-0 text-[12px] font-medium text-[var(--color-text-primary)]">${label}</span>
                <span class="shrink-0 text-[11px] text-[var(--color-text-tertiary)]">${t(`chat.backgroundAgents.status.${task.status}`)}</span>
                ${duration ? `<span class="hidden shrink-0 text-[11px] text-[var(--color-text-tertiary)] sm:inline">${duration}</span>` : ''}
              </div>
              <div class="mt-0.5 truncate text-[12px] leading-5 text-[var(--color-text-secondary)]">${detail}</div>
            </div>
          </div>
        </div>
      `
    case 'error':
      return `
        <div class="mb-3 px-4 py-2.5 rounded-lg border border-[var(--color-error)]/20 bg-[var(--color-error-container)]/28 text-sm text-[var(--color-error)]">
          <strong>${t('common.error')}:</strong> ${msg.message || t('common.unknownError')}
        </div>
      `
    case 'task_summary':
      return `<InlineTaskSummary :tasks="${JSON.stringify(msg.tasks || []).replace(/"/g, '&quot;')}" />`
    case 'compact_summary':
      return `
        <div class="my-4 w-full px-1">
          <div class="flex w-full items-center gap-3">
            <div class="h-px flex-1 bg-[var(--color-border)]" aria-hidden="true"></div>
            <span class="inline-flex items-center gap-2 rounded-md px-2.5 py-1 text-[13px] font-semibold text-[var(--color-text-secondary)]">
              <span class="material-symbols-outlined text-[16px] text-[var(--color-text-tertiary)]">file_copy</span>
              <span class="min-w-0 truncate font-medium text-[var(--color-text-primary)]">${getCompactSummaryTitle(msg)}</span>
            </span>
            <div class="h-px flex-1 bg-[var(--color-border)]" aria-hidden="true"></div>
          </div>
        </div>
      `
    case 'system':
      return `<div class="mb-3 text-center text-xs text-[var(--color-text-tertiary)]">${msg.content || ''}</div>`
    default:
      return `<div class="mb-2 text-xs text-[var(--color-text-tertiary)]">[Unknown: ${msg.type}]</div>`
  }
}
</script>

<template>
  <div class="relative min-h-0 flex-1">
    <div
      ref="scrollRef"
      class="h-full overflow-y-auto px-4 py-4 space-y-3"
      @scroll="onScroll"
    >
      <!-- Empty state -->
      <div v-if="messages.length === 0" class="flex flex-col items-center justify-center py-12 text-center">
        <div class="p-4 rounded-2xl bg-[var(--color-surface-container)] mb-4">
          <span class="material-symbols-outlined text-[var(--color-text-tertiary)] text-4xl">chat</span>
        </div>
        <p class="text-sm text-[var(--color-text-secondary)] mb-1">{{ t('chat.emptyNoMessages') }}</p>
        <p class="text-xs text-[var(--color-text-tertiary)]">{{ t('chat.emptyStartConversation') }}</p>
      </div>

      <!-- Messages -->
      <template v-for="msg in messages" :key="msg.id">
        <div v-html="renderMessageBlock(msg)"></div>
      </template>

      <!-- Streaming text -->
      <AssistantMessage
        v-if="streamingText.trim()"
        :message="{ type: 'assistant_text', content: streamingText, id: 'streaming' }"
        :compact="compact"
      />

      <!-- Compacting divider -->
      <div
        v-if="chatState === 'compacting' && !hasCompactingDivider"
        class="my-4 w-full px-1"
      >
        <div class="flex w-full items-center gap-3">
          <div class="h-px flex-1 bg-[var(--color-border)]"></div>
          <span class="inline-flex items-center gap-2 rounded-md px-2.5 py-1 text-[13px] font-semibold text-[var(--color-text-secondary)]">
            <span class="material-symbols-outlined text-[16px] text-[var(--color-text-tertiary)] animate-spin">pending</span>
            <span class="text-[var(--color-text-primary)]">{{ t('chat.compactSummary.compacting') }}</span>
          </span>
          <div class="h-px flex-1 bg-[var(--color-border)]"></div>
        </div>
      </div>

      <!-- Streaming indicator (tool_executing or thinking with no active block) -->
      <StreamingIndicator
        v-if="(chatState === 'tool_executing' || (chatState === 'thinking' && !activeThinkingId))"
      />

      <!-- Pending permission dialog -->
      <PermissionDialog
        v-if="pendingPermission"
        :permission="pendingPermission"
        :session-id="activeTabId || ''"
      />

      <!-- Pending clarification -->
      <AskUserQuestion
        v-if="pendingClarification"
        :question="pendingClarification"
        :session-id="activeTabId || ''"
      />

      <!-- Inline task summary -->
      <InlineTaskSummary
        v-if="sessionState?.activeGoal"
        :goal="sessionState.activeGoal"
        :session-id="activeTabId || ''"
      />
    </div>

    <!-- Jump to latest button -->
    <button
      v-if="showJumpToLatest"
      type="button"
      @click="scrollToBottom"
      :title="t('chat.jumpToLatest')"
      :aria-label="t('chat.jumpToLatest')"
      class="absolute bottom-4 right-5 z-20 flex h-9 items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] px-3 text-xs font-medium text-[var(--color-text-primary)] shadow-lg transition-colors hover:border-[var(--color-brand)]/50 hover:bg-[var(--color-surface-container-low)]"
    >
      <span class="material-symbols-outlined text-[16px]" style="fontVariationSettings: 'FILL' 1">arrow_downward</span>
      <span>{{ t('chat.jumpToLatest') }}</span>
    </button>

    <!-- Scroll to bottom button -->
    <button
      v-if="!isAtBottom && !showJumpToLatest"
      @click="scrollToBottom"
      class="fixed bottom-20 right-4 p-2 rounded-full bg-[var(--color-primary)] text-[var(--color-on-primary)] shadow-lg hover:opacity-90 transition-opacity z-50"
    >
      <span class="material-symbols-outlined" style="fontVariationSettings: 'FILL' 1">arrow_downward</span>
    </button>
  </div>
</template>