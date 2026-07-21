<script setup lang="ts">
/**
 * MessageList — Vue 3 SFC full translation of components/chat/MessageList.tsx (2223 lines)
 * Full version: virtual scrolling, selection menu, turn change cards, goal/memory/task cards
 */

import {
  ref,
  computed,
  watch,
  onMounted,
  onBeforeUnmount,
  nextTick,
  defineComponent,
  h,
  type PropType,
  type Ref,
} from 'vue'

// ─── Stores ───────────────────────────────────────────────────
import { useChatStore, type UIMessage } from '../../stores/chatStore'
import { useSessionStore } from '../../stores/sessionStore'
import { useWorkspaceChatContextStore } from '../../stores/workspaceChatContextStore'
import { useTabStore } from '../../stores/tabs'
import { useTeamStore } from '../../stores/teamStore'
import { useUIStore } from '../../stores/uiStore'

// ─── i18n ─────────────────────────────────────────────────────
import { useTranslation } from '../../i18n'

// ─── Utilities (extracted from MessageList.tsx) ───────────────
import {
  buildRenderModel,
  getCompletedTurnTargets,
  getLatestCompletedTurnTarget,
  getBranchableMessageTargets,
  buildTurnCardInsertionMap,
  buildChangedFilesByRenderIndex,
  buildVirtualTranscriptWindow,
  shouldVirtualizeRenderItems,
  estimateMessageHeight,
  estimateRenderItemHeight,
  getMessageMetricSignature,
  getRenderItemMetricSignature,
  getRenderItemKey,
  getCompactSummaryTitle,
  formatBackgroundTaskDuration,
  getBackgroundTaskLabel,
  memoryFileLabel,
  isNearScrollBottom,
  rememberSessionScroll,
  getBottomScrollTop,
  setScrollToBottomWithoutLayoutRead,
  setScrollTopWithoutLayoutRead,
  getChatSelectionFromContainer,
  getSelectionPointer,
  sessionScrollSnapshots,
  SCROLL_BOTTOM_SENTINEL,
  AUTO_SCROLL_BOTTOM_THRESHOLD_PX,
  MAX_SCROLL_SNAPSHOTS,
  VIRTUALIZE_MIN_RENDER_ITEMS,
  VIRTUALIZE_MIN_CONTENT_CHARS,
  TOUCH_H5_VIRTUALIZE_MIN_RENDER_ITEMS,
  TOUCH_H5_VIRTUALIZE_MIN_CONTENT_CHARS,
  VIRTUAL_OVERSCAN_PX,
  VIRTUAL_DEFAULT_VIEWPORT_HEIGHT,
  VIRTUAL_MIN_ITEM_HEIGHT,
  VIRTUAL_MAX_ITEM_HEIGHT,
  CONTENT_RESIZE_FOLLOW_MIN_DELTA_PX,
  VIRTUAL_SPACER_CHUNK_PX,
  CHAT_SELECTION_MENU_OFFSET,
  CHAT_SELECTION_MENU_WIDTH,
  CHAT_SELECTION_MENU_HEIGHT,
  CHAT_SCROLL_AREA_CLASS,
  CHAT_RENDER_ITEM_CLASS,
  type RenderItem,
  type RenderModel,
  type TurnChangeCardModel,
  type BranchableMessageTarget,
  type VirtualViewport,
  type VirtualTranscriptWindow,
  type VirtualRenderItemMetric,
  type ChatSelectionState,
  type SelectionPointer,
  type ToolCall,
  type ToolResult,
} from './messageListUtils'

import {
  getHeightsForSession,
  getMetricsForSession,
} from './virtualHeightCache'

import { clearWindowSelection, useSelectionPopoverDismiss } from '../../hooks/useSelectionPopoverDismiss'

// ─── Child components ─────────────────────────────────────────
import UserMessage from './UserMessage.vue'
import AssistantMessage from './AssistantMessage.vue'
import SubAgentPanel from './SubAgentPanel.vue'
import SpriteIsland from '../studio/SpriteIsland.vue'
import {
  buildSpriteRoster,
  selectSpriteDetail,
  type SpriteAgent,
  type SpriteDetail,
} from '../../lib/spriteStudio'
import { sanitizeAgentDisplayText } from '../../lib/agentDisplayText'
import ThinkingBlock from './ThinkingBlock.vue'
import ToolCallBlock from './ToolCallBlock.vue'
import ToolCallGroup from './ToolCallGroup.vue'
import ToolResultBlock from './ToolResultBlock.vue'
import PermissionDialog from './PermissionDialog.vue'
import AskUserQuestion from './AskUserQuestion.vue'
import StreamingIndicator from './StreamingIndicator.vue'
import ThinkingIndicator from './ThinkingIndicator.vue'
import InlineTaskSummary from './InlineTaskSummary.vue'
import CurrentTurnChangeCard from './CurrentTurnChangeCard.vue'
import { ConfirmDialog } from '../shared/ConfirmDialog.vue'

// ─── Constants ────────────────────────────────────────────────
const EMPTY_MESSAGES: UIMessage[] = []

// ─── Props ────────────────────────────────────────────────────
interface MessageListProps {
  sessionId?: string | null
  compact?: boolean
}

const props = withDefaults(defineProps<MessageListProps>(), {
  compact: false,
})

// ─── State ────────────────────────────────────────────────────
const t = useTranslation()
const chatStore = useChatStore()
const sessionStore = useSessionStore()
const workspaceChatContextStore = useWorkspaceChatContextStore()
const tabStore = useTabStore()
const teamStore = useTeamStore()
const uiStore = useUIStore()

// ─── Session / message data ───────────────────────────────────
const activeTabId = computed(() => props.sessionId || tabStore.activeTabId)

const sessionState = computed(() => {
  if (!activeTabId.value) return undefined
  return chatStore.sessions[activeTabId.value]
})

