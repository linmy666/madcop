import { defineStore } from 'pinia'

/**
 * Pinia mirror of stores/chatStore.ts (3341 lines)
 * Per-session chat state management — messages, streaming, composer, permissions.
 * 
 * Simplified: WebSocket/streaming internals removed. Provides the same
 * public API shape that ChatInput and other components use.
 * All methods are available; WebSocket-dependent ones are no-ops or
 * work with in-memory state.
 */

// ─── Types ───────────────────────────────────────────────────────────

export type ChatState = 'idle' | 'busy' | 'error' | 'stopped'
export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'

export interface TokenUsage { input_tokens: number; output_tokens: number }
export interface AttachmentRef { id: string; name: string; path?: string; type?: string }
export interface UIAttachment { id: string; name: string; type: string; path?: string }
export interface PermissionUpdate { toolName: string; allowed: boolean }
export interface RuntimeSelection { providerId: string; modelId: string; effortLevel: string }
export interface PermissionMode {}

export type ServerMessage = Record<string, unknown>
export type AgentTaskNotification = Record<string, unknown>
export type BackgroundAgentTask = Record<string, unknown>
export type ActiveGoalState = Record<string, unknown> | null
export type ComputerUsePermissionRequest = Record<string, unknown>
export type ComputerUsePermissionResponse = Record<string, unknown>

export type UIMessage =
  | { type: 'user'; content: string; attachments?: AttachmentRef[]; id: string; timestamp: number }
  | { type: 'assistant_text'; content: string; id: string; timestamp: number; model?: string }
  | { type: 'tool_use'; toolUseId: string; toolName: string; input: unknown; id: string; timestamp: number; isPending?: boolean; status?: string }
  | { type: 'tool_result'; toolUseId: string; result: string; id: string; timestamp: number }
  | { type: 'thinking'; thinkingId: string; content: string; id: string; timestamp: number }
  | { type: 'compact_summary'; summary: string; id: string; timestamp: number }

export type ComposerAttachment = {
  id: string
  name: string
  type: 'file' | 'image' | 'text'
  path?: string
  isDirectory?: boolean
  lineStart?: number
  lineEnd?: number
  note?: string
  quote?: string
}

export type ComposerDraftState = {
  input: string
  attachments: ComposerAttachment[]
}

export type QueuedUserMessage = {
  id: string
  content: string
  attachments?: AttachmentRef[]
  displayContent: string
  displayAttachments?: AttachmentRef[]
  createdAt: number
}

export type ComposerReferenceInsertion = {
  text: string
  reference?: { kind: 'file'; path: string; name: string; isDirectory?: boolean }
  nonce: number
}

export type ComposerPrefillMode = 'replace' | 'append'

export type ApiRetryState = { attempt: number; maxRetries: number } | null
export type StreamingFallbackState = { reason: string } | null

export type PerSessionState = {
  messages: UIMessage[]
  chatState: ChatState
  connectionState: ConnectionState
  historyStatus?: 'idle' | 'loading' | 'ready' | 'error'
  historyError?: string | null
  streamingText: string
  streamingToolInput: string
  activeToolUseId: string | null
  activeToolName: string | null
  activeThinkingId: string | null
  pendingPermission: {
    requestId: string
    toolName: string
    toolUseId?: string
    input: unknown
    description?: string
  } | null
  pendingComputerUsePermission: {
    requestId: string
    request: ComputerUsePermissionRequest
  } | null
  pendingClarification?: {
    toolUseId: string
    question: string
    options: string[]
    allowFreeText: boolean
  } | null
  tokenUsage: TokenUsage
  compactCount?: number
  streamingResponseChars: number
  elapsedSeconds: number
  statusVerb: string
  thinkingStage?: string | null
  apiRetry?: ApiRetryState | null
  streamingFallback?: StreamingFallbackState | null
  slashCommands: Array<{ name: string; description: string; argumentHint?: string }>
  agentTaskNotifications: Record<string, AgentTaskNotification>
  backgroundAgentTasks?: Record<string, BackgroundAgentTask>
  activeGoal?: ActiveGoalState | null
  composerPrefill?: {
    text: string
    attachments?: UIAttachment[]
    mode?: ComposerPrefillMode
    nonce: number
  } | null
  composerInsertion?: ComposerReferenceInsertion | null
  composerDraft?: ComposerDraftState | null
  queuedUserMessages?: QueuedUserMessage[]
}

