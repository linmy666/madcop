<script setup lang="ts">
// v3.0 — MemorySettings (Vue 3)
// Full translation of React MemorySettings.tsx (911 lines)
// - useState → ref() ; useEffect → onMounted/watch ; useMemo → computed
// - lucide-react icons → <span class="material-symbols-outlined">icon_name</span>
// - createPortal → <teleport to="body"> (not used here)
// - keep ALL Tailwind classes and --color-* CSS variables VERBATIM
// - i18n key format: settings.memory.*
// - prop-driven leaf: no Pinia store imports for sub-components

import {
  computed,
  onMounted,
  onUnmounted,
  ref,
  watch,
} from 'vue'
import { memoryApi } from '../../api/memory'
import { formatBytes } from '../../lib/formatBytes'
import { useTranslation } from '../../i18n'
import { useSessionStore } from '../stores/sessionStore'
import { useUIStore } from '../stores/uiStore'
import type { MemoryFile, MemoryFileDetail, MemoryProject } from '../../types/memory'
import Button from '../components/shared/Button.vue'
import { MarkdownRenderer } from '../components/markdown/MarkdownRenderer'

// ─── Types ───────────────────────────────────────────────────────────────────

type MemoryTreeNode =
  | {
      kind: 'folder'
      id: string
      name: string
      path: string
      fileCount: number
      children: MemoryTreeNode[]
    }
  | {
      kind: 'file'
      id: string
      name: string
      path: string
      file: MemoryFile
    }

type MutableFolderNode = Extract<MemoryTreeNode, { kind: 'folder' }>

// ─── Constants ───────────────────────────────────────────────────────────────

const DEFAULT_MEMORY_PATH = 'MEMORY.md'

// ─── Reactive state ─────────────────────────────────────────────────────────

const t = useTranslation()

const sessionStore = useSessionStore()
const uiStore = useUIStore()

// Local state (mirrors React useState)
const resourceQuery = ref('')
const expandedProjectId = ref<string | null>(null)
const collapsedFolders = ref<Set<string>>(new Set())

// Data from API (mirrors store state)
const projects = ref<MemoryProject[]>([])
const files = ref<MemoryFile[]>([])
const selectedProjectId = ref<string | null>(null)
const selectedFile = ref<MemoryFileDetail | null>(null)
const draftContent = ref('')
const isLoadingProjects = ref(false)
const isLoadingFiles = ref(false)
const isLoadingFile = ref(false)
const isSaving = ref(false)
const error = ref<string | null>(null)
const lastSavedAt = ref<string | null>(null)

// Local UI state
const isEditing = ref(false)

// ─── Computed ────────────────────────────────────────────────────────────────

const activeSession = computed(() => {
  const sid = sessionStore.activeSessionId
  return sessionStore.sessions.find((s) => s.id === sid) ?? null
})

const activeCwd = computed(() => activeSession.value?.workDir || activeSession.value?.projectPath)

const selectedProject = computed(
  () => projects.value.find((p) => p.id === selectedProjectId.value) ?? null,
)

const isDirty = computed(
  () => Boolean(selectedFile.value && draftContent.value !== selectedFile.value?.content),
)

const filteredProjects = computed(() =>
  filterProjects(projects.value, resourceQuery.value, selectedProjectId.value, files.value),
)

const filteredFiles = computed(() => filterFiles(files.value, resourceQuery.value))

const fileTree = computed(() => buildMemoryFileTree(filteredFiles.value))

const previewContent = computed(() => stripMarkdownFrontmatter(draftContent.value))

const selectedFilePath = computed(() => selectedFile.value?.path ?? null)

const forceExpandFiles = computed(() => Boolean(resourceQuery.value.trim()))

// ─── API helpers ─────────────────────────────────────────────────────────────

async function fetchProjects(cwd?: string) {
  isLoadingProjects.value = true
  error.value = null
  try {
    const { projects: fetchedProjects } = await memoryApi.listProjects(cwd)
    const selectable = fetchedProjects.filter(canSelectMemoryProject)
    const current = selectable.find((p) => p.isCurrent)
    const prevId = selectedProjectId.value
    const newId =
      prevId && selectable.some((p) => p.id === prevId)
        ? prevId
        : current?.id ?? selectable[0]?.id ?? null
    projects.value = fetchedProjects
    selectedProjectId.value = newId
    isLoadingProjects.value = false
    if (newId !== prevId) {
      files.value = []
      selectedFile.value = null
      draftContent.value = ''
      lastSavedAt.value = null
    }
  } catch (err) {
    error.value = (err as Error).message
    isLoadingProjects.value = false
  }
}