const messages = computed(() => sessionState.value?.messages ?? EMPTY_MESSAGES)
const chatState = computed(() => sessionState.value?.chatState ?? 'idle')
const isAIThinking = computed(() => {
  // v3.7.5 — the indicator should stay visible as long as the
  // agent is producing output (busy / thinking / tool_executing /
  // streaming). Previously it was hidden the moment streamingText
  // became non-empty, which meant the streaming reasoning panel
  // disappeared the instant the first answer token arrived — so
  // the user never saw the 'thinking' animation we added.
  const s = chatState.value
  if (s === 'busy' || s === 'thinking' || s === 'tool_executing' || s === 'streaming') {
    return true
  }
  // If a clarification JSON is pending, the AI is "thinking about"
  // what to ask — show the indicator too.
  if (sessionState.value?.clarificationPending) return true
  return false
})
const streamingText = computed(() => sessionState.value?.streamingText ?? '')
const reasoningContent = computed(() => sessionState.value?.reasoningContent ?? null)
const agentStreams = computed(() => sessionState.value?.agentStreams ?? {})
// Live "what is the AI doing right now" context for the thinking indicator.
const liveToolName = computed(() => sessionState.value?.activeToolName ?? null)

/** Sprite Studio P0: roster from the same session signals as SubAgentPanel. */
const spriteRoster = computed<SpriteAgent[]>(() =>
  buildSpriteRoster({
    agentStreams: sessionState.value?.agentStreams,
    deepRoute: sessionState.value?.deepRoute,
    clarificationPending: sessionState.value?.clarificationPending,
    activeToolName: sessionState.value?.activeToolName,
    chatState: sessionState.value?.chatState,
  }),
)
/**
 * v3.7.3 — only show the sprite island when there's a genuine
 * multi-agent roster (deep mode with specialists, or multiple
 * concurrent agent streams). Standard mode has a single agent that
 * is already represented by ThinkingIndicator; rendering a second
 * floating mascot for it was redundant.
 */
const hasDeepRoster = computed(() => {
  const streams = sessionState.value?.agentStreams
  const streamCount = streams ? Object.keys(streams).length : 0
  const specialists = sessionState.value?.deepRoute?.specialists
  const specialistCount = Array.isArray(specialists) ? specialists.length : 0
  return streamCount >= 2 || specialistCount >= 2
})
const selectedSpriteId = ref<string | null>(null)
const selectedSpriteDetail = computed<SpriteDetail | null>(() =>
  selectSpriteDetail(spriteRoster.value, selectedSpriteId.value),
)
function onSpriteSelect(id: string) {
  selectedSpriteId.value = id
}
const planStep = computed(() => {
  const plan = sessionState.value?.plan
  if (!plan || !plan.steps || plan.steps.length === 0) return null
  const cur = plan.current_step
  const step = plan.steps.find((s: any) => s.step === cur) || plan.steps[0]
  const idx = plan.steps.findIndex((s: any) => s.step === (step?.step ?? cur))
  return {
    label: step?.action || `第 ${cur} 步`,
    tool: step?.tool || null,
    index: idx >= 0 ? idx + 1 : 1,
    total: plan.steps.length,
    status: step?.status,
  }
})
const streamingToolInput = computed(() => sessionState.value?.streamingToolInput ?? '')
const activeThinkingId = computed(() => sessionState.value?.activeThinkingId ?? null)
const activeToolUseId = computed(() => sessionState.value?.activeToolUseId ?? null)
const activeToolName = computed(() => sessionState.value?.activeToolName ?? null)
const agentTaskNotifications = computed(() => sessionState.value?.agentTaskNotifications ?? {})
const pendingPermission = computed(() => sessionState.value?.pendingPermission ?? null)

const activeAskUserQuestionToolUseId = computed(() => {
  if (pendingPermission.value?.toolName === 'AskUserQuestion') {
    return pendingPermission.value.toolUseId
  }
  return null
})

const shouldFollowContentResize = computed(() => {
  return (
    streamingText.value.trim().length > 0 ||
    chatState.value === 'streaming' ||
    chatState.value === 'compacting' ||
    chatState.value === 'tool_executing' ||
    (chatState.value === 'thinking' && Boolean(activeThinkingId.value))
  )
})

const isMemberSession = computed(() => {
  if (!activeTabId.value) return false
  return Boolean(teamStore.getMemberBySessionId(activeTabId.value))
})

const branchActionsDisabled = computed(() => {
  return (
    isMemberSession.value ||
    chatState.value !== 'idle' ||
    streamingText.value.trim().length > 0 ||
    Boolean(activeThinkingId.value) ||
    Boolean(activeToolUseId.value) ||
    Boolean(activeToolName.value)
  )
})

// ─── Scroll refs ──────────────────────────────────────────────
const scrollContainerRef = ref<HTMLDivElement | null>(null)
const scrollContentRef = ref<HTMLDivElement | null>(null)

const shouldAutoScrollRef = ref(true)
const isProgrammaticScrollingRef = ref(false)
const lastAutoScrollAtRef = ref(0)
const lastContentResizeFollowHeightRef = ref<number | null>(null)
const ignoreProgrammaticScrollUntilRef = ref(0)
const ignoreProgrammaticScrollTopRef = ref<number | null>(null)

// ─── Virtual scrolling refs ───────────────────────────────────
const virtualItemHeightsRef = ref(
  activeTabId.value ? getHeightsForSession(activeTabId.value) : new Map<string, number>()
)
const virtualItemMetricCacheRef = ref(
  activeTabId.value ? getMetricsForSession(activeTabId.value) : new Map<string, VirtualRenderItemMetric>()
)
const pendingMeasuredHeightsRef = ref(false)
const measureFlushFrameRef = ref<number | null>(null)
const lastSessionIdRef = ref<string | null | undefined>(activeTabId.value)
const lastTailMessageIdBySessionRef = ref(new Map<string, string | null>())

// ─── Render model ─────────────────────────────────────────────
const renderModel = computed<RenderModel>(() => {
  return buildRenderModel(messages.value, activeAskUserQuestionToolUseId.value)
})

const renderItems = computed(() => renderModel.value.renderItems)
const toolResultMap = computed(() => renderModel.value?.toolResultMap ?? new Map())
const childToolCallsByParent = computed(() => renderModel.value.childToolCallsByParent)

