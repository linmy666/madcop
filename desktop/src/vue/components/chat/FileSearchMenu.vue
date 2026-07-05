<script setup lang="ts">
// v3.0 — FileSearchMenu (Vue 3 SFC)
// Full translation of src/components/chat/FileSearchMenu.tsx (330 lines).
// Dropdown file search menu with keyboard navigation, directory browsing,
// and search mode. Exposes handleKeyDown via defineExpose (mirrors forwardRef + useImperativeHandle).
import {
  ref,
  computed,
  onMounted,
  onBeforeUnmount,
  watch,
  nextTick,
  type Ref,
} from 'vue'
import { ApiError } from '../../../api/client'
import { filesystemApi } from '../../../api/filesystem'
import { useTranslation, type TranslationKey } from '../../../i18n'

// ── Types ─────────────────────────────────────────────────────────────
export type DirEntry = {
  name: string
  path: string
  isDirectory: boolean
  relativePath?: string
}

export type FileSearchMenuHandle = {
  handleKeyDown: (e: KeyboardEvent) => void
}

export interface FileSearchMenuProps {
  cwd: string
  filter?: string
  compact?: boolean
  onSelect: (path: string, relativePath: string, isDirectory: boolean) => void
  onNavigate?: (relativePath: string) => void
}

const props = withDefaults(defineProps<FileSearchMenuProps>(), {
  filter: '',
  compact: false,
})
const emit = defineEmits<{
  select: [path: string, relativePath: string, isDirectory: boolean]
}>()

const t = useTranslation()

// ── Reactive state ────────────────────────────────────────────────────
const entries = ref<DirEntry[]>([])
const errorMessage = ref<string | null>(null)
const errorKey = ref<TranslationKey | null>(null)
const currentPath = ref(props.cwd)
const isSearchMode = ref(false)
const loading = ref(false)
const selectedIndex = ref(0)
const rootPath = ref(props.cwd)

const listRef = ref<HTMLDivElement | null>(null)
const currentPathRef = ref(props.cwd)
const rootPathRef = ref(props.cwd)

// ── Helpers ───────────────────────────────────────────────────────────
function getErrorState(error: unknown): { errorKey: TranslationKey | null; errorMessage: string | null } {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return { errorKey: 'fileSearch.accessDenied', errorMessage: null }
    }
    const apiMessage =
      typeof error.body === 'string'
        ? error.body
        : typeof error.body === 'object' &&
            error.body !== null &&
            'error' in error.body &&
            typeof error.body.error === 'string'
          ? error.body.error
          : null
    if (apiMessage) {
      return { errorKey: null, errorMessage: apiMessage }
    }
  }
  return { errorKey: 'fileSearch.loadFailed', errorMessage: null }
}

function getRelativePath(entry: DirEntry): string {
  const basePath = (props.cwd || rootPath.value).replace(/\/+$/, '')
  if (entry.path.startsWith(`${basePath}/`)) return entry.path.slice(basePath.length + 1)
  if (entry.relativePath) return entry.relativePath
  return entry.name
}

function getDisplayPath(entry: DirEntry): string {
  const relativePath = getRelativePath(entry).replace(/\\/g, '/')
  if (!entry.isDirectory) return relativePath
  return `${relativePath.replace(/\/+$/, '')}/`
}

function parseFilter(rawFilter: string): { navigateTo: string; searchQuery: string } {
  const trimmed = rawFilter.trim()
  const basePath = (props.cwd || rootPathRef.value).replace(/\/+$/, '')
  if (!trimmed) return { navigateTo: basePath, searchQuery: '' }
  if (trimmed.endsWith('/')) {
    if (!basePath) return { navigateTo: '', searchQuery: trimmed.replace(/\/+$/, '') }
    return { navigateTo: `${basePath}/${trimmed.replace(/\/+$/, '')}`, searchQuery: '' }
  }
  return { navigateTo: basePath, searchQuery: trimmed }
}