function selectProject(projectId: string) {
  selectedProjectId.value = projectId
  files.value = []
  selectedFile.value = null
  draftContent.value = ''
  error.value = null
  lastSavedAt.value = null
}

async function fetchFiles(projectId: string) {
  isLoadingFiles.value = true
  error.value = null
  try {
    const { files: fetchedFiles } = await memoryApi.listFiles(projectId)
    const stillSelected =
      selectedFile.value && fetchedFiles.some((f) => f.path === selectedFile.value?.path)
    files.value = fetchedFiles
    selectedFile.value = stillSelected ? selectedFile.value : null
    draftContent.value = stillSelected ? draftContent.value : ''
    isLoadingFiles.value = false
  } catch (err) {
    error.value = (err as Error).message
    isLoadingFiles.value = false
  }
}

async function openFile(projectId: string, path: string) {
  isLoadingFile.value = true
  error.value = null
  try {
    const { file } = await memoryApi.readFile(projectId, path)
    selectedFile.value = file
    draftContent.value = file.content
    isLoadingFile.value = false
    lastSavedAt.value = null
  } catch (err) {
    error.value = (err as Error).message
    isLoadingFile.value = false
  }
}

function updateDraft(content: string) {
  draftContent.value = content
}

async function saveFile(): Promise<boolean> {
  if (!selectedProjectId.value || !selectedFile.value) return false
  isSaving.value = true
  error.value = null
  try {
    const { file } = await memoryApi.saveFile({
      projectId: selectedProjectId.value,
      path: selectedFile.value.path,
      content: draftContent.value,
    })
    selectedFile.value = {
      ...selectedFile.value,
      updatedAt: file.updatedAt,
      bytes: file.bytes,
      content: draftContent.value,
    } as MemoryFileDetail
    isSaving.value = false
    lastSavedAt.value = file.updatedAt
    await fetchFiles(selectedProjectId.value!)
    return true
  } catch (err) {
    error.value = (err as Error).message
    isSaving.value = false
    return false
  }
}

function canSelectMemoryProject(project: MemoryProject): boolean {
  return project.exists || project.fileCount > 0
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

// useEffect(() => { void fetchProjects(activeCwd) }, [activeCwd])
watch(activeCwd, (cwd) => {
  void fetchProjects(cwd)
}, { immediate: true })

// useEffect(() => { if (!selectedProjectId) return; void fetchFiles(selectedProjectId) }, [selectedProjectId])
watch(selectedProjectId, (id) => {
  if (!id) return
  void fetchFiles(id)
})

// useEffect(() => { if (!selectedProjectId) return; setExpandedProjectId(selectedProjectId) }, [selectedProjectId])
watch(selectedProjectId, (id) => {
  if (!id) return
  expandedProjectId.value = id
})

// useEffect(() => { setIsEditing(false) }, [selectedFilePath])
watch(selectedFilePath, () => {
  isEditing.value = false
})

// useEffect(() => {
//   if (!selectedProjectId || selectedFile || isLoadingFiles || isLoadingFile) return
//   if (pendingMemoryPath) return
//   const firstFile = files[0]
//   if (firstFile) { void openFile(selectedProjectId, firstFile.path) }
// }, [files, isLoadingFile, isLoadingFiles, openFile, pendingMemoryPath, selectedFile, selectedProjectId])
watch(
  [() => files.value.length, isLoadingFile, isLoadingFiles],
  ([, loadingFile, loadingFiles]) => {
    if (!selectedProjectId.value || selectedFile.value || loadingFiles || loadingFile) return
    const pm = uiStore.pendingMemoryPath
    if (pm) return
    const first = files.value[0]
    if (first) {
      void openFile(selectedProjectId.value, first.path)
    }
  },
)

// useEffect for pendingMemoryPath resolution
watch(
  [() => uiStore.pendingMemoryPath, isLoadingFile, isLoadingProjects, () => projects.value.length],
  ([pm, loadingFile, loadingProjects, projLen]) => {
    if (!pm || loadingProjects || projLen === 0) return
    const target = resolveMemoryFileTarget(projects.value, pm)
    if (!target) {
      uiStore.setPendingMemoryPath(null)
      return
    }
    if (selectedProjectId.value !== target.projectId) {
      selectProject(target.projectId)
      return
    }
    if (selectedFile.value?.path === target.path && !loadingFile) {
      uiStore.setPendingMemoryPath(null)
      return
    }
    void openFile(target.projectId, target.path).then(() => {
      uiStore.setPendingMemoryPath(null)
    })
  },
)

// ─── Event handlers ──────────────────────────────────────────────────────────

function canLeaveDirtyEdit(): boolean {
  if (!isEditing.value || !isDirty.value) return true
  return window.confirm(t('settings.memory.discardUnsavedConfirm'))
}

function handleRefresh() {
  if (!canLeaveDirtyEdit()) return
  void fetchProjects(activeCwd.value)
  if (selectedProjectId.value) {
    void fetchFiles(selectedProjectId.value)
  }
}

function handleProjectToggle(projectId: string) {
  if (expandedProjectId.value === projectId) {
    expandedProjectId.value = null
    return
  }
  if (projectId !== selectedProjectId.value && !canLeaveDirtyEdit()) return
  expandedProjectId.value = projectId
  if (projectId !== selectedProjectId.value) {
    selectProject(projectId)
  }
}

function handleFileOpen(file: MemoryFile) {
  if (!selectedProjectId.value || file.path === selectedFile.value?.path) return
  if (!canLeaveDirtyEdit()) return
  void openFile(selectedProjectId.value, file.path)
}

async function handleSave() {
  if (!selectedFile.value) return
  if (!isDirty.value) {
    isEditing.value = false
    return
  }
  const saved = await saveFile()
  if (saved) {
    isEditing.value = false
  }
}

// keyboard shortcut: Cmd/Ctrl+S
function handleKeyDown(event: KeyboardEvent) {
  if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 's') return
  event.preventDefault()
  void handleSave()
}

