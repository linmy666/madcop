<script setup lang="ts">
import { ref } from 'vue'

/**
 * MessageBlocks — Vue 3 port of components/trace/detail/MessageBlocks.tsx
 * Renders normalized trace message blocks (text, thinking, tool_use, tool_result, image).
 * Prop-driven: parent passes a NormalizedMessage.
 */

const ROLE_STYLES: Record<string, { badge: string; container: string }> = {
  user: { badge: 'text-[var(--color-info)]', container: 'border-l-[var(--color-info)] bg-[var(--color-info)]/8' },
  assistant: { badge: 'text-[var(--color-brand)]', container: 'border-l-[var(--color-brand)] bg-[var(--color-brand)]/8' },
  system: { badge: 'text-[var(--color-warning)]', container: 'border-l-[var(--color-warning)] bg-[var(--color-warning)]/8' },
  tool: { badge: 'text-[var(--color-text-tertiary)]', container: 'border-l-[var(--color-outline)] bg-[var(--color-surface-container)]/60' },
}

export interface MessageBlock {
  type: string
  text?: string
  thinking?: string
  id?: string
  name?: string
  input?: unknown
  toolUseId?: string
  content?: unknown
  isError?: boolean
  mediaType?: string
}

export interface MessageProps {
  message: { role: string; content: MessageBlock[] }
}

const props = defineProps<MessageProps>()
const openThinking = ref(false)

function safeJson(value: unknown): string {
  try { return JSON.stringify(value, null, 2) || 'null' }
  catch { return String(value) }
}
</script>

<template>
  <div :class="['trace-message-cv rounded-[var(--radius-md)] border-l-2 px-3 py-2', ROLE_STYLES[props.message.role]?.container]">
    <div :class="['text-[10px] font-semibold uppercase tracking-[0.12em]', ROLE_STYLES[props.message.role]?.badge]">
      {{ props.message.role }}
    </div>
    <div class="mt-1.5 flex flex-col gap-2">
      <template v-for="(block, index) in props.message.content" :key="index">
        <!-- Text block -->
        <template v-if="block.type === 'text' && block.text">
          <MarkdownRenderer v-if="block.text.length < 2000" :content="block.text" variant="compact" />
          <div v-else class="relative">
            <pre class="max-h-[400px] overflow-y-auto whitespace-pre-wrap break-words rounded-[var(--radius-sm)] bg-[var(--color-surface)]/60 px-2 py-1.5 font-mono text-[11px] leading-5 text-[var(--color-text-secondary)]">{{ block.text }}</pre>
            <button class="absolute right-1.5 top-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)] px-1.5 py-0.5 text-[10px] text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text-primary)]">Copy</button>
          </div>
        </template>
        <!-- Thinking block -->
        <div v-else-if="block.type === 'thinking'">
          <button type="button" @click="openThinking = !openThinking"
            class="inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text-primary)]">
            Thinking · {{ block.thinking?.length || 0 }} chars
          </button>
          <pre v-if="openThinking" class="mt-1.5 max-h-[300px] overflow-y-auto whitespace-pre-wrap break-words text-[11px] italic leading-5 text-[var(--color-text-tertiary)]">{{ block.thinking }}</pre>
        </div>
        <!-- Tool use block -->
        <div v-else-if="block.type === 'tool_use'">
          <div class="flex min-w-0 items-center gap-1.5 text-[11px] font-semibold text-[var(--color-text-secondary)]">
            <span class="material-symbols-outlined text-[13px] shrink-0 text-[var(--color-warning)]">build</span>
            <span class="truncate">{{ block.name }}</span>
            <span v-if="block.id" class="truncate font-mono text-[10px] font-normal text-[var(--color-text-tertiary)]">{{ block.id }}</span>
          </div>
          <pre class="mt-1 max-h-60 overflow-y-auto rounded-[var(--radius-sm)] bg-[var(--color-surface)]/60 px-2 py-1.5 font-mono text-[11px] leading-5 text-[var(--color-text-secondary)]">{{ safeJson(block.input) }}</pre>
        </div>
        <!-- Tool result block -->
        <div v-else-if="block.type === 'tool_result'">
          <div class="flex min-w-0 items-center gap-1.5 text-[11px] font-semibold text-[var(--color-text-secondary)]">
            <span :class="block.isError ? 'text-[var(--color-error)]' : ''">
              {{ block.isError ? 'Error' : 'Result' }}
            </span>
            <span v-if="block.toolUseId" class="truncate font-mono text-[10px] font-normal text-[var(--color-text-tertiary)]">{{ block.toolUseId }}</span>
          </div>
          <pre class="mt-1 max-h-[400px] overflow-y-auto whitespace-pre-wrap break-words rounded-[var(--radius-sm)] bg-[var(--color-surface)]/60 px-2 py-1.5 font-mono text-[11px] leading-5 text-[var(--color-text-secondary)]">{{ safeJson(block.content) }}</pre>
        </div>
        <!-- Image chip -->
        <span v-else-if="block.type === 'image'" class="inline-flex w-fit items-center gap-1 rounded-[var(--radius-sm)] border border-[var(--color-border)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-text-tertiary)]">[image] {{ block.mediaType }}</span>
      </template>
    </div>
  </div>
</template>
