<script setup lang="ts">
/**
 * WorkspacePanel — Vue 3 port of components/workspace/WorkspacePanel.tsx (1558 lines)
 * File browser, code editor, workspace navigation panel.
 *
 * Sub-components (rendered as local components in template via component registration):
 * - FileTypeBadge, FileStatusBadge
 * - PanelMessage, ToolbarIconButton
 * - WorkspaceFilterInput
 * - CodeSurface (with line comments, text selection)
 * - MarkdownSurface (with text selection)
 * - ImagePreview
 * - ChangedFileRow
 * - TreeNode (recursive file tree)
 * - FloatingSelectionMenu
 */

import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useWorkspacePanelStore, getWorkspacePreviewTabId, WORKSPACE_PANEL_DEFAULT_WIDTH } from '../stores/workspacePanelStore'
import { useChatStore } from '../stores/chatStore'
import { useWorkspaceChatContextStore } from '../stores/workspaceChatContextStore'
import { useUIStore } from '../stores/uiStore'
import { useTranslation } from '../../i18n'
import MarkdownRenderer from '../components/shared/MarkdownRenderer.vue'
import WorkspaceFileOpenWith from './WorkspaceFileOpenWith.vue'

// ─── Props / Emits ───────────────────────────────────────────────────

export interface WorkspacePanelProps {
  sessionId: string
  embedded?: boolean
  forceVisible?: boolean
}

const props = withDefaults(defineProps<WorkspacePanelProps>(), {
  embedded: false,
  forceVisible: false,
})

const emit = defineEmits<{
  close: []
}>()

// ─── Constants ───────────────────────────────────────────────────────

const FILE_STATUS_META: Record<string, { label: string; className: string }> = {
  modified: { label: 'M', className: 'border-[var(--color-warning)]/35 bg-[var(--color-warning)]/12 text-[var(--color-warning)]' },
  added: { label: 'A', className: 'border-[var(--color-success)]/35 bg-[var(--color-success)]/12 text-[var(--color-success)]' },
  deleted: { label: 'D', className: 'border-[var(--color-error)]/35 bg-[var(--color-error)]/12 text-[var(--color-error)]' },
  renamed: { label: 'R', className: 'border-[var(--color-brand)]/35 bg-[var(--color-brand)]/12 text-[var(--color-brand)]' },
  untracked: { label: 'U', className: 'border-[var(--color-tertiary)]/35 bg-[var(--color-tertiary)]/12 text-[var(--color-tertiary)]' },
  copied: { label: 'C', className: 'border-[var(--color-secondary)]/35 bg-[var(--color-secondary)]/12 text-[var(--color-secondary)]' },
  type_changed: { label: 'T', className: 'border-[var(--color-outline)]/45 bg-[var(--color-outline)]/10 text-[var(--color-text-secondary)]' },
  unknown: { label: '?', className: 'border-[var(--color-outline)]/45 bg-[var(--color-outline)]/10 text-[var(--color-text-secondary)]' },
}

const FILE_BADGE_META: Record<string, { label: string; className: string }> = {
  ts: { label: 'TS', className: 'bg-[var(--color-secondary)]/14 text-[var(--color-secondary)]' },
  tsx: { label: 'TSX', className: 'bg-[var(--color-secondary)]/14 text-[var(--color-secondary)]' },
  js: { label: 'JS', className: 'bg-[var(--color-warning)]/16 text-[var(--color-warning)]' },
  jsx: { label: 'JSX', className: 'bg-[var(--color-warning)]/16 text>[var(--color-warning)]' },
  json: { label: '{}', className: 'bg-[var(--color-tertiary)]/14 text-[var(--color-tertiary)]' },
  md: { label: 'MD', className: 'bg-[var(--color-text-tertiary)]/14 text-[var(--color-text-secondary)]' },
  css: { label: 'CSS', className: 'bg-[var(--color-secondary)]/14 text>[var(--color-secondary)]' },
  html: { label: 'H', className: 'bg-[var(--color-brand)]/14 text-[var(--color-brand)]' },
  png: { label: 'IMG', className: 'bg-[var(--color-success)]/14 text>[var(--color-success)]' },
  jpg: { label: 'IMG', className: 'bg-[var(--color-success)]/14 text>[var(--color-success)]' },
  jpeg: { label: 'IMG', className: 'bg-[var(--color-success)]/14 text>[var(--color-success)]' },
  gif: { label: 'IMG', className: 'bg-[var(--color-success)]/14 text>[var(--color-success)]' },
  svg: { label: 'SVG', className: 'bg-[var(--color-success)]/14 text>[var(--color-success)]' },
}

const EMPTY_TREE_BY_PATH: Record<string, any> = {}
const EMPTY_PREVIEW_TABS: any[] = []
const EMPTY_EXPANDED_PATHS: string[] = []
const SELECTION_MENU_OFFSET = 10
const SELECTION_MENU_WIDTH = 158
const SELECTION_MENU_HEIGHT = 44
const WORKSPACE_PREVIEW_LINE_LIMIT = 2000

