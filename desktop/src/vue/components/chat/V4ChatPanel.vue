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
import MarkdownRenderer from '../markdown/MarkdownRenderer.vue'

const props = defineProps<{
  sessionId: string
}>()

const input = ref('')
const isComposing = ref(false)
const scrollRef = ref<HTMLElement | null>(null)

const {
  thoughtBlocks,
  toolCalls,
  answer,
  isStreaming,
  errorMessage,
  clarifyQuestion,
  clarifyOptions,
  connect,
  abort,
} = useSSEStream()

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
.v4-turn__user { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.v4-turn__user span {
  max-width: 70%; padding: 8px 14px;
  background: var(--color-brand, #7c3aed); color: #fff;
  border-radius: 14px 14px 4px 14px; font-size: 14px; line-height: 1.5;
}
.v4-turn__ai { display: flex; flex-direction: column; gap: 6px; }
.v4-thought { font-size: 13px; line-height: 1.7; color: var(--color-text-secondary, #555); padding: 2px 0; }
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
@keyframes zcode-spin { to { transform: rotate(360deg); } }
.v4-answer { padding: 8px 0; font-size: 14px; line-height: 1.7; color: var(--color-text-primary, #111); }
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
  padding: 3px 8px; font-size: 12px;
  border: 1px solid var(--color-border, #e5e5e7); border-radius: 6px;
  background: var(--color-surface, #fff);
  color: var(--color-text-secondary, #555);
  cursor: pointer; outline: none;
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