watch(isEditing, (val) => {
  if (val) {
    document.addEventListener('keydown', handleKeyDown)
  } else {
    document.removeEventListener('keydown', handleKeyDown)
  }
})

const handlePreviewLinkClick = (href: string): boolean => {
  if (!selectedProjectId.value || !selectedFile.value) return false
  const targetPath = resolveMarkdownMemoryLink(
    href,
    selectedFile.value.path,
    selectedProject.value?.memoryDir,
    files.value,
  )
  if (!targetPath || targetPath === selectedFile.value.path) return false
  if (!canLeaveDirtyEdit()) return true
  void openFile(selectedProjectId.value, targetPath)
  return true
}

function toggleFolder(path: string) {
  const next = new Set(collapsedFolders.value)
  if (next.has(path)) {
    next.delete(path)
  } else {
    next.add(path)
  }
  collapsedFolders.value = next
}

function handleCancelEdit() {
  if (selectedFile.value) {
    updateDraft(selectedFile.value.content)
  }
  isEditing.value = false
}

// ─── Utility functions ───────────────────────────────────────────────────────

function normalizeSearch(value: string): string {
  return value.toLowerCase().replace(/\\/g, '/').replace(/\/+/g, '/').trim()
}

function filterProjects(
  projects: MemoryProject[],
  query: string,
  selectedProjectId: string | null,
  selectedProjectFiles: MemoryFile[],
): MemoryProject[] {
  const normalized = normalizeSearch(query)
  if (!normalized) return projects
  return projects.filter((project) =>
    normalizeSearch(`${project.label} ${project.memoryDir} ${project.id}`).includes(normalized) ||
    (project.id === selectedProjectId &&
      selectedProjectFiles.some((file) =>
        normalizeSearch(
          `${file.title} ${file.path} ${file.description ?? ''} ${file.type ?? ''}`,
        ).includes(normalized),
      )),
  )
}

function filterFiles(files: MemoryFile[], query: string): MemoryFile[] {
  const normalized = normalizeSearch(query)
  if (!normalized) return files
  return files.filter((file) =>
    normalizeSearch(
      `${file.title} ${file.path} ${file.description ?? ''} ${file.type ?? ''}`,
    ).includes(normalized),
  )
}

function projectDisplayName(label: string): string {
  const normalized = label.replace(/\\/g, '/').replace(/\/+/g, '/').replace(/\/$/, '')
  const parts = normalized.split('/').filter(Boolean)
  if (parts.length >= 2) return `${parts[parts.length - 2]}/${parts[parts.length - 1]}`
  return parts[0] ?? label
}

function stripMarkdownFrontmatter(content: string): string {
  if (!content.startsWith('---')) return content
  const end = content.indexOf('\n---', 3)
  if (end < 0) return content
  const after = content.indexOf('\n', end + 4)
  return after < 0 ? '' : content.slice(after + 1).trimStart()
}

function normalizeFsPath(value: string): string {
  return value.replace(/\\/g, '/').replace(/\/+$/, '')
}

function resolveMemoryFileTarget(
  projects: MemoryProject[],
  absolutePath: string,
): { projectId: string; path: string } | null {
  const target = normalizeFsPath(absolutePath)
  for (const project of projects) {
    const memoryDir = normalizeFsPath(project.memoryDir)
    if (!memoryDir) continue
    if (target === memoryDir) {
      return { projectId: project.id, path: DEFAULT_MEMORY_PATH }
    }
    if (target.startsWith(`${memoryDir}/`)) {
      return {
        projectId: project.id,
        path: target.slice(memoryDir.length + 1),
      }
    }
  }
  return null
}

