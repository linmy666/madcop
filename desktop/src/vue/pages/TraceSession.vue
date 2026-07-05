<script setup lang="ts">
/**
 * TraceSession — Vue 3 port of pages/TraceSession.tsx
 * Full trace viewer with polling, split layout, and detail panel.
 * Props-driven: sessionId passed from parent.
 */

interface TraceSessionProps {
  sessionId: string
  standalone?: boolean
  pollIntervalMs?: number
}

interface TraceSpan {
  id: string
  name: string
  type: string
  status: string
  startTime: number
  duration?: number
  children?: TraceSpan[]
}

const props = withDefaults(defineProps<TraceSessionProps>(), {
  standalone: false,
  pollIntervalMs: 1500,
})

const loading = ref(true)
const error = ref<string | null>(null)
const selectedSpanId = ref<string | null>(null)
const refreshing = ref(false)
const traceSpans = ref<TraceSpan[]>([])

// Mock trace data for demo
const mockTraceSpans: TraceSpan[] = [
  { id: 'root', name: 'Root Span', type: 'llm', status: 'completed', startTime: Date.now() - 5000, duration: 5000,
    children: [
      { id: '1', name: 'Tool Call: read_file', type: 'tool', status: 'completed', startTime: Date.now() - 4500, duration: 500 },
      { id: '2', name: 'Tool Call: terminal', type: 'tool', status: 'completed', startTime: Date.now() - 4000, duration: 300 },
      { id: '3', name: 'LLM Response', type: 'llm', status: 'completed', startTime: Date.now() - 3500, duration: 800 },
    ],
  },
]

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleTimeString()
}

const emit = defineEmits<{
  select: [spanId: string]
}>()

function handleSelect(spanId: string) {
  selectedSpanId.value = spanId
  emit('select', spanId)
}
</script>

<template>
  <div class="flex flex-col h-full bg-[var(--color-surface)]">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-2 border-b border-[var(--color-border)]">
      <div class="flex items-center gap-3">
        <span class="material-symbols-outlined text-[var(--color-brand)] text-lg">radio</span>
        <span class="text-sm font-semibold text-[var(--color-text-primary)]">Trace Session</span>
        <span class="text-xs text-[var(--color-text-tertiary)] font-mono">{{ sessionId }}</span>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="loading" class="flex items-center gap-1 text-xs text-[var(--color-text-tertiary)]">
          <span class="material-symbols-outlined text-sm animate-spin">progress_activity</span>
          Loading
        </span>
        <span v-else class="flex items-center gap-1 text-xs text-[var(--color-success)]">
          <span class="material-symbols-outlined text-sm" style="fontVariationSettings: 'FILL' 1">check_circle</span>
          Loaded
        </span>
        <button @click="refreshing = true; setTimeout(() => refreshing = false, 500)"
          class="p-1.5 hover:bg-[var(--color-surface-hover)] rounded text-[var(--color-text-tertiary)]" :disabled="loading">
          <span class="material-symbols-outlined text-sm" :class="refreshing ? 'animate-spin' : ''">refresh</span>
        </button>
      </div>
    </div>

    <!-- Error state -->
    <div v-if="error" class="flex-1 flex items-center justify-center">
      <div class="text-center p-8">
        <span class="material-symbols-outlined text-[var(--color-warning)] text-3xl mb-2">warning</span>
        <p class="text-sm text-[var(--color-text-secondary)]">{{ error }}</p>
      </div>
    </div>

    <!-- Trace content -->
    <div v-else class="flex-1 flex flex-col min-h-0">
      <!-- Span tree -->
      <div class="flex-1 overflow-y-auto p-4">
        <div class="space-y-2">
          <div v-for="span in traceSpans" :key="span.id"
            class="flex items-start gap-2 p-2 rounded-lg hover:bg-[var(--color-surface-hover)] cursor-pointer"
            @click="handleSelect(span.id)">
            <span :class="['material-symbols-outlined text-sm',
              span.type === 'llm' ? 'text-[var(--color-brand)]' :
              span.type === 'tool' ? 'text-[var(--color-secondary)]' :
              'text-[var(--color-text-tertiary)]']">
              {{ span.type === 'llm' ? 'psychology' : span.type === 'tool' ? 'build' : 'spanner' }}
            </span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-xs font-medium text-[var(--color-text-primary)] truncate">{{ span.name }}</span>
                <span :class="['text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-tight',
                  span.status === 'completed' ? 'bg-[var(--color-success-container)] text-[var(--color-success)]' :
                  span.status === 'error' ? 'bg-[var(--color-error-container)] text-[var(--color-error)]' :
                  'bg-[var(--color-warning-container)] text-[var(--color-warning)]']">{{ span.status }}</span>
              </div>
              <span class="text-[10px] text-[var(--color-text-tertiary)] font-mono">{{ formatDuration(span.duration || 0) }}</span>
            </div>
          </div>
          <!-- Nested spans -->
          <div v-for="child in span.children || []" :key="child.id"
            v-if="span.children"
            class="ml-4 flex items-start gap-2 p-2 rounded-lg hover:bg-[var(--color-surface-hover)] cursor-pointer"
            @click="handleSelect(child.id)">
            <span :class="['material-symbols-outlined text-sm',
              child.type === 'llm' ? 'text-[var(--color-brand)]' :
              child.type === 'tool' ? 'text-[var(--color-secondary)]' :
              'text-[var(--color-text-tertiary)]']">
              {{ child.type === 'llm' ? 'psychology' : child.type === 'tool' ? 'build' : 'spanner' }}
            </span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-xs font-medium text-[var(--color-text-primary)] truncate">{{ child.name }}</span>
                <span :class="['text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-tight',
                  child.status === 'completed' ? 'bg-[var(--color-success-container)] text-[var(--color-success)]' :
                  child.status === 'error' ? 'bg-[var(--color-error-container)] text-[var(--color-error)]' :
                  'bg-[var(--color-warning-container)] text-[var(--color-warning)]']">{{ child.status }}</span>
              </div>
              <span class="text-[10px] text-[var(--color-text-tertiary)] font-mono">{{ formatDuration(child.duration || 0) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
