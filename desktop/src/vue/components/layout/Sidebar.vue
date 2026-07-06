<script setup lang="ts">
// v3.0 — MadCop Sidebar (Vue 3) — Phase 1: main component + hooks
// Full translation of Sidebar.tsx lines 1-1293 (React → Vue 3 SFC).
// Sub-components (NavItem, etc.) are render-function helpers or TODO placeholders.

import { ref, computed, onMounted, onUnmounted, watch, h, defineComponent, nextTick } from 'vue'
import { useSessionStore } from '../../stores/sessionStore'
import { useUIStore } from '../../stores/uiStore'
import { useSettingsStore } from '../../stores/settingsStore'
import { useTabStore, SETTINGS_TAB_ID, SCHEDULED_TAB_ID } from '../../stores/tabs'
import { useChatStore } from '../../stores/chatStore'
import { useOpenTargetStore } from '../../stores/openTargetStore'
import { translate, type TranslationKey } from '../../i18n'
import type { SessionListItem } from '../../../types/session'
import { desktopUiPreferencesApi, type SidebarProjectPreferences } from '../../../api/desktopUiPreferences'
import { getDesktopHost } from '../../../lib/desktopHost'
import ConfirmDialog from '../shared/ConfirmDialog.vue'
import AnimationPlayer from '../animations/AnimationPlayer.vue'
import MascotAvatar from '../common/MascotAvatar.vue'
// GlobalSearchModal not yet translated — using placeholder
const GlobalSearchModal = { template: '<div></div>' }

// ─── Constants ──────────────────────────────────────────────────────────

const desktopHost = getDesktopHost()
const isDesktopRuntime = desktopHost.isDesktop
const canUseNativeDialogs = desktopHost.capabilities.dialogs
const isWindows = typeof navigator !== 'undefined' && /Win/.test(navigator.platform)
const SESSION_LIST_AUTO_REFRESH_MS = 30_000
const SESSION_LIST_FOCUS_REFRESH_MIN_MS = 5_000
const PROJECT_ORDER_STORAGE_KEY = 'madcop-agent-sidebar-project-order'
const PROJECT_PINNED_STORAGE_KEY = 'madcop-agent-sidebar-pinned-projects'
const PROJECT_HIDDEN_STORAGE_KEY = 'madcop-agent-sidebar-hidden-projects'
const PROJECT_ORGANIZATION_STORAGE_KEY = 'madcop-agent-sidebar-project-organization'
const PROJECT_SORT_STORAGE_KEY = 'madcop-agent-sidebar-project-sort'
const PROJECT_GROUP_VISIBLE_COUNT = 6
const PROJECT_GROUP_SCROLL_COUNT = 12

// ─── Type definitions ───────────────────────────────────────────────────

type SidebarProjectOrganization = 'project' | 'recentProject' | 'time'
type SidebarProjectSortBy = 'createdAt' | 'updatedAt'
type SidebarHeaderMenuType = 'main' | 'organize' | 'sort' | 'create'

type ProjectGroup = {
  key: string
  title: string
  subtitle: string | null
  workDir: string | undefined
  sessions: SessionListItem[]
}

// ─── Props ──────────────────────────────────────────────────────────────

const props = defineProps<{
  isMobile?: boolean
  onRequestClose?: () => void
}>()

// ─── Store access (Pinia) ───────────────────────────────────────────────

const sessionStore = useSessionStore()
const uiStore = useUIStore()
const tabStore = useTabStore()
const chatStore = useChatStore()
const settingsStore = useSettingsStore()
const openTargetStore = useOpenTargetStore()

// Translation function (Vue-friendly, using Pinia settingsStore)
const t = (key: TranslationKey, params?: Record<string, string | number>): string =>
  translate(settingsStore.locale as any, key, params)

// ─── Helper function s (pure, no state) ──────────────────────────────────

function isDocumentVisible(): boolean {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden'
}

function domSafeProjectKey(projectKey: string): string {
  return projectKey.replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '') || 'unknown'
}

function positionProjectMenu(clientX: number, clientY: number): { left: number; top: number } {
  if (typeof window === 'undefined') return { left: clientX, top: clientY }
  const width = 230
  const height = 280
  return {
    left: Math.max(8, Math.min(clientX, window.innerWidth - width - 8)),
    top: Math.max(8, Math.min(clientY, window.innerHeight - height - 8)),
  }
}

function formatRelativeTime(
  dateStr: string,
  tFn: (key: TranslationKey, params?: Record<string, string | number>) => string,
): string {
  const date = new Date(dateStr)
  const timestamp = date.getTime()
  if (!Number.isFinite(timestamp)) return ''
  const diff = Date.now() - timestamp
  const min = Math.floor(diff / 60000)
  if (min < 1) return tFn('session.timeJustNow')
  if (min < 60) return tFn('session.timeMinutes', { n: min })
  const hr = Math.floor(min / 60)
  if (hr < 24) return tFn('session.timeHours', { n: hr })
  const day = Math.floor(hr / 24)
  if (day < 30) return tFn('session.timeDays', { n: day })
  return new Intl.DateTimeFormat(undefined, { month: 'numeric', day: 'numeric' }).format(date)
}

function normalizeProjectKeyList(values: unknown): string[] {
  if (!Array.isArray(values)) return []
  const seen = new Set<string>()
  const normalized: string[] = []
  for (const value of values) {
    if (typeof value !== 'string' || value.length === 0 || seen.has(value)) continue
    seen.add(value)
    normalized.push(value)
  }
  return normalized
}

function normalizeProjectPathForComparison(value: string): string {
  const normalized = value.replace(/\\/g, '/').replace(/\/+$/g, '') || value
  return isWindows ? normalized.toLowerCase() : normalized
}

function isDriveRootComparisonPath(value: string): boolean {
  return /^[a-z]:$/i.test(value)
}

function projectPathMatches(projectKey: string, workDir: string): boolean {
  const normalizedProjectKey = normalizeProjectPathForComparison(projectKey)
  const normalizedWorkDir = normalizeProjectPathForComparison(workDir)
  if (normalizedProjectKey === normalizedWorkDir) return true
  if (isDriveRootComparisonPath(normalizedProjectKey)) return false
  return normalizedWorkDir.startsWith(`${normalizedProjectKey}/`)
}

function hasSidebarProjectPreferences(preferences: SidebarProjectPreferences): boolean {
  return preferences.projectOrder.length > 0
    || preferences.pinnedProjects.length > 0
    || preferences.hiddenProjects.length > 0
    || preferences.projectOrganization !== 'recentProject'
    || preferences.projectSortBy !== 'updatedAt'
}

function normalizeProjectOrganization(value: unknown): SidebarProjectOrganization {
  return (value === 'project' || value === 'recentProject' || value === 'time') ? (value as SidebarProjectOrganization) : 'recentProject'
}

function normalizeProjectSortBy(value: unknown): SidebarProjectSortBy {
  return (value === 'createdAt' || value === 'updatedAt') ? (value as SidebarProjectSortBy) : 'updatedAt'
}

function normalizeSidebarProjectPreferences(preferences?: Partial<SidebarProjectPreferences>): SidebarProjectPreferences {
  return {
    projectOrder: normalizeProjectKeyList(preferences?.projectOrder),
    pinnedProjects: normalizeProjectKeyList(preferences?.pinnedProjects),
    hiddenProjects: normalizeProjectKeyList(preferences?.hiddenProjects),
    projectOrganization: normalizeProjectOrganization(preferences?.projectOrganization),
    projectSortBy: normalizeProjectSortBy(preferences?.projectSortBy),
  }
}

function buildSidebarProjectPreferences(
  projectOrder: string[],
  pinnedProjectKeys: Set<string>,
  hiddenProjectKeys: Set<string>,
  projectOrganization: SidebarProjectOrganization,
  projectSortBy: SidebarProjectSortBy,
): SidebarProjectPreferences {
  return normalizeSidebarProjectPreferences({
    projectOrder,
    pinnedProjects: [...pinnedProjectKeys],
    hiddenProjects: [...hiddenProjectKeys],
    projectOrganization,
    projectSortBy,
  })
}

function readStoredProjectOrder(): string[] {
  if (typeof localStorage === 'undefined') return []
  try {
    const parsed = JSON.parse(localStorage.getItem(PROJECT_ORDER_STORAGE_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === 'string') : []
  } catch {
    return []
  }
}

function writeStoredProjectOrder(projectOrder: string[]): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(PROJECT_ORDER_STORAGE_KEY, JSON.stringify(projectOrder))
  } catch { /* noop */ }
}

function readStoredProjectPins(): Set<string> {
  if (typeof localStorage === 'undefined') return new Set()
  try {
    const parsed = JSON.parse(localStorage.getItem(PROJECT_PINNED_STORAGE_KEY) ?? '[]')
    return new Set(Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === 'string') : [])
  } catch {
    return new Set()
  }
}

function writeStoredProjectPins(projectKeys: Set<string>): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(PROJECT_PINNED_STORAGE_KEY, JSON.stringify([...projectKeys]))
  } catch { /* noop */ }
}

function readStoredProjectHidden(): Set<string> {
  if (typeof localStorage === 'undefined') return new Set()
  try {
    const parsed = JSON.parse(localStorage.getItem(PROJECT_HIDDEN_STORAGE_KEY) ?? '[]')
    return new Set(Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === 'string') : [])
  } catch {
    return new Set()
  }
}

function writeStoredProjectHidden(projectKeys: Set<string>): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(PROJECT_HIDDEN_STORAGE_KEY, JSON.stringify([...projectKeys]))
  } catch { /* noop */ }
}

function readStoredProjectOrganization(): SidebarProjectOrganization {
  if (typeof localStorage === 'undefined') return 'recentProject'
  return normalizeProjectOrganization(localStorage.getItem(PROJECT_ORGANIZATION_STORAGE_KEY))
}

function writeStoredProjectOrganization(organization: SidebarProjectOrganization): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(PROJECT_ORGANIZATION_STORAGE_KEY, organization)
  } catch { /* noop */ }
}

function readStoredProjectSortBy(): SidebarProjectSortBy {
  if (typeof localStorage === 'undefined') return 'updatedAt'
  return normalizeProjectSortBy(localStorage.getItem(PROJECT_SORT_STORAGE_KEY))
}

function writeStoredProjectSortBy(sortBy: SidebarProjectSortBy): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(PROJECT_SORT_STORAGE_KEY, sortBy)
  } catch { /* noop */ }
}

function readCachedSidebarProjectPreferences(): SidebarProjectPreferences {
  return {
    projectOrder: readStoredProjectOrder(),
    pinnedProjects: [...readStoredProjectPins()],
    hiddenProjects: [...readStoredProjectHidden()],
    projectOrganization: readStoredProjectOrganization(),
    projectSortBy: readStoredProjectSortBy(),
  }
}