// ─── Branchable messages ──────────────────────────────────────
const branchableMessageTargets = computed(() => {
  return getBranchableMessageTargets(messages.value)
})

const branchingMessageId = ref<string | null>(null)

async function handleBranchMessage(target: BranchableMessageTarget) {
  const sid = activeTabId.value
  if (!sid || branchingMessageId.value || branchActionsDisabled.value) return
  branchingMessageId.value = target.uiMessageId
  try {
    const result = await sessionStore.branchSession(sid, target.transcriptMessageId)
    const title = (result.title || '').trim() || t('sidebar.newSession')
    tabStore.openTab(result.sessionId, title)
    try {
      await chatStore.connectToSession?.(result.sessionId)
    } catch {
      // connectToSession may not exist / may no-op depending on chatStore version
    }
    uiStore.addToast({
      type: 'success',
      message: t('chat.branchSuccess', { title }),
    })
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    uiStore.addToast({
      type: 'error',
      message: t('chat.branchError', { detail }),
    })
  } finally {
    branchingMessageId.value = null
  }
}

// ─── Turn change cards ────────────────────────────────────────
const turnChangeCards = ref<TurnChangeCardModel[]>([])
const turnChangeLoadError = ref<string | null>(null)
const turnActionErrors = ref<Record<string, string>>({})
const isLoadingTurnChangeCards = ref(false)

const turnChangeCardsByIndex = computed(() => {
  return buildTurnCardInsertionMap(renderItems.value, turnChangeCards.value)
})

const changedFilesByRenderIndex = computed(() => {
  return buildChangedFilesByRenderIndex(renderItems.value, turnChangeCards.value)
})

// ─── Selection menu ───────────────────────────────────────────
const selectionMenu = ref<ChatSelectionState | null>(null)
const selectionMenuRef = ref<HTMLButtonElement | null>(null)
const lastSelectionPointerRef = ref<SelectionPointer | null>(null)
const selectionUpdateFrameRef = ref<number | null>(null)

const dismissSelectionMenu = () => {
  selectionMenu.value = null
}

const queueSelectionMenuUpdate = (pointer?: SelectionPointer) => {
  if (pointer) lastSelectionPointerRef.value = pointer

  if (selectionUpdateFrameRef.value !== null) {
    window.cancelAnimationFrame(selectionUpdateFrameRef.value)
  }

  selectionUpdateFrameRef.value = window.requestAnimationFrame(() => {
    selectionUpdateFrameRef.value = window.requestAnimationFrame(() => {
      selectionUpdateFrameRef.value = null
      const root = scrollContainerRef.value
      const rootRect = root?.getBoundingClientRect()
      const fallbackPointer = lastSelectionPointerRef.value ?? {
        clientX: (rootRect?.left ?? 0) + 24,
        clientY: (rootRect?.top ?? 0) + 24,
      }
      selectionMenu.value = getChatSelectionFromContainer(root, fallbackPointer)
    })
  })
}

const addCurrentSelectionToChat = () => {
  if (!activeTabId.value || !selectionMenu.value) return
  workspaceChatContextStore.addReference(activeTabId.value, {
    kind: 'chat-selection',
    path: `chat://user/${selectionMenu.value.text}`,
    name: t('chat.userMessageReference'),
    quote: selectionMenu.value.text,
  })
  selectionMenu.value = null
  clearWindowSelection()
}

// ─── Virtual viewport ─────────────────────────────────────────
const virtualViewport = ref<VirtualViewport>({
  scrollTop: SCROLL_BOTTOM_SENTINEL,
  viewportHeight: VIRTUAL_DEFAULT_VIEWPORT_HEIGHT,
})

const measuredItemsVersion = ref(0)

const itemKeys = computed(() => renderItems.value.map(getRenderItemKey))

const virtualTranscriptWindow = computed<VirtualTranscriptWindow>(() => {
  const metricsArray = Array.from(virtualItemMetricCacheRef.value.values())
  return buildVirtualTranscriptWindow(
    renderItems.value,
    itemKeys.value,
    metricsArray,
    virtualItemHeightsRef.value,
    virtualViewport.value,
    VIRTUAL_OVERSCAN_PX
  )
})

// ─── Jump to latest / bottom state ────────────────────────────
const showJumpToLatest = ref(false)

// ─── Scroll management ────────────────────────────────────────
const syncVirtualViewportFromContainer = (container: HTMLElement) => {
  const nextScrollTop = container.scrollTop
  const nextViewportHeight = container.clientHeight || VIRTUAL_DEFAULT_VIEWPORT_HEIGHT

  if (
    Math.abs(virtualViewport.value.scrollTop - nextScrollTop) < 1 &&
    Math.abs(virtualViewport.value.viewportHeight - nextViewportHeight) < 1
  ) {
    return
  }

  virtualViewport.value = {
    scrollTop: nextScrollTop,
    viewportHeight: nextViewportHeight,
  }
}

const scrollToBottom = (behavior: ScrollBehavior = 'smooth') => {
  shouldAutoScrollRef.value = true
  isProgrammaticScrollingRef.value = true
  ignoreProgrammaticScrollUntilRef.value = performance.now() + 250
  lastAutoScrollAtRef.value = performance.now()

  const container = scrollContainerRef.value
  let requestedScrollTop: number | null = null

  if (container) {
    setScrollToBottomWithoutLayoutRead(container, behavior)
    requestedScrollTop = container.scrollTop
    ignoreProgrammaticScrollTopRef.value = requestedScrollTop
  }

  virtualViewport.value = {
    scrollTop: SCROLL_BOTTOM_SENTINEL,
    viewportHeight: virtualViewport.value.viewportHeight,
  }

  if (container && activeTabId.value) {
    sessionScrollSnapshots.set(activeTabId.value, {
      scrollTop: container.scrollTop,
      wasAtBottom: true,
    })
  }

  showJumpToLatest.value = false

  requestAnimationFrame(() => {
    const latestContainer = scrollContainerRef.value
    if (
      shouldAutoScrollRef.value &&
      latestContainer &&
      (requestedScrollTop === null || latestContainer.scrollTop === requestedScrollTop)
    ) {
      setScrollToBottomWithoutLayoutRead(latestContainer, 'auto')
      if (activeTabId.value) {
        sessionScrollSnapshots.set(activeTabId.value, {
          scrollTop: latestContainer.scrollTop,
          wasAtBottom: true,
        })
      }
    }
    isProgrammaticScrollingRef.value = false
  })
}

