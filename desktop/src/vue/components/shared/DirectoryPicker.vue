<script setup lang="ts">
/**
 * DirectoryPicker — Vue 3 port of components/shared/DirectoryPicker.tsx
 * Project/directory selector with recent-projects list, desktop folder dialog,
 * and web directory browser. Teleport replaces createPortal.
 */
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { sessionsApi, type RecentProject } from '../../api/sessions'
import { filesystemApi } from '../../api/filesystem'
import { useTranslation } from '../../i18n'
import { getDesktopHost } from '../../lib/desktopHost'
import MobileBottomSheet from './MobileBottomSheet.vue'

interface Props {
  value: string
  onChange?: (path: string) => void
  variant?: 'chip' | 'workbar'
  isGitProject?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'chip',
  isGitProject: false,
})

const emit = defineEmits<{
  (e: 'update:value', path: string): void
  (e: 'change', path: string): void
}>()

// ─── Reactive state ────────────────────────────────────────────────
const isOpen = ref(false)
const mode = ref<'recent' | 'browse'>('recent')
const projects = ref<RecentProject[]>([])
const browseEntries = ref<any[]>([])
const browsePath = ref('')
const browseParent = ref('')
const loading = ref(false)
const dropdownPos = ref<{ top: number; left: number; width: number; direction: 'up' | 'down' } | null>(null)

const ref = ref<HTMLDivElement | null>(null)
const triggerRef = ref<HTMLButtonElement | null>(null)
const dropdownRef = ref<HTMLDivElement | null>(null)

// ─── i18n ──────────────────────────────────────────────────────────
const t = useTranslation()

// ─── Mobile detection (ported from useMobileViewport hook) ──────────
const MOBILE_VIEWPORT_QUERY = '(max-width: 767px)'
const isMobileBrowser = ref(false)

function getInitialMobileViewport() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia(MOBILE_VIEWPORT_QUERY).matches
}

let mobileMediaQuery: MediaQueryList | null = null
function handleMobileChange(event: MediaQueryListEvent | MediaQueryList) {
  isMobileBrowser.value = (event as MediaQueryListEvent).matches ?? event.matches
}

if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
  isMobileBrowser.value = getInitialMobileViewport()
  mobileMediaQuery = window.matchMedia(MOBILE_VIEWPORT_QUERY)
  if (typeof mobileMediaQuery.addEventListener === 'function') {
    mobileMediaQuery.addEventListener('change', handleMobileChange)
  } else {
    mobileMediaQuery.addListener(handleMobileChange as any)
  }
}

function isDesktopRuntime() {
  return typeof window !== 'undefined' && getDesktopHost().isDesktop
}

// ─── Constants ─────────────────────────────────────────────────────
const DESKTOP_WORKTREE_MARKER = '/.madcop/worktrees/'
const DROPDOWN_WIDTH = 400
const DROPDOWN_VIEWPORT_MARGIN = 12
const DROPDOWN_HEIGHT = 380
const CACHE_TTL = 30_000

// ─── Module-level cache (persists across renders) ──────────────────
let cachedProjects: RecentProject[] | null = null
let cacheTimestamp = 0

// ─── Helper functions ──────────────────────────────────────────────
function projectNameFromPath(filePath: string) {
  const displayRoot = filePath.includes(DESKTOP_WORKTREE_MARKER)
    ? filePath.slice(0, filePath.indexOf(DESKTOP_WORKTREE_MARKER))
    : filePath
  return displayRoot.split('/').filter(Boolean).pop() || filePath
}

