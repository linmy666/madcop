<script setup lang="ts">
/**
 * RepositoryLaunchControls — Vue 3 port of shared/RepositoryLaunchControls.tsx
 * Full translation: workDir + DirectoryPicker, branch dropdown (search + keyboard nav),
 * worktree toggle dropdown, status/warning messages, mobile bottom sheet fallback.
 * Props use direct onChange callbacks (matches parent usage).
 * Icons: lucide-react → Material Symbols Outlined.
 * createPortal → <Teleport to="body">.
 */
import { ref, onMounted, onUnmounted, watch, computed, useId } from 'vue'
import { sessionsApi, type RepositoryBranchInfo, type RepositoryContextResult } from '../../../api/sessions'
import { useTranslation } from '../../i18n'
import DirectoryPicker from './DirectoryPicker.vue'
import MobileBottomSheet from './MobileBottomSheet.vue'
import { getDesktopHost } from '../../lib/desktopHost'

// ─── Props / Emits ──────────────────────────────────────────────────
interface Props {
  workDir: string
  onWorkDirChange: (path: string) => void
  branch: string | null
  onBranchChange: (branch: string | null) => void
  useWorktree: boolean
  onUseWorktreeChange: (enabled: boolean) => void
  disabled?: boolean
  placement?: 'standalone' | 'composer'
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  placement: 'standalone',
})

const emit = defineEmits<{
  workDirChange: [path: string]
  branchChange: [branch: string | null]
  useWorktreeChange: [enabled: boolean]
  launchReadyChange: [ready: boolean]
}>()

// ─── i18n ──────────────────────────────────────────────────────────
const t = useTranslation()

// ─── Accessibility IDs (useId from Vue 3.2+) ───────────────────────
const searchInputId = useId()
const listboxId = useId()
const worktreeListboxId = useId()

// ─── Mobile detection (ported from useMobileViewport hook) ──────────
const MOBILE_VIEWPORT_QUERY = '(max-width: 767px)'
const isMobileBrowser = ref(false)
let mobileMediaQuery: MediaQueryList | null = null

function getInitialMobileViewport(): boolean {
  try {
    return window.matchMedia(MOBILE_VIEWPORT_QUERY).matches
  } catch {
    return false
  }
}

