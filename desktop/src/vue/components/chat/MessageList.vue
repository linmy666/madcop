<script setup lang="ts">
/**
 * MessageList — Vue 3 port of components/chat/MessageList.tsx (2223 lines)
 * 
 * Renders the conversation message list.
 * Uses already-translated sub-components:
 *   UserMessage, AssistantMessage, ThinkingBlock, ToolCallBlock,
 *   ToolResultBlock, PermissionDialog, AskUserQuestion, StreamingIndicator,
 *   InlineTaskSummary, CurrentTurnChangeCard.
 * 
 * Simplified: renders all messages (no virtual scrolling).
 */

import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useChatStore, type UIMessage } from '../../stores/chatStore'
import { useTabStore } from '../../stores/tabs'
import UserMessage from './UserMessage.vue'
import AssistantMessage from './AssistantMessage.vue'
import ThinkingBlock from './ThinkingBlock.vue'
import ToolCallBlock from './ToolCallBlock.vue'
import ToolResultBlock from './ToolResultBlock.vue'
import PermissionDialog from './PermissionDialog.vue'
import AskUserQuestion from './AskUserQuestion.vue'
import StreamingIndicator from './StreamingIndicator.vue'
import InlineTaskSummary from './InlineTaskSummary.vue'

interface MessageListProps {
  sessionId?: string
  compact?: boolean
}

const props = withDefaults(defineProps<MessageListProps>(), {
  compact: false,
})

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

function scrollToBottom() {
  if (!scrollRef.value) return
  scrollRef.value.scrollTop = scrollRef.value.scrollHeight
}

function onScroll() {
  if (!scrollRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = scrollRef.value
  isAtBottom.value = scrollHeight - scrollTop - clientHeight < 50
}

watch(messages, () => {
  if (isAtBottom.value || chatState.value === 'busy') {
    nextTick(scrollToBottom)
  }
}, { deep: true })

watch(chatState, (newState) => {
  if (newState === 'busy') {
    nextTick(scrollToBottom)
  }
})

onMounted(() => nextTick(scrollToBottom))

function handleStop() {
  if (activeTabId.value) chatStore.stopGeneration(activeTabId.value)
}
</script>

<template>
  <div
    ref="scrollRef"
    class="flex-1 overflow-y-auto px-4 py-4 space-y-3"
    @scroll="onScroll"
  >
    <!-- Empty state -->
    <div v-if="messages.length === 0" class="flex flex-col items-center justify-center py-12 text-center">
      <div class="p-4 rounded-2xl bg-[var(--color-surface-container)] mb-4">
        <span class="material-symbols-outlined text-[var(--color-text-tertiary)] text-4xl">chat</span>
      </div>
      <p class="text-sm text-[var(--color-text-secondary)] mb-1">No messages yet</p>
      <p class="text-xs text-[var(--color-text-tertiary)]">Start a conversation by typing a message</p>
    </div>

    <!-- Messages -->
    <template v-for="msg in messages" :key="msg.id">
      <UserMessage
        v-if="msg.type === 'user'"
        :message="msg"
        :compact="compact"
      />
      <AssistantMessage
        v-else-if="msg.type === 'assistant_text'"
        :message="msg"
        :compact="compact"
      />
      <ThinkingBlock
        v-else-if="msg.type === 'thinking'"
        :message="msg"
      />
      <ToolCallBlock
        v-else-if="msg.type === 'tool_use'"
        :message="msg"
        :compact="compact"
      />
      <ToolResultBlock
        v-else-if="msg.type === 'tool_result'"
        :message="msg"
        :compact="compact"
      />
    </template>

    <!-- Streaming indicator -->
    <StreamingIndicator
      v-if="chatState === 'busy'"
      :streaming-text="streamingText"
      :streaming-tool-input="streamingToolInput"
      :active-tool-name="sessionState?.activeToolName ?? null"
      @stop="handleStop"
    />

    <!-- Pending permission dialog -->
    <PermissionDialog
      v-if="pendingPermission"
      :permission="pendingPermission"
      :session-id="activeTabId!"
    />

    <!-- Pending clarification -->
    <AskUserQuestion
      v-if="pendingClarification"
      :question="pendingClarification"
      :session-id="activeTabId!"
    />

    <!-- Inline task summary -->
    <InlineTaskSummary
      v-if="sessionState?.activeGoal"
      :goal="sessionState.activeGoal"
      :session-id="activeTabId!"
    />

    <!-- Scroll to bottom button -->
    <button
      v-if="!isAtBottom"
      @click="scrollToBottom"
      class="fixed bottom-20 right-4 p-2 rounded-full bg-[var(--color-primary)] text-[var(--color-on-primary)] shadow-lg hover:opacity-90 transition-opacity z-50"
    >
      <span class="material-symbols-outlined" style="fontVariationSettings: 'FILL' 1">arrow_downward</span>
    </button>
  </div>
</template>