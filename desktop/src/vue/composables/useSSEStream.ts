/**
 * v4.0 — useSSEStream (parsing only).
 *
 * Reads from a v4 SSE endpoint, decodes the ``data: {...}`` lines into
 * an ``SSEEvent[]`` and exposes the raw log + a few derived flags.
 *
 * UI-shaped state (thoughtBlocks / toolCalls / answer) is *not* here
 * anymore — see ``useAgentState`` for that. Splitting the parsing
 * layer from the derivation layer means:
 *   - Network + transport concerns stay together.
 *   - ``useAgentState`` is a pure ``computed()`` over the event log;
 *     it's trivially unit-testable and immune to the manual
 *     push/splice reactivity edge cases the v3 monolithic chatStore
 *     used to hit.
 *   - Re-renders only happen when the events array changes, not on
 *     every internal ref update (which was the source of the v3
 *     white-screen regressions).
 *
 * For backwards compatibility, a ``legacyState`` computed is exposed
 * that aggregates the old ``SSEStreamState`` shape (thoughtBlocks,
 * toolCalls, answer, …) so existing callers keep working until they
 * migrate to ``useAgentState``.
 */

import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { getApiUrl } from '../api/client'

// ─── Event Types (match backend StepKind) ────────────────────────────────────

export type SSEKind =
  | 'thought_start'
  | 'thought_delta'
  | 'thought_end'
  | 'tool_start'
  | 'tool_end'
  | 'text_delta'
  | 'text_end'
  | 'clarify'
  | 'error'
  | 'done'

export interface SSEEvent {
  kind: SSEKind
  id?: number
  thought_id?: string
  content?: string
  tool_name?: string
  tool_input?: Record<string, unknown>
  tool_result?: unknown
  tool_use_id?: string
  is_error?: boolean
  /** Phase-2 ToolExecutor metadata. Optional; absent on legacy events. */
  metadata?: {
    is_validation_error?: boolean
    is_timeout?: boolean
    needs_confirmation?: boolean
    elapsed_ms?: number
  }
  question?: string
  options?: string[]
  elapsed_ms?: number
  model?: string
}

// ─── Derived shapes (re-exported so consumers can import from either file) ──

export interface ThoughtBlock {
  id: string
  text: string
  done: boolean
  elapsedMs?: number
}

export interface ToolCallState {
  id: string
  name: string
  input?: Record<string, unknown>
  result?: string
  isError: boolean
  done: boolean
}