function handleMobileChange(e: MediaQueryListEvent) {
  isMobileBrowser.value = e.matches
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

const isComposerPlacement = computed(
  () => props.placement === 'composer' && !isMobileBrowser.value
)

// ─── Constants ─────────────────────────────────────────────────────
const BRANCH_MENU_HEIGHT = 360
const BRANCH_MENU_WIDTH = 390
const WORKTREE_MENU_HEIGHT = 126
const WORKTREE_MENU_WIDTH = 226
const VIEWPORT_GUTTER = 12

// ─── Reactive state ────────────────────────────────────────────────
const context = ref<RepositoryContextResult | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const branchMenuOpen = ref(false)
const branchFilter = ref('')
const selectedIndex = ref(0)
const menuPos = ref<{ top: number; left: number; direction: 'up' | 'down' } | null>(null)
const worktreeMenuOpen = ref(false)
const worktreeMenuPos = ref<{ top: number; left: number; direction: 'up' | 'down' } | null>(null)

const rootRef = ref<HTMLDivElement | null>(null)
const branchButtonRef = ref<HTMLButtonElement | null>(null)
const worktreeButtonRef = ref<HTMLButtonElement | null>(null)
const menuRef = ref<HTMLDivElement | null>(null)
const worktreeMenuRef = ref<HTMLDivElement | null>(null)
const searchRef = ref<HTMLInputElement | null>(null)
const itemRefs = ref<(HTMLButtonElement | null)[]>([])

// ─── Helper: stateMessage (moved out of render) ────────────────────
function stateMessage(ctx: RepositoryContextResult | null, err: string | null) {
  if (err) return err
  if (!ctx) return null
  if (ctx.state === 'not_git_repo') return null
  if (ctx.state === 'missing_workdir') return 'missing'
  if (ctx.state === 'error') return ctx.error || 'error'
  return null
}

// ─── Menu positioning ──────────────────────────────────────────────
function updateMenuPos() {
  if (!branchButtonRef.value) return
  const rect = branchButtonRef.value.getBoundingClientRect()
  const spaceAbove = rect.top
  const spaceBelow = window.innerHeight - rect.bottom
  const direction = spaceBelow >= BRANCH_MENU_HEIGHT || spaceBelow >= spaceAbove ? 'down' : 'up'
  const maxLeft = Math.max(VIEWPORT_GUTTER, window.innerWidth - BRANCH_MENU_WIDTH - VIEWPORT_GUTTER)
  menuPos.value = {
    top: direction === 'down' ? rect.bottom + 6 : rect.top - 6,
    left: Math.min(Math.max(rect.left, VIEWPORT_GUTTER), maxLeft),
    direction,
  }
}

function updateWorktreeMenuPos() {
  if (!worktreeButtonRef.value) return
  const rect = worktreeButtonRef.value.getBoundingClientRect()
  const spaceAbove = rect.top
  const spaceBelow = window.innerHeight - rect.bottom
  const direction = spaceBelow >= WORKTREE_MENU_HEIGHT || spaceBelow >= spaceAbove ? 'down' : 'up'
  const maxLeft = Math.max(VIEWPORT_GUTTER, window.innerWidth - WORKTREE_MENU_WIDTH - VIEWPORT_GUTTER)
  worktreeMenuPos.value = {
    top: direction === 'down' ? rect.bottom + 6 : rect.top - 6,
    left: Math.min(Math.max(rect.left, VIEWPORT_GUTTER), maxLeft),
    direction,
  }
}

// ─── Fetch repository context when workDir changes ─────────────────
watch(
  () => props.workDir,
  async (workDir) => {
    if (!workDir) {
      context.value = null
      error.value = null
      loading.value = false
      props.onBranchChange(null)
      return
    }

    let cancelled = false
    loading.value = true
    error.value = null
    try {
      const result = await sessionsApi.getRepositoryContext(workDir)
      if (!cancelled) context.value = result
    } catch (err) {
      if (!cancelled) {
        context.value = null
        error.value = err instanceof Error ? err.message : String(err)
      }
    } finally {
      if (!cancelled) loading.value = false
    }

    return () => {
      cancelled = true
    }
  },
  { immediate: true }
)

// ─── Auto-select a valid branch when context changes ────────────────
watch(
  () => [props.branch, context.value],
  () => {
    const ctx = context.value
    if (ctx?.state !== 'ok') {
      if (ctx && props.branch !== null) props.onBranchChange(null)
      return
    }
    const branchExists = props.branch && ctx.branches.some((candidate) => candidate.name === props.branch)
    if (branchExists) return

    const fallbackBranch = [
      ctx.currentBranch,
      ctx.defaultBranch,
      ctx.branches[0]?.name,
    ].find((name) => name && ctx.branches.some((candidate) => candidate.name === name))

    props.onBranchChange(fallbackBranch || null)
  }
)

// ─── Close menus on outside click / Escape ─────────────────────────
function handleOutsideClick(e: MouseEvent) {
  if (!branchMenuOpen.value && !worktreeMenuOpen.value) return
  const target = e.target as Node
  if (rootRef.value?.contains(target)) return
  if (menuRef.value?.contains(target)) return
  if (worktreeMenuRef.value?.contains(target)) return
  branchMenuOpen.value = false
  worktreeMenuOpen.value = false
}

function handleKey(e: KeyboardEvent) {
  if (e.key !== 'Escape') return
  e.preventDefault()
  branchMenuOpen.value = false
  worktreeMenuOpen.value = false
}

// ─── Branch menu open: position + focus + scroll/resize ────────────
const branchMenuScrollHandler: EventListener = () => updateMenuPos()
const branchMenuResizeHandler = () => updateMenuPos()

watch(branchMenuOpen, (open) => {
  if (!open) return
  updateMenuPos()
  window.addEventListener('scroll', branchMenuScrollHandler, true)
  window.addEventListener('resize', branchMenuResizeHandler)
  // focus search input after DOM update
  requestAnimationFrame(() => searchRef.value?.focus())
})

// ─── Worktree menu open: position + scroll/resize ──────────────────
const worktreeMenuScrollHandler: EventListener = () => updateWorktreeMenuPos()
const worktreeMenuResizeHandler = () => updateWorktreeMenuPos()

watch(worktreeMenuOpen, (open) => {
  if (!open) return
  updateWorktreeMenuPos()
  window.addEventListener('scroll', worktreeMenuScrollHandler, true)
  window.addEventListener('resize', worktreeMenuResizeHandler)
})

// ─── Reset selection index on filter change ────────────────────────
watch(branchFilter, () => {
  selectedIndex.value = 0
})

// ─── Scroll active item into view ──────────────────────────────────
watch([branchMenuOpen, selectedIndex], () => {
  if (branchMenuOpen.value && itemRefs.value[selectedIndex.value]) {
    itemRefs.value[selectedIndex.value]?.scrollIntoView({ block: 'nearest' })
  }
})

// ─── Computed: selected branch ─────────────────────────────────────
const selectedBranch = computed<RepositoryBranchInfo | null>(() => {
  if (context.value?.state !== 'ok') return null
  return context.value.branches.find((candidate) => candidate.name === props.branch) ?? null
})

// ─── Computed: filtered branches ───────────────────────────────────
const filteredBranches = computed<RepositoryBranchInfo[]>(() => {
  if (context.value?.state !== 'ok') return []
  const query = branchFilter.value.trim().toLowerCase()
  if (!query) return context.value.branches
  return context.value.branches.filter((candidate) =>
    candidate.name.toLowerCase().includes(query) ||
    (candidate.remoteRef?.toLowerCase().includes(query) ?? false) ||
    (candidate.worktreePath?.toLowerCase().includes(query) ?? false)
  )
})

// ─── Computed: warning message ─────────────────────────────────────
const warningMessage = computed(() => {
  const ctx = context.value
  if (ctx?.state !== 'ok' || !selectedBranch.value || props.useWorktree) return null
  if (selectedBranch.value.name !== ctx.currentBranch && ctx.dirty) {
    return t('repoLaunch.dirtyWarning')
  }
  if (selectedBranch.value.name !== ctx.currentBranch && selectedBranch.value.checkedOut) {
    return t('repoLaunch.checkedOutWarning')
  }
  return null
})

// ─── Computed: message ─────────────────────────────────────────────
const message = computed(() => stateMessage(context.value, error.value))

// ─── Computed: isGitReady ──────────────────────────────────────────
const isGitReady = computed(() => context.value?.state === 'ok')

// ─── Computed: isLaunchReady ───────────────────────────────────────
// Matches React exactly: !workDir returns true
const isLaunchReady = computed(() => {
  if (!props.workDir) return true
  if (loading.value) return false
  if (!context.value && !error.value) return false
  const ctx = context.value
  if (ctx?.state !== 'ok') return true
  if (ctx.branches.length === 0) return true
  return !!selectedBranch.value
})

// ─── Notify parent of launch-ready state ───────────────────────────
watch(isLaunchReady, (ready) => {
  emit('launchReadyChange', ready)
})

// ─── Computed: worktree label ──────────────────────────────────────
const worktreeLabel = computed(() =>
  props.useWorktree ? t('repoLaunch.worktreeIsolated') : t('repoLaunch.worktreeCurrent')
)

// ─── Actions ───────────────────────────────────────────────────────
function selectBranch(candidate: RepositoryBranchInfo) {
  props.onBranchChange(candidate.name)
  branchMenuOpen.value = false
  branchFilter.value = ''
}

function selectWorktreeMode(enabled: boolean) {
  props.onUseWorktreeChange(enabled)
  worktreeMenuOpen.value = false
}

function toggleBranchMenu() {
  branchMenuOpen.value = !branchMenuOpen.value
  worktreeMenuOpen.value = false
  branchFilter.value = ''
}

function toggleWorktreeMenu() {
  worktreeMenuOpen.value = !worktreeMenuOpen.value
  branchMenuOpen.value = false
}

// ─── Branch search keyboard handler ────────────────────────────────
function handleBranchKeyDown(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    selectedIndex.value = Math.min(selectedIndex.value + 1, Math.max(filteredBranches.value.length - 1, 0))
    return
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    selectedIndex.value = Math.max(selectedIndex.value - 1, 0)
    return
  }
  if (e.key === 'Enter') {
    e.preventDefault()
    const candidate = filteredBranches.value[selectedIndex.value]
    if (candidate) selectBranch(candidate)
    return
  }
  if (e.key === 'Escape') {
    e.preventDefault()
    branchMenuOpen.value = false
  }
}

