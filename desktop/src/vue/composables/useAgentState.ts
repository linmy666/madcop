/**
 * v4.0 — useAgentState (derived UI state composable).
 *
 * Pure derivation: takes the raw SSE event log from useSSEStream
 * and computes the UI-friendly state objects (ThoughtBlock[],
 * ToolCallState[], running answer text, isStreaming flag).
 *
 * No network, no parsing, no mutation — just ``computed()`` over a
 * Ref<SSEEvent[]>. That means:
 *   - State is always consistent with the event log.
 *   - No manual push/splice bookkeeping that could leak a Vue
 *     reactivity edge case (the original bug class for the v3
 *     white-screen regressions).
 *   - Easy to unit-test: feed events in, assert the computed shape.
 *
 * Phase 3 of the v4 architecture plan: chatStore 1464 → ~300 lines,
 * with composables composing via plain refs.
 */

import { computed, type Ref, type ComputedRef } from 'vue'
import type { SSEEvent, ThoughtBlock, ToolCallState } from './useSSEStream'

// ─── Derived shapes ─────────────────────────────────────────────────────────

export interface AgentState {
  thoughtBlocks: ComputedRef<ThoughtBlock[]>
  toolCalls: ComputedRef<ToolCallState[]>
  answer: ComputedRef<string>
  hasError: ComputedRef<boolean>
  isStreaming: ComputedRef<boolean>
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function filterProtocol(text: string): string {
  return text
    .replace(/\b(Thought|Action\s*Input|Action|Observation|FINAL_ANSWER)\b\s*[:：]\s*/gi, '')
    .replace(/\bFINAL_ANSWER\b\s*/gi, '')
    .replace(/\{[^{}]*(?:\[[^\[\]]*\][^{}]*)*\}/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useAgentState(events: Ref<SSEEvent[]>): AgentState {
  // Thought blocks: walk events, build the list incrementally.
  const thoughtBlocks = computed<ThoughtBlock[]>(() => {
    const blocks: ThoughtBlock[] = []
    let currentId = ''
    let raw = ''
    for (const ev of events.value) {
      if (ev.kind === 'thought_start') {
        currentId = ev.thought_id || `t-${blocks.length}`
        raw = ''
        blocks.push({ id: currentId, text: '', done: false })
      } else if (ev.kind === 'thought_delta') {
        if (!currentId) continue
        raw += ev.content || ''
        const last = blocks[blocks.length - 1]
        if (last && last.id === currentId) last.text = filterProtocol(raw)
      } else if (ev.kind === 'thought_end') {
        const last = blocks[blocks.length - 1]
        if (last) {
          last.done = true
          last.elapsedMs = ev.elapsed_ms
        }
        currentId = ''
        raw = ''
      }
    }
    return blocks
  })

  // Tool calls: similar incremental build, paired by tool_use_id.
  const toolCalls = computed<ToolCallState[]>(() => {
    const calls: ToolCallState[] = []
    const lookup = new Map<string, ToolCallState>()
    for (const ev of events.value) {
      if (ev.kind === 'tool_start') {
        const id = ev.tool_use_id || `tool-${calls.length}`
        const call: ToolCallState = {
          id,
          name: ev.tool_name || '',
          input: ev.tool_input,
          result: undefined,
          isError: false,
          done: false,
        }
        lookup.set(id, call)
        calls.push(call)
      } else if (ev.kind === 'tool_end') {
        const id = ev.tool_use_id || calls[calls.length - 1]?.id
        if (!id) continue
        const call = lookup.get(id)
        if (call) {
          call.result = typeof ev.tool_result === 'string'
            ? ev.tool_result.slice(0, 500)
            : JSON.stringify(ev.tool_result)?.slice(0, 500)
          call.isError = !!ev.is_error
          call.done = true
        }
      }
    }
    return calls
  })

  // Running answer = concatenation of all text_delta contents.
  const answer = computed<string>(() => {
    let buf = ''
    for (const ev of events.value) {
      if (ev.kind === 'text_delta') {
        let chunk = ev.content || ''
        chunk = chunk.replace(
          /\b(Thought|Action\s*Input|Action|Observation|FINAL_ANSWER)\b\s*[:：]\s*/gi,
          '',
        )
        if (chunk) buf += chunk
      }
    }
    return buf
  })

  // Error flag: any error event with non-empty content.
  const hasError = computed<boolean>(() =>
    events.value.some(
      (ev) => ev.kind === 'error' && !!(ev.content || '').trim(),
    ),
  )

  // Streaming = at least one event arrived but no terminal done/error yet.
  const isStreaming = computed<boolean>(() => {
    const evs = events.value
    if (evs.length === 0) return false
    const last = evs[evs.length - 1]
    return last.kind !== 'done' && last.kind !== 'error'
  })

  return { thoughtBlocks, toolCalls, answer, hasError, isStreaming }
}

export { filterProtocol }