const flushMeasuredHeightVersion = () => {
  if (!pendingMeasuredHeightsRef.value) return
  pendingMeasuredHeightsRef.value = false
  measuredItemsVersion.value += 1
}

const handleVirtualItemHeightChange = (itemKey: string, height: number) => {
  const measuredHeight = Math.min(VIRTUAL_MAX_ITEM_HEIGHT, Math.max(VIRTUAL_MIN_ITEM_HEIGHT, height))
  const previousHeight = virtualItemHeightsRef.value.get(itemKey)
  if (previousHeight !== undefined && Math.abs(previousHeight - measuredHeight) < 1) return

  virtualItemHeightsRef.value.set(itemKey, measuredHeight)

  if (!pendingMeasuredHeightsRef.value) {
    pendingMeasuredHeightsRef.value = true
    if (measureFlushFrameRef.value !== null) {
      cancelAnimationFrame(measureFlushFrameRef.value)
    }
    measureFlushFrameRef.value = requestAnimationFrame(() => {
      measureFlushFrameRef.value = null
      flushMeasuredHeightVersion()
    })
  }
}

const handleScroll = () => {
  const container = scrollContainerRef.value
  if (!container) return

  if (!isProgrammaticScrollingRef.value) {
    // User initiated scroll — stop auto-scrolling
    shouldAutoScrollRef.value = false
  }

  syncVirtualViewportFromContainer(container)

  // Show/hide jump-to-latest button
  if (!isNearScrollBottom(container)) {
    showJumpToLatest.value = true
  } else {
    showJumpToLatest.value = false
  }
}

const handleWheel = () => {
  shouldAutoScrollRef.value = false
}

// ─── Event listeners ──────────────────────────────────────────
onMounted(() => {
  // Pointer events for selection tracking
  document.addEventListener('pointerdown', handlePointerDown, true)
  document.addEventListener('pointerup', handlePointerUp, true)
  document.addEventListener('mouseup', handleMouseUp, true)
  document.addEventListener('selectionchange', handleSelectionChange)
  document.addEventListener('keyup', handleKeyUp, true)

  // Auto-scroll on mount
  nextTick(() => {
    scrollToBottom('auto')
  })
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handlePointerDown, true)
  document.removeEventListener('pointerup', handlePointerUp, true)
  document.removeEventListener('mouseup', handleMouseUp, true)
  document.removeEventListener('selectionchange', handleSelectionChange)
  document.removeEventListener('keyup', handleKeyUp, true)

  if (measureFlushFrameRef.value !== null) {
    cancelAnimationFrame(measureFlushFrameRef.value)
  }
})

const handlePointerDown = (event: PointerEvent) => {
  lastSelectionPointerRef.value = getSelectionPointer({
    clientX: event.clientX,
    clientY: event.clientY,
  })
}

const handlePointerUp = (event: PointerEvent) => {
  queueSelectionMenuUpdate(getSelectionPointer({
    clientX: event.clientX,
    clientY: event.clientY,
  }))
}

const handleMouseUp = (event: MouseEvent) => {
  queueSelectionMenuUpdate(getSelectionPointer({
    clientX: event.clientX,
    clientY: event.clientY,
  }))
}

const handleSelectionChange = () => {
  queueSelectionMenuUpdate()
}

const handleKeyUp = () => {
  queueSelectionMenuUpdate()
}

// ─── Watch for scroll position reset on session change ────────
watch(
  () => activeTabId.value,
  (newId, oldId) => {
    if (oldId) {
      const container = scrollContainerRef.value
      if (container) {
        rememberSessionScroll(oldId, container)
      }
    }

    // Restore scroll position for new session
    if (newId) {
      const snapshot = sessionScrollSnapshots.get(newId)
      const container = scrollContainerRef.value

      if (snapshot && container) {
        setScrollTopWithoutLayoutRead(container, snapshot.scrollTop)
      }

      // Reset virtual state
      virtualItemHeightsRef.value = getHeightsForSession(newId)
      virtualItemMetricCacheRef.value = getMetricsForSession(newId)
      virtualViewport.value = {
        scrollTop: snapshot?.wasAtBottom ?? true ? SCROLL_BOTTOM_SENTINEL : snapshot?.scrollTop ?? 0,
        viewportHeight: container?.clientHeight ?? VIRTUAL_DEFAULT_VIEWPORT_HEIGHT,
      }
    }
  }
)

// ─── Auto-scroll on messages/streaming ────────────────────────
watch(
  () => messages.value.length,
  () => {
    if (shouldAutoScrollRef.value || chatState.value === 'busy' || chatState.value === 'streaming' || chatState.value === 'tool_executing') {
      nextTick(() => scrollToBottom('auto'))
    }
  }
)

watch(
  [() => streamingText.value, () => streamingToolInput.value],
  () => {
    if (shouldAutoScrollRef.value) {
      nextTick(() => scrollToBottom('smooth'))
    }
  }
)

watch(
  () => chatState.value,
  (newState) => {
    if (newState === 'idle') {
      nextTick(() => scrollToBottom('auto'))
    }
  }
)

// ─── Stop generation ──────────────────────────────────────────
const handleStop = () => {
  if (activeTabId.value) {
    chatStore.stopGeneration(activeTabId.value)
  }
}

