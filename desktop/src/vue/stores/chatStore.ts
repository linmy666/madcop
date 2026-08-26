import { defineStore } from 'pinia'
import { deriveSessionTitle, isPlaceholderTitle } from '../lib/autoTitle'
import { saveToStorage } from './sessionStore'
import { useSessionStore } from './sessionStore'
import { useSessionRuntimeStore } from './sessionRuntimeStore'
import { useSettingsStore } from './settingsStore'
import { useTabStore } from './tabs'
import { useUIStore } from './uiStore'
import {syncLiveState, resetLiveState, endLiveState, useLiveState} from '../composables/useLiveState'

// DEDUP-FIX: merge tool entries by id instead of wholesale replacement,
// so multi-step tool progress survives subsequent syncLiveState calls
// (e.g. text_delta events that would otherwise wipe the running tool list).
function _merge_tools(prev: any[] | null | undefined, next: any[]): any[] {
  const seen = new Set<string>()
  const out: any[] = []
  for (const t of [...(next || []), ...(prev || [])]) {
    if (!t || seen.has(t.id)) continue
    seen.add(t.id)
    out.push(t)
  }
  return out
}

import { getApiUrl } from '../api/client'

// v3.0: local persistence for per-session messages. The chat API
// doesn't round-trip every send (we keep state in memory) so without
// this, reloading the app forgets every conversation. The payload is
// small (a few MB even with big threads) so a single localStorage
// key per session is fine.
const MESSAGES_STORAGE_KEY = 'madcop_chat_messages'

// v4 — per-session in-flight fetch registry. When the user jumps
// A → B → A faster than the backend can respond, two concurrent
// loadHistory() calls for the same session race to write the same
// `sessions[sessionId]` slot, producing a torn / partial history
// (most visibly: assistant_text rows become "[Unknown: assistant]"
// because their concatenated stream never finished). The
// AbortController cancels the previous fetch on re-entry, so the
// newer write is the only one that lands.
const _inflightLoadHistory = new Map<string, AbortController>()

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