function writeCachedSidebarProjectPreferences(preferences: SidebarProjectPreferences): void {
  const normalized = normalizeSidebarProjectPreferences(preferences)
  writeStoredProjectOrder(normalized.projectOrder)
  writeStoredProjectPins(new Set(normalized.pinnedProjects))
  writeStoredProjectHidden(new Set(normalized.hiddenProjects))
  writeStoredProjectOrganization(normalized.projectOrganization)
  writeStoredProjectSortBy(normalized.projectSortBy)
}

function getVisibleProjectSessions(
  sessions: SessionListItem[],
  expanded: boolean,
  activeSessionId: string | null,
): SessionListItem[] {
  if (expanded || sessions.length <= PROJECT_GROUP_VISIBLE_COUNT) return sessions
  const visible = sessions.slice(0, PROJECT_GROUP_VISIBLE_COUNT)
  if (!activeSessionId || visible.some((session) => session.id === activeSessionId)) return visible
  const activeSession = sessions.find((session) => session.id === activeSessionId)
  return activeSession ? [...visible, activeSession] : visible
}

function getSessionProjectKey(session: SessionListItem): string {
  return session.projectRoot || session.workDir || session.projectPath || 'unknown'
}

function compareSessionsByTimestamp(
  a: SessionListItem | undefined,
  b: SessionListItem | undefined,
  sortBy: SidebarProjectSortBy,
): number {
  return getSessionTimestamp(b, sortBy) - getSessionTimestamp(a, sortBy)
}

function getSessionTimestamp(session: SessionListItem | undefined, sortBy: SidebarProjectSortBy): number {
  const value = sortBy === 'createdAt' ? session?.createdAt : session?.modifiedAt
  const timestamp = new Date(value ?? 0).getTime()
  return Number.isFinite(timestamp) ? timestamp : 0
}

function projectTitle(pathLike: string | null | undefined): string {
  if (!pathLike) return 'Unknown project'
  const normalized = pathLike.replace(/[\\\/]+$/, '')
  const segments = normalized.split(/[\\\/]/).filter(Boolean)
  const last = segments[segments.length - 1]
  if (last) return last
  return normalized || 'Unknown project'
}

function projectSubtitle(projectRoot: string | null | undefined, fallbackKey: string): string | null {
  if (!projectRoot) return fallbackKey === 'unknown' ? null : fallbackKey
  return compactProjectPath(projectRoot)
}

function isWorktreeSession(session: SessionListItem): boolean {
  if (!session.workDir) return false
  if (/[/\\]\.claude[/\\]worktrees[/\\]/.test(session.workDir)) return true
  if (!session.projectRoot || session.workDir === session.projectRoot) return false
  return !isSameOrChildPath(session.workDir, session.projectRoot)
}

function isSameOrChildPath(childPath: string, parentPath: string): boolean {
  const child = normalizePathForCompare(childPath)
  const parent = normalizePathForCompare(parentPath)
  return child === parent || child.startsWith(`${parent}/`)
}

function normalizePathForCompare(pathLike: string): string {
  return pathLike.replace(/\\/g, '/').replace(/\/+$/, '')
}

function compactProjectPath(pathLike: string): string {
  const normalized = normalizePathForCompare(pathLike)
  const segments = normalized.split('/').filter(Boolean)
  if (segments.length <= 3) return normalized
  return `.../${segments.slice(-3, -1).join('/')}`
}

function moveProjectKey(
  projectKeys: string[],
  sourceKey: string,
  targetKey: string,
  position: 'before' | 'after',
): string[] {
  const withoutSource = projectKeys.filter((key) => key !== sourceKey)
  const targetIndex = withoutSource.indexOf(targetKey)
  if (targetIndex < 0) return projectKeys
  const insertIndex = position === 'before' ? targetIndex : targetIndex + 1
  return [
    ...withoutSource.slice(0, insertIndex),
    sourceKey,
    ...withoutSource.slice(insertIndex),
  ]
}

function getProjectDropPosition(event: MouseEvent): 'before' | 'after' {
  const target = event.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  return event.clientY <= rect.top + rect.height / 2 ? 'before' : 'after'
}

function groupByProject(sessions: SessionListItem[], sortBy: SidebarProjectSortBy): ProjectGroup[] {
  const groupsByKey = new Map<string, SessionListItem[]>()
  for (const session of sessions) {
    const key =getSessionProjectKey(session)
    const items = groupsByKey.get(key) ?? []
    items.push(session)
    groupsByKey.set(key, items)
  }
  const groups = [...groupsByKey.entries()].map(([key, items]) => {
    const sortedSessions = [...items].sort((a, b) => compareSessionsByTimestamp(a, b, sortBy))
    const newest = sortedSessions[0]
    const projectRoot = newest?.projectRoot || newest?.workDir || key
    return {
      key,
      title: projectTitle(projectRoot),
      subtitle: projectSubtitle(projectRoot, key),
      workDir: projectRoot || newest?.workDir || undefined,
      sessions: sortedSessions,
    }
  })
  return groups.sort((a, b) => compareSessionsByTimestamp(a.sessions[0], b.sessions[0], sortBy))
}

function applyProjectOrder(
  groups: ProjectGroup[],
  projectOrder: string[],
  pinnedProjectKeys: Set<string>,
  organization: SidebarProjectOrganization,
  sortBy: SidebarProjectSortBy,
): ProjectGroup[] {
  const orderIndex = new Map(projectOrder.map((key, index) => [key, index]))
  return [...groups].sort((a, b) => {
    const aPinned = pinnedProjectKeys.has(a.key)
    const bPinned = pinnedProjectKeys.has(b.key)
    if (aPinned !== bPinned) return aPinned ? -1 : 1
    if (organization === 'project') return a.title.localeCompare(b.title)
    const aIndex = orderIndex.get(a.key)
    const bIndex = orderIndex.get(b.key)
    if (aIndex !== undefined && bIndex !== undefined) return aIndex - bIndex
    if (aIndex !== undefined) return -1
    if (bIndex !== undefined) return 1
    return compareSessionsByTimestamp(a.sessions[0], b.sessions[0], sortBy)
  })
}

// ─── SVG Icon Components ────────────────────────────────────────────────

const GitHubIcon = defineComponent({
  setup() {
    return () => h('svg', { width: '18', height: '18', viewBox: '0 0 24 24', fill: 'currentColor' }, [
      h('path', { d: 'M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z' }),
    ])
  },
})

const PlusIcon = defineComponent({
  setup() {
    return () => h('svg', { width: '18', height: '18', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: '2', strokeLinecap: 'round', strokeLinejoin: 'round' }, [
      h('line', { x1: '12', y1: '5', x2: '12', y2: '19' }),
      h('line', { x1: '5', y1: '12', x2: '19', y2: '12' }),
    ])
  },
})

const GitBranchIcon = defineComponent({
  setup() {
    return () => h('svg', { width: '18', height: '18', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: '2', strokeLinecap: 'round', strokeLinejoin: 'round' }, [
      h('line', { x1: '6', y1: '3', x2: '6', y2: '15' }),
      h('circle', { cx: '18', cy: '6', r: '3' }),
      h('circle', { cx: '6', cy: '18', r: '3' }),
      h('path', { d: 'M18 9a9 9 0 0 1-9 9' }),
    ])
  },
})

const ClockIcon = defineComponent({
  setup() {
    return () => h('svg', { width: '18', height: '18', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: '2', strokeLinecap: 'round', strokeLinejoin: 'round' }, [
      h('circle', { cx: '12', cy: '12', r: '10' }),
      h('polyline', { points: '12 6 12 12 16 14' }),
    ])
  },
})

const DesignIcon = defineComponent({
  setup() {
    return () => h('svg', { width: '18', height: '18', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: '2', strokeLinecap: 'round', strokeLinejoin: 'round' }, [
      h('rect', { x: '3', y: '3', width: '18', height: '18', rx: '2' }),
      h('path', { d: 'M3 9h18' }),
      h('path', { d: 'M9 21V9' }),
    ])
  },
})

const SearchIcon = defineComponent({
  setup() {
    return () => h('svg', { width: '15', height: '15', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: '2', strokeLinecap: 'round', strokeLinejoin: 'round' }, [
      h('circle', { cx: '11', cy: '11', r: '7' }),
      h('line', { x1: '21', y1: '21', x2: '16.65', y2: '16.65' }),
    ])
  },
})

const SidebarToggleIcon = defineComponent({
  props: { collapsed: Boolean },
  setup(props) {
    return () => h('svg', {
      width: props.collapsed ? 16 : 14,
      height: props.collapsed ? 16 : 14,
      viewBox: '0 0 14 14',
      fill: 'none',
      class: `sidebar-toggle-icon ${props.collapsed ? 'sidebar-toggle-icon--collapsed' : 'sidebar-toggle-icon--open'}`,
      'aria-hidden': 'true',
    }, [
      h('path', {
        d: props.collapsed ? 'M5 3 9 7l-4 4' : 'M9 3 5 7l4 4',
        class: 'sidebar-toggle-chevron',
      }),
    ])
  },
})

// ─── Reactive state (useState → ref) ────────────────────────────────────

const isMobileComputed = computed(() => props.isMobile ?? false)
const closeMobileDrawer = () => props.onRequestClose?.()

// === v3.1 — Graph-theoretic nav: more/less state for secondary nav ===
const navMoreOpen = ref(false)
const activeSessionCount = computed(() => sessionStore.sessions?.length ?? 0)
const runningSessionCount = computed(() => (tabStore.tabs ?? []).filter((tb: any) => tb.status === 'running').length)

// === v3.1 — Nav item class generators (no icons, typography-driven) ===
function primaryNavClass(isActive: boolean): string {
  return `group flex w-full h-9 items-center gap-2.5 rounded-lg px-2.5 text-[13px] font-medium transition-all duration-150 ${
    isActive
      ? 'bg-[var(--color-sidebar-item-active)] text-[var(--color-text-primary)]'
      : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-sidebar-item-hover)] hover:text-[var(--color-text-primary)]'
  } ${!expanded ? 'justify-center' : ''}`
}

function secondaryNavClass(isActive: boolean): string {
  return `group flex w-full h-8 items-center gap-2.5 rounded-md px-2.5 transition-all duration-150 ${
    isActive
      ? 'bg-[var(--color-sidebar-item-active)]/60 text-[var(--color-text-primary)]'
      : 'text-[var(--color-text-tertiary)] hover:bg-[var(--color-sidebar-item-hover)]/50 hover:text-[var(--color-text-secondary)]'
  } ${!expanded ? 'justify-center' : ''}`
}