function resolveMarkdownMemoryLink(
  href: string,
  currentPath: string,
  projectMemoryDir: string | undefined,
  files: MemoryFile[],
): string | null {
  const rawHref = safeDecodeUriComponent(href.trim())
  if (!rawHref || rawHref.startsWith('#')) return null

  let target = rawHref
  try {
    const url = new URL(rawHref)
    if (url.protocol !== 'file:') return null
    target = url.pathname
  } catch {
    if (/^[a-z][a-z\d+.-]*:/i.test(rawHref)) return null
  }

  target = stripMarkdownLinkSuffix(target)
  if (!target || !target.endsWith('.md')) return null

  const absoluteTarget = normalizeFsPath(target)
  const memoryDir = projectMemoryDir ? normalizeFsPath(projectMemoryDir) : ''
  if (memoryDir) {
    if (absoluteTarget === memoryDir) return DEFAULT_MEMORY_PATH
    if (absoluteTarget.startsWith(`${memoryDir}/`)) {
      return findMemoryFileByPath(files, absoluteTarget.slice(memoryDir.length + 1))
    }
  }

  if (target.startsWith('/')) return null

  const currentParts = currentPath.split('/').filter(Boolean)
  const baseParts = currentParts.slice(0, -1)
  const resolvedParts: string[] = []
  for (const part of [...baseParts, ...target.split('/')]) {
    if (!part || part === '.') continue
    if (part === '..') {
      resolvedParts.pop()
      continue
    }
    resolvedParts.push(part)
  }

  return findMemoryFileByPath(files, resolvedParts.join('/'))
}

function safeDecodeUriComponent(value: string): string {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

function stripMarkdownLinkSuffix(value: string): string {
  return value.split('#')[0]?.split('?')[0]?.trim() ?? ''
}

function findMemoryFileByPath(files: MemoryFile[], path: string): string | null {
  const normalized = normalizeFsPath(path)
  return files.find((file) => normalizeFsPath(file.path) === normalized)?.path ?? null
}

function buildMemoryFileTree(files: MemoryFile[]): MemoryTreeNode[] {
  const root: MutableFolderNode = {
    kind: 'folder',
    id: '__root__',
    name: '__root__',
    path: '',
    fileCount: 0,
    children: [],
  }

  const folders = new Map<string, MutableFolderNode>([['', root]])
  for (const file of files) {
    const parts = file.path.split('/').filter(Boolean)
    let parent = root
    parts.slice(0, -1).forEach((part, index) => {
      const folderPath = parts.slice(0, index + 1).join('/')
      let folder = folders.get(folderPath)
      if (!folder) {
        folder = {
          kind: 'folder',
          id: `folder:${folderPath}`,
          name: part,
          path: folderPath,
          fileCount: 0,
          children: [],
        }
        folders.set(folderPath, folder)
        parent.children.push(folder)
      }
      folder.fileCount += 1
      parent = folder
    })
    parent.children.push({
      kind: 'file',
      id: `file:${file.path}`,
      name: parts[parts.length - 1] ?? file.name,
      path: file.path,
      file,
    })
  }

  sortMemoryTree(root.children)
  return root.children
}

function sortMemoryTree(nodes: MemoryTreeNode[]): void {
  nodes.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === 'folder' ? -1 : 1
    const aIndex = a.kind === 'file' ? a.file.isIndex : false
    const bIndex = b.kind === 'file' ? b.file.isIndex : false
    if (aIndex !== bIndex) return aIndex ? -1 : 1
    return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
  })
  for (const node of nodes) {
    if (node.kind === 'folder') sortMemoryTree(node.children)
  }
}