// ─── Lifecycle ─────────────────────────────────────────────────────
onMounted(() => {
  document.addEventListener('mousedown', handleOutsideClick)
  document.addEventListener('keydown', handleKey)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', handleOutsideClick)
  document.removeEventListener('keydown', handleKey)
  window.removeEventListener('scroll', branchMenuScrollHandler, true)
  window.removeEventListener('resize', branchMenuResizeHandler)
  window.removeEventListener('scroll', worktreeMenuScrollHandler, true)
  window.removeEventListener('resize', worktreeMenuResizeHandler)
  if (mobileMediaQuery && typeof window !== 'undefined') {
    if (typeof mobileMediaQuery.removeEventListener === 'function') {
      mobileMediaQuery.removeEventListener('change', handleMobileChange)
    } else {
      mobileMediaQuery.removeListener(handleMobileChange as any)
    }
  }
})

// ─── Shared CSS classes ────────────────────────────────────────────
const workbarButtonClassName =
  'group inline-flex h-9 min-w-0 items-center gap-1.5 rounded-[7px] border border-transparent px-2.5 text-[13px] font-medium leading-none text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-container-lowest)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/35 disabled:cursor-not-allowed disabled:opacity-50'

// These MUST be computed (not static) because isMobileBrowser is reactive
const branchMenuClassName = computed(() =>
  isMobileBrowser.value
    ? 'max-h-[72dvh] overflow-hidden rounded-t-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] shadow-[0_-18px_48px_rgba(54,35,28,0.2)]'
    : 'w-[390px] overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] shadow-[var(--shadow-dropdown)]'
)