const contextMenu = ref<{ id: string; x: number; y: number } | null>(null)
const projectContextMenu = ref<{ key: string; x: number; y: number } | null>(null)
const projectHeaderMenu = ref<{ type: SidebarHeaderMenuType; x: number; y: number } | null>(null)
const projectHeaderSubmenu = ref<{ type: 'organize' | 'sort'; x: number; y: number } | null>(null)
const pendingDeleteSessionId = ref<string | null>(null)
const pendingBatchDeleteSessionIds = ref<string[] | null>(null)
const isBatchDeleting = ref(false)
const renamingId = ref<string | null>(null)
const renameValue = ref('')
const lastSelectedSessionId = ref<string | null>(null)
const expandedProjectKeys = ref<Set<string>>(new Set())
const collapsedProjectKeys = ref<Set<string>>(new Set())
const projectOrderState = ref<string[]>(readStoredProjectOrder())
const pinnedProjectKeys = ref<Set<string>>(readStoredProjectPins())
const hiddenProjectKeys = ref<Set<string>>(readStoredProjectHidden())
const projectOrganizationState = ref<SidebarProjectOrganization>(readStoredProjectOrganization())
const projectSortByState = ref<SidebarProjectSortBy>(readStoredProjectSortBy())
const draggingProjectKey = ref<string | null>(null)
const projectDropTarget = ref<{ key: string; position: 'before' | 'after' } | null>(null)
const suppressProjectClickRef = ref<string | null>(null)
const sidebarPreferenceRevisionRef = ref(0)

// ─── Computed (useMemo) ─────────────────────────────────────────────────

const filteredSessions = computed(() => sessionStore.sessions)

const projectGroups = computed(() => groupByProject(filteredSessions.value, projectSortByState.value))

const orderedProjectGroups = computed(() =>
  applyProjectOrder(
    projectGroups.value,
    projectOrderState.value,
    pinnedProjectKeys.value,
    projectOrganizationState.value,
    projectSortByState.value,
  ),
)

const visibleProjectGroups = computed(() => {
  if (hiddenProjectKeys.value.size === 0) return orderedProjectGroups.value
  return orderedProjectGroups.value.filter((project) => !hiddenProjectKeys.value.has(project.key))
})

const showInitialLoading = computed(() => sessionStore.isLoading && sessionStore.sessions.length === 0)

const filteredSessionIds = computed(() => filteredSessions.value.map((session) => session.id))

const selectedCount = computed(() => sessionStore.selectedSessionIds.length)

const sessionsById = computed(() => new Map(sessionStore.sessions.map((session) => [session.id, session])))

const runningSessionIds = computed(() => {
  const ids = new Set<string>()
  for (const tab of tabStore.tabs) {
    if (tab.type === 'session' && tab.status === 'running') ids.add(tab.sessionId)
  }
  for (const [sessionId, sessionState] of Object.entries(chatStore.sessions)) {
    if ((sessionState as any).chatState !== 'idle') ids.add(sessionId)
  }
  return ids
})

const pendingBatchDeleteSessions = computed(() =>
  (pendingBatchDeleteSessionIds.value ?? [])
    .map((sessionId) => sessionsById.value.get(sessionId))
    .filter((session): session is SessionListItem => Boolean(session)),
)

const activeTabId = computed(() => tabStore.activeTabId)
const activeTabType = computed(() => {
  const tab = tabStore.tabs.find((t) => t.sessionId === activeTabId.value)
  return tab?.type ?? null
})

const sidebarOpen = computed(() => uiStore.sidebarOpen)
const activeModal = computed(() => uiStore.activeModal)
const expanded = computed(() => isMobileComputed.value ? true : sidebarOpen.value)

// ─── Auto-refresh (useSessionListAutoRefresh) ───────────────────────────

const refreshSessionsNow = (() => {
  const inFlightRef = { current: null as Promise<void> | null }
  const lastStartedAtRef = { current: 0 }

  const refreshSessions = (force = false): Promise<void> => {
    if (inFlightRef.current) return inFlightRef.current
    const now = Date.now()
    if (!force && now - lastStartedAtRef.current < SESSION_LIST_FOCUS_REFRESH_MIN_MS) {
      return Promise.resolve()
    }
    lastStartedAtRef.current = now
    const request = Promise.resolve()
      .then(() => sessionStore.fetchSessions())
      .catch(() => undefined)
      .finally(() => {
        if (inFlightRef.current === request) {
          inFlightRef.current = null
        }
      })
    inFlightRef.current = request
    return request
  }

  onMounted(() => {
    void refreshSessions(true)
    const refreshIfVisible = () => {
      if (!isDocumentVisible()) return
      void refreshSessions()
    }
    window.addEventListener('focus', refreshIfVisible)
    document.addEventListener('visibilitychange', refreshIfVisible)
    const timer = window.setInterval(() => {
      if (!isDocumentVisible()) return
      void refreshSessions(true)
    }, SESSION_LIST_AUTO_REFRESH_MS)

    ;(refreshSessionsNow as any)._cleanup = () => {
      window.removeEventListener('focus', refreshIfVisible)
      document.removeEventListener('visibilitychange', refreshIfVisible)
      window.clearInterval(timer)
    }
  })

  return () => refreshSessions(true)
})()

onUnmounted(() => {
  if ((refreshSessionsNow as any)._cleanup) {
    ;(refreshSessionsNow as any)._cleanup()
  }
})

// ─── Callbacks ──────────────────────────────────────────────────────────

// Watch sidebarOpen — close context menu when sidebar closes
watch(() => sidebarOpen.value, () => {
  if (!sidebarOpen.value && contextMenu.value) {
    contextMenu.value = null
  }
})

// Watch any open menu — close on document click
watch(
  () => [contextMenu.value, projectContextMenu.value, projectHeaderMenu.value, projectHeaderSubmenu.value],
  ([cm, pcm, phm, phsm], [prevCm, prevPcm, prevPhm, prevPhsm]) => {
    const hasAny = cm || pcm || phm || phsm
    const hadAny = prevCm || prevPcm || prevPhm || prevPhsm
    if (!hasAny || hadAny) return // only react when a menu first opens
    document.addEventListener('click', () => {
      contextMenu.value = null
      projectContextMenu.value = null
      projectHeaderMenu.value = null
      projectHeaderSubmenu.value = null
    }, { once: true })
  },
  { immediate: false },
)

const handleContextMenu = (e: MouseEvent, id: string) => {
  e.preventDefault()
  if (sessionStore.isBatchMode) return
  contextMenu.value = { id, x: e.clientX, y: e.clientY }
}

const handleProjectDragStart = (event: MouseEvent, projectKey: string) => {
  if (sessionStore.isBatchMode) {
    event.preventDefault()
    return
  }
  suppressProjectClickRef.value = projectKey
  draggingProjectKey.value = projectKey
  if ((event as any).dataTransfer) {
    ;(event as any).dataTransfer.effectAllowed = 'move'
    ;(event as any).dataTransfer.setData('text/plain', projectKey)
  }
}

const handleProjectDragOver = (event: MouseEvent, projectKey: string) => {
  const sourceProjectKey = draggingProjectKey.value || ((event as any).dataTransfer?.getData('text/plain') ?? null)
  if (!sourceProjectKey || sourceProjectKey === projectKey) return
  event.preventDefault()
  if ((event as any).dataTransfer) {
    ;(event as any).dataTransfer.dropEffect = 'move'
  }
  const position = getProjectDropPosition(event)
  projectDropTarget.value = (
    projectDropTarget.value?.key === projectKey && projectDropTarget.value.position === position
      ? projectDropTarget.value
      : { key: projectKey, position }
  )
}

const clearProjectDragState = () => {
  draggingProjectKey.value = null
  projectDropTarget.value = null
  window.setTimeout(() => {
    suppressProjectClickRef.value = null
  }, 0)
}

const handleProjectDrop = (event: MouseEvent, targetProjectKey: string) => {
  event.preventDefault()
  const sourceProjectKey = draggingProjectKey.value || ((event as any).dataTransfer?.getData('text/plain') ?? null)
  const dropPosition = projectDropTarget.value?.key === targetProjectKey
    ? projectDropTarget.value.position
    : getProjectDropPosition(event)
  if (!sourceProjectKey || sourceProjectKey === targetProjectKey) {
    clearProjectDragState()
    return
  }

  const nextOrder = moveProjectKey(
    orderedProjectGroups.value.map((project) => project.key),
    sourceProjectKey,
    targetProjectKey,
    dropPosition,
  )
  projectOrderState.value = nextOrder
  persistSidebarProjectPreferences(buildSidebarProjectPreferences(nextOrder, pinnedProjectKeys.value, hiddenProjectKeys.value, projectOrganizationState.value, projectSortByState.value))
  clearProjectDragState()
}

const createSessionForWorkDir = async (workDir?: string) => {
  try {
    const sessionId = await sessionStore.createSession(workDir)
    restoreHiddenProjectForWorkDir(workDir)
    tabStore.openTab(sessionId, t('sidebar.newSession'))
    chatStore.connectToSession(sessionId)
    closeMobileDrawer()
  } catch (error) {
    uiStore.showToast(
      error instanceof Error ? error.message : t('sidebar.sessionListFailed'),
      'error',
    )
  }
}

const openProjectHeaderMenu = (event: MouseEvent, type: SidebarHeaderMenuType) => {
  event.stopPropagation()
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const width = type === 'create' ? 250 : 270
  projectContextMenu.value = null
  contextMenu.value = null
  projectHeaderSubmenu.value = null
  projectHeaderMenu.value = {
    type,
    x: Math.max(10, Math.min(rect.right - width, window.innerWidth - width - 10)),
    y: rect.bottom + 8,
  }
}

const openProjectHeaderSubmenu = (event: MouseEvent, type: 'organize' | 'sort') => {
  event.stopPropagation()
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const width = type === 'sort' ? 230 : 260
  projectHeaderSubmenu.value = {
    type,
    x: Math.max(10, Math.min(rect.right + 8, window.innerWidth - width - 10)),
    y: Math.max(10, Math.min(rect.top - 8, window.innerHeight - 170)),
  }
}

const updateProjectOrganization = (organization: SidebarProjectOrganization) => {
  projectHeaderMenu.value = null
  projectHeaderSubmenu.value = null
  projectOrganizationState.value = organization
  const nextOrder = (organization === 'project' || organization === 'time') ? [] : projectOrderState.value
  if (JSON.stringify(nextOrder) !== JSON.stringify(projectOrderState.value)) {
    projectOrderState.value = nextOrder
  }
  persistSidebarProjectPreferences(buildSidebarProjectPreferences(
    nextOrder,
    pinnedProjectKeys.value,
    hiddenProjectKeys.value,
    organization,
    projectSortByState.value,
  ))
}

