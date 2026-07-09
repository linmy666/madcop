import { defineStore } from 'pinia'
import { deriveSessionTitle, isPlaceholderTitle } from '../lib/autoTitle'
import { saveToStorage } from './sessionStore'
import { useSessionStore } from './sessionStore'
import { getApiUrl } from '../api/client'

// v3.0: local persistence for per-session messages. The chat API
// doesn't round-trip every send (we keep state in memory) so without
// this, reloading the app forgets every conversation. The payload is
// small (a few MB even with big threads) so a single localStorage
// key per session is fine.
const MESSAGES_STORAGE_KEY = 'madcop_chat_messages'

function loadMessagesFromStorage(): Record<string, { messages: any[]; title?: string }> {
  try {
    const raw = localStorage.getItem(MESSAGES_STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {}
  return {}
}

function saveMessagesToStorage(data: Record<string, { messages: any[]; title?: string }>) {
  try {
    localStorage.setItem(MESSAGES_STORAGE_KEY, JSON.stringify(data))
  } catch (err) {
    // QuotaExceededError: drop oldest entries until it fits.
    const keys = Object.keys(data)
    if (keys.length > 1) {
      keys
        .sort((a, b) => {
          const ta = data[a]?.messages?.length ?? 0
          const tb = data[b]?.messages?.length ?? 0
          return ta - tb
        })
        .slice(0, Math.max(1, Math.floor(keys.length / 2)))
        .forEach((k) => delete data[k])
      try {
        localStorage.setItem(MESSAGES_STORAGE_KEY, JSON.stringify(data))
      } catch {}
    }
  }
}

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
  /** Display title for this session (shown in tab + sidebar). */
  title?: string
  /** Pending clarification from the LLM (ambiguous query). */
  clarificationPending?: { question: string; options: string[] } | null
  /** Skip the rest of the current SSE text stream (after clarify/choices JSON). */
  skipResponse?: boolean
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
  reasoningContent?: string | null
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
    reasoningContent: null,
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
      _persistSession(sessionId: string) {
      // v3.0: write the current messages + title to localStorage so
      // the user can see their old threads after a reload. Triggered
      // after every user message and on store init.
      const s = this.sessions[sessionId]
      if (!s) return
      const data = loadMessagesFromStorage()
      data[sessionId] = {
        messages: s.messages,
        title: s.title,
      }
      saveMessagesToStorage(data)
    },
    getSession(sessionId: string): PerSessionState {
      const existing = this.sessions[sessionId]
      // v3.0: hydrate from localStorage if we have no in-memory
      // messages yet but the storage does. This covers the case
      // where the user reloads the app — the session id is known
      // (e.g. from a tab) but the messages haven't been pulled in.
      if (existing) {
        if ((existing.messages?.length ?? 0) === 0) {
          const stored = loadMessagesFromStorage()[sessionId]
          if (stored?.messages?.length) {
            this.sessions[sessionId] = {
              ...existing,
              messages: stored.messages as any,
              title: stored.title ?? existing.title,
            }
            return this.sessions[sessionId]
          }
        }
        return existing
      }
      // Create a fresh session state on first access; hydrate from
      // localStorage if we have a previously-saved thread for this id.
      const stored = loadMessagesFromStorage()[sessionId]
      const state = createDefaultSessionState() as PerSessionState
      if (stored) {
        if (Array.isArray(stored.messages)) state.messages = stored.messages as any
        if (stored.title) state.title = stored.title
      }
      this.sessions[sessionId] = state
      return this.sessions[sessionId]
    },

    /**
     * Connect to a session (simplified — no WebSocket setup here).
     * Components should not call this directly; it's a no-op in the
     * Pinia layer. The real WebSocket logic lives in the React store.
     */
    connectToSession(sessionId: string) {
      // v3.0: ensure the per-session state exists in the store. The
      // first call hydrates from localStorage (so old threads show
      // up on reload); subsequent calls are no-ops.
      this.getSession(sessionId)
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
        type: 'user_text',
        content,
        attachments: _attachments,
        id: nextId(),
        timestamp: Date.now(),
      }
      session.messages.push(userMsg)
      // v3.0: persist after each user message so reloads keep the
      // thread visible. Cheap because we only write on local edits.
      this._persistSession(sessionId)

      // Auto-derive session title from the first user message.
      // Use a small debounce so rapid follow-up messages don't thrash the title.
      // (Only re-titles if the current title is the placeholder.)
      if (isPlaceholderTitle(this.sessions[sessionId]?.title)) {
        const derived = deriveSessionTitle(content)
        if (derived) {
          session.title = derived
          // Also update sessionStore so sidebar sees the new title.
          // Use this.$pinia to get sessionStore without circular deps.
          try {
            const ss = useSessionStore(this.$pinia)
            ss.updateSessionTitle(sessionId, derived)
          } catch {}
        }
      }
      // Clear composer state
      session.composerPrefill = null
      session.composerInsertion = null
      
      // Call the backend API
      const apiUrl = 'http://127.0.0.1:8765/api/chat'
      // v3.0: include the locally-cached message history so the
      // backend LLM can see context. Without this, after a reload
      // the assistant thinks the user is starting a new chat because
      // the backend never received the prior messages.
      const history = (session.messages || [])
        .filter((m: any) => m && (m.type === 'user_text' || m.type === 'assistant_text'))
        .map((m: any) => ({ role: m.role || (m.type === 'user_text' ? 'user' : 'assistant'), content: m.content || '' }))
        // Cap at the last 20 messages to keep the request small
        .slice(-20)
      // v3.0: auto-router + workspace + tools system prompt
      const ws = (() => { try { return localStorage.getItem('madcop_workspace_dir') || '' } catch { return '' } })()
      const toolUsePrompt = `你有以下工具可供使用：web_search（联网搜索）、web_fetch（抓取网页内容）、weather（查天气）、clarify（向用户追问）、read_file（读取文件）、write_file（写入文件）、edit_file（编辑文件）。当用户让你做任何需要实时信息的事情时，你必须调用 web_search 工具，不要自己编造答案。直接调用工具，不要输出工具的参数描述。`
      const sysBase = ws ? `当前用户的工作目录是 ${ws}。当用户要求保存文件、生成报告、写入代码等操作时，请将文件保存在该目录下。` : `当前用户的工作目录是当前目录。当用户要求保存文件时，请保存在当前目录下。`
      const sysMsg = `${sysBase}\n\n${toolUsePrompt}`
      const requestMessages = [{ role: 'system', content: sysMsg }, ...history, { role: 'user', content }]
      fetch(apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'glm-5.2',
          messages: requestMessages,
          attachments: _attachments?.map((a) => ({
            id: a.id,
            name: a.name,
            type: a.type,
            path: a.path,
            dataUrl: (a as any).previewUrl || (a as any).data,
          })),
          temperature: 0.7,
          max_tokens: 8192,
        }),
      })
        .then(async (res) => {
          if (!res.ok) {
            session.chatState = 'error'
            return
          }
          // Read the SSE stream
          const reader = res.body?.getReader()
          if (!reader) {
            session.chatState = 'error'
            return
          }
          session.reasoningContent = null
          const decoder = new TextDecoder()
          let buffer = ''
          let assistantMsg = ''
          const assistantId = nextId()
          // Don't push assistant placeholder here — wait until first 'text'
          // event so tool_use messages that arrive earlier are placed before
          // the assistant message in the timeline.
          let assistantPushed = false

          const ensureAssistantPushed = () => {
            if (assistantPushed) return
            assistantPushed = true
            session.messages.push({
              type: 'assistant_text',
              content: assistantMsg,
              id: assistantId,
              timestamp: Date.now(),
            })
          }
          
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })
            
            // Parse SSE events
            const lines = buffer.split('\n')
            buffer = lines.pop() || ''
            
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const event = JSON.parse(line.slice(6))
                                    if (event.type === 'text' && event.content) {
                    // Push the assistant placeholder NOW (after any tool_use
                    // messages have already been pushed) so the timeline is
                    // tool → assistant instead of assistant → tool.
                    ensureAssistantPushed()
                    assistantMsg += event.content
                    // Update the placeholder message
                    const msg = session.messages.find((m: any) => m.id === assistantId)
                    if (msg) msg.content = assistantMsg
                  } else if (event.type === 'done') {
                    session.chatState = 'idle'
                    // Update the final message
                    const msg = session.messages.find((m: any) => m.id === assistantId)
                    if (msg) msg.content = assistantMsg
                  } else if (event.type === 'reasoning' && event.content) {
                    session.reasoningContent = (session.reasoningContent || '') + event.content
                  } else if (event.type === 'tool' && event.name) {
                    // AI is calling a tool — show it transparently under the
                    // thinking indicator so the user can see what's happening.
                    const toolMsg: UIMessage = {
                      type: 'tool_use',
                      toolUseId: event.tool_use_id || `tool-${Date.now()}-${Math.random()}`,
                      toolName: event.name,
                      input: event.args,
                      id: nextId(),
                      timestamp: Date.now(),
                      isPending: true,
                    }
                    session.messages.push(toolMsg)
                  } else if (event.type === 'tool_result') {
                    // Tool returned — pair it with the matching pending
                    // tool_use and mark it as resolved so the UI shows ✓
                    // instead of "正在准备工具".
                    const prev = session.messages.find((m: any) =>
                      m.type === 'tool_use' && m.isPending === true
                    )
                    if (prev) {
                      prev.isPending = false
                      ;(prev as any).result = event.result
                    } else {
                      // Orphan result (no matching pending tool_use)
                      session.messages.push({
                        type: 'tool_result',
                        toolUseId: `result-${Date.now()}`,
                        result: event.result,
                        id: nextId(),
                        timestamp: Date.now(),
                      })
                    }
                  } else if (event.type === 'session_title' && event.title) {
                    // Backend-generated Claude-style title — replace the local
                    // heuristic title with a more meaningful one.
                    this.sessions[sessionId].title = event.title
                    try {
                      const ss = useSessionStore()
                      ss.updateSessionTitle(sessionId, event.title)
                    } catch {}
                  }
                } catch {}
              }
            }
          }
          session.chatState = 'idle'
        })
        .catch(() => {
          session.chatState = 'error'
        })
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

    async loadHistory(sessionId: string) {
      // v3.0: actually fetch the session's message history from the
      // backend. This is the entry point ActiveSession calls when the
      // user switches to a session that hasn't been hydrated yet.
      //
      // Hydration order matters: we read localStorage first so that
      // locally-cached threads (from a previous session) take
      // precedence over the backend's (likely empty) list, and we
      // don't clobber them with an empty array.
      const existing = this.sessions[sessionId]
      if (!existing) {
        // No in-memory state yet — hydrate from localStorage so the
        // user sees their old thread, and mark historyStatus as 'ready'
        // since we're not actually going to overwrite with backend data.
        const stored = loadMessagesFromStorage()[sessionId]
        if (stored?.messages?.length) {
          this.sessions[sessionId] = {
            ...(createDefaultSessionState() as PerSessionState),
            messages: stored.messages as any,
            title: stored.title ?? '新对话',
            historyStatus: 'ready',
          }
          return
        }
        // Nothing in localStorage either; create an empty state and
        // try the backend as a last resort.
        this.sessions[sessionId] = {
          ...(createDefaultSessionState() as PerSessionState),
          historyStatus: 'loading',
        }
      } else {
        // State already exists (e.g. hydrated earlier). Just make
        // sure the historyStatus reflects a freshly-attempted load.
        if (existing.historyStatus !== 'ready') {
          this.sessions[sessionId] = {
            ...existing,
            historyStatus: 'loading',
          }
        }
      }
      try {
        const res = await fetch(getApiUrl(`/api/sessions/${encodeURIComponent(sessionId)}/messages`))
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        const list = Array.isArray(data?.messages) ? data.messages : []
        // Normalize message format: {role, content, ...}
        const normalized = list.map((m: any) => ({
          id: m.id || m.messageId || `${sessionId}-${m.createdAt || Math.random()}`,
          role: m.role || m.type || 'assistant',
          type: m.type || (m.role === 'user' ? 'user_text' : 'assistant_text'),
          content: m.content || m.text || '',
          createdAt: m.createdAt || m.timestamp || new Date().toISOString(),
          toolCalls: m.toolCalls || [],
          attachments: m.attachments || [],
          reasoning: m.reasoning,
        }))
        this.sessions[sessionId] = {
          ...(this.sessions[sessionId] ?? {}),
          messages: normalized,
          historyStatus: 'ready',
          historyError: undefined,
        }
      } catch (err) {
        this.sessions[sessionId] = {
          ...(this.sessions[sessionId] ?? {}),
          historyStatus: 'error',
          historyError: (err as Error).message,
        }
      }
    },
    async reloadHistory(sessionId: string) {
      // v3.0: drop cached messages and re-fetch.
      const existing = this.sessions[sessionId]
      if (existing) {
        this.sessions[sessionId] = { ...existing, messages: [], historyStatus: 'loading' }
      }
      return this.loadHistory(sessionId)
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
