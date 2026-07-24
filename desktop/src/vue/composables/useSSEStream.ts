/**
 * v4.0 — Unified SSE Stream composable.
 *
 * Replaces the 550-line SSE parsing block inside chatStore.ts.
 * Parses the v4 event protocol (kind field, not type field) and
 * provides reactive state for the UI.
 *
 * Usage:
 *   const { state, connect } = useSSEStream()
 *   await connect('/api/v4/chat', { messages, agent_mode })
 *   // state.thoughtBlocks, state.toolCalls, state.answer, state.isStreaming
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
  question?: string
  options?: string[]
  elapsed_ms?: number
  model?: string
}

// ─── Derived State ───────────────────────────────────────────────────────────

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

// ─── Protocol filter ─────────────────────────────────────────────────────────

const PROTOCOL_RE = /\b(Thought|Action\s*Input|Action|Observation|FINAL_ANSWER)\b\s*[:：]\s*/gi

function filterProtocol(text: string): string {
  return text
    .replace(PROTOCOL_RE, '')
    .replace(/\bFINAL_ANSWER\b\s*/gi, '')
    .replace(/\{[^{}]*(?:\[[^\[\]]*\][^{}]*)*\}/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useSSEStream() {
  const events: Ref<SSEEvent[]> = ref([])
  const thoughtBlocks: Ref<ThoughtBlock[]> = ref([])
  const toolCalls: Ref<ToolCallState[]> = ref([])
  const answer: Ref<string> = ref('')
  const clarifyQuestion = ref<string | null>(null)
  const clarifyOptions = ref<string[]>([])
  const errorMessage = ref<string | null>(null)
  const isStreaming = ref(false)
  const model = ref('')

  let abortCtrl: AbortController | null = null

  async function connect(url: string, body: unknown): Promise<void> {
    // Reset state
    events.value = []
    thoughtBlocks.value = []
    toolCalls.value = []
    answer.value = ''
    clarifyQuestion.value = null
    clarifyOptions.value = []
    errorMessage.value = null
    isStreaming.value = true
    model.value = ''

    abortCtrl = new AbortController()

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

      const reader = res.body?.getReader()
      if (!reader) {
        errorMessage.value = '无法读取数据流'
        isStreaming.value = false
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''
      let curThoughtId = ''
      let curThoughtRaw = ''  // accumulate raw for filtering

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
          handleEvent(ev)
        }
      }
    } catch (err: any) {
      if (err?.name === 'AbortError') return
      errorMessage.value = err?.message || '连接失败'
    } finally {
      isStreaming.value = false
    }
  }

  function handleEvent(ev: SSEEvent) {
    switch (ev.kind) {
      case 'thought_start': {
        curThoughtId = ev.thought_id || `t-${Date.now()}`
        curThoughtRaw = ''
        thoughtBlocks.value = [...thoughtBlocks.value, {
          id: curThoughtId, text: '', done: false,
        }]
        break
      }
      case 'thought_delta': {
        curThoughtRaw += ev.content || ''
        const filtered = filterProtocol(curThoughtRaw)
        const blocks = [...thoughtBlocks.value]
        const last = blocks[blocks.length - 1]
        if (last && last.id === curThoughtId) {
          last.text = filtered
        }
        thoughtBlocks.value = blocks
        break
      }
      case 'thought_end': {
        const blocks = [...thoughtBlocks.value]
        const last = blocks[blocks.length - 1]
        if (last) {
          last.done = true
          last.elapsedMs = ev.elapsed_ms
        }
        thoughtBlocks.value = blocks
        curThoughtId = ''
        curThoughtRaw = ''
        break
      }
      case 'tool_start': {
        toolCalls.value = [...toolCalls.value, {
          id: ev.tool_use_id || `tool-${Date.now()}`,
          name: ev.tool_name || '',
          input: ev.tool_input,
          result: undefined,
          isError: false,
          done: false,
        }]
        break
      }
      case 'tool_end': {
        const calls = [...toolCalls.value]
        const last = calls[calls.length - 1]
        if (last) {
          last.result = typeof ev.tool_result === 'string'
            ? ev.tool_result.slice(0, 500)
            : JSON.stringify(ev.tool_result)?.slice(0, 500)
          last.isError = ev.is_error || false
          last.done = true
        }
        toolCalls.value = calls
        break
      }
      case 'text_delta': {
        let chunk = ev.content || ''
        // Strip protocol markers (defense in depth)
        chunk = chunk.replace(PROTOCOL_RE, '')
        chunk = chunk.replace(/\bAction\s*Input\b\s*[:：]\s*/gi, '')
        if (chunk) answer.value += chunk
        break
      }
      case 'text_end': {
        // No-op for now; could mark answer as finalized
        break
      }
      case 'clarify': {
        clarifyQuestion.value = ev.question || ''
        clarifyOptions.value = ev.options || []
        break
      }
      case 'error': {
        errorMessage.value = ev.content || '未知错误'
        break
      }
      case 'done': {
        model.value = ev.model || ''
        isStreaming.value = false
        break
      }
    }
  }

  function abort() {
    if (abortCtrl) abortCtrl.abort()
    isStreaming.value = false
  }

  const state: ComputedRef<SSEStreamState> = computed(() => ({
    thoughtBlocks: thoughtBlocks.value,
    toolCalls: toolCalls.value,
    answer: answer.value,
    clarifyQuestion: clarifyQuestion.value,
    clarifyOptions: clarifyOptions.value,
    errorMessage: errorMessage.value,
    isStreaming: isStreaming.value,
    model: model.value,
  }))

  return {
    events,
    thoughtBlocks,
    toolCalls,
    answer,
    state,
    isStreaming,
    errorMessage,
    connect,
    abort,
  }
}

export { getApiUrl }
