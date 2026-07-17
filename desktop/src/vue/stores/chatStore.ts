import { defineStore } from 'pinia'
import { deriveSessionTitle, isPlaceholderTitle } from '../lib/autoTitle'
import { saveToStorage } from './sessionStore'
import { useSessionStore } from './sessionStore'
import { useSessionRuntimeStore } from './sessionRuntimeStore'
import { useUIStore } from './uiStore'
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
export interface RuntimeSelection { providerId: string; modelId: string; effortLevel: string; agentMode?: string; workDir?: string | null }
export interface PermissionMode {}

export type ServerMessage = Record<string, unknown>
export type AgentTaskNotification = Record<string, unknown>
export type BackgroundAgentTask = Record<string, unknown>
export type ActiveGoalState = Record<string, unknown> | null
export type ComputerUsePermissionRequest = Record<string, unknown>
export type ComputerUsePermissionResponse = Record<string, unknown>

export type UIMessage =
  | { type: 'user_text'; content: string; attachments?: AttachmentRef[]; id: string; timestamp: number; pending?: boolean; role?: string; sessionId?: string; transcriptMessageId?: string }
  | { type: 'assistant_text'; content: string; id: string; timestamp: number; model?: string; isStreaming?: boolean; sessionId?: string; transcriptMessageId?: string }
  | { type: 'tool_use'; toolUseId: string; toolName: string; input: unknown; id: string; timestamp: number; isPending?: boolean; status?: string; partialInput?: string; result?: string; isError?: boolean; args?: unknown }
  | { type: 'tool_result'; toolUseId: string; result: string; id: string; timestamp: number; isError?: boolean; toolName?: string }
  | { type: 'thinking'; thinkingId: string; content: string; id: string; timestamp: number }
  | { type: 'compact_summary'; summary: string; id: string; timestamp: number; phase?: string; trigger?: string; preTokens?: number; messagesSummarized?: number; title?: string }
  | { type: 'goal_event'; action?: string; status?: string; objective?: string; message?: string; id: string; timestamp: number }
  | { type: 'memory_event'; files?: Array<{ path?: string }>; message?: string; id: string; timestamp: number }
  | { type: 'background_task'; task?: { status?: string; taskType?: string; summary?: string; lastToolName?: string; description?: string; outputFile?: string; taskId?: string; usage?: { durationMs?: number; totalTokens?: number } }; id: string; timestamp: number }
  | { type: 'task_summary'; tasks?: unknown[]; id: string; timestamp: number }
  | { type: 'permission_request'; requestId?: string; toolUseId?: string; description?: string; id: string; timestamp: number }
  | { type: 'error'; message?: string; code?: string; id: string; timestamp: number }
  | { type: 'system'; content?: string; id: string; timestamp: number }

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
  /** Plan-and-Execute mode toggle (per-session) */
  planModeEnabled: boolean
  /** Plan-and-Execute / deep-mode state */
  plan: {
    goal: string
    steps: Array<{
      step: number
      action: string
      tool: string | null
      input_hint: string
      expected_result: string
      status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'skipped'
      result: string | null
      error: string | null
    }>
    current_step: number
    total_steps: number
    completed_steps: number
    failed_steps: number
    status: string
    /** Deep-mode scenario classification (optional) */
    category?: string
    category_label?: string
    category_label_en?: string
    specialists?: string[]
    roster_labels?: string[]
    classification_reason?: string
    matched_signals?: string[]
    mode?: string
  } | null
  /** Last deep-mode route detail (from SSE deep_route) */
  deepRoute?: {
    category: string
    specialists: string[]
    label_zh: string
    label_en: string
    reason?: string
    pipeline?: string[]
    matched?: string[]
  } | null
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
  /** Deep-mode sub-agent streams: agent_id → { name, color, text, status }.
   *  Populated by agent_start/agent_token/agent_done SSE events. */
  agentStreams?: Record<string, { name: string; color: string; text: string; status: 'running' | 'done' | 'error'; elapsed_ms?: number }>
  /** Increments each time the AI writes to the preview directory, so the
   *  right-side PreviewPanel can refresh immediately instead of polling. */
  previewRefreshKey?: number
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
    planModeEnabled: true,  // Plan-and-Execute mode default ON
    plan: null,
    deepRoute: null,
    pendingPermission: null,
    pendingComputerUsePermission: null,
    clarificationPending: null,
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
    agentStreams: {},
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
      // Also persist to the backend so the conversation lives in the
      // workspace directory (<workDir>/.madcop/...) instead of opaque
      // Electron localStorage. Best-effort: ignore network failures.
      try {
        // Carry the session's working directory so the backend stores the
        // conversation under <workDir>/.madcop/ instead of its own cwd.
        let wd = ''
        try {
          const ss = useSessionStore(this.$pinia)
          const sess = ss.sessions.find((x: any) => x.id === sessionId)
          wd = sess?.workDir || sess?.projectPath || sess?.projectRoot || ''
        } catch {}
        const payload = JSON.stringify({ messages: s.messages, title: s.title, workDir: wd })
        fetch(getApiUrl(`/api/sessions/${encodeURIComponent(sessionId)}/messages`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload,
        }).catch(() => {})
      } catch {}
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
      _options?: { displayContent?: string; displayAttachments?: AttachmentRef[]; hideDisplayContent?: boolean, model?: string },
    ) {
      const session = this.getSession(sessionId)
      session.chatState = 'busy'
      // Add the user message. transcriptMessageId mirrors id so session
      // branching (fork-from-here) can locate the backend message by id.
      const userId = nextId()
      const userMsg: UIMessage = {
        type: 'user_text',
        content,
        attachments: _attachments,
        id: userId,
        transcriptMessageId: userId,
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

      // Clear stale plan so the task panel doesn't show the previous
      // message's completed plan while the new one is being generated.
      // The new SSE stream will populate fresh plan data.
      session.plan = null
      session.deepRoute = null
      session.agentStreams = {}

      // Abort any in-flight request for this session so stale SSE events
      // from the old message can't overwrite the new plan / messages.
      if (session._abortCtrl) { try { session._abortCtrl.abort() } catch {} }
      session._abortCtrl = new AbortController()

      // Call the backend API. Route through getApiUrl() so the chat
      // endpoint respects the single base-URL source of truth (set at
      // startup via initializeDesktopServerUrl / setBaseUrl) instead of
      // a second hard-coded port that can drift out of sync.
      const apiUrl = getApiUrl('/api/chat')
      // v3.0: include the locally-cached message history so the
      // backend LLM can see context. Without this, after a reload
      // the assistant thinks the user is starting a new chat because
      // the backend never received the prior messages.
      const history = (session.messages || [])
        .filter((m: any) => m && (m.type === 'user_text' || m.type === 'assistant_text'))
        .map((m: any) => ({
          role: m.role || (m.type === 'user_text' ? 'user' : 'assistant'),
          content: m.content || '',
          // Stable id for backend persist / branch cut points
          id: m.transcriptMessageId || m.id || undefined,
        }))
        // Cap at the last 20 messages to keep the request small
        .slice(-20)
      // NOTE: The system prompt is owned by the backend (madcop/server/app.py
      // prepends a memory + workspace + tool system message and replaces any
      // frontend-sent `system` role). Sending a frontend-authored system
      // message here would be dead code, so we intentionally omit it.
      // NOTE: `userMsg` was already pushed into `session.messages` above
      // (line ~342), so it is already part of `history`. Do NOT append it a
      // second time — that previously duplicated every user message in the
      // request and doubled token usage / confused the model.
      const requestMessages = [...history]
      // Shared error surfacer: mark the session errored and append a visible
      // assistant message so the reason is never silently swallowed.
      const pushChatError = (message: string) => {
        session.chatState = 'error'
        const errId = nextId()
        session.messages.push({
          type: 'assistant_text',
          content: `错误: ${message}`,
          id: errId,
          transcriptMessageId: errId,
          timestamp: Date.now(),
          model: session.messages.find((m: any) => m.type === 'assistant_text')?.model,
        } as any)
      }
      // Per-session reasoning intensity (effort), from the session runtime
      // selection. 'auto' (or unset) means: let the backend/model decide.
      const _runtimeSel = useSessionRuntimeStore(this.$pinia).selections[sessionId]
      const _effort = _runtimeSel?.effortLevel || 'auto'
      // Unified agent mode (quick/standard/deep). 'auto'/unset falls through
      // to the normal chat flow on the backend.
      const _agentMode = _runtimeSel?.agentMode || 'auto'
      // Bump the preview refresh key so any stale HTML from a previous
      // task is re-fetched — prevents the user from seeing the last
      // task's preview while the new one is still streaming.
      session.previewRefreshKey = (session.previewRefreshKey || 0) + 1
      fetch(apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: session._abortCtrl.signal,
        body: JSON.stringify({
          // Prefer the model the user picked in the session selector
          // (_options.model, set from ChatInput's selectedModel). If none is
          // selected, omit it and let the backend use its active provider model.
          model: _options?.model || '',
          messages: requestMessages,
          attachments: _attachments?.map((a) => ({
            id: (a as any).id || `att-${Date.now()}`,
            name: a.name,
            type: a.type,
            path: a.path,
            // Backend ChatAttachment.dataUrl — required for docx/pdf extract
            // when the Electron path is missing or unreadable by the sidecar.
            dataUrl: (a as any).previewUrl || (a as any).data || (a as any).dataUrl,
          })),
          // Send null so the backend resolves temperature/max_tokens from
          // the active provider's persisted config (set in Settings). The
          // old hardcoded 0.7/8192 ignored whatever the user configured.
          temperature: null,
          max_tokens: null,
          conversation_id: sessionId,
          plan_mode: !!session.planModeEnabled,
          effort: _effort === 'auto' ? null : _effort,
          agent_mode: _agentMode === 'auto' ? null : _agentMode,
          // Session project folder → file-tool allowlist (write/read).
          work_dir: (() => {
            try {
              const ss = useSessionStore(this.$pinia)
              const s = ss.sessions?.find((x: any) => x.id === sessionId)
              return s?.workDir || s?.projectRoot || s?.projectPath
                || localStorage.getItem('madcop_workspace_dir')
                || null
            } catch {
              try {
                return localStorage.getItem('madcop_workspace_dir') || null
              } catch {
                return null
              }
            }
          })(),
        }),
      })
        .then(async (res) => {
          if (!res.ok) {
            // The backend sends a real reason (FastAPI { detail }, our
            // { message }, or a plain-text body). Surface it instead of a
            // blank red state so the user can actually see what went wrong.
            let reason = ''
            try {
              const raw = await res.text()
              if (raw) {
                try {
                  const parsed = JSON.parse(raw)
                  const d = parsed && (parsed.detail ?? parsed.message ?? parsed.error)
                  if (typeof d === 'string') {
                    reason = d
                  } else if (Array.isArray(d)) {
                    // FastAPI validation errors: [{ loc, msg, type }]
                    reason = d
                      .map((x: any) => (x && x.msg) || (typeof x === 'string' ? x : ''))
                      .filter(Boolean)
                      .join('; ')
                  } else if (d && typeof d === 'object') {
                    reason = d.message || JSON.stringify(d)
                  }
                } catch {
                  reason = raw
                }
              }
            } catch {}
            pushChatError(reason || `请求失败 (HTTP ${res.status})`)
            return
          }
          // Read the SSE stream
          const reader = res.body?.getReader()
          if (!reader) {
            pushChatError('无法读取服务器返回的数据流')
            return
          }
          session.reasoningContent = null
          session.agentStreams = {}
          const decoder = new TextDecoder()
          let buffer = ''
          let assistantMsg = ''
          const assistantId = nextId()
          // Don't push assistant placeholder here — wait until first 'text'
          // event so tool_use messages that arrive earlier are placed before
          // the assistant message in the timeline.
          let assistantPushed = false
          let assistantMsgObj: any = null
          // Throttle UI updates during streaming: accumulate tokens and
          // flush to assistantMsgObj.content at most once per animation
          // frame (~60fps). Without this, every token triggers a full
          // markdown re-parse in MessageList, causing jank on long replies.
          let _pendingFlush = false
          const _flushContent = () => {
            _pendingFlush = false
            if (assistantMsgObj) assistantMsgObj.content = assistantMsg
          }
          const _scheduleFlush = () => {
            if (!_pendingFlush) {
              _pendingFlush = true
              requestAnimationFrame(_flushContent)
            }
          }

          const ensureAssistantPushed = () => {
            if (assistantPushed) return
            assistantPushed = true
            assistantMsgObj = {
              type: 'assistant_text',
              content: assistantMsg,
              id: assistantId,
              transcriptMessageId: assistantId,
              timestamp: Date.now(),
            }
            session.messages.push(assistantMsgObj)
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
                    // Update the placeholder message via the cached reference
                    // (avoids an O(n) Array.find on every streamed token).
                    // Throttled via requestAnimationFrame so we don't trigger
                    // a markdown re-parse per token on long replies.
                    _scheduleFlush()
                    // The final answer is now streaming in. Switch out of the
                    // "thinking" state so the hand-drawn planning animation is
                    // hidden and the text trickles in live (instead of popping
                    // out all at once at `done`). Planning/tool phases keep the
                    // animation because they run while chatState is still
                    // 'busy'/'tool_executing'.
                    if (session.chatState !== 'streaming') {
                      session.chatState = 'streaming'
                      if (assistantMsgObj) assistantMsgObj.isStreaming = true
                    }
                  } else if (event.type === 'done') {
                    session.chatState = 'idle'
                    // Cancel any pending throttled flush and write the
                    // final content immediately so nothing is lost.
                    _pendingFlush = false
                    if (assistantMsgObj) {
                      assistantMsgObj.content = assistantMsg
                      assistantMsgObj.isStreaming = false
                    }
                  } else if (event.type === 'skill_distilled' && (event.skillName || event.skill_name)) {
                    const skillName = event.skillName || event.skill_name
                    try {
                      useUIStore().addToast({
                        type: 'success',
                        message: `已自动蒸馏技能：${skillName}`,
                      })
                    } catch { /* toast optional */ }
                  } else if (event.type === 'reasoning' && event.content) {
                    session.reasoningContent = (session.reasoningContent || '') + event.content
                  } else if (event.type === 'agent_start') {
                    // Deep mode: a sub-agent begins. Register it in the
                    // session's agentStreams so SubAgentPanel renders it.
                    if (!session.agentStreams) session.agentStreams = {}
                    const aid = event.agent_id
                    if (!session.agentStreams[aid]) {
                      session.agentStreams[aid] = {
                        name: event.agent_name || aid,
                        color: event.color || '#7C3AED',
                        text: '',
                        status: 'running',
                      }
                    } else {
                      session.agentStreams[aid].status = 'running'
                    }
                  } else if (event.type === 'agent_token' && event.agent_id) {
                    // Append the token to the matching sub-agent's stream.
                    if (!session.agentStreams) session.agentStreams = {}
                    const aid = event.agent_id
                    if (!session.agentStreams[aid]) {
                      session.agentStreams[aid] = { name: aid, color: '#7C3AED', text: '', status: 'running' }
                    }
                    session.agentStreams[aid].text += (event.text || '')
                  } else if (event.type === 'agent_done' && event.agent_id) {
                    if (session.agentStreams && session.agentStreams[event.agent_id]) {
                      session.agentStreams[event.agent_id].status = event.status === 'error' ? 'error' : 'done'
                      session.agentStreams[event.agent_id].elapsed_ms = event.elapsed_ms
                    }
                  } else if (event.type === 'tool' && event.name) {
                    // AI is calling a tool — show it transparently under the
                    // thinking indicator so the user can see what's happening.
                    session.activeToolName = event.name
                    session.activeToolUseId = event.tool_use_id || `tool-${Date.now()}-${Math.random()}`
                    const toolMsg: UIMessage = {
                      type: 'tool_use',
                      toolUseId: session.activeToolUseId,
                      toolName: event.name,
                      input: event.args,
                      id: nextId(),
                      timestamp: Date.now(),
                      isPending: true,
                    }
                    // Insert BEFORE the assistant text placeholder if it was
                    // already pushed (Phase-1 now streams text before deciding
                    // to call tools, so a 'tool' event can arrive after text
                    // started). This keeps tool cards above the answer.
                    if (assistantPushed && assistantMsgObj) {
                      const idx = session.messages.lastIndexOf(assistantMsgObj)
                      if (idx >= 0) session.messages.splice(idx, 0, toolMsg)
                      else session.messages.push(toolMsg)
                    } else {
                      session.messages.push(toolMsg)
                    }
                  } else if (event.type === 'clarification_request') {
                    // Agent asked the user a clarifying question (ask_user tool).
                    const q = event.question || '需要你补充信息'
                    const opts = Array.isArray(event.options) ? event.options : []
                    session.clarificationPending = { question: q, options: opts }
                    // Ensure a visible assistant message even if no text event follows
                    if (!assistantPushed) {
                      const clarifyBody = opts.length
                        ? `${q}\n\n${opts.map((o: string) => `- ${o}`).join('\n')}`
                        : q
                      assistantMsg = clarifyBody
                      assistantMsgObj = {
                        type: 'assistant_text',
                        content: clarifyBody,
                        id: nextId(),
                        timestamp: Date.now(),
                        isStreaming: false,
                      } as any
                      session.messages.push(assistantMsgObj)
                      assistantPushed = true
                    }
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
                    // If ask_user returned a clarify marker but SSE event was missed,
                    // still surface the panel from the tool result payload.
                    const tname = (event.name || prev?.toolName || '').toLowerCase()
                    if ((tname === 'ask_user' || tname === 'clarify') && !session.clarificationPending) {
                      try {
                        let raw: any = event.result
                        if (typeof raw === 'string') {
                          try { raw = JSON.parse(raw) } catch { raw = null }
                        }
                        if (raw && typeof raw === 'object') {
                          if (typeof raw.output === 'string' && raw.output.includes('__clarify')) {
                            try { raw = { ...raw, ...JSON.parse(raw.output) } } catch {}
                          }
                          if (raw.question || raw.__clarify_pending__) {
                            session.clarificationPending = {
                              question: String(raw.question || '需要你补充信息'),
                              options: Array.isArray(raw.options) ? raw.options.map(String) : [],
                            }
                          }
                        }
                      } catch { /* ignore parse errors */ }
                    }
                    // Clear the live "calling tool" status line.
                    if (session.activeToolName && (!prev || prev.toolName === session.activeToolName)) {
                      session.activeToolName = null
                    }
                    session.activeToolUseId = null
                    // After tool execution, the next 'text' events belong to
                    // the Phase-2 synthesis (a fresh answer), so reset the
                    // assistant placeholder. This starts a NEW assistant
                    // bubble after the tool cards instead of appending to
                    // the Phase-1 pre-tool text — keeping the timeline as
                    // [phase-1 text] → [tool] → [tool_result] → [phase-2 answer].
                    assistantPushed = false
                    assistantMsgObj = null
                    assistantMsg = ''
                  } else if (event.type === 'session_title' && event.title) {
                    // Backend-generated Claude-style title — replace the local
                    // heuristic title with a more meaningful one.
                    this.sessions[sessionId].title = event.title
                    try {
                      const ss = useSessionStore()
                      ss.updateSessionTitle(sessionId, event.title)
                    } catch {}
                  } else if (event.type === 'deep_route' && event.route) {
                    // Deep mode: scenario → specialist roster preview
                    this.sessions[sessionId].deepRoute = event.route
                  } else if (event.type === 'plan' && event.plan) {
                    // Plan-and-Execute / deep multi-agent: full plan update
                    this.sessions[sessionId].plan = event.plan
                    if (event.plan.category) {
                      this.sessions[sessionId].deepRoute = {
                        category: event.plan.category,
                        specialists: event.plan.specialists || [],
                        label_zh: event.plan.category_label || event.plan.category,
                        label_en: event.plan.category_label_en || event.plan.category,
                        reason: event.plan.classification_reason,
                        pipeline: event.plan.roster_labels,
                        matched: event.plan.matched_signals,
                      }
                    }
                  } else if (event.type === 'plan_step' && event.step) {
                    // Plan-and-Execute: single step status update
                    const plan = this.sessions[sessionId].plan
                    if (plan) {
                      const idx = plan.steps.findIndex((s: any) => s.step === event.step.step)
                      if (idx >= 0) {
                        plan.steps[idx] = event.step
                        plan.completed_steps = plan.steps.filter((s: any) => s.status === 'completed').length
                        plan.failed_steps = plan.steps.filter((s: any) => s.status === 'failed').length
                        plan.current_step = event.step.step
                      }
                    }
                  } else if (event.type === 'plan_done') {
                    // Plan-and-Execute: all steps complete
                    // Plan stays in the session state for display
                  } else if (event.type === 'preview_update') {
                    // The AI wrote a file into ~/.madcop/preview/ — bump the
                    // refresh key so the PreviewPanel reloads immediately,
                    // AND auto-open the right-side workbench in browser mode
                    // so the user sees the result without manual steps.
                    session.previewRefreshKey = (session.previewRefreshKey || 0) + 1
                    try {
                      const { useWorkspacePanelStore } = await import('../stores/workspacePanelStore')
                      const ws = useWorkspacePanelStore()
                      ws.openPanel(sessionId)
                      ws.setMode(sessionId, 'browser')
                    } catch {}
                  } else if (event.type === 'error' && event.message) {
                    // Backend error (API error, rate limit, etc.)
                    pushChatError(event.message)
                  }
                } catch {}
              }
            }
          }
          session.chatState = 'idle'
        })
        .catch((err: any) => {
          // A new message aborts the previous in-flight request via
          // session._abortCtrl — that's expected, not an error.
          if (err && err.name === 'AbortError') return
          // Network-level failure (backend down, connection refused, etc.).
          // Surface a concrete reason instead of a blank red state.
          const reason =
            err && err.message
              ? `无法连接到后端服务 (${err.message})`
              : '无法连接到后端服务，请确认服务已启动'
          pushChatError(reason)
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
        // Normalize message format. If the backend stored our native
        // UIMessage shape (has both `type` and `id`), keep it as-is so
        // tool_use/tool_result/plan messages round-trip intact.
        const normalized = list.map((m: any) => {
          const id = m.id || m.messageId || `${sessionId}-${m.createdAt || Math.random()}`
          if (m && m.type && m.id) {
            return {
              ...m,
              id,
              transcriptMessageId: m.transcriptMessageId || id,
            }
          }
          const role = m.role || m.type || 'assistant'
          const type = m.type || (role === 'user' || role === 'user_text' ? 'user_text' : 'assistant_text')
          return {
            id,
            transcriptMessageId: id,
            role,
            type,
            content: m.content || m.text || '',
            createdAt: m.createdAt || m.timestamp || new Date().toISOString(),
            timestamp: typeof m.timestamp === 'number' ? m.timestamp : Date.now(),
            toolCalls: m.toolCalls || [],
            attachments: m.attachments || [],
            reasoning: m.reasoning,
          }
        })
        this.sessions[sessionId] = {
          ...(this.sessions[sessionId] ?? {}),
          // Don't clobber locally-hydrated threads with an empty backend
          // response — keep the existing messages if the backend has none.
          messages: normalized.length > 0 ? normalized : (this.sessions[sessionId]?.messages ?? normalized),
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