// ─── Selection menu ───────────────────────────────────────────
const SelectionMenu = defineComponent({
  name: 'SelectionMenu',
  props: {
    selection: { type: Object as PropType<ChatSelectionState | null>, required: true },
    i18nT: { type: Function as PropType<(key: string) => string>, required: true },
  },
  emits: ['add'],
  setup() {},
  template: `
    <button
      v-if="selection"
      type="button"
      class="fixed z-50 inline-flex h-11 items-center gap-2 rounded-full border border-[var(--color-border)]/70 bg-[var(--color-surface-container-lowest)] px-5 text-[15px] font-semibold text-[var(--color-text-primary)] shadow-[0_10px_28px_rgba(15,23,42,0.14),0_2px_8px_rgba(15,23,42,0.08)] transition-colors hover:bg-[var(--color-surface)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/35"
      :style="{ left: selection.x + 'px', top: selection.y + 'px' }"
      @mousedown.prevent="true"
      @click="$emit('add')"
    >
      <span class="material-symbols-outlined shrink-0 text-[var(--color-text-primary)]" style="font-size: 21px; fontVariationSettings: 'FILL' 1">chat</span>
      <span>{{ i18nT('chat.addSelectionToChat') }}</span>
    </button>
  `,
})

// ─── Compact Status Divider ───────────────────────────────────
const CompactStatusDivider = defineComponent({
  props: {
    message: { type: Object as PropType<any>, default: undefined },
    state: { type: String as PropType<'compacting' | 'complete'>, required: true },
  },
  setup(props) {
    const expanded = ref(false)
    const hasSummary = computed(() => Boolean(props.message?.summary?.trim()))
    const meta = computed(() => {
      const items: string[] = []
      if (props.message?.trigger) {
        items.push(t(`chat.compactSummary.trigger.${props.message.trigger}`))
      }
      if (typeof props.message?.preTokens === 'number') {
        items.push(t('chat.compactSummary.tokens', { count: String(props.message.preTokens) }))
      }
      if (typeof props.message?.messagesSummarized === 'number') {
        items.push(t('chat.compactSummary.messages', { count: String(props.message.messagesSummarized) }))
      }
      return items
    })
    const hasDetails = computed(() => hasSummary.value || meta.value.length > 0)
    const title = computed(() => {
      if (props.state === 'compacting') return t('chat.compactSummary.compacting')
      if (props.message) return getCompactSummaryTitle(props.message, t)
      return t('chat.compactSummary.title')
    })

    return () => {
      return h('section', {
        'data-testid': 'compact-status-divider',
        class: 'my-4 w-full px-1',
      }, [
        h('div', { class: 'flex w-full items-center gap-3' }, [
          h('div', { class: 'h-px flex-1 bg-[var(--color-border)]', 'aria-hidden': 'true' }),
          h('button', {
            type: 'button',
            'aria-expanded': hasDetails.value ? expanded.value : undefined,
            onClick: () => hasDetails.value && (expanded.value = !expanded.value),
            disabled: !hasDetails.value,
            class: 'group inline-flex min-h-8 max-w-[min(78vw,520px)] items-center gap-2 rounded-md px-2.5 py-1 text-[13px] font-semibold text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)] disabled:cursor-default disabled:hover:text-[var(--color-text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/30',
          }, [
            props.state === 'compacting'
              ? h('span', { class: 'material-symbols-outlined shrink-0 animate-spin text-[var(--color-text-tertiary)]', style: { fontSize: '16px' } }, 'pending')
              : h('span', { class: 'material-symbols-outlined shrink-0 text-[var(--color-text-tertiary)]', style: { fontSize: '16px' } }, 'layers'),
            h('span', { class: 'min-w-0 truncate font-medium text-[var(--color-text-primary)]' }, title.value),
          ]),
          h('div', { class: 'h-px flex-1 bg-[var(--color-border)]', 'aria-hidden': 'true' }),
        ]),
        hasDetails.value && expanded.value ? h('div', {
          class: 'mx-auto mt-1.5 w-full max-w-[620px] rounded-md border border-[var(--color-border)]/65 bg-[var(--color-surface-container-lowest)] px-3 py-2',
        }, [
          meta.value.length > 0 ? h('div', { class: 'mb-1.5 flex flex-wrap gap-x-2 gap-y-1 text-[11px] font-medium text-[var(--color-text-tertiary)]' }, meta.value.map(item => h('span', {}, item))) : null,
          props.message?.summary ? h('div', {
            class: 'max-h-[220px] overflow-auto whitespace-pre-wrap break-words text-[12px] leading-5 text-[var(--color-text-secondary)]',
          }, props.message.summary) : null,
        ]) : null,
      ])
    }
  },
})

// ─── Goal Event Card ──────────────────────────────────────────
const GoalEventCard = defineComponent({
  props: {
    message: { type: Object as PropType<any>, required: true },
  },
  setup(props) {
    const expanded = ref(true)
    const titleKey = computed(() => {
      const key = `chat.goalEvent.${props.message.action === 'status' ? 'statusTitle' : props.message.action}`
      const translated = t(key)
      return translated === key ? 'chat.goalEvent.message' : key
    })

    const metaDetails = computed(() => {
      const items: string[] = []
      if (props.message.status) items.push(t('chat.goalEvent.statusValue', { value: props.message.status }))
      if (props.message.budget) items.push(t('chat.goalEvent.budget', { value: props.message.budget }))
      if (props.message.continuations) items.push(t('chat.goalEvent.continuations', { value: props.message.continuations }))
      return items
    })

    return () => {
      return h('div', { class: 'mb-2' }, [
        h('div', {
          'data-testid': 'goal-event-card',
          class: 'overflow-hidden rounded-lg border border-[var(--color-memory-border)] bg-[var(--color-memory-surface)]',
        }, [
          h('button', {
            type: 'button',
            onClick: () => { expanded.value = !expanded.value },
            class: 'flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-[var(--color-surface-hover)]/50',
          }, [
            h('span', { class: 'material-symbols-outlined shrink-0 text-[var(--color-text-tertiary)]', style: { fontSize: '15px' } }, expanded.value ? 'expand_less' : 'chevron_right'),
            h('span', { class: 'material-symbols-outlined shrink-0 text-[var(--color-memory-accent)]', style: { fontSize: '15px' } }, 'track_changes'),
            h('span', { class: 'min-w-0 flex-1 truncate text-[13px] font-medium text-[var(--color-text-primary)]' }, t(titleKey.value)),
            props.message.status ? h('span', { class: 'inline-flex shrink-0 items-center gap-1 text-[12px] text-[var(--color-text-tertiary)]' }, [
              h('span', { class: 'h-1.5 w-1.5 rounded-full bg-[var(--color-memory-accent)]', 'aria-hidden': 'true' }),
              props.message.status,
            ]) : null,
          ]),
          expanded.value ? h('div', { class: 'border-t border-[var(--color-border)]/55 px-3 py-2.5' }, [
            h('div', { class: 'space-y-1.5' }, [
              props.message.objective ? h('div', {
                class: 'line-clamp-2 rounded-md px-2 py-1 text-[12px] leading-5 text-[var(--color-text-secondary)]',
              }, t('chat.goalEvent.objective', { value: props.message.objective })) :
              props.message.message ? h('div', {
                class: 'whitespace-pre-wrap rounded-md px-2 py-1 text-[12px] leading-5 text-[var(--color-text-secondary)]',
              }, props.message.message) : null,
              metaDetails.value.length > 0 ? h('div', { class: 'flex flex-wrap items-center gap-1.5 px-2 pt-0.5' },
                metaDetails.value.map(detail => h('span', {
                  key: detail,
                  class: 'rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--color-text-secondary)]',
                }, detail))
              ) : null,
            ])
          ]) : null,
        ])
      ])
    }
  },
})

