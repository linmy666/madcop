<script setup lang="ts">
import { ref, watch } from 'vue'

/**
 * TaskRunsPanel — Vue 3 port of components/tasks/TaskRunsPanel.tsx
 * Shows task run logs with expandable output.
 * Prop-driven: parent passes runs[], loading state, and callbacks.
 * No React store imports.
 */

export interface TaskRun {
  id: string
  status: string
  startedAt: number | string
  durationMs?: number | null
  sessionId?: string
  taskName?: string
  output?: string
  error?: string
}

export interface TaskRunsPanelProps {
  runs: TaskRun[]
  loading: boolean
  refreshKey?: number
}

const props = withDefaults(defineProps<TaskRunsPanelProps>(), {
  refreshKey: 0,
})

const emit = defineEmits<{ close: []; run: [] }>()

const expandedId = ref<string | null>(null)
const STATUS_CONFIG: Record<string, { icon: string; color: string }> = {
  running: { icon: 'sync', color: 'var(--color-warning)' },
  completed: { icon: 'check_circle', color: 'var(--color-success)' },
  failed: { icon: 'error', color: 'var(--color-error)' },
  timeout: { icon: 'timer_off', color: 'var(--color-error)' },
}

function formatStatusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1)
}
</script>

<template>
  <div class="mt-2 mb-1 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
    <div class="flex items-center justify-between px-4 py-2.5 bg-[var(--color-surface-container)]">
      <span class="text-xs font-medium text-[var(--color-text-primary)]">Logs</span>
      <button @click="emit('close')"
        class="p-0.5 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] transition-colors">
        <span class="material-symbols-outlined text-[16px]">close</span>
      </button>
    </div>
    <div class="max-h-64 overflow-y-auto">
      <div v-if="loading" class="flex items-center justify-center py-6">
        <div class="animate-spin w-4 h-4 border-2 border-[var(--color-brand)] border-t-transparent rounded-full" />
      </div>
      <div v-else-if="props.runs.length === 0" class="px-4 py-6 text-center text-xs text-[var(--color-text-tertiary)]">
        No logs yet
      </div>
      <div v-else class="divide-y divide-[var(--color-border-separator)]">
        <div v-for="run in props.runs" :key="run.id" class="px-4 py-2.5">
          <div class="flex items-center gap-3">
            <span :class="['material-symbols-outlined text-[16px]', run.status === 'running' ? 'animate-spin' : '']"
              :style="{ color: STATUS_CONFIG[run.status]?.color || 'var(--color-text-tertiary)', fontVariationSettings: "'FILL' 1" }">
              {{ STATUS_CONFIG[run.status]?.icon || 'error' }}
            </span>
            <span class="text-xs font-medium" :style="{ color: STATUS_CONFIG[run.status]?.color }">
              {{ formatStatusLabel(run.status) }}
            </span>
            <span class="text-xs text-[var(--color-text-tertiary)]">
              {{ new Date(run.startedAt).toLocaleString() }}
            </span>
            <div class="ml-auto flex items-center gap-2">
              <button v-if="run.sessionId && run.status !== 'running'" @click="emit('run')"
                class="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-[var(--color-brand)] bg-[var(--color-brand)]/8 hover:bg-[var(--color-brand)]/15 rounded-[var(--radius-sm)] transition-colors">
                <span class="material-symbols-outlined text-[14px]">open_in_new</span>Open Session
              </button>
              <button v-if="run.output || run.error" @click="expandedId = expandedId === run.id ? null : run.id"
                class="text-xs text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] transition-colors">
                {{ expandedId === run.id ? 'Hide' : 'View' }}
              </button>
            </div>
          </div>
          <div v-if="expandedId === run.id">
            <div v-if="run.error" class="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap break-words rounded-[var(--radius-sm)] border border-[var(--color-error)]/20 bg-[var(--color-error-container)]/28 p-2.5 text-xs text-[var(--color-error)]">{{ run.error }}</div>
            <div v-else-if="run.output" class="mt-2 max-h-48 overflow-y-auto rounded-[var(--radius-sm)] bg-[var(--color-surface-container)] p-2.5">
              <pre class="m-0 whitespace-pre-wrap break-words text-xs text-[var(--color-text-secondary)]">{{ run.output }}</pre>
            </div>
            <div v-else class="mt-2 p-2.5 rounded-[var(--radius-sm)] bg-[var(--color-surface-container)] text-xs text-[var(--color-text-tertiary)] italic">
              {{ run.sessionId ? 'See session for details' : 'No output' }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