function fileNameFromPath(path: string): string {
  const parts = path.split('/').filter(Boolean)
  return parts[parts.length - 1] ?? path
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

// Lifecycle
onMounted(() => {
  void fetchProjects(activeCwd.value)
})
</script>

<template>
  <div
    class="flex h-full min-h-[640px] flex-col overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)]"
  >
    <!-- Header -->
    <header
      class="grid min-h-[58px] border-b border-[var(--color-border)] bg-[var(--color-surface-container-low)] lg:grid-cols-[280px_minmax(0,1fr)]"
    >
      <div
        class="flex min-w-0 items-center gap-3 border-b border-[var(--color-border)] px-4 py-3 lg:border-b-0 lg:border-r"
      >
        <span
          class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-brand)]"
        >
          <span class="material-symbols-outlined text-sm" aria-hidden="true">
            menu_book
          </span>
        </span>
        <div class="min-w-0">
          <h2 class="truncate text-base font-semibold text-[var(--color-text-primary)]">
            {{ t('settings.memory.title') }}
          </h2>
          <p class="truncate text-xs text-[var(--color-text-tertiary)]">
            {{ t('settings.memory.projects') }}
          </p>
        </div>
      </div>

      <div class="flex min-w-0 flex-wrap items-center justify-between gap-3 px-4 py-3">
        <!-- Breadcrumb -->
        <nav
          aria-label="Memory file path"
          class="flex min-w-0 items-center gap-1 text-sm text-[var(--color-text-tertiary)]"
        >
          <template v-for="(part, index) in breadcrumbParts" :key="`${part}-${index}`">
            <span class="flex min-w-0 items-center gap-1">
              <span
                v-if="index > 0"
                class="material-symbols-outlined text-sm shrink-0"
                aria-hidden="true"
              >
                chevron_right
              </span>
              <span
                :class="
                  index === breadcrumbParts.length - 1
                    ? 'truncate font-semibold text-[var(--color-text-primary)]'
                    : 'truncate'
                "
              >
                {{ part }}
              </span>
            </span>
          </template>
        </nav>

        <div class="flex shrink-0 flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            :loading="isLoadingProjects || isLoadingFiles"
            @click="handleRefresh"
          >
            <template #icon>
              <span class="material-symbols-outlined text-sm" aria-hidden="true">refresh</span>
            </template>
            {{ t('settings.memory.refresh') }}
          </Button>
        </div>
      </div>
    </header>

    <!-- Error -->
    <div
      v-if="error"
      class="m-3 rounded-[var(--radius-md)] border border-[var(--color-error)]/30 bg-[var(--color-error)]/10 px-3 py-2 text-sm text-[var(--color-error)]"
    >
      {{ error }}
    </div>

    <!-- Body: sidebar + content -->
    <div class="grid min-h-0 flex-1 lg:grid-cols-[280px_minmax(0,1fr)]">
      <!-- Sidebar -->
      <aside
        class="min-h-0 overflow-hidden border-b border-[var(--color-border)] lg:border-b-0 lg:border-r"
      >
        <section
          class="flex h-full min-h-0 flex-col bg-[var(--color-surface-container-lowest)]"
        >
          <!-- PanelHeader -->
          <div
            class="flex h-11 items-center justify-between border-b border-[var(--color-border)] px-3"
          >
            <h3
              class="flex min-w-0 items-center gap-2 text-sm font-semibold text-[var(--color-text-primary)]"
            >
              <span class="text-[var(--color-text-tertiary)]">
                <span class="material-symbols-outlined text-sm" aria-hidden="true">
                  storage
                </span>
              </span>
              <span class="truncate">{{ t('settings.memory.resourceManager') }}</span>
            </h3>
            <span v-if="isLoadingProjects" class="text-xs text-[var(--color-text-tertiary)]">
              {{ t('common.loading') }}
            </span>
          </div>

          <!-- SearchField -->
          <div class="px-3 py-3">
            <div class="relative">
              <span
                class="material-symbols-outlined text-sm pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-tertiary)]"
                aria-hidden="true"
              >
                search
              </span>
              <input
                :aria-label="t('settings.memory.resourceSearchPlaceholder')"
                :value="resourceQuery"
                @input="resourceQuery = ($event.target as HTMLInputElement).value"
                :placeholder="t('settings.memory.resourceSearchPlaceholder')"
                class="h-10 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] pl-9 pr-9 text-sm text-[var(--color-text-primary)] outline-none transition-colors duration-150 placeholder:text-[var(--color-text-tertiary)] focus:border-[var(--color-border-focus)] focus:shadow-[var(--shadow-focus-ring)]"
              />
              <button
                v-if="resourceQuery"
                type="button"
                :aria-label="t('settings.memory.clearSearch')"
                @click="resourceQuery = ''"
                class="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
              >
                <span class="material-symbols-outlined text-sm" aria-hidden="true">
                  close
                </span>
              </button>
            </div>
          </div>

          <!-- Projects tree -->
          <div class="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            <div v-if="projects.length === 0 && !isLoadingProjects">
              <EmptyStateIcon>
                <span class="material-symbols-outlined text-lg" aria-hidden="true">
                  folder_open
                </span>
              </EmptyStateIcon>
              <span>{{ t('settings.memory.emptyProjects') }}</span>
            </div>
            <div v-else-if="filteredProjects.length === 0">
              <EmptyStateIcon>
                <span class="material-symbols-outlined text-lg" aria-hidden="true">
                  search_off
                </span>
              </EmptyStateIcon>
              <span>{{ t('settings.memory.noProjectMatches') }}</span>
            </div>
            <div v-else class="py-1">
              <template v-for="project in filteredProjects" :key="project.id">
                <ProjectTreeRow
                  :project="project"
                  :expanded="project.id === expandedProjectId"
                  :active="project.id === selectedProjectId"
                  :loading="project.id === selectedProjectId && isLoadingFiles"
                  :file-tree="project.id === selectedProjectId ? fileTree : []"
                  :active-path="selectedFile?.path ?? null"
                  :collapsed-folders="collapsedFolders"
                  :force-expanded="forceExpandFiles"
                  :empty-text="t('settings.memory.emptyFiles')"
                  @toggle="handleProjectToggle(project.id)"
                  @toggle-folder="toggleFolder"
                  @file-select="handleFileOpen"
                />
              </template>
            </div>
          </div>
        </section>
      </aside>

      <!-- Content -->
      <section
        class="flex min-h-0 flex-col overflow-hidden bg-[var(--color-surface-container-lowest)]"
      >
        <!-- File title bar -->
        <div
          class="grid gap-3 border-b border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] px-4 py-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center"
        >
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <h3 class="truncate text-sm font-semibold text-[var(--color-text-primary)]">
                {{ selectedFile ? fileNameFromPath(selectedFile.path) : t('settings.memory.noFileSelected') }}
              </h3>
              <Badge v-if="isDirty">{{ t('settings.memory.unsaved') }}</Badge>
              <Badge v-else-if="lastSavedAt && !isDirty">{{ t('settings.memory.saved') }}</Badge>
            </div>
            <p class="mt-1 truncate text-xs text-[var(--color-text-tertiary)]">
              {{ selectedProject?.memoryDir ?? t('settings.memory.selectProject') }}
            </p>
          </div>
          <div
            class="flex shrink-0 items-center gap-2 text-xs text-[var(--color-text-tertiary)]"
          >
            <template v-if="selectedFile">
              <span>{{ formatBytes(selectedFile.bytes) }}</span>
              <span v-if="selectedFile.updatedAt">
                {{ formatDate(selectedFile.updatedAt) }}
              </span>
            </template>
          </div>
        </div>

        <!-- Editor / Preview / Empty -->
        <template v-if="selectedFile">
          <!-- Editing mode -->
          <div v-if="isEditing" class="flex min-h-0 flex-1 flex-col">
            <div
              class="flex h-10 shrink-0 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-3 text-xs font-medium uppercase tracking-normal text-[var(--color-text-tertiary)]"
            >
              <div class="flex min-w-0 items-center gap-2">
                <span>{{ t('settings.memory.editor') }}</span>
                <span>MARKDOWN</span>
              </div>
              <div class="flex shrink-0 items-center gap-2 normal-case">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  :disabled="isSaving"
                  @click="handleCancelEdit"
                >
                  {{ t('common.cancel') }}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  :disabled="!isDirty || isSaving"
                  @click="selectedFile && updateDraft(selectedFile.content)"
                >
                  <template #icon>
                    <span class="material-symbols-outlined text-sm" aria-hidden="true">
                      settings_backup_restore
                    </span>
                  </template>
                  {{ t('settings.memory.revert') }}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  :disabled="isSaving"
                  :loading="isSaving"
                  @click="handleSave"
                >
                  <template #icon>
                    <span class="material-symbols-outlined text-sm" aria-hidden="true">
                      save
                    </span>
                  </template>
                  {{ t('common.save') }}
                </Button>
              </div>
            </div>
            <textarea
              :aria-label="t('settings.memory.editor')"
              :value="draftContent"
              @input="updateDraft(($event.target as HTMLTextAreaElement).value)"
              spellcheck="false"
              class="min-h-0 flex-1 w-full resize-none overflow-auto bg-transparent p-5 font-mono text-[13px] leading-6 text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-tertiary)]"
            />
          </div>

          <!-- Preview mode -->
          <div v-else class="flex min-h-0 flex-1 flex-col overflow-hidden">
            <div
              class="flex h-10 shrink-0 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-3 text-xs font-medium uppercase tracking-normal text-[var(--color-text-tertiary)]"
            >
              <div class="flex min-w-0 items-center gap-2">
                <span>{{ t('settings.memory.preview') }}</span>
                <span>{{ t('settings.memory.rendered') }}</span>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                :aria-label="t('settings.memory.edit')"
                :title="t('settings.memory.edit')"
                @click="isEditing = true"
              >
                <template #icon>
                  <span class="material-symbols-outlined text-sm" aria-hidden="true">
                    edit
                  </span>
                </template>
              </Button>
            </div>
            <div class="min-h-0 flex-1 overflow-y-auto p-6">
              <MarkdownRenderer
                :content="previewContent || ' '"
                variant="document"
                @link-click="handlePreviewLinkClick"
              />
            </div>
          </div>
        </template>

        <!-- No file selected -->
        <div
          v-else
          class="flex min-h-0 flex-1 items-center justify-center p-8"
        >
          <EmptyStateIcon>
            <span class="material-symbols-outlined text-xl" aria-hidden="true">
              article
            </span>
          </EmptyStateIcon>
          <span>{{ isLoadingFile ? t('common.loading') : t('settings.memory.selectFile') }}</span>
        </div>
      </section>
    </div>
  </div>
