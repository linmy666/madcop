<script setup lang="ts">
/**
 * V4ChatPanel — unified chat panel using useSSEStream.
 *
 * Renders the v4 SSE event stream:
 * - Thought blocks (gray inline text, pulse dots while active)
 * - Tool calls (gray inline with spinner/check/error)
 * - Answer (markdown rendered)
 * - Clarification panel
 * - Error display
 *
 * This component replaces the old MessageList + ThinkingIndicator +
 * ToolCallInline + chatStore SSE parsing chain with a single
 * composable-driven panel.
 */
import { ref, computed, nextTick, watch } from 'vue'
import { useSSEStream, type ThoughtBlock, type ToolCallState } from '../../composables/useSSEStream'
import MarkdownRenderer from '../markdown/MarkdownRenderer.vue'

const props = defineProps<{
  sessionId: string
}>()

const emit = defineEmits<{
  (e: 'clarify', question: string, options: string[]): void
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

// Scroll to bottom on new content
watch([thoughtBlocks, toolCalls, answer], () => {
  nextTick(() => {
    if (scrollRef.value) {
      scrollRef.value.scrollTop = scrollRef.value.scrollHeight
    }
  })
}, { deep: true })

// User's message history (local, simple)
const userMessages = ref<{ role: 'user'; content: string; timestamp: number }[]>([])
const assistantAnswer = computed(() => answer.value)

// Full conversation for display
interface Turn {
  id: number
  userMessage: string
  thoughts: ThoughtBlock[]
  tools: ToolCallState[]
  answer: string
  error: string | null
  done: boolean
}
const turns = ref<Turn[]>([])
let turnIdCounter = 0

async function send() {
  const text = input.value.trim()
  if (!text || isStreaming.value) return
  input.value = ''

  // Create a new turn
  const turn: Turn = {
    id: ++turnIdCounter,
    userMessage: text,
    thoughts: [],
    tools: [],
    answer: '',
    error: null,
    done: false,
  }
  turns.value.push(turn)

  // Connect to v4 endpoint
  await connect('/api/v4/chat', {
    messages: [
      ...userMessages.value.map(m => ({ role: m.role, content: m.content })),
      { role: 'user', content: text },
    ],
    agent_mode: 'standard',
    conversation_id: props.sessionId,
  })

  // After stream completes, snapshot the state into the turn
  userMessages.value.push({ role: 'user', content: text, timestamp: Date.now() })
  turn.thoughts = [...thoughtBlocks.value]
  turn.tools = [...toolCalls.value]
  turn.answer = answer.value
  turn.error = errorMessage.value
  turn.done = true
}

function stop() {
  abort()
}

function onCompositionStart() { isComposing.value = true }
function onCompositionEnd() { isComposing.value = false }

// Clarification handling
function chooseClarify(option: string) {
  input.value = option
  send()
}

// Streaming overlay (current in-progress turn)
const hasActiveStream = computed(() => isStreaming.value)
</script>

<template>
  <div class="v4-chat">
    <!-- Message area -->
    <div ref="scrollRef" class="v4-chat__scroll">
      <div class="v4-chat__inner">
        <!-- Completed turns -->
        <div v-for="turn in turns" :key="turn.id" class="v4-turn">
          <!-- User message -->
          <div class="v4-turn__user">
            <span>{{ turn.userMessage }}</span>
          </div>

          <!-- AI response -->
          <div class="v4-turn__ai">
            <!-- Thought blocks -->
            <div
              v-for="tb in turn.thoughts"
              :key="tb.id"
              class="v4-thought"
            >
              <span>{{ tb.text }}</span>
            </div>

            <!-- Tool calls -->
            <div
              v-for="tc in turn.tools"
              :key="tc.id"
              class="v4-tool"
              :class="{ 'v4-tool--error': tc.isError }"
            >
              <span class="v4-tool__icon">{{ tc.done ? (tc.isError ? '✗' : '✓') : '⏳' }}</span>
              <span class="v4-tool__name">{{ tc.name }}</span>
            </div>

            <!-- Answer -->
            <div v-if="turn.answer" class="v4-answer">
              <MarkdownRenderer :content="turn.answer" />
            </div>

            <!-- Error -->
            <div v-if="turn.error" class="v4-error">{{ turn.error }}</div>
          </div>
        </div>

        <!-- Active streaming turn -->
        <div v-if="hasActiveStream" class="v4-turn v4-turn--active">
          <div class="v4-turn__ai">
            <!-- Live thought blocks -->
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

            <!-- Live tool calls -->
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

            <!-- Live answer -->
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
      <textarea
        v-model="input"
        class="v4-input__textarea"
        placeholder="输入消息…"
        rows="1"
        @compositionstart="onCompositionStart"
        @compositionend="onCompositionEnd"
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
</template>

<style scoped>
.v4-chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.v4-chat__scroll {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.v4-chat__inner {
  max-width: 860px;
  margin: 0 auto;
}

/* Turn */
.v4-turn {
  margin-bottom: 24px;
}

.v4-turn__user {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}
.v4-turn__user span {
  max-width: 70%;
  padding: 8px 14px;
  background: var(--color-brand, #7c3aed);
  color: #fff;
  border-radius: 14px 14px 4px 14px;
  font-size: 14px;
  line-height: 1.5;
}

.v4-turn__ai {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* Thought block — gray inline text, no frame */
.v4-thought {
  font-size: 13px;
  line-height: 1.7;
  color: var(--color-text-secondary, #555);
  padding: 2px 0;
}
.v4-thought__text {
  white-space: pre-wrap;
  word-break: break-word;
}

/* Thinking dots */
.thinking-dots {
  display: inline-flex;
  align-items: baseline;
  gap: 2px;
  margin-left: 4px;
}
.thinking-dots i {
  width: 3px; height: 3px;
  border-radius: 50%;
  background: var(--color-text-secondary, #555);
  opacity: 0.3;
  animation: thinking-dot-pulse 1.2s ease-in-out infinite;
}
.thinking-dots i:nth-child(2) { animation-delay: 0.15s; }
.thinking-dots i:nth-child(3) { animation-delay: 0.30s; }
@keyframes thinking-dot-pulse {
  0%, 100% { opacity: 0.25; transform: translateY(0); }
  50%      { opacity: 0.9;  transform: translateY(-1px); }
}

/* Tool call — gray inline */
.v4-tool {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 2px 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-tertiary, #999);
}
.v4-tool__icon {
  font-size: 13px;
  color: var(--zcode-diff-added, #1e8a3e);
}
.v4-tool--error .v4-tool__icon {
  color: #e03131;
}
.v4-tool__name {
  font-weight: 400;
}
.v4-tool__spinner {
  width: 10px; height: 10px;
  border-width: 1.5px;
  color: var(--color-text-tertiary, #999);
}

/* Answer */
.v4-answer {
  padding: 8px 0;
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text-primary, #111);
}

/* Error */
.v4-error {
  padding: 8px 12px;
  background: color-mix(in srgb, #ef4444 12%, transparent);
  color: #b91c1c;
  border-radius: 8px;
  font-size: 13px;
}

/* Clarification */
.v4-clarify {
  padding: 14px 16px;
  background: var(--color-surface, #fff);
  border: 1px solid color-mix(in srgb, var(--color-brand, #7c3aed) 28%, var(--color-border));
  border-radius: 14px;
  margin: 8px 0;
}
.v4-clarify__q {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
}
.v4-clarify__opts {
  display: flex; flex-wrap: wrap; gap: 8px;
}
.v4-clarify__opt {
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  background: var(--color-surface-container-low, #f5f5f7);
  color: var(--color-text-secondary, #555);
  border: 1px solid var(--color-border, #e5e5e7);
  border-radius: 999px;
  transition: all 140ms;
}
.v4-clarify__opt:hover {
  background: var(--color-brand, #7c3aed);
  color: #fff;
}

/* Input */
.v4-input {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--color-border, #e5e5e7);
  background: var(--color-surface, #fff);
}
.v4-input__textarea {
  flex: 1;
  padding: 10px 14px;
  font-size: 14px;
  border: 1px solid var(--color-border, #e5e5e7);
  border-radius: 12px;
  resize: none;
  outline: none;
  font-family: inherit;
  caret-color: var(--color-text-primary, #111) !important;
  background: var(--color-surface, #fff);
  color: var(--color-text-primary, #111);
}
.v4-input__textarea:focus {
  border-color: var(--color-text-tertiary, #999);
}
.v4-input__send, .v4-input__stop {
  padding: 10px 20px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  border-radius: 12px;
  transition: opacity 120ms;
}
.v4-input__send {
  background: var(--color-brand, #7c3aed);
  color: #fff;
}
.v4-input__send:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.v4-input__stop {
  background: var(--color-error, #ef4444);
  color: #fff;
}

/* ZCode spinner + stream-in (from globals.css) */
.zcode-spinner {
  display: inline-block;
  border: 1.5px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: zcode-spin 1s linear infinite;
}
.zcode-stream-in {
  animation: zcode-stream-fade 0.6s cubic-bezier(0.16, 1, 0.3, 1) both;
}

@media (prefers-reduced-motion: reduce) {
  .thinking-dots i { animation: none; opacity: 0.5; }
  .zcode-spinner { animation-duration: 2.5s; }
  .zcode-stream-in { animation: none; }
}
</style>