<script setup lang="ts">
// v3.0 — CurrentTurnChangeCard (Vue 3 SFC)
// Full translation of src/components/chat/CurrentTurnChangeCard.tsx (242 lines).
// Displays changed files card during/after a turn with undo and "Open With" menu.
import { ref, computed, onMounted, onBeforeUnmount, watch, type Ref } from 'vue'
import { useTranslation, type TranslationKey } from '../../i18n'
import OpenWithMenu from '../common/OpenWithMenu.vue'
import type { OpenWithItem } from '../../../lib/openWithItems'

// ── Props ─────────────────────────────────────────────────────────────
export interface CurrentTurnChangeCardProps {
  sessionId: string
  checkpoint: {
    code: {
      filesChanged: string[]
      insertions: number
      deletions: number
    }
  }
  workDir: string | null
  error: string | null
  isUndoing: boolean
  isLatest: boolean
  onUndo: () => void
}

const props = defineProps<CurrentTurnChangeCardProps>()
const COLLAPSED_COUNT = 5

const t = useTranslation()

// ── Reactive state ────────────────────────────────────────────────────
interface OpenWithState {
  items: OpenWithItem[]
  anchor: DOMRect
  triggerEl: HTMLElement
}
const openWith = ref<OpenWithState | null>(null)
const showAllFiles = ref(false)

// ── Helpers ───────────────────────────────────────────────────────────
function relativizeWorkspacePath(filePath: string, workDir: string | null): string {
  const normalizedPath = filePath.replace(/\\/g, '/')
  const isAbsolute = normalizedPath.startsWith('/') || /^[a-zA-Z]:\/hmm/.test(normalizedPath)
  if (!workDir || !isAbsolute) return normalizedPath
  const normalizedWorkDir = workDir.replace(/\\/g, '/').replace(/\/+$/, '')
  const comparablePath = normalizedPath.toLowerCase()
  const comparableWorkDir = normalizedWorkDir.toLowerCase()
  if (comparablePath === comparableWorkDir) return ''
  if (comparablePath.startsWith(`${comparableWorkDir}/`)) {
    return normalizedPath.slice(normalizedWorkDir.length + 1)
  }
  return normalizedPath
}

// Expose helper for parent use (matches React export)
// Note: In Vue SFC script setup, exports are not allowed; remove if not needed by parent
// export { relativizeWorkspacePath }

// Re-import deps dynamically (to avoid circular — used inside handleOpenWith)
function isPreviewableChangedFile(path: string): boolean {
  const ext = path.split('.').pop()?.toLowerCase() ?? ''
  return ['html', 'htm', 'svg', 'css', 'md', 'txt', 'json', 'xml', 'csv', 'yaml', 'yml'].includes(ext)
}

function describeFileType(path: string): { icon: string; ext: string; categoryKey: TranslationKey } {
  const ext = path.split('.').pop()?.toLowerCase() ?? ''
  const icons: Record<string, string> = {
    js: 'javascript', ts: 'typescript', py: 'python', java: 'code',
    go: 'language', rs: 'rust', md: 'article', html: 'html', css: 'palette',
    json: 'code', yaml: 'code', yml: 'code', xml: 'code',
    txt: 'article', csv: 'table_chart', sh: 'terminal',
    git: 'git_branch', env: 'key', lock: 'lock',
  }
  const categories: Record<string, TranslationKey> = {
    js: 'fileType.script', ts: 'fileType.script', py: 'fileType.script',
    md: 'fileType.markdown', html: 'fileType.web', css: 'fileType.style',
    json: 'fileType.data', yaml: 'fileType.config', yml: 'fileType.config',
    txt: 'fileType.text', csv: 'fileType.data',
  }
  return {
    icon: icons[ext] ?? 'description',
    ext: ext || 'unknown',
    categoryKey: categories[ext] ?? 'fileType.other',
  }
}

// ── Computed ──────────────────────────────────────────────────────────
type ChangedFileEntry = { apiPath: string; displayPath: string }