// ─── Background Task Event ────────────────────────────────────
const BackgroundTaskEventCard = defineComponent({
  props: {
    message: { type: Object as PropType<any>, required: true },
  },
  setup(props) {
    const task = computed(() => props.message.task)
    const isRunning = computed(() => task.value.status === 'running')
    const isFailed = computed(() => task.value.status === 'failed')
    const isStopped = computed(() => task.value.status === 'stopped')
    const duration = computed(() => formatBackgroundTaskDuration(task.value.usage?.durationMs))
    const detail = computed(() => task.value.summary || task.value.lastToolName || task.value.description || task.value.outputFile || task.value.taskId || '')
    const label = computed(() => getBackgroundTaskLabel(task.value.taskType, t))

    return () => {
      return h('div', { class: 'mb-2' }, [
        h('div', {
          'data-testid': 'background-task-event-card',
          'data-status': task.value.status,
          class: 'flex min-w-0 items-start gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-3 py-2',
        }, [
          h('span', { class: 'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center' }, [
            h('span', {
              class: 'material-symbols-outlined',
              style: {
                fontSize: '15px',
                color: isRunning.value ? 'var(--color-accent)' : isFailed.value ? 'var(--color-error)' : isStopped.value ? 'var(--color-text-tertiary)' : 'var(--color-success)',
              },
            }, isRunning.value ? 'pending' : isFailed.value ? 'close' : isStopped.value ? 'stop' : 'check_circle'),
          ]),
          h('div', { class: 'min-w-0 flex-1' }, [
            h('div', { class: 'flex min-w-0 items-center gap-2' }, [
              h('span', { class: 'material-symbols-outlined shrink-0 text-[var(--color-text-tertiary)]', style: { fontSize: '14px' } }, 'bot'),
              h('span', { class: 'shrink-0 text-[12px] font-medium text-[var(--color-text-primary)]' }, label.value),
              h('span', { class: 'shrink-0 text-[11px] text-[var(--color-text-tertiary)]' }, t(`chat.backgroundAgents.status.${task.value.status}`)),
              task.value.usage?.totalTokens ? h('span', { class: 'hidden shrink-0 text-[11px] text-[var(--color-text-tertiary)] sm:inline' }, t('chat.backgroundAgents.tokens', { count: task.value.usage.totalTokens })) : null,
              duration.value ? h('span', { class: 'hidden shrink-0 text-[11px] text-[var(--color-text-tertiary)] sm:inline' }, duration.value) : null,
            ]),
            h('div', { class: 'mt-0.5 truncate text-[12px] leading-5 text-[var(--color-text-secondary)]' }, detail.value),
          ]),
        ])
      ])
    }
  },
})

// ─── Memory Event Card ────────────────────────────────────────
const MemoryEventCard = defineComponent({
  props: {
    message: { type: Object as PropType<any>, required: true },
  },
  setup(props) {
    const visibleFiles = computed(() => props.message.files.slice(0, 3))
    const hiddenCount = computed(() => Math.max(0, props.message.files.length - visibleFiles.value.length))

    const openMemorySettings = () => {
      if (props.message.files[0]?.path) {
        uiStore.setPendingMemoryPath(props.message.files[0].path)
      }
      uiStore.setPendingSettingsTab('memory')
      tabStore.openTab('settings', 'Settings', 'settings')
    }

    return () => {
      return h('div', { class: 'mb-3 flex justify-center px-3' }, [
        h('div', {
          class: 'w-full max-w-2xl rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-3.5 py-3 text-xs shadow-sm',
        }, [
          h('div', { class: 'flex items-start gap-3' }, [
            h('div', {
              class: 'mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-brand)]',
            }, [
              h('span', { class: 'material-symbols-outlined', style: { fontSize: '15px' } }, 'bookmark_added'),
            ]),
            h('div', { class: 'min-w-0 flex-1' }, [
              h('div', { class: 'flex flex-wrap items-center justify-between gap-2' }, [
                h('div', { class: 'font-medium text-[var(--color-text-primary)]' }, t('chat.memorySavedTitle', { count: props.message.files.length })),
                h('button', {
                  type: 'button',
                  onClick: openMemorySettings,
                  class: 'inline-flex h-7 items-center gap-1.5 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-[11px] font-medium text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-brand)]/50 hover:text-[var(--color-text-primary)]',
                }, [
                  h('span', { class: 'material-symbols-outlined', style: { fontSize: '13px' } }, 'settings'),
                  t('chat.memoryOpenSettings'),
                ]),
              ]),
              props.message.message ? h('div', { class: 'mt-1 text-[var(--color-text-tertiary)]' }, props.message.message) : null,
              h('div', { class: 'mt-2 flex flex-wrap gap-1.5' }, [
                visibleFiles.value.map((file: any) =>
                  h('span', {
                    key: file.path,
                    title: file.path,
                    class: 'max-w-full truncate rounded-sm border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 font-mono text-[10px] text-[var(--color-text-secondary)]',
                  }, memoryFileLabel(file.path))
                ),
                hiddenCount.value > 0 ? h('span', {
                  class: 'rounded-sm border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 font-mono text-[10px] text-[var(--color-text-tertiary)]',
                }, t('chat.memoryMoreFiles', { count: hiddenCount.value })) : null,
              ]),
            ]),
          ]),
        ]),
      ])
    }
  },
})

