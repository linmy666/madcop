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
  // BUG-FIX (批次2.1): the previous implementation used computed() that
  // re-walked the entire events array on every token (O(n²) for a long
  // turn). useSSEStream now maintains incremental refs (answerRef,
  // thoughtBlocksRef, toolCallsRef) updated in O(1) per event. We forward
  // them here as readonly computed so existing consumers
  // (V4ChatPanel reads `.value`) keep working without changes.
  //
  // To preserve backwards compatibility for callers that still create
  // useAgentState with just an events ref (e.g. unit tests), we fall back
  // to the old full-scan computed ONLY when the incremental refs aren't
  // attached to the events ref. In production, useSSEStream always attaches
  // them.
  const incremental = (events as any).__incremental as {
    answerRef?: Ref<string>
    thoughtBlocksRef?: Ref<ThoughtBlock[]>
    toolCallsRef?: Ref<ToolCallState[]>
  } | undefined

  const thoughtBlocks = incremental?.thoughtBlocksRef
    ? computed<ThoughtBlock[]>(() => incremental!.thoughtBlocksRef!.value)
    : computed<ThoughtBlock[]>(() => {
        // Legacy fallback (full scan) — only used in unit tests.
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
            if (last) { last.done = true; last.elapsedMs = ev.elapsed_ms }
            currentId = ''
            raw = ''
          }
        }
        return blocks
      })

  const toolCalls = incremental?.toolCallsRef
    ? computed<ToolCallState[]>(() => incremental!.toolCallsRef!.value)
    : computed<ToolCallState[]>(() => {
        const calls: ToolCallState[] = []
        const lookup = new Map<string, ToolCallState>()
        for (const ev of events.value) {
          if (ev.kind === 'tool_start') {
            const id = ev.tool_use_id || `tool-${calls.length}`
            const call: ToolCallState = { id, name: ev.tool_name || '', input: ev.tool_input, result: undefined, isError: false, done: false }
            lookup.set(id, call)
            calls.push(call)
          } else if (ev.kind === 'tool_end') {
            const id = ev.tool_use_id || calls[calls.length - 1]?.id
            if (!id) continue
            const call = lookup.get(id)
            if (call) {
              call.result = typeof ev.tool_result === 'string' ? ev.tool_result.slice(0, 500) : JSON.stringify(ev.tool_result)?.slice(0, 500)
              call.isError = !!ev.is_error
              call.done = true
            }
          }
        }
        return calls
      })

  const answer = incremental?.answerRef
    ? computed<string>(() => incremental!.answerRef!.value)
    : computed<string>(() => {
        let buf = ''
        for (const ev of events.value) {
          if (ev.kind === 'text_delta') {
            let chunk = ev.content || ''
            chunk = chunk.replace(/\b(Thought|Action\s*Input|Action|Observation|FINAL_ANSWER)\b\s*[:：]\s*/gi, '')
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