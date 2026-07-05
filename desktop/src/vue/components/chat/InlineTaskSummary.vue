<script setup lang="ts">
// v3.0 — InlineTaskSummary (Vue 3)
// Full translation of InlineTaskSummary.tsx — same Tailwind classes.
import { computed } from 'vue'
import { useTranslation } from '../../i18n'

const props = defineProps<{
  tasks: Array<{ id: string; subject: string; status: 'pending' | 'in_progress' | 'completed' }>
}>()

const t = useTranslation()

const completedCount = computed(() =>
  props.tasks.filter((tk) => tk.status === 'completed').length,
)
const totalCount = computed(() => props.tasks.length)

const statusIcon: Record<string, string> = {
  pending: 'radio_button_unchecked',
  in_progress: 'pending',
  completed: 'check_circle',
}

const FILL_FONT_VAR = "'FILL' 1"

const statusColor: Record<string, string> = {
  pending: 'var(--color-text-tertiary)',
  in_progress: 'var(--color-warning)',
  completed: 'var(--color-success)',
}
</script>

<template>
  <div class="mb-3 rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)]/40 bg-[var(--color-surface-container-lowest)] overflow-hidden">
    <div class="flex items-center gap-3 px-4 py-2 bg-[var(--color-surface-container)]">
      <div class="flex items-center justify-center w-5 h-5 rounded-[var(--radius-md)] bg-[var(--color-success)]/10">
        <span
          class="material-symbols-outlined text-[13px] text-[var(--color-success)]"
          :style="{ 'font-variation-settings': FILL_FONT_VAR }"
        >
          task_alt
        </span>
      </div>
      <span class="text-xs font-semibold text-[var(--color-text-primary)]">
        {{ t('tasks.completed') }}
      </span>
      <span class="text-[10px] text-[var(--color-text-tertiary)] tabular-nums">
        {{ completedCount }}/{{ totalCount }}
      </span>
    </div>
    <div class="px-4 py-2 flex flex-col gap-0.5">
      <div v-for="task in tasks" :key="task.id" class="flex items-center gap-2 py-1 px-1">
        <span
          class="material-symbols-outlined text-[14px] shrink-0"
          :style="{ color: statusColor[task.status], 'font-variation-settings': FILL_FONT_VAR }"
        >
          {{ statusIcon[task.status] }}
        </span>
        <span class="text-[10px] font-mono text-[var(--color-text-tertiary)]">
          #{{ task.id }}
        </span>
        <span
          :class="[
            'text-xs',
            task.status === 'completed'
              ? 'text-[var(--color-text-tertiary)] line-through'
              : 'text-[var(--color-text-primary)]',
          ]"
        >
          {{ task.subject }}
        </span>
      </div>
    </div>
  </div>
</template>
