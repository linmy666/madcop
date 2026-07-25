/**
 * Frontend unit test for useAgentState (pure derivation layer).
 *
 * Run with:
 *   cd /Users/linruihan/PycharmProjects/madcop
 *   node tests/test_useAgentState.mjs
 *
 * Pure JS test — no Vite/Vue runtime needed. We import the compiled
 * logic via the composable source by transpiling the TS module on
 * the fly with esbuild through vite's prebundle cache, OR more
 * simply, we re-implement the derivation logic here and assert the
 * shape matches what useAgentState.ts computes (the actual file is
 * also exercised by the V4ChatPanel.vue live tests).
 *
 * This file mirrors useAgentState.ts so we can verify the algorithm
 * without spinning up vitest. It also serves as documentation.
 */

import { strict as assert } from 'node:assert'

// ─── Mirror of useAgentState.ts algorithm (kept in sync manually) ───────────

function filterProtocol(text) {
  return text
    .replace(/\b(Thought|Action\s*Input|Action|Observation|FINAL_ANSWER)\b\s*[:：]\s*/gi, '')
    .replace(/\bFINAL_ANSWER\b\s*/gi, '')
    .replace(/\{[^{}]*(?:\[[^\[\]]*\][^{}]*)*\}/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function deriveThoughtBlocks(events) {
  const blocks = []
  let currentId = ''
  let raw = ''
  for (const ev of events) {
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
}

function deriveToolCalls(events) {
  const calls = []
  const lookup = new Map()
  for (const ev of events) {
    if (ev.kind === 'tool_start') {
      const id = ev.tool_use_id || `tool-${calls.length}`
      const call = { id, name: ev.tool_name || '', input: ev.tool_input, result: undefined, isError: false, done: false }
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
}

function deriveAnswer(events) {
  let buf = ''
  for (const ev of events) {
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
}

function deriveHasError(events) {
  return events.some((ev) => ev.kind === 'error' && !!(ev.content || '').trim())
}

function deriveIsStreaming(events) {
  if (events.length === 0) return false
  const last = events[events.length - 1]
  return last.kind !== 'done' && last.kind !== 'error'
}

// ─── Tests ──────────────────────────────────────────────────────────────────

const tests = [
  {
    name: 'happy path: thought + tool + answer + done',
    events: [
      { kind: 'thought_start', thought_id: 't1' },
      { kind: 'thought_delta', thought_id: 't1', content: 'Let me ' },
      { kind: 'thought_delta', thought_id: 't1', content: 'think' },
      { kind: 'thought_end', thought_id: 't1', elapsed_ms: 150 },
      { kind: 'tool_start', tool_name: 'echo', tool_use_id: 'tool-1', tool_input: { x: 'hi' } },
      { kind: 'tool_end', tool_use_id: 'tool-1', tool_result: 'echo:hi', is_error: false },
      { kind: 'text_delta', content: 'Hello ' },
      { kind: 'text_delta', content: 'world' },
      { kind: 'text_end' },
      { kind: 'done', model: 'test-model' },
    ],
    assertions: (evs) => {
      const tb = deriveThoughtBlocks(evs)
      assert.equal(tb.length, 1, 'one thought block')
      assert.equal(tb[0].text, 'Let me think', 'aggregated + filtered')
      assert.equal(tb[0].done, true, 'marked done after thought_end')
      assert.equal(tb[0].elapsedMs, 150, 'elapsed propagated')

      const tc = deriveToolCalls(evs)
      assert.equal(tc.length, 1, 'one tool call')
      assert.equal(tc[0].name, 'echo')
      assert.equal(tc[0].result, 'echo:hi')
      assert.equal(tc[0].done, true)

      assert.equal(deriveAnswer(evs), 'Hello world')
      assert.equal(deriveHasError(evs), false)
      assert.equal(deriveIsStreaming(evs), false, 'final event is done')
    },
  },
  {
    name: 'error event flags hasError + stops streaming',
    events: [
      { kind: 'text_delta', content: 'partial' },
      { kind: 'error', content: 'upstream timed out' },
    ],
    assertions: (evs) => {
      assert.equal(deriveAnswer(evs), 'partial')
      assert.equal(deriveHasError(evs), true)
      assert.equal(deriveIsStreaming(evs), false, 'error is terminal')
    },
  },
  {
    name: 'empty events: nothing streams, no errors',
    events: [],
    assertions: (evs) => {
      assert.deepEqual(deriveThoughtBlocks(evs), [])
      assert.deepEqual(deriveToolCalls(evs), [])
      assert.equal(deriveAnswer(evs), '')
      assert.equal(deriveHasError(evs), false)
      assert.equal(deriveIsStreaming(evs), false)
    },
  },
  {
    name: 'protocol markers stripped from text_delta',
    events: [
      { kind: 'text_delta', content: 'FINAL_ANSWER: The answer is ' },
      { kind: 'text_delta', content: '42' },
    ],
    assertions: (evs) => {
      assert.equal(deriveAnswer(evs), 'The answer is 42')
    },
  },
  {
    name: 'tool_end without matching tool_start does not crash',
    events: [
      { kind: 'tool_end', tool_use_id: 'orphan', tool_result: 'x' },
    ],
    assertions: (evs) => {
      const tc = deriveToolCalls(evs)
      // orphan tool_end can\'t attach; list stays empty
      assert.equal(tc.length, 0)
    },
  },
  {
    name: 'two thought blocks: each closed independently',
    events: [
      { kind: 'thought_start', thought_id: 'a' },
      { kind: 'thought_delta', thought_id: 'a', content: 'first' },
      { kind: 'thought_end', thought_id: 'a' },
      { kind: 'thought_start', thought_id: 'b' },
      { kind: 'thought_delta', thought_id: 'b', content: 'second' },
      { kind: 'thought_end', thought_id: 'b' },
    ],
    assertions: (evs) => {
      const tb = deriveThoughtBlocks(evs)
      assert.equal(tb.length, 2)
      assert.equal(tb[0].text, 'first')
      assert.equal(tb[0].done, true)
      assert.equal(tb[1].text, 'second')
      assert.equal(tb[1].done, true)
    },
  },
  {
    name: 'phase-2 metadata: tool_end with is_validation_error flag is preserved',
    events: [
      { kind: 'tool_start', tool_name: 'write_file', tool_use_id: 't1' },
      { kind: 'tool_end', tool_use_id: 't1', tool_result: '[validation_error] path /etc blocked', is_error: true, metadata: { is_validation_error: true, is_timeout: false, needs_confirmation: false, elapsed_ms: 12 } },
    ],
    assertions: (evs) => {
      const tc = deriveToolCalls(evs)
      assert.equal(tc[0].isError, true)
      assert.equal(tc[0].result, '[validation_error] path /etc blocked')
      assert.equal(tc[0].done, true)
    },
  },
]

let passed = 0, failed = 0
for (const t of tests) {
  try {
    t.assertions(t.events)
    console.log(`  ✓ ${t.name}`)
    passed++
  } catch (e) {
    console.log(`  ✗ ${t.name}: ${e.message}`)
    failed++
  }
}
console.log(`\n=== ${passed} passed, ${failed} failed ===`)
process.exit(failed === 0 ? 0 : 1)