function createDefaultSessionState(): PerSessionState {
  return {
    messages: [],
    chatState: 'idle',
    connectionState: 'disconnected',
    historyStatus: 'idle',
    historyError: null,
    streamingText: '',
    streamingToolInput: '',
    activeToolUseId: null,
    activeToolName: null,
    activeThinkingId: null,
    pendingPermission: null,
    pendingComputerUsePermission: null,
    pendingClarification: null,
    tokenUsage: { input_tokens: 0, output_tokens: 0 },
    compactCount: 0,
    streamingResponseChars: 0,
    elapsedSeconds: 0,
    statusVerb: '',
    thinkingStage: null,
    apiRetry: null,
    streamingFallback: null,
    slashCommands: [
      { name: '/new', description: 'Start a new chat session' },
      { name: '/stop', description: 'Stop the current generation' },
      { name: '/settings', description: 'Open settings' },
      { name: '/compact', description: 'Compact the session history' },
    ],
    agentTaskNotifications: {},
    backgroundAgentTasks: {},
    activeGoal: null,
    composerPrefill: null,
    composerInsertion: null,
    composerDraft: null,
    queuedUserMessages: [],
  }
}

let msgCounter = 0
const nextId = () => `msg-${++msgCounter}-${Date.now()}`

// ─── Store ───────────────────────────────────────────────────────────

