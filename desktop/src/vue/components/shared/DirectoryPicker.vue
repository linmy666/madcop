<script setup lang="ts">
// v3.0 — DirectoryPicker (Vue 3, ref-tdz-fixed)
// CRITICAL: no variable named 'ref' — shadows Vue's import
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'

interface RecentProject {
  name: string
  path: string
}

const props = withDefaults(defineProps<{
  value?: string
  isGitProject?: boolean
}>(), {
  value: '',
  isGitProject: false,
})

const emit = defineEmits<{
  (e: 'update:value', v: string): void
  (e: 'change', v: string): void
}>()

const isOpen = ref(false)
const mode = ref<'recent' | 'browse'>('recent')
const projects = ref<RecentProject[]>([])
const browseEntries = ref<any[]>([])
const browsePath = ref('')
const browseParent = ref('')
const loading = ref(false)
const dropdownPos = ref<{ top: number; left: number; width: number; direction: 'up' | 'down' } | null>(null)
const dialogRef = ref<HTMLDivElement | null>(null)
const triggerRef = ref<HTMLButtonElement | null>(null)
const dropdownRef = ref<HTMLDivElement | null>(null)
const isMobileBrowser = ref(false)

function onDocClick(e: MouseEvent) {
  if (dialogRef.value?.contains(e.target as Node)) return
  if (triggerRef.value?.contains(e.target as Node)) return
  isOpen.value = false
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') isOpen.value = false
}

onMounted(() => {
  document.addEventListener('mousedown', onDocClick)
  document.addEventListener('keydown', onKey)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onDocClick)
  document.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div class="relative">
    <button
      ref="triggerRef"
      type="button"
      @click="isOpen = !isOpen"
      class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]"
    >
      <span class="material-symbols-outlined text-[14px]">folder</span>
      <span class="truncate max-w-[120px]">{{ value || '选择目录…' }}</span>
    </button>

    <Teleport to="body">
      <div
        v-if="isOpen"
        ref="dialogRef"
        class="fixed z-50 min-w-[280px] rounded-[12px] border border-[var(--color-border)] bg-[var(--color-surface)] py-1 shadow-[var(--shadow-dropdown)]"
        :style="{
          top: (triggerRef?.getBoundingClientRect().bottom ?? 0) + 6 + 'px',
          left: Math.max(8, Math.min(triggerRef?.getBoundingClientRect().left ?? 0, window.innerWidth - 280 - 8)) + 'px',
        }"
      >
        <div class="px-3 py-2 text-xs text-[var(--color-text-tertiary)] font-medium">
          选择目录
        </div>
        <div v-if="projects.length > 0" class="border-t border-[var(--color-border-separator)]">
          <button
            v-for="p in projects" :key="p.path"
            @click="emit('update:value', p.path)" 
            class="w-full flex items-center gap-3 px-3 py-2.5 text-left text-sm font-medium text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)]"
          >
            <span class="material-symbols-outlined text-[16px] text-[var(--color-text-secondary)]">folder</span>
            <span class="min-w-0 truncate">{{ p.name }}</span>
          </button>
        </div>
      </div>
    </Teleport>
  </div>
</template>