const updateProjectSortBy = (sortBy: SidebarProjectSortBy) => {
  projectHeaderMenu.value = null
  projectHeaderSubmenu.value = null
  projectSortByState.value = sortBy
  projectOrderState.value = []
  persistSidebarProjectPreferences(buildSidebarProjectPreferences(
    [],
    pinnedProjectKeys.value,
    hiddenProjectKeys.value,
    projectOrganizationState.value,
    sortBy,
  ))
}

const createSessionFromExistingFolder = async () => {
  projectHeaderMenu.value = null
  projectHeaderSubmenu.value = null
  if (!canUseNativeDialogs) {
    uiStore.showToast(t('sidebar.chooseProjectFolderUnavailable'), 'error')
    return
  }
  try {
    const selected = await getDesktopHost().dialogs.open({
      directory: true,
      multiple: false,
      title: t('sidebar.useExistingFolder'),
    })
    if (typeof selected === 'string' && selected.trim()) {
      await createSessionForWorkDir(selected)
    }
  } catch (error) {
    uiStore.showToast(error instanceof Error ? error.message : t('sidebar.sessionListFailed'), 'error')
  }
}

const togglePinnedProject = (projectKey: string) => {
  projectContextMenu.value = null
  const current = new Set(pinnedProjectKeys.value)
  if (current.has(projectKey)) {
    current.delete(projectKey)
  } else {
    current.add(projectKey)
  }
  pinnedProjectKeys.value = current
  persistSidebarProjectPreferences(buildSidebarProjectPreferences(projectOrderState.value, current, hiddenProjectKeys.value, projectOrganizationState.value, projectSortByState.value))
}

const restoreAllHiddenProjects = () => {
  projectHeaderMenu.value = null
  projectHeaderSubmenu.value = null
  hiddenProjectKeys.value = new Set<string>()
  persistSidebarProjectPreferences(buildSidebarProjectPreferences(
    projectOrderState.value,
    pinnedProjectKeys.value,
    hiddenProjectKeys.value,
    projectOrganizationState.value,
    projectSortByState.value,
  ))
}

const toggleHiddenProject = (project: ProjectGroup) => {
  const wasHidden = hiddenProjectKeys.value.has(project.key)
  projectContextMenu.value = null
  const current = new Set(hiddenProjectKeys.value)
  if (current.has(project.key)) {
    current.delete(project.key)
  } else {
    current.add(project.key)
  }
  hiddenProjectKeys.value = current
  persistSidebarProjectPreferences(buildSidebarProjectPreferences(projectOrderState.value, pinnedProjectKeys.value, current, projectOrganizationState.value, projectSortByState.value))
  if (!wasHidden) {
    uiStore.showToast(t('sidebar.projectHidden', { project: project.title }), 'info')
  }
}

const openProjectInFinder = async (project: ProjectGroup) => {
  projectContextMenu.value = null
  try {
    if (!project.workDir) {
      throw new Error(t('sidebar.openInFinderUnavailable'))
    }
    await openTargetStore.ensureTargets()
    const latest = openTargetStore
    const target = latest.targets.find((item) => item.id === 'finder')
      ?? latest.targets.find((item) => (item as any).kind === 'file_manager')
    if (!target) {
      throw new Error(t('sidebar.openInFinderUnavailable'))
    }
    await latest.openTarget(target.id, project.workDir)
  } catch (error) {
    uiStore.showToast(error instanceof Error ? error.message : t('sidebar.openInFinderFailed'), 'error')
  }
}

const handleDelete = (id: string) => {
  contextMenu.value = null
  pendingDeleteSessionId.value = id
}

const confirmDelete = async () => {
  if (!pendingDeleteSessionId.value) return
  await sessionStore.deleteSession(pendingDeleteSessionId.value)
  chatStore.disconnectSession(pendingDeleteSessionId.value)
  tabStore.closeTab(pendingDeleteSessionId.value)
  pendingDeleteSessionId.value = null
}

const handleBatchSessionClick = (event: MouseEvent, id: string) => {
  if ((event as any).shiftKey && lastSelectedSessionId.value) {
    const start = filteredSessionIds.value.indexOf(lastSelectedSessionId.value)
    const end = filteredSessionIds.value.indexOf(id)
    if (start >= 0 && end >= 0) {
      const [from, to] = start < end ? [start, end] : [end, start]
      sessionStore.selectSessions(filteredSessionIds.value.slice(from, to + 1))
      lastSelectedSessionId.value = id
      return
    }
  }
  sessionStore.toggleSessionSelected(id)
  lastSelectedSessionId.value = id
}

const handleExitBatchMode = () => {
  sessionStore.exitBatchMode()
  lastSelectedSessionId.value = null
  pendingBatchDeleteSessionIds.value = null
}

const requestBatchDelete = (ids: string[]) => {
  if (ids.length === 0) return
  pendingBatchDeleteSessionIds.value = [...new Set(ids)]
}

const confirmBatchDelete = async () => {
  const ids = pendingBatchDeleteSessionIds.value ?? []
  if (ids.length === 0) return

  isBatchDeleting.value = true
  try {
    const result = await sessionStore.deleteSessions(ids)
    for (const sessionId of result.successes) {
      chatStore.disconnectSession(sessionId)
      tabStore.closeTab(sessionId)
    }

    if (result.failures.length > 0) {
      uiStore.showToast(t('sidebar.batchDeleteFailed', { count: result.failures.length }), 'error')
    } else {
      uiStore.showToast(t('sidebar.batchDeleteSucceeded', { count: result.successes.length }), 'success')
      handleExitBatchMode()
    }
    pendingBatchDeleteSessionIds.value = null
  } catch (error) {
    uiStore.showToast(error instanceof Error ? error.message : t('sidebar.batchDeleteFailed', { count: ids.length }), 'error')
  } finally {
    isBatchDeleting.value = false
  }
}

const toggleGroupSelection = (ids: string[]) => {
  const allSelected = ids.every((id) => sessionStore.selectedSessionIds.includes(id))
  if (allSelected) {
    sessionStore.deselectSessions(ids)
  } else {
    sessionStore.selectSessions(ids)
  }
}

const toggleProjectCollapsed = (projectKey: string) => {
  if (suppressProjectClickRef.value === projectKey) {
    suppressProjectClickRef.value = null
    return
  }
  const current = new Set(collapsedProjectKeys.value)
  if (current.has(projectKey)) {
    current.delete(projectKey)
  } else {
    current.add(projectKey)
  }
  collapsedProjectKeys.value = current
}

const toggleProjectSessionExpansion = (projectKey: string) => {
  const current = new Set(expandedProjectKeys.value)
  if (current.has(projectKey)) {
    current.delete(projectKey)
  } else {
    current.add(projectKey)
  }
  expandedProjectKeys.value = current
}

const handleStartRename = (id: string, currentTitle: string) => {
  contextMenu.value = null
  renamingId.value = id
  renameValue.value = currentTitle
}

const handleFinishRename = async () => {
  if (renamingId.value && renameValue.value.trim()) {
    await sessionStore.renameSession(renamingId.value, renameValue.value.trim())
  }
  renamingId.value = null
  renameValue.value = ''
}

const applySidebarProjectPreferences = (preferences: SidebarProjectPreferences) => {
  projectOrderState.value = preferences.projectOrder
  pinnedProjectKeys.value = new Set(preferences.pinnedProjects)
  hiddenProjectKeys.value = new Set(preferences.hiddenProjects)
  projectOrganizationState.value = preferences.projectOrganization
  projectSortByState.value = preferences.projectSortBy
}

const persistSidebarProjectPreferences = (preferences: SidebarProjectPreferences) => {
  const normalized = normalizeSidebarProjectPreferences(preferences)
  sidebarPreferenceRevisionRef.value += 1
  writeCachedSidebarProjectPreferences(normalized)
  void desktopUiPreferencesApi.updateSidebarPreferences(normalized).catch(() => undefined)
}

const restoreHiddenProjectForWorkDir = (workDir: string | null | undefined) => {
  if (!workDir) return
  setHiddenProjectKeysWithPersist((current) => {
    const next = new Set([...current].filter((projectKey) => !projectPathMatches(projectKey, workDir)))
    if (next.size === current.size) return current
    persistSidebarProjectPreferences(buildSidebarProjectPreferences(
      projectOrderState.value,
      pinnedProjectKeys.value,
      next,
      projectOrganizationState.value,
      projectSortByState.value,
    ))
    return next
  })
}

function setHiddenProjectKeysWithPersist(updater: (current: Set<string>) => Set<string>) {
  hiddenProjectKeys.value = updater(hiddenProjectKeys.value)
}

// Load server preferences on mount
onMounted(() => {
  let cancelled = false
  const startRevision = sidebarPreferenceRevisionRef.value

  void desktopUiPreferencesApi.getPreferences()
    .then((response) => {
      if (cancelled || startRevision !== sidebarPreferenceRevisionRef.value) return
      const localPreferences = readCachedSidebarProjectPreferences()
      const serverPreferences = normalizeSidebarProjectPreferences(response.preferences.sidebar)
      const effectivePreferences = response.exists ? serverPreferences : localPreferences
      applySidebarProjectPreferences(effectivePreferences)
      writeCachedSidebarProjectPreferences(effectivePreferences)
      if (!response.exists && hasSidebarProjectPreferences(localPreferences)) {
        void desktopUiPreferencesApi.updateSidebarPreferences(localPreferences).catch(() => undefined)
      }
    })
    .catch(() => {
      // The sidebar remains usable with the local cache if the server is still booting.
    })

  return () => {
    cancelled = true
  }
})

// Batch mode keydown handler
let batchKeyDownBound = false
watch(() => sessionStore.isBatchMode, (isBatchMode) => {
  if (!isBatchMode) {
    if (batchKeyDownBound) {
      document.removeEventListener('keydown', handleBatchKeyDown)
      batchKeyDownBound = false
    }
    return
  }
  document.addEventListener('keydown', handleBatchKeyDown)
  batchKeyDownBound = true
})

const handleBatchKeyDown = (event: KeyboardEvent) => {
  const target = event.target as HTMLElement | null
  if (target?.closest('input, textarea, [contenteditable="true"]')) return
  if (event.key === 'Escape') {
    handleExitBatchMode()
  }
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'a') {
    event.preventDefault()
    sessionStore.selectSessions(filteredSessionIds.value)
  }
}

