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
import { useAgentState } from '../../composables/useAgentState'
import MarkdownRenderer from '../markdown/MarkdownRenderer.vue'

const props = defineProps<{
  sessionId: string
}>()

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
  connect,
  abort,
} = useSSEStream()

// Derivation layer: pure computed() over the event log. Splits the
// 1464-line chatStore's manual push/splice bookkeeping into a
// single function that's testable in isolation.
const { thoughtBlocks, toolCalls, answer } = useAgentState(events)

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
}
const turns = ref<Turn[]>([])
let turnIdCounter = 0

const conversationMessages = ref<{ role: string; content: string }[]>([])
const selectedAgentMode = ref<'quick' | 'standard' | 'deep'>('standard')
const selectedModel = ref('')

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
      agentMode: d.agentMode || 'standard',
      model: '',
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

  conversationMessages.value.push({ role: 'user', content: text })

  const turn: Turn = {
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
  }
  turns.value.push(turn)

  await connect('/api/v4/chat', {
    messages: conversationMessages.value.map(m => ({ role: m.role, content: m.content })),
    agent_mode: selectedAgentMode.value,
    model: selectedModel.value || undefined,
    conversation_id: props.sessionId,
    work_dir: (() => {
      try { return localStorage.getItem('madcop_workspace_dir') || undefined }
      catch { return undefined }
    })(),
  })

  if (answer.value) {
    conversationMessages.value.push({ role: 'assistant', content: answer.value })
  }
  turn.thoughts = [...thoughtBlocks.value]
  turn.tools = [...toolCalls.value]
  turn.answer = answer.value
  turn.error = errorMessage.value
  turn.done = true
  turn.model = model.value || selectedModel.value

  persistTurns()
}

function stop() {
  abort()
}

function chooseClarify(option: string) {
  input.value = option
  send()
}

// Auto-scroll on new content
watch([thoughtBlocks, toolCalls, answer], () => {
  nextTick(() => {
    if (scrollRef.value) {
      scrollRef.value.scrollTop = scrollRef.value.scrollHeight
    }
  })
}, { deep: true })
</script>

<template>
  <div class="v4-chat-wrap">
    <!-- Message area -->
    <div ref="scrollRef" class="v4-chat__scroll">
      <div class="v4-chat__inner">
        <!-- Completed turns -->
        <div v-for="turn in turns" :key="turn.id" class="v4-turn">
          <div class="v4-turn__user">
            <span>{{ turn.userMessage }}</span>
          </div>
          <div class="v4-turn__ai">
            <div
              v-for="(tb, i) in turn.thoughts"
              :key="`${turn.id}-t-${i}`"
              class="v4-thought"
            >
              <span>{{ tb.text }}</span>
            </div>
            <div
              v-for="(tc, i) in turn.tools"
              :key="`${turn.id}-tc-${i}`"
              class="v4-tool"
              :class="{ 'v4-tool--error': tc.isError }"
            >
              <span class="v4-tool__icon">{{ tc.done ? (tc.isError ? '✗' : '✓') : '⏳' }}</span>
              <span class="v4-tool__name">{{ tc.name }}</span>
            </div>
            <div v-if="turn.answer" class="v4-answer">
              <MarkdownRenderer :content="turn.answer" />
            </div>
            <div v-if="turn.error" class="v4-error">{{ turn.error }}</div>
          </div>
        </div>

        <!-- Active streaming turn -->
        <div v-if="isStreaming" class="v4-turn v4-turn--active">
          <div class="v4-turn__ai">
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
            <div
              v-for="tc in toolCalls"
              :key="tc.id"
              class="v4-tool"
              :class="{ 'v4-tool--error': tc.isError }"
            >
              <span v-if="!tc.done" class="zcode-spinner v4-tool__spinner"></span>
              <span v-else class="v4-tool__icon">{{ tc.isError ? '✗' : '✓' }}</span>
              <span class="v4-tool__name">{{ tc.name }}</span>
            </div>
            <div v-if="answer" class="v4-answer v4-answer--streaming">
              <MarkdownRenderer :content="answer" :streaming="true" />
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
          <option value="quick">快速</option>
          <option value="standard">标准</option>
          <option value="deep">深度</option>
        </select>
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
/* ── Emil Kowalski design tokens (interpolated into the existing system).
   Strong ease-out for UI, on-screen morphs use ease-in-out, both custom. ──*/