// ─── Measured Render Item ─────────────────────────────────────
const MeasuredRenderItem = defineComponent({
  props: {
    itemKey: { type: String, required: true },
  },
  setup(props, { slots }) {
    const itemRef = ref<HTMLElement | null>(null)

    onMounted(() => {
      if (typeof ResizeObserver !== 'undefined' && itemRef.value) {
        const observer = new ResizeObserver((entries) => {
          const entry = entries[0]
          if (entry && Number.isFinite(entry.contentRect.height) && entry.contentRect.height > 0) {
            handleVirtualItemHeightChange(props.itemKey, Math.ceil(entry.contentRect.height))
          }
        })
        observer.observe(itemRef.value)
      }
    })

    return () => {
      return h('div', {
        ref: itemRef,
        'data-virtual-message-item': props.itemKey,
        class: CHAT_RENDER_ITEM_CLASS,
      }, slots.default?.())
    }
  },
})

// ─── Virtual Spacer ───────────────────────────────────────────
const VirtualSpacer = defineComponent({
  props: {
    height: { type: Number, required: true },
    position: { type: String as PropType<'top' | 'bottom'>, required: true },
  },
  setup(props) {
    if (props.height <= 0) return () => null
    if (props.height <= VIRTUAL_SPACER_CHUNK_PX) {
      return () => h('div', {
        'data-virtual-spacer': props.position,
        'aria-hidden': 'true',
        style: { height: props.height + 'px' },
      })
    }

    const chunkCount = Math.max(1, Math.ceil(props.height / VIRTUAL_SPACER_CHUNK_PX))
    const chunkHeight = Math.floor(props.height / chunkCount)
    const remainder = props.height - chunkHeight * chunkCount

    const chunks = []
    for (let i = 0; i < chunkCount; i++) {
      const px = i === chunkCount - 1 ? chunkHeight + remainder : chunkHeight
      chunks.push(h('div', {
        key: `${props.position}-${i}`,
        'data-virtual-spacer-chunk': props.position,
        style: {
          height: px + 'px',
          contentVisibility: 'auto',
          containIntrinsicSize: `0 ${px}px`,
        },
      }))
    }

    return () => h('div', { 'data-virtual-spacer': props.position, 'aria-hidden': 'true' }, chunks)
  },
})

// ─── Render item content ──────────────────────────────────────
function renderItemContent(item: RenderItem) {
  if (item.kind === 'tool_group') {
    return h(ToolCallGroup, {
      toolCalls: item.toolCalls,
      toolResultMap: toolResultMap.value,
      childToolCallsByParent: childToolCallsByParent.value,
    })
  }

  const msg = item.message

  // AskUserQuestion
  if (msg.type === 'tool_use' && msg.toolName === 'AskUserQuestion') {
    return h(AskUserQuestion, {
      question: msg.input || {},
      sessionId: activeTabId.value || '',
    })
  }

  // Message types
  if (msg.type === 'user_text') {
    return h(UserMessage, {
      content: msg.content || '',
      attachments: (msg as any).attachments,
      sessionId: msg.sessionId,
      compact: props.compact,
    })
  }
  if (msg.type === 'assistant_text') {
    const branchTarget = branchableMessageTargets.value.get(msg.id)
    const canBranch = Boolean(branchTarget) && !branchActionsDisabled.value
    return h(AssistantMessage, {
      content: msg.content || '',
      isStreaming: msg.isStreaming,
      sessionId: msg.sessionId,
      timestamp: msg.timestamp,
      compact: props.compact,
      canBranch,
      branchLoading: branchingMessageId.value === msg.id,
      branchLabel: t('chat.branchFromHere'),
      onBranch: branchTarget ? () => { void handleBranchMessage(branchTarget) } : undefined,
    })
  }
  if (msg.type === 'thinking') {
    return h(ThinkingBlock, { message: msg })
  }
  if (msg.type === 'tool_use') {
    // result is attached on the same tool_use message when SSE tool_result pairs
    const rawResult = (msg as any).result
    const resultProp =
      rawResult == null
        ? null
        : typeof rawResult === 'object' && rawResult !== null && 'content' in (rawResult as object)
          ? (rawResult as { content: unknown; isError?: boolean })
          : { content: rawResult, isError: !!(msg as any).isError }
    return h(ToolCallBlock, {
      toolName: msg.toolName,
      input: msg.input,
      isPending: msg.isPending,
      result: resultProp,
      partialInput: msg.partialInput,
      compact: props.compact,
    })
  }
  if (msg.type === 'tool_result') {
    return h(ToolResultBlock, {
      toolName: msg.toolName,
      result: msg.result,
      isError: msg.isError,
      compact: props.compact,
    })
  }
  if (msg.type === 'goal_event') {
    return h(GoalEventCard, { message: msg })
  }
  if (msg.type === 'memory_event') {
    return h(MemoryEventCard, { message: msg })
  }
  if (msg.type === 'background_task') {
    return h(BackgroundTaskEventCard, { message: msg })
  }
  if (msg.type === 'error') {
    return h('div', {
      class: 'mb-3 px-4 py-2.5 rounded-lg border border-[var(--color-error)]/20 bg-[var(--color-error-container)]/28 text-sm text-[var(--color-error)]',
    }, `${t('common.error')}: ${msg.message || t('common.unknownError')}`)
  }
  if (msg.type === 'task_summary') {
    return h(InlineTaskSummary, { tasks: msg.tasks || [] })
  }
  if (msg.type === 'compact_summary') {
    const state = msg.phase === 'compacting' ? 'compacting' : 'complete'
    return h(CompactStatusDivider, { message: msg, state })
  }
  if (msg.type === 'system') {
    return h('div', { class: 'mb-3 text-center text-xs text-[var(--color-text-tertiary)]' }, msg.content || '')
  }

  return h('div', { class: 'mb-2 text-xs text-[var(--color-text-tertiary)]' }, `[Unknown: ${msg.type}]`)
}

