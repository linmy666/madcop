/**
 * messageListUtils.ts — Pure utility functions extracted from MessageList.tsx
 * Used by both React and Vue MessageList components.
 */
import type { UIMessage } from '../../stores/chatStore'
import type { SessionTurnCheckpoint } from '../../api/sessions'

// ─── Type Aliases ────────────────────────────────────────────

export type ToolCall = Extract<UIMessage, { type: 'tool_use' }>
export type ToolResult = Extract<UIMessage, { type: 'tool_result' }>
export type MemoryEvent = Extract<UIMessage, { type: 'memory_event' }>
export type GoalEvent = Extract<UIMessage, { type: 'goal_event' }>
export type BackgroundTaskEvent = Extract<UIMessage, { type: 'background_task' }>
export type CompactSummaryEvent = Extract<UIMessage, { type: 'compact_summary' }>

export type RenderItem =
  | { kind: 'tool_group'; toolCalls: ToolCall[]; id: string }
  | { kind: 'message'; message: UIMessage }

export type RenderModel = {
  renderItems: RenderItem[]
  toolResultMap: Map<string, ToolResult>
  childToolCallsByParent: Map<string, ToolCall[]>
}

export type RewindTurnTarget = {
  messageId: string
  userMessageIndex: number
  content: string
  expectedContent: string
  attachments?: Extract<UIMessage, { type: 'user_text' }>['attachments']
}

export type BranchableMessageTarget = {
  uiMessageId: string
  transcriptMessageId: string
}

export type TurnChangeCardModel = {
  target: RewindTurnTarget
  checkpoint: SessionTurnCheckpoint
  workDir: string | null
  isLatest: boolean
}

export type VirtualRenderItemMetric = {
  signature: string
  contentWeight: number
  estimatedHeight: number
}

export type VirtualViewport = {
  scrollTop: number
  viewportHeight: number
}

export type VirtualTranscriptWindow = {
  enabled: boolean
  beforeHeight: number
  afterHeight: number
  items: Array<{ item: RenderItem; index: number }>
}

export type ChatMessageRole = 'user' | 'assistant'
export type ChatSelectionState = { text: string; x: number; y: number }
export type SelectionPointer = { clientX: number; clientY: number }

// ─── Constants ───────────────────────────────────────────────

export const SCROLL_BOTTOM_SENTINEL = 1_000_000_000
export const AUTO_SCROLL_BOTTOM_THRESHOLD_PX = 48
export const MAX_SCROLL_SNAPSHOTS = 100
export const VIRTUALIZE_MIN_RENDER_ITEMS = 120
export const VIRTUALIZE_MIN_CONTENT_CHARS = 120_000
export const TOUCH_H5_VIRTUALIZE_MIN_RENDER_ITEMS = 60
export const TOUCH_H5_VIRTUALIZE_MIN_CONTENT_CHARS = 60_000
export const VIRTUAL_OVERSCAN_PX = 1200
export const VIRTUAL_DEFAULT_VIEWPORT_HEIGHT = 720
export const VIRTUAL_MIN_ITEM_HEIGHT = 48
export const VIRTUAL_MAX_ITEM_HEIGHT = 24_000
export const CONTENT_RESIZE_FOLLOW_MIN_DELTA_PX = 2
export const VIRTUAL_SPACER_CHUNK_PX = 800
export const CHAT_SELECTION_MENU_OFFSET = 10
export const CHAT_SELECTION_MENU_WIDTH = 158
export const CHAT_SELECTION_MENU_HEIGHT = 44
export const CHAT_SCROLL_AREA_CLASS = [
  'chat-scroll-area',
  '[scrollbar-width:auto]',
  '[scrollbar-color:color-mix(in_srgb,var(--color-outline)_72%,transparent)_transparent]',
  '[&::-webkit-scrollbar]:w-2.5',
  '[&::-webkit-scrollbar-track]:bg-transparent',
  '[&::-webkit-scrollbar-thumb]:rounded-full',
  '[&::-webkit-scrollbar-thumb]:border-[3px]',
  '[&::-webkit-scrollbar-thumb]:border-transparent',
  '[&::-webkit-scrollbar-thumb]:bg-[color-mix(in_srgb,var(--color-outline)_74%,transparent)]',
  '[&::-webkit-scrollbar-thumb]:bg-clip-content',
  '[&::-webkit-scrollbar-thumb:hover]:border-2',
  '[&::-webkit-scrollbar-thumb:hover]:bg-[color-mix(in_srgb,var(--color-outline)_90%,transparent)]',
].join(' ')
export const CHAT_RENDER_ITEM_CLASS = ['chat-render-item'].join(' ')

