<template>
  <div v-if="hasContent" data-message-shell="assistant" data-layout="document" class="assistant-message group flex gap-3 py-4">
    <MascotAvatar :size="28" class="mt-0.5 shrink-0" />
    <div class="assistant-message__body min-w-0 flex-1">
      <!-- Error message: styled card instead of raw text -->
      <div v-if="isError" class="error-card" role="alert">
        <span class="material-symbols-outlined text-[18px] shrink-0">error_outline</span>
        <div class="min-w-0 flex-1">
          <p class="error-card__title">{{ errorTitle }}</p>
          <p class="error-card__detail">{{ errorDetail }}</p>
        </div>
      </div>

      <!-- If this is a clarify/choices JSON, render question + chips -->
      <template v-else-if="clarifyData">
        <p class="text-[14px] leading-[1.7] text-[var(--color-text-primary)] mb-3">
          {{ clarifyData.question }}
        </p>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="opt in clarifyData.options"
            :key="opt"
            type="button"
            class="clarify-chip"
            :class="opt === '自定义' ? 'clarify-chip--custom' : ''"
            @click.stop="pickOption(opt)"
          >
            {{ opt === '自定义' ? '✏️ 自定义' : opt }}
          </button>
        </div>
      </template>

      <!-- Regular markdown content -->
      <template v-else>
        <!-- Reasoning / thinking block (Codex-style): live while streaming,
             collapsible. Distinct visual treatment from the final answer. -->
        <div v-if="hasReasoning" class="reasoning-block">
          <button
            type="button"
            class="reasoning-block__toggle"
            @click.stop="toggleReasoning"
          >
            <span class="material-symbols-outlined text-[14px] reasoning-block__icon">
              {{ reasoningExpanded ? 'expand_less' : 'psychology' }}
            </span>
            <span class="reasoning-block__label">
              {{ isStreaming && !cleanContent ? '思考中…' : '思考过程' }}
            </span>
            <span v-if="!reasoningExpanded" class="reasoning-block__hint">点击展开</span>
          </button>
          <div v-if="reasoningExpanded" class="reasoning-block__body">
            <p class="reasoning-block__text">{{ reasoningContent }}</p>
          </div>
        </div>

        <MarkdownRenderer
          :content="cleanContent"
          :streaming="isStreaming"
          class="text-[14px] leading-[1.7] text-[var(--color-text-primary)]"
        />
        <!-- Streaming indicator: breathing dots before the first token,
             then a soft breathing caret once text starts flowing. -->
        <div v-if="isStreaming" class="mt-1.5 flex items-center gap-1.5">
          <template v-if="!cleanContent">
            <span class="typing-dot" />
            <span class="typing-dot" />
            <span class="typing-dot" />
          </template>
          <span
            v-else
            class="inline-block h-[18px] w-[3px] rounded-full bg-[var(--color-brand)] align-text-bottom animate-caret-breathe"
          />
        </div>
      </template>

      <!-- Hover actions -->
      <div class="assistant-message__actions mt-2 flex items-center gap-0.5 opacity-0 transition-opacity duration-150 group-hover:opacity-100 focus-within:opacity-100">
        <button type="button" class="msg-action" :title="copied ? '已复制' : '复制'" @click="copy">
          <span class="material-symbols-outlined text-[16px]">{{ copied ? 'check' : 'content_copy' }}</span>
        </button>
        <button v-if="!isStreaming" type="button" class="msg-action" title="重新生成" @click="regenerate">
          <span class="material-symbols-outlined text-[16px]">refresh</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useChatStore } from '../../stores/chatStore'
import { useTabStore } from '../../stores/tabs'
import MarkdownRenderer from '../markdown/MarkdownRenderer.vue'
import MascotAvatar from '../common/MascotAvatar.vue'

interface ClarifyPayload {
  clarify?: boolean
  choices?: boolean
  question?: string
  options?: string[]
}

