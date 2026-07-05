<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

/**
 * FileSearchMenu — Vue 3 port of components/chat/FileSearchMenu.tsx
 * Dropdown file search menu. Prop-driven.
 */

export interface FileEntry { name: string; path: string; isDirectory: boolean }

export interface FileSearchMenuProps {
  files: FileEntry[]
  placeholder?: string
}

const props = withDefaults(defineProps<FileSearchMenuProps>(), { placeholder: 'Search files...' })
const emit = defineEmits<{ select: [path: string] }>()

const open = ref(false)
const query = ref('')
const rootRef = ref<HTMLDivElement | null>(null)

const filteredFiles = computed(() => {
  if (!query.value) return props.files
  const q = query.value.toLowerCase()
  return props.files.filter((f) => f.name.toLowerCase().includes(q) || f.path.toLowerCase().includes(q))
})

onMounted(() => {
  const handler = (e: MouseEvent) => {
    if (rootRef.value && !rootRef.value.contains(e.target as Node)) open.value = false
  }
  document.addEventListener('mousedown', handler)
})

onUnmounted(() => { document.removeEventListener('mousedown', () => {}) })

function onSelect(file: FileEntry) { emit('select', file.path); open.value = false; query.value = '' }
</script>

<template>
  <div ref="rootRef" class="relative">
    <input :value="query" @input="query = ($event.target as HTMLInputElement).value" @focus="open = true"
      :placeholder="placeholder" class="w-full min-w-0 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1.5 text-xs text-[var(--color-text-primary)] outline-none transition-colors placeholder:text-[var(--color-text-tertiary)] focus:border-[var(--color-brand)]/60" />
    <div v-if="open && filteredFiles.length > 0" class="absolute z-50 mt-1 max-h-60 w-full overflow-y-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] shadow-[var(--shadow-dropdown)]">
      <button v-for="file in filteredFiles" :key="file.path" @click="onSelect(file)"
        class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors hover:bg-[var(--color-surface-container)]">
        <span class="material-symbols-outlined text-[13px] text-[var(--color-text-tertiary)]">{{ file.isDirectory ? 'folder' : 'description' }}</span>
        <span class="min-w-0 flex-1 truncate">{{ file.name }}</span>
      </button>
    </div>
    <div v-if="open && query && filteredFiles.length === 0" class="absolute z-50 mt-1 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] px-3 py-2 text-xs text-[var(--color-text-tertiary)] shadow-[var(--shadow-dropdown)]">
      No files found for "{{ query }}"
    </div>
  </div>
</template>
