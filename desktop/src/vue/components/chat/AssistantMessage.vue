<script setup lang="ts">
// v3.0 — AssistantMessage (Vue 3)
// Direct translation of AssistantMessage.tsx — same Tailwind classes.
// Markdown rendering deferred to a Vue port of MarkdownRenderer.
import { computed } from 'vue'
import MessageActionBar from './MessageActionBar.vue'

const props = withDefaults(defineProps<{
  content: string
  isStreaming?: boolean
  sessionId?: string
  timestamp?: number
  branchLabel?: string
}>(), {
  isStreaming: false,
})

function shouldUseDocumentLayout(content: string): boolean {
  const n = content.trim()
  if (!n) return false
  if (/```/.test(n)) return true
  if (/^\s{0,3}(#{1,6}\s|[-*+]\s|\d+\.\s|>\s|\.+\|)/m.test(n)) return true
  const paragraphs = n.split(/\n\s*\n/).map((c) => c.trim()).filter(Boolean)
  return paragraphs.length >= 2 || n.split('\n').filter((l) => l.trim()).length >= 8
}

const documentLayout = computed(() => shouldUseDocumentLayout(props.content))
const hasContent = computed(() => props.content.trim().length > 0)
</script>

<template>
  <div v-if="hasContent" class="mb-5 flex justify-start">
    <div
      data-message-shell="assistant"
      :data-layout="documentLayout ? 'document' : 'bubble'"
      :class="[
        'group flex min-w-0 flex-col items-start',
        documentLayout ? 'w-full max-w-full' : 'max-w-[88%] sm:max-w-[80%] lg:max-w-[72%]',
      ]"
    >
      <div
        :class="[
          'rounded-[20px] rounded-tl-[8px] border border-[var(--color-border)]/60 bg-[var(--color-surface)] px-4 py-3 text-sm text-[var(--color-text-primary)] shadow-sm',
          documentLayout ? 'w-full' : 'max-w-full',
        ]"
      >
        <!-- TODO: replace with Vue MarkdownRenderer -->
        <div class="whitespace-pre-wrap break-words leading-relaxed">{{ content }}</div>
        <span
          v-if="isStreaming"
          class="ml-0.5 inline-block h-4 w-0.5 animate-shimmer bg-[var(--color-brand)] align-text-bottom"
        />
      </div>
      <MessageActionBar
        :copy-text="isStreaming ? undefined : content"
        copy-label="复制回复"
        :branch-label="branchLabel"
        align="start"
        :timestamp="timestamp"
        @branch="$emit('branch')"
      />
    </div>
  </div>
</template>