const branchMenuStyle = computed(() =>
  isMobileBrowser.value
    ? ({
        position: 'fixed' as const,
        left: 12,
        right: 12,
        bottom: 'calc(env(safe-area-inset-bottom) + 84px)',
        zIndex: 9999,
      } as const)
    : ({
        position: 'fixed' as const,
        left: menuPos.value?.left,
        ...(menuPos.value?.direction === 'down'
          ? { top: menuPos.value.top }
          : { bottom: window.innerHeight - (menuPos.value?.top ?? 0) }),
        zIndex: 9999,
      } as const)
)

const worktreeMenuClassName = computed(() =>
  isMobileBrowser.value
    ? 'overflow-hidden rounded-t-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] py-2 shadow-[0_-18px_48px_rgba(54,35,28,0.2)]'
    : 'w-[226px] overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] py-1 shadow-[var(--shadow-dropdown)]'
)

const worktreeMenuStyle = computed(() =>
  isMobileBrowser.value
    ? ({
        position: 'fixed' as const,
        left: 12,
        right: 12,
        bottom: 'calc(env(safe-area-inset-bottom) + 84px)',
        zIndex: 9999,
      } as const)
    : ({
        position: 'fixed' as const,
        left: worktreeMenuPos.value?.left,
        ...(worktreeMenuPos.value?.direction === 'down'
          ? { top: worktreeMenuPos.value.top }
          : { bottom: window.innerHeight - (worktreeMenuPos.value?.top ?? 0) }),
        zIndex: 9999,
      } as const)
)
</script>