export const useChatStore = defineStore('chat', {
  state: () => ({
    sessions: {} as Record<string, PerSessionState>,
  }),

  actions: {
    getSession(sessionId: string): PerSessionState {
      if (this.sessions[sessionId]) return this.sessions[sessionId]
      // Create a fresh session state on first access
      this.sessions[sessionId] = createDefaultSessionState()
      return this.sessions[sessionId]
    },

    /**
     * Connect to a session (simplified — no WebSocket setup here).
     * Components should not call this directly; it's a no-op in the
     * Pinia layer. The real WebSocket logic lives in the React store.
     */
    connectToSession(_sessionId: string) {
      // No-op: WebSocket connection handled elsewhere
    },

    disconnectSession(sessionId: string) {
      if (this.sessions[sessionId]) {
        this.sessions[sessionId].connectionState = 'disconnected'
        this.sessions[sessionId].chatState = 'idle'
      }
    },

    sendMessage(
      sessionId: string,
      content: string,
      _attachments?: AttachmentRef[],
      _options?: { displayContent?: string; displayAttachments?: AttachmentRef[]; hideDisplayContent?: boolean },
    ) {
      const session = this.getSession(sessionId)
      session.chatState = 'busy'
      // Add the user message
      const userMsg: UIMessage = {
        type: 'user',
        content,
        attachments: _attachments,
        id: nextId(),
        timestamp: Date.now(),
      }
      session.messages.push(userMsg)
      // Clear composer state
      session.composerPrefill = null
      session.composerInsertion = null
    },

    stopGeneration(sessionId: string) {
      const session = this.sessions[sessionId]
      if (!session) return
      session.chatState = 'stopped'
      session.streamingText = ''
      session.streamingToolInput = ''
      session.activeToolUseId = null
      session.activeToolName = null
      session.activeThinkingId = null
    },

    respondToPermission(_sessionId: string, _requestId: string, _allowed: boolean, _options?: any) {
      // No-op: permission handling is WebSocket-bound
    },

    respondToComputerUsePermission(_sessionId: string, _requestId: string, _response: ComputerUsePermissionResponse) {
      // No-op: computer use permission handling
    },

    setSessionRuntime(_sessionId: string, _selection: RuntimeSelection) {
      // No-op: runtime selection is handled by sessionRuntimeStore
    },

    setSessionPermissionMode(_sessionId: string, _mode: string) {
      // No-op: permission mode is in sessionStore
    },

    async loadHistory(_sessionId: string) {
      // No-op: history loading is WebSocket-bound
    },

    async reloadHistory(_sessionId: string) {
      // No-op: history reload
    },

    queueComposerPrefill(
      sessionId: string,
      prefill: { text: string; attachments?: UIAttachment[]; mode?: ComposerPrefillMode },
    ) {
      const session = this.getSession(sessionId)
      session.composerPrefill = {
        text: prefill.text,
        attachments: prefill.attachments,
        mode: prefill.mode ?? 'replace',
        nonce: Date.now(),
      }
    },

    clearComposerPrefill(sessionId: string, _nonce?: number) {
      const session = this.sessions[sessionId]
      if (session) session.composerPrefill = null
    },

    queueComposerInsertion(
      sessionId: string,
      insertion: Omit<ComposerReferenceInsertion, 'nonce'>,
    ) {
      const session = this.getSession(sessionId)
      session.composerInsertion = {
        text: insertion.text,
        reference: insertion.reference,
        nonce: Date.now(),
      }
    },

    clearComposerInsertion(sessionId: string, _nonce?: number) {
      const session = this.sessions[sessionId]
      if (session) session.composerInsertion = null
    },

    setComposerDraft(sessionId: string, draft: ComposerDraftState) {
      const session = this.getSession(sessionId)
      session.composerDraft = draft
    },

    clearComposerDraft(sessionId: string) {
      const session = this.sessions[sessionId]
      if (session) session.composerDraft = null
    },

    queueUserMessage(
      sessionId: string,
      message: Omit<QueuedUserMessage, 'id' | 'createdAt'>,
    ): string {
      const id = nextId()
      const session = this.getSession(sessionId)
      if (!session.queuedUserMessages) session.queuedUserMessages = []
      session.queuedUserMessages.push({
        ...message,
        id,
        createdAt: Date.now(),
      })
      return id
    },

    updateQueuedUserMessage(sessionId: string, messageId: string, content: string) {
      const session = this.sessions[sessionId]
      if (!session?.queuedUserMessages) return
      const msg = session.queuedUserMessages.find(m => m.id === messageId)
      if (msg) {
        msg.content = content
        msg.displayContent = content
      }
    },

    removeQueuedUserMessage(sessionId: string, messageId: string) {
      const session = this.sessions[sessionId]
      if (!session?.queuedUserMessages) return
      session.queuedUserMessages = session.queuedUserMessages.filter(m => m.id !== messageId)
    },

    sendQueuedUserMessage(sessionId: string, messageId: string) {
      const session = this.sessions[sessionId]
      if (!session?.queuedUserMessages) return
      const msg = session.queuedUserMessages.find(m => m.id === messageId)
      if (msg) {
        this.sendMessage(sessionId, msg.content, msg.attachments, {
          displayContent: msg.displayContent,
          displayAttachments: msg.displayAttachments,
        })
        session.queuedUserMessages = session.queuedUserMessages.filter(m => m.id !== messageId)
      }
    },

    clearMessages(sessionId: string) {
      const session = this.sessions[sessionId]
      if (!session) return
      session.messages = []
      session.chatState = 'idle'
      session.streamingText = ''
      session.streamingToolInput = ''
      session.activeToolUseId = null
      session.activeToolName = null
      session.activeThinkingId = null
      session.tokenUsage = { input_tokens: 0, output_tokens: 0 }
    },

    handleServerMessage(_sessionId: string, _msg: ServerMessage) {
      // No-op: server message handling is WebSocket-bound
    },
  },
})