// ─── Dropdown positioning ──────────────────────────────────────────
function updateDropdownPos() {
  if (!triggerRef.value) return
  const rect = triggerRef.value.getBoundingClientRect()
  const spaceAbove = rect.top
  const spaceBelow = window.innerHeight - rect.bottom
  const direction = spaceBelow >= DROPDOWN_HEIGHT || spaceBelow >= spaceAbove ? 'down' : 'up'
  const width = Math.min(DROPDOWN_WIDTH, Math.max(0, window.innerWidth - DROPDOWN_VIEWPORT_MARGIN * 2))
  const maxLeft = Math.max(DROPDOWN_VIEWPORT_MARGIN, window.innerWidth - width - DROPDOWN_VIEWPORT_MARGIN)
  const left = Math.min(Math.max(rect.left, DROPDOWN_VIEWPORT_MARGIN), maxLeft)
  dropdownPos.value = {
    top: direction === 'down' ? rect.bottom + 4 : rect.top - 4,
    left,
    width,
    direction,
  }
}

// ─── Close on outside click ────────────────────────────────────────
function handleClick(e: MouseEvent) {
  if (!isOpen.value) return
  const target = e.target as Node
  if (ref.value?.contains(target)) return
  if (dropdownRef.value?.contains(target)) return
  isOpen.value = false
}

// ─── Lifecycle ─────────────────────────────────────────────────────
onMounted(() => {
  document.addEventListener('mousedown', handleClick)
  if (typeof window !== 'undefined') {
    window.addEventListener('scroll', updateDropdownPos, true)
    window.addEventListener('resize', updateDropdownPos)
  }
})

onUnmounted(() => {
  document.removeEventListener('mousedown', handleClick)
  if (mobileMediaQuery && typeof window !== 'undefined') {
    if (typeof mobileMediaQuery.removeEventListener === 'function') {
      mobileMediaQuery.removeEventListener('change', handleMobileChange)
    } else {
      mobileMediaQuery.removeListener(handleMobileChange as any)
    }
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener('scroll', updateDropdownPos, true)
    window.removeEventListener('resize', updateDropdownPos)
  }
})

// ─── Update dropdown position when open changes ────────────────────
watch(isOpen, (open) => {
  if (open) {
    updateDropdownPos()
  }
})

// ─── Load recent projects ──────────────────────────────────────────
watch(
  [isOpen, mode],
  ([open, currentMode]) => {
    if (!open || currentMode !== 'recent') return
    if (cachedProjects && Date.now() - cacheTimestamp < CACHE_TTL) {
      projects.value = cachedProjects
      return
    }
    loading.value = true
    sessionsApi.getRecentProjects()
      .then(({ projects: p }) => {
        cachedProjects = p
        cacheTimestamp = Date.now()
        projects.value = p
      })
      .catch(() => {
        projects.value = []
      })
      .finally(() => {
        loading.value = false
      })
  },
  { immediate: true },
)

// ─── Browse directory ──────────────────────────────────────────────
async function loadBrowseDir(path?: string) {
  loading.value = true
  try {
    const result = await filesystemApi.browse(path)
    browsePath.value = result.currentPath
    browseParent.value = result.parentPath
    browseEntries.value = result.entries
  } catch {
    /* API not available */
  }
  loading.value = false
}

// ─── Selection ─────────────────────────────────────────────────────
function handleSelect(path: string) {
  onChange(path)
  isOpen.value = false
  mode.value = 'recent'
  cachedProjects = null
}

function onChange(path: string) {
  emit('update:value', path)
  emit('change', path)
}

// ─── Choose folder ─────────────────────────────────────────────────
async function handleChooseFolder() {
  const host = getDesktopHost()
  if (host.isDesktop && host.capabilities.dialogs) {
    isOpen.value = false
    try {
      const selected = await host.dialogs.open({
        directory: true,
        multiple: false,
        title: t('dirPicker.chooseProjectFolder'),
      })
      if (typeof selected === 'string' && selected.length > 0) onChange(selected)
    } catch (err) {
      console.error('[DirectoryPicker] Failed to open folder dialog:', err)
    }
  } else {
    mode.value = 'browse'
    loadBrowseDir(props.value || undefined)
  }
}