const props = withDefaults(defineProps<{
  content: string
  isStreaming?: boolean
  sessionId?: string
  reasoningContent?: string | null
}>(), {
  isStreaming: false,
  sessionId: '',
  reasoningContent: null,
})

const chatStore = useChatStore()
const tabStore = useTabStore()

const copied = ref(false)

// Reasoning (thinking) block — Codex-style: auto-expand while streaming,
// auto-collapse when the final answer begins arriving. User can still
// toggle manually either way.
const reasoningExpanded = ref(true)
const hasReasoning = computed(() => !!(props.reasoningContent || '').trim())
watch(() => props.isStreaming, (streaming) => {
  // When streaming ends, collapse the reasoning block.
  if (!streaming) reasoningExpanded.value = false
})
watch(() => props.content, (c) => {
  // Once the real answer starts flowing in, collapse reasoning to keep
  // focus on the answer (Codex behaviour).
  if ((c || '').trim().length > 0 && reasoningExpanded.value) {
    reasoningExpanded.value = false
  }
})
function toggleReasoning() {
  reasoningExpanded.value = !reasoningExpanded.value
}

const hasContent = computed(() => (props.content || '').trim().length > 0)

// Detect error messages pushed by pushChatError ("错误: ..."). Only treat
// as an error when the *whole* content is a short error line — a legitimate
// answer that happens to start with "Error" (e.g. "Error handling in Go")
// must NOT be misrendered as an error card.
const isError = computed(() => {
  const c = (props.content || '').trim()
  if (c.length > 240) return false                  // long content = a real answer
  // "错误: ..." / "Error: ..." with a colon right after the keyword
  if (/^(错误|Error)\s*[:：]/.test(c)) return true
  // bare "failed ..." only when it's a terse failure, not a sentence
  if (/^failed\b/i.test(c) && c.split(/\s+/).length < 8) return true
  return false
})
const errorTitle = computed(() => {
  const raw = (props.content || '').trim()
  const match = raw.match(/^(错误|Error):\s*(.+)/)
  return match ? '请求出错' : '连接失败'
})
const errorDetail = computed(() => {
  const raw = (props.content || '').trim()
  // Strip the "错误: " or "Error: " prefix
  const stripped = raw.replace(/^(错误|Error)[:\s]*/, '')
  return stripped || raw
})

// Detect clarify/choices JSON at the start of content. Only when the entire
// content is a small JSON object with a clarify/choices flag — never for a
// code block or a long answer that merely begins with '{'.
const clarifyData = computed<ClarifyPayload | null>(() => {
  const c = (props.content || '').trim()
  if (!c.startsWith('{') || !c.endsWith('}')) return null
  if (c.length > 600) return null                    // too big to be a clarify payload
  if (c.includes('```')) return null                 // a fenced code block, not a payload
  try {
    const parsed = JSON.parse(c) as ClarifyPayload
    // Require an explicit clarify/choices signal AND that it looks like a
    // payload (question/options present), not arbitrary JSON data.
    if ((parsed.clarify || parsed.choices) && (parsed as any).question) return parsed
    return null
  } catch {
    return null
  }
})

// For regular messages, strip the JSON prefix if it exists (as fallback)
const cleanContent = computed(() => {
  if (clarifyData.value) return ''
  return props.content || ''
})

function pickOption(opt: string) {
  const sessionId = tabStore.activeTabId
  if (!sessionId) return

  if (opt === '自定义') {
    // Focus the chat input so user can type
    const el = document.querySelector('[data-testid="chat-input"]') as HTMLElement
    el?.focus()
    return
  }

  // Find the last user message
  const session = chatStore.sessions[sessionId]
  if (!session) return

  const lastUserMsg = [...session.messages]
    .reverse()
    .find((m: any) => m.type === 'user' || m.type === 'user_text')
  const originalQuery = lastUserMsg ? (lastUserMsg as any).content || '' : ''

  // Append choice and send
  const fullQuery = `${originalQuery}（${opt}）`
  chatStore.sendMessage(sessionId, fullQuery)
}