export type SessionScrollSnapshot = { scrollTop: number; wasAtBottom: boolean }

export const sessionScrollSnapshots = new Map<string, SessionScrollSnapshot>()

// ─── DOM / Scroll helpers ────────────────────────────────────

export function isNearScrollBottom(element: HTMLElement): boolean {
  return (
    element.scrollHeight - element.scrollTop - element.clientHeight <=
    AUTO_SCROLL_BOTTOM_THRESHOLD_PX
  )
}

export function rememberSessionScroll(sessionId: string, element: HTMLElement): void {
  if (sessionScrollSnapshots.size >= MAX_SCROLL_SNAPSHOTS && !sessionScrollSnapshots.has(sessionId)) {
    const oldestSessionId = sessionScrollSnapshots.keys().next().value
    if (oldestSessionId) sessionScrollSnapshots.delete(oldestSessionId)
  }
  sessionScrollSnapshots.set(sessionId, {
    scrollTop: element.scrollTop,
    wasAtBottom: isNearScrollBottom(element),
  })
}

export function getBottomScrollTop(element: HTMLElement): number {
  return Math.max(0, element.scrollHeight - element.clientHeight)
}

export function setScrollTopWithoutLayoutRead(element: HTMLElement, scrollTop: number): void {
  element.scrollTop = Math.max(0, scrollTop)
}

export function setScrollToBottomWithoutLayoutRead(element: HTMLElement, behavior: ScrollBehavior): void {
  if (typeof element.scrollTo === 'function') {
    try {
      element.scrollTo({ top: SCROLL_BOTTOM_SENTINEL, behavior })
    } catch {
      element.scrollTo(0, SCROLL_BOTTOM_SENTINEL)
    }
  }
  element.scrollTop = SCROLL_BOTTOM_SENTINEL
  if (element.scrollTop === SCROLL_BOTTOM_SENTINEL) {
    element.scrollTop = getBottomScrollTop(element)
  }
}

export function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export function getRenderItemKey(item: RenderItem): string {
  return item.kind === 'tool_group' ? item.id : item.message.id
}

// ─── Content weight estimation ───────────────────────────────