// ─── Derived values ────────────────────────────────────────────────
const selectedProject = computed(() => projects.value.find((p) => p.realPath === props.value))
const isWorkbar = computed(() => props.variant === 'workbar')
const selectedLabel = computed(() => selectedProject.value?.repoName || selectedProject.value?.projectName || projectNameFromPath(props.value))
const showGitIcon = computed(() => selectedProject.value?.isGit || props.isGitProject)

const dropdownClassName = 'overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] shadow-[var(--shadow-dropdown)]'

const dropdownStyle = computed(() => {
  if (!dropdownPos.value) return {}
  return {
    position: 'fixed' as const,
    left: dropdownPos.value.left,
    width: dropdownPos.value.width,
    ...(dropdownPos.value.direction === 'down'
      ? { top: dropdownPos.value.top }
      : { bottom: window.innerHeight - (dropdownPos.value.top ?? 0) }),
    zIndex: 9999,
  }
})

const dropdownTitle = computed(() => (mode.value === 'recent' ? t('dirPicker.recent') : t('dirPicker.chooseProjectFolder')))
</script>

<template>
  <div
    ref="ref"
    :class="isWorkbar ? `relative min-w-0 ${isMobileBrowser ? 'flex-1' : 'max-w-[320px] shrink'}` : 'relative'"
  >
    <!-- Trigger — shows selected project chip or placeholder -->
    <button
      v-if="value"
      ref="triggerRef"
      @click="() => { isOpen = !isOpen; mode = 'recent' }"
      :class="isWorkbar
        ? 'inline-flex h-9 max-w-full min-w-0 items-center gap-1.5 rounded-[7px] border border-transparent px-2.5 text-[13px] font-medium leading-none text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-container-lowest)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/35'
        : 'flex items-center gap-2 px-3 py-1.5 bg-[var(--color-surface-container-low)] hover:bg-[var(--color-surface-hover)] rounded-full text-xs transition-colors border border-[var(--color-border)]'"
      :title="value"
    >
      <!-- Git icon -->
      <svg
        v-if="showGitIcon"
        width="15"
        height="15"
        viewBox="0 0 16 16"
        fill="currentColor"
        class="shrink-0 text-[var(--color-text-secondary)]"
      >
        <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.20.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2.20.27 1.53-1.04 2.20-.82 2.20-.82.44 1.10.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.20 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
      </svg>
      <!-- Folder icon -->
      <span
        v-else
        class="material-symbols-outlined shrink-0 text-[var(--color-text-secondary)]"
        :class="isWorkbar ? 'text-[17px]' : 'text-[14px]'"
      >folder</span>
      <span class="min-w-0 flex-1 truncate text-[var(--color-text-primary)]">
        {{ selectedLabel }}
      </span>
      <span
        class="material-symbols-outlined shrink-0 text-[var(--color-text-tertiary)]"
        :class="isWorkbar ? 'text-[15px]' : 'text-[12px]'"
      >expand_more</span>
    </button>

    <!-- Empty trigger -->
    <button
      v-else
      ref="triggerRef"
      @click="() => { isOpen = !isOpen; mode = 'recent' }"
      :class="isWorkbar
        ? 'flex h-9 min-w-0 items-center gap-1.5 rounded-[7px] border border-transparent px-2.5 text-[13px] font-medium leading-none text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-container-lowest)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/35'
        : 'flex items-center gap-2 text-xs text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] transition-colors'"
      :title="t('dirPicker.selectProject')"
    >
      <span
        class="material-symbols-outlined shrink-0"
        :class="isWorkbar ? 'text-[17px]' : 'text-[14px]'"
      >folder_open</span>
      <span class="min-w-0 truncate">{{ t('dirPicker.selectProject') }}</span>
    </button>

    <!-- Dropdown / Bottom sheet -->
    <template v-if="isOpen && dropdownPos">
      <!-- Mobile: bottom sheet -->
      <MobileBottomSheet
        v-if="isMobileBrowser"
        :open="isOpen"
        @close="isOpen = false"
        :title="dropdownTitle"
        :closeLabel="t('tabs.close')"
      >
        <!-- Recent mode -->
        <template v-if="mode === 'recent'">
          <div v-if="!isMobileBrowser" class="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--color-outline)]">
            {{ t('dirPicker.recent') }}
          </div>
          <div :class="isMobileBrowser ? '' : 'max-h-[300px]' + ' overflow-y-auto'">
            <div v-if="loading" class="px-4 py-6 text-center text-xs text-[var(--color-text-tertiary)]">{{ t('common.loading') }}</div>
            <div v-else-if="projects.length === 0" class="px-4 py-6 text-center text-xs text-[var(--color-text-tertiary)]">{{ t('dirPicker.noRecent') }}</div>
            <button
              v-for="project in projects"
              :key="project.projectPath"
              @click="() => handleSelect(project.realPath)"
              :class="[
                'flex w-full items-center gap-3 px-4 text-left transition-colors hover:bg-[var(--color-surface-hover)]',
                isMobileBrowser ? 'min-h-[72px] py-3.5' : 'py-3',
                { 'bg-[var(--color-surface-selected)]': project.realPath === value },
              ]"
            >
              <!-- Git icon -->
              <svg
                v-if="project.isGit"
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="var(--color-text-secondary)"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
                class="flex-shrink-0"
              >
                <circle cx="18" cy="18" r="3" />
                <circle cx="6" cy="6" r="3" />
                <path d="M13 6h3a2 2 0 0 1 2 2v7" />
                <line x1="6" y1="9" x2="6" y2="21" />
              </svg>
              <span
                v-else
                class="material-symbols-outlined flex-shrink-0 text-[20px] text-[var(--color-text-secondary)]"
              >folder</span>
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm font-semibold text-[var(--color-text-primary)]">
                  {{ project.repoName || project.projectName }}
                </div>
                <div class="truncate font-[var(--font-mono)] text-[11px] text-[var(--color-text-tertiary)]">
                  {{ project.realPath }}
                </div>
              </div>
              <span
                v-if="project.realPath === value"
                class="material-symbols-outlined flex-shrink-0 text-[18px] text-[var(--color-brand)]"
                style="fontVariationSettings: 'FILL' 1"
              >check</span>
            </button>
          </div>
          <div class="border-t border-[var(--color-border)]">
            <button
              @click="handleChooseFolder"
              class="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--color-surface-hover)]"
            >
              <span class="material-symbols-outlined text-[20px] text-[var(--color-text-tertiary)]">create_new_folder</span>
              <span class="text-sm text-[var(--color-text-secondary)]">{{ t('dirPicker.chooseFolder') }}</span>
            </button>
          </div>
        </template>

        <!-- Browse mode -->
        <template v-else>
          <div class="flex flex-wrap items-center gap-1 border-b border-[var(--color-border)] px-3 py-2">
            <button
              @click="mode = 'recent'"
              class="mr-2 text-xs text-[var(--color-text-accent)] hover:underline"
            >← {{ t('dirPicker.recent') }}</button>
            <button
              @click="() => loadBrowseDir('/')"
              class="text-[10px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)]"
            >/</button>
            <span
              v-for="(seg, i) in browsePath.split('/').filter(Boolean)"
              :key="i"
              class="flex items-center gap-1"
            >
              <span class="text-[10px] text-[var(--color-text-tertiary)]">/</span>
              <button
                @click="() => loadBrowseDir('/' + browsePath.split('/').filter(Boolean).slice(0, i + 1).join('/'))"
                class="text-[10px] text-[var(--color-text-accent)] hover:underline"
              >{{ seg }}</button>
            </span>
          </div>

          <div :class="isMobileBrowser ? '' : 'max-h-[240px]' + ' overflow-y-auto'">
            <div v-if="loading" class="px-3 py-4 text-center text-xs text-[var(--color-text-tertiary)]">{{ t('common.loading') }}</div>
            <template v-else>
              <button
                v-if="browseParent && browseParent !== browsePath"
                @click="() => loadBrowseDir(browseParent)"
                class="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-[var(--color-surface-hover)]"
              >
                <span class="material-symbols-outlined text-[16px] text-[var(--color-text-tertiary)]">arrow_upward</span>
                <span class="text-xs text-[var(--color-text-secondary)]">..</span>
              </button>
              <div v-if="browseEntries.length === 0" class="px-3 py-4 text-center text-xs text-[var(--color-text-tertiary)]">{{ t('dirPicker.noSubdirs') }}</div>
              <div
                v-for="entry in browseEntries"
                :key="entry.path"
                class="flex w-full items-center gap-2 px-3 py-2 hover:bg-[var(--color-surface-hover)]"
              >
                <button
                  type="button"
                  @click="() => loadBrowseDir(entry.path)"
                  class="flex min-w-0 flex-1 items-center gap-2 text-left"
                >
                  <span class="material-symbols-outlined text-[16px] text-[var(--color-text-tertiary)]">folder</span>
                  <span class="min-w-0 flex-1 truncate text-xs text-[var(--color-text-primary)]">{{ entry.name }}</span>
                </button>
                <button
                  type="button"
                  @click="() => handleSelect(entry.path)"
                  class="rounded px-2 py-0.5 text-[10px] font-semibold text-[var(--color-brand)] transition-colors hover:bg-[var(--color-primary-fixed)]"
                >
                  {{ t('common.select') }}
                </button>
              </div>
            </template>
          </div>

          <div class="flex items-center justify-between border-t border-[var(--color-border)] px-3 py-2">
            <span class="truncate font-[var(--font-mono)] text-[10px] text-[var(--color-text-tertiary)]">{{ browsePath }}</span>
            <button
              @click="() => handleSelect(browsePath)"
              class="rounded-lg bg-[var(--color-brand)] px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90"
            >
              {{ t('dirPicker.useThisFolder') }}
            </button>
          </div>
        </template>
      </MobileBottomSheet>

      <!-- Desktop: fixed dropdown portal -->
      <Teleport v-else to="body">
        <div
          ref="dropdownRef"
          data-testid="directory-picker-menu"
          :class="dropdownClassName"
          :style="dropdownStyle"
        >
          <!-- Recent mode -->
          <template v-if="mode === 'recent'">
            <div class="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--color-outline)]">
              {{ t('dirPicker.recent') }}
            </div>
            <div class="max-h-[300px] overflow-y-auto">
              <div v-if="loading" class="px-4 py-6 text-center text-xs text-[var(--color-text-tertiary)]">{{ t('common.loading') }}</div>
              <div v-else-if="projects.length === 0" class="px-4 py-6 text-center text-xs text-[var(--color-text-tertiary)]">{{ t('dirPicker.noRecent') }}</div>
              <button
                v-for="project in projects"
                :key="project.projectPath"
                @click="() => handleSelect(project.realPath)"
                :class="[
                  'flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--color-surface-hover)]',
                  { 'bg-[var(--color-surface-selected)]': project.realPath === value },
                ]"
              >
                <svg
                  v-if="project.isGit"
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="var(--color-text-secondary)"
                  stroke-width="1.5"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  class="flex-shrink-0"
                >
                  <circle cx="18" cy="18" r="3" />
                  <circle cx="6" cy="6" r="3" />
                  <path d="M13 6h3a2 2 0 0 1 2 2v7" />
                  <line x1="6" y1="9" x2="6" y2="21" />
                </svg>
                <span
                  v-else
                  class="material-symbols-outlined flex-shrink-0 text-[20px] text-[var(--color-text-secondary)]"
                >folder</span>
                <div class="min-w-0 flex-1">
                  <div class="truncate text-sm font-semibold text-[var(--color-text-primary)]">
                    {{ project.repoName || project.projectName }}
                  </div>
                  <div class="truncate font-[var(--font-mono)] text-[11px] text-[var(--color-text-tertiary)]">
                    {{ project.realPath }}
                  </div>
                </div>
                <span
                  v-if="project.realPath === value"
                  class="material-symbols-outlined flex-shrink-0 text-[18px] text-[var(--color-brand)]"
                  style="fontVariationSettings: 'FILL' 1"
                >check</span>
              </button>
            </div>
            <div class="border-t border-[var(--color-border)]">
              <button
                @click="handleChooseFolder"
                class="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--color-surface-hover)]"
              >
                <span class="material-symbols-outlined text-[20px] text-[var(--color-text-tertiary)]">create_new_folder</span>
                <span class="text-sm text-[var(--color-text-secondary)]">{{ t('dirPicker.chooseFolder') }}</span>
              </button>
            </div>
          </template>

          <!-- Browse mode -->
          <template v-else>
            <div class="flex flex-wrap items-center gap-1 border-b border-[var(--color-border)] px-3 py-2">
              <button
                @click="mode = 'recent'"
                class="mr-2 text-xs text-[var(--color-text-accent)] hover:underline"
              >← {{ t('dirPicker.recent') }}</button>
              <button
                @click="() => loadBrowseDir('/')"
                class="text-[10px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)]"
              >/</button>
              <span
                v-for="(seg, i) in browsePath.split('/').filter(Boolean)"
                :key="i"
                class="flex items-center gap-1"
              >
                <span class="text-[10px] text-[var(--color-text-tertiary)]">/</span>
                <button
                  @click="() => loadBrowseDir('/' + browsePath.split('/').filter(Boolean).slice(0, i + 1).join('/'))"
                  class="text-[10px] text-[var(--color-text-accent)] hover:underline"
                >{{ seg }}</button>
              </span>
            </div>

            <div class="max-h-[240px] overflow-y-auto">
              <div v-if="loading" class="px-3 py-4 text-center text-xs text-[var(--color-text-tertiary)]">{{ t('common.loading') }}</div>
              <template v-else>
                <button
                  v-if="browseParent && browseParent !== browsePath"
                  @click="() => loadBrowseDir(browseParent)"
                  class="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-[var(--color-surface-hover)]"
                >
                  <span class="material-symbols-outlined text-[16px] text-[var(--color-text-tertiary)]">arrow_upward</span>
                  <span class="text-xs text-[var(--color-text-secondary)]">..</span>
                </button>
                <div v-if="browseEntries.length === 0" class="px-3 py-4 text-center text-xs text-[var(--color-text-tertiary)]">{{ t('dirPicker.noSubdirs') }}</div>
                <div
                  v-for="entry in browseEntries"
                  :key="entry.path"
                  class="flex w-full items-center gap-2 px-3 py-2 hover:bg-[var(--color-surface-hover)]"
                >
                  <button
                    type="button"
                    @click="() => loadBrowseDir(entry.path)"
                    class="flex min-w-0 flex-1 items-center gap-2 text-left"
                  >
                    <span class="material-symbols-outlined text-[16px] text-[var(--color-text-tertiary)]">folder</span>
                    <span class="min-w-0 flex-1 truncate text-xs text-[var(--color-text-primary)]">{{ entry.name }}</span>
                  </button>
                  <button
                    type="button"
                    @click="() => handleSelect(entry.path)"
                    class="rounded px-2 py-0.5 text-[10px] font-semibold text-[var(--color-brand)] transition-colors hover:bg-[var(--color-primary-fixed)]"
                  >
                    {{ t('common.select') }}
                  </button>
                </div>
              </template>
            </div>

            <div class="flex items-center justify-between border-t border-[var(--color-border)] px-3 py-2">
              <span class="truncate font-[var(--font-mono)] text-[10px] text-[var(--color-text-tertiary)]">{{ browsePath }}</span>
              <button
                @click="() => handleSelect(browsePath)"
                class="rounded-lg bg-[var(--color-brand)] px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90"
              >
                {{ t('dirPicker.useThisFolder') }}
              </button>
            </div>
          </template>
        </div>
      </Teleport>
    </template>
  </div>
</template>