// ─── Store access ────────────────────────────────────────────────────

const store = useWorkspacePanelStore()
const chatStore = useChatStore()
const workspaceChatStore = useWorkspaceChatContextStore()
const uiStore = useUIStore()
const t = useTranslation()

// ─── Local state ─────────────────────────────────────────────────────

const filterQuery = ref('')
const isViewMenuOpen = ref(false)
const isNavigatorOpen = ref(false)
const previewTabContextMenu = ref<{ tabId: string; x: number; y: number } | null>(null)
const fileContextMenu = ref<{ path: string; isDirectory: boolean; x: number; y: number } | null>(null)

// Computed from store (session-scoped)
const sessionId = computed(() => props.sessionId)
const panelWidth = computed(() => store.width)
const isPanelOpen = computed(() => store.isPanelOpen(sessionId.value))
const activeView = computed(() => store.getActiveView(sessionId.value))
const status = computed(() => store.statusBySession[sessionId.value])
const statusLoading = computed(() => store.loading.statusBySession[sessionId.value] ?? false)
const statusError = computed(() => store.errors.statusBySession[sessionId.value] ?? null)

// Session-scoped tree state
function getSessionScopedRecord<T>(record: Record<string, T>): Record<string, T> {
  const prefix = `${sessionId.value}::`
  return Object.fromEntries(
    Object.entries(record).filter(([key]) => key.startsWith(prefix)),
  ) as Record<string, T>
}

const treeByPath = computed(() => store.treeBySessionPath[sessionId.value] ?? EMPTY_TREE_BY_PATH)
const treeLoadingByPath = computed(() => getSessionScopedRecord(store.loading.treeBySessionPath))
const treeErrorsByPath = computed(() => getSessionScopedRecord(store.errors.treeBySessionPath))
const previewTabs = computed(() => store.previewTabsBySession[sessionId.value] ?? EMPTY_PREVIEW_TABS)
const activePreviewTabId = computed(() => store.activePreviewTabIdBySession[sessionId.value] ?? null)
const expandedPaths = computed(() => store.expandedPathsBySession[sessionId.value] ?? EMPTY_EXPANDED_PATHS)

const rootTree = computed(() => treeByPath.value[''])
const rootTreeKey = computed(() => `${sessionId.value}::`)
const rootTreeLoading = computed(() => treeLoadingByPath.value[rootTreeKey.value] ?? false)
const rootTreeError = computed(() => treeErrorsByPath.value[rootTreeKey.value] ?? null)

const normalizedFilterQuery = computed(() => filterQuery.value.trim().toLowerCase())
const expandedPathSet = computed(() => new Set(expandedPaths.value))

const activePreviewTab = computed(() => {
  const tabs = previewTabs.value
  return tabs.find((tab: any) => tab.id === activePreviewTabId.value) ?? tabs[tabs.length - 1] ?? null
})
const hasPreviewTabs = computed(() => previewTabs.value.length > 0)
const isNavigatorVisible = computed(() => !hasPreviewTabs.value || isNavigatorOpen.value)
const activeTreePath = computed(() => activePreviewTab.value?.kind === 'file' ? activePreviewTab.value.path : null)

const chatState = computed(() => {
  const session = chatStore.sessions?.[sessionId.value]
  return session?.chatState ?? 'idle'
})

const filteredChangedFiles = computed(() => {
  const files = status.value?.changedFiles ?? []
  return files.filter((file: any) => changedFileMatchesFilter(file, normalizedFilterQuery.value))
})

const filteredRootEntries = computed(() => {
  if (rootTree.value?.state !== 'ok') return []
  return rootTree.value.entries.filter((entry: any) => treeEntryMatchesFilter(entry, normalizedFilterQuery.value, treeByPath.value))
})

const activePreviewRequestKey = computed(() => {
  if (!activePreviewTab.value) return null
  return `${sessionId.value}::${activePreviewTab.value.id}`
})
const activePreviewLoading = computed(() => {
  if (!activePreviewRequestKey.value) return false
  return store.loading.previewByTabId[activePreviewRequestKey.value] ?? false
})
const activePreviewError = computed(() => {
  if (!activePreviewRequestKey.value) return null
  return store.errors.previewByTabId[activePreviewRequestKey.value] ?? null
})

const shouldRender = computed(() => props.forceVisible || isPanelOpen.value)

// ─── Lifecycle refresh tracking ──────────────────────────────────────

const refreshLifecycle = ref({
  sessionId: sessionId.value,
  isOpen: shouldRender.value,
  chatState: chatState.value as string,
})

