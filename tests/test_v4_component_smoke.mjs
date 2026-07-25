/**
 * Component-shape smoke test for V4ChatPanel wiring.
 *
 * Phase-3 deliverable: confirms that V4ChatPanel.vue composes
 * useSSEStream (parsing) + useAgentState (derivation) rather than
 * relying on the legacy monolithic chatStore path.
 *
 * Run:
 *   cd /Users/linruihan/PycharmProjects/madcop
 *   node tests/test_v4_component_smoke.mjs
 */

import fs from 'node:fs'
import path from 'node:path'

const root = '/Users/linruihan/PycharmProjects/madcop/desktop/src/vue'
const files = {
  v4: path.join(root, 'components/chat/V4ChatPanel.vue'),
  sse: path.join(root, 'composables/useSSEStream.ts'),
  agent: path.join(root, 'composables/useAgentState.ts'),
}

let failed = 0
function assert(cond, msg) {
  if (!cond) { console.log(`  x ${msg}`); failed++ }
  else console.log(`  ok ${msg}`)
}

const v4 = fs.readFileSync(files.v4, 'utf-8')
const sse = fs.readFileSync(files.sse, 'utf-8')
const agent = fs.readFileSync(files.agent, 'utf-8')

console.log('=== V4ChatPanel.vue wiring (phase-3 composable split) ===')
assert(/import \{ useSSEStream[,\s\w]*\} from ['"]\.\.\/\.\.\/composables\/useSSEStream['"]/.test(v4),
  'imports useSSEStream')
assert(v4.includes("import { useAgentState }"), 'imports useAgentState')
assert(/useAgentState\(events\)/.test(v4),
  'composes useAgentState(events) for derived state')
assert(/events[\s\S]{0,200}\} = useSSEStream\(\)/.test(v4),
  'destructures events from useSSEStream')
assert(v4.includes('.v4-chat-wrap'), 'has .v4-chat-wrap container')
assert(v4.includes('.v4-input__textarea'), 'has .v4-input__textarea')
assert(v4.includes('flex: 1 1 auto'), 'textarea has flex: 1 1 auto')
assert(v4.includes('min-height: 56px'), 'textarea min-height 56px')
assert(v4.includes('v4-input__mode'), 'has agent_mode selector')
assert(/value=["']quick["']/.test(v4) && /value=["']standard["']/.test(v4) && /value=["']deep["']/.test(v4),
  'three agent modes (quick / standard / deep)')

console.log('\n=== useSSEStream.ts (parsing layer) ===')
assert(sse.includes('export function useSSEStream'), 'exports useSSEStream')
assert(/events: Ref<SSEEvent\[\]>/.test(sse) || /events.value/.test(sse), 'returns events ref')
assert(sse.includes('function connect('), 'has connect function')
assert(/JSON\.parse\(line\.slice\(6\)\)/.test(sse), 'parses data: lines')
assert(!sse.includes('function handleEvent'), 'NO monolithic handleEvent — derivation moved to useAgentState')

console.log('\n=== useAgentState.ts (derivation layer) ===')
assert(agent.includes('export function useAgentState'), 'exports useAgentState')
assert(agent.includes('thoughtBlocks = computed'), 'derives thoughtBlocks')
assert(agent.includes('toolCalls = computed'), 'derives toolCalls')
assert(agent.includes('answer = computed'), 'derives answer')
assert(agent.includes('isStreaming = computed'), 'derives isStreaming')
assert(/events\.value\.some/.test(agent), 'computes hasError from events')

console.log(`\n=== ${failed === 0 ? 'PASS' : 'FAIL'} (${failed} failures) ===`)
process.exit(failed === 0 ? 0 : 1)