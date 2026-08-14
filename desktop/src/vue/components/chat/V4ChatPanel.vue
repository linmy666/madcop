<script setup lang="ts">
/**
 * V4ChatPanel — v4 unified chat panel.
 *
 * Features:
 * - Renders thought blocks (gray inline text, pulse dots while active)
 * - Renders tool calls (spinner → ✓/✗)
 * - Renders answer (MarkdownRenderer with streaming)
 * - Clarification panel
 * - Agent mode selector (quick / standard / deep)
 * - localStorage persistence (session-keyed turns)
 * - Multi-turn conversation context sent to /api/v4/chat
 */
import { ref, computed, nextTick, watch } from 'vue'
import { useSSEStream, type ThoughtBlock, type ToolCallState } from '../../composables/useSSEStream'
import { syncLiveState, resetLiveState, endLiveState } from '../../composables/useLiveState'
import { useChatStore } from '../../stores/chatStore'
import { useSettingsStore } from '../../stores/settingsStore'
import { useTabStore } from '../../stores/tabStore'
import MarkdownRenderer from '../markdown/MarkdownRenderer.vue'
import InlineDiffCard from './InlineDiffCard.vue'

const props = defineProps<{
  sessionId: string
}>()

// BUG-FIX (批次1.1): V4ChatPanel is the default chat path but historically
// bypassed chatStore entirely, so the right-side Task Monitor panel (which
// reads chatStore.sessions[tabId].plan / chatState) always showed "暂无执行
// 计划" and never reflected live thoughts/tool calls. We now write the
// monitor-relevant derived state back into the store. We do NOT write
// messages — the chat column is rendered by V4ChatPanel's own `turns`, and
// duplicating into store.messages would double-render.
const chatStore = useChatStore()
const settingsStore = useSettingsStore()
const tabStore = useTabStore()

const input = ref('')
const isComposing = ref(false)
const scrollRef = ref<HTMLElement | null>(null)

// Parsing layer: streams SSE events from /api/v4/chat.
const {
  events,
  isStreaming,
  errorMessage,
  model,
  clarifyQuestion,
  clarifyOptions,
  pendingConfirm,
  respondConfirm,
  textEnded,
  thoughtBlocksRef,
  toolCallsRef,
  answerRef,
  connect,
  abort,
} = useSSEStream()

// DIRECT refs from useSSEStream — bypass useAgentState entirely.
// The __incremental property mechanism was unreliable; using raw refs
// guarantees thoughtBlocks/toolCalls/answer update on every SSE event.
const thoughtBlocks = computed(() => thoughtBlocksRef.value)
const toolCalls = computed(() => toolCallsRef.value)
const answer = computed(() => answerRef.value)

interface Turn {
  id: number
  userMessage: string
  thoughts: ThoughtBlock[]
  tools: ToolCallState[]
  answer: string
  error: string | null
  done: boolean
  timestamp: number
  agentMode: string
  model: string
  // #6: regenerate variants
  variants: Turn[]
  activeVariant: number  // index into variants, -1 = no variants
  // #10: fork tracking
  forkedFrom?: number  // turn.id this was forked from (via edit-resubmit)
}
const turns = ref<Turn[]>([])
let turnIdCounter = 0

const conversationMessages = ref<{ role: string; content: string }[]>([])
const selectedAgentMode = ref<'chat' | 'task' | 'create'>('chat')
const selectedModel = ref('')
const thoughtCollapsed = ref(false)  // thinking section collapse state
// #3: tool card accordion — track which tool card is expanded.
const expandedToolId = ref<string | null>(null)
const expandedTurnTool = ref<string | null>(null)  // for completed turns
// #5: edit-and-resubmit user message
const editingTurnId = ref<number | null>(null)
const editText = ref('')
function startEdit(turn: Turn) {
  editingTurnId.value = turn.id
  editText.value = turn.userMessage
}
function cancelEdit() {
  editingTurnId.value = null
  editText.value = ''
}
function applyEdit(turn: Turn) {
  if (!editText.value.trim()) return
  editingTurnId.value = null
  // Truncate turns from this point onward (keep history up to but not
  // including this turn — the edited message becomes a fresh send).
  const idx = turns.value.findIndex(t => t.id === turn.id)
  if (idx >= 0) {
    turns.value = turns.value.slice(0, idx)
    // Rebuild conversation messages from remaining turns
    conversationMessages.value = []
    for (const t of turns.value) {
      conversationMessages.value.push({ role: 'user', content: t.userMessage })
      if (t.answer) conversationMessages.value.push({ role: 'assistant', content: t.answer })
    }
    persistTurns()
  }
  // Send the edited text as a new message
  input.value = editText.value
  editText.value = ''
  // #10: mark that the next turn is a fork of the edited one
  _forkParentId.value = turn.id
  send()
}
const _forkParentId = ref<number | null>(null)
// #2: display mode — controls visibility of thinking blocks + tool cards.
// Verbose = everything; Thinking = reasoning + answer (no tool detail);
// Normal = answer only; Summary = brief overview.
type DisplayMode = 'verbose' | 'thinking' | 'normal' | 'summary'
const displayMode = ref<DisplayMode>(
  (() => { try { return (localStorage.getItem('madcop_display_mode') as DisplayMode) || 'verbose' } catch { return 'verbose' } })()
)
watch(displayMode, (m) => { try { localStorage.setItem('madcop_display_mode', m) } catch {} })
const showThinking = computed(() => displayMode.value === 'verbose' || displayMode.value === 'thinking')
const showTools = computed(() => displayMode.value === 'verbose')
// #8: track thinking duration. Records wall-clock start on first
// thought_start, shows elapsed while active, uses backend elapsedMs
// (summed across all thought blocks) when done.
const _thinkStart = ref<number | null>(null)
const _now = ref(Date.now())  // tick ref for live timer
let _thinkTimer: ReturnType<typeof setInterval> | null = null
const thinkElapsedLabel = computed(() => {
  const doneBlocks = thoughtBlocks.value.filter(t => t.done && t.elapsedMs)
  if (doneBlocks.length > 0) {
    const total = doneBlocks.reduce((s, t) => s + (t.elapsedMs || 0), 0)
    return total >= 1000 ? `思考 ${Math.round(total / 1000)}s` : `思考 ${total}ms`
  }
  if (_thinkStart.value && thoughtBlocks.value.some(t => !t.done)) {
    const sec = Math.round((_now.value - _thinkStart.value) / 1000)
    return `思考 ${sec}s`
  }
  return ''
})
// BUG-FIX: watch thoughtBlocks VALUE (not .length) so thought_end
// (which updates `done` flag via .map → new array identity) triggers
// the watcher. Previously auto-collapse never fired for single-thought
// turns because .length didn't change on thought_end.
watch(thoughtBlocks, (blocks) => {
  if (blocks.length > 0 && !_thinkStart.value) {
    _thinkStart.value = Date.now()
    _thinkTimer = setInterval(() => { _now.value = Date.now() }, 500)
  }
  // Stop timer when all done — but DON'T auto-collapse. The user wants
  // to see the thinking process. Let them collapse manually. Auto-collapse
  // was hiding the reasoning before users could read it.
  if (_thinkTimer && blocks.length > 0 && blocks.every(t => t.done)) {
    clearInterval(_thinkTimer); _thinkTimer = null
  }
}, { deep: false })  // shallow — identity changes on each thought_delta/end