watch(
  [chatState, shouldRender, statusLoading],
  ([cs, sr, sl]) => {
    const previous = refreshLifecycle.value
    const sessionChanged = previous.sessionId !== sessionId.value
    const opened = sr && (sessionChanged || !previous.isOpen)
    const completedTurn = sr && !sessionChanged && previous.chatState !== 'idle' && cs === 'idle'

    refreshLifecycle.value = { sessionId: sessionId.value, isOpen: sr, chatState: cs }

    const shouldRefreshOnOpen = opened
    const shouldRefreshAfterCompletedTurn = completedTurn && cs === 'idle'
    if ((!shouldRefreshOnOpen && !shouldRefreshAfterCompletedTurn) || sl) return
    void store.loadStatus(sessionId.value)
  },
)

watch(
  [activeView, isNavigatorVisible, () => rootTree.value, rootTreeLoading, rootTreeError, shouldRender],
  () => {
    if (!shouldRender.value || !isNavigatorVisible.value || activeView.value !== 'all' || rootTree.value || rootTreeLoading.value || rootTreeError.value) return
    void store.loadTree(sessionId.value, '')
  },
)

// Close context menus on click outside
let contextMenuCloseHandler: (() => void) | null = null
watch([previewTabContextMenu, fileContextMenu], () => {
  if (previewTabContextMenu.value || fileContextMenu.value) {
    if (contextMenuCloseHandler) contextMenuCloseHandler()
    const close = () => {
      previewTabContextMenu.value = null
      fileContextMenu.value = null
    }
    document.addEventListener('click', close)
    contextMenuCloseHandler = () => document.removeEventListener('click', close)
  }
})

watch([hasPreviewTabs, isNavigatorOpen], ([has, isOpen]) => {
  if (!has && isOpen) isNavigatorOpen.value = false
})

watch(isNavigatorVisible, (visible) => {
  if (!visible) isViewMenuOpen.value = false
})

// ─── Helper functions ────────────────────────────────────────────────

function getFileExtension(name: string): string {
  const dotIndex = name.lastIndexOf('.')
  if (dotIndex < 0) return ''
  return name.slice(dotIndex + 1).toLowerCase()
}

function getFileBadgeMeta(name: string) {
  const extension = getFileExtension(name)
  return FILE_BADGE_META[extension] ?? {
    label: extension ? extension.slice(0, 3).toUpperCase() : 'TXT',
    className: 'bg-[var(--color-text-tertiary)]/12 text-[var(--color-text-secondary)]',
  }
}

function resolveWorkspaceAttachmentPath(workDir: string | undefined, filePath: string): string {
  if (!workDir || filePath.startsWith('/') or /^[a-zA-Z]:[\\\/]/.test(filePath)) return filePath
  return `${workDir.replace(/[\\\/]+$/, '')}/${filePath.replace(/^[/\\]+/, '')}`
}

function getWorkspaceReferenceName(path: string, isDirectory = false): string {
  const name = path.split('/').filter(Boolean).pop() || path
  return isDirectory && !name.endsWith('/') ? `${name}/` : name
}

function isMarkdownPreview(tab: any): boolean {
  if (!tab || tab.kind !== 'file') return false
  const language = (tab.language ?? '').toLowerCase()
  const extension = getFileExtension(tab.path)
  return language === 'markdown' || language === 'md' || extension === 'md' || extension === 'markdown'
}

function getPreviewKindLabel(kind: string): string {
  return kind === 'diff' ? t('workspace.previewKind.diff') : t('workspace.previewKind.file')
}

function getInlineStateMessage(
  state: string | undefined,
  fallbackError?: string | null,
): string {
  switch (state) {
    case 'loading': return t('workspace.previewState.loading')
    case 'binary': return t('workspace.previewState.binary')
    case 'too_large': return t('workspace.previewState.tooLarge')
    case 'missing': return t('workspace.previewState.missing')
    case 'not_git_repo': return t('workspace.notGitRepo')
    case 'error': return fallbackError || t('workspace.loadError')
    default: return fallbackError || t('workspace.loadError')
  }
}

function changedFileMatchesFilter(file: any, query: string): boolean {
  if (!query) return true
  return (
    file.path.toLowerCase().includes(query) ||
    (file.oldPath?.toLowerCase().includes(query)) ||
    file.status.toLowerCase().includes(query)
  )
}

function treeEntryMatchesFilter(
  entry: any,
  query: string,
  treeByPath: Record<string, any>,
): boolean {
  if (!query) return true
  if (entry.name.toLowerCase().includes(query) || entry.path.toLowerCase().includes(query)) {
    return true
  }
  if (!entry.isDirectory) return false
  const childTree = treeByPath[entry.path]
  if (childTree?.state !== 'ok') return false
  return childTree.entries.some((child: any) => treeEntryMatchesFilter(child, query, treeByPath))
}

function makeTreeStateKey(sessionId: string, path: string): string {
  return `${sessionId}::${path}`
}