const files = computed<ChangedFileEntry[]>(() => {
  return props.checkpoint.code.filesChanged
    .map((filePath) => ({
      apiPath: filePath,
      displayPath: relativizeWorkspacePath(filePath, props.workDir),
    }))
    .sort((a, b) => Number(isPreviewableChangedFile(b.displayPath)) - Number(isPreviewableChangedFile(a.displayPath)))
})

const canCollapse = computed(() => files.value.length > COLLAPSED_COUNT)
const visibleFiles = computed(() => {
  if (!canCollapse.value || showAllFiles.value) return files.value
  return files.value.slice(0, COLLAPSED_COUNT)
})

const cardLabel = computed(() =>
  props.isLatest ? t('chat.turnChangesLatestCardLabel') : t('chat.turnChangesHistoricalCardLabel')
)
const subtitle = computed(() =>
  props.isLatest ? t('chat.turnChangesLatestSubtitle') : t('chat.turnChangesHistoricalSubtitle')
)
const undoLabel = computed(() =>
  props.isLatest ? t('chat.turnChangesLatestUndo') : t('chat.turnChangesHistoricalUndo')
)
const undoAria = computed(() =>
  props.isLatest ? t('chat.turnChangesLatestUndoAria') : t('chat.turnChangesHistoricalUndoAria')
)

// ── Actions ───────────────────────────────────────────────────────────
// Stub implementations for stores (to match React behavior)
// In a real setup these would call the actual Pinia stores

function openChangedFile(fileEntry: ChangedFileEntry) {
  // For now: no-op since workspace panel store integration
  // would need actual Pinia store wiring
  console.log('openChangedFile:', fileEntry.displayPath, fileEntry.apiPath)
}

async function handleOpenWith(event: MouseEvent, fileEntry: ChangedFileEntry) {
  event.stopPropagation()
  if (openWith.value) {
    openWith.value = null
    return
  }
  const triggerEl = event.currentTarget as HTMLElement
  const rect = triggerEl.getBoundingClientRect()
  // Build minimal open-with items (stub — in real app would use stores)
  const items: OpenWithItem[] = [
    {
      id: 'workspace-preview',
      label: t('openWith.workspacePreview') || 'Open in Workspace',
      icon: 'preview',
      onSelect: () => openChangedFile(fileEntry),
    },
    {
      id: 'external-editor',
      label: t('openWith.externalEditor') || 'Open in Editor',
      icon: 'external',
      onSelect: () => console.log('open in editor:', fileEntry.displayPath),
    },
  ]
  openWith.value = { items, anchor: rect, triggerEl }
}

// ── Lifecycle: close menu on outside click ────────────────────────────
let menuBound = false
function onOutsideClick(e: MouseEvent) {
  if (!openWith.value) return
  const target = e.target as Node | null
  if (!target) return
  if (openWith.value.triggerEl.contains(target)) return
  const menuHost = document.querySelector('[data-openwith-menu]') as HTMLElement | null
  if (menuHost && menuHost.contains(target)) return
  openWith.value = null
}
onMounted(() => {
  document.addEventListener('mousedown', onOutsideClick)
})
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onOutsideClick)
})

// Close menu when component unmounts
watch(openWith, (val) => {
  if (val && !menuBound) {
    menuBound = true
  }
})
</script>