function persistTurns() {
  try {
    const key = `madcop_v4_turns_${props.sessionId}`
    const data = turns.value.map(t => ({
      userMessage: t.userMessage,
      answer: t.answer,
      thoughts: t.thoughts.map(tb => ({ text: tb.text })),
      tools: t.tools.map(tc => ({ name: tc.name, isError: tc.isError })),
      timestamp: t.timestamp,
      agentMode: t.agentMode,
    }))
    localStorage.setItem(key, JSON.stringify(data))
  } catch {}
}

function loadTurns() {
  try {
    const key = `madcop_v4_turns_${props.sessionId}`
    const raw = localStorage.getItem(key)
    if (!raw) return
    const data = JSON.parse(raw) as Array<{
      userMessage: string; answer: string;
      thoughts: Array<{ text: string }>;
      tools: Array<{ name: string; isError: boolean }>;
      timestamp: number; agentMode: string;
    }>
    turns.value = data.map((d, i) => ({
      id: i + 1,
      userMessage: d.userMessage,
      thoughts: d.thoughts.map((t, j) => ({ id: `t-${i}-${j}`, text: t.text, done: true })),
      tools: d.tools.map((t, j) => ({ id: `tc-${i}-${j}`, name: t.name, result: '', isError: t.isError, done: true })),
      answer: d.answer,
      error: null,
      done: true,
      timestamp: d.timestamp,
      agentMode: d.agentMode || 'chat',
      model: '',
      variants: [],
      activeVariant: -1,
    }))
    turnIdCounter = turns.value.length
    conversationMessages.value = []
    for (const t of turns.value) {
      conversationMessages.value.push({ role: 'user', content: t.userMessage })
      if (t.answer) conversationMessages.value.push({ role: 'assistant', content: t.answer })
    }
  } catch {}
}

// Load history on mount
loadTurns()
// Persist on changes
watch(turns, () => {
  persistTurns()
}, { deep: true })

async function send() {
  const text = input.value.trim()
  if (!text || isStreaming.value) return
  input.value = ''
  resetLiveState(props.sessionId)  // notify PlanTasksPanel that streaming started

  // #6: If this is a regeneration, reuse the existing turn + don't push
  // a new user message (the conversation context already has it).
  let turn: Turn
  if (_regenTargetTurnId.value !== null) {
    turn = turns.value.find(t => t.id === _regenTargetTurnId.value)!
    _regenTargetTurnId.value = null
    // Reset the turn for the new generation
    turn.answer = ''
    turn.thoughts = []
    turn.tools = []
    turn.error = null
    turn.done = false
    turn.model = selectedModel.value
  } else {
    conversationMessages.value.push({ role: 'user', content: text })
    turn = {
      id: ++turnIdCounter,
      userMessage: text,
      thoughts: [],
      tools: [],
      answer: '',
      error: null,
      done: false,
      timestamp: Date.now(),
      agentMode: selectedAgentMode.value,
      model: selectedModel.value,
      variants: [],
      activeVariant: -1,
      forkedFrom: _forkParentId.value ?? undefined,
    }
    _forkParentId.value = null
    turns.value.push(turn)
  }

  await connect('/api/v4/chat', {
    messages: conversationMessages.value.map(m => ({ role: m.role, content: m.content })),
    agent_mode: selectedAgentMode.value,
    model: selectedModel.value || undefined,
    conversation_id: props.sessionId,
    // BUG-FIX (批次1.4): previously only model+messages+mode were sent,
    // dropping attachments / output_style / effort / temperature. The
    // backend handler (chat_v4.py) reads all of these, so the V4 path
    // silently lost user settings. Now we mirror chatStore's request body.
    output_style: (settingsStore as any).outputStyle || 'Learning',
    temperature: (settingsStore as any).currentModel?.temperature ?? undefined,
    work_dir: (() => {
      try { return localStorage.getItem('madcop_workspace_dir') || undefined }
      catch { return undefined }
    })(),
  })

  // Deep-Review V3: don't persist partial replies from aborted/errored
  // turns into conversation context. Previously an aborted reply's
  // partial text was pushed to conversationMessages, so the NEXT turn
  // sent a truncated assistant reply as full context — confusing the
  // model. Now we only add to context if there was no error/abort.
  const _hadError = !!errorMessage.value
  if (answer.value && !_hadError) {
    conversationMessages.value.push({ role: 'assistant', content: answer.value })
  }
  turn.thoughts = [...thoughtBlocks.value]
  turn.tools = [...toolCalls.value]
  turn.answer = answer.value
  turn.error = errorMessage.value
  turn.done = true
  endLiveState()  // notify PlanTasksPanel that streaming ended
  turn.model = model.value || selectedModel.value

  persistTurns()
}

