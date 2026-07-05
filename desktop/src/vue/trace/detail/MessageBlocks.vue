<script setup lang="ts">
/**
 * MessageBlocks — Vue 3 port of components/trace/detail/MessageBlocks.tsx
 * Renders normalized trace message blocks (text, thinking, tool_use, tool_result, image).
 * Prop-driven: parent passes a NormalizedMessage.
 */
import { ref } from 'vue'
import { useTranslation } from '../../../i18n'
import type { NormalizedBlock, NormalizedMessage } from '../../../lib/trace/types'
import MarkdownRenderer from '../../components/shared/MarkdownRenderer.vue'
import CopyButton from '../../components/shared/CopyButton.vue'
import CodeViewer from '../../components/chat/CodeViewer.vue'

const LONG_TEXT_CHARS = 2000

const ROLE_STYLES: Record<NormalizedMessage['role'], { badge: string; container: string }> = {
  user: {
    badge: 'text-[var(--color-info)]',
    container: 'border-l-[var(--color-info)] bg-[var(--color-info)]/8',
  },
  assistant: {
    badge: 'text-[var(--color-brand)]',
    container: 'border-l-[var(--color-brand)] bg-[var(--color-brand)]/8',
  },
  system: {
    badge: 'text-[var(--color-warning)]',
    container: 'border-l-[var(--color-warning)] bg-[var(--color-warning)]/8',
  },
  tool: {
    badge: 'text-[var(--color-text-tertiary)]',
    container: 'border-l-[var(--color-outline)] bg-[var(--color-surface-container)]/60',
  },
}

const props = defineProps<{
  message: NormalizedMessage
}>()

const t = useTranslation()

function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2) ?? 'null'
  } catch {
    return String(value)
  }
}

function extractPlainText(content: unknown): string | null {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    const parts: string[] = []
    for (const item of content) {
      if (typeof item === 'string') {
        parts.push(item)
        continue
      }
      if (item && typeof item === 'object' && typeof (item as { text?: unknown }).text === 'string') {
        parts.push((item as { text: string }).text)
        continue
      }
      return null
    }
    return parts.join('\n')
  }
  return null
}
</script>

<template>
  <div
    :class="['trace-message-cv rounded-[var(--radius-md)] border-l-2 px-3 py-2', ROLE_STYLES[props.message.role]?.container]"
    :data-testid="'trace-message-' + props.message.role"
  >
    <div :class="['text-[10px] font-semibold uppercase tracking-[0.12em]', ROLE_STYLES[props.message.role]?.badge]">
      {{ props.message.role }}
    </div>
    <div class="mt-1.5 flex flex-col gap-2">
      <template v-for="(block, index) in props.message.content" :key="index">
        <!-- Text block -->
        <template v-if="block.type === 'text' && block.text">
          <!-- Short text: render markdown -->
          <MarkdownRenderer
            v-if="block.text.length < LONG_TEXT_CHARS"
            :content="block.text"
            variant="compact"
          />
          <!-- Long text: pre-wrapped with copy button -->
          <div v-else class="relative">
            <pre class="max-h-[400px] overflow-y-auto whitespace-pre-wrap break-words rounded-[var(--radius-sm)] bg-[var(--color-surface)]/60 px-2 py-1.5 font-mono text-[11px] leading-5 text-[var(--color-text-secondary)]">
{{ block.text }}
            </pre>
            <CopyButton
              :text="block.text!"
              :copied-label="t('common.copied')"
              class="absolute right-1.5 top-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)] px-1.5 py-0.5 text-[10px] text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text-primary)]"
            />
          </div>
        </template>

        <!-- Thinking block -->
        <ThinkingBlock v-else-if="block.type === 'thinking'" :thinking="block.thinking!" />

        <!-- Tool use block -->
        <div v-else-if="block.type === 'tool_use'" class="min-w-0">
          <div class="flex min-w-0 items-center gap-1.5 text-[11px] font-semibold text-[var(--color-text-secondary)]">
            <span class="material-symbols-outlined text-[13px] shrink-0 text-[var(--color-warning)]">build</span>
            <span class="truncate">{{ block.name }}</span>
            <span v-if="block.id" class="truncate font-mono text-[10px] font-normal text-[var(--color-text-tertiary)]">{{ block.id }}</span>
          </div>
          <div class="mt-1">
            <CodeViewer :code="safeJson(block.input)" language="json" :max-lines="24" show-line-numbers />
          </div>
        </div>

        <!-- Tool result block -->
        <div v-else-if="block.type === 'tool_result'" :class="block.isError ? 'min-w-0 rounded-[var(--radius-sm)] border border-[var(--color-error)]/40 p-1.5' : 'min-w-0'">
          <div class="flex min-w-0 items-center gap-1.5 text-[11px] font-semibold text-[var(--color-text-secondary)]">
            <span :class="block.isError ? 'text-[var(--color-error)]' : ''">
              {{ block.isError ? t('trace.toolError') : t('trace.toolResult') }}
            </span>
            <span v-if="block.toolUseId" class="truncate font-mono text-[10px] font-normal text-[var(--color-text-tertiary)]">{{ block.toolUseId }}</span>
          </div>
          <div class="mt-1">
            <ToolResultContent :content="block.content!" />
          </div>
        </div>

        <!-- Image chip -->
        <span v-else-if="block.type === 'image'" class="inline-flex w-fit items-center gap-1 rounded-[var(--radius-sm)] border border-[var(--color-border)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-text-tertiary)]">
          [image]
          <span v-if="block.mediaType">{{ block.mediaType }}</span>
        </span>
      </template>
    </div>
  </div>
