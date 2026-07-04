<script setup lang="ts">
// v3.0 — ToolResultBlock (Vue 3)
// Direct translation — same Tailwind classes, same expand/collapse logic.
import { ref, computed } from 'vue'

const props = withDefaults(defineProps<{
  content: unknown
  isError: boolean
  toolName?: string
  standalone?: boolean
}>(), {
  standalone: true,
})

const expanded = ref(false)

function extractText(content: unknown): string {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    return content.map((c: any) => (typeof c === 'string' ? c : c?.text || '')).filter(Boolean).join('\n')
  }
  if (content && typeof content === 'object') return JSON.stringify(content, null, 2)
  return String(content ?? '')
}

const text = computed(() => extractText(props.content))
const preview = computed(() => text.value.slice(0, 200))
const hasMore = computed(() => text.value.length > 200)
</script>

<template>
  <div v-if="standalone" :class="['mb-2 overflow-hidden rounded-xl border', isError ? 'border-[var(--color-error)]/20' : 'border-[var(--color-outline-variant)]/20']">
    <button
      type="button"
      @click="expanded = !expanded"
      :class="[
        'flex w-full items-center justify-between px-3 py-2 text-left text-[10px] font-bold uppercase tracking-wider',
        isError
          ? 'bg-[var(--color-error-container)] text-[var(--color-error)]'
          : 'bg-[var(--color-surface-container-high)] text-[var(--color-outline)]',
      ]"
    >
      <span class="flex items-center gap-1.5">
        <span class="material-symbols-outlined text-[12px]">{{ isError ? 'error' : 'check_circle' }}</span>
        {{ toolName ? `结果: ${toolName}` : '工具结果' }}
      </span>
      <span :class="['px-2 py-0.5 rounded-full text-[9px]', isError ? 'bg-[var(--color-error)]/10' : 'bg-[var(--color-diff-added-bg)] text-[var(--color-diff-added-text)]']">
        {{ isError ? '错误' : '成功' }}
      </span>
    </button>

    <div v-if="expanded" :class="isError ? 'bg-[var(--color-error-container)]/50 px-3 py-2.5 font-[var(--font-mono)] text-[11px] leading-[1.5] whitespace-pre-wrap break-words text-[var(--color-error)]' : 'bg-[var(--color-surface-container-lowest)] px-3 py-2.5 font-[var(--font-mono)] text-[11px] leading-[1.5] whitespace-pre-wrap break-words text-[var(--color-text-secondary)]'">
      {{ text }}
    </div>
    <div v-else class="bg-[var(--color-surface-container-lowest)] px-3 py-2 font-[var(--font-mono)] text-[10px] leading-[1.35] text-[var(--color-text-tertiary)]">
      {{ preview }}{{ hasMore ? '…' : '' }}
    </div>

    <button
      v-if="hasMore"
      @click="expanded = !expanded"
      class="w-full py-1 text-[10px] font-medium text-[var(--color-text-accent)] hover:underline bg-[var(--color-surface-container-low)] border-t border-[var(--color-outline-variant)]/10"
    >
      {{ expanded ? '收起' : `展开全部 (${text.length - 200} 字)` }}
    </button>
  </div>
</template>