function stop() {
  abort()
}

// #6: Regenerate — re-send the last user message and store the old
// answer as a variant. User can page through variants with ◀ ▶.
async function regenerate(turn: Turn) {
  if (isStreaming.value) return
  // Save current answer as a variant
  if (!turn.variants) turn.variants = []
  if (turn.activeVariant < 0 || turn.activeVariant >= turn.variants.length) {
    // First regenerate: push the current state as variant 0
    turn.variants.push({
      ...turn, id: turn.id, variants: [], activeVariant: -1,
    })
    turn.activeVariant = 0
  }
  // Re-send the same user message
  input.value = turn.userMessage
  // Mark that this is a regeneration (send() will create a new turn,
  // but we want to UPDATE this turn instead). Use a flag.
  _regenTargetTurnId.value = turn.id
  await send()
}

const _regenTargetTurnId = ref<number | null>(null)
function switchVariant(turn: Turn, dir: number) {
  if (!turn.variants?.length) return
  turn.activeVariant = Math.max(0, Math.min(turn.variants.length - 1, turn.activeVariant + dir))
  const v = turn.variants[turn.activeVariant]
  if (v) {
    turn.answer = v.answer
    turn.model = v.model
    turn.thoughts = [...v.thoughts]
    turn.tools = [...v.tools]
  }
}

function chooseClarify(option: string) {
  input.value = option
  send()
}