function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      return navigator.clipboard.writeText(text).then(() => true).catch(() => false)
    }
  } catch { /* fall through */ }
  try {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', 'true')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    const copied = document.execCommand('copy')
    document.body.removeChild(textarea)
    return Promise.resolve(copied)
  } catch {
    return Promise.resolve(false)
  }
}

function clearWindowSelection() {
  window.getSelection()?.removeAllRanges()
}

// ─── Actions ─────────────────────────────────────────────────────────

function handleRefresh() {
  void store.loadStatus(sessionId.value)
  if (activeView.value === 'all') {
    void store.loadTree(sessionId.value, '')
  }
}

function handleOpenDiff(path: string) {
  void store.openPreview(sessionId.value, path, 'diff')
}

function handleOpenFile(path: string) {
  void store.openPreview(sessionId.value, path, 'file')
}

function addWorkspacePathToChat(path: string, isDirectory = false) {
  workspaceChatStore.addReference(sessionId.value, {
    kind: 'file',
    path,
    absolutePath: resolveWorkspaceAttachmentPath(status.value?.workDir, path),
    name: getWorkspaceReferenceName(path, isDirectory),
    isDirectory,
  })
}

function addLineCommentToChat(path: string, line: number, note: string, quote: string) {
  workspaceChatStore.addReference(sessionId.value, {
    kind: 'code-comment',
    path,
    absolutePath: resolveWorkspaceAttachmentPath(status.value?.workDir, path),
    name: path.split('/').pop() || path,
    lineStart: line,
    lineEnd: line,
    note,
    quote,
  })
}

function addSelectionToChat(path: string, selection: { text: string; startLine?: number; endLine?: number }) {
  workspaceChatStore.addReference(sessionId.value, {
    kind: 'code-selection',
    path,
    absolutePath: resolveWorkspaceAttachmentPath(status.value?.workDir, path),
    name: path.split('/').pop() || path,
    lineStart: selection.startLine,
    lineEnd: selection.endLine,
    quote: selection.text,
  })
}

function handleSetActiveView(view: 'changed' | 'all') {
  store.setActiveView(sessionId.value, view)
  isViewMenuOpen.value = false
}

function handlePreviewTabContextMenu(event: MouseEvent, tabId: string) {
  event.preventDefault()
  event.stopPropagation()
  fileContextMenu.value = null
  previewTabContextMenu.value = { tabId, x: event.clientX, y: event.clientY }
}

function handleFileContextMenu(event: MouseEvent, path: string, isDirectory = false) {
  event.preventDefault()
  event.stopPropagation()
  previewTabContextMenu.value = null
  fileContextMenu.value = { path, isDirectory, x: event.clientX, y: event.clientY }
}

function handleClosePreviewTabs(scope: string) {
  if (!previewTabContextMenu.value) return
  store.closePreviewTabs(sessionId.value, previewTabContextMenu.value.tabId, scope as any)
  previewTabContextMenu.value = null
}

async function copyWorkspacePath(path: string, mode: 'relative' | 'absolute' = 'relative') {
  const pathToCopy = mode === 'absolute' ? resolveWorkspaceAttachmentPath(status.value?.workDir, path) : path
  const copied = await copyTextToClipboard(pathToCopy)
  fileContextMenu.value = null
  uiStore.showToast(
    copied ? t('workspace.pathCopied') : t('common.copyFailed'),
    copied ? 'success' : 'error',
  )
}

function handleClosePanel() {
  store.closePanel(sessionId.value)
  emit('close')
}

// ─── Selection position helpers ──────────────────────────────────────

function getSelectionPopoverPosition(
  range: Range,
  root: HTMLElement,
  opts: { menuWidth: number; menuHeight: number; offset: number; fallbackPointer?: { clientX: number; clientY: number } },
): { x: number; y: number } {
  const viewportMargin = 12
  const selectionRect = (() => {
    const clientRects = Array.from(range.getClientRects()).filter((r) => r.width > 0 || r.height > 0)
    if (clientRects.length > 0) {
      return {
        left: Math.min(...clientRects.map((r) => r.left)),
        top: Math.min(...clientRects.map((r) => r.top)),
        right: Math.max(...clientRects.map((r) => r.right)),
        bottom: Math.max(...clientRects.map((r) => r.bottom)),
        width: 0, height: 0,
      }
    }
    const boundingRect = range.getBoundingClientRect()
    if (boundingRect.width > 0 || boundingRect.height > 0) return boundingRect
    const fallback = opts.fallbackPointer
      ? { left: opts.fallbackPointer.clientX, top: opts.fallbackPointer.clientY, right: 0, bottom: 0, width: 0, height: 0 }
      : null
    return fallback ?? { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }
  })()

  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1000
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 800
  const minX = viewportMargin
  const maxX = Math.max(minX, viewportWidth - opts.menuWidth - viewportMargin)
  const minY = viewportMargin
  const maxY = Math.max(minY, viewportHeight - opts.menuHeight - viewportMargin)
  const clamp = (pos: { x: number; y: number }) => ({
    x: Math.max(minX, Math.min(maxX, pos.x)),
    y: Math.max(minY, Math.min(maxY, pos.y)),
  })

  const centerX = selectionRect.left + selectionRect.width / 2
  const centerY = selectionRect.top + selectionRect.height / 2
  const above = { x: centerX - opts.menuWidth / 2, y: selectionRect.top - opts.menuHeight - opts.offset }
  const right = { x: selectionRect.right + opts.offset, y: centerY - opts.menuHeight / 2 }
  const below = { x: centerX - opts.menuWidth / 2, y: selectionRect.bottom + opts.offset }

  // Prefer above for single-line selections
  if (above.y >= viewportMargin) return clamp(above)
  if (right.x + opts.menuWidth <= viewportWidth - viewportMargin) return clamp(right)
  if (below.y + opts.menuHeight <= viewportHeight - viewportMargin) return clamp(below)
  return clamp(above)
}