.v4-chat-wrap {
  /* Custom easing curves — stronger than built-ins. */
  --ease-out: cubic-bezier(0.23, 1, 0.32, 1);
  --ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);
  --ease: cubic-bezier(0.4, 0, 0.2, 1);
  /* Typography scale — locked at 12/13/14 for consistency. */
  --fs-xs: 12px;
  --fs-sm: 13px;
  --fs-md: 14px;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  min-height: 0;
  /* Slightly higher z than legacy chat so it sits on top during transitions. */
  position: relative;
}

/* ── Scroll area ─────────────────────────────────────────────────── */
.v4-chat__scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 24px 16px 16px;
  /* momentum scrolling on touch devices. */
  -webkit-overflow-scrolling: touch;
}
.v4-chat__inner { max-width: 860px; margin: 0 auto; }

/* ── Turn ─────────────────────────────────────────────────────────── */
.v4-turn { margin-bottom: 24px; }
/* Stagger entering turns. Each turn fades+slides 8px. */
.v4-turn { animation: turn-in 320ms var(--ease-out) both; }
@keyframes turn-in {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* User bubble — speech-bubble shape, brand background. */
.v4-turn__user { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.v4-turn__user span {
  max-width: 70%;
  padding: 9px 14px;
  background: var(--color-brand, #7c3aed);
  color: #fff;
  border-radius: 16px 16px 4px 16px;
  font-size: var(--fs-md);
  line-height: 1.55;
  letter-spacing: -0.005em;
  /* Crisp text on translucent brand bg. */
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
}

/* AI column. */
.v4-turn__ai { display: flex; flex-direction: column; gap: 8px; }

/* Thought blocks — secondary, subdued but not gray-on-gray. */
.v4-thought {
  font-size: var(--fs-sm);
  line-height: 1.7;
  /* mix-on-secondary so it reads as inline reasoning, not noise. */
  color: var(--color-text-secondary, #5b5b66);
  padding: 2px 0;
}
.v4-thought__text {
  white-space: pre-wrap;
  word-break: break-word;
  /* Slight opacity lets the "thinking" read as ambient, not assertive. */
  opacity: 0.78;
}

/* Thinking dots — stagger pulse, ease-in-out (continuous motion = linear-ish). */
.thinking-dots {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: 6px;
  /* Anchor dots to text baseline instead of arbitrary baseline. */
  transform: translateY(-1px);
}
.thinking-dots i {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.3;
  animation: thinking-dot-pulse 1.4s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
.thinking-dots i:nth-child(2) { animation-delay: 0.18s; }
.thinking-dots i:nth-child(3) { animation-delay: 0.36s; }
@keyframes thinking-dot-pulse {
  0%, 100% { opacity: 0.25; transform: translateY(0); }
  50%      { opacity: 0.85; transform: translateY(-2px); }
}

/* Tool calls — pill-like, quiet by default. */
.v4-tool {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  font-size: var(--fs-xs);
  line-height: 1.5;
  font-weight: 500;
  letter-spacing: 0.01em;
  color: var(--color-text-tertiary, #6b7280);
  background: color-mix(in srgb, var(--color-text-tertiary, #6b7280) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-text-tertiary, #6b7280) 14%, transparent);
  border-radius: 999px;
  align-self: flex-start;
  /* Width change animates so the ✓/✗ swap doesn't feel jumpy. */
  transition: background-color 200ms var(--ease), border-color 200ms var(--ease), color 200ms var(--ease);
}
.v4-tool--error {
  color: #b91c1c;
  background: color-mix(in srgb, #ef4444 10%, transparent);
  border-color: color-mix(in srgb, #ef4444 22%, transparent);
}
.v4-tool__icon { font-size: 13px; line-height: 1; color: var(--zcode-diff-added, #16a34a); font-weight: 600; }
.v4-tool--error .v4-tool__icon { color: #e03131; }
.v4-tool__name { font-weight: 500; }

/* Tool spinner — slow enough to feel deliberate. */
.v4-tool__spinner {
  width: 10px;
  height: 10px;
  border: 1.5px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: zcode-spin 0.9s linear infinite;
}
@keyframes zcode-spin { to { transform: rotate(360deg); } }

/* Answer body — generous line-height for reading. */
.v4-answer {
  padding: 4px 0;
  font-size: var(--fs-md);
  line-height: 1.75;
  color: var(--color-text-primary, #111);
  /* Slight letter-spacing tightens the body copy. */
  letter-spacing: -0.003em;
}

/* Error chip. */
.v4-error {
  padding: 10px 12px;
  background: color-mix(in srgb, #ef4444 10%, transparent);
  color: #b91c1c;
  border-radius: 10px;
  font-size: var(--fs-sm);
  border: 1px solid color-mix(in srgb, #ef4444 18%, transparent);
}

/* ── Clarification popover ─────────────────────────────────────────
   Origin-aware: scales from the question, not center. ── */
.v4-clarify {
  padding: 14px 16px;
  background: var(--color-surface, #fff);
  border: 1px solid color-mix(in srgb, var(--color-brand, #7c3aed) 22%, var(--color-border, #e5e5e7));
  border-radius: 14px;
  margin: 8px 0;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  /* Anchor near the top so transform-origin feels right. */
  transform-origin: top left;
  animation: clarify-in 240ms var(--ease-out) both;
}
@keyframes clarify-in {
  from { opacity: 0; transform: scale(0.96); }
  to   { opacity: 1; transform: scale(1); }
}
.v4-clarify__q {
  font-size: var(--fs-md);
  font-weight: 600;
  margin-bottom: 12px;
  letter-spacing: -0.005em;
}
.v4-clarify__opts { display: flex; flex-wrap: wrap; gap: 8px; }
.v4-clarify__opt {
  padding: 7px 14px;
  font-size: var(--fs-sm);
  font-weight: 500;
  letter-spacing: 0.005em;
  cursor: pointer;
  background: var(--color-surface-container-low, #f5f5f7);
  color: var(--color-text-secondary, #555);
  border: 1px solid var(--color-border, #e5e5e7);
  border-radius: 999px;
  /* Specify exact properties: never `transition: all`. */
  transition: background-color 160ms var(--ease-out),
              color 160ms var(--ease-out),
              transform 120ms var(--ease-out),
              border-color 160ms var(--ease-out);
  /* Hide hover scale on touch devices per Emil. */
  will-change: transform;
}
.v4-clarify__opt:hover {
  background: var(--color-brand, #7c3aed);
  color: #fff;
  border-color: var(--color-brand, #7c3aed);
}
.v4-clarify__opt:active { transform: scale(0.97); }

@media (hover: none) {
  .v4-clarify__opt:hover { background: var(--color-surface-container-low, #f5f5f7); color: var(--color-text-secondary, #555); border-color: var(--color-border, #e5e5e7); }
}

/* ── Input column ────────────────────────────────────────────────── */
.v4-input {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 16px 14px;
  border-top: 1px solid var(--color-border, #e5e5e7);
  background: var(--color-surface, #fff);
}
.v4-input__toolbar { display: flex; align-items: center; gap: 8px; }

/* Mode pill — segmented style, but a single select. */
.v4-input__mode {
  padding: 4px 10px;
  font-size: var(--fs-xs);
  font-weight: 500;
  letter-spacing: 0.01em;
  border: 1px solid var(--color-border, #e5e5e7);
  border-radius: 8px;
  background: var(--color-surface, #fff);
  color: var(--color-text-secondary, #555);
  cursor: pointer;
  outline: none;
  transition: border-color 160ms var(--ease-out), background-color 160ms var(--ease-out), transform 120ms var(--ease-out);
}
.v4-input__mode:hover { border-color: var(--color-brand, #7c3aed); }
.v4-input__mode:active { transform: scale(0.97); }
.v4-input__mode:focus-visible { border-color: var(--color-brand, #7c3aed); box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-brand, #7c3aed) 18%, transparent); }

.v4-input__row { display: flex; gap: 8px; align-items: flex-end; }
.v4-input__textarea {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 56px;
  max-height: 200px;
  padding: 11px 14px;
  font-size: var(--fs-md);
  line-height: 1.55;
  letter-spacing: -0.005em;
  border: 1px solid var(--color-border, #e5e5e7);
  border-radius: 14px;
  outline: none;
  font-family: inherit;
  caret-color: var(--color-text-primary, #111) !important;
  background: var(--color-surface, #fff);
  color: var(--color-text-primary, #111);
  /* Animate border so focus feels intentional, not jarring. */
  transition: border-color 180ms var(--ease-out), box-shadow 180ms var(--ease-out), background-color 180ms var(--ease-out);
  resize: none;
}
.v4-input__textarea::placeholder { color: var(--color-text-tertiary, #9ca3af); }
.v4-input__textarea:hover:not(:focus) { border-color: color-mix(in srgb, var(--color-border, #e5e5e7) 70%, var(--color-brand, #7c3aed)); }
.v4-input__textarea:focus {
  border-color: var(--color-brand, #7c3aed);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-brand, #7c3aed) 18%, transparent);
}

/* Send / stop buttons. */
.v4-input__send,
.v4-input__stop {
  padding: 11px 20px;
  font-size: var(--fs-md);
  font-weight: 500;
  letter-spacing: 0.005em;
  cursor: pointer;
  border: none;
  border-radius: 14px;
  min-height: 44px;
  /* Specify exact properties — never `transition: all`. */
  transition: transform 120ms var(--ease-out), filter 160ms var(--ease-out), background-color 160ms var(--ease-out);
}
.v4-input__send {
  background: var(--color-brand, #7c3aed);
  color: #fff;
}
.v4-input__send:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  filter: none;
}
.v4-input__send:not(:disabled):hover { filter: brightness(1.08); }
.v4-input__send:not(:disabled):active { transform: scale(0.97); }

.v4-input__stop {
  background: var(--color-error, #ef4444);
  color: #fff;
}
.v4-input__stop:hover { filter: brightness(1.05); }
.v4-input__stop:active { transform: scale(0.97); }

/* ── Streaming transitions ───────────────────────────────────────── */
.zcode-stream-in { animation: stream-fade 220ms var(--ease-out) both; }
@keyframes stream-fade {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ── Accessibility ─────────────────────────────────────────────────
   Respect prefers-reduced-motion: kill movement, keep opacity. */
@media (prefers-reduced-motion: reduce) {
  .v4-turn,
  .v4-clarify,
  .zcode-stream-in {
    animation: none;
  }
  .thinking-dots i,
  .v4-tool__spinner {
    animation-duration: 4s;
  }
  /* Disable transform on press when reduced motion. */
  .v4-clarify__opt:active,
  .v4-input__send:active,
  .v4-input__stop:active,
  .v4-input__mode:active {
    transform: none;
  }
}

/* ── Mobile-tight spacing — slightly compress vertical rhythm. */
@media (max-width: 640px) {
  .v4-chat__scroll { padding: 16px 12px 12px; }
  .v4-input { padding: 8px 12px 12px; }
}
</style>