// Auto-scroll on new content — BUT respect user scroll-up.
// If the user scrolled up to read, don't yank them back down.
let _userScrolledUp = false
function _onScroll() {
  if (!scrollRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = scrollRef.value
  const atBottom = scrollHeight - scrollTop - clientHeight < 60
  _userScrolledUp = !atBottom
}
// Auto-scroll on new content (shallow watch — no deep traversal)
watch([thoughtBlocks, toolCalls, answer], () => {
  if (_userScrolledUp) return  // user is reading upstream — don't force scroll
  nextTick(() => {
    if (scrollRef.value) scrollRef.value.scrollTop = scrollRef.value.scrollHeight
  })
})

// BUG-FIX (批次1.1): mirror live agent state into chatStore so the Task
// Monitor panel (PlanTasksPanel) and Sidebar reflect what's happening.
// Without this, the right panel is frozen on "暂无执行计划" during V4 runs.
// We only write monitor-relevant fields (chatState, thoughtBlocks,
// activeToolName) — NOT messages (those are owned by V4ChatPanel.turns).
//
// Deep-Review V2: removed { deep: true }. The watched refs (thoughtBlocks,
// toolCalls) are replaced with new top-level array refs on every change,
// so a SHALLOW watch already fires. Deep-watching caused Vue to traverse
// the entire array contents on every token (O(n) per token = O(n²) over a
// long turn) — the exact regression class 批次2.1 was meant to eliminate.
// Also throttled the store write to every ~200ms via a timer so we don't
// serialize thoughtBlocks on every single token.
let _mirrorPending = false
function _mirrorToStore() {
  const session = chatStore.getSession(props.sessionId)
  if (!session) return
  if (isStreaming.value) {
    const hasToolRunning = toolCalls.value.some(t => !t.done)
    const hasThought = thoughtBlocks.value.some(t => !t.done)
    const hasText = answer.value.length > 0
    session.chatState = hasToolRunning ? 'tool_executing' : (hasText ? 'streaming' : 'busy')
  } else {
    session.chatState = 'idle'
  }
  session.thoughtBlocks = thoughtBlocks.value.map(tb => ({
    id: tb.id, text: tb.text, done: tb.done, elapsedMs: (tb as any).elapsedMs,
  }))
  const runningTool = toolCalls.value.find(t => !t.done) || null
  session.activeToolName = runningTool?.name || null
}
// Write to chatStore IMMEDIATELY on every change — no throttle. The task
// monitor (PlanTasksPanel) needs real-time updates to show "思考中" / "调用工具".
// Previous 200ms throttle made the monitor appear frozen during streaming.
watch([isStreaming, thoughtBlocks, toolCalls, answer], () => {
  _mirrorToStore()
  // Also sync to liveState for PlanTasksPanel (direct, no chatStore bridge)
  syncLiveState({
    isStreaming: isStreaming.value,
    thoughts: thoughtBlocks.value.map(tb => ({ id: tb.id, text: tb.text, done: tb.done })),
    tools: toolCalls.value.map(tc => ({ id: tc.id, name: tc.name, done: tc.done, isError: tc.isError })),
    answerLength: answer.value.length,
    sessionId: props.sessionId,
  })
}, { deep: true })

// Mark tab status (running/idle) so the Sidebar running indicator works
// on the V4 path too — previously this only worked on the legacy path.
watch(isStreaming, (streaming) => {
  try {
    tabStore.setTabStatus(props.sessionId, streaming ? 'running' : 'idle')
  } catch { /* ignore */ }
})

// On unmount or session switch, ensure we don't leave the tab "running".
import { onBeforeUnmount } from 'vue'
onBeforeUnmount(() => {
  try {
    const session = chatStore.getSession(props.sessionId)
    if (session) session.chatState = 'idle'
    tabStore.setTabStatus(props.sessionId, 'idle')
  } catch { /* ignore */ }
  abort()
})
</script>

<template>
  <div class="v4-chat-wrap">
    <!-- Message area -->
    <div ref="scrollRef" class="v4-chat__scroll" @scroll="_onScroll">
      <div class="v4-chat__inner">
        <!-- Completed turns -->
        <div v-for="turn in turns" :key="turn.id" class="v4-turn">
          <!-- C-1: Summary banner (only in summary mode) -->
          <div v-if="displayMode === 'summary' && turn.done" class="v4-summary-banner">
            {{ turn.tools.length }} 工具 · {{ turn.thoughts.length }} 思考 · ~{{ Math.max(1, Math.round((turn.answer||'').length / 3)) }} tokens
          </div>
          <div v-if="turn.forkedFrom" class="v4-fork-badge">已编辑 · 从对话分叉</div>
          <div class="v4-turn__user" :class="{ 'v4-turn__user--editing': editingTurnId === turn.id }">
            <!-- #5: Edit mode -->
            <div v-if="editingTurnId === turn.id" class="v4-edit-box">
              <textarea v-model="editText" class="v4-edit-textarea" rows="2" @keydown.enter.exact.prevent="applyEdit(turn)" @keydown.esc="cancelEdit"></textarea>
              <div class="v4-edit-actions">
                <button type="button" class="v4-edit-btn v4-edit-btn--ghost" @click="cancelEdit">取消</button>
                <button type="button" class="v4-edit-btn v4-edit-btn--primary" @click="applyEdit(turn)">发送</button>
              </div>
            </div>
            <!-- Normal display + edit pencil on hover -->
            <template v-else>
              <span>{{ turn.userMessage }}</span>
              <button type="button" class="v4-edit-pencil" title="编辑并重新发送" @click="startEdit(turn)">✎</button>
            </template>
          </div>
          <div class="v4-turn__ai">
            <div
              v-for="(tb, i) in turn.thoughts"
              :key="`${turn.id}-t-${i}`"
              class="v4-thought"
            >
              <span>{{ tb.text }}</span>
            </div>
            <!-- C-3: unified tool card style (same accordion as active turn) -->
            <template v-if="showTools">
            <div
              v-for="(tc, i) in turn.tools"
              :key="`${turn.id}-tc-${i}`"
              class="v4-tool-card v4-tool-card--done"
              :class="{ 'v4-tool-card--error': tc.isError }"
              @click="expandedTurnTool = expandedTurnTool === `${turn.id}-${i}` ? null : `${turn.id}-${i}`"
            >
              <div class="v4-tool-card__header">
                <span class="v4-tool-card__icon">{{ tc.isError ? '✗' : '✓' }}</span>
                <span class="v4-tool-card__label">{{ tc.isError ? '失败' : '已完成' }}</span>
                <span class="v4-tool-card__name">{{ tc.name }}</span>
                <span class="v4-tool-card__expand">{{ expandedTurnTool === `${turn.id}-${i}` ? '−' : '+' }}</span>
              </div>
              <div v-if="expandedTurnTool !== `${turn.id}-${i}`" class="v4-tool-card__summary">
                {{ tc.name }} · 点击查看详情
              </div>
              <div v-if="expandedTurnTool === `${turn.id}-${i}`" class="v4-tool-card__detail">
                <pre class="v4-tool-card__code">{{ tc.result || '(无结果)' }}</pre>
              </div>
            </div>
            </template>
            <div v-if="turn.answer" class="v4-answer">
              <MarkdownRenderer :content="turn.answer" />
            </div>
            <!-- #7: message metadata (model · ~tokens · time) -->
            <div v-if="turn.done && (turn.model || turn.answer)" class="v4-meta">
              <span v-if="turn.model" class="v4-meta__item">{{ turn.model }}</span>
              <span v-if="turn.answer" class="v4-meta__sep">·</span>
              <span v-if="turn.answer" class="v4-meta__item">~{{ Math.max(1, Math.round(turn.answer.length / 3)) }} tokens</span>
              <span v-if="turn.timestamp" class="v4-meta__sep">·</span>
              <span v-if="turn.timestamp" class="v4-meta__item">{{ new Date(turn.timestamp).toLocaleTimeString('zh', {hour:'2-digit',minute:'2-digit'}) }}</span>
              <!-- #6: regenerate button + variant pager -->
              <button v-if="turn.done && !isStreaming" type="button" class="v4-regen-btn" title="重新生成" @click="regenerate(turn)">↻</button>
              <span v-if="turn.variants?.length" class="v4-variant-pager">
                <button type="button" class="v4-variant-arrow" :disabled="turn.activeVariant <= 0" @click="switchVariant(turn, -1)">◀</button>
                <span class="v4-variant-count">{{ (turn.activeVariant + 1) }}/{{ turn.variants.length + 1 }}</span>
                <button type="button" class="v4-variant-arrow" :disabled="turn.activeVariant >= (turn.variants.length - 1)" @click="switchVariant(turn, 1)">▶</button>
              </span>
            </div>
            <div v-if="turn.error" class="v4-error">{{ turn.error }}</div>
          </div>
        </div>

        <!-- Active streaming turn -->
        <div v-if="isStreaming" class="v4-turn v4-turn--active">
          <div class="v4-turn__ai">
            <!-- Pre-token loading state: show immediately after send,
                 before any thought/text/tool event arrives. Fills the
                 "blank void" gap that ChatGPT/Claude don't have. -->
            <div v-if="!thoughtBlocks.length && !answer && !toolCalls.length && !pendingConfirm" class="v4-pretoken">
              <span class="v4-pretoken__spinner"></span>
              <span class="v4-pretoken__text">思考中…</span>
            </div>
            <!-- Thinking section: collapsible, with label like Claude/Cursor -->
            <div v-if="showThinking && thoughtBlocks.length" class="v4-thinking-section">
              <button
                type="button"
                class="v4-thinking-header"
                @click="thoughtCollapsed = !thoughtCollapsed"
              >
                <span class="v4-thinking-icon">
                  <span v-if="thoughtBlocks.some(t => !t.done)" class="v4-thinking-spinner"></span>
                  <span v-else class="v4-thinking-done">✓</span>
                </span>
                <span class="v4-thinking-label">
                  {{ thoughtBlocks.some(t => !t.done) ? '思考中' : '思考过程' }}
                </span>
                <span v-if="thinkElapsedLabel" class="v4-thinking-elapsed">{{ thinkElapsedLabel }}</span>
                <span class="v4-thinking-toggle">{{ thoughtCollapsed ? '展开' : '收起' }}</span>
              </button>
              <div v-if="!thoughtCollapsed" class="v4-thinking-body">
                <div
                  v-for="(tb, i) in thoughtBlocks"
                  :key="tb.id"
                  class="v4-thought zcode-stream-in"
                >
                  <span class="v4-thought__text">{{ tb.text }}</span>
                  <span
                    v-if="i === thoughtBlocks.length - 1 && !tb.done"
                    class="thinking-dots"
                    aria-hidden="true"
                  ><i></i><i></i><i></i></span>
                </div>
              </div>
            </div>
            <template v-if="showTools">
            <div
              v-for="tc in toolCalls"
              :key="tc.id"
              class="v4-tool-card"
              :class="{ 'v4-tool-card--error': tc.isError, 'v4-tool-card--done': tc.done, 'v4-tool-card--expanded': expandedToolId === tc.id }"
              @click="expandedToolId = expandedToolId === tc.id ? null : tc.id"
            >
              <div class="v4-tool-card__header">
                <span v-if="!tc.done" class="v4-tool-card__spinner"></span>
                <span v-else class="v4-tool-card__icon">{{ tc.isError ? '✗' : '✓' }}</span>
                <span class="v4-tool-card__label">
                  {{ tc.done ? (tc.isError ? '失败' : '已完成') : '调用中' }}
                </span>
                <span class="v4-tool-card__name">{{ tc.name }}</span>
                <span v-if="tc.done" class="v4-tool-card__expand">{{ expandedToolId === tc.id ? '−' : '+' }}</span>
              </div>
              <!-- Collapsed: one-line summary -->
              <div v-if="expandedToolId !== tc.id && tc.input && Object.keys(tc.input).length" class="v4-tool-card__summary">
                {{ Object.entries(tc.input).map(([k,v]) => `${k}: ${String(v).slice(0,40)}`).join(' · ') }}
              </div>
              <!-- Expanded: full input + result -->
              <div v-if="expandedToolId === tc.id" class="v4-tool-card__detail">
                <!-- #1: Inline diff preview for file-edit tools -->
                <InlineDiffCard
                  v-if="['write_file', 'edit_file', 'write_xlsx'].includes(tc.name)"
                  :tool-name="tc.name"
                  :input="tc.input || {}"
                  :result="tc.result"
                />
                <div v-if="tc.input && Object.keys(tc.input).length" class="v4-tool-card__section">
                  <div class="v4-tool-card__section-label">输入</div>
                  <pre class="v4-tool-card__code">{{ JSON.stringify(tc.input, null, 2) }}</pre>
                </div>
                <div v-if="tc.result" class="v4-tool-card__section">
                  <div class="v4-tool-card__section-label">结果</div>
                  <pre class="v4-tool-card__code v4-tool-card__result">{{ tc.result }}</pre>
                </div>
              </div>
            </div>
            </template>
            <!-- HITL: tool confirmation card (Approve/Reject) -->
            <div v-if="pendingConfirm" class="v4-confirm-card">
              <div class="v4-confirm-card__header">
                <span class="v4-confirm-card__icon">⚠</span>
                <span class="v4-confirm-card__title">需要确认</span>
                <span class="v4-confirm-card__tool">{{ pendingConfirm.tool_name }}</span>
              </div>
              <!-- Diff preview for file-edit tools -->
              <InlineDiffCard
                v-if="['write_file', 'edit_file', 'write_xlsx'].includes(pendingConfirm.tool_name)"
                :tool-name="pendingConfirm.tool_name"
                :input="pendingConfirm.tool_input"
                :show-actions="true"
                @accept="respondConfirm(pendingConfirm!.tool_use_id, true)"
                @reject="respondConfirm(pendingConfirm!.tool_use_id, false)"
              />
              <!-- Generic parameter display for other mutating tools -->
              <pre v-else class="v4-confirm-card__params">{{ JSON.stringify(pendingConfirm.tool_input, null, 2) }}</pre>
              <!-- Action buttons -->
              <div v-if="!['write_file', 'edit_file', 'write_xlsx'].includes(pendingConfirm.tool_name)" class="v4-confirm-card__actions">
                <button type="button" class="v4-confirm-btn v4-confirm-btn--reject" @click="respondConfirm(pendingConfirm!.tool_use_id, false)">拒绝</button>
                <button type="button" class="v4-confirm-btn v4-confirm-btn--accept" @click="respondConfirm(pendingConfirm!.tool_use_id, true)">批准</button>
              </div>
            </div>
            <div v-if="answer" class="v4-answer v4-answer--streaming">
              <MarkdownRenderer :content="answer" :streaming="true" />
              <span v-if="!textEnded" class="v4-caret"></span>
            </div>
          </div>
        </div>

        <!-- Clarification -->
        <div v-if="clarifyQuestion" class="v4-clarify">
          <div class="v4-clarify__q">{{ clarifyQuestion }}</div>
          <div class="v4-clarify__opts">
            <button
              v-for="opt in clarifyOptions"
              :key="opt"
              type="button"
              class="v4-clarify__opt"
              @click="chooseClarify(opt)"
            >{{ opt }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Input area -->
    <div class="v4-input">
      <div class="v4-input__toolbar">
        <select v-model="selectedAgentMode" class="v4-input__mode" :disabled="isStreaming">
          <option value="chat">对话</option>
          <option value="task">任务</option>
          <option value="create">创作</option>
        </select>
        <!-- #2: Display mode segmented control -->
        <div class="v4-display-mode">
          <button
            v-for="m in [{v:'verbose',l:'详细'},{v:'thinking',l:'思考'},{v:'normal',l:'简洁'},{v:'summary',l:'概要'}]"
            :key="m.v"
            type="button"
            class="v4-display-mode__btn"
            :class="{ 'v4-display-mode__btn--active': displayMode === m.v }"
            @click="displayMode = m.v as DisplayMode"
          >{{ m.l }}</button>
        </div>
      </div>
      <div class="v4-input__row">
        <textarea
          v-model="input"
          class="v4-input__textarea"
          placeholder="输入消息…"
          rows="1"
          @compositionstart="isComposing = true"
          @compositionend="isComposing = false"
          @keydown.enter.exact.prevent="send"
        />
        <button
          v-if="!isStreaming"
          type="button"
          class="v4-input__send"
          :disabled="!input.trim()"
          @click="send"
        >发送</button>
        <button
          v-else
          type="button"
          class="v4-input__stop"
          @click="stop"
        >停止</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.v4-chat-wrap {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  min-height: 0;
}
.v4-chat__scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
}
.v4-chat__inner { max-width: 860px; margin: 0 auto; }
.v4-turn { margin-bottom: 24px; }
.v4-turn__user { display: flex; justify-content: flex-end; align-items: center; gap: 6px; margin-bottom: 8px; position: relative; }
/* C-1: Summary mode banner */
.v4-summary-banner {
  font-size: 11px; color: var(--color-text-tertiary, #aaa);
  padding: 4px 10px; margin-bottom: 6px; border-radius: 6px;
  background: rgba(128,128,128,0.04); font-variant-numeric: tabular-nums;
}
/* #10: fork badge */
.v4-fork-badge {
  font-size: 10.5px; color: var(--color-text-tertiary, #aaa);
  padding: 2px 0; margin-bottom: 4px;
  border-top: 1px dashed var(--color-border, rgba(128,128,128,0.15));
  padding-top: 6px;
}
/* #5: edit pencil */
.v4-edit-pencil {
  opacity: 0; font-size: 12px; padding: 2px 4px; border: none; background: none;
  color: var(--color-text-tertiary, #aaa); cursor: pointer; transition: opacity .15s;
}
.v4-turn__user:hover .v4-edit-pencil { opacity: 0.6; }
.v4-edit-pencil:hover { opacity: 1 !important; }
.v4-edit-box { width: 100%; max-width: 500px; }
.v4-edit-textarea {
  width: 100%; box-sizing: border-box; padding: 8px 12px; font-size: 13px;
  border: 1px solid var(--color-border, rgba(128,128,128,0.25)); border-radius: 10px;
  background: var(--color-surface, #fff); color: var(--color-text-primary, #111);
  resize: vertical; min-height: 50px; outline: none; font-family: inherit;
}
.v4-edit-textarea:focus { border-color: rgba(128,128,128,0.4); }
.v4-edit-actions { display: flex; justify-content: flex-end; gap: 6px; margin-top: 6px; }
.v4-edit-btn { padding: 4px 14px; border-radius: 8px; font-size: 12px; cursor: pointer; border: none; }
.v4-edit-btn--ghost { background: none; color: var(--color-text-tertiary, #888); }
.v4-edit-btn--primary { background: rgba(128,128,128,0.15); color: var(--color-text-primary, #111); }
.v4-turn__user span {
  max-width: 70%; padding: 8px 14px;
  background: var(--color-brand, #7c3aed); color: #fff;
  border-radius: 14px 14px 4px 14px; font-size: 14px; line-height: 1.5;
}
.v4-turn__ai { display: flex; flex-direction: column; gap: 6px; }
/* Pre-token loading state */
.v4-pretoken { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.v4-pretoken__spinner {
  width: 14px; height: 14px; border: 2px solid var(--color-text-tertiary, #888);
  border-top-color: transparent; border-radius: 50%; animation: zcode-spin 0.8s linear infinite;
}
.v4-pretoken__text { font-size: 13px; color: var(--color-text-tertiary, #888); }
/* Thinking section — collapsible container, grayscale minimalist */
.v4-thinking-section {
  border-radius: 10px; margin-bottom: 4px;
  border: 1px solid var(--color-border, rgba(128,128,128,0.2));
  overflow: hidden;
}
.v4-thinking-header {
  display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 7px 12px; background: none; border: none; cursor: pointer;
  font-size: 12px; color: var(--color-text-tertiary, #888); transition: color .15s;
}
.v4-thinking-header:hover { color: var(--color-text-secondary, #555); }
.v4-thinking-icon { display: flex; align-items: center; width: 14px; height: 14px; }
.v4-thinking-spinner {
  width: 12px; height: 12px; border: 1.5px solid var(--color-text-tertiary, #888);
  border-top-color: transparent; border-radius: 50%; animation: zcode-spin 0.8s linear infinite;
}
.v4-thinking-done { font-size: 13px; color: var(--color-text-tertiary, #aaa); }
.v4-thinking-label { font-weight: 500; font-size: 12px; }
.v4-thinking-elapsed { font-size: 11px; color: var(--color-text-tertiary, #888); opacity: 0.7; font-variant-numeric: tabular-nums; }
.v4-thinking-toggle { margin-left: auto; font-size: 11px; opacity: 0.5; }
.v4-thinking-body { padding: 4px 12px 10px; }
.v4-thought { font-size: 13px; line-height: 1.7; color: var(--color-text-tertiary, #888); padding: 2px 0; }
.v4-thought__text { white-space: pre-wrap; word-break: break-word; }
.thinking-dots { display: inline-flex; align-items: baseline; gap: 2px; margin-left: 4px; }
.thinking-dots i {
  width: 3px; height: 3px; border-radius: 50%;
  background: var(--color-text-secondary, #555); opacity: 0.3;
  animation: thinking-dot-pulse 1.2s ease-in-out infinite;
}
.thinking-dots i:nth-child(2) { animation-delay: 0.15s; }
.thinking-dots i:nth-child(3) { animation-delay: 0.30s; }
@keyframes thinking-dot-pulse {
  0%, 100% { opacity: 0.25; transform: translateY(0); }
  50%      { opacity: 0.9;  transform: translateY(-1px); }
}
.v4-tool { display: flex; align-items: center; gap: 5px; padding: 2px 0; font-size: 12px; line-height: 1.5; color: var(--color-text-tertiary, #999); }
.v4-tool--error .v4-tool__icon { color: #e03131; }
.v4-tool__icon { font-size: 13px; color: var(--zcode-diff-added, #1e8a3e); }
.v4-tool__name { font-weight: 400; }
.v4-tool__spinner {
  width: 10px; height: 10px; border: 1.5px solid currentColor;
  border-top-color: transparent; border-radius: 50%;
  animation: zcode-spin 1s linear infinite;
}
/* Tool call card — grayscale minimalist, accordion */
.v4-tool-card {
  display: flex; flex-direction: column; gap: 4px;
  margin: 6px 0; padding: 7px 12px; border-radius: 8px;
  border: 1px solid var(--color-border, rgba(128,128,128,0.2));
  font-size: 12.5px; transition: all .15s; cursor: pointer;
}
.v4-tool-card:hover { border-color: rgba(128,128,128,0.35); }
.v4-tool-card--done { opacity: 0.7; }
.v4-tool-card--done:hover { opacity: 1; }
.v4-tool-card--expanded { opacity: 1; border-color: rgba(128,128,128,0.35); }
.v4-tool-card__header { display: flex; align-items: center; gap: 6px; }
.v4-tool-card__spinner {
  width: 11px; height: 11px; border: 1.5px solid var(--color-text-tertiary, #888);
  border-top-color: transparent; border-radius: 50%;
  animation: zcode-spin 0.8s linear infinite; flex-shrink: 0;
}
.v4-tool-card__icon { font-size: 13px; font-weight: 600; color: var(--color-text-tertiary, #888); }
.v4-tool-card__label { color: var(--color-text-tertiary, #888); font-size: 11px; }
.v4-tool-card__name { font-weight: 500; color: var(--color-text-secondary, #555); font-family: var(--font-mono, monospace); }
.v4-tool-card__expand { margin-left: auto; font-size: 14px; color: var(--color-text-tertiary, #aaa); }
.v4-tool-card__summary {
  font-size: 11px; color: var(--color-text-tertiary, #aaa); padding-left: 22px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.v4-tool-card__detail { padding: 6px 0 2px; }
.v4-tool-card__section { margin-bottom: 6px; }
.v4-tool-card__section-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--color-text-tertiary, #aaa); margin-bottom: 3px; }
.v4-tool-card__code {
  font-family: var(--font-mono, monospace); font-size: 11px; line-height: 1.5;
  background: rgba(128,128,128,0.06); border-radius: 6px; padding: 8px 10px;
  color: var(--color-text-secondary, #555); white-space: pre-wrap; word-break: break-all;
  max-height: 300px; overflow-y: auto; margin: 0;
}
.v4-tool-card__result { color: var(--color-text-tertiary, #888); }
@keyframes zcode-spin { to { transform: rotate(360deg); } }
.v4-answer { padding: 8px 0; font-size: 14px; line-height: 1.7; color: var(--color-text-primary, #111); }
/* Streaming caret — blinking block at the growth point */
.v4-caret {
  display: inline-block; width: 7px; height: 16px; vertical-align: text-bottom;
  background: var(--color-text-tertiary, #888); border-radius: 1px; margin-left: 2px;
  animation: v4-blink 1s step-end infinite;
}
@keyframes v4-blink { 0%,50% { opacity: 1; } 51%,100% { opacity: 0; } }
/* HITL confirmation card */
.v4-confirm-card {
  margin: 8px 0; padding: 10px 14px; border-radius: 10px;
  border: 1px solid var(--color-border, rgba(128,128,128,0.25));
  background: rgba(128,128,128,0.04);
}
.v4-confirm-card__header { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
.v4-confirm-card__icon { font-size: 14px; }
.v4-confirm-card__title { font-weight: 600; font-size: 13px; color: var(--color-text-primary, #111); }
.v4-confirm-card__tool { font-family: var(--font-mono, monospace); font-size: 12px; color: var(--color-text-secondary, #555); }
.v4-confirm-card__params {
  font-family: var(--font-mono, monospace); font-size: 11px; line-height: 1.5;
  background: rgba(128,128,128,0.06); border-radius: 6px; padding: 8px 10px;
  color: var(--color-text-secondary, #555); white-space: pre-wrap; margin: 6px 0; max-height: 200px; overflow-y: auto;
}
.v4-confirm-card__actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.v4-confirm-btn { padding: 6px 18px; border-radius: 8px; font-size: 13px; font-weight: 500; cursor: pointer; border: 1px solid transparent; transition: all .15s; }
.v4-confirm-btn--reject { background: none; border-color: var(--color-border, rgba(128,128,128,0.25)); color: var(--color-text-secondary, #555); }
.v4-confirm-btn--reject:hover { border-color: rgba(128,128,128,0.4); }
.v4-confirm-btn--accept { background: rgba(128,128,128,0.15); color: var(--color-text-primary, #111); }
.v4-confirm-btn--accept:hover { background: rgba(128,128,128,0.25); }
/* #7: message metadata */
.v4-meta { display: flex; align-items: center; gap: 4px; padding: 2px 0 6px; font-size: 10.5px; color: var(--color-text-tertiary, #aaa); font-variant-numeric: tabular-nums; }
.v4-meta__item { }
.v4-meta__sep { opacity: 0.5; }
/* #6: regenerate + variant pager */
.v4-regen-btn {
  margin-left: 6px; padding: 1px 5px; font-size: 12px; border: none; background: none;
  color: var(--color-text-tertiary, #aaa); cursor: pointer; border-radius: 4px; transition: all .15s;
}
.v4-regen-btn:hover { color: var(--color-text-secondary, #555); background: rgba(128,128,128,0.08); }
.v4-variant-pager { display: inline-flex; align-items: center; gap: 2px; margin-left: 4px; }
.v4-variant-arrow {
  padding: 1px 4px; font-size: 9px; border: none; background: none; cursor: pointer;
  color: var(--color-text-tertiary, #aaa); transition: color .15s;
}
.v4-variant-arrow:hover:not(:disabled) { color: var(--color-text-secondary, #555); }
.v4-variant-arrow:disabled { opacity: 0.3; cursor: default; }
.v4-variant-count { font-size: 10px; color: var(--color-text-tertiary, #aaa); font-variant-numeric: tabular-nums; }
.v4-error { padding: 8px 12px; background: color-mix(in srgb, #ef4444 12%, transparent); color: #b91c1c; border-radius: 8px; font-size: 13px; }
.v4-clarify { padding: 14px 16px; background: var(--color-surface, #fff); border: 1px solid color-mix(in srgb, var(--color-brand, #7c3aed) 28%, var(--color-border)); border-radius: 14px; margin: 8px 0; }
.v4-clarify__q { font-size: 14px; font-weight: 600; margin-bottom: 10px; }
.v4-clarify__opts { display: flex; flex-wrap: wrap; gap: 8px; }
.v4-clarify__opt {
  padding: 6px 14px; font-size: 13px; font-weight: 500; cursor: pointer;
  background: var(--color-surface-container-low, #f5f5f7);
  color: var(--color-text-secondary, #555);
  border: 1px solid var(--color-border, #e5e5e7);
  border-radius: 999px; transition: all 140ms;
}
.v4-clarify__opt:hover { background: var(--color-brand, #7c3aed); color: #fff; }
.v4-input { display: flex; flex-direction: column; gap: 6px; padding: 8px 16px 12px; border-top: 1px solid var(--color-border, #e5e5e7); background: var(--color-surface, #fff); }
.v4-input__toolbar { display: flex; align-items: center; gap: 8px; }
.v4-input__mode {
  font-size: 12px; padding: 3px 8px; border-radius: 6px;
  border: 1px solid var(--color-border, rgba(128,128,128,0.2));
  background: var(--color-surface, #fff); color: var(--color-text-secondary, #555);
  outline: none; cursor: pointer;
}
/* #2: Display mode segmented control */
.v4-display-mode {
  display: inline-flex; border-radius: 6px; overflow: hidden;
  border: 1px solid var(--color-border, rgba(128,128,128,0.2));
}
.v4-display-mode__btn {
  padding: 3px 10px; font-size: 11px; border: none; background: none;
  color: var(--color-text-tertiary, #888); cursor: pointer; transition: all .15s;
}
.v4-display-mode__btn:hover { color: var(--color-text-secondary, #555); }
.v4-display-mode__btn--active {
  background: rgba(128,128,128,0.1); color: var(--color-text-primary, #111); font-weight: 500;
}
.v4-input__row { display: flex; gap: 8px; }
.v4-input__textarea {
  flex: 1 1 auto; min-width: 0;
  min-height: 56px; max-height: 200px;
  padding: 10px 14px; font-size: 14px; line-height: 1.5;
  border: 1px solid var(--color-border, #e5e5e7); border-radius: 12px;
  outline: none; font-family: inherit;
  caret-color: var(--color-text-primary, #111) !important;
  background: var(--color-surface, #fff);
  color: var(--color-text-primary, #111);
}
.v4-input__send, .v4-input__stop {
  padding: 10px 20px; font-size: 14px; font-weight: 500;
  cursor: pointer; border: none; border-radius: 12px;
  transition: opacity 120ms;
}
.v4-input__send { background: var(--color-brand, #7c3aed); color: #fff; }
.v4-input__send:disabled { opacity: 0.4; cursor: not-allowed; }
.v4-input__stop { background: var(--color-error, #ef4444); color: #fff; }
</style>