function getElementForNode(node: Node | null): Element | null {
  if (!node) return null
  return node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement
}

function getLineNumberFromNode(node: Node | null, root: HTMLElement): number | undefined {
  const element = getElementForNode(node)
  const row = element?.closest('[data-workspace-line-number]')
  if (!row || !root.contains(row)) return undefined
  const line = Number(row.getAttribute('data-workspace-line-number'))
  return Number.isFinite(line) ? line : undefined
}

function getTextSelectionFromContainer(
  root: HTMLElement | null,
  resolveLines?: (text: string, range: Range) => { startLine?: number; endLine?: number },
  pointer?: { clientX: number; clientY: number },
): { text: string; startLine?: number; endLine?: number; x: number; y: number } | null {
  if (!root) return null
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return null
  const range = selection.getRangeAt(0)
  const startElement = getElementForNode(range.startContainer)
  const endElement = getElementForNode(range.endContainer)
  if (!startElement || !endElement || !root.contains(startElement) || !root.contains(endElement)) {
    return null
  }
  const text = selection.toString().trim()
  if (!text) return null

  const nodeLines = {
    startLine: getLineNumberFromNode(range.startContainer, root),
    endLine: getLineNumberFromNode(range.endContainer, root),
  }
  const resolvedLines = resolveLines?.(text, range) ?? nodeLines
  const startLine = resolvedLines.startLine ?? nodeLines.startLine
  const endLine = resolvedLines.endLine ?? nodeLines.endLine ?? startLine
  const orderedStart = startLine && endLine ? Math.min(startLine, endLine) : startLine
  const orderedEnd = startLine && endLine ? Math.max(startLine, endLine) : endLine

  return {
    ...getSelectionPopoverPosition(range, root, {
      menuWidth: SELECTION_MENU_WIDTH,
      menuHeight: SELECTION_MENU_HEIGHT,
      offset: SELECTION_MENU_OFFSET,
      fallbackPointer: pointer,
    }),
    text,
    ...(orderedStart ? { startLine: orderedStart } : {}),
    ...(orderedEnd ? { endLine: orderedEnd } : {}),
  }
}

function getLineRangeForText(value: string, text: string): { startLine?: number; endLine?: number } {
  const index = value.indexOf(text)
  if (index < 0) return {}
  const startLine = value.slice(0, index).split('\n').length
  const endLine = startLine + text.split('\n').length - 1
  return { startLine, endLine }
}

// ─── Selection popover dismiss (composable) ──────────────────────────

function useSelectionPopoverDismiss(
  active: boolean,
  popoverRef: { value: HTMLButtonElement | null },
  onDismiss: () => void,
) {
  let dismiss = () => {
    onDismiss()
    clearWindowSelection()
  }

  const handlePointerDown = (event: PointerEvent) => {
    const popover = popoverRef.value
    const target = event.target
    if (popover && target instanceof Node && popover.contains(target)) return
    dismiss()
  }

  const handleScroll = () => dismiss()

  onMounted(() => {
    document.addEventListener('pointerdown', handlePointerDown, true)
    document.addEventListener('scroll', handleScroll, true)
  })

  onUnmounted(() => {
    document.removeEventListener('pointerdown', handlePointerDown, true)
    document.removeEventListener('scroll', handleScroll, true)
  })
}

// ─── Panel dimensions ────────────────────────────────────────────────

const panelMaxWidth = computed(() => hasPreviewTabs.value ? 'min(62%, calc(100% - 328px))' : '36%')
const panelMinWidth = computed(() => hasPreviewTabs.value ? 'min(420px, 54%)' : 'min(340px, 40%)')
</script>

