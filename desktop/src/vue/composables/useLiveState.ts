/**
 * useLiveState — module-level reactive state shared between the chat store
 * and PlanTasksPanel. Eliminates the fragile chatStore bridge that kept
 * breaking the task monitor + thinking display.
 *
 * the chat store writes to this on every SSE event.
 * PlanTasksPanel reads from this directly — no indirection.
 */
import { reactive } from 'vue'

interface LiveThought {
  id: string
  text: string
  done: boolean
}

interface LiveTool {
  id: string
  name: string
  done: boolean
  isError: boolean
}

interface LiveState {
  isStreaming: boolean
  thoughts: LiveThought[]
  tools: LiveTool[]
  answerLength: number
  sessionId: string | null
}

const state = reactive<LiveState>({
  isStreaming: false,
  thoughts: [],
  tools: [],
  answerLength: 0,
  sessionId: null,
})

/** Called by the chat store on every state change. */
export function syncLiveState(data: Partial<LiveState>) {
  Object.assign(state, data)
}

/** Reset when a new turn starts. */
export function resetLiveState(sessionId: string) {
  state.isStreaming = true
  state.thoughts = []
  state.tools = []
  state.answerLength = 0
  state.sessionId = sessionId
}

/** Called when streaming ends. */
export function endLiveState() {
  state.isStreaming = false
}

/** Read by PlanTasksPanel + any component that needs live agent state. */
export function useLiveState() {
  return state
}