</template>

<script lang="ts">
// ─── Sub-components (rendered via Vue component registration) ────────────────
// Using inline <script> + template blocks via defineComponent-style
// pattern isn't possible in <script setup>; instead, we define them as
// inline Vue components below and register them in the template via <template> refs.

// We use a simpler approach: render sub-components as template functions
// embedded via the `#` pattern isn't supported. Instead we use separate
// script blocks — but Vue SFC only supports ONE <script setup> block.
// Solution: define sub-components as Vue objects and use them in the template
// directly. The template above already references them (ProjectTreeRow, FileRow,
// MemoryTreeRow, EmptyStateIcon, Badge). We define them below.

import { defineComponent, h, type PropType } from 'vue'

// Register sub-components that the template above references:
// Badge, EmptyStateIcon, ProjectTreeRow, FileRow, MemoryTreeRow

const Badge = defineComponent({
  props: {
    children: { type: String, required: true },
  },
  setup(props) {
    return () =>
      h(
        'span',
        {
          class:
            'shrink-0 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--color-text-secondary)]',
        },
        props.children,
      )
  },
})

const EmptyStateIcon = defineComponent({
  setup(_props, { slots }) {
    return () =>
      h(
        'div',
        {
          class:
            'grid place-items-center gap-2 px-3 py-8 text-center text-sm text-[var(--color-text-tertiary)]',
        },
        [slots.default?.(), slots.text?.()],
      )
  },
})

