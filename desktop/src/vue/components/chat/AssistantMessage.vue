<template>
  <div v-if="hasContent" data-message-shell="assistant" data-layout="document" class="assistant-message group py-4">
    <div class="assistant-message__body">
      <!-- If this is a clarify/choices JSON, render question + chips -->
      <template v-if="clarifyData">
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
        <MarkdownRenderer
          :content="cleanContent"
          :streaming="isStreaming"
          class="text-[14px] leading-[1.7] text-[var(--color-text-primary)]"
        />
        <span
          v-if="isStreaming"
          class="ml-0.5 inline-block h-4 w-0.5 bg-[var(--color-brand)] align-text-bottom animate-caret-blink"
        />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useChatStore } from '../../stores/chatStore'
import { useTabStore } from '../../stores/tabs'
import MarkdownRenderer from '../markdown/MarkdownRenderer.vue'

interface ClarifyPayload {
  clarify?: boolean
  choices?: boolean
  question?: string
  options?: string[]
}

const props = withDefaults(defineProps<{
  content: string
  isStreaming?: boolean
}>(), {
  isStreaming: false,
})

const chatStore = useChatStore()
const tabStore = useTabStore()

const hasContent = computed(() => (props.content || '').trim().length > 0)

// Detect clarify/choices JSON at the start of content
const clarifyData = computed<ClarifyPayload | null>(() => {
  const c = (props.content || '').trim()
  if (!c.startsWith('{')) return null
  try {
    const parsed = JSON.parse(c) as ClarifyPayload
    if (parsed.clarify || parsed.choices) return parsed
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
</script>

<style scoped>
.assistant-message {
  display: block;
}
.assistant-message__body {
  position: relative;
}

.clarify-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  background: var(--color-surface);
  border: 1.5px solid var(--color-border);
  border-radius: 20px;
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

@keyframes caret-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
.animate-caret-blink {
  animation: caret-blink 1s step-end infinite;
}
</style>