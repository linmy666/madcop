<script setup lang="ts">
import { computed } from 'vue'

/**
 * SessionTaskBar — Vue 3 port of components/chat/SessionTaskBar.tsx
 *
 * Shows CLI task progress bar with collapsible task list.
 * Prop-driven: parent passes tasks[] and expanded state.
 * No React store imports.
 */

export interface CLITask {
  id: number
  subject: string
  status: 'pending' | 'in_progress' | 'completed'
  activeForm?: string
  owner?: string
}

export interface SessionTaskBarProps {
  tasks: CLITask[]
  expanded?: boolean
  completedAndDismissed?: boolean
}

const props = withDefaults(defineProps<SessionTaskBarProps>(), {
  tasks: () => [] as CLITask[],
  expanded: false,
  completedAndDismissed: false,
})

const emit = defineEmits<{
  toggleExpanded: []
  resetCompletedTasks: []
}>()

const statusConfig = {
  pending: { icon: 'radio_button_unchecked', color: 'var(--color-text-tertiary)' },
  in_progress: { icon: 'pending', color: 'var(--color-warning)' },
  completed: { icon: 'check_circle', color: 'var(--color-success)' },
} as const

const allCompleted = computed(() => (props.tasks ?? []).every((tk) => tk.status === 'completed'))
const completedCount = computed(() => (props.tasks ?? []).filter((tk) => tk.status === 'completed').length)
const totalCount = computed(() => (props.tasks ?? []).length)
const progressPercent = computed(() => totalCount.value > 0 ? Math.round((completedCount.value / totalCount.value) * 100) : 0)
</script>

<template>
  <div v-if="(props.tasks ?? []).length > 0 && !(allCompleted && completedAndDismissed)" class="shrink-0 px-8">
    <div class="mx-auto max-w-[860px] rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)]/40 bg-[var(--color-surface-container-lowest)] overflow-hidden mb-2">
      <!-- Header -->
      <div class="flex items-center gap-2 bg-[var(--color-surface-container)] px-2 py-1.5">
        <button type="button" @click="emit('toggleExpanded')"
          class="flex min-w-0 flex-1 items-center gap-3 rounded-[var(--radius-md)] px-2 py-1 hover:bg-[var(--color-surface-container-low)] transition-colors">
          <div class="flex items-center justify-center w-6 h-6 rounded-[var(--radius-md)] bg-[var(--color-secondary)]/10">
            <span class="material-symbols-outlined text-[14px] text-[var(--color-secondary)]">checklist</span>
          </div>
          <span class="text-xs font-semibold text-[var(--color-text-primary)]">Task Progress</span>
          <div class="flex-1 h-1.5 rounded-full bg-[var(--color-border)] overflow-hidden max-w-[200px]">
            <div class="h-full rounded-full transition-all duration-300"
              :style="{ width: `${progressPercent}%`, backgroundColor: completedCount === totalCount ? 'var(--color-success)' : 'var(--color-brand)' }" />
          </div>
          <span class="text-[10px] text-[var(--color-text-tertiary)] tabular-nums">
            {{ completedCount }}/{{ totalCount }}
          </span>
          <span class="material-symbols-outlined text-[14px] text-[var(--color-text-tertiary)] transition-transform duration-200"
            :style="{ transform: props.expanded ? 'rotate(180deg)' : 'rotate(0deg)' }">expand_less</span>
        </button>
        <button v-if="allCompleted" type="button" @click="emit('resetCompletedTasks')" aria-label="Dismiss"
          class="flex shrink-0 items-center justify-center rounded-[var(--radius-md)] p-1.5 text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-container-low)] hover:text-[var(--color-text-primary)] transition-colors">
          <span class="material-symbols-outlined text-[16px]">close</span>
        </button>
      </div>

      <!-- Task list -->
      <div v-if="props.expanded" class="px-4 pb-2 pt-1 flex flex-col gap-0.5 max-h-[240px] overflow-y-auto border-t border-[var(--color-outline-variant)]/20">
        <div v-for="task in props.tasks" :key="task.id" class="flex items-start gap-2 py-1.5 px-1 rounded-md">
          <span class="material-symbols-outlined text-[16px] mt-px shrink-0"
            :style="{ color: statusConfig[task.status as keyof typeof statusConfig].color }">
            {{ statusConfig[task.status as keyof typeof statusConfig].icon }}
          </span>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-1.5">
              <span class="text-[10px] font-mono text-[var(--color-text-tertiary)]">#{{ task.id }}</span>
              <span :class="[
                'text-xs',
                task.status === 'completed' ? 'text-[var(--color-text-tertiary)] line-through' : 'text-[var(--color-text-primary)]'
              ]">{{ task.subject }}</span>
            </div>
            <div v-if="task.status === 'in_progress' && task.activeForm" class="flex items-center gap-1 mt-0.5">
              <span class="w-1.5 h-1.5 rounded-full bg-[var(--color-warning)] animate-pulse" />
              <span class="text-[10px] text-[var(--color-warning)]">{{ task.activeForm }}</span>
            </div>
            <span v-if="task.owner" class="text-[10px] text-[var(--color-text-tertiary)] mt-0.5 inline-flex items-center gap-0.5">
              <span class="material-symbols-outlined text-[10px]">person</span>{{ task.owner }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