function isRecordValue(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function getShallowStringWeight(value: unknown, depth = 0): number {
  if (typeof value === 'string') return value.length
  if (!value || depth > 1) return 0
  if (Array.isArray(value)) {
    return value.slice(0, 12).reduce((total, item) => total + getShallowStringWeight(item, depth + 1), 0)
  }
  if (!isRecordValue(value)) return 0
  let total = 0
  for (const item of Object.values(value).slice(0, 24)) {
    total += getShallowStringWeight(item, depth + 1)
    if (total >= VIRTUALIZE_MIN_CONTENT_CHARS) return total
  }
  return total
}

export function getMessageContentWeight(message: UIMessage): number {
  switch (message.type) {
    case 'user_text':
    case 'assistant_text':
    case 'thinking':
    case 'system':
      return message.content.length
    case 'tool_use':
      return getShallowStringWeight(message.input) + (message.partialInput?.length ?? 0)
    case 'tool_result':
      return getShallowStringWeight(message.content)
    case 'permission_request':
      return getShallowStringWeight(message.input) + (message.description?.length ?? 0)
    case 'error':
      return message.message.length
    case 'compact_summary':
      return message.title.length + (message.summary?.length ?? 0)
    case 'goal_event':
      return (message.objective?.length ?? 0) + (message.message?.length ?? 0)
    case 'memory_event':
      return (message.message?.length ?? 0) +
        message.files.reduce((total, file) => total + file.path.length + (file.summary?.length ?? 0), 0)
    case 'background_task':
      return getShallowStringWeight(message.task)
    case 'task_summary':
      return message.tasks.reduce((total, task) => total + task.subject.length + (task.activeForm?.length ?? 0), 0)
  }
}

export function getRenderItemContentWeight(item: RenderItem): number {
  if (item.kind === 'message') return getMessageContentWeight(item.message)
  return item.toolCalls.reduce((total, toolCall) => total + getMessageContentWeight(toolCall), 0)
}

// ─── Virtualization decision ─────────────────────────────────

export function shouldVirtualizeRenderItems(
  metrics: VirtualRenderItemMetric[],
  touchH5 = false,
): boolean {
  const minRenderItems = touchH5 ? TOUCH_H5_VIRTUALIZE_MIN_RENDER_ITEMS : VIRTUALIZE_MIN_RENDER_ITEMS
  const minContentChars = touchH5 ? TOUCH_H5_VIRTUALIZE_MIN_CONTENT_CHARS : VIRTUALIZE_MIN_CONTENT_CHARS
  if (metrics.length >= minRenderItems) return true
  let totalWeight = 0
  for (const metric of metrics) {
    totalWeight += metric.contentWeight
    if (totalWeight >= minContentChars) return true
  }
  return false
}

// ─── Height estimation ───────────────────────────────────────

function countLineBreaksCapped(content: string, maxLines: number): number {
  let lineBreaks = 0
  for (let index = 0; index < content.length; index += 1) {
    if (content.charCodeAt(index) === 10) {
      lineBreaks += 1
      if (lineBreaks >= maxLines) return lineBreaks
    }
  }
  return lineBreaks
}

function estimateTextHeight(content: string, baseHeight: number): number {
  const sample = content.length > 12_000 ? content.slice(0, 12_000) : content
  const sampledLineBreaks = countLineBreaksCapped(sample, 900)
  const explicitLines = content.length > sample.length
    ? Math.ceil((sampledLineBreaks + 1) * (content.length / sample.length))
    : sampledLineBreaks + 1
  const wrappedLines = Math.ceil(content.length / 76)
  const estimated = baseHeight + Math.max(explicitLines, wrappedLines) * 22
  return clampNumber(estimated, VIRTUAL_MIN_ITEM_HEIGHT, VIRTUAL_MAX_ITEM_HEIGHT)
}

export function estimateMessageHeight(message: UIMessage): number {
  switch (message.type) {
    case 'user_text':
      return estimateTextHeight(message.content, message.attachments?.length ? 140 : 74)
    case 'assistant_text':
      return estimateTextHeight(message.content, 96)
    case 'thinking':
      return estimateTextHeight(message.content, 88)
    case 'tool_use':
      return clampNumber(92 + Math.ceil(getMessageContentWeight(message) / 120) * 18, 72, 2200)
    case 'tool_result':
      return clampNumber(88 + Math.ceil(getMessageContentWeight(message) / 120) * 18, 64, 2200)
    case 'background_task':
    case 'goal_event':
    case 'memory_event':
    case 'permission_request':
    case 'task_summary':
      return 110
    case 'compact_summary':
      return message.summary
        ? clampNumber(92 + Math.ceil(message.summary.length / 90) * 20, 80, 1800)
        : 70
    case 'error':
    case 'system':
      return 64
  }
}

export function estimateRenderItemHeight(item: RenderItem): number {
  if (item.kind === 'message') return estimateMessageHeight(item.message)
  const textWeight = getRenderItemContentWeight(item)
  return clampNumber(92 + item.toolCalls.length * 78 + Math.ceil(textWeight / 140) * 16, 88, 2600)
}

// ─── Metric signatures ───────────────────────────────────────

export function getMessageMetricSignature(message: UIMessage): string {
  switch (message.type) {
    case 'user_text':
      return `${message.type}:${message.content.length}:${message.attachments?.length ?? 0}:${message.pending ? 1 : 0}`
    case 'assistant_text':
    case 'thinking':
    case 'system':
      return `${message.type}:${message.content.length}`
    case 'tool_use':
      return `${message.type}:${message.toolName}:${message.toolUseId}:${message.partialInput?.length ?? 0}:${message.isPending ? 1 : 0}:${message.status ?? ''}`
    case 'tool_result':
      return `${message.type}:${message.toolUseId}:${message.isError ? 1 : 0}`
    case 'compact_summary':
      return `${message.type}:${message.phase ?? ''}:${message.title.length}:${message.summary?.length ?? 0}`
    case 'goal_event':
      return `${message.type}:${message.action}:${message.status ?? ''}:${message.objective?.length ?? 0}:${message.message?.length ?? 0}`
    case 'memory_event':
      return `${message.type}:${message.event}:${message.files.length}:${message.message?.length ?? 0}`
    case 'background_task':
      return `${message.type}:${message.task.taskId}:${message.task.status}:${message.task.updatedAt}`
    case 'permission_request':
      return `${message.type}:${message.requestId}:${message.toolUseId ?? ''}:${message.description?.length ?? 0}`
    case 'error':
      return `${message.type}:${message.code}:${message.message.length}`
    case 'task_summary':
      return `${message.type}:${message.tasks.length}:${message.tasks.map((task) => task.id).join(',')}`
  }
}

export function getRenderItemMetricSignature(item: RenderItem): string {
  if (item.kind === 'message') return getMessageMetricSignature(item.message)
  return item.toolCalls.map(getMessageMetricSignature).join('|')
}

// ─── Virtual transcript window ───────────────────────────────

function findVirtualStartIndex(offsets: number[], target: number): number {
  let low = 0
  let high = offsets.length - 1
  while (low < high) {
    const mid = Math.floor((low + high) / 2)
    if ((offsets[mid + 1] ?? offsets[mid] ?? 0) < target) {
      low = mid + 1
    } else {
      high = mid
    }
  }
  return Math.max(0, low)
}

function findVirtualEndIndex(offsets: number[], target: number): number {
  let low = 0
  let high = offsets.length - 1
  while (low < high) {
    const mid = Math.floor((low + high) / 2)
    if ((offsets[mid] ?? 0) <= target) {
      low = mid + 1
    } else {
      high = mid
    }
  }
  return clampNumber(low + 1, 0, offsets.length - 1)
}

export function buildVirtualTranscriptWindow(
  renderItems: RenderItem[],
  itemKeys: string[],
  metrics: VirtualRenderItemMetric[],
  measuredHeights: Map<string, number>,
  viewport: VirtualViewport,
  overscanPx: number,
): VirtualTranscriptWindow {
  if (!shouldVirtualizeRenderItems(metrics)) {
    return {
      enabled: false,
      beforeHeight: 0,
      afterHeight: 0,
      items: renderItems.map((item, index) => ({ item, index })),
    }
  }

  const offsets = new Array<number>(renderItems.length + 1)
  offsets[0] = 0
  for (let index = 0; index < renderItems.length; index += 1) {
    const item = renderItems[index]!
    const measuredHeight = measuredHeights.get(itemKeys[index]!)
    const height = measuredHeight && measuredHeight > 0
      ? measuredHeight
      : metrics[index]?.estimatedHeight ?? estimateRenderItemHeight(item)
    offsets[index + 1] = offsets[index]! + height
  }

  const totalHeight = offsets[renderItems.length] ?? 0
  const viewportHeight = viewport.viewportHeight || VIRTUAL_DEFAULT_VIEWPORT_HEIGHT
  const maxScrollTop = Math.max(0, totalHeight - viewportHeight)
  const scrollTop = clampNumber(viewport.scrollTop, 0, maxScrollTop)
  const windowTop = Math.max(0, scrollTop - overscanPx)
  const windowBottom = Math.min(totalHeight, scrollTop + viewportHeight + overscanPx)
  const startIndex = findVirtualStartIndex(offsets, windowTop)
  const endIndex = Math.min(renderItems.length, findVirtualEndIndex(offsets, windowBottom))

  return {
    enabled: true,
    beforeHeight: offsets[startIndex] ?? 0,
    afterHeight: totalHeight - (offsets[endIndex] ?? totalHeight),
    items: renderItems.slice(startIndex, endIndex).map((item, offset) => ({
      item,
      index: startIndex + offset,
    })),
  }
}

// ─── Selection / pointer helpers ─────────────────────────────

export function getElementForNode(node: Node | null): Element | null {
  if (!node) return null
  return node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement
}

export function getSelectionPointer(event: SelectionPointer): SelectionPointer {
  return { clientX: event.clientX, clientY: event.clientY }
}

export function getChatSelectionFromContainer(
  root: HTMLElement | null,
  pointer: SelectionPointer,
): ChatSelectionState | null {
  if (!root) return null
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return null

  const range = selection.getRangeAt(0)
  const startElement = getElementForNode(range.startContainer)
  const endElement = getElementForNode(range.endContainer)
  if (!startElement || !endElement || !root.contains(startElement) || !root.contains(endElement)) {
    return null
  }

  const text = selection.toString().trim()
  if (!text) return null

  return {
    x: pointer.clientX,
    y: pointer.clientY,
    text,
  }
}

// ─── Render model builder ────────────────────────────────────

function isAgentBackgroundTaskMessage(message: UIMessage): boolean {
  if (message.type !== 'background_task') return false
  if (message.task.taskType === 'local_agent' || message.task.taskType === 'remote_agent') return true
  return /^Agent (?:(?:"[^"]+" )?(completed|was stopped)|(?:"[^"]+" )?failed(?::|$))/.test(
    message.task.summary ?? '',
  )
}

function appendChildToolCall(
  childToolCallsByParent: Map<string, ToolCall[]>,
  parentToolUseId: string,
  toolCall: ToolCall,
): void {
  const siblings = childToolCallsByParent.get(parentToolUseId)
  if (siblings) {
    siblings.push(toolCall)
  } else {
    childToolCallsByParent.set(parentToolUseId, [toolCall])
  }
}

export function buildRenderModel(
  messages: UIMessage[],
  activeAskUserQuestionToolUseId?: string | null,
): RenderModel {
  const items: RenderItem[] = []
  const toolResultMap = new Map<string, ToolResult>()
  const childToolCallsByParent = new Map<string, ToolCall[]>()
  const toolUseIds = new Set<string>()
  const lastUnresolvedAskUserQuestionIndexByToolUseId = new Map<string, number>()
  let lastUnresolvedAskUserQuestionIndex: number | null = null
  let pendingToolCalls: ToolCall[] = []

  const flushGroup = () => {
    if (pendingToolCalls.length > 0) {
      items.push({
        kind: 'tool_group',
        toolCalls: [...pendingToolCalls],
        id: `group-${pendingToolCalls[0]!.id}`,
      })
      pendingToolCalls = []
    }
  }

  const appendRootToolCall = (toolCall: ToolCall) => {
    const nextIsAgent = toolCall.toolName === 'Agent'
    const pendingIsAgentGroup = pendingToolCalls.every((pendingToolCall) => pendingToolCall.toolName === 'Agent')
    if (pendingToolCalls.length > 0 && pendingIsAgentGroup !== nextIsAgent) {
      flushGroup()
    }
    pendingToolCalls.push(toolCall)
  }

  for (const msg of messages) {
    if (msg.type === 'tool_use') toolUseIds.add(msg.toolUseId)
    if (msg.type === 'tool_result') toolResultMap.set(msg.toolUseId, msg)
  }

  messages.forEach((msg, index) => {
    if (
      msg.type === 'tool_use' &&
      msg.toolName === 'AskUserQuestion' &&
      !toolResultMap.has(msg.toolUseId)
    ) {
      lastUnresolvedAskUserQuestionIndexByToolUseId.set(msg.toolUseId, index)
      lastUnresolvedAskUserQuestionIndex = index
    }
  })

  for (const msg of messages) {
    if (msg.type === 'assistant_text' && !msg.content.trim()) continue
    if (isAgentBackgroundTaskMessage(msg)) continue
    if (msg.type === 'tool_result' && toolUseIds.has(msg.toolUseId)) continue
    if (msg.type === 'tool_result' && msg.parentToolUseId && toolUseIds.has(msg.parentToolUseId)) continue

    if (msg.type === 'tool_use') {
      if (msg.parentToolUseId && toolUseIds.has(msg.parentToolUseId)) {
        flushGroup()
        appendChildToolCall(childToolCallsByParent, msg.parentToolUseId, msg)
        continue
      }
      if (msg.toolName === 'AskUserQuestion') {
        const isResolved = toolResultMap.has(msg.toolUseId)
        const lastUnresolvedIndex = lastUnresolvedAskUserQuestionIndexByToolUseId.get(msg.toolUseId)
        if (!isResolved && lastUnresolvedIndex !== undefined && messages[lastUnresolvedIndex] !== msg) continue
        if (!isResolved && activeAskUserQuestionToolUseId && msg.toolUseId !== activeAskUserQuestionToolUseId) continue
        if (!isResolved && !activeAskUserQuestionToolUseId && lastUnresolvedAskUserQuestionIndex !== null && messages[lastUnresolvedAskUserQuestionIndex] !== msg) continue
        flushGroup()
        items.push({ kind: 'message', message: msg })
      } else {
        appendRootToolCall(msg)
      }
    } else {
      flushGroup()
      items.push({ kind: 'message', message: msg })
    }
  }

  flushGroup()
  return { renderItems: items, toolResultMap, childToolCallsByParent }
}

// ─── Branchable / turn targets ───────────────────────────────

function isTurnResponseMessage(message: UIMessage): boolean {
  return (
    message.type === 'assistant_text' ||
    message.type === 'tool_use' ||
    message.type === 'tool_result' ||
    (message.type === 'background_task' && !isAgentBackgroundTaskMessage(message)) ||
    message.type === 'error' ||
    message.type === 'task_summary'
  )
}

export function getBranchableMessageTargets(messages: UIMessage[]): Map<string, BranchableMessageTarget> {
  const branchableTargets = new Map<string, BranchableMessageTarget>()
  let currentTurnCandidates: Array<Extract<UIMessage, { type: 'user_text' | 'assistant_text' }>> = []
  let hasResponseForCurrentTurn = false

  const markCurrentTurnBranchable = () => {
    if (!hasResponseForCurrentTurn) return
    for (const candidate of currentTurnCandidates) {
      if (!candidate.transcriptMessageId) continue
      branchableTargets.set(candidate.id, {
        uiMessageId: candidate.id,
        transcriptMessageId: candidate.transcriptMessageId,
      })
    }
  }

  for (const message of messages) {
    if (message.type === 'user_text') {
      markCurrentTurnBranchable()
      currentTurnCandidates = []
      hasResponseForCurrentTurn = false
      if (!message.pending && message.transcriptMessageId) {
        currentTurnCandidates = [message]
      }
      continue
    }
    if (currentTurnCandidates.length === 0) continue
    if (isTurnResponseMessage(message)) hasResponseForCurrentTurn = true
    if (message.type === 'assistant_text' && message.transcriptMessageId) {
      currentTurnCandidates.push(message)
    }
  }
  markCurrentTurnBranchable()
  return branchableTargets
}

export function getCompletedTurnTargets(messages: UIMessage[]): RewindTurnTarget[] {
  let userMessageIndex = -1
  const completedTurns: RewindTurnTarget[] = []
  let currentTarget: RewindTurnTarget | null = null
  let hasResponseForCurrentTarget = false

  for (const message of messages) {
    if (message.type === 'user_text' && !message.pending) {
      if (currentTarget && hasResponseForCurrentTarget) {
        completedTurns.push(currentTarget)
      }
      userMessageIndex += 1
      currentTarget = {
        messageId: message.id,
        userMessageIndex,
        content: message.content,
        expectedContent: message.modelContent ?? message.content,
        attachments: message.attachments,
      }
      hasResponseForCurrentTarget = false
      continue
    }
    if (currentTarget && isTurnResponseMessage(message)) {
      hasResponseForCurrentTarget = true
    }
  }
  if (currentTarget && hasResponseForCurrentTarget) {
    completedTurns.push(currentTarget)
  }
  return completedTurns
}

export function getLatestCompletedTurnTarget(messages: UIMessage[]): RewindTurnTarget | null {
  const completedTurns = getCompletedTurnTargets(messages)
  return completedTurns.length > 0 ? completedTurns[completedTurns.length - 1] ?? null : null
}

// ─── Turn card insertion map ─────────────────────────────────

export function buildTurnCardInsertionMap(
  renderItems: RenderItem[],
  turnChangeCards: TurnChangeCardModel[],
): Map<number, TurnChangeCardModel[]> {
  const lastResponseIndexByTurnId = new Map<string, number>()
  const userIndexByTurnId = new Map<string, number>()
  let activeTurnId: string | null = null

  renderItems.forEach((item, index) => {
    if (item.kind === 'message' && item.message.type === 'user_text' && !item.message.pending) {
      activeTurnId = item.message.id
      userIndexByTurnId.set(activeTurnId, index)
      return
    }
    if (activeTurnId) {
      lastResponseIndexByTurnId.set(activeTurnId, index)
    }
  })

  const cardsByRenderIndex = new Map<number, TurnChangeCardModel[]>()
  turnChangeCards.forEach((card) => {
    const renderIndex =
      lastResponseIndexByTurnId.get(card.target.messageId) ??
      userIndexByTurnId.get(card.target.messageId)
    if (renderIndex === undefined) return
    const existing = cardsByRenderIndex.get(renderIndex)
    if (existing) {
      existing.push(card)
    } else {
      cardsByRenderIndex.set(renderIndex, [card])
    }
  })
  return cardsByRenderIndex
}

/**
 * Map each render item to the REAL changed files of the turn it belongs to.
 */
export function buildChangedFilesByRenderIndex(
  renderItems: RenderItem[],
  turnChangeCards: TurnChangeCardModel[],
): Map<number, string[]> {
  const filesByTurnId = new Map<string, string[]>()
  for (const card of turnChangeCards) {
    if (card.checkpoint.code.filesChanged.length > 0) {
      filesByTurnId.set(card.target.messageId, card.checkpoint.code.filesChanged)
    }
  }
  if (filesByTurnId.size === 0) return new Map()

  const filesByRenderIndex = new Map<number, string[]>()
  let activeTurnId: string | null = null
  renderItems.forEach((item, index) => {
    if (item.kind === 'message' && item.message.type === 'user_text' && !item.message.pending) {
      activeTurnId = item.message.id
      return
    }
    if (activeTurnId) {
      const files = filesByTurnId.get(activeTurnId)
      if (files) filesByRenderIndex.set(index, files)
    }
  })
  return filesByRenderIndex
}

// ─── Compact summary / goal event helpers ────────────────────

export function getCompactSummaryTitle(
  message: CompactSummaryEvent | undefined,
  t: (key: string, params?: Record<string, string | number>) => string,
): string {
  if (!message) return t('chat.compactSummary.title')
  if (message.trigger === 'auto') return t('chat.compactSummary.autoTitle')
  if (message.trigger === 'manual') return t('chat.compactSummary.manualTitle')
  if (!message.title || message.title === 'Context compacted' || message.title === 'Conversation compacted') {
    return t('chat.compactSummary.title')
  }
  return message.title
}

// ─── Background task helpers ─────────────────────────────────

export function formatBackgroundTaskDuration(durationMs?: number): string | null {
  if (typeof durationMs !== 'number' || durationMs < 0) return null
  const seconds = Math.round(durationMs / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m ${seconds % 60}s`
}

export function getBackgroundTaskLabel(
  taskType: string | undefined,
  t: (key: string, params?: Record<string, string | number>) => string,
): string {
  if (taskType === 'local_bash') return t('chat.backgroundTasks.command')
  if (taskType === 'local_workflow') return t('chat.backgroundTasks.workflow')
  return t('chat.backgroundTasks.task')
}

// ─── Memory helpers ──────────────────────────────────────────

export function memoryFileLabel(path: string): string {
  const normalized = path.replace(/\\/g, '/')
  return normalized.split('/').pop() || normalized
}

// ─── API error helper ────────────────────────────────────────

import { ApiError } from '../../api/client'

export function getApiErrorMessage(error: unknown): string {
  return error instanceof ApiError
    ? typeof error.body === 'object' && error.body && 'message' in error.body
      ? String((error.body as { message: unknown }).message)
      : error.message
    : error instanceof Error
      ? error.message
      : String(error)
}

export function isSessionTurnCheckpoint(value: unknown): value is SessionTurnCheckpoint {
  if (!value || typeof value !== 'object') return false
  const checkpoint = value as Partial<SessionTurnCheckpoint>
  return (
    Boolean(checkpoint.target) &&
    typeof checkpoint.target?.targetUserMessageId === 'string' &&
    typeof checkpoint.target?.userMessageIndex === 'number' &&
    Boolean(checkpoint.code) &&
    typeof checkpoint.code?.available === 'boolean' &&
    Array.isArray(checkpoint.code?.filesChanged)
  )
}

export function normalizeTurnCheckpoints(response: unknown): SessionTurnCheckpoint[] {
  if (!response || typeof response !== 'object') return []
  const checkpoints = (response as { checkpoints?: unknown }).checkpoints
  if (!Array.isArray(checkpoints)) return []
  return checkpoints.filter(isSessionTurnCheckpoint)
}