async function copy() {
  try {
    await navigator.clipboard.writeText(props.content)
    copied.value = true
    window.setTimeout(() => (copied.value = false), 1500)
  } catch {
    /* clipboard unavailable */
  }
}

function regenerate() {
  if (!props.sessionId || props.isStreaming) return
  const session = chatStore.sessions[props.sessionId]
  if (!session) return
  // Find the most recent user prompt that produced this assistant turn
  let lastUserIdx = -1
  for (let i = session.messages.length - 1; i >= 0; i--) {
    if (session.messages[i].type === 'user_text') {
      lastUserIdx = i
      break
    }
  }
  if (lastUserIdx === -1) return
  const query = session.messages[lastUserIdx].content || ''
  if (!query.trim()) return
  chatStore.sendMessage(props.sessionId, query)
}
</script>

<style scoped>
.assistant-message {
  display: block;
}

/* Reasoning / thinking block — Codex-style live collapsible. */
.reasoning-block {
  margin-bottom: 10px;
  border-left: 2px solid var(--color-border);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  background: var(--color-surface-container-lowest);
  overflow: hidden;
}
.reasoning-block__toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 10px;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 12px;
  color: var(--color-text-tertiary);
  font-weight: 500;
}
.reasoning-block__toggle:hover { color: var(--color-text-secondary); }
.reasoning-block__icon { font-size: 14px; }
.reasoning-block__label { font-style: italic; }
.reasoning-block__hint { margin-left: auto; opacity: 0.7; font-size: 11px; }
.reasoning-block__body {
  padding: 2px 12px 10px 10px;
}
.reasoning-block__text {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.65;
  font-style: italic;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow-y: auto;
}
.assistant-message__body {
  position: relative;
}

.assistant-message__actions {
  min-height: 0;
}

.msg-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 28px;
  border-radius: 4px;
  color: var(--color-text-secondary);
  background: transparent;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 0.12s, color 0.12s, border-color 0.12s;
}
.msg-action:hover {
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
  border-color: var(--color-border);
}
.msg-action:active {
  transform: scale(0.94);
}

/* Breathing typing dots (pre-first-token) */
.typing-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-brand);
  opacity: 0.35;
  animation: typing-breathe 1.2s ease-in-out infinite;
}
.typing-dot:nth-child(2) { animation-delay: 0.18s; }
.typing-dot:nth-child(3) { animation-delay: 0.36s; }
@keyframes typing-breathe {
  0%, 100% { opacity: 0.25; transform: translateY(0) scale(0.85); }
  50% { opacity: 0.9; transform: translateY(-2px) scale(1); }
}


.clarify-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  background: var(--color-surface);
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius-full);
  font-size: 13px;
  color: var(--color-text-primary);
  cursor: pointer;
  transition: all 0.12s;
  font-family: inherit;
  user-select: none;
}
.clarify-chip:hover {
  background: var(--color-brand);
  border-color: var(--color-brand);
  color: white;
}
.clarify-chip--custom {
  border-style: dashed;
  opacity: 0.75;
}
.clarify-chip--custom:hover {
  border-style: solid;
  opacity: 1;
}

@keyframes caret-breathe {
  0%, 100% { opacity: 0.35; transform: scaleY(0.78); }
  50% { opacity: 1; transform: scaleY(1); }
}
.animate-caret-breathe {
  animation: caret-breathe 1.1s ease-in-out infinite;
  transform-origin: center bottom;
}

/* Error card */
.error-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 12px;
  background: var(--color-error-container, rgba(220, 38, 38, 0.07));
  border: 1px solid var(--color-error, rgba(220, 38, 38, 0.18));
  color: var(--color-on-error-container, #991b1b);
}
.error-card__title {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
  margin-bottom: 2px;
}
.error-card__detail {
  font-size: 13px;
  line-height: 1.5;
  opacity: 0.8;
  word-break: break-word;
}
</style>