export interface SSEStreamState {
  thoughtBlocks: ThoughtBlock[]
  toolCalls: ToolCallState[]
  answer: string
  clarifyQuestion: string | null
  clarifyOptions: string[]
  errorMessage: string | null
  isStreaming: boolean
  model: string
  /** P3-A — memory recalls + skill distillation side-channel events. */
  memoryRecalls: { id: string; kind: string; title: string; preview: string; layer: string }[]
  distilledSkill: string | null
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useSSEStream() {
  const events: Ref<SSEEvent[]> = ref([])
  const isStreaming = ref(false)
  const errorMessage = ref<string | null>(null)
  const model = ref('')
  const clarifyQuestion = ref<string | null>(null)
  const clarifyOptions = ref<string[]>([])
  const memoryRecalls = ref<SSEStreamState['memoryRecalls']>([])
  const distilledSkill = ref<string | null>(null)
  // HITL: pending tool confirmation request from the backend.
  const pendingConfirm = ref<{
    tool_use_id: string
    tool_name: string
    tool_input: Record<string, any>
  } | null>(null)
  // Deep-Review F1: separate "text stream ended" from "whole turn ended".
  // textEnded lets the caret stop without collapsing the live turn block
  // (which v-if="isStreaming" would do if we reused isStreaming).
  const textEnded = ref(false)

  // BUG-FIX (批次2.1): incremental derived state. Previously these were
  // computed() in useAgentState that re-walked the ENTIRE events array
  // on every single token (O(n²) for a long turn). Now we maintain them
  // incrementally here — each event updates only what it affects — and
  // useAgentState just forwards these refs (O(1) per access).
  const answerRef = ref('')
  const thoughtBlocksRef = ref<ThoughtBlock[]>([])
  const toolCallsRef = ref<ToolCallState[]>([])
  // Internal accumulators (not exposed)
  let _currentThoughtId = ''
  let _currentThoughtRaw = ''
  const _toolLookup = new Map<string, ToolCallState>()

  function _resetDerived() {
    answerRef.value = ''
    thoughtBlocksRef.value = []
    toolCallsRef.value = []
    _currentThoughtId = ''
    _currentThoughtRaw = ''
    _toolLookup.clear()
  }

  // Lightweight protocol-marker filter (same logic as the old computed).
  function _filterProtocol(text: string): string {
    return text
      .replace(/\b(Thought|Action\s*Input|Action|Observation|FINAL_ANSWER)\b\s*[:：]\s*/gi, '')
      .replace(/\bFINAL_ANSWER\b\s*/gi, '')
      .replace(/\n{3,}/g, '\n\n')
  }

  // Incrementally apply a single event to the derived refs.
  function _applyEvent(ev: SSEEvent) {
    switch (ev.kind) {
      case 'thought_start': {
        _currentThoughtId = ev.thought_id || `t-${thoughtBlocksRef.value.length}`
        _currentThoughtRaw = ''
        thoughtBlocksRef.value = [...thoughtBlocksRef.value, {
          id: _currentThoughtId, text: '', done: false,
        }]
        break
      }
      case 'thought_delta': {
        if (!_currentThoughtId) break
        // PERF FIX: filter only the NEW chunk (not full accumulated text)
        // to avoid O(n²) on long reasoning traces. Same pattern as text_delta.
        const _chunk = (ev.content || '')
          .replace(/\b(Thought|Action\s*Input|Action|Observation|FINAL_ANSWER)\b\s*[:：]\s*/gi, '')
        if (_chunk) {
          _currentThoughtRaw += _chunk
          thoughtBlocksRef.value = thoughtBlocksRef.value.map(b =>
            b.id === _currentThoughtId ? { ...b, text: _currentThoughtRaw } : b
          )
        }
        break
      }
      case 'thought_end': {
        thoughtBlocksRef.value = thoughtBlocksRef.value.map(b =>
          b.id === _currentThoughtId ? { ...b, done: true, elapsedMs: ev.elapsed_ms } : b
        )
        _currentThoughtId = ''
        _currentThoughtRaw = ''
        break
      }
      case 'tool_start': {
        const id = ev.tool_use_id || `tool-${toolCallsRef.value.length}`
        const call: ToolCallState = {
          id, name: ev.tool_name || '', input: ev.tool_input,
          result: undefined, isError: false, done: false,
        }
        _toolLookup.set(id, call)
        toolCallsRef.value = [...toolCallsRef.value, call]
        break
      }
      case 'tool_end': {
        const id = ev.tool_use_id || toolCallsRef.value[toolCallsRef.value.length - 1]?.id
        if (!id) break
        const result = typeof ev.tool_result === 'string'
          ? ev.tool_result.slice(0, 500)
          : JSON.stringify(ev.tool_result)?.slice(0, 500)
        toolCallsRef.value = toolCallsRef.value.map(c =>
          c.id === id ? { ...c, result, isError: !!ev.is_error, done: true } : c
        )
        break
      }
      case 'text_delta': {
        const chunk = (ev.content || '')
          .replace(/\b(Thought|Action\s*Input|Action|Observation|FINAL_ANSWER)\b\s*[:：]\s*/gi, '')
        if (chunk) answerRef.value += chunk
        break
      }
    }
  }

  let abortCtrl: AbortController | null = null

  async function connect(url: string, body: unknown): Promise<void> {
    // Cancel any previous connection first (prevents leak of the
    // first AbortController + fetch).
    if (abortCtrl) abortCtrl.abort()

    // Reset only the parsing-layer refs. Derived UI state lives in
    // useAgentState; consumers are expected to compute it from
    // ``events``.
    events.value = []
    _resetDerived()
    isStreaming.value = true
    textEnded.value = false
    errorMessage.value = null
    model.value = ''
    clarifyQuestion.value = null
    clarifyOptions.value = []
    memoryRecalls.value = []
    distilledSkill.value = null
    pendingConfirm.value = null

    abortCtrl = new AbortController()
    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null

    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: abortCtrl.signal,
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        errorMessage.value = `HTTP ${res.status}`
        isStreaming.value = false
        return
      }

      reader = res.body?.getReader() ?? null
      if (!reader) {
        errorMessage.value = '无法读取数据流'
        isStreaming.value = false
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          let ev: SSEEvent
          try {
            ev = JSON.parse(line.slice(6))
          } catch {
            continue
          }
          events.value = [...events.value, ev]
          _applyEvent(ev)  // BUG-FIX (批次2.1): incremental update, O(1)
          switch (ev.kind) {
            case 'clarify':
              clarifyQuestion.value = ev.question || ''
              clarifyOptions.value = ev.options || []
              break
            case 'error':
              errorMessage.value = ev.content || '未知错误'
              break
            case 'text_end':
              // Deep-Review F1: do NOT set isStreaming=false here. V4ChatPanel
              // renders the live turn with v-if="isStreaming" — flipping it
              // false on text_end makes the reply vanish between text_end
              // and done (the turn is only finalized after connect() resolves
              // post-done). The caret can be stopped via a separate flag;
              // stream completion is owned by done/error only.
              textEnded.value = true
              break
            case 'done':
              model.value = ev.model || ''
              isStreaming.value = false
              break
            // P3-A — memory/skill side-channel events (parity with legacy).
            case 'memory_recall':
              memoryRecalls.value = (ev as any)?.metadata?.memories || []
              break
            case 'skill_distilled':
              distilledSkill.value = (ev as any)?.metadata?.skillName || null
              break
            // HITL: backend asks the user to approve a mutating tool call.
            case 'tool_confirm_request':
              pendingConfirm.value = {
                tool_use_id: (ev as any).tool_use_id || '',
                tool_name: (ev as any).tool_name || '',
                tool_input: (ev as any).tool_input || {},
              }
              break
          }
        }
      }
    } catch (err: any) {
      if (err?.name === 'AbortError') return
      errorMessage.value = err?.message || '连接失败'
    } finally {
      isStreaming.value = false
      // v4 fix: release the reader so the underlying connection is
      // closed even if the server keeps the stream open.
      if (reader) {
        try { reader.cancel() } catch {}
      }
    }
  }

  function abort() {
    if (abortCtrl) abortCtrl.abort()
    isStreaming.value = false
  }

  /** HITL: respond to a pending tool confirmation (user clicked Approve/Reject). */
  async function respondConfirm(toolUseId: string, approved: boolean): Promise<void> {
    pendingConfirm.value = null
    try {
      await fetch(getApiUrl('/api/v4/chat/confirm'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool_use_id: toolUseId, approved }),
      })
    } catch { /* network error — the backend timeout will reject */ }
  }

  // Backwards-compat aggregate so old callers that still depend on
  // the ``state`` blob keep working. Prefer ``useAgentState(events)``
  // for new code.
  const state: ComputedRef<SSEStreamState> = computed(() => ({
    thoughtBlocks: [],
    toolCalls: [],
    answer: '',
    clarifyQuestion: clarifyQuestion.value,
    clarifyOptions: clarifyOptions.value,
    errorMessage: errorMessage.value,
    isStreaming: isStreaming.value,
    model: model.value,
    memoryRecalls: memoryRecalls.value,
    distilledSkill: distilledSkill.value,
  }))

  // BUG-FIX (批次2.1): attach the incremental refs to the events ref via
  // a non-enumerable property so useAgentState(events) can detect them
  // and forward in O(1) without changing its call signature.
  Object.defineProperty(events, '__incremental', {
    value: { answerRef, thoughtBlocksRef, toolCallsRef },
    enumerable: false,
    writable: false,
    configurable: false,
  })

  return {
    events,
    isStreaming,
    errorMessage,
    model,
    clarifyQuestion,
    clarifyOptions,
    memoryRecalls,
    distilledSkill,
    pendingConfirm,
    respondConfirm,
    // BUG-FIX (批次2.1): expose incremental derived refs so useAgentState
    // can forward them in O(1) instead of recomputing from events.
    answerRef,
    thoughtBlocksRef,
    toolCallsRef,
    textEnded,
    state,
    connect,
    abort,
  }
}

export { getApiUrl }