// ProjectTreeRow
const ProjectTreeRow = defineComponent({
  props: {
    project: { type: Object as PropType<MemoryProject>, required: true },
    expanded: { type: Boolean, default: false },
    active: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
    fileTree: { type: Array as PropType<MemoryTreeNode[]>, default: () => [] },
    activePath: { type: String as PropType<string | null>, default: null },
    collapsedFolders: { type: Set as PropType<Set<string>>, default: () => new Set() },
    forceExpanded: { type: Boolean, default: false },
    emptyText: { type: String, required: true },
  },
  emits: ['toggle', 'toggle-folder', 'file-select'],
  setup(props, { emit }) {
    const display = projectDisplayName(props.project.label)
    return () =>
      h(
        'div',
        { class: 'mb-1' },
        [
          h(
            'button',
            {
              type: 'button',
              'data-testid': 'memory-project-row',
              onClick: () => emit('toggle'),
              title: props.project.label,
              'aria-expanded': props.expanded,
              'aria-label': t('settings.memory.toggleFolder', { name: display }),
              class: `group flex min-h-9 w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left transition-colors focus:outline-none focus-visible:shadow-[var(--shadow-focus-ring)] ${
                props.active
                  ? 'bg-[var(--color-memory-surface)] text-[var(--color-text-primary)] ring-1 ring-inset ring-[var(--color-memory-border)]'
                  : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]'
              }`,
            },
            [
              h('span', { class: 'material-symbols-outlined text-sm shrink-0 text-[var(--color-brand)]', 'aria-hidden': 'true' }, 'folder'),
              h('span', { class: 'min-w-0 flex-1 truncate text-sm font-medium' }, display),
              !props.project.exists
                ? h('span', { class: 'shrink-0 text-xs text-[var(--color-text-tertiary)]' }, t('settings.memory.missing'))
                : null,
            ],
          ),
          props.expanded
            ? h(
                'div',
                { class: 'ml-[18px] mt-1.5 border-l border-[var(--color-border)] pl-2.5' },
                props.loading
                  ? [h('div', { class: 'px-2 py-1.5 text-xs text-[var(--color-text-tertiary)]' }, t('common.loading'))]
                  : props.fileTree.length === 0
                    ? [h('div', { class: 'px-2 py-1.5 text-xs text-[var(--color-text-tertiary)]' }, props.emptyText)]
                    : props.fileTree.map((node) =>
                        h(MemoryTreeRow, {
                          key: node.id,
                          node,
                          depth: 1,
                          activePath: props.activePath,
                          collapsedFolders: props.collapsedFolders,
                          forceExpanded: props.forceExpanded,
                          onToggleFolder: (path: string) => emit('toggle-folder', path),
                          onFileSelect: (file: MemoryFile) => emit('file-select', file),
                        }),
                      ),
              )
            : null,
        ],
      )
  },
})