// ── Actions ───────────────────────────────────────────────────────────
async function loadDir(dirPath: string, searchQuery: string) {
  loading.value = true
  errorMessage.value = null
  errorKey.value = null
  if (dirPath !== currentPathRef.value) {
    currentPath.value = dirPath
    currentPathRef.value = dirPath
  }
  try {
    if (searchQuery) {
      isSearchMode.value = true
      const result = await filesystemApi.search(searchQuery, dirPath)
      currentPath.value = result.currentPath
      currentPathRef.value = result.currentPath
      if (!props.cwd) {
        rootPath.value = result.currentPath
        rootPathRef.value = result.currentPath
      }
      entries.value = result.entries
    } else {
      isSearchMode.value = false
      const result = await filesystemApi.browse(dirPath, { includeFiles: true })
      currentPath.value = result.currentPath
      currentPathRef.value = result.currentPath
      if (!props.cwd) {
        rootPath.value = result.currentPath
        rootPathRef.value = result.currentPath
      }
      entries.value = result.entries
    }
    selectedIndex.value = 0
  } catch (error) {
    entries.value = []
    const nextError = getErrorState(error)
    errorKey.value = nextError.errorKey
    errorMessage.value = nextError.errorMessage
  }
  loading.value = false
}

function selectEntry(entry: DirEntry) {
  props.onSelect(entry.path, getRelativePath(entry), entry.isDirectory)
}

function navigateEntry(entry: DirEntry) {
  if (!entry.isDirectory) return
  const relativePath = `${getRelativePath(entry).replace(/\/+$/, '')}/`
  void loadDir(entry.path, '')
  props.onNavigate?.(relativePath)
}

// ── Keyboard handler (exposed via defineExpose) ───────────────────────
const handleKeyDown = (e: KeyboardEvent) => {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    selectedIndex.value = Math.min(selectedIndex.value + 1, entries.value.length - 1)
    return
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    selectedIndex.value = Math.max(selectedIndex.value - 1, 0)
    return
  }
  if (e.key === 'Enter' || e.key === 'Tab') {
    e.preventDefault()
    const selected = entries.value[selectedIndex.value]
    if (selected) selectEntry(selected)
    return
  }
  if (e.key === 'ArrowRight') {
    const selected = entries.value[selectedIndex.value]
    if (selected?.isDirectory) {
      e.preventDefault()
      navigateEntry(selected)
    }
    return
  }
}

// Expose to parent (mirrors React's useImperativeHandle + forwardRef)
defineExpose<FileSearchMenuHandle>({ handleKeyDown })

// ── Lifecycle ─────────────────────────────────────────────────────────
// Keep workspace root stable when host session changes
watch(
  () => props.cwd,
  (newCwd) => {
    currentPathRef.value = newCwd
    rootPathRef.value = newCwd
    rootPath.value = newCwd
    currentPath.value = newCwd
  },
)

// Initial load: parse filter path and navigate accordingly
watch(
  () => [props.cwd, props.filter] as const,
  () => {
    const { navigateTo, searchQuery } = parseFilter(props.filter)
    void loadDir(navigateTo, searchQuery)
  },
  { immediate: true },
)

// Scroll selected into view
watch(selectedIndex, () => {
  void nextTick(() => {
    const el = listRef.value?.querySelector(`[data-index="${selectedIndex.value}"]`) as HTMLButtonElement | null
    el?.scrollIntoView({ block: 'nearest' })
  })
})

// ── Computed ──────────────────────────────────────────────────────────
const breadcrumbs = computed((): string[] => {
  const result: string[] = []
  if (currentPath.value !== props.cwd && currentPath.value.startsWith(props.cwd)) {
    const rel = currentPath.value.slice(props.cwd.length).replace(/^\/hmm/, '')
    if (rel) result.push(...rel.split('/'))
  }
  return result
})
</script>