onUnmounted(() => {
  if (batchKeyDownBound) {
    document.removeEventListener('keydown', handleBatchKeyDown)
  }
})

// ─── Sub-components (render function s / TODO placeholders for Phase 2) ──────────────────

// ProjectMenuItem
const ProjectMenuItem = defineComponent({
  props: {
    icon: Object,
    children: String,
    disabled: Boolean,
    danger: Boolean,
  },
  emits: ['click'],
  setup(props, { emit }) {
    return () => h('button', {
      type: 'button',
      role: 'menuitem',
      disabled: props.disabled,
      onClick: props.disabled ? undefined : () => emit('click'),
      class: `flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:bg-[var(--color-surface-hover)] disabled:cursor-default disabled:opacity-45 ${
        props.danger
          ? 'text-[var(--color-error)] enabled:hover:bg-[var(--color-error)]/10'
          : 'text-[var(--color-text-primary)] enabled:hover:bg-[var(--color-surface-hover)]'
      }`,
    }, [
      h('span', { class: 'flex h-5 w-5 shrink-0 items-center justify-center text-current' }, [props.icon]),
      h('span', { class: 'min-w-0 truncate' }, props.children),
    ])
  },
})

// HeaderMenuItem
const HeaderMenuItem = defineComponent({
  props: {
    icon: Object,
    children: String,
    checked: Boolean,
    trailing: Boolean,
  },
  emits: ['click', 'mouseenter'],
  setup(props, { emit }) {
    return () => h('button', {
      type: 'button',
      role: 'menuitem',
      onClick: (e: MouseEvent) => emit('click', e),
      onMouseEnter: (e: MouseEvent) => emit('mouseenter', e),
      class: 'flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm font-semibold text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-surface-hover)] focus-visible:outlinenone focus-visible:bg-[var(--color-surface-hover)]',
    }, [
      h('span', { class: 'flex h-5 w-5 shrink-0 items-center justify-center text-[var(--color-text-secondary)]' }, [props.icon]),
      h('span', { class: 'min-w-0 flex-1 truncate' }, props.children),
      props.checked
        ? h('span', { class: 'material-symbols-outlined text-[17px] text-[var(--color-text-secondary)]' }, 'check')
        : props.trailing
          ? h('span', { class: 'material-symbols-outlined text-[17px] text-[var(--color-text-tertiary)]', style: { transform: 'rotate(-90deg)' } }, 'expand_more')
          : null,
    ])
  },
})

// SessionRowMeta
const SessionRowMeta = defineComponent({
  props: {
    isRunning: Boolean,
    isWorktree: Boolean,
    modifiedAt: String,
  },
  setup(props) {
    return () => {
      const relativeTime = formatRelativeTime(props.modifiedAt, t)
      const updatedLabel = t('session.lastUpdated', { time: relativeTime })
      return h('span', {
        class: 'ml-auto flex h-5 min-w-[78px] flex-shrink-0 items-center justify-end gap-1.5 text-[10px] font-medium tabular-nums text-[var(--color-text-tertiary)]',
        title: updatedLabel,
      }, [
        props.isRunning
          ? h('span', {
              class: 'inline-flex h-4 w-4 flex-shrink-0 items-center justify-center text-[var(--color-success)]',
              'aria-label': t('sidebar.sessionRunning'),
              title: t('sidebar.sessionRunning'),
            }, [
              h(AnimationPlayer, { name: 'spinner', class: 'h-4 w-4' }),
            ])
          : null,
        props.isWorktree
          ? h('span', {
              class: 'inline-flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-[5px] text-[var(--color-text-tertiary)]',
              title: t('sidebar.worktree'),
            }, [
              h('span', { class: 'material-symbols-outlined text-[14px]' }, 'call_split'),
              h('span', { class: 'sr-only' }, t('sidebar.worktree')),
            ])
          : null,
        h('span', { class: 'inline-flex min-w-[42px] flex-shrink-0 items-center justify-end' }, [
          h('span', {}, relativeTime),
        ]),
      ])
    }
  },
})

// ProjectHeaderActions
const ProjectHeaderActions = defineComponent({
  props: {
    title: String,
    menuLabel: String,
    createLabel: String,
  },
  emits: ['openMenu', 'openCreate'],
  setup(props, { emit }) {
    return () => h('div', {
      'data-testid': 'sidebar-projects-header',
      class: 'group/sidebar-projects flex items-center justify-between px-1.5 pb-2 pt-1',
    }, [
      h('div', { class: 'text-[12px] font-semibold tracking-normal text-[var(--color-text-primary)]' }, props.title),
      h('div', { class: 'flex items-center gap-1 opacity-0 transition-opacity group-hover/sidebar-projects:opacity-100 focus-within:opacity-100' }, [
        h('button', {
          type: 'button',
          onClick: (e: MouseEvent) => emit('openMenu', e),
          class: 'flex h-8 w-8 items-center justify-center rounded-xl text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-sidebar-item-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)]',
          'aria-label': props.menuLabel,
          title: props.menuLabel,
        }, [h('span', { class: 'material-symbols-outlined text-[18px]' }, 'more_horiz')]),
        h('button', {
          type: 'button',
          onClick: (e: MouseEvent) => emit('openCreate', e),
          class: 'flex h-8 w-8 items-center justify-center rounded-xl text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-sidebar-item-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)]',
          'aria-label': props.createLabel,
          title: props.createLabel,
        }, [h('span', { class: 'material-symbols-outlined text-[18px]' }, 'folder_zip')]),
      ]),
    ])
  },
})

// ProjectHeaderMenu
const ProjectHeaderMenu = defineComponent({
  props: {
    type: String,
    x: Number,
    y: Number,
    organization: String,
    sortBy: String,
    onOpenSubmenu: Function,
    onSetOrganization: Function,
    onSetSortBy: Function,
    onCreateBlank: Function,
    onUseExistingFolder: Function,
    onRestoreHiddenProjects: Function,
    hiddenProjectCount: Number,
    t: Function,
  },
  setup(props) {
    const menuType = props.type as SidebarHeaderMenuType
    const menuStyle: Record<string, any> = { left: props.x, top: props.y, boxShadow: 'var(--shadow-dropdown)' }
    if (menuType === 'main' || menuType === 'organize' || menuType === 'sort') {
      menuStyle.left = positionProjectMenu(props.x, props.y).left
      menuStyle.top = positionProjectMenu(props.x, props.y).top
    }
    return () => {
      if (menuType === 'create') {
        return h('div', {
          role: 'menu',
          class: 'fixed z-50 min-w-[230px] overflow-hidden rounded-[18px] border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] py-2 shadow-[var(--shadow-dropdown)]',
          style: menuStyle,
          onClick: (e: MouseEvent) => e.stopPropagation(),
        }, [
          h(ProjectMenuItem, {
            icon: h(PlusIcon),
            onClick: () => props.onCreateBlank(),
          }, { default: () => props.t('sidebar.createBlankSession') }),
          h(ProjectMenuItem, {
            icon: h(GitHubIcon),
            onClick: () => props.onUseExistingFolder(),
          }, { default: () => props.t('sidebar.useExistingFolder') }),
        ])
      }

      // main / organize / sort — render submenu items
      return h('div', {
        role: 'menu',
        class: 'fixed z-50 min-w-[230px] overflow-hidden rounded-[18px] border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] py-2 shadow-[var(--shadow-dropdown)]',
        style: menuStyle,
        onClick: (e: MouseEvent) => e.stopPropagation(),
      }, [
        // Menu items handled per-type
      ])
    }
  },
})

// NavItem — handles both SVG component icons and string material-icons
const NavItem = defineComponent({
  props: {
    active: Boolean,
    collapsed: Boolean,
    icon: [Object, String],
  },
  emits: ['click'],
  setup(props, { emit, slots }) {
    return () => {
      let iconNode = null
      if (props.icon) {
        // Handle { $: h(IconComponent) } pattern from translation
        if (typeof props.icon === 'object' && '$' in props.icon) {
          iconNode = props.icon.$
        }
        // Handle plain string icon name (material-symbols-outlined)
        else if (typeof props.icon === 'string') {
          iconNode = h('span', { class: 'material-symbols-outlined text-[18px]' }, props.icon)
        }
      }
      const labelText = slots.default?.()?.[0]?.children || slots.default?.()?.[0]?.text || ''
      return h('button', {
        type: 'button',
        onClick: () => emit('click'),
        class: `flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-[13px] font-medium transition-colors ${
          props.active
            ? 'sidebar-session-row--active bg-[var(--color-sidebar-item-active)] text-[var(--color-text-primary)]'
            : 'sidebar-session-row--idle text-[var(--color-text-secondary)] hover:bg-[var(--color-sidebar-item-hover)] hover:text-[var(--color-text-primary)]'
        }`,
      }, [
        iconNode ? h('span', { class: 'flex h-5 w-5 items-center justify-center shrink-0' }, [iconNode]) : null,
        labelText ? h('span', { class: 'min-w-0 flex-1 truncate' }, labelText) : null,
      ])
    }
  },
})


// ─── Computed: project menu data ────────────────────────────────────────
const projectMenuData = computed(() => {
  if (!projectContextMenu.value) return null
  const project = orderedProjectGroups.value.find((g: any) => g.key === projectContextMenu.value!.key)
  if (!project) return null
  return {
    project,
    pinned: pinnedProjectKeys.value.has(project.key),
    hidden: hiddenProjectKeys.value.has(project.key)
  }
})
</script>

