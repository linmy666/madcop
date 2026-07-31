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
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useSSEStream() {
  const events: Ref<SSEEvent[]> = ref([])
  const isStreaming = ref(false)
  const errorMessage = ref<string | null>(null)
  const model = ref('')
  const clarifyQuestion = ref<string | null>(null)
  const clarifyOptions = ref<string[]>([])

  let abortCtrl: AbortController | null = null

  async function connect(url: string, body: unknown): Promise<void> {
    // Cancel any previous connection first (prevents leak of the
    // first AbortController + fetch).
    if (abortCtrl) abortCtrl.abort()

    // Reset only the parsing-layer refs. Derived UI state lives in
    // useAgentState; consumers are expected to compute it from
    // ``events``.
    events.value = []
    isStreaming.value = true
    errorMessage.value = null
    model.value = ''
    clarifyQuestion.value = null
    clarifyOptions.value = []

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
          switch (ev.kind) {
            case 'clarify':
              clarifyQuestion.value = ev.question || ''
              clarifyOptions.value = ev.options || []
              break
            case 'error':
              errorMessage.value = ev.content || '未知错误'
              break
            case 'done':
              model.value = ev.model || ''
              isStreaming.value = false
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
  }))

  return {
    events,
    isStreaming,
    errorMessage,
    model,
    clarifyQuestion,
    clarifyOptions,
    state,
    connect,
    abort,
  }
}

export { getApiUrl }