<template>
  <div
    id="file-search-menu"
    :class="[
      'absolute bottom-full mb-2 z-50 w-full overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] shadow-[var(--shadow-dropdown)]',
      props.compact ? 'left-0 right-0 min-w-0 max-w-[calc(100vw-32px)]' : 'left-0 min-w-[480px]',
    ]"
    @mousedown.stop
  >
    <!-- Header with path -->
    <div class="flex items-center gap-1.5 border-b border-[var(--color-border)] px-3 py-2 text-[11px]">
      <span class="material-symbols-outlined text-[14px] text-[var(--color-text-tertiary)]">folder_open</span>
      <span class="text-[var(--color-text-tertiary)] font-mono">{{ props.cwd.split('/').pop() || props.cwd }}</span>
      <span v-for="(seg, i) in breadcrumbs" :key="i" class="flex items-center gap-1">
        <span class="text-[var(--color-text-tertiary)]">/</span>
        <span class="text-[var(--color-text-primary)] font-mono">{{ seg }}</span>
      </span>
      <span
        v-if="isSearchMode && props.filter"
        class="ml-auto truncate font-mono text-[11px] text-[var(--color-text-tertiary)]"
      >
        @{{ props.filter }}
      </span>
      <span
        v-if="loading"
        class="material-symbols-outlined text-[12px] text-[var(--color-text-tertiary)] animate-spin ml-1"
      >
        progress_activity
      </span>
    </div>

    <!-- File list -->
    <div ref="listRef" class="max-h-[300px] overflow-y-auto py-1">
      <div v-if="loading && entries.length === 0" class="px-4 py-6 text-center text-xs text-[var(--color-text-tertiary)]">
        {{ t('fileSearch.searching') }}
      </div>
      <div v-else-if="errorKey || errorMessage" class="px-4 py-6 text-center text-xs text-[var(--color-error)]">
        {{ errorKey ? t(errorKey) : errorMessage }}
      </div>
      <div v-else-if="entries.length === 0" class="px-4 py-6 text-center text-xs text-[var(--color-text-tertiary)]">
        {{ props.filter ? t('fileSearch.noMatch') : t('fileSearch.noFiles') }}
      </div>
      <template v-else>
        <div
          v-for="(entry, index) in entries"
          :key="entry.path"
          :data-index="index"
          :class="['group flex items-stretch px-1.5 py-0.5', selectedIndex === index ? 'bg-[var(--color-surface-hover)]' : '']"
          @mouseenter="selectedIndex = index"
        >
          <button
            type="button"
            @click="selectEntry(entry)"
            :class="[
              'flex min-w-0 flex-1 items-center rounded-lg px-2.5 text-left transition-colors hover:bg-[var(--color-surface-hover)] focus-visible:outlineNone focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/40',
              isSearchMode ? 'gap-2.5 py-2' : 'gap-3 py-2',
            ]"
            role="option"
            :aria-selected="selectedIndex === index"
          >
            <span
              :class="[
                'material-symbols-outlined shrink-0 text-[17px]',
                entry.isDirectory ? 'text-[var(--color-brand)]' : 'text-[var(--color-text-secondary)]',
              ]"
            >
              {{ entry.isDirectory ? 'folder' : 'description' }}
            </span>
            <span class="min-w-0 flex-1">
              <span
                v-if="isSearchMode"
                class="block truncate font-[var(--font-mono)] text-sm text-[var(--color-text-primary)]"
                :title="getDisplayPath(entry)"
              >
                {{ getDisplayPath(entry) }}
              </span>
              <template v-else>
                <span class="block truncate text-sm font-medium text-[var(--color-text-primary)]">{{ entry.name }}</span>
                <span class="block truncate font-[var(--font-mono)] text-[11px] text-[var(--color-text-tertiary)]">
                  {{ getRelativePath(entry).split('/').slice(0, -1).join('/') || (entry.isDirectory ? t('fileSearch.directory') : t('fileSearch.currentDirectory')) }}
                </span>
              </template>
            </span>
            <span
              v-if="!isSearchMode"
              class="shrink-0 rounded-md border border-[var(--color-border)] px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.02em] text-[var(--color-text-tertiary)]"
            >
              {{ entry.isDirectory ? t('fileSearch.folderTag') : t('fileSearch.fileTag') }}
            </span>
          </button>
          <button
            v-if="entry.isDirectory"
            type="button"
            :aria-label="t('fileSearch.openFolder')"
            :title="t('fileSearch.openFolder')"
            @click.stop="navigateEntry(entry)"
            class="my-1 flex w-9 shrink-0 items-center justify-center rounded-lg text-[var(--color-text-tertiary)] opacity-70 transition hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/40 group-hover:opacity-100"
          >
            <span class="material-symbols-outlined text-[16px]">chevron_right</span>
          </button>
        </div>
      </template>
    </div>

    <!-- Footer hint -->
    <div
      v-if="!props.compact"
      class="flex items-center gap-1.5 border-t border-[var(--color-border)] px-3 py-1.5 text-[10px] text-[var(--color-text-tertiary)]"
    >
      <kbd class="rounded border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-1 py-0.5 font-mono">↑↓</kbd>
      <span>{{ t('fileSearch.navigate') }}</span>
      <kbd class="ml-2 rounded border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-1 py-0.5 font-mono">Enter</kbd>
      <span>{{ t('fileSearch.select') }}</span>
      <kbd class="ml-2 rounded border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-1 py-0.5 font-mono">→</kbd>
      <span>{{ t('fileSearch.open') }}</span>
      <kbd class="ml-2 rounded border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-1 py-0.5 font-mono">Esc</kbd>
      <span>{{ t('fileSearch.close') }}</span>
    </div>
  </div>
</template>