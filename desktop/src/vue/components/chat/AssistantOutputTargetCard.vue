<script setup lang="ts">
// v3.0 — AssistantOutputTargetCard (Vue 3)
// Simplified translation — same Tailwind classes, same card layout.
import { ref, computed } from 'vue'

interface OutputTarget {
  id: string
  kind: string  // 'localhost-url' | 'local-html' | 'markdown' | 'image'
  title: string
  subtitle?: string
  href: string
  normalizedPath?: string
}

const props = defineProps<{
  target: OutputTarget
  sessionId?: string
  workDir?: string
}>()

const emit = defineEmits<{ (e: 'open', href: string): void }>()

const badge = computed(() => {
  switch (props.target.kind) {
    case 'localhost-url': return 'Localhost'
    case 'local-html': return 'HTML'
    case 'markdown': return 'Markdown'
    case 'image': return 'Image'
    default: return '文件'
  }
})

const showSubtitle = computed(() => (props.target.subtitle ?? props.target.normalizedPath ?? props.target.href) !== props.target.title)

const iconMap: Record<string, string> = {
  'localhost-url': 'public',
  'local-html': 'code',
  'markdown': 'description',
  'image': 'image',
  'default': 'draft',
}
const icon = computed(() => iconMap[props.target.kind] || iconMap.default)

function handleOpen() {
  emit('open', props.target.href)
}
</script>

<template>
  <button
    type="button"
    @click="handleOpen"
    class="group flex w-full items-center gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2.5 text-left transition-colors hover:bg-[var(--color-surface-hover)]"
  >
    <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-surface-container-high)] text-[var(--color-text-secondary)]">
      <span class="material-symbols-outlined text-[18px]">{{ icon }}</span>
    </span>
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <span class="min-w-0 truncate text-sm font-medium text-[var(--color-text-primary)]">{{ target.title }}</span>
        <span class="shrink-0 rounded-full bg-[var(--color-surface-container-high)] px-2 py-0.5 text-[9px] font-medium uppercase text-[var(--color-text-tertiary)]">{{ badge }}</span>
      </div>
      <div v-if="showSubtitle" class="mt-0.5 min-w-0 truncate text-xs text-[var(--color-text-tertiary)] font-[var(--font-mono)]">
        {{ target.subtitle ?? target.normalizedPath ?? target.href }}
      </div>
    </div>
    <span class="material-symbols-outlined text-[16px] text-[var(--color-text-tertiary)] opacity-0 transition-opacity group-hover:opacity-100">open_in_new</span>
  </button>
</template>