export type ChatState = 'idle' | 'busy' | 'error' | 'stopped' | 'streaming'
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
  // P2-2 — skipResponse removed: dead field (never read or written anywhere).
  historyStatus?: 'idle' | 'loading' | 'ready' | 'error'
  historyError?: string | null
  streamingText: string
  /** v3.10 — Grok-Build-style thought blocks. Each segment of
   *  reasoning is an independent block (not one big accumulated
   *  string). Tool calls between thoughts create natural
   *  boundaries. Rendered as gray inline text without frames. */
  thoughtBlocks?: { id: string; text: string; done: boolean }[]
  /** Temporary SSE event log for in-UI debugging (no DevTools needed).
   *  Each entry is { t, type, id, preview }. Capped at 200 entries. */
  debugSSELog?: { t: number; type, string; id?: number; preview?: string }[]
  streamingToolInput: string
  activeToolUseId: string | null
  activeToolName: string | null
  /** HITL confirm queue (tool_confirm_request SSE). Parallel tools
   *  emit several cards; they render ONE at a time (head of queue). */
  pendingToolConfirms: { toolUseId: string; toolName: string; input: any }[]
  /** Sprint 2 — memories the LLM drew on for this turn. */
  memoryRecalls?: { id: string; kind: string; title: string; preview: string; layer: string }[]
  /** Sprint 4 — source citations from the creation engine (DONE.metadata.citations). */
  citations?: { url: string; title: string; snippet: string }[]
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
  // P2-2 — `pendingClarification` removed: unused dead field
  // (clarificationPending is the one components actually read).
  tokenUsage: TokenUsage
  compactCount?: number
  // P2-2 — removed dead fields: streamingResponseChars, elapsedSeconds,
  // statusVerb, thinkingStage, apiRetry, streamingFallback. These were
  // always defined and never read by any component.
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
  memoryRecalls: [],
  citations: [],
    activeToolUseId: null,
    activeToolName: null,
    pendingToolConfirms: [],
    activeThinkingId: null,
    // Default OFF: plan sidebar "生成执行计划" confuses normal chat / file Q&A.
    // Multi-step planning still works when the user enables plan mode explicitly.
    planModeEnabled: false,
    plan: null,
    deepRoute: null,
    pendingPermission: null,
    pendingComputerUsePermission: null,
    clarificationPending: null,
    tokenUsage: { input_tokens: 0, output_tokens: 0 },
    compactCount: 0,
    // P2-2 — defaults for removed dead fields deleted.
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
          wd = sess?.workDir || sess?.projectPath || ''
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
      // Sync to liveState so PlanTasksPanel shows "思考中" immediately
      resetLiveState(sessionId)
      // P2-12 — flip the tab's status so Sidebar's running indicator
      // reflects this session. (Previously status was hard-coded to
      // 'idle' on open and never updated.)
      try { useTabStore().setTabStatus(sessionId, 'running') } catch { /* store not ready */ }
      // P2-NS — guard against the "task panel stuck on 正在处理" bug.
      // If a 'done' event is lost (e.g. upstream error before flush,
      // SSE socket close, sensenova silent-hang), chatState never
      // flips back to 'idle' and PlanTasksPanel shows 正在处理 forever.
      // Auto-flip after 5 min so the UI is never permanently stuck.
      if (session._busyWatchdog) clearTimeout(session._busyWatchdog)
      session._busyWatchdog = setTimeout(() => {
        const s = this.sessions[sessionId]
        if (!s || s.chatState !== 'busy') return
        s.chatState = 'idle'
        try { useTabStore().setTabStatus(sessionId, 'idle') } catch { /* ignore */ }
        try {
          useUIStore().addToast({
            type: 'info',
            message: '会话超时未收到完成信号，已自动重置',
          })
        } catch { /* ignore */ }
      }, 5 * 60 * 1000)
      // The user is sending a new message — clear any pending
      // clarification from a prior ask_user turn. Otherwise the purple
      // ClarificationPanel stays stuck on screen even though the user
      // has moved on to a new question.
      session.clarificationPending = null
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
      session.clarificationPending = null
      // Sprint 4 — clear citations from the previous turn.
      session.citations = []

      // Diagnostic: count how many times sendMessage is called for this
      // session within a short window. If the count climbs while a fetch
      // is in-flight, the new call will abort the old one — that's the
      // root cause of "ABORT fetch aborted" appearing immediately after
      // the user sends a single message.
      const _now = Date.now()
      const _lastSendAt = (session as any)._lastSendAt || 0
      const _sendCount = (session as any)._sendCount || 0
      ;(session as any)._lastSendAt = _now
      ;(session as any)._sendCount = _sendCount + 1
      if (_now - _lastSendAt < 5000) {
        // Rapid double-send within 5s — this is almost certainly a bug
        // (duplicate event binding, watcher firing, etc.). Record the
        // stack so we can identify the caller without DevTools.
        const stack = new Error('sendMessage rapid-call').stack || ''
        if (!session.debugSSELog) session.debugSSELog = []
        session.debugSSELog.push({
          t: _now,
          type: 'RAPID_SEND',
          preview: `count=${_sendCount + 1} within 5s; stack=${stack.split('\n').slice(2, 6).join(' | ')}`,
        })
      }

      // Abort any in-flight request for this session so stale SSE events
      // from the old message can't overwrite the new plan / messages.
      if (session._abortCtrl) { try { session._abortCtrl.abort() } catch {} }
      session._abortCtrl = new AbortController()

      // Call the backend API. Route through getApiUrl() so the chat
      // endpoint respects the single base-URL source of truth (set at
      // startup via initializeDesktopServerUrl / setBaseUrl) instead of
      // a second hard-coded port that can drift out of sync.
      // P3-G — migrate main chat to the v4 engine endpoint. The v4 route
      // uses the unified AgentEngine (Quick/ReAct/Deep/Create) and emits
      // `kind`-based SSE events, which the adapter above maps back to the
      // legacy `type` vocabulary this store was built on. The old
      // /api/chat handler is retained for backward compat but is deprecated.
      const apiUrl = getApiUrl('/api/v4/chat')
      // v3.0: include the locally-cached message history so the
      // backend LLM can see context. Without this, after a reload
      // the assistant thinks the user is starting a new chat because
      // the backend never received the prior messages.
      const history = (session.messages || [])
        .filter((m: any) => m && (m.type === 'user_text' || m.type === 'assistant_text'))
        .map((m: any) => {
          let content = m.content || ''
          // Keep attachment filenames in history so follow-up turns know a
          // file was uploaded even if the first turn only stored a short caption.
          if (m.type === 'user_text' && Array.isArray(m.attachments) && m.attachments.length) {
            const names = m.attachments.map((a: any) => a.name || a.path || 'file').filter(Boolean)
            if (names.length && !content.includes('ATTACHMENT:') && !content.includes('[已上传附件')) {
              content = `${content}\n\n[已上传附件: ${names.join(', ')}]`
            }
          }
          return {
            role: m.role || (m.type === 'user_text' ? 'user' : 'assistant'),
            content,
            id: m.transcriptMessageId || m.id || undefined,
          }
        })
        // Keep more history so resume analysis stays available for rewrite turns
        .slice(-30)
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
      // Unified agent mode (quick/standard/deep/create). Must match AgentModeSelector
      // default (standard). Using 'auto' here when unset made the UI show「标准」
      // while the backend ran plan_mode + clarify with no visible reply.
      const _agentMode = _runtimeSel?.agentMode || 'chat'
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
          // selected, OMIT the field — an empty string would reach the
          // upstream LLM as the model id and produce 'unknown model ""'.
          ...(_options?.model ? { model: _options.model } : {}),
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
          // Attachments: never open plan-and-execute (it invents clarify steps
          // and leaves the chat blank). Matches AgentModeSelector default standard.
          plan_mode: !!session.planModeEnabled && !(_attachments && _attachments.length > 0),
          effort: _effort === 'auto' ? null : _effort,
          agent_mode: _agentMode === 'auto' ? null : _agentMode,
          // P2-3 — outputStyle from settingsStore (Learning / Concise / Detailed).
          // Backend injects a small behavioral nudge into the system prompt.
          output_style: (() => {
            try { return useSettingsStore(this.$pinia)?.outputStyle || 'Learning' }
            catch { return 'Learning' }
          })(),
          // Session project folder → file-tool allowlist (write/read).
          work_dir: (() => {
            try {
              const ss = useSessionStore(this.$pinia)
              const s = ss.sessions?.find((x: any) => x.id === sessionId)
              return s?.workDir || s?.projectPath
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
            if (!session.debugSSELog) session.debugSSELog = []
            session.debugSSELog.push({
              t: Date.now(), type: 'HTTP_ERROR',
              preview: `status=${res.status} ${reason.slice(0, 100)}`,
            })
            return
          }
          // Read the SSE stream
          const reader = res.body?.getReader()
          if (!reader) {
            pushChatError('无法读取服务器返回的数据流')
            if (!session.debugSSELog) session.debugSSELog = []
            session.debugSSELog.push({ t: Date.now(), type: 'NO_READER', preview: 'res.body null' })
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
          // Frame-based batching: opencode's SDK adapter batches every
          // parsed event into one Solid render via a 16ms frame budget
          // (one rAF). All token deltas in the same frame become one
          // Vue re-render. Terminal events (done / error / cancelled)
          // bypass the budget and flush synchronously so the user sees
          // the final state without a 16ms delay.
          // Tradeoff vs. plain queueMicrotask: microtask fires faster
          // (a few microseconds) but each text event can schedule one
          // Vue update, which is the same "one update per token" we
          // were trying to avoid. The 16ms budget keeps it at ≤62.5fps
          // for sparse events, and exactly once per frame for bursts.
          // Net win: lower per-event CPU work, no perceptible latency
          // for the user (text already takes 100ms+ per token to
          // arrive from the upstream model).
          let _pendingFlush = false
          const _flushNow = () => {
            _pendingFlush = false
            if (assistantMsgObj) {
              assistantMsgObj.content = assistantMsg
              // v3.8.9 — ULTIMATE reactivity fix. Assign a brand-new
              // array to session.messages so Vue MUST re-evaluate
              // every computed that depends on it. push/splice weren't
              // enough — Pinia's proxy may have lost track of the
              // messages array if it was hydrated from localStorage
              // (a plain JSON-parsed array, not reactive-wrapped).
              // A fresh array reference forces re-evaluation unconditionally.
              session.messages = [...session.messages]
            } else {
              // P1-7 — before ensureAssistantPushed() runs, the only
              // place the live text is visible is <AssistantMessage
              // :content="streamingText">. Mirror the accumulated text
              // there. Once assistantMsgObj is pushed (above branch),
              // we stop writing to streamingText to avoid the same
              // reply rendering twice (once in messages, once via the
              // streaming component).
              session.streamingText = assistantMsg
            }
          }
          // 16ms is one rAF frame at 60fps. opencode's tui uses the
          // same value (sdk.tsx:48-80). Terminal events bypass this
          // and call _flushTerminal() instead of _flushNow() so a 'done'
          // event doesn't sit in the queue behind a stale rAF.
          //
          // Deep-Review C3: rAF callbacks are throttled to ZERO when the
          // Electron window is hidden/minimized or the tab is backgrounded.
          // Without a fallback, a long unattended run would accumulate
          // tokens with no visible update until the user refocuses. We
          // schedule BOTH a rAF (for visible smoothness) AND a setTimeout
          // (for background reliability); _pendingFlush dedupes so only
          // the first to fire runs _flushNow.
          const _requestFlush = () => {
            if (_pendingFlush) return
            _pendingFlush = true
            requestAnimationFrame(() => _flushNow())
            setTimeout(_flushNow, 100)  // background fallback
          }
          const _flushTerminal = () => {
            // BUG-FIX (Deep-Review C1): before the final write, recover any
            // text held back in the tail buffer. The 批次2.2 incremental
            // filter holds the last ≤24 chars of every chunk in
            // sess._filterTail (in case they're the start of a split
            // protocol marker). On terminal events (done/error/cancel/
            // stream-end) that buffer must be flushed or up to 24 chars
            // of the reply are silently lost. Previously only the
            // text_end handler flushed it — done/error/stream-close all
            // dropped the tail.
            const _tsess: any = session
            if (_tsess._filterTail) {
              assistantMsg = (assistantMsg || '') + _tsess._filterTail
              _tsess._filterTail = ''
            }
            // Cancel any pending frame; apply the final write now.
            _pendingFlush = false
            _flushNow()
          }

          const ensureAssistantPushed = () => {
            if (assistantPushed) return
            assistantPushed = true
            assistantMsgObj = {
              type: 'assistant_text',
              // v3.8.7 — use a space placeholder instead of empty string.
              // buildRenderModel (messageListUtils.ts:509) skips
              // assistant_text messages whose content.trim() is empty.
              // When this object is first pushed, assistantMsg is usually
              // empty (the first text token hasn't arrived yet), so the
              // message gets filtered out and never appears even after
              // content is updated later — because Vue's computed cache
              // for `messages` doesn't re-evaluate when only a nested
              // object property changes (the array reference is stable).
              // A space placeholder ensures trim() returns non-empty,
              // so the message is never skipped.
              content: assistantMsg || ' ',
              id: assistantId,
              transcriptMessageId: assistantId,
              timestamp: Date.now(),
            }
            session.messages.push(assistantMsgObj)
          }
          
          while (true) {
            const { done, value } = await reader.read()
            if (done) {
              break
            }
            buffer += decoder.decode(value, { stream: true })
            
            // Parse SSE events
            const lines = buffer.split('\n')
            buffer = lines.pop() || ''
            
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                let event: any
                try {
                  event = JSON.parse(line.slice(6))
                } catch {
                  // Skip malformed event line; keep the SSE stream
                  // alive so a single bad line doesn't drop the run.
                  continue
                }
                // P3-G — v4→legacy SSE vocabulary adapter. The v4 endpoint
                // (/api/v4/chat) emits `kind` (StepKind enum), but this
                // store's parse logic below is built on legacy `type`
                // values. Map kind→type so both endpoints work without
                // rewriting 50+ event.type branches.
                if (event.kind && !event.type) {
                  const KIND_TO_TYPE: Record<string, string> = {
                    text_delta: 'text',
                    text_end: 'text_end',
                    tool_start: 'tool',
                    tool_end: 'tool_result',
                    thought_start: 'reasoning',
                    thought_delta: 'reasoning',
                    thought_end: 'thought_end',
                    clarify: 'clarification_request',
                    memory_recall: 'memory_recall',
                    skill_distilled: 'skill_distilled',
                    session_title: 'session_title',
                    error: 'error',
                    done: 'done',
                    plan: 'plan',
                    tool_confirm_request: 'tool_confirm_request',
                  }
                  const mapped = KIND_TO_TYPE[event.kind]
                  if (mapped) {
                    event.type = mapped
                    // P3-G/fix — preserve thought sub-type so the
                    // reasoning handler below can distinguish
                    // thought_start / thought_delta / thought_end.
                    // Without this, all 3 get mapped to 'reasoning'
                    // with empty thought_event, so thought blocks
                    // are never created and the user sees nothing
                    // during the (potentially long) thinking phase.
                    if (event.kind === 'thought_start') {
                      event.thought_event = 'thought_start'
                    } else if (event.kind === 'thought_delta') {
                      event.thought_event = 'thought_delta'
                    } else if (event.kind === 'thought_end') {
                      event.thought_event = 'thought_end'
                    }
                    // Preserve thought_id so blocks can be paired.
                    if (event.thought_id) {
                      // already set by v4
                    }
                    // v4 puts content in `content`; legacy uses `content`
                    // for text and `message` for error — normalize.
                    if (event.kind === 'error' && event.content) {
                      event.message = event.content
                    }
                    // v4 memory_recall/skill_distilled use metadata;
                    // legacy uses top-level fields — normalize.
                    if (event.kind === 'memory_recall' && event.metadata?.memories) {
                      event.memories = event.metadata.memories
                    }
                    if (event.kind === 'plan' && event.metadata?.plan) {
                      event.plan = event.metadata.plan
                    }
                    if (event.kind === 'skill_distilled' && event.metadata?.skillName) {
                      event.skillName = event.metadata.skillName
                    }
                    if (event.kind === 'session_title' && event.metadata?.title) {
                      event.title = event.metadata.title
                    }
                    // v4 clarify uses question/options fields directly;
                    // legacy uses the same field names — no transform needed.
                  }
                }
                // Debug telemetry — mirrors opencode's stream.ts which
                // logs every event id/type at 'debug' level. Without
                // this, a silently-dropped event leaves no trace and
                // "the chat just didn't reply" becomes impossible to
                // triage from the client side.
                if (typeof window !== 'undefined') {
                  const w = window as any
                  if (!w.__madcopSSE) w.__madcopSSE = []
                  if (w.__madcopSSE.length < 500) {
                    w.__madcopSSE.push({ t: Date.now(), type: event.type, id: event.id })
                  }
                }
                // In-UI mirror so users without DevTools can still see
                // what events arrived. Capped at 200 to bound memory.
                if (!session.debugSSELog) session.debugSSELog = []
                if (session.debugSSELog.length < 200) {
                  let preview = ''
                  if (event.type === 'text' && event.content) {
                    preview = String(event.content).slice(0, 60)
                  } else if (event.type === 'error' && event.message) {
                    preview = String(event.message).slice(0, 120)
                  } else if (event.type === 'tool_confirm_request') {
                    // HITL: backend BLOCKED waiting for user approve/deny.
                    // Without this handler the confirm event was silently
                    // dropped and the reply stalled forever after intro
                    // text. P0-3: parallel tools queue several cards —
                    // dedupe by tool_use_id, render head-of-queue first.
                    const reqId = (event as any).tool_use_id || `confirm-${Date.now()}`
                    if (!session.pendingToolConfirms.some((c: any) => c.toolUseId === reqId)) {
                      session.pendingToolConfirms.push({
                        toolUseId: reqId,
                        toolName: (event as any).tool_name || '',
                        input: (event as any).tool_input || {},
                      })
                    }
                  } else if (event.type === 'plan') {
                    const _p = (event as any).plan ?? event.metadata?.plan
                    if (_p) {
                      preview = `steps=${_p.steps?.length ?? 0} status=${_p.status}`
                      // Persist the plan onto the session so PlanTasksPanel
                      // (right sidebar) can render live task steps — without
                      // this the sidebar stays blank ("准备就绪") because
                      // the panel reads from session.plan, not from the
                      // streaming events. v4 SSE carries the plan under
                      // metadata.plan; the legacy plan-mode emitter puts
                      // it at event.plan — accept both.
                      // PlanTasksPanel reads step.action; the MEA emitter
                      // uses step.title. Mirror so a single source of
                      // truth can serve both UI surfaces.
                      const _steps = (_p.steps || []).map((s: any) => ({
                        ...s,
                        action: s.action || s.title || '',
                      }))
                      session.plan = { ..._p, steps: _steps }
                    } else {
                      preview = 'plan'
                    }
                  } else if (event.type === 'tool' && event.name) {
                    preview = event.name
                  }
                  session.debugSSELog.push({
                    t: Date.now(),
                    type: event.type,
                    id: event.id,
                    preview,
                  })
                }
                if (event.type === 'text' && event.content) {
                    // Push the assistant placeholder NOW (after any tool_use
                    // messages have already been pushed) so the timeline is
                    // tool → assistant instead of assistant → tool.
                    ensureAssistantPushed()
                    // Some models wrap FINAL_ANSWER as {"message":"a\\nb"} —
                    // unwrap so markdown renders instead of raw JSON.
                    let chunk = event.content as string
                    // Fallback: if the backend ThinkSeparator didn't strip
                    // <think> tags (e.g. legacy path or edge case), strip
                    // them here so reasoning doesn't leak into the answer.
                    if (chunk.includes('<think>') || chunk.includes('</think>')) {
                      chunk = chunk.replace(/<think>[\s\S]*?<\/think>/g, '').replace(/<\/?think>/g, '').trim()
                    }
                    const trimmed = chunk.trim()
                    if (
                      (trimmed.startsWith('{') && trimmed.includes('"message"'))
                      || (trimmed.startsWith('{') && trimmed.includes('"answer"'))
                    ) {
                      try {
                        const parsed = JSON.parse(trimmed)
                        if (parsed && typeof parsed === 'object') {
                          const inner = parsed.message || parsed.answer || parsed.content || parsed.text
                          if (typeof inner === 'string' && inner.trim()) chunk = inner
                        }
                      } catch { /* keep raw */ }
                    }
                    // BUG-FIX (批次2.2): previously every token re-ran 4
                    // global regexes over the ENTIRE accumulated text
                    // (sess2._rawText), making long replies O(n²) and
                    // visibly choppy. Now we filter only the NEW chunk and
                    // append, with a small tail-buffer to catch protocol
                    // markers split across chunks (e.g. "Action" + " Input:").
                    const sess2: any = session
                    // _filterTail holds the last ~24 chars of the previous
                    // chunk that might be the start of a split marker.
                    const _tail = (sess2._filterTail || '') as string
                    const _combined = _tail + chunk
                    // Filter protocol markers from the combined buffer.
                    let _filteredChunk = _combined
                      .replace(/\b(Thought|Action\s*Input|Action|Observation|FINAL_ANSWER)\b\s*[:：]\s*/gi, '')
                      .replace(/(FINAL_ANSWER)\s*[:：]/gi, '')
                      .replace(/\bAction\s*Input\b\s*[:：]\s*/gi, '')
                      .replace(/\\n/g, '\n').replace(/\\t/g, '\t')
                      .replace(/\n{3,}/g, '\n\n')
                    // Save the tail of what's LEFT after filtering, in case
                    // a marker is still forming. We only keep the last 24
                    // chars (longest marker is "FINAL_ANSWER" = 13 chars).
                    //
                    // Deep-Review C5: only engage the tail buffer once the
                    // accumulated text is long enough that holding back 24
                    // chars is negligible. For short replies (< 48 chars
                    // total), appending directly means the user sees text
                    // trickle in immediately instead of nothing-then-pop.
                    const _accLen = (assistantMsg || '').length
                    const _TAIL_THRESHOLD = 48
                    if (_accLen >= _TAIL_THRESHOLD) {
                      sess2._filterTail = _filteredChunk.slice(-24)
                      const _safeAppend = _filteredChunk.slice(0, -24)
                      if (_safeAppend) assistantMsg = (assistantMsg || '') + _safeAppend
                    } else {
                      // Short reply: append the whole filtered chunk. The
                      // risk of a split marker at this length is minimal
                      // (most markers are mid-sentence), and visibility
                      // matters more than perfect filtering.
                      sess2._filterTail = ''
                      assistantMsg = (assistantMsg || '') + _filteredChunk
                    }
                    // Keep rawText for debugging/compaction, but don't filter it.
                    sess2._rawText = (sess2._rawText || '') + chunk
                    _requestFlush()
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
                    // Sync live state for PlanTasksPanel (thinking + answer progress)
                    syncLiveState({
                      isStreaming: true,
                      thoughts: (session.thoughtBlocks || []).map(tb => ({ id: tb.id, text: tb.text, done: tb.done })),
                      tools: _merge_tools(useLiveState().tools, []),
                      answerLength: (assistantMsg || '').length,
                      sessionId,
                    })
                  } else if (event.type === 'text_end') {
                    // BUG-FIX: text_end was mapped in KIND_TO_TYPE but had
                    // no handler, so assistantMsgObj.isStreaming stayed true
                    // until 'done' arrived. If 'done' was ever lost/delayed,
                    // the streaming caret blinked forever on a finished
                    // message. Now we stop the caret here — 'done' still
                    // handles session.chatState + tab status + finalization.
                    // (_flushTerminal now handles tail-buffer recovery
                    // uniformly — see Deep-Review C1.)
                    if (assistantMsgObj) assistantMsgObj.isStreaming = false
                    _flushTerminal()
                  } else if (event.type === 'done') {
                    session.chatState = 'idle'
                    // P1-7/feature-clear — clear the live-streaming buffer
                    // so the floating <AssistantMessage> bubble (v-if'd on
                    // `streamingText.trim()`) disappears and the cursor stops
                    // blinking. The finalized content remains visible via
                    // the assistant_msg row in session.messages.
                    session.streamingText = ''
                    endLiveState()  // notify PlanTasksPanel streaming ended
                    // P2-12 — mark the tab idle so Sidebar's running count clears.
                    try { useTabStore().setTabStatus(sessionId, 'idle') } catch { /* ignore */ }
                    // Sprint 4 — capture creation-engine citations from
                    // DONE.metadata (only present in create mode).
                    const _meta = (event as any)?.metadata
                    // P1-5 — token usage from the run's final DONE step:
                    // feeds the context budget indicator.
                    const _usage = _meta?.usage
                    if (_usage && (typeof _usage.prompt_tokens === 'number')) {
                      session.tokenUsage = {
                        input_tokens: _usage.prompt_tokens || 0,
                        output_tokens: _usage.completion_tokens || 0,
                      }
                    }
                    if (_meta && Array.isArray(_meta.citations) && _meta.citations.length > 0) {
                      session.citations = _meta.citations.map((c: any) => ({
                        url: String(c.url || ''),
                        title: String(c.title || c.url || ''),
                        snippet: String(c.snippet || ''),
                      }))
                    }
                    // v3.8.2 — reset the raw-text accumulator so the
                    // next turn starts clean.
                    ;(session as any)._rawText = ''
                    // Terminal event: flush the final assistant content
                    // synchronously so the streaming text and the idle
                    // state land in the same Vue tick. _flushTerminal
                    // cancels the pending rAF and writes the final
                    // assistantMsgObj.content immediately, avoiding
                    // the visible 'final word appears 16ms after
                    // chatState=idle' glitch that pure frame batching
                    // would cause.
                    _flushTerminal()
                    if (assistantMsgObj) {
                      assistantMsgObj.isStreaming = false
                    } else if (assistantMsg) {
                      // Defensive: if we somehow accumulated text
                      // without ever calling ensureAssistantPushed
                      // (e.g. an upstream event-ordering bug), make
                      // sure the user sees the reply instead of an
                      // empty bubble. This matches opencode's
                      // invariant that 'done' always leaves an
                      // assistant turn on screen.
                      ensureAssistantPushed()
                      if (assistantMsgObj) assistantMsgObj.isStreaming = false
                    }
                    // The ReAct loop ended without the user answering
                    // a pending ask_user question (the loop bails on
                    // context_overflow, network error, or just a model
                    // that stopped emitting). Clear the pending question
                    // so the ClarificationPanel doesn't sit stuck above
                    // the composer with no way to dismiss it.
                    session.clarificationPending = null
                  } else if (event.type === 'skill_distilled' && (event.skillName || event.skill_name)) {
                    const skillName = event.skillName || event.skill_name
                    try {
                      useUIStore().addToast({
                        type: 'success',
                        message: `已自动蒸馏技能：${skillName}`,
                      })
                    } catch { /* toast optional */ }
                  } else if (event.type === 'memory_recall' && Array.isArray(event.memories)) {
                    // Sprint 2 — proactive memory recall. Stash the
                    // list on the session so MemoryRecallBadge can
                    // render a "based on N memories" pill above the
                    // assistant's first message.
                    // NOTE: `sess` is defined here (instead of only in the
                    // reasoning branch below) because v4's memory_recall
                    // event arrives BEFORE the reasoning events in the SSE
                    // stream, and the previous lazy-define pattern would
                    // throw `ReferenceError: sess is not defined`.
                    const sess: any = session
                    if (event.memories.length > 0) {
                      sess.memoryRecalls = event.memories.map((m: any) => ({
                        id: String(m.id ?? m.slug ?? Math.random()),
                        kind: m.kind ?? 'memory',
                        title: m.title ?? '',
                        preview: m.preview ?? m.content?.slice?.(0, 100) ?? '',
                        layer: m.layer ?? 'L1',
                      }))
                    }
                  } else if (event.type === 'reasoning' && event.content) {
                    // DEDUP-FIX: a new thought_start begins a new round
                    // — drop any unfinished thought blocks from the prior
                    // round (their text would otherwise leak into this
                    // round's reasoning and confuse the user). State
                    // reset is centralized here; downstream paths read
                    // fresh data.
                    // v3.10 — Grok-Build-style thought blocks.
                    // Each segment of reasoning is an independent block,
                    // thought_event tells us whether to start a new block,
                    // append to existing, or the thought_end event closes it.
                    const sess: any = session
                    const tev = (event as any).thought_event || ''
                    const tid = (event as any).thought_id || ''
                    let chunk = event.content as string

                    // v3.10.2 — accumulate raw per-block and re-filter,
                    // same pattern as the old reasoningContent logic.
                    // Per-chunk filtering misses markers split across
                    // chunks (e.g. 'Action' + ' Input:').
                    if (tev === 'thought_start' || (!tev && !sess._curThoughtId)) {
                      // v3.10 — new round: clear last round's leftover
                      // thought blocks so the user sees a fresh timeline.
                      // This is the "round" boundary that resets elapsedMs
                      // in the UI; the accumulator (curRawBlock) too.
                      session.thoughtBlocks = []
                      sess._curThoughtId = tid || `t-${Date.now()}`
                      sess._curRawBlock = chunk
                    } else {
                      sess._curRawBlock = (sess._curRawBlock || '') + chunk
                    }
                    // Filter the accumulated block text
                    let filtered = (sess._curRawBlock || '') as string
                    filtered = filtered
                      .replace(/\b(Thought|Action\s*Input|Action|Observation|FINAL_ANSWER)\b\s*[:：]\s*/gi, '')
                      .replace(/\bFINAL_ANSWER\b\s*/gi, '')
                      .replace(/\{[^{}]*(?:\[[^\[\]]*\][^{}]*)*\}/g, '')
                      .replace(/\n{3,}/g, '\n\n')
                      .trim()

                    if (!filtered && tev !== 'thought_start') {
                      // skip empty
                    } else if (tev === 'thought_start' || (!tev && !sess._curThoughtId)) {
                      if (!session.thoughtBlocks) session.thoughtBlocks = []
                      session.thoughtBlocks.push({
                        id: sess._curThoughtId,
                        text: filtered,
                        done: false,
                      })
                    } else {
                      if (!session.thoughtBlocks) session.thoughtBlocks = []
                      const block = session.thoughtBlocks[session.thoughtBlocks.length - 1]
                      if (block) block.text = filtered
                    }
                    // Force Vue reactivity
                    session.thoughtBlocks = [...(session.thoughtBlocks || [])]
                    // Keep reasoningContent for backward compat
                    session.reasoningContent = (session.thoughtBlocks || [])
                      .map((b: any) => b.text).join('\n\n')
                    // Sync live state for PlanTasksPanel
                    syncLiveState({
                      isStreaming: true,
                      thoughts: (session.thoughtBlocks || []).map(tb => ({ id: tb.id, text: tb.text, done: tb.done })),
                      tools: _merge_tools(useLiveState().tools, []),
                      answerLength: (assistantMsg || '').length,
                      sessionId,
                    })
                  } else if (event.type === 'thought_end') {
                    // v3.10 — close the current thought block
                    const sess: any = session
                    if (session.thoughtBlocks && session.thoughtBlocks.length > 0) {
                      const block = session.thoughtBlocks[session.thoughtBlocks.length - 1]
                      if (block) block.done = true
                    }
                    sess._curThoughtId = null
                    sess._curRawBlock = ''  // v3.10.2 — reset for next block
                    session.thoughtBlocks = [...(session.thoughtBlocks || [])]
                    // Sync: thought done → AgentPulse switches from "思考中"
                    syncLiveState({
                      isStreaming: true,
                      thoughts: (session.thoughtBlocks || []).map(tb => ({ id: tb.id, text: tb.text, done: tb.done })),
                      tools: _merge_tools(useLiveState().tools, []),
                      answerLength: (assistantMsg || '').length,
                      sessionId,
                    })
                  } else if (event.type === 'reasoning_clear') {
                    // v3.10 — clear thought blocks + reasoningContent
                    session.reasoningContent = null
                    session.thoughtBlocks = []
                    ;(session as any)._rawReasoning = ''
                    ;(session as any)._curThoughtId = null
                  } else if (
                    // Short form: t=1 (agent_start) with id / n / c / o
                    // Long form (legacy): type='agent_start' + agent_id +
                    // agent_name / node_id / color
                    event.t === 1 || event.type === 'agent_start'
                  ) {
                    // Deep mode: a sub-agent begins. Register it in the
                    // session's agentStreams so SubAgentPanel renders it.
                    if (!session.agentStreams) session.agentStreams = {}
                    const aid = event.id || event.agent_id
                    const aName = event.n || event.agent_name || aid
                    const aNode = event.o || event.node_id
                    if (!session.agentStreams[aid]) {
                      session.agentStreams[aid] = {
                        name: aName || aid,
                        color: event.c || event.color || '#7C3AED',
                        text: '',
                        status: 'running',
                      }
                    } else {
                      session.agentStreams[aid].status = 'running'
                    }
                  } else if (
                    // Short form: t=2 (agent_token) with id / x
                    // Long form (legacy): type='agent_token' + agent_id + text
                    (event.t === 2 || event.type === 'agent_token') &&
                    (event.id || event.agent_id)
                  ) {
                    // Append the token to the matching sub-agent's stream.
                    if (!session.agentStreams) session.agentStreams = {}
                    const aid = event.id || event.agent_id
                    const text = event.x !== undefined ? event.x : event.text
                    if (!session.agentStreams[aid]) {
                      session.agentStreams[aid] = { name: aid, color: '#7C3AED', text: '', status: 'running' }
                    }
                    session.agentStreams[aid].text += (text || '')
                  } else if (
                    // Short form: t=3 (agent_done) with id / s / ms
                    // Long form (legacy): type='agent_done' + agent_id +
                    // status / elapsed_ms
                    (event.t === 3 || event.type === 'agent_done') &&
                    (event.id || event.agent_id)
                  ) {
                    const aid = event.id || event.agent_id
                    if (session.agentStreams && session.agentStreams[aid]) {
                      const st = event.s || event.status
                      session.agentStreams[aid].status = st === 'error' ? 'error' : 'done'
                      session.agentStreams[aid].elapsed_ms = event.ms !== undefined ? event.ms : event.elapsed_ms
                    }
                  } else if (event.type === 'tool' && event.name) {
                    // AI is calling a tool — show it transparently under the
                    // thinking indicator so the user can see what's happening.
                    session.activeToolName = event.name
                    session.activeToolUseId = event.tool_use_id || `tool-${Date.now()}-${Math.random()}`
                    // Sync live state so AgentPulse shows "调用 <tool>..."
                    syncLiveState({
                      isStreaming: true,
                      thoughts: (session.thoughtBlocks || []).map(tb => ({ id: tb.id, text: tb.text, done: tb.done })),
                      tools: _merge_tools(useLiveState().tools, [{ id: session.activeToolUseId, name: event.name, done: false, isError: false }]),
                      answerLength: (assistantMsg || '').length,
                      sessionId,
                    })
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
                    // instead of "正在准备工具". P0-3 made parallel tools
                    // real: results arrive in COMPLETION order, so pairing
                    // by "first pending" mispooled sibling calls — match by
                    // tool_use_id, fall back to first pending (legacy SSE).
                    const evTid = (event as any).tool_use_id
                    let prev = evTid
                      ? session.messages.find((m: any) =>
                          m.type === 'tool_use' && m.isPending === true &&
                          (m as any).toolUseId === evTid)
                      : undefined
                    if (!prev) {
                      prev = session.messages.find((m: any) =>
                        m.type === 'tool_use' && m.isPending === true)
                    }
                    if (prev) {
                      prev.isPending = false
                      ;(prev as any).result = event.result
                      // SDK-standard display data (Claude Code tool rows):
                      // duration + error flag from the v4 tool_end metadata.
                      const _meta = (event as any).metadata || {}
                      ;(prev as any).elapsedMs = typeof _meta.elapsed_ms === 'number'
                        ? _meta.elapsed_ms : undefined
                      if (typeof (event as any).is_error === 'boolean') {
                        ;(prev as any).isError = (event as any).is_error
                      }
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
                    // v4-4 — preview_update: when write_file/edit_file completes,
                    // bump the preview refresh key so any HTML/markdown preview
                    // re-reads the file. (Legacy /api/chat emitted a separate
                    // preview_update SSE event; v4 folds it into tool_result.)
                    if (['write_file', 'edit_file', 'write_xlsx'].includes(tname)) {
                      session.previewRefreshKey = (session.previewRefreshKey || 0) + 1
                    }
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
                    // BUG-FIX (批次3.1): previously this reset assistantPushed
                    // + assistantMsgObj + assistantMsg on every tool_result,
                    // which fragmented ReAct loops with multiple tool calls
                    // into a series of partial bubbles ([text1][tool][text2]
                    // [tool][text3]...). Now we keep the SAME assistant message
                    // object across the whole turn and only clear the text
                    // ARCHITECTURE FIX (Codex-style timeline): after a tool
                    // result, RESET the assistant placeholder so the next
                    // text segment becomes a NEW message. This makes the
                    // messages array interleave naturally:
                    //   [text₁, tool, tool_result, text₂, tool, text₃]
                    // so the user sees text → tool animation → text → ...
                    // instead of one giant text block with tools stuck on top.
                    ;(session as any)._rawText = ''
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
                    // Backend error (API error, rate limit, etc.).
                    // Terminal event: flush the final assistant
                    // placeholder synchronously so the streamed content
                    // and the error toast land in the same tick.
                    _flushTerminal()
                    pushChatError(event.message)
                    // P2-12 — mark the tab error so Sidebar can flag it.
                    try { useTabStore().setTabStatus(sessionId, 'error') } catch { /* ignore */ }
                  } else if (event.type === 'cancelled') {
                    // User-initiated abort acknowledgement. The backend
                    // does not emit this yet (round-2 audit gap), but we
                    // accept the event here so the moment it does ship,
                    // the chatStore is wired correctly. Flush the final
                    // text first so the user sees the last generated
                    // token before the 'cancelled' marker renders.
                    _flushTerminal()
                    if (session.pendingPermission) {
                      // Surface permission-cancel as a normal error so the
                      // permission dialog closes on its own.
                      pushChatError('操作已取消')
                    }
                  }
              }
            }
          }
          // BUG-FIX (Deep-Review C2): stream ended without a terminal event
          // (backend crash, proxy drop, renderer kill). Recover the tail
          // buffer + stop the caret + clear streamingText so we don't
          // leave a "ghost" streaming bubble blinking forever on a
          // finalized message.
          _flushTerminal()
          if (assistantMsgObj) assistantMsgObj.isStreaming = false
          session.streamingText = ''
          session.chatState = 'idle'
        })
        .catch((err: any) => {
          // A new message aborts the previous in-flight request via
          // session._abortCtrl — that's expected, not an error.
          if (err && err.name === 'AbortError') {
            if (!session.debugSSELog) session.debugSSELog = []
            session.debugSSELog.push({ t: Date.now(), type: 'ABORT', preview: 'fetch aborted' })
            return
          }
          // Network-level failure (backend down, connection refused, etc.).
          // Surface a concrete reason instead of a blank red state.
          const reason =
            err && err.message
              ? `无法连接到后端服务 (${err.message})`
              : '无法连接到后端服务，请确认服务已启动'
          if (!session.debugSSELog) session.debugSSELog = []
          session.debugSSELog.push({ t: Date.now(), type: 'NETWORK_ERROR', preview: reason })
          pushChatError(reason)
        })
    },

    stopGeneration(sessionId: string) {
      const session = this.sessions[sessionId]
      if (!session) return
      // Abort the in-flight SSE so backend work can stop promptly.
      if (session._abortCtrl) {
        try {
          session._abortCtrl.abort()
        } catch {
          /* ignore */
        }
      }
      session.chatState = 'stopped'
      session.streamingText = ''
      session.streamingToolInput = ''
      session.activeToolUseId = null
      session.activeToolName = null
      session.activeThinkingId = null
    },

    /** P0-4: rehydrate live HITL confirm cards for a session.
     *  Covers tab switches / UI refreshes while the turn streams in
     *  another connection — the backend keeps pending confirmations
     *  keyed by session. Dedupes against cards already in the queue. */
    async rehydratePendingConfirms(sessionId: string) {
      if (!sessionId) return
      try {
        const res = await fetch(getApiUrl(
          `/api/v4/chat/confirm/pending?conversation_id=${encodeURIComponent(sessionId)}`))
        if (!res.ok) return
        const data = await res.json()
        const items: any[] = data?.pending || []
        const session = this.sessions[sessionId]
        if (!session) return
        for (const it of items) {
          if (!it?.tool_use_id) continue
          if (session.pendingToolConfirms.some((c: any) => c.toolUseId === it.tool_use_id)) continue
          session.pendingToolConfirms.push({
            toolUseId: it.tool_use_id,
            toolName: it.tool_name || '',
            input: it.tool_input || {},
          })
        }
      } catch { /* offline / server restart — nothing to rehydrate */ }
    },

    /** HITL: respond to the head-of-queue tool confirmation (Approve/Deny).
     *  Parallel tools queue several cards; answering resolves the current
     *  one and the next card (if any) slides in. */
    async respondToolConfirm(sessionId: string, approved: boolean) {
      const session = this.sessions[sessionId]
      if (!session?.pendingToolConfirms?.length) return
      const req = session.pendingToolConfirms.shift()!
      try {
        await fetch(getApiUrl('/api/v4/chat/confirm'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            conversation_id: sessionId,
            tool_use_id: req.toolUseId,
            approved,
          }),
        })
      } catch { /* network error — backend timeout rejects safely */ }
    },

    /**
     * Codex-style mid-run steer: inject guidance into the active turn
     * without aborting (backend drains between ReAct steps / deep waves;
     * quick does one follow-up after the first answer).
     */
    async steerMessage(sessionId: string, text: string): Promise<boolean> {
      const body = (text || '').trim()
      if (!sessionId || !body) return false
      const session = this.getSession(sessionId)
      try {
        const res = await fetch(
          getApiUrl(`/api/sessions/${encodeURIComponent(sessionId)}/steer`),
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: body }),
          },
        )
        if (!res.ok) {
          const err = await res.text().catch(() => '')
          throw new Error(err || `HTTP ${res.status}`)
        }
        // Visible marker in the timeline so the user sees the steer landed.
        const id = nextId()
        session.messages.push({
          type: 'user_text',
          content: `🎯 Steer: ${body}`,
          id,
          transcriptMessageId: id,
          timestamp: Date.now(),
        } as any)
        this._persistSession(sessionId)
        return true
      } catch (e: any) {
        const errId = nextId()
        session.messages.push({
          type: 'assistant_text',
          content: `Steer 失败: ${e?.message || e}`,
          id: errId,
          transcriptMessageId: errId,
          timestamp: Date.now(),
        } as any)
        return false
      }
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
      //
      // v4 — cancel any in-flight load for this same session before
      // starting a new one. Without this guard the user jumping
      // A→B→A produces two concurrent fetches that race to write the
      // shared `sessions[sessionId]` slot. The trailing write wins
      // and the messages get torn.
      const previous = _inflightLoadHistory.get(sessionId)
      if (previous) previous.abort()
      const controller = new AbortController()
      _inflightLoadHistory.set(sessionId, controller)

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
        const res = await fetch(
          getApiUrl(`/api/sessions/${encodeURIComponent(sessionId)}/messages`),
          { signal: controller.signal },
        )
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
          // v4 — normalize legacy aliases. Server may persist with the
          // bare shape `type: 'user'` (no _text suffix). Coerce to the
          // canonical 'user_text' / 'assistant_text' so the rest of the
          // code (MessageList dispatch, messageListUtils, buildRenderModel)
          // only has to think about one spelling. This also unblocks the
          // MessageList type-alias I added so it accepts both.
          let type = m.type || (role === 'user' || role === 'user_text' ? 'user_text' : 'assistant_text')
          if (type === 'user') type = 'user_text'
          else if (type === 'assistant') type = 'assistant_text'
          // v3.7.6 — sanitize historical assistant messages: older
          // backend builds (before the streaming FINAL_ANSWER
          // detector) could persist the raw ReAct protocol text
          // ('Thought:', 'Action:', 'FINAL_ANSWER:') into the
          // stored assistant_text content. Strip those on load so
          // the user doesn't see protocol noise from prior buggy
          // turns. We only touch assistant_text; user_text is
          // preserved verbatim.
          let content = m.content || m.text || ''
          if (type === 'assistant_text' && content) {
            content = content
              .replace(/\b(Thought|Action\s*Input|Action|Observation|FINAL_ANSWER)\b\s*[:：]\s*/gi, '')
              .replace(/\n{3,}/g, '\n\n')
              .replace(/^\s+/, '')
          }
          return {
            id,
            transcriptMessageId: id,
            role,
            type,
            content,
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
        // Only clear the in-flight slot if WE are still the latest
        // registration — another loadHistory() may have replaced us
        // and is still flying.
        if (_inflightLoadHistory.get(sessionId) === controller) {
          _inflightLoadHistory.delete(sessionId)
        }
      } catch (err) {
        // Cancelled by a newer loadHistory() call — keep whatever
        // messages state the newer call set, don't surface an error.
        if (controller.signal.aborted) return
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (_inflightLoadHistory.get(sessionId) === controller) {
          _inflightLoadHistory.delete(sessionId)
        }
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