<template>
  <div v-if="!shouldRender"></div>
  <aside
    v-else
    data-testid="workspace-panel"
    :class="embedded
      ? 'flex h-full min-h-0 w-full min-w-0 bg-[var(--color-surface)]'
      : 'flex h-full shrink-0 border-l border-[var(--color-border)] bg-[var(--color-surface)]'
    "
    :style="embedded ? undefined : { width: panelWidth, maxWidth: panelMaxWidth, minWidth: panelMinWidth }"
  >
    <!-- Preview area -->
    <div
      v-if="hasPreviewTabs"
      :class="['flex min-w-0 flex-1 flex-col bg-[var(--color-surface)]', isNavigatorVisible ? 'border-r border-[var(--color-border)]' : '']"
    >
      <!-- Preview tabs -->
      <div class="flex h-11 shrink-0 items-center gap-2 border-b border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] px-3">
        <div
          role="tablist"
          :aria-label="t('workspace.previewTabs')"
          class="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto bg-[var(--color-surface-container-lowest)]"
        >
          <div
            v-if="previewTabs.length === 0"
            class="flex items-center gap-2 px-1.5 text-[12px] text>[var(--color-text-tertiary)]"
          >
            <span class="material-symbols-outlined text>[15px]" style="fontVariationSettings: 'FILL' 1">docs</span>
            <span>{{ t('workspace.preview') }}</span>
          </div>
          <div
            v-for="tab in previewTabs"
            :key="tab.id"
            @contextmenu="(event) => handlePreviewTabContextMenu(event, tab.id)"
            :class="['group flex h-8 min-w-[118px] max-w-[210px] shrink-0 items-center gap-2 rounded-[8px] px-2 text-left text-[13px] transition-colors',
              tab.id === activePreviewTab?.id
                ? 'bg>[var(--color-surface-selected)] text>[var(--color-text-primary)]'
                : 'text>[var(--color-text-secondary)] hover:bg>[var(--color-surface-hover)] hover:text>[var(--color-text-primary)]'
            ]"
          >
            <button
              type="button"
              role="tab"
              :aria-selected="tab.id === activePreviewTab?.id"
              @click="store.openPreview(sessionId, tab.path, tab.kind)"
              class="min-w-0 flex flex-1 items-center gap-2 text-left"
            >
              <span
                v-if="tab.kind === 'diff'"
                class="material-symbols-outlined shrink-0 text>[15px] text>[var(--color-text-tertiary)]"
                style="fontVariationSettings: 'FILL' 1"
              >difference</span>
              <FileTypeBadge v-else :name="tab.title" :subtle="tab.id !== activePreviewTab?.id" />
              <span class="min-w-0 flex-1 truncate">{{ tab.title }}</span>
            </button>
            <button
              type="button"
              :aria-label="t('workspace.closeTab') + ' ' + tab.title + ' ' + getPreviewKindLabel(tab.kind)"
              @click="store.closePreview(sessionId, tab.id)"
              class="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-[5px] text>[var(--color-text-tertiary)] opacity-0 transition-colors hover:bg>[var(--color-surface-hover)] hover:text>[var(--color-text-primary)] group-hover:opacity-100 focus-visible:opacity-100"
            >
              <span class="material-symbols-outlined text>[13px] leading-none" style="fontVariationSettings: 'FILL' 1">close</span>
            </button>
          </div>
        </div>
        <ToolbarIconButton
          :icon="isNavigatorVisible ? 'right_panel_close' : 'account_tree'"
          :label="isNavigatorVisible ? t('workspace.hideNavigator') : t('workspace.showNavigator')"
          @click="isNavigatorOpen = !isNavigatorOpen"
        />
      </div>

      <!-- Preview content -->
      <PreviewContent
        :session-id="sessionId"
        :status="status"
        :active-preview-tab="activePreviewTab"
        :active-preview-loading="activePreviewLoading"
        :active-preview-error="activePreviewError"
        @add-selection="(path, sel) => addSelectionToChat(path, sel)"
        @add-line-comment="(path, line, note, quote) => addLineCommentToChat(path, line, note, quote)"
        @add-path="addWorkspacePathToChat"
      />

      <!-- Preview tab context menu -->
      <div
        v-if="previewTabContextMenu"
        role="menu"
        class="fixed z-50 min-w-[156px] rounded-[10px] border border>[var(--color-border)] bg>[var(--color-surface-container-lowest)] py-1 text>[12px] shadow>[var(--shadow-dropdown)]"
        :style="{ left: previewTabContextMenu.x, top: previewTabContextMenu.y }"
        @click.stop
      >
        <button
          type="button"
          role="menuitem"
          @click="handleClosePreviewTabs('current')"
          class="block w-full px-3 py-1.5 text-left text>[var(--color-text-primary)] hover:bg>[var(--color-surface-hover)]"
        >{{ t('tabs.close') }}</button>
        <button
          type="button"
          role="menuitem"
          @click="handleClosePreviewTabs('others')"
          class="block w-full px-3 py-1.5 text-left text>[var(--color-text-primary)] hover:bg>[var(--color-surface-hover)]"
        >{{ t('tabs.closeOthers') }}</button>
        <button
          type="button"
          role="menuitem"
          @click="handleClosePreviewTabs('left')"
          class="block w-full px-3 py-1.5 text-left text>[var(--color-text-primary)] hover:bg>[var(--color-surface-hover)]"
        >{{ t('tabs.closeLeft') }}</button>
        <button
          type="button"
          role="menuitem"
          @click="handleClosePreviewTabs('right')"
          class="block w-full px-3 py-1.5 text-left text>[var(--color-text-primary)] hover:bg>[var(--color-surface-hover)]"
        >{{ t('tabs.closeRight') }}</button>
        <div class="my-1 border-t border>[var(--color-border)]"></div>
        <button
          type="button"
          role="menuitem"
          @click="handleClosePreviewTabs('all')"
          class="block w-full px-3 py-1.5 text-left text>[var(--color-text-primary)] hover:bg>[var(--color-surface-hover)]"
        >{{ t('tabs.closeAll') }}</button>
      </div>
    </div>

    <!-- Navigator panel -->
    <div
      v-if="isNavigatorVisible"
      :class="hasPreviewTabs ? 'basis-[32%] min-w-[220px] max-w>[320px] flex h-full shrink-0 flex-col bg>[var(--color-surface)]' : 'w-full flex h-full shrink-0 flex-col bg>[var(--color-surface)]'"
    >
      <!-- Header -->
      <div class="flex h-10 shrink-0 items-center gap-1.5 border-b border>[var(--color-border)] px-2.5">
        <div class="relative min-w-0">
          <button
            type="button"
            :aria-label="activeView === 'changed' ? t('workspace.changedFiles') : t('workspace.allFiles')"
            aria-haspopup="menu"
            :aria-expanded="isViewMenuOpen"
            @click="isViewMenuOpen = !isViewMenuOpen"
            class="inline-flex min-w-0 max-w-full items-center gap-1 rounded-[7px] px-2 py-1 text-[14px] font-semibold leading-5 text>[var(--color-text-primary)] transition-colors hover:bg>[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring>[var(--color-brand)]/35"
          >
            <span class="truncate">
              {{ activeView === 'changed' ? t('workspace.changedFiles') : t('workspace.allFiles') }}
            </span>
            <span class="material-symbols-outlined shrink-0 text>[15px] font-normal text>[var(--color-text-tertiary)]" style="fontVariationSettings: 'FILL' 1">expand_more</span>
          </button>
          <div
            v-if="isViewMenuOpen"
            role="menu"
            class="absolute left-0 top-[calc(100%+4px)] z-30 min-w-[124px] overflow-hidden rounded-[9px] border border>[var(--color-border)] bg>[var(--color-surface-container-lowest)] py-1 shadow>[var(--shadow-dropdown)]"
          >
            <button
              v-for="view in ['changed', 'all']"
              :key="view"
              type="button"
              role="menuitem"
              @click="handleSetActiveView(view as 'changed' | 'all')"
              :class="['flex h-7 w-full items-center gap-2 px-2.5 text-left text>[12px] transition-colors',
                activeView === view
                  ? 'bg>[var(--color-surface-selected)] text>[var(--color-text-primary)]'
                  : 'text>[var(--color-text-secondary)] hover:bg>[var(--color-surface-hover)]'
              ]"
            >
              <span class="min-w-0 flex-1 truncate">
                {{ view === 'changed' ? t('workspace.changedFiles') : t('workspace.allFiles') }}
              </span>
              <span
                v-if="activeView === view"
                class="material-symbols-outlined text>[14px] text>[var(--color-brand)]"
                style="fontVariationSettings: 'FILL' 1"
              >check</span>
            </button>
          </div>
        </div>

        <div class="ml-auto flex shrink-0 items-center gap-1">
          <ToolbarIconButton
            icon="refresh"
            :label="t('workspace.refresh')"
            @click="handleRefresh"
          />
          <ToolbarIconButton
            v-if="!embedded"
            icon="close"
            :label="t('workspace.closePanel')"
            @click="handleClosePanel"
          />
        </div>
      </div>

      <!-- Filter input -->
      <WorkspaceFilterInput :value="filterQuery" @change="filterQuery = $event" />

      <!-- Content area -->
      <div class="min-h-0 flex-1 overflow-auto py-2">
        <template v-if="activeView === 'changed'">
          <PanelMessage v-if="statusLoading && !status" icon="progress_activity" :message="t('common.loading')" />
          <PanelMessage v-else-if="status?.state === 'missing_workdir'" icon="folder_off" :message="t('workspace.missingWorkdir')" />
          <PanelMessage v-else-if="status?.state === 'not_git_repo'" icon="account_tree" :message="t('workspace.notGitRepo')" />
          <PanelMessage v-else-if="statusError || status?.state === 'error'" icon="error" tone="error" :message="statusError || status?.error || t('workspace.loadError')" />
          <PanelMessage v-else-if="!status" icon="progress_activity" :message="t('common.loading')" />
          <PanelMessage v-else-if="status.changedFiles.length === 0" icon="check_circle" :message="t('workspace.noChanges')" />
          <PanelMessage v-else-if="filteredChangedFiles.length === 0" icon="search_off" :message="t('workspace.noMatchingFiles')" />
          <div v-else>
            <ChangedFileRow
              v-for="file in filteredChangedFiles"
              :key="file.path + ':' + file.status + ':' + (file.oldPath ?? '')"
              :file="file"
              @click="handleOpenDiff(file.path)"
              @context-menu="(event, p) => handleFileContextMenu(event, p)"
            />
          </div>
        </template>
        <template v-else>
          <PanelMessage v-if="rootTreeLoading && !rootTree" icon="progress_activity" :message="t('common.loading')" />
          <PanelMessage v-else-if="rootTreeError" icon="error" tone="error" :message="rootTreeError" />
          <PanelMessage v-else-if="rootTree?.state === 'missing'" icon="folder_off" :message="t('workspace.missingWorkdir')" />
          <PanelMessage v-else-if="rootTree?.state === 'error'" icon="error" tone="error" :message="rootTree.error || t('workspace.loadError')" />
          <PanelMessage v-else-if="!rootTree" icon="progress_activity" :message="t('common.loading')" />
          <PanelMessage v-else-if="rootTree.entries.length === 0" icon="folder_open" :message="t('workspace.noFiles')" />
          <PanelMessage v-else-if="filteredRootEntries.length === 0" icon="search_off" :message="t('workspace.noMatchingFiles')" />
          <div v-else class="py-1">
            <TreeNode
              v-for="entry in filteredRootEntries"
              :key="entry.path"
              :session-id="sessionId"
              :entry="entry"
              :depth="0"
              :expanded-paths="expandedPathSet"
              :tree-by-path="treeByPath"
              :tree-loading-by-path="treeLoadingByPath"
              :tree-errors-by-path="treeErrorsByPath"
              :filter-query="normalizedFilterQuery"
              @toggle="(path) => store.toggleTreeNode(sessionId, path)"
              @open-file="handleOpenFile"
              @context-menu="(event, path, isDir) => handleFileContextMenu(event, path, isDir)"
              :active-path="activeTreePath"
            />
          </div>
        </template>
      </div>
    </div>

    <!-- File context menu -->
    <div
      v-if="fileContextMenu"
      role="menu"
      class="fixed z-50 min-w>[156px] rounded>[10px] border border>[var(--color-border)] bg>[var(--color-surface-container-lowest)] py-1 text>[12px] shadow>[var(--shadow-dropdown)]"
      :style="{ left: fileContextMenu.x, top: fileContextMenu.y }"
      @click.stop
    >
      <button
        type="button"
        role="menuitem"
        @click="addWorkspacePathToChat(fileContextMenu.path, fileContextMenu.isDirectory); fileContextMenu = null"
        class="flex w-full items-center gap-2 px-3 py-1.5 text-left text>[var(--color-text-primary)] hover:bg>[var(--color-surface-hover)]"
      >
        <span aria-hidden="true" class="material-symbols-outlined text>[14px] text>[var(--color-text-tertiary)]" style="fontVariationSettings: 'FILL' 1">person_add</span>
        <span>{{ t('workspace.addToChat') }}</span>
      </button>
      <button
        type="button"
        role="menuitem"
        @click="copyWorkspacePath(fileContextMenu.path)"
        class="flex w-full items-center gap-2 px-3 py-1.5 text-left text>[var(--color-text-primary)] hover:bg>[var(--color-surface-hover)]"
      >
        <span aria-hidden="true" class="material-symbols-outlined text>[14px] text>[var(--color-text-tertiary)]" style="fontVariationSettings: 'FILL' 1">content_copy</span>
        <span>{{ t('workspace.copyPath') }}</span>
      </button>
      <button
        type="button"
        role="menuitem"
        @click="copyWorkspacePath(fileContextMenu.path, 'absolute')"
        class="flex w-full items-center gap-2 px-3 py-1.5 text-left text>[var(--color-text-primary)] hover:bg>[var(--color-surface-hover)]"
      >
        <span aria-hidden="true" class="material-symbols-outlined text>[14px] text>[var(--color-text-tertiary)]" style="fontVariationSettings: 'FILL' 1">file_copy</span>
        <span>{{ t('workspace.copyAbsolutePath') }}</span>
      </button>
      <WorkspaceFileOpenWith
        :absolute-path="resolveWorkspaceAttachmentPath(status?.workDir, fileContextMenu.path)"
        :session-id="sessionId"
        :workspace-path="fileContextMenu.isDirectory ? undefined : fileContextMenu.path"
        @after-select="fileContextMenu = null"
      />
    </div>
  </aside>
</template>