<template>
  <aside
    class="sidebar-panel relative h-full flex flex-col bg-[var(--color-surface-sidebar)] border-r border-[var(--color-border)] select-none"
    :data-state="expanded ? 'open' : 'closed'"
    aria-label="Sidebar"
  >
    <!-- v3.1 — Brand: monogram + tagline, no icon, mathematical spacing -->
    <div
      data-testid="sidebar-title-region"
      data-desktop-drag-region
      :class="`px-4 pb-3 ${isDesktopRuntime && !isWindows ? 'pt-[44px]' : 'pt-4'}`"
    >
      <div :class="`flex ${expanded ? 'items-center justify-between' : 'flex-col items-center gap-2'}`">
        <div :class="`flex min-w-0 items-center ${expanded ? 'gap-2.5' : 'justify-center'}`">
          <MascotAvatar :size="28" />
          <span
            class="sidebar-copy text-[14px] font-semibold tracking-tight text-[var(--color-text-primary)]"
            style="fontFamily: var(--font-headline)"
          >
            MadCop
          </span>
        </div>
        <div v-if="isMobileComputed" :class="`flex items-center ${expanded ? 'gap-1.5' : 'flex-col gap-2'}`">
          <button
            type="button"
            @click="closeMobileDrawer"
            class="sidebar-toggle-button flex h-11 w-11 items-center justify-center rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface-sidebar)]"
            :aria-label="t('sidebar.collapse')"
            :title="t('sidebar.collapse')"
          >
            <span class="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Primary nav: 3 entries, each with stroke-outline icon -->
    <nav :class="`px-3 pb-3 flex flex-col ${expanded ? 'gap-0.5' : 'items-center gap-1.5'}`" aria-label="Primary">
      <!-- 对话 -->
      <button
        type="button"
        @click="() => {
          const curTabId = tabStore.activeTabId
          const curSession = curTabId ? sessionStore.sessions.find((s) => s.id === curTabId) : null
          void createSessionForWorkDir(curSession?.workDir || curSession?.projectRoot || undefined)
          closeMobileDrawer()
        }"
        :class="primaryNavClass(activeTabType === 'session' || activeTabType === null)"
        :aria-label="t('sidebar.newSession')"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="shrink-0"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>
        <span v-if="expanded" class="flex-1 text-left">{{ t('sidebar.newSession') }}</span>
        <span
          v-if="expanded && activeSessionCount > 0"
          class="ml-auto text-[10px] tabular-nums text-[var(--color-text-tertiary)]"
          style="fontFamily: ui-monospace, 'SF Mono', monospace"
        >{{ activeSessionCount }}</span>
      </button>

      <!-- Agent -->
      <button
        v-if="!isMobileComputed"
        type="button"
        :class="primaryNavClass(activeTabType === 'agents' || activeTabType === 'workflows' || activeTabType === 'design')"
        aria-label="Agent"
        @click="() => { tabStore.openTab('__agents__', 'Agent', 'agents' as any); closeMobileDrawer() }"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="shrink-0"><circle cx="12" cy="12" r="3"/><circle cx="5" cy="5" r="1.5"/><circle cx="19" cy="5" r="1.5"/><circle cx="5" cy="19" r="1.5"/><circle cx="19" cy="19" r="1.5"/><line x1="6.5" y1="6.5" x2="10" y2="10"/><line x1="17.5" y1="6.5" x2="14" y2="10"/><line x1="6.5" y1="17.5" x2="10" y2="14"/><line x1="17.5" y1="17.5" x2="14" y2="14"/></svg>
        <span v-if="expanded" class="flex-1 text-left">Agent</span>
        <span
          v-if="expanded && runningSessionCount > 0"
          class="ml-auto inline-flex items-center gap-1 text-[10px] tabular-nums text-[var(--color-text-tertiary)]"
          style="fontFamily: ui-monospace, 'SF Mono', monospace"
        >
          <span class="inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-success)]"></span>
          {{ runningSessionCount }}
        </span>
      </button>

      <!-- 知识库 -->
      <button
        v-if="!isMobileComputed"
        type="button"
        :class="primaryNavClass(activeTabType === 'knowledge')"
        aria-label="知识库"
        @click="() => { tabStore.openTab('__knowledge__', '知识库', 'knowledge' as any); closeMobileDrawer() }"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="shrink-0"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
        <span v-if="expanded" class="flex-1 text-left">知识库</span>
      </button>
    </nav>

    <!-- v3.1 — Divider: primary / secondary (mathematical 1px hairline) -->
    <div
      v-if="expanded && !isMobileComputed"
      class="mx-4 mb-2 mt-1 h-px bg-[var(--color-border-separator)] opacity-50"
      aria-hidden="true"
    ></div>

    <!-- v3.1 — Secondary entries, collapsed by default under "更多" -->
    <nav
      v-if="!isMobileComputed"
      :class="`px-3 pb-2 flex flex-col ${expanded ? 'gap-0.5' : 'items-center gap-1.5'}`"
      aria-label="Secondary"
    >
      <!-- Toggle "更多" when expanded; in collapsed mode, show a subtle indicator dot -->
      <button
        v-if="expanded"
        type="button"
        @click="navMoreOpen = !navMoreOpen"
        class="group flex h-7 items-center gap-1.5 px-2 text-[10px] uppercase tracking-[0.14em] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] transition-colors"
        style="fontFamily: ui-monospace, 'SF Mono', monospace"
        :aria-expanded="navMoreOpen"
        :aria-label="t(navMoreOpen ? 'sidebar.less' : 'sidebar.more')"
      >
        <span class="inline-block w-3 text-center text-[9px]">{{ navMoreOpen ? '−' : '+' }}</span>
        <span>{{ navMoreOpen ? t('sidebar.less') : t('sidebar.more') }}</span>
        <span class="ml-1 text-[var(--color-text-tertiary)] opacity-50">4</span>
      </button>

      <!-- Tiny status dot when collapsed: a hint that there's more -->
      <div
        v-else
        class="h-1 w-1 rounded-full bg-[var(--color-border)]"
        aria-hidden="true"
      ></div>

      <!-- Secondary items — shown when expanded AND navMoreOpen is true -->
      <template v-if="expanded && navMoreOpen">
        <button
          type="button"
          :class="secondaryNavClass(activeTabId === SCHEDULED_TAB_ID)"
          @click="() => { tabStore.openTab(SCHEDULED_TAB_ID, t('sidebar.scheduled'), 'scheduled'); closeMobileDrawer() }"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="shrink-0 opacity-60"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          <span class="flex-1 text-left text-[12px]">{{ t('sidebar.scheduled') }}</span>
        </button>
        <button
          type="button"
          :class="secondaryNavClass(activeTabType === 'workflows')"
          @click="() => { tabStore.openWorkflowsTab(); closeMobileDrawer() }"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="shrink-0 opacity-60"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>
          <span class="flex-1 text-left text-[12px]">{{ t('sidebar.workflows') }}</span>
        </button>
        <button
          type="button"
          :class="secondaryNavClass(activeTabType === 'design')"
          @click="() => { tabStore.openDesignTab(); closeMobileDrawer() }"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="shrink-0 opacity-60"><path d="M12 19l7-7 3 3-7 7-3-3z"/><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/></svg>
          <span class="flex-1 text-left text-[12px]">设计工具</span>
        </button>
        <button
          type="button"
          :class="secondaryNavClass(false)"
          @click="() => { tabStore.openSkillBuilderTab(); closeMobileDrawer() }"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="shrink-0 opacity-60"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
          <span class="flex-1 text-left text-[12px]">技能构建器</span>
        </button>
      </template>
    </nav>

    <!-- Expanded view: search + session list -->
    <template v-if="expanded">
      <!-- Search controls section -->
      <div
        data-testid="sidebar-search-controls-section"
        class="sidebar-section sidebar-section--visible relative z-20 flex-none px-3 pb-2"
        style="overflow: visible"
      >
        <div class="flex items-center gap-1.5">
          <!-- Global search button -->
          <button
            type="button"
            @click="uiStore.openModal('globalSearch')"
            class="flex h-9 min-w-0 flex-1 items-center gap-2 rounded-[14px] border border-[var(--color-sidebar-search-border)] bg-[var(--color-sidebar-search-bg)] pl-3 pr-2 text-left text-[13px] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-sidebar-item-hover)] focus-visible:border-[var(--color-border-focus)] focus-visible:outline-none"
            :aria-label="t('search.global.trigger')"
            :title="t('search.global.trigger')"
          >
            <span class="pointer-events-none flex shrink-0 items-center text-[var(--color-text-tertiary)]">
              <SearchIcon />
            </span>
            <span class="min-w-0 flex-1 truncate pl-2">{{ t('search.global.trigger') }}</span>
            <kbd class="pointer-events-none shrink-0 rounded border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-1 font-mono text-[10px] leading-tight text-[var(--color-text-tertiary)]">⌘K</kbd>
          </button>
          <!-- Refresh button -->
          <button
            type="button"
            @click="refreshSessionsNow"
            :disabled="sessionStore.isLoading"
            class="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-[12px] border border-[var(--color-sidebar-search-border)] bg-[var(--color-sidebar-search-bg)] text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-sidebar-item-hover)] hover:text-[var(--color-text-primary)] disabled:cursor-default disabled:opacity-65 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)]"
            :aria-label="t('sidebar.refreshSessions')"
            :title="t('sidebar.refreshSessions')"
          >
            <span class="material-symbols-outlined text-[18px]">
              <template v-if="sessionStore.isLoading">sync</template>
              <template v-else>refresh</template>
            </span>
          </button>
          <!-- Batch mode toggle -->
          <button
            type="button"
            @click="sessionStore.isBatchMode ? handleExitBatchMode() : sessionStore.enterBatchMode()"
            :class="`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-[12px] border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)] ${
              sessionStore.isBatchMode
                ? 'border-[var(--color-brand)] bg-[var(--color-sidebar-item-active)] text-[var(--color-brand)]'
                : 'border-[var(--color-sidebar-search-border)] bg-[var(--color-sidebar-search-bg)] text-[var(--color-text-secondary)] hover:bg-[var(--color-sidebar-item-hover)] hover:text-[var(--color-text-primary)]'
            }`"
            :aria-label="sessionStore.isBatchMode ? t('sidebar.batchExit') : t('sidebar.batchManage')"
            :title="sessionStore.isBatchMode ? t('sidebar.batchExit') : t('sidebar.batchManage')"
          >
            <span class="material-symbols-outlined text-[18px]">
              {{ sessionStore.isBatchMode ? 'close' : 'delete_sweep' }}
            </span>
          </button>
        </div>
      </div>

      <!-- Session list section -->
      <div
        data-testid="sidebar-session-list-section"
        class="sidebar-section sidebar-section--visible flex flex-1 min-h-0 flex-col"
      >
        <!-- Batch mode toolbar -->
        <div v-if="sessionStore.isBatchMode" class="mx-3 mb-2 rounded-[8px] border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-2 shadow-sm">
          <div class="flex items-center justify-between gap-2">
            <span class="min-w-0 text-xs font-medium text-[var(--color-text-primary)]">
              {{ t('sidebar.batchSelectedCount', { count: selectedCount }) }}
            </span>
            <button
              type="button"
              @click="handleExitBatchMode"
              class="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)]"
              :aria-label="t('sidebar.batchExit')"
              :title="t('sidebar.batchExit')"
            >
              <span class="material-symbols-outlined text-[17px]">close</span>
            </button>
          </div>
          <div class="mt-2 grid grid-cols-2 gap-1.5">
            <button
              type="button"
              @click="() => {
                const all = filteredSessionIds.every((id) => sessionStore.selectedSessionIds.includes(id))
                if (all) sessionStore.deselectSessions(filteredSessionIds)
                else sessionStore.selectSessions(filteredSessionIds)
              }"
              :disabled="filteredSessionIds.length === 0"
              class="rounded-md border border-[var(--color-border)] px-2 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] disabled:opacity-50"
            >
              {{ filteredSessionIds.length > 0 && filteredSessionIds.every((id) => sessionStore.selectedSessionIds.includes(id))
                ? t('sidebar.batchDeselectAll')
                : t('sidebar.batchSelectAll') }}
            </button>
            <button
              type="button"
              @click="() => requestBatchDelete([...sessionStore.selectedSessionIds])"
              :disabled="selectedCount === 0"
              class="rounded-md bg-[var(--color-error)] px-2 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {{ t('sidebar.batchDeleteSelected', { count: selectedCount }) }}
            </button>
          </div>
        </div>

        <!-- Scrollable session list -->
        <div class="sidebar-scroll-area min-h-0 flex-1 overflow-y-auto px-3 pb-20">
          <!-- Error -->
          <div
            v-if="sessionStore.error"
            class="mx-1 mt-2 rounded-[var(--radius-md)] border border-[var(--color-error)]/20 bg-[var(--color-error)]/5 px-3 py-2"
          >
            <div class="text-xs font-medium text-[var(--color-error)]">{{ t('sidebar.sessionListFailed') }}</div>
            <div class="mt-1 text-[11px] text-[var(--color-text-secondary)] break-words">{{ sessionStore.error }}</div>
            <button
              @click="sessionStore.fetchSessions"
              class="mt-2 text-[11px] font-medium text-[var(--color-brand)] hover:underline"
            >
              {{ t('common.retry') }}
            </button>
          </div>

          <!-- Loading -->
          <div
            v-else-if="showInitialLoading"
            class="px-3 py-4 text-center text-xs text-[var(--color-text-tertiary)]"
          >
            {{ t('common.loading') }}
          </div>

          <!-- Empty -->
          <div
            v-else-if="filteredSessions.length === 0"
            class="px-3 py-4 text-center text-xs text![var(--color-text-tertiary)]"
          >
            {{ t('sidebar.noSessions') }}
          </div>

          <!-- Projects header -->
          <ProjectHeaderActions
            v-if="orderedProjectGroups.length > 0"
            :title="t('sidebar.projects')"
            :menu-label="t('sidebar.projectMenu')"
            :create-label="t('sidebar.newProject')"
            @open-menu="openProjectHeaderMenu"
            @open-create="(e) => openProjectHeaderMenu(e, 'create')"
          />

          <!-- Project groups -->
          <template v-for="project in visibleProjectGroups" :key="project.key">
            <section
              :data-testid="`sidebar-project-group-${domSafeProjectKey(project.key)}`"
              @dragover="(e) => handleProjectDragOver(e, project.key)"
              @drop="(e) => handleProjectDrop(e, project.key)"
              @dragleave="(e) => {
                if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) {
                  projectDropTarget = projectDropTarget?.key === project.key ? null : projectDropTarget
                }
              }"
              :class="`group/project relative mb-3.5 transition-opacity ${draggingProjectKey === project.key ? 'opacity-50' : ''}`"
            >
              <!-- Drop indicator before -->
              <div
                v-if="projectDropTarget?.key === project.key && projectDropTarget.position === 'before'"
                class="pointer-events None absolute -top-1 left-1 right-1 z-10 h-0.5 rounded-full bg-[var(--color-brand)]"
              />

              <!-- Project header row -->
              <div class="flex items-center gap-1">
                <button
                  type="button"
                  :draggable="!sessionStore.isBatchMode"
                  @dragstart="(e) => handleProjectDragStart(e, project.key)"
                  @dragend="clearProjectDragState"
                  @click="toggleProjectCollapsed(project.key)"
                  :data-state="collapsedProjectKeys.has(project.key) ? 'closed' : 'open'"
                  class="flex min-w-0 flex-1 cursor-grab items-center gap-2 rounded-xl px-1.5 py-2 text-left transition-[background,color] active:cursor-grabbing hover:bg-[var(--color-sidebar-item-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)]"
                  :aria-expanded="!collapsedProjectKeys.has(project.key)"
                  :aria-label="t(collapsedProjectKeys.has(project.key) ? 'sidebar.expandProject' : 'sidebar.collapseProject', { project: project.title })"
                  :title="project.subtitle || project.title"
                >
                  <!-- Folder icon -->
                  <span
                    :data-testid="`sidebar-project-icon-${domSafeProjectKey(project.key)}`"
                    :data-icon-state="collapsedProjectKeys.has(project.key) ? 'closed' : 'open'"
                    :class="`flex h-5 w-5 flex-shrink-0 items-center justify-center transition-colors ${
                      collapsedProjectKeys.has(project.key)
                        ? 'text-[var(--color-text-secondary)]'
                        : 'text-[var(--color-text-primary)]'
                    }`"
                  >
                    <span class="material-symbols-outlined text-[18px]">
                      {{ collapsedProjectKeys.has(project.key) ? 'folder' : 'folder_open' }}
                    </span>
                  </span>
                  <!-- Project title -->
                  <span :class="`min-w-0 flex-1 truncate text-[13px] font-semibold leading-5 transition-colors ${
                    collapsedProjectKeys.has(project.key)
                      ? 'text-[var(--color-text-secondary)]'
                      : 'text-[var(--color-text-primary)]'
                  }`">
                    {{ project.title }}
                  </span>
                  <!-- Pin indicator -->
                  <span
                    v-if="pinnedProjectKeys.has(project.key)"
                    class="flex-shrink-0"
                    style="fontVariationSettings: 'FILL' 1"
                  >
                    <span class="material-symbols-outlined text-[14px] text-[var(--color-text-tertiary)]">push_pin</span>
                  </span>
                </button>

                <!-- Batch mode: group select button -->
                <template v-if="sessionStore.isBatchMode">
                  <button
                    type="button"
                    @click="() => toggleGroupSelection(project.sessions.map((s) => s.id))"
                    :class="`rounded-md px-1.5 py-1 text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)] ${
                      project.sessions.filter((s) => sessionStore.selectedSessionIds.includes(s.id)).length > 0
                        ? 'text-[var(--color-brand)] hover:bg-[var(--color-brand)]/10'
                        : 'text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-secondary)]'
                    }`"
                    :aria-label="t('sidebar.batchSelectGroup', { group: project.title })"
                  >
                    {{ project.sessions.filter((s) => sessionStore.selectedSessionIds.includes(s.id)).length === project.sessions.length
                      ? t('sidebar.batchDeselectAll')
                      : t('sidebar.batchSelectAll') }}
                  </button>
                </template>

                <!-- Non-batch mode: action buttons -->
                <template v-else>
                  <div class="pointer-events-none flex items-center gap-0.5 opacity-0 transition-opacity duration-150 group-hover/project:pointer-events-auto group-hover/project:opacity-100 group-focus-within/project:pointer-events-auto group-focus-within/project:opacity-100">
                    <!-- More actions -->
                    <button
                      type="button"
                      @click.stop="(e) => {
                        contextMenu = null
                        projectContextMenu = { key: project.key, x: e.clientX, y: e.clientY }
                      }"
                      class="flex h-7 w-7 items-center justify-center rounded-lg text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-sidebar-item-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)]"
                      :aria-label="t('sidebar.projectActions', { project: project.title })"
                      :title="t('sidebar.projectActions', { project: project.title })"
                    >
                      <span class="material-symbols-outlined text-[17px]">more_horiz</span>
                    </button>
                    <!-- New session in project -->
                    <button
                      type="button"
                      @click.stop="() => void createSessionForWorkDir(project.workDir)"
                      class="flex h-7 w-7 items-center justify-center rounded-lg text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-sidebar-item-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)]"
                      :aria-label="t('sidebar.newSessionInProject', { project: project.title })"
                      :title="t('sidebar.newSessionInProject', { project: project.title })"
                    >
                      <span class="material-symbols-outlined text-[16px]">edit_note</span>
                    </button>
                  </div>
                </template>
              </div>

              <!-- Expanded project sessions -->
              <div v-if="!collapsedProjectKeys.has(project.key)" class="mt-0.5 pl-6">
                <div
                  :class="sessionsExpanded && project.sessions.length > PROJECT_GROUP_SCROLL_COUNT ? 'max-h-[420px] overflow-y-auto pr-1' : ''"
                  :data-testid="`sidebar-project-session-list-${domSafeProjectKey(project.key)}`"
                >
                  <!-- Render visible sessions -->
                  <div
                    v-for="session in (collapsedProjectKeys.has(project.key)
                      ? []
                      : getVisibleProjectSessions(project.sessions, expandedProjectKeys.has(project.key), activeTabId))"
                    :key="session.id"
                    class="relative mb-0.5 last:mb-0"
                  >
                    <!-- Rename input -->
                    <input
                      v-if="renamingId === session.id"
                      ref="renameInput"
                      v-model="renameValue"
                      @blur="handleFinishRename"
                      @keydown.enter="handleFinishRename"
                      @keydown.escape="() => { renamingId = null; renameValue = '' }"
                      class="w-full rounded-[var(--radius-md)] border border-[var(--color-border-focus)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none"
                      autofocus
                    />
                    <!-- Session button -->
                    <button
                      v-else
                      @click="(e) => {
                        if (sessionStore.isBatchMode) { handleBatchSessionClick(e, session.id); return }
                        tabStore.openTab(session.id, session.title)
                        chatStore.connectToSession(session.id)
                        closeMobileDrawer()
                      }"
                      @contextmenu="(e) => handleContextMenu(e, session.id)"
                      :class="`group/session w-full rounded-lg px-2.5 ${isMobileComputed ? 'py-3' : 'py-1.5'} text-left text-[13px] transition-[background,filter,color] duration-200 ${
                        sessionStore.selectedSessionIds.includes(session.id)
                          ? 'sidebar-session-row--selected bg-[var(--color-sidebar-item-active)] text-[var(--color-text-primary)]'
                          : session.id === activeTabId
                          ? 'sidebar-session-row--active bg-[var(--color-sidebar-item-active)] text-[var(--color-text-primary)]'
                          : 'sidebar-session-row--idle text-[var(--color-text-secondary)] hover:bg-[var(--color-sidebar-item-hover)] hover:text-[var(--color-text-primary)]'
                      }`"
                      :aria-pressed="sessionStore.isBatchMode ? sessionStore.selectedSessionIds.includes(session.id) : undefined"
                    >
                      <span class="flex min-w-0 items-center gap-2">
                        <!-- Batch mode checkbox -->
                        <span
                          v-if="sessionStore.isBatchMode"
                          :class="`flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-[5px] border transition-colors ${
                            sessionStore.selectedSessionIds.includes(session.id)
                              ? 'border-[var(--color-brand)] bg-[var(--color-brand)] text-white'
                              : 'border-[var(--color-border)] bg-[var(--color-surface)]'
                          }`"
                          aria-hidden="true"
                        >
                          <span v-if="sessionStore.selectedSessionIds.includes(session.id)" class="material-symbols-outlined text-[12px]">check</span>
                        </span>
                        <!-- Session title -->
                        <span class="min-w-0 flex-1 truncate font-medium tracking-normal">{{ session.title || 'Untitled' }}</span>
                        <!-- Missing dir warning -->
                        <span
                          v-if="!session.workDirExists"
                          class="flex-shrink-0 text-[10px] text-[var(--color-warning)]"
                          :title="session.workDir ?? ''"
                        >
                          {{ t('sidebar.missingDir') }}
                        </span>
                        <!-- Session metadata -->
                        <SessionRowMeta
                          :is-running="runningSessionIds.has(session.id)"
                          :is-worktree="isWorktreeSession(session)"
                          :modified-at="session.modifiedAt"
                        />
                      </span>
                    </button>
                  </div>
                </div>

                <!-- Show more/less button -->
                <div
                  v-if="(project.sessions.length - (collapsedProjectKeys.has(project.key) ? 0 : getVisibleProjectSessions(project.sessions, expandedProjectKeys.has(project.key), activeTabId).length) > 0 || expandedProjectKeys.has(project.key))"
                  class="mt-2 flex justify-start px-2.5"
                >
                  <button
                    type="button"
                    @click="toggleProjectSessionExpansion(project.key)"
                    class="inline-flex items-center justify-start py-1 text-[13px] font-semibold text-[var(--color-text-tertiary)] opacity-75 transition-[color,opacity] hover:text-[var(--color-text-secondary)] hover:opacity-100 focus-visible:rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)]"
                    :aria-expanded="expandedProjectKeys.has(project.key)"
                  >
                    {{ expandedProjectKeys.has(project.key)
                      ? t('sidebar.showFewerSessions')
                      : t('sidebar.showMoreSessions') }}
                  </button>
                </div>
              </div>

              <!-- Drop indicator after -->
              <div
                v-if="projectDropTarget?.key === project.key && projectDropTarget.position === 'after'"
                class="pointer-events-none absolute -bottom-1 left-1 right-1 z-10 h-0.5 rounded-full bg-[var(--color-brand)]"
              />
            </section>
          </template>
        </div>
      </div>
    </template>

    <!-- Collapsed view placeholder -->
    <div v-else class="flex-1" aria-hidden="true" />

    <!-- Settings dock (bottom) -->
    <div
      v-if="!isMobileComputed"
      data-testid="sidebar-settings-dock"
      :class="`sidebar-settings-dock absolute bottom-0 left-0 right-0 border-t border-[var(--color-border)] p-3 ${expanded ? '' : 'flex justify-center'}`"
    >
      <!-- TODO: Phase 2 — NavItem for Settings -->
      <NavItem
        :active="activeTabId === SETTINGS_TAB_ID"
        :collapsed="!expanded"
                        @click="() => {
          tabStore.openTab(SETTINGS_TAB_ID, t('sidebar.settings'), 'settings')
          closeMobileDrawer()
        }"
        :icon="'settings'"
      >
        {{ t('sidebar.settings') }}
      </NavItem>
    </div>

    <!-- Context menu for session -->
    <div
      v-if="contextMenu"
      class="fixed z-50 min-w-[140px] rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] py-1"
      :style="{ left: contextMenu.x, top: contextMenu.y, boxShadow: 'var(--shadow-dropdown)' }"
    >
      <button
        @click="() => {
          const session = sessionStore.sessions.find((s) => s.id === contextMenu.id)
          handleStartRename(contextMenu.id, session?.title || '')
        }"
        class="w-full px-3 py-1.5 text-left text-xs text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-surface-hover)]"
      >
        {{ t('common.rename') }}
      </button>
      <button
        @click="() => handleDelete(contextMenu.id)"
        class="w-full px-3 py-1.5 text-left text-xs text-[var(--color-error)] transition-colors hover:bg-[var(--color-surface-hover)]"
      >
        {{ t('common.delete') }}
      </button>
    </div>



    <!-- Project context menu -->
    <template v-if="projectMenuData">
      <div
        role="menu"
        class="fixed z-50 min-w-[230px] overflow-hidden rounded-[18px] border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] py-2 shadow-[var(--shadow-dropdown)]"
        :style="positionProjectMenu(projectContextMenu!.x, projectContextMenu!.y)"
        @click.stop
      >
        <ProjectMenuItem
          :icon="projectMenuData.pinned ? 'push_pin' : 'push_pin'"
          @click="() => togglePinnedProject(projectMenuData.project.key)"
        >
          {{ t(projectMenuData.pinned ? 'sidebar.unpinProject' : 'sidebar.pinProject') }}
        </ProjectMenuItem>
        <ProjectMenuItem
          :icon="'folder_open'"
          @click="() => void openProjectInFinder(projectMenuData.project)"
        >
          {{ t('sidebar.openInFinder') }}
        </ProjectMenuItem>
        <ProjectMenuItem
          :icon="projectMenuData.hidden ? 'restore' : 'close'"
          @click="() => toggleHiddenProject(projectMenuData.project)"
          :danger="!projectMenuData.hidden"
        >
          {{ t(projectMenuData.hidden ? 'sidebar.restoreProjectToSidebar' : 'sidebar.hideProjectFromSidebar') }}
        </ProjectMenuItem>
      </div>
    </template>

    <!-- Project header menu (main/organize/sort/create) -->
    <ProjectHeaderMenu
      v-if="projectHeaderMenu"
      :type="projectHeaderMenu.type"
      :x="projectHeaderMenu.x"
      :y="projectHeaderMenu.y"
      :organization="projectOrganizationState"
      :sort-by="projectSortByState"
      @open-submenu="openProjectHeaderSubmenu"
      @set-organization="updateProjectOrganization"
      @set-sort-by="updateProjectSortBy"
      @create-blank="() => void createSessionForWorkDir()"
      @use-existing-folder="() => void createSessionFromExistingFolder()"
      @restore-hidden-projects="restoreAllHiddenProjects"
      :hidden-project-count="hiddenProjectKeys.size"
      :t="t"
    />

    <!-- Project header submenu -->
    <ProjectHeaderMenu
      v-if="projectHeaderSubmenu"
      :type="projectHeaderSubmenu.type"
      :x="projectHeaderSubmenu.x"
      :y="projectHeaderSubmenu.y"
      :organization="projectOrganizationState"
      :sort-by="projectSortByState"
      @open-submenu="openProjectHeaderSubmenu"
      @set-organization="updateProjectOrganization"
      @set-sort-by="updateProjectSortBy"
      @create-blank="() => void createSessionForWorkDir()"
      @use-existing-folder="() => void createSessionFromExistingFolder()"
      @restore-hidden-projects="restoreAllHiddenProjects"
      :hidden-project-count="hiddenProjectKeys.size"
      :t="t"
    />

    <!-- Confirm dialog: single session delete -->
    <ConfirmDialog
      :open="pendingDeleteSessionId !== null"
      @close="() => pendingDeleteSessionId = null"
      @confirm="confirmDelete"
      :title="t('common.delete')"
      :confirm-label="t('common.delete')"
      :cancel-label="t('common.cancel')"
      confirm-variant="danger"
    >
      {{ pendingDeleteSessionId ? t('sidebar.confirmDelete') : '' }}
    </ConfirmDialog>

    <!-- Confirm dialog: batch delete -->
    <ConfirmDialog
      :open="pendingBatchDeleteSessionIds !== null"
      @close="() => { if (!isBatchDeleting) pendingBatchDeleteSessionIds = null }"
      @confirm="confirmBatchDelete"
      :title="t('common.delete')"
      :confirm-label="t('common.delete')"
      :cancel-label="t('common.cancel')"
      confirm-variant="danger"
      :loading="isBatchDeleting"
    >
      <div class="space-y-3">
        <p class="text-sm leading-6 text-[var(--color-text-secondary)]">
          {{ t('sidebar.batchDeleteConfirm', { count: pendingBatchDeleteSessionIds?.length ?? 0 }) }}
        </p>
        <div>
          <div class="mb-1.5 text-xs font-medium text-[var(--color-text-primary)]">
            {{ t('sidebar.batchDeleteConfirmBody') }}
          </div>
          <ul class="max-h-40 space-y-1 overflow-y-auto rounded-[8px] border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-2">
            <li v-for="session in (pendingBatchDeleteSessionIds ?? []).slice(0, 5).map(id => sessionsById.get(id)).filter(Boolean)" :key="session.id" class="truncate text-xs text-[var(--color-text-secondary)]">
              {{ session.title || 'Untitled' }}
            </li>
            <li
              v-if="pendingBatchDeleteSessionIds && pendingBatchDeleteSessionIds.length > 5"
              class="text-xs text-[var(--color-text-tertiary)]"
            >
              {{ t('sidebar.batchDeleteMore', { count: pendingBatchDeleteSessionIds.length - 5 }) }}
            </li>
          </ul>
        </div>
      </div>
    </ConfirmDialog>

    <!-- Global search modal -->
    <GlobalSearchModal
      :open="activeModal === 'globalSearch'"
      @close="uiStore.closeModal"
    />
  </aside>
</template>

<style scoped>
/* Sidebar-specific styles */
.sidebar-copy {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.sidebar-copy--visible {
  opacity: 1;
}
.sidebar-copy--hidden {
  opacity: 0;
  width: 0;
  overflow: hidden;
}
.sidebar-toggle-icon {
  transition: transform 0.2s ease;
}
.sidebar-toggle-icon--collapsed {
  transform: rotate(180deg);
}
.sidebar-toggle-icon--open {
  transform: rotate(0deg);
}
.sidebar-toggle-icon--collapsed .sidebar-toggle-chevron {
  transform: rotate(180deg);
}
.sidebar-settings-dock {
  z-index: 3;
}
.sidebar-scroll-area {
  scrollbar-color: var(--color-surface-hover) transparent;
  scrollbar-width: thin;
}
.sidebar-scroll-area::-webkit-scrollbar {
  width: 6px;
}
.sidebar-scroll-area::-webkit-scrollbar-track {
  background: transparent;
}
.sidebar-scroll-area::-webkit-scrollbar-thumb {
  background: var(--color-surface-hover);
  border-radius: 3px;
}
.sidebar-session-row--active,
.sidebar-session-row--selected {
  box-shadow: inset 0 0 0 1px var(--color-brand);
}
</style>