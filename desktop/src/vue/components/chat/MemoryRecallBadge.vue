<script setup lang="ts">
import { useTranslation } from '../../i18n'
const t = useTranslation()
/** Sprint 2 — Memory Recall Badge.
 * Shown above assistant message when the model used memories from the
 * 5-layer retriever (Sprint 2). Click to expand and see which memories
 * were injected into the system prompt.
 */
import { ref } from 'vue'

const props = defineProps<{
  memories: Array<{ id: string; kind: string; title: string; preview: string; layer: string }>
}>()

const expanded = ref(false)
</script>

<template>
  <div class="mb-2 flex flex-col gap-1 text-xs">
    <button
      class="self-start flex items-center gap-1.5 rounded-full bg-[var(--color-secondary-container)] text-[var(--color-secondary)] px-3 py-1 hover:bg-[var(--color-secondary-container)]/80 transition-colors"
      @click="expanded = !expanded"
    >
      <span class="material-symbols-outlined text-[14px]">memory</span>
      <span class="font-medium">{{ t('chat.memoryAnswer', '基于 {count} 条记忆回答', { count: memories.length }) }}</span>
      <span class="material-symbols-outlined text-[14px]">
        {{ expanded ? 'expand_less' : 'expand_more' }}
      </span>
    </button>
    <div
      v-if="expanded"
      class="rounded-[var(--radius-md)] border border-[var(--color-border-separator)] bg-[var(--color-surface-container-lowest)] p-2 space-y-1"
    >
      <div
        v-for="m in memories"
        :key="m.id"
        class="flex items-start gap-2 text-xs"
      >
        <span
          class="inline-flex shrink-0 items-center rounded bg-[var(--color-surface-container)] px-1.5 py-0.5 text-[10px] font-mono text-[var(--color-text-tertiary)]"
        >{{ m.layer }}</span>
        <div class="flex-1 min-w-0">
          <div class="font-medium text-[var(--color-text-primary)] truncate">{{ m.title }}</div>
          <div class="text-[var(--color-text-tertiary)] truncate">{{ m.preview }}</div>
        </div>
      </div>
    </div>
  </div>
</template>
