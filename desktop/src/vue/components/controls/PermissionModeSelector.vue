<script setup lang="ts">
// v3.1 — PermissionModeSelector — click-outside to close dropdown
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  value?: string
  compact?: boolean
}>()

const emit = defineEmits<{ (e: 'update:value', v: string): void }>()

const modes = [
  { id: 'ask', label: '询问', desc: '每次操作前确认' },
  { id: 'acceptEdits', label: '自动编辑', desc: '文件编辑无需确认' },
  { id: 'plan', label: '计划', desc: '只读分析模式' },
  { id: 'bypass', label: '跳过', desc: '完全自主执行' },
]

const current = computed(() => modes.find(m => m.id === props.value) ?? modes[0])
const open = ref(false)

const rootRef = ref<HTMLElement | null>(null)

function onClickOutside(e: MouseEvent) {
  if (open.value && rootRef.value && !rootRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('mousedown', onClickOutside))
onUnmounted(() => document.removeEventListener('mousedown', onClickOutside))
</script>

<template>
  <div ref="rootRef" class="relative">
    <div
      class="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)] cursor-pointer transition-colors"
      :class="current.id === 'bypass' 
        ? 'bg-[var(--color-error)]/10 text-[var(--color-error)] border border-[var(--color-error)]/30'
        : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]'"
      @click.stop="open = !open"
    >
      <!-- Custom shield icon -->
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" class="flex-shrink-0">
        <path d="M8 1.5L2.5 3.5V7.5C2.5 10.8 4.8 13.5 8 14.5C11.2 13.5 13.5 10.8 13.5 7.5V3.5L8 1.5Z" 
          :fill="current.id === 'bypass' ? 'currentColor' : 'none'"
          stroke="currentColor" stroke-width="1.2" opacity="0.7"/>
        <path v-if="current.id !== 'bypass'" d="M5.5 8L7 9.5L10.5 6" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      {{ current.label }}
      <svg width="10" height="10" viewBox="0 0 12 12" fill="none" class="opacity-50">
        <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </div>

    <!-- Dropdown -->
    <Transition name="perm-drop">
      <div v-if="open" class="absolute bottom-full left-0 mb-2 z-50 min-w-[200px] rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] shadow-[var(--shadow-dropdown)] py-1">
        <button
          v-for="mode in modes" :key="mode.id"
          @click.stop="emit('update:value', mode.id); open = false"
          :class="[
            'w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-[var(--color-surface-hover)]',
            mode.id === current.id ? 'bg-[var(--color-surface-hover)]' : '',
          ]"
        >
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" class="flex-shrink-0 opacity-70">
            <path d="M8 1.5L2.5 3.5V7.5C2.5 10.8 4.8 13.5 8 14.5C11.2 13.5 13.5 10.8 13.5 7.5V3.5L8 1.5Z" stroke="currentColor" stroke-width="1.2"/>
          </svg>
          <div class="min-w-0">
            <div class="text-xs font-medium text-[var(--color-text-primary)]">{{ mode.label }}</div>
            <div class="text-[10px] text-[var(--color-text-tertiary)]">{{ mode.desc }}</div>
          </div>
          <span v-if="mode.id === current.id" class="ml-auto material-symbols-outlined text-[14px] text-[var(--color-primary)]">check</span>
        </button>
      </div>
    </Transition>
  </div>
</template>

<style>
.perm-drop-enter-active, .perm-drop-leave-active { transition: all 120ms; }
.perm-drop-enter-from, .perm-drop-leave-to { opacity: 0; transform: translateY(4px); }
</style>