</template>

<script lang="ts">
// ── Sub-components defined in non-setup script ───────────────────────
import type { Component } from 'vue'
import { ref } from 'vue'
import { useTranslation } from '../../../i18n'
import CodeViewer from '../../components/chat/CodeViewer.vue'

// ThinkingBlock — collapsible thinking content
export const ThinkingBlock: Component = {
  name: 'ThinkingBlock',
  props: {
    thinking: String,
  },
  setup() {
    const t = useTranslation()
    const open = ref(false)
    return { t, open }
  },
  template: `
    <div>
      <button
        type="button"
        @click="open = !open"
        :aria-expanded="open"
        class="inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text-primary)]"
      >
        {{ t('trace.detail.thinking') }} · {{ t('trace.detail.chars', { count: props.thinking.length }) }}
      </button>
      <pre v-if="open" class="mt-1.5 max-h-[300px] overflow-y-auto whitespace-pre-wrap break-words text-[11px] italic leading-5 text-[var(--color-text-tertiary)]">
{{ props.thinking }}
      </pre>
    </div>
  `,
}

// ToolResultContent — extracts plain text or renders JSON
export const ToolResultContent: Component = {
  name: 'ToolResultContent',
  props: {
    content: null as unknown as () => unknown,
  },
  setup(props) {
    const text = extractPlainText(props.content)
    return { text, safeJson }
  },
  methods: {},
  template: `
    <TextResult v-if="text !== null && text.trim()" :text="text" />
    <CodeViewer v-else :code="safeJson(props.content)" language="json" :max-lines="24" show-line-numbers />
  `,
}

// TextResult — plain text in a pre block
export const TextResult: Component = {
  name: 'TextResult',
  props: {
    text: String,
  },
  template: `
    <pre class="max-h-[400px] overflow-y-auto whitespace-pre-wrap break-words rounded-[var(--radius-sm)] bg-[var(--color-surface)]/60 px-2 py-1.5 font-mono text-[11px] leading-5 text-[var(--color-text-secondary)]">
{{ props.text }}
    </pre>
  `,
}

// ── Helpers (declared here, used by ToolResultContent) ───────────────
function extractPlainText(content: unknown): string | null {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    const parts: string[] = []
    for (const item of content) {
      if (typeof item === 'string') {
        parts.push(item)
        continue
      }
      if (item && typeof item === 'object' && typeof (item as { text?: unknown }).text === 'string') {
        parts.push((item as { text: string }).text)
        continue
      }
      return null
    }
    return parts.join('\n')
  }
  return null
}

function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2) ?? 'null'
  } catch {
    return String(value)
  }
}
</script>