<template>
  <div
    ref="rootRef"
    :class="[
      'flex min-w-0 flex-col',
      isMobileBrowser ? 'gap-0' : isComposerPlacement ? 'gap-1' : 'gap-2'
    ]"
  >
    <div
      :class="[
        'flex min-w-0 items-center justify-start gap-x-1.5 gap-y-1 overflow-hidden border-t border-[var(--color-border-separator)]',
        isMobileBrowser
          ? 'min-h-[52px] flex-wrap rounded-none bg-[var(--color-surface-container-lowest)] px-3 py-2 shadow-none'
          : isComposerPlacement
            ? 'min-h-[44px] flex-nowrap bg-transparent px-4 py-2'
            : 'min-h-[48px] flex-nowrap rounded-b-xl bg-[var(--color-surface-container-low)] px-4 py-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.45)]'
      ]"
    >
      <DirectoryPicker
        :value="props.workDir"
        :on-change="props.onWorkDirChange"
        variant="workbar"
        :is-git-project="isGitReady"
      />

      <div
        v-if="loading && props.workDir && !isMobileBrowser"
        class="inline-flex h-9 items-center gap-1.5 rounded-[7px] px-2.5 text-[13px] text-[var(--color-text-secondary)]"
      >
        <span class="material-symbols-outlined text-[14px] animate-spin">sync</span>
        <span>{{ t('common.loading') }}</span>
      </div>

      <template v-if="isGitReady">
        <span
          class="hidden h-4 w-px shrink-0 bg-[var(--color-border-separator)] opacity-70 sm:block"
          aria-hidden="true"
        />
        <button
          ref="branchButtonRef"
          type="button"
          :disabled="props.disabled || loading || context!.branches.length === 0"
          :aria-haspopup="'listbox'"
          :aria-expanded="branchMenuOpen"
          :aria-controls="branchMenuOpen ? listboxId : undefined"
          :aria-label="`${t('repoLaunch.selectBranch')}: ${selectedBranch?.name || t('repoLaunch.noBranch')}`"
          :title="selectedBranch?.name || t('repoLaunch.noBranch')"
          @click="toggleBranchMenu"
          :class="[
            workbarButtonClassName,
            isMobileBrowser ? 'max-w-[160px] shrink-0 bg-[var(--color-surface-container)]' : 'max-w-[260px] shrink'
          ]"
        >
          <span class="material-symbols-outlined text-[17px] shrink-0 text-[var(--color-text-tertiary)] group-hover:text-[var(--color-text-secondary)]">git_branch</span>
          <span class="min-w-0 flex-1 truncate text-[var(--color-text-primary)]">
            {{ selectedBranch?.name || t('repoLaunch.noBranch') }}
          </span>
          <span class="material-symbols-outlined text-[16px] shrink-0 text-[var(--color-text-tertiary)]">expand_more</span>
        </button>

        <button
          ref="worktreeButtonRef"
          type="button"
          :disabled="props.disabled"
          :aria-haspopup="'listbox'"
          :aria-expanded="worktreeMenuOpen"
          :aria-controls="worktreeMenuOpen ? worktreeListboxId : undefined"
          :aria-label="`${t('repoLaunch.selectWorktree')}: ${worktreeLabel}`"
          :title="worktreeLabel"
          @click="toggleWorktreeMenu"
          :class="[
            workbarButtonClassName,
            'shrink-0',
            isMobileBrowser ? 'bg-[var(--color-surface-container)]' : '',
            props.useWorktree ? 'bg-[var(--color-surface-container-lowest)] text-[var(--color-text-primary)]' : ''
          ]"
        >
          <span class="material-symbols-outlined text-[17px] shrink-0 text-[var(--color-text-tertiary)]">git_pull_request</span>
          <span class="min-w-0 truncate">{{ worktreeLabel }}</span>
          <span class="material-symbols-outlined text-[16px] shrink-0 text-[var(--color-text-tertiary)]">expand_more</span>
        </button>
      </template>
    </div>

    <!-- Status / error message -->
    <div
      v-if="message && props.workDir"
      class="flex items-center gap-2 px-1 text-[11px] text-[var(--color-text-tertiary)]"
    >
      <span class="material-symbols-outlined text-[13px] shrink-0">error_outline</span>
      <span>{{ message === 'missing' ? t('repoLaunch.missingWorkdir') : message }}</span>
    </div>

    <!-- Warning message -->
    <div
      v-if="warningMessage"
      class="flex items-center gap-2 px-1 text-[11px] text-[var(--color-warning)]"
    >
      <span class="material-symbols-outlined text-[13px] shrink-0">error_outline</span>
      <span>{{ warningMessage }}</span>
    </div>

    <!-- ─── Branch menu (mobile: bottom sheet) ──────────────────── -->
    <template v-if="branchMenuOpen && menuPos">
      <MobileBottomSheet
        v-if="isMobileBrowser"
        :open="branchMenuOpen"
        :title="t('repoLaunch.selectBranch')"
        :close-label="t('tabs.close')"
        :panel-ref="menuRef"
        @close="branchMenuOpen = false"
      >
        <template #header-extra>
          <div class="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-3 py-2">
            <span class="material-symbols-outlined text-[15px] shrink-0 text-[var(--color-text-tertiary)]">search</span>
            <input
              :id="searchInputId"
              ref="searchRef"
              :value="branchFilter"
              @input="branchFilter = ($event.target as HTMLInputElement).value"
              @keydown="handleBranchKeyDown"
              :aria-controls="listboxId"
              :aria-activedescendant="filteredBranches[selectedIndex] ? `${listboxId}-option-${selectedIndex}` : undefined"
              :placeholder="t('repoLaunch.searchBranch')"
              class="min-w-0 flex-1 bg-transparent text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-tertiary)]"
            />
          </div>
        </template>

        <div :id="listboxId" role="listbox" :aria-label="t('repoLaunch.selectBranch')" class="py-1">
          <div
            v-if="filteredBranches.length === 0"
            class="px-4 py-8 text-center text-xs text-[var(--color-text-tertiary)]"
          >
            {{ t('repoLaunch.noBranchMatch') }}
          </div>
          <button
            v-for="(candidate, index) in filteredBranches"
            :key="candidate.name"
            :id="`${listboxId}-option-${index}`"
            :ref="(el: any) => { if (el) itemRefs[index] = el as HTMLButtonElement }"
            type="button"
            role="option"
            :aria-selected="candidate.name === selectedBranch?.name"
            @mouseenter="selectedIndex = index"
            @click="selectBranch(candidate)"
            :class="[
              'flex min-h-[56px] w-full items-center gap-3 px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-brand)]/35',
              (index === selectedIndex || candidate.name === selectedBranch?.name)
                ? 'bg-[var(--color-surface-hover)]'
                : 'hover:bg-[var(--color-surface-hover)]'
            ]"
          >
            <span :class="['h-8 w-1 rounded-full', candidate.name === selectedBranch?.name ? 'bg-[var(--color-brand)]' : 'bg-transparent']" />
            <span class="material-symbols-outlined text-[17px] shrink-0 text-[var(--color-text-secondary)]">git_branch</span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-sm font-semibold text-[var(--color-text-primary)]">{{ candidate.name }}</span>
              <span class="block truncate text-[11px] text-[var(--color-text-tertiary)]">
                {{
                  candidate.current
                    ? t('repoLaunch.currentBranch')
                    : candidate.checkedOut
                      ? t('repoLaunch.checkedOut')
                      : candidate.remote && !candidate.local
                        ? (candidate.remoteRef || t('repoLaunch.remoteBranch'))
                        : t('repoLaunch.localBranch')
                }}
              </span>
            </span>
            <span v-if="candidate.name === selectedBranch?.name" class="material-symbols-outlined text-[17px] shrink-0 text-[var(--color-brand)]">check</span>
          </button>
        </div>
      </MobileBottomSheet>

      <!-- Branch menu (desktop: portal) -->
      <Teleport v-else to="body">
        <div
          ref="menuRef"
          :class="branchMenuClassName"
          :style="branchMenuStyle"
        >
          <div class="border-b border-[var(--color-border)] p-3">
            <label :for="searchInputId" class="mb-2 block text-[10px] font-bold uppercase tracking-widest text-[var(--color-outline)]">
              {{ t('repoLaunch.selectBranch') }}
            </label>
            <div class="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-3 py-2">
              <span class="material-symbols-outlined text-[15px] shrink-0 text-[var(--color-text-tertiary)]">search</span>
              <input
                :id="searchInputId"
                ref="searchRef"
                :value="branchFilter"
                @input="branchFilter = ($event.target as HTMLInputElement).value"
                @keydown="handleBranchKeyDown"
                :aria-controls="listboxId"
                :aria-activedescendant="filteredBranches[selectedIndex] ? `${listboxId}-option-${selectedIndex}` : undefined"
                :placeholder="t('repoLaunch.searchBranch')"
                class="min-w-0 flex-1 bg-transparent text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-tertiary)]"
              />
            </div>
          </div>

          <div :id="listboxId" role="listbox" :aria-label="t('repoLaunch.selectBranch')" class="max-h-[280px] overflow-y-auto py-1">
            <div
              v-if="filteredBranches.length === 0"
              class="px-4 py-8 text-center text-xs text-[var(--color-text-tertiary)]"
            >
              {{ t('repoLaunch.noBranchMatch') }}
            </div>
            <button
              v-for="(candidate, index) in filteredBranches"
              :key="candidate.name"
              :id="`${listboxId}-option-${index}`"
              :ref="(el: any) => { if (el) itemRefs[index] = el as HTMLButtonElement }"
              type="button"
              role="option"
              :aria-selected="candidate.name === selectedBranch?.name"
              @mouseenter="selectedIndex = index"
              @click="selectBranch(candidate)"
              :class="[
                'flex w-full items-center gap-3 px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-brand)]/35',
                (index === selectedIndex || candidate.name === selectedBranch?.name)
                  ? 'bg-[var(--color-surface-hover)]'
                  : 'hover:bg-[var(--color-surface-hover)]'
              ]"
            >
              <span :class="['h-8 w-1 rounded-full', candidate.name === selectedBranch?.name ? 'bg-[var(--color-brand)]' : 'bg-transparent']" />
              <span class="material-symbols-outlined text-[17px] shrink-0 text-[var(--color-text-secondary)]">git_branch</span>
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-semibold text-[var(--color-text-primary)]">{{ candidate.name }}</span>
                <span class="block truncate text-[11px] text-[var(--color-text-tertiary)]">
                  {{
                    candidate.current
                      ? t('repoLaunch.currentBranch')
                      : candidate.checkedOut
                        ? t('repoLaunch.checkedOut')
                        : candidate.remote && !candidate.local
                          ? (candidate.remoteRef || t('repoLaunch.remoteBranch'))
                          : t('repoLaunch.localBranch')
                  }}
                </span>
              </span>
              <span v-if="candidate.name === selectedBranch?.name" class="material-symbols-outlined text-[17px] shrink-0 text-[var(--color-brand)]">check</span>
            </button>
          </div>
        </div>
      </Teleport>
    </template>

    <!-- ─── Worktree menu (mobile: bottom sheet) ────────────────── -->
    <template v-if="worktreeMenuOpen && worktreeMenuPos">
      <MobileBottomSheet
        v-if="isMobileBrowser"
        :open="worktreeMenuOpen"
        :title="t('repoLaunch.selectWorktree')"
        :close-label="t('tabs.close')"
        :panel-ref="worktreeMenuRef"
        :content-class-name="'py-2'"
        @close="worktreeMenuOpen = false"
      >
        <div :id="worktreeListboxId" role="listbox" :aria-label="t('repoLaunch.selectWorktree')">
          <button
            type="button"
            role="option"
            :aria-selected="!props.useWorktree"
            @click="selectWorktreeMode(false)"
            :class="[
              'flex min-h-[52px] w-full items-center gap-2.5 px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-brand)]/35 disabled:cursor-not-allowed disabled:opacity-45',
              !props.useWorktree ? 'bg-[var(--color-surface-hover)]' : 'hover:bg-[var(--color-surface-hover)]'
            ]"
          >
            <span class="material-symbols-outlined text-[16px] shrink-0 text-[var(--color-text-tertiary)]">git_pull_request</span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-[13px] font-medium text-[var(--color-text-primary)]">{{ t('repoLaunch.worktreeCurrent') }}</span>
            </span>
            <span v-if="!props.useWorktree" class="material-symbols-outlined text-[16px] shrink-0 text-[var(--color-brand)]">check</span>
          </button>

          <button
            type="button"
            role="option"
            :aria-selected="props.useWorktree"
            @click="selectWorktreeMode(true)"
            :class="[
              'flex min-h-[52px] w-full items-center gap-2.5 px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-brand)]/35',
              props.useWorktree ? 'bg-[var(--color-surface-hover)]' : 'hover:bg-[var(--color-surface-hover)]'
            ]"
          >
            <span class="material-symbols-outlined text-[16px] shrink-0 text-[var(--color-text-tertiary)]">git_pull_request</span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-[13px] font-medium text-[var(--color-text-primary)]">{{ t('repoLaunch.worktreeIsolated') }}</span>
            </span>
            <span v-if="props.useWorktree" class="material-symbols-outlined text-[16px] shrink-0 text-[var(--color-brand)]">check</span>
          </button>
        </div>
      </MobileBottomSheet>

      <!-- Worktree menu (desktop: portal) -->
      <Teleport v-else to="body">
        <div
          ref="worktreeMenuRef"
          :class="worktreeMenuClassName"
          :style="worktreeMenuStyle"
        >
          <div :id="worktreeListboxId" role="listbox" :aria-label="t('repoLaunch.selectWorktree')">
            <button
              type="button"
              role="option"
              :aria-selected="!props.useWorktree"
              @click="selectWorktreeMode(false)"
              :class="[
                'flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-brand)]/35 disabled:cursor-not-allowed disabled:opacity-45',
                !props.useWorktree ? 'bg-[var(--color-surface-hover)]' : 'hover:bg-[var(--color-surface-hover)]'
              ]"
            >
              <span class="material-symbols-outlined text-[16px] shrink-0 text-[var(--color-text-tertiary)]">git_pull_request</span>
              <span class="min-w-0 flex-1">
                <span class="block truncate text-[13px] font-medium text-[var(--color-text-primary)]">{{ t('repoLaunch.worktreeCurrent') }}</span>
              </span>
              <span v-if="!props.useWorktree" class="material-symbols-outlined text-[16px] shrink-0 text-[var(--color-brand)]">check</span>
            </button>

            <button
              type="button"
              role="option"
              :aria-selected="props.useWorktree"
              @click="selectWorktreeMode(true)"
              :class="[
                'flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-brand)]/35',
                props.useWorktree ? 'bg-[var(--color-surface-hover)]' : 'hover:bg-[var(--color-surface-hover)]'
              ]"
            >
              <span class="material-symbols-outlined text-[16px] shrink-0 text-[var(--color-text-tertiary)]">git_pull_request</span>
              <span class="min-w-0 flex-1">
                <span class="block truncate text-[13px] font-medium text-[var(--color-text-primary)]">{{ t('repoLaunch.worktreeIsolated') }}</span>
              </span>
              <span v-if="props.useWorktree" class="material-symbols-outlined text-[16px] shrink-0 text-[var(--color-brand)]">check</span>
            </button>
          </div>
        </div>
      </Teleport>
    </template>
  </div>
</template>