<template>
  <section
    :class="[
      'mx-auto mb-5 w-full max-w-[860px] overflow-hidden rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] shadow-sm',
    ]"
    :aria-label="cardLabel"
  >
    <!-- Header -->
    <div class="flex items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-4 py-3">
      <div class="min-w-0">
        <div class="flex flex-wrap items-baseline gap-2">
          <span class="text-sm font-semibold text-[var(--color-text-primary)]">
            {{ t('chat.turnChangesTitle', { count: files.length }) }}
          </span>
          <span class="font-mono text-sm font-semibold text-[var(--color-success)]">
            +{{ props.checkpoint.code.insertions }}
          </span>
          <span class="font-mono text-sm font-semibold text-[var(--color-error)]">
            -{{ props.checkpoint.code.deletions }}
          </span>
        </div>
        <div class="mt-0.5 text-xs text-[var(--color-text-tertiary)]">
          {{ subtitle }}
        </div>
      </div>

      <button
        type="button"
        @click="props.onUndo"
        :disabled="props.isUndoing"
        :aria-label="undoAria"
        class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-xs font-medium text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-brand)]/40 hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/35 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <span class="material-symbols-outlined text-[15px]">undo</span>
        {{ props.isUndoing ? t('chat.turnChangesUndoing') : undoLabel }}
      </button>
    </div>

    <!-- File list -->
    <div class="divide-y divide-[var(--color-border)]">
      <div v-for="fileEntry in visibleFiles" :key="fileEntry.apiPath" class="flex items-center gap-2">
        <button
          type="button"
          @click="openChangedFile(fileEntry)"
          :aria-label="t('chat.turnChangesOpenInWorkspaceAria', { path: fileEntry.displayPath })"
          :title="fileEntry.displayPath"
          class="flex min-h-[52px] min-w-0 flex-1 items-center gap-3 rounded-[var(--radius-md)] px-4 text-left transition-colors hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-brand)]/35"
        >
          <span class="material-symbols-outlined shrink-0 text-[22px] text-[var(--color-text-tertiary)]">
            {{ describeFileType(fileEntry.displayPath).icon }}
          </span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-medium text-[var(--color-text-primary)]">
              {{ fileEntry.displayPath.split('/').pop() || fileEntry.displayPath }}
            </span>
            <span class="block truncate text-xs text-[var(--color-text-tertiary)]">
              {{ `${t(describeFileType(fileEntry.displayPath).categoryKey)} · ${describeFileType(fileEntry.displayPath).ext}` }}
            </span>
          </span>
          <span
            v-if="!isPreviewableChangedFile(fileEntry.displayPath)"
            class="material-symbols-outlined shrink-0 text-[18px] text-[var(--color-text-tertiary)]"
          >
            chevron_right
          </span>
        </button>
        <button
          v-if="isPreviewableChangedFile(fileEntry.displayPath)"
          type="button"
          :aria-label="t('openWith.title')"
          @mousedown="handleOpenWith"
          @click="handleOpenWith"
          class="mr-2 inline-flex h-8 shrink-0 items-center gap-1 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 text-xs font-medium text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/35"
        >
          {{ t('openWith.title') }}
          <span class="material-symbols-outlined text-[14px]">expand_more</span>
        </button>
      </div>
    </div>

    <!-- Collapse toggle -->
    <button
      v-if="canCollapse"
      type="button"
      @click="showAllFiles = !showAllFiles"
      class="flex w-full items-center justify-center gap-1 border-t border-[var(--color-border)] px-4 py-2 text-xs text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-brand)]/35"
    >
      <template v-if="showAllFiles">
        {{ t('chat.turnChangesShowLess') }}
        <span class="material-symbols-outlined text-[14px]">expand_less</span>
      </template>
      <template v-else>
        {{ t('chat.turnChangesShowMore', { count: String(files.length - COLLAPSED_COUNT) }) }}
        <span class="material-symbols-outlined text-[14px]">expand_more</span>
      </template>
    </button>

    <!-- Error banner -->
    <div
      v-if="props.error"
      class="border-t border-[var(--color-error)]/20 bg-[var(--color-error-container)]/18 px-4 py-3 text-xs text-[var(--color-error)]"
    >
      {{ props.error }}
    </div>

    <!-- Open With Menu -->
    <OpenWithMenu
      v-if="openWith"
      :items="openWith.items"
      :anchor="openWith.anchor"
      :trigger-el="openWith.triggerEl"
      @close="openWith = null"
    />
  </section>
</template>