// ─── Main render (auto-exposed to template via script setup) ──
// All `const` declarations above are automatically available in the template.
</script>

<template>
  <div class="relative min-h-0 flex-1">
    <!-- Scroll container -->
    <div
      ref="scrollContainerRef"
      :class="CHAT_SCROLL_AREA_CLASS"
      class="h-full overflow-y-auto px-4 py-4 space-y-3"
      @scroll="handleScroll"
      @wheel="handleWheel"
    >
      <!-- Empty state -->
      <div
        v-if="messages.length === 0"
        class="flex flex-col items-center justify-center py-12 text-center"
      >
        <div class="p-4 rounded-2xl bg-[var(--color-surface-container)] mb-4">
          <span class="material-symbols-outlined text-[var(--color-text-tertiary)]" style="font-size: 48px; fontVariationSettings: 'FILL' 1">
            chat
          </span>
        </div>
        <p class="text-sm text-[var(--color-text-secondary)] mb-1">{{ t('chat.emptyNoMessages') }}</p>
        <p class="text-xs text-[var(--color-text-tertiary)]">{{ t('chat.emptyStartConversation') }}</p>
      </div>

      <!-- Messages list -->
      <div v-else ref="scrollContentRef" class="mx-auto max-w-[860px] space-y-3">
        <template
          v-for="(renderedItem, index) in virtualTranscriptWindow.items"
          :key="itemKeys[renderedItem.index]"
        >
          <!-- Turn change cards for this render item -->
          <template
            v-for="card in (turnChangeCardsByIndex.get(renderedItem.index) || [])"
            :key="card.target.messageId"
          >
            <CurrentTurnChangeCard :card="card" />
          </template>

          <!-- Render item with height measurement -->
          <MeasuredRenderItem :item-key="itemKeys[renderedItem.index]">
            <component :is="renderItemContent(renderedItem.item)" />
          </MeasuredRenderItem>
        </template>

        <!-- Compact status dividers -->
        <template
          v-for="(msg, idx) in messages"
          :key="`compact-${msg.id}-${idx}`"
        >
          <CompactStatusDivider
            v-if="msg.type === 'compact_summary' && msg.phase === 'compacting'"
            :message="msg"
            state="compacting"
          />
        </template>

        <!-- Deep-mode sub-agent streams (multiple colored sprites working
             in parallel, each with its own live text area). -->
        <SubAgentPanel
          v-if="Object.keys(agentStreams).length > 0"
          :agents="agentStreams"
        />

        <!-- P0 Sprite Island: compact mascot dock bound to session roster.
             v3.7.3 — only render in deep mode (multi-specialist roster).
             In standard / quick mode the single agent is already
             represented by ThinkingIndicator, so the island was
             redundant visual noise. -->
        <SpriteIsland
          v-if="hasDeepRoster"
          :roster="spriteRoster"
          :selected-id="selectedSpriteId"
          @select="onSpriteSelect"
        />
        <div
          v-if="selectedSpriteDetail"
          class="sprite-island-detail"
        >
          <div class="sprite-island-detail__head">
            <strong :style="{ color: selectedSpriteDetail.color }">{{ selectedSpriteDetail.name }}</strong>
            <button type="button" class="sprite-island-detail__close" @click="selectedSpriteId = null">×</button>
          </div>
          <pre v-if="selectedSpriteDetail.text" class="sprite-island-detail__text">{{ sanitizeAgentDisplayText(selectedSpriteDetail.text, 800) }}</pre>
          <p v-else class="sprite-island-detail__empty">{{ sanitizeAgentDisplayText(selectedSpriteDetail.bubble || '暂无输出', 80) }}</p>
        </div>

        <!-- Streaming text (live assistant text being typed out) -->
        <AssistantMessage
          v-if="streamingText.trim()"
          :content="streamingText"
          :is-streaming="true"
          :compact="compact"
        />

        <!-- v3.7.6 — ZCode-style reasoning panel. Stays visible
             for the whole turn (busy / streaming) so the gradient
             "正在思考" label + streaming body are actually seen. -->
        <ThinkingIndicator
          v-if="isAIThinking"
          :reasoning-content="reasoningContent"
          :active-tool-name="liveToolName"
          :plan-step="planStep"
          :is-streaming="chatState !== 'idle' && chatState !== 'error'"
        />

        <!-- Streaming indicator (tool_executing or thinking with no active block) -->
        <StreamingIndicator
          v-if="chatState === 'tool_executing' || (chatState === 'thinking' && !activeThinkingId)"
        />

        <!-- Pending permission dialog -->
        <PermissionDialog
          v-if="pendingPermission"
          :permission="pendingPermission"
          :session-id="activeTabId || ''"
        />
      </div>

      <!-- Selection menu portal -->
      <teleport to="body">
        <SelectionMenu
          v-if="selectionMenu"
          :selection="selectionMenu"
          :i18n-t="t"
          @add="addCurrentSelectionToChat"
        />
      </teleport>
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
      <span class="material-symbols-outlined" style="font-size: 16px; fontVariationSettings: 'FILL' 1">
        arrow_downward
      </span>
      <span>{{ t('chat.jumpToLatest') }}</span>
    </button>
  </div>
</template>

<style scoped>
.sprite-island-detail {
  margin: 0 0 12px;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-surface-container-lowest, #fff);
}
.sprite-island-detail__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 12px;
}
.sprite-island-detail__close {
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--color-text-tertiary);
  font-size: 16px;
  line-height: 1;
}
.sprite-island-detail__text {
  margin: 0;
  max-height: 160px;
  overflow: auto;
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--color-text-primary);
}
.sprite-island-detail__empty {
  margin: 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
</style>