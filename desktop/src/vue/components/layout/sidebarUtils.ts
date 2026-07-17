/**
 * Pure helpers extracted from Sidebar.vue so the SFC stays smaller and
 * list-performance tweaks can live next to the session-row windowing logic.
 */
import type { SessionListItem } from '../../../types/session'
import type { TranslationKey } from '../../i18n'
import type { SidebarProjectPreferences } from '../../../api/desktopUiPreferences'

export type SidebarProjectOrganization = 'project' | 'recentProject' | 'time'
export type SidebarProjectSortBy = 'createdAt' | 'updatedAt'

export type ProjectGroup = {
  key: string
  title: string
  subtitle: string | null
  workDir: string | undefined
  sessions: SessionListItem[]
}

export const PROJECT_GROUP_VISIBLE_COUNT = 6
export const PROJECT_GROUP_SCROLL_COUNT = 12
/** Hard cap of DOM rows per project when expanded (windowed scroll). */
export const PROJECT_SESSION_WINDOW_SIZE = 80

export function isDocumentVisible(): boolean {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden'
}

export function domSafeProjectKey(projectKey: string): string {
  return projectKey.replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '') || 'unknown'
}

export function positionProjectMenu(clientX: number, clientY: number): { left: number; top: number } {
  if (typeof window === 'undefined') return { left: clientX, top: clientY }
  const width = 230
  const height = 280
  return {
    left: Math.max(8, Math.min(clientX, window.innerWidth - width - 8)),
    top: Math.max(8, Math.min(clientY, window.innerHeight - height - 8)),
  }
}

export function formatRelativeTime(
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

export function normalizeProjectKeyList(values: unknown): string[] {
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

export function normalizeProjectPathForComparison(value: string, isWindows: boolean): string {
  const normalized = value.replace(/\\/g, '/').replace(/\/+$/g, '') || value
  return isWindows ? normalized.toLowerCase() : normalized
}

export function isDriveRootComparisonPath(value: string): boolean {
  return /^[a-z]:$/i.test(value)
}

export function projectPathMatches(projectKey: string, workDir: string, isWindows: boolean): boolean {
  const normalizedProjectKey = normalizeProjectPathForComparison(projectKey, isWindows)
  const normalizedWorkDir = normalizeProjectPathForComparison(workDir, isWindows)
  if (normalizedProjectKey === normalizedWorkDir) return true
  if (isDriveRootComparisonPath(normalizedProjectKey)) return false
  return normalizedWorkDir.startsWith(`${normalizedProjectKey}/`)
}

export function hasSidebarProjectPreferences(preferences: SidebarProjectPreferences): boolean {
  return preferences.projectOrder.length > 0
    || preferences.pinnedProjects.length > 0
    || preferences.hiddenProjects.length > 0
    || preferences.projectOrganization !== 'recentProject'
    || preferences.projectSortBy !== 'updatedAt'
}

export function normalizeProjectOrganization(value: unknown): SidebarProjectOrganization {
  return (value === 'project' || value === 'recentProject' || value === 'time')
    ? (value as SidebarProjectOrganization)
    : 'recentProject'
}

export function normalizeProjectSortBy(value: unknown): SidebarProjectSortBy {
  return (value === 'createdAt' || value === 'updatedAt')
    ? (value as SidebarProjectSortBy)
    : 'updatedAt'
}

export function normalizeSidebarProjectPreferences(
  preferences?: Partial<SidebarProjectPreferences>,
): SidebarProjectPreferences {
  return {
    projectOrder: normalizeProjectKeyList(preferences?.projectOrder),
    pinnedProjects: normalizeProjectKeyList(preferences?.pinnedProjects),
    hiddenProjects: normalizeProjectKeyList(preferences?.hiddenProjects),
    projectOrganization: normalizeProjectOrganization(preferences?.projectOrganization),
    projectSortBy: normalizeProjectSortBy(preferences?.projectSortBy),
  }
}

export function buildSidebarProjectPreferences(
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

export function getVisibleProjectSessions(
  sessions: SessionListItem[],
  expanded: boolean,
  activeSessionId: string | null,
  visibleCount = PROJECT_GROUP_VISIBLE_COUNT,
): SessionListItem[] {
  if (expanded || sessions.length <= visibleCount) {
    // Window large expanded lists so the DOM stays bounded.
    if (expanded && sessions.length > PROJECT_SESSION_WINDOW_SIZE) {
      // Prefer keeping the active session in the window.
      if (activeSessionId) {
        const activeIdx = sessions.findIndex((s) => s.id === activeSessionId)
        if (activeIdx >= 0) {
          const half = Math.floor(PROJECT_SESSION_WINDOW_SIZE / 2)
          const start = Math.max(0, Math.min(activeIdx - half, sessions.length - PROJECT_SESSION_WINDOW_SIZE))
          return sessions.slice(start, start + PROJECT_SESSION_WINDOW_SIZE)
        }
      }
      return sessions.slice(0, PROJECT_SESSION_WINDOW_SIZE)
    }
    return sessions
  }
  const visible = sessions.slice(0, visibleCount)
  if (!activeSessionId || visible.some((session) => session.id === activeSessionId)) return visible
  const activeSession = sessions.find((session) => session.id === activeSessionId)
  return activeSession ? [...visible, activeSession] : visible
}

export function getSessionTimestamp(
  session: SessionListItem | undefined,
  sortBy: SidebarProjectSortBy,
): number {
  const value = sortBy === 'createdAt' ? session?.createdAt : session?.modifiedAt
  const timestamp = new Date(value ?? 0).getTime()
  return Number.isFinite(timestamp) ? timestamp : 0
}

export function compareSessionsByTimestamp(
  a: SessionListItem | undefined,
  b: SessionListItem | undefined,
  sortBy: SidebarProjectSortBy,
): number {
  return getSessionTimestamp(b, sortBy) - getSessionTimestamp(a, sortBy)
}

export function normalizePathForCompare(pathLike: string): string {
  return pathLike.replace(/\\/g, '/').replace(/\/+$/, '')
}

export function projectTitle(pathLike: string | null | undefined): string {
  if (!pathLike) return '默认'
  if (pathLike === '__default__') return '默认'
  const normalized = pathLike.replace(/[\\/]+$/, '')
  const segments = normalized.split(/[\\/]/).filter(Boolean)
  const last = segments[segments.length - 1]
  if (last) return last
  return normalized || '默认'
}

export function compactProjectPath(pathLike: string): string {
  const normalized = normalizePathForCompare(pathLike)
  const segments = normalized.split('/').filter(Boolean)
  if (segments.length <= 3) return normalized
  return `.../${segments.slice(-3, -1).join('/')}`
}

export function projectSubtitle(projectRoot: string | null | undefined, fallbackKey: string): string | null {
  if (!projectRoot) return fallbackKey === 'unknown' ? null : fallbackKey
  return compactProjectPath(projectRoot)
}

export function isSameOrChildPath(childPath: string, parentPath: string): boolean {
  const child = normalizePathForCompare(childPath)
  const parent = normalizePathForCompare(parentPath)
  return child === parent || child.startsWith(`${parent}/`)
}

export function isWorktreeSession(session: SessionListItem): boolean {
  if (!session.workDir) return false
  if (/[/\\]\.claude[/\\]worktrees[/\\]/.test(session.workDir)) return true
  if (!session.projectRoot || session.workDir === session.projectRoot) return false
  return !isSameOrChildPath(session.workDir, session.projectRoot)
}

export function moveProjectKey(
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

export function applyProjectOrder(
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