// FileRow
const FileRow = defineComponent({
  props: {
    file: { type: Object as PropType<MemoryFile>, required: true },
    active: { type: Boolean, default: false },
    depth: { type: Number, default: 0 },
  },
  emits: ['select'],
  setup(props, { emit }) {
    return () =>
      h(
        'button',
        {
          type: 'button',
          onClick: () => emit('select'),
          style: { paddingLeft: `${4 + Math.max(props.depth - 1, 0) * 16}px` },
          class: `mb-1 flex min-h-8 w-full items-center gap-1.5 rounded-md border py-1 pr-2 text-left transition-colors focus:outline-none focus-visible:shadow-[var(--shadow-focus-ring)] ${
            props.active
              ? 'border-[var(--color-memory-border)] bg-[var(--color-surface-selected)] text-[var(--color-text-primary)]'
              : 'border-transparent text-[var(--color-text-secondary)] hover:border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]'
          }`,
        },
        [
          h('span', { class: 'material-symbols-outlined text-sm shrink-0 text-[var(--color-text-tertiary)]', 'aria-hidden': 'true' }, 'article'),
          h('span', { class: 'min-w-0 flex-1 truncate text-sm' }, props.file.title),
        ],
      )
  },
})

// MemoryTreeRow
const MemoryTreeRow = defineComponent({
  props: {
    node: { type: Object as PropType<MemoryTreeNode>, required: true },
    depth: { type: Number, required: true },
    activePath: { type: String as PropType<string | null>, default: null },
    collapsedFolders: { type: Set as PropType<Set<string>>, default: () => new Set() },
    forceExpanded: { type: Boolean, default: false },
  },
  emits: ['toggle-folder', 'file-select'],
  setup(props, { emit }) {
    return () => {
      if (props.node.kind === 'file') {
        return h(FileRow, {
          file: props.node.file,
          active: props.node.file.path === props.activePath,
          depth: props.depth,
          onSelect: () => emit('file-select', props.node.file),
        })
      }

      const isCollapsed = !props.forceExpanded && props.collapsedFolders.has(props.node.path)
      return h(
        'div',
        null,
        [
          h(
            'button',
            {
              type: 'button',
              onClick: () => emit('toggle-folder', props.node.path),
              'aria-expanded': !isCollapsed,
              'aria-label': t('settings.memory.toggleFolder', { name: props.node.name }),
              class:
                'mb-1 flex min-h-8 w-full items-center gap-1.5 rounded-md border border-transparent py-1 pr-2 text-left text-sm text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus:outline-none focus-visible:shadow-[var(--shadow-focus-ring)]',
              style: { paddingLeft: `${4 + Math.max(props.depth - 1, 0) * 16}px` },
            },
            [
              h(
                'span',
                { class: 'material-symbols-outlined text-sm', 'aria-hidden': 'true' },
                isCollapsed ? 'chevron_right' : 'expand_more',
              ),
              h('span', { class: 'material-symbols-outlined text-sm shrink-0 text-[var(--color-brand)]', 'aria-hidden': 'true' }, 'folder'),
              h('span', { class: 'min-w-0 flex-1 truncate font-medium' }, props.node.name),
            ],
          ),
          !isCollapsed
            ? h(
                'div',
                { class: 'ml-[18px] mt-1 border-l border-[var(--color-border)] pl-2.5' },
                (props.node as MutableFolderNode).children.map((child) =>
                  h(MemoryTreeRow, {
                    key: child.id,
                    node: child,
                    depth: props.depth + 1,
                    activePath: props.activePath,
                    collapsedFolders: props.collapsedFolders,
                    forceExpanded: props.forceExpanded,
                    onToggleFolder: (path: string) => emit('toggle-folder', path),
                    onFileSelect: (file: MemoryFile) => emit('file-select', file),
                  }),
                ),
              )
            : null,
        ],
      )
    }
  },
})

// Expose to template (Vue 3 SFC: components defined in <script setup> auto-register)
</script>

<script setup lang="ts">
// Computed: breadcrumb parts
const breadcrumbParts = computed(() => {
  const projectLabel = selectedProject.value ? projectDisplayName(selectedProject.value.label) : ''
  const filePath = selectedFile.value?.path
  const parts = filePath
    ? [projectLabel, ...filePath.split('/').filter(Boolean)]
    : [projectLabel || (activeCwd.value ? projectDisplayName(activeCwd.value) : '~/.claude/projects'), t('settings.memory.noFileSelected')]
  return parts
})
</script>