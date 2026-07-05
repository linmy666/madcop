<script setup lang="ts">
import {
  computed,
  onMounted,
  onUnmounted,
  ref,
  watch,
} from 'vue'
import {
  activityStatsApi,
  type ActivityStatsResponse,
  type DailyActivity,
} from '../../api/activityStats'
import {
  desktopUiPreferencesApi,
  getProfileAvatarUrl,
  type DesktopProfilePreferences,
} from '../../api/desktopUiPreferences'
import { type Locale, useTranslation } from '../../i18n'
import { useSettingsStore } from '../../stores/settingsStore'
import { publicAssetPath } from '../../lib/publicAsset'

// ─── Types ───────────────────────────────────────────────────────────────────

type HeatmapDay = {
  date: string
  sessionCount: number
  messageCount: number
  toolCallCount: number
  tokens: number
  level: number
  mode: HeatmapMode
  rangeStart?: string
  rangeEnd?: string
}

type SummaryMetric = {
  label: string
  value: string
  detail?: string
}

type InsightMetric = {
  label: string
  value: string
  detail?: string
}

type PluginRankItem = {
  id: string
  label: string
  count: number
  kind: 'plugin' | 'skill'
}

type HeatmapMode = 'daily' | 'weekly' | 'cumulative'

// ─── Constants ───────────────────────────────────────────────────────────────

const WEEK_COUNT = 52
const WEEKDAY_LABEL_KEYS = [
  'settings.activity.weekday.mon',
  'settings.activity.weekday.wed',
  'settings.activity.weekday.fri',
] as const
const HEAT_CELL_GAP = 3
const HEAT_LABEL_WIDTH = 38
const HEAT_CELL_MIN = 6
const HEAT_CELL_MAX = 22
const TOOLTIP_WIDTH = 172
const HEAT_COLORS = [
  'var(--color-activity-heat-0)',
  'var(--color-activity-heat-1)',
  'var(--color-activity-heat-2)',
  'var(--color-activity-heat-3)',
  'var(--color-activity-heat-4)',
]
const DATE_LOCALES: Record<Locale, string> = {
  en: 'en-US',
  zh: 'zh-CN',
  'zh-TW': 'zh-TW',
  jp: 'ja-JP',
  kr: 'ko-KR',
}
const DEFAULT_PROFILE: DesktopProfilePreferences = {
  displayName: 'madcop-agent',
  subtitle: 'github.com/linmy666/madcop',
  avatarFile: null,
  avatarUpdatedAt: null,
}
const DEFAULT_AVATAR_SRC = publicAssetPath('mascot.png?v=2633')

// ─── Helpers ─────────────────────────────────────────────────────────────────

function localDateKey(date: Date): string {
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

function parseLocalDate(dateKey: string): Date {
  return new Date(`${dateKey}T00:00:00`)
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}

function startOfWeek(date: Date): Date {
  const next = new Date(date)
  next.setHours(0, 0, 0, 0)
  next.setDate(next.getDate() - next.getDay())
  return next
}

function formatDateLabel(dateKey: string, locale: Locale): string {
  return parseLocalDate(dateKey).toLocaleDateString(DATE_LOCALES[locale], {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000_000)
    return `${(tokens / 1_000_000_000).toFixed(tokens >= 10_000_000_000 ? 0 : 1)}B`
  if (tokens >= 1_000_000)
    return `${(tokens / 1_000_000).toFixed(tokens >= 10_000_000 ? 0 : 1)}M`
  if (tokens >= 1_000) return `${Math.round(tokens / 1_000)}K`
  return `${tokens}`
}

function formatInteger(value: number, locale: Locale): string {
  return new Intl.NumberFormat(DATE_LOCALES[locale], { maximumFractionDigits: 0 }).format(value)
}

function formatPercent(numerator: number, denominator: number, locale: Locale): string {
  if (denominator <= 0) return '0%'
  return new Intl.NumberFormat(DATE_LOCALES[locale], {
    maximumFractionDigits: 0,
    style: 'percent',
  }).format(numerator / denominator)
}

function formatDayCount(value: number, t: ReturnType<typeof useTranslation>): string {
  return t(value === 1 ? 'settings.activity.count.dayOne' : 'settings.activity.count.dayOther', { count: value })
}

function formatTaskDuration(
  duration: number | undefined,
  locale: Locale,
  t: ReturnType<typeof useTranslation>,
): string {
  if (!duration || duration <= 0) return t('settings.activity.noDuration')
  const totalMinutes = Math.max(1, Math.round(duration / 60_000))
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60

  if (locale === 'zh') {
    if (hours > 0 && minutes > 0) return `${hours} 小时 ${minutes} 分钟`
    if (hours > 0) return `${hours} 小时`
    return `${minutes} 分钟`
  }

  if (hours > 0 && minutes > 0) return `${hours}h ${minutes}m`
  if (hours > 0) return `${hours}h`
  return `${minutes}m`
}

function formatSessionCount(value: number, t: ReturnType<typeof useTranslation>): string {
  return t(value === 1 ? 'settings.activity.count.sessionOne' : 'settings.activity.count.sessionOther', { count: value })
}

function formatMessageCount(value: number, t: ReturnType<typeof useTranslation>): string {
  return `${value} ${t('settings.activity.messages')}`
}

function formatRunCount(value: number, t: ReturnType<typeof useTranslation>): string {
  return t(value === 1 ? 'settings.activity.count.runOne' : 'settings.activity.count.runOther', { count: value })
}

function getModelTokenTotal(
  usage: ActivityStatsResponse['modelUsage'][string] | undefined,
): number {
  if (!usage) return 0
  return (
    (usage.inputTokens ?? 0) +
    (usage.outputTokens ?? 0) +
    (usage.cacheReadInputTokens ?? 0) +
    (usage.cacheCreationInputTokens ?? 0)
  )
}

function formatModelName(model: string): string {
  return model
    .replace(/^claude-/i, '')
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function getPluginNameFromToolName(toolName: string): string | null {
  if (!toolName.startsWith('mcp__')) return null
  const parts = toolName.split('__').filter(Boolean)
  const serverName = parts[1]
  if (!serverName) return null
  if (serverName === 'codex_apps' && parts[2]) return parts[2]
  return serverName
}

function formatPluginName(pluginName: string): string {
  return pluginName.replace(/_/g, '-')
}

function buildPluginAndSkillRankItems(stats: ActivityStatsResponse | null): PluginRankItem[] {
  const skillItems = Object.entries(stats?.skillUsage ?? {}).map<PluginRankItem>(([skill, count]) => ({
    id: `skill:${skill}`,
    label: `$${skill}`,
    count,
    kind: 'skill',
  }))

  const pluginUsage = new Map<string, number>()
  for (const [toolName, count] of Object.entries(stats?.toolUsage ?? {})) {
    const pluginName = getPluginNameFromToolName(toolName)
    if (!pluginName || count <= 0) continue
    pluginUsage.set(pluginName, (pluginUsage.get(pluginName) || 0) + count)
  }
  const pluginItems = [...pluginUsage.entries()].map<PluginRankItem>(([pluginName, count]) => ({
    id: `plugin:${pluginName}`,
    label: `@${formatPluginName(pluginName)}`,
    count,
    kind: 'plugin',
  }))

  return [...skillItems, ...pluginItems]
    .filter((item) => item.count > 0)
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
    .slice(0, 6)
}

function withProfileDefaults(
  profile: Partial<DesktopProfilePreferences> | null | undefined,
): DesktopProfilePreferences {
  return { ...DEFAULT_PROFILE, ...profile }
}

function getProfileSubtitleHref(subtitle: string): string | null {
  if (/^https?:\/\//i.test(subtitle)) return subtitle
  if (/^[\w.-]+\.[a-z]{2,}(?:\/.*)?$/i.test(subtitle)) return `https://${subtitle}`
  return null
}

function calculateHeatCellSize(width: number): number {
  const available = width - HEAT_LABEL_WIDTH - (WEEK_COUNT - 1) * HEAT_CELL_GAP
  return Math.max(HEAT_CELL_MIN, Math.min(HEAT_CELL_MAX, Math.floor(available / WEEK_COUNT)))
}

function sumDailyUsage(days: HeatmapDay[]) {
  return days.reduce(
    (sum, day) => ({
      sessions: sum.sessions + day.sessionCount,
      tokens: sum.tokens + day.tokens,
    }),
    { sessions: 0, tokens: 0 },
  )
}

function getDailyTokenMap(stats: ActivityStatsResponse | null): Map<string, number> {
  const map = new Map<string, number>()
  for (const day of stats?.dailyModelTokens ?? []) {
    const total = Object.values(day.tokensByModel).reduce((sum, tokens) => sum + tokens, 0)
    map.set(day.date, total)
  }
  return map
}

function getHeatLevel(day: DailyActivity | undefined, tokens: number, maxScore: number): number {
  const sessionCount = day?.sessionCount ?? 0
  if (sessionCount === 0 && tokens === 0) return 0
  if (maxScore <= 0) return 1

  const score = sessionCount * 3 + Math.ceil(tokens / 50_000)
  const ratio = score / maxScore
  if (ratio >= 0.78) return 4
  if (ratio >= 0.5) return 3
  if (ratio >= 0.24) return 2
  return 1
}

function getBarHeight(value: number, maxValue: number): number {
  if (value <= 0 || maxValue <= 0) return 0
  return Math.max(1, Math.min(7, Math.ceil((value / maxValue) * 7)))
}

function getBarLevel(value: number, maxValue: number): number {
  if (value <= 0) return 0
  if (maxValue <= 0) return 1
  const ratio = value / maxValue
  if (ratio >= 0.78) return 4
  if (ratio >= 0.5) return 3
  if (ratio >= 0.24) return 2
  return 1
}

function buildHeatmapDays(stats: ActivityStatsResponse | null, mode: HeatmapMode): HeatmapDay[] {
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  const finalWeekStart = startOfWeek(today)
  const start = addDays(finalWeekStart, -(WEEK_COUNT - 1) * 7)
  const activityMap = new Map((stats?.dailyActivity ?? []).map((day) => [day.date, day]))
  const tokenMap = getDailyTokenMap(stats)
  const dates: string[] = []
  for (let cursor = new Date(start); cursor <= today; cursor = addDays(cursor, 1)) {
    dates.push(localDateKey(cursor))
  }

  const scores: number[] = []
  for (const dateKey of dates) {
    const day = activityMap.get(dateKey)
    const tokens = tokenMap.get(dateKey) ?? 0
    scores.push((day?.sessionCount ?? 0) * 3 + Math.ceil(tokens / 50_000))
  }
  const maxScore = Math.max(...scores, 0)

  const days: HeatmapDay[] = []
  for (const dateKey of dates) {
    const day = activityMap.get(dateKey)
    const tokens = tokenMap.get(dateKey) ?? 0
    days.push({
      date: dateKey,
      sessionCount: day?.sessionCount ?? 0,
      messageCount: day?.messageCount ?? 0,
      toolCallCount: day?.toolCallCount ?? 0,
      tokens,
      level: getHeatLevel(day, tokens, maxScore),
      mode: 'daily',
    })
  }

  if (mode === 'daily') return days

  const weeks = Array.from({ length: WEEK_COUNT }, (_, index) => {
    const rangeStart = dates[index * 7] ?? ''
    const rangeEnd = dates[Math.min(index * 7 + 6, dates.length - 1)] ?? rangeStart
    return {
      rangeStart,
      rangeEnd,
      sessionCount: 0,
      messageCount: 0,
      toolCallCount: 0,
      tokens: 0,
      cumulativeTokens: 0,
    }
  })

  dates.forEach((dateKey, index) => {
    const week = weeks[Math.floor(index / 7)]
    const day = activityMap.get(dateKey)
    if (!week) return
    week.sessionCount += day?.sessionCount ?? 0
    week.messageCount += day?.messageCount ?? 0
    week.toolCallCount += day?.toolCallCount ?? 0
    week.tokens += tokenMap.get(dateKey) ?? 0
  })

  let runningTotal = 0
  for (const week of weeks) {
    runningTotal += week.tokens
    week.cumulativeTokens = runningTotal
  }

  const maxValue = Math.max(
    ...weeks.map((week) => (mode === 'weekly' ? week.tokens : week.cumulativeTokens)),
    0,
  )

  return dates.map((dateKey, index) => {
    const week = weeks[Math.floor(index / 7)]
    const row = index % 7
    const tokens = mode === 'weekly' ? week?.tokens ?? 0 : week?.cumulativeTokens ?? 0
    const height = getBarHeight(tokens, maxValue)
    const isFilled = height > 0 && row >= 7 - height

    return {
      date: dateKey,
      sessionCount: week?.sessionCount ?? 0,
      messageCount: week?.messageCount ?? 0,
      toolCallCount: week?.toolCallCount ?? 0,
      tokens,
      level: isFilled ? getBarLevel(tokens, maxValue) : 0,
      mode,
      rangeStart: week?.rangeStart,
      rangeEnd: week?.rangeEnd,
    }
  })
}

function buildMonthLabels(days: HeatmapDay[], locale: Locale): Array<{ week: number; label: string }> {
  if (days.length === 0) return []
  const labels: Array<{ week: number; label: string }> = []
  const firstDay = days[0]
  const lastDay = days[days.length - 1]
  if (!firstDay || !lastDay) return labels

  const firstDate = parseLocalDate(firstDay.date)
  const lastDate = parseLocalDate(lastDay.date)
  let previousMonth = -1

  for (let week = 0; week < WEEK_COUNT; week += 1) {
    const weekDate = addDays(firstDate, week * 7)
    if (weekDate > lastDate) break
    if (weekDate.getMonth() !== previousMonth) {
      labels.push({
        week,
        label: weekDate.toLocaleDateString(DATE_LOCALES[locale], { month: 'short' }),
      })
      previousMonth = weekDate.getMonth()
    }
  }

  return labels
}

function getHeatmapCellTitle(
  day: HeatmapDay,
  locale: Locale,
  t: ReturnType<typeof useTranslation>,
): string {
  if (day.mode === 'weekly') {
    return t('settings.activity.weekRange', {
      start: formatDateLabel(day.rangeStart ?? day.date, locale),
      end: formatDateLabel(day.rangeEnd ?? day.date, locale),
    })
  }

  if (day.mode === 'cumulative') {
    return t('settings.activity.cumulativeThrough', {
      date: formatDateLabel(day.rangeEnd ?? day.date, locale),
    })
  }

  return formatDateLabel(day.date, locale)
}

function getHeatmapCellDetail(
  day: HeatmapDay,
  t: ReturnType<typeof useTranslation>,
): string {
  if (day.mode === 'cumulative') {
    return t('settings.activity.tokenValue', { tokens: formatTokens(day.tokens) })
  }

  return `${formatSessionCount(day.sessionCount, t)} · ${formatTokens(day.tokens)} ${t('settings.activity.tokens')}`
}

// ─── Reactive State ─────────────────────────────────────────────────────────

const t = useTranslation()
const locale = useSettingsStore((state) => state.locale)

const heatmapMeasureRef = ref<HTMLDivElement | null>(null)
const avatarInputRef = ref<HTMLInputElement | null>(null)

const stats = ref<ActivityStatsResponse | null>(null)
const isLoading = ref(true)
const error = ref<string | null>(null)

const profile = ref<DesktopProfilePreferences>(DEFAULT_PROFILE)
const profileError = ref<string | null>(null)
const profileStatus = ref<string | null>(null)
const isProfileLoading = ref(true)
const isEditingProfile = ref(false)
const isSavingProfile = ref(false)
const draftDisplayName = ref(DEFAULT_PROFILE.displayName)
const draftSubtitle = ref(DEFAULT_PROFILE.subtitle)

const heatmapMode = ref<HeatmapMode>('daily')
const hoveredDate = ref<string | null>(null)
const focusedDate = ref<string | null>(null)
const heatCellSize = ref(10)

// ─── Side effects ────────────────────────────────────────────────────────────

onMounted(async () => {
  // Fetch stats
  setIsLoadingStats(true)
  setError(null)

  try {
    const nextStats = await activityStatsApi.getStats('all')
    setStats(nextStats)
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  } finally {
    setIsLoadingStats(false)
  }

  // Fetch profile
  setIsProfileLoading(true)
  setProfileError(null)

  try {
    const result = await desktopUiPreferencesApi.getPreferences()
    const nextProfile = withProfileDefaults(result.preferences.profile)
    setProfile(nextProfile)
    setDraftDisplayName(nextProfile.displayName)
    setDraftSubtitle(nextProfile.subtitle)
  } catch (err) {
    setProfileError(err instanceof Error ? err.message : String(err))
  } finally {
    setIsProfileLoading(false)
  }
})

// Helper setter aliases for clarity
function setStats(value: ActivityStatsResponse | null) { stats.value = value }
function setIsLoadingStats(value: boolean) { isLoading.value = value }
function setError(value: string | null) { error.value = value }
function setProfile(value: DesktopProfilePreferences) { profile.value = value }
function setProfileError(value: string | null) { profileError.value = value }
function setProfileStatus(value: string | null) { profileStatus.value = value }
function setIsProfileLoading(value: boolean) { isProfileLoading.value = value }
function setIsEditingProfile(value: boolean) { isEditingProfile.value = value }
function setIsSavingProfile(value: boolean) { isSavingProfile.value = value }
function setDraftDisplayName(value: string) { draftDisplayName.value = value }
function setDraftSubtitle(value: string) { draftSubtitle.value = value }
function setHeatmapMode(value: HeatmapMode) { heatmapMode.value = value }
function setHoveredDate(value: string | null) { hoveredDate.value = value }
function setFocusedDate(value: string | null) { focusedDate.value = value }
function setHeatCellSize(value: number | ((prev: number) => number)) {
  heatCellSize.value = typeof value === 'function' ? value(heatCellSize.value) : value
}

// Watch for heatmap measure resize — mirror React useEffect([error, isLoading])
// Disconnect old observer before creating a new one, skip while loading/error
let resizeObserver: ResizeObserver | null = null

watch(
  [isLoading, error],
  ([loading, err]) => {
    // Tear down previous observer whenever loading state changes
    if (resizeObserver) {
      resizeObserver.disconnect()
      resizeObserver = null
    }

    if (loading || err) return

    const element = heatmapMeasureRef.value
    if (!element) return

    const updateCellSize = () => {
      const nextSize = calculateHeatCellSize(element.clientWidth)
      setHeatCellSize((prev) => (prev === nextSize ? prev : nextSize))
    }

    updateCellSize()

    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(updateCellSize)
      resizeObserver.observe(element)
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  resizeObserver?.disconnect()
})

// ─── Computed ────────────────────────────────────────────────────────────────

const days = computed(() => buildHeatmapDays(stats.value, heatmapMode.value))
const monthLabels = computed(() => buildMonthLabels(days.value, locale))
const today = computed(() => (days.value.length > 0 ? days.value[days.value.length - 1] : null))
const activeTooltipDate = computed(() => hoveredDate.value ?? focusedDate.value)
const tooltipDay = computed(() => days.value.find((day) => day.date === activeTooltipDate.value) ?? null)
const tooltipIndex = computed(() =>
  tooltipDay.value ? days.value.findIndex((day) => day.date === tooltipDay.value.date) : -1,
)
const heatGridWidth = computed(() => WEEK_COUNT * heatCellSize.value + (WEEK_COUNT - 1) * HEAT_CELL_GAP)
const heatGridHeight = computed(() => 7 * heatCellSize.value + 6 * HEAT_CELL_GAP)
const heatmapWidth = computed(() => HEAT_LABEL_WIDTH + heatGridWidth.value)
const tooltipStyle = computed(() =>
  tooltipIndex.value >= 0
    ? {
        left: Math.max(
          HEAT_LABEL_WIDTH,
          Math.min(
            heatmapWidth.value - TOOLTIP_WIDTH,
            HEAT_LABEL_WIDTH + Math.floor(tooltipIndex.value / 7) * (heatCellSize.value + HEAT_CELL_GAP) - 52,
          ),
        ),
        top: Math.max(28, 30 + (tooltipIndex.value % 7) * (heatCellSize.value + HEAT_CELL_GAP) - 50),
      }
    : undefined,
)
const last30Usage = computed(() => sumDailyUsage(days.value.slice(-30)))
const totalTokens = computed(() => {
  return (stats.value?.dailyModelTokens ?? []).reduce((sum, day) => sum + Object.values(day.tokensByModel).reduce((daySum, tokens) => daySum + tokens, 0), 0)
})
const totalToolCalls = computed(() => {
  return (stats.value?.dailyActivity ?? []).reduce((sum, day) => sum + day.toolCallCount, 0)
})
const totalSkillUses = computed(() => {
  return Object.values(stats.value?.skillUsage ?? {}).reduce((sum, count) => sum + count, 0)
})
const exploredSkillsCount = computed(() => Object.keys(stats.value?.skillUsage ?? {}).length)
const topModel = computed(() => {
  return Object.entries(stats.value?.modelUsage ?? {}).reduce<{ model: string; tokens: number } | null>(
    (top, [model, usage]) => {
      const tokens = getModelTokenTotal(usage)
      if (tokens <= 0) return top
      if (!top || tokens > top.tokens) return { model, tokens }
      return top
    },
    null,
  )
})
const peakTokens = computed(() => {
  return (stats.value?.dailyModelTokens ?? []).reduce((peak, day) => {
    const dayTotal = Object.values(day.tokensByModel).reduce((sum, tokens) => sum + tokens, 0)
    return Math.max(peak, dayTotal)
  }, 0)
})
const topPluginItems = computed(() => buildPluginAndSkillRankItems(stats.value))

const metrics = computed<SummaryMetric[]>(() => [
  {
    label: t('settings.activity.totalTokens'),
    value: formatTokens(totalTokens.value),
    detail: formatDayCount(stats.value?.activeDays ?? 0, t),
  },
  {
    label: t('settings.activity.peakTokens'),
    value: formatTokens(peakTokens.value),
    detail: stats.value?.peakActivityDay ? formatDateLabel(stats.value.peakActivityDay, locale) : undefined,
  },
  {
    label: t('settings.activity.longestTask'),
    value: formatTaskDuration(stats.value?.longestSession?.duration, locale, t),
    detail: stats.value?.longestSession ? formatMessageCount(stats.value.longestSession.messageCount, t) : undefined,
  },
  {
    label: t('settings.activity.currentStreak'),
    value: formatDayCount(stats.value?.streaks.currentStreak ?? 0, t),
    detail: today.value ? `${formatTokens(today.value.tokens)} ${t('settings.activity.tokens')}` : undefined,
  },
  {
    label: t('settings.activity.longestStreak'),
    value: formatDayCount(stats.value?.streaks.longestStreak ?? 0, t),
    detail: formatSessionCount(last30Usage.value.sessions, t),
  },
])

const insightMetrics = computed<InsightMetric[]>(() => [
  {
    label: t('settings.activity.activeRate'),
    value: formatPercent(stats.value?.activeDays ?? 0, stats.value?.totalDays ?? 0, locale),
  },
  {
    label: t('settings.activity.mostUsedModel'),
    value: topModel.value ? formatModelName(topModel.value.model) : t('settings.activity.none'),
    detail: topModel.value ? `${formatTokens(topModel.value.tokens)} ${t('settings.activity.tokens')}` : undefined,
  },
  {
    label: t('settings.activity.exploredSkills'),
    value: formatInteger(exploredSkillsCount.value, locale),
  },
  {
    label: t('settings.activity.totalSkillUses'),
    value: formatInteger(totalSkillUses.value, locale),
  },
  {
    label: t('settings.activity.totalToolCalls'),
    value: formatInteger(totalToolCalls.value, locale),
  },
  {
    label: t('settings.activity.totalSessions'),
    value: formatInteger(stats.value?.totalSessions ?? 0, locale),
  },
])

const avatarSrc = computed(() => (profile.value.avatarFile ? getProfileAvatarUrl(profile.value.avatarUpdatedAt) : DEFAULT_AVATAR_SRC))
const avatarClassName = computed(() =>
  profile.value.avatarFile
    ? 'h-full w-full object-cover'
    : 'h-full w-full scale-[1.28] object-contain transition-transform',
)
const profileSubtitleHref = computed(() => getProfileSubtitleHref(profile.value.subtitle))
const hasUsage = computed(() => Boolean(stats.value && (stats.value.totalSessions > 0 || totalTokens.value > 0)))
const modeOptions = computed(() => [
  { mode: 'daily' as const, label: t('settings.activity.mode.daily'), help: t('settings.activity.modeHelp.daily') },
  { mode: 'weekly' as const, label: t('settings.activity.mode.weekly'), help: t('settings.activity.modeHelp.weekly') },
  { mode: 'cumulative' as const, label: t('settings.activity.mode.cumulative'), help: t('settings.activity.modeHelp.cumulative') },
])

// ─── Actions ─────────────────────────────────────────────────────────────────

const saveProfile = async () => {
  setIsSavingProfile(true)
  setProfileError(null)
  setProfileStatus(null)
  try {
    const result = await desktopUiPreferencesApi.updateProfilePreferences({
      displayName: draftDisplayName.value,
      subtitle: draftSubtitle.value,
    })
    const nextProfile = withProfileDefaults(result.preferences.profile)
    setProfile(nextProfile)
    setDraftDisplayName(nextProfile.displayName)
    setDraftSubtitle(nextProfile.subtitle)
    setIsEditingProfile(false)
    setProfileStatus(t('settings.activity.profileSaved'))
  } catch (err) {
    setProfileError(err instanceof Error ? err.message : t('settings.activity.profileSaveFailed'))
  } finally {
    setIsSavingProfile(false)
  }
}

const handleAvatarChange = async (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  target.value = ''
  if (!file) return
  setIsSavingProfile(true)
  setProfileError(null)
  setProfileStatus(null)
  try {
    const result = await desktopUiPreferencesApi.uploadProfileAvatar(file)
    const nextProfile = withProfileDefaults(result.preferences.profile)
    setProfile(nextProfile)
    setDraftDisplayName(nextProfile.displayName)
    setDraftSubtitle(nextProfile.subtitle)
    setProfileStatus(t('settings.activity.profileSaved'))
  } catch (err) {
    setProfileError(err instanceof Error ? err.message : t('settings.activity.profileSaveFailed'))
  } finally {
    setIsSavingProfile(false)
  }
}

const removeAvatar = async () => {
  setIsSavingProfile(true)
  setProfileError(null)
  setProfileStatus(null)
  try {
    const result = await desktopUiPreferencesApi.deleteProfileAvatar()
    setProfile(withProfileDefaults(result.preferences.profile))
    setProfileStatus(t('settings.activity.profileSaved'))
  } catch (err) {
    setProfileError(err instanceof Error ? err.message : t('settings.activity.profileSaveFailed'))
  } finally {
    setIsSavingProfile(false)
  }
}

const triggerAvatarInput = () => {
  avatarInputRef.value?.click()
}

const openEditProfile = () => {
  setIsEditingProfile(true)
  setDraftDisplayName(profile.value.displayName)
  setDraftSubtitle(profile.value.subtitle)
}

const cancelEditProfile = () => {
  setIsEditingProfile(false)
  setDraftDisplayName(profile.value.displayName)
  setDraftSubtitle(profile.value.subtitle)
  setProfileError(null)
}

// Image error handler
const onAvatarError = (event: Event) => {
  const el = event.currentTarget as HTMLImageElement
  el.src = DEFAULT_AVATAR_SRC
  el.className = 'h-full w-full scale-[1.28] object-contain transition-transform'
}

// Expose for template use
const WEEKDAY_KEYS = WEEKDAY_LABEL_KEYS
</script>

<template>
  <div class="mx-auto w-full max-w-[1060px] min-w-0 pb-12">
    <!-- ─── Profile Header ─────────────────────────────────────────── -->
    <section class="relative flex min-h-[176px] flex-col items-center justify-start pt-4 text-center">
      <div class="relative h-16 w-16 overflow-hidden rounded-full border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] shadow-[0_10px_28px_-22px_rgba(15,23,42,0.6)]">
        <img
          :src="avatarSrc"
          :alt="`${profile.displayName} avatar`"
          :class="avatarClassName"
          @error="onAvatarError"
        />
      </div>
      <div class="group/activity-profile mt-4 flex max-w-full items-center justify-center gap-2">
        <h1 class="max-w-[min(720px,calc(100%-2.25rem))] truncate text-[28px] font-semibold tracking-tight text-[var(--color-text-primary)] sm:text-[34px]">
          {{ profile.displayName }}
        </h1>
        <button
          type="button"
          :aria-label="t('settings.activity.editProfile')"
          :title="t('settings.activity.editProfile')"
          class="mt-1 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[var(--color-text-tertiary)] opacity-0 transition-[background-color,color,opacity,transform] group-hover/activity-profile:opacity-100 hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] focus:ring-offset-2 focus:ring-offset-[var(--color-surface)] focus-visible:opacity-100 active:translate-y-[1px] disabled:pointer-events-none disabled:opacity-0"
          @click="openEditProfile"
          :disabled="isProfileLoading"
        >
          <span class="material-symbols-outlined text-[16px]" aria-hidden="true">edit</span>
        </button>
      </div>

      <a
        v-if="profileSubtitleHref"
        :href="profileSubtitleHref"
        target="_blank"
        rel="noreferrer"
        class="mt-2 inline-flex max-w-full items-center justify-center gap-2 truncate text-base text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text-primary)]"
      >
        <span>{{ profile.subtitle }}</span>
      </a>
      <div v-else class="mt-2 max-w-full truncate text-base text-[var(--color-text-tertiary)]">
        {{ profile.subtitle }}
      </div>

      <div v-if="profileStatus" class="mt-3 text-xs text-[var(--color-success)]">{{ profileStatus }}</div>
      <div v-if="profileError && !isEditingProfile" class="mt-3 text-xs text-[var(--color-error)]">{{ profileError }}</div>
    </section>

    <!-- ─── Summary Panel ──────────────────────────────────────────── -->
    <section class="activity-summary-panel mx-auto mt-7 w-full max-w-[900px] overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-border)] p-px shadow-[0_12px_34px_-32px_rgba(15,23,42,0.55)]">
      <div v-if="isLoading" class="activity-summary-grid grid gap-px">
        <div
          v-for="index in 5"
          :key="index"
          class="activity-summary-metric min-h-[76px] animate-pulse bg-[var(--color-surface)] px-4 py-3"
          :class="{ 'activity-summary-metric-primary': index === 1 }"
        >
          <div class="mx-auto h-5 w-16 rounded bg-[var(--color-surface-container)]" />
          <div class="mx-auto mt-2 h-3 w-20 rounded bg-[var(--color-surface-container)]" />
          <div class="mx-auto mt-2 h-2.5 w-14 rounded bg-[var(--color-surface-container)]" />
        </div>
      </div>
      <div v-else class="activity-summary-grid grid gap-px">
        <div
          v-for="(metric, index) in metrics"
          :key="metric.label"
          class="activity-summary-metric min-w-0 bg-[var(--color-surface-container-lowest)] px-4 py-3 text-center opacity-0 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)] [animation:activity-reveal_420ms_cubic-bezier(0.16,1,0.3,1)_forwards]"
          :class="{ 'activity-summary-metric-primary': index === 0 }"
          :style="{ animationDelay: `${index * 45}ms` }"
        >
          <div class="flex min-h-[68px] flex-col items-center justify-center gap-1.5">
            <div
              class="activity-summary-value max-w-full truncate font-semibold leading-none tracking-tight text-[var(--color-text-primary)] tabular-nums"
              :class="{ 'text-[23px]': index === 0, 'text-[22px]': index !== 0 }"
            >
              {{ metric.value }}
            </div>
            <div class="min-w-0 truncate text-[13px] font-medium leading-tight text-[var(--color-text-secondary)]">
              {{ metric.label }}
            </div>
            <div v-if="metric.detail" class="max-w-full truncate text-[11px] leading-tight text-[var(--color-text-tertiary)]">
              {{ metric.detail }}
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ─── Edit Profile Dialog ────────────────────────────────────── -->
    <teleport to="body">
      <div
        v-if="isEditingProfile"
        class="fixed inset-0 z-[10000] flex items-center justify-center bg-[var(--color-overlay-scrim)] px-4 py-8"
        role="dialog"
        aria-modal="true"
        aria-labelledby="activity-profile-dialog-title"
      >
        <div class="w-full max-w-[420px] rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] p-5 shadow-2xl">
          <div class="flex items-start justify-between gap-4">
            <div>
              <h2 id="activity-profile-dialog-title" class="text-base font-semibold text-[var(--color-text-primary)]">
                {{ t('settings.activity.editProfile') }}
              </h2>
              <p class="mt-1 text-xs text-[var(--color-text-tertiary)]">
                {{ t('settings.activity.displayNameHelper') }}
              </p>
            </div>
            <button
              type="button"
              class="inline-flex h-8 w-8 items-center justify-center rounded-md text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
              @click="cancelEditProfile"
              :aria-label="t('settings.activity.cancelEdit')"
            >
              <span class="material-symbols-outlined text-[17px]" aria-hidden="true">close</span>
            </button>
          </div>

          <div class="mt-5 grid gap-4">
            <div class="grid gap-2">
              <label for="activity-profile-display-name" class="text-xs font-medium text-[var(--color-text-secondary)]">
                {{ t('settings.activity.displayName') }}
              </label>
              <input
                id="activity-profile-display-name"
                v-model="draftDisplayName"
                class="h-10 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-sm text-[var(--color-text-primary)] outline-none transition-colors focus:border-[var(--color-border-focus)]"
              />
            </div>

            <div class="grid gap-2">
              <label for="activity-profile-subtitle" class="text-xs font-medium text-[var(--color-text-secondary)]">
                {{ t('settings.activity.subtitle') }}
              </label>
              <input
                id="activity-profile-subtitle"
                v-model="draftSubtitle"
                class="h-10 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-sm text-[var(--color-text-primary)] outline-none transition-colors focus:border-[var(--color-border-focus)]"
              />
            </div>

            <div class="grid gap-2">
              <div class="text-xs font-medium text-[var(--color-text-secondary)]">
                {{ t('settings.activity.avatar') }}
              </div>
              <p class="text-xs text-[var(--color-text-tertiary)]">
                {{ t('settings.activity.avatarHelper') }}
              </p>
              <div class="flex flex-wrap gap-2">
                <input
                  ref="avatarInputRef"
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  class="hidden"
                  @change="handleAvatarChange"
                />
                <button
                  type="button"
                  class="inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--color-border)] px-2.5 text-xs font-medium text-[var(--color-text-secondary)] transition-[background-color,transform] hover:bg-[var(--color-surface-hover)] active:translate-y-[1px]"
                  @click="triggerAvatarInput"
                >
                  <span class="material-symbols-outlined text-[15px]" aria-hidden="true">upload</span>
                  {{ t('settings.activity.changeAvatar') }}
                </button>
                <button
                  v-if="profile.avatarFile"
                  type="button"
                  class="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium text-[var(--color-text-tertiary)] transition-[background-color,transform] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] active:translate-y-[1px]"
                  @click="removeAvatar"
                >
                  {{ t('settings.activity.removeAvatar') }}
                </button>
              </div>
            </div>
          </div>

          <div v-if="profileError" class="mt-4 rounded-md border border-[var(--color-error)]/30 bg-[var(--color-error)]/10 px-3 py-2 text-xs text-[var(--color-error)]">
            {{ profileError }}
          </div>

          <div class="mt-5 flex justify-end gap-2">
            <button
              type="button"
              class="h-8 rounded-md px-3 text-xs font-medium text-[var(--color-text-secondary)] transition-[background-color,transform] hover:bg-[var(--color-surface-hover)] active:translate-y-[1px]"
              @click="cancelEditProfile"
            >
              {{ t('settings.activity.cancelEdit') }}
            </button>
            <button
              type="button"
              class="h-8 rounded-md bg-[var(--color-text-primary)] px-3 text-xs font-medium text-[var(--color-surface)] transition-[opacity,transform] active:translate-y-[1px] disabled:opacity-50"
              @click="saveProfile"
              :disabled="isSavingProfile"
            >
              {{ t('settings.activity.saveProfile') }}
            </button>
          </div>
        </div>
      </div>
    </teleport>

    <!-- ─── Token Activity Heatmap ─────────────────────────────────── -->
    <div class="mt-10">
      <div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 class="text-xl font-semibold text-[var(--color-text-primary)]">
            {{ t('settings.activity.tokenActivity') }}
          </h2>
        </div>
        <div class="inline-flex w-fit items-center gap-7">
          <button
            v-for="option in modeOptions"
            :key="option.mode"
            type="button"
            :aria-pressed="heatmapMode === option.mode"
            :title="option.help"
            class="text-lg font-semibold transition-[color,transform] active:translate-y-[1px]"
            :class="heatmapMode === option.mode ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)]'"
            @click="heatmapMode = option.mode"
          >
            {{ option.label }}
          </button>
        </div>
      </div>

      <!-- Loading skeleton -->
      <div v-if="isLoading" class="min-h-[190px] space-y-3">
        <div class="h-4 w-1/4 animate-pulse rounded bg-[var(--color-surface-container)]" />
        <div class="grid grid-flow-col gap-[3px]">
          <div v-for="col in 52" :key="col" class="grid grid-rows-7 gap-[3px]">
            <div v-for="row in 7" :key="row" class="h-2.5 w-2.5 animate-pulse rounded-[3px] bg-[var(--color-surface-container)]" />
          </div>
        </div>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="rounded-md border border-[var(--color-error)]/30 bg-[var(--color-error)]/10 px-4 py-3 text-sm text-[var(--color-error)]">
        {{ error }}
      </div>

      <!-- Empty state -->
      <div v-else-if="!hasUsage" class="flex min-h-[190px] items-center justify-center">
        <div class="max-w-sm text-center">
          <div class="mx-auto flex h-11 w-11 items-center justify-center rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] text-[var(--color-text-tertiary)]">
            <span class="material-symbols-outlined text-[20px]" aria-hidden="true">monitoring</span>
          </div>
          <div class="mt-3 text-sm font-medium text-[var(--color-text-primary)]">
            {{ t('settings.activity.emptyTitle') }}
          </div>
          <p class="mt-1 text-sm leading-5 text-[var(--color-text-tertiary)]">
            {{ t('settings.activity.emptyBody') }}
          </p>
        </div>
      </div>

      <!-- Heatmap -->
      <template v-else>
        <div ref="heatmapMeasureRef" class="min-w-0 pb-2">
          <div class="relative" :style="{ width: heatmapWidth, maxWidth: '100%' }">
            <!-- Month labels -->
            <div
              class="mb-3 grid h-5 text-[11px] leading-none text-[var(--color-text-tertiary)]"
              :style="{
                marginLeft: HEAT_LABEL_WIDTH,
                gridTemplateColumns: `repeat(${WEEK_COUNT}, ${heatCellSize}px)`,
                columnGap: HEAT_CELL_GAP,
              }"
            >
              <div
                v-for="month in monthLabels"
                :key="`${month.week}-${month.label}`"
                :style="{ gridColumn: `${month.week + 1} / span 4` }"
              >
                {{ month.label }}
              </div>
            </div>

            <!-- Heatmap grid -->
            <div class="flex items-start" :style="{ gap: HEAT_CELL_GAP }">
              <!-- Weekday labels -->
              <div
                class="grid shrink-0 grid-rows-7 text-[11px] leading-none text-[var(--color-text-tertiary)]"
                :style="{ width: HEAT_LABEL_WIDTH, height: heatGridHeight, rowGap: HEAT_CELL_GAP }"
              >
                <div class="row-start-2 flex items-center">{{ t(WEEKDAY_KEYS[0]) }}</div>
                <div class="row-start-4 flex items-center">{{ t(WEEKDAY_KEYS[1]) }}</div>
                <div class="row-start-6 flex items-center">{{ t(WEEKDAY_KEYS[2]) }}</div>
              </div>

              <!-- Cells -->
              <div
                role="grid"
                :aria-label="t('settings.activity.heatmapLabel')"
                class="grid grid-flow-col"
                :style="{
                  gridTemplateRows: `repeat(7, ${heatCellSize}px)`,
                  gridAutoColumns: `${heatCellSize}px`,
                  columnGap: HEAT_CELL_GAP,
                  rowGap: HEAT_CELL_GAP,
                }"
                @mouseleave="hoveredDate = null"
              >
                <button
                  v-for="day in days"
                  :key="day.date"
                  type="button"
                  role="gridcell"
                  :aria-label="`${getHeatmapCellTitle(day, locale, t)}: ${getHeatmapCellDetail(day, t)}`"
                  :aria-describedby="activeTooltipDate === day.date ? `activity-day-tooltip-${day.date}` : undefined"
                  class="activity-heat-cell rounded-[3px] border focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] focus:ring-offset-2 focus:ring-offset-[var(--color-surface)]"
                  :class="
                    activeTooltipDate === day.date
                      ? 'is-active border-[var(--color-activity-cell-border-active)]'
                      : 'border-[var(--color-activity-cell-border)] hover:border-[var(--color-activity-cell-border-hover)]'
                  "
                  :style="{
                    width: heatCellSize,
                    height: heatCellSize,
                    backgroundColor: HEAT_COLORS[day.level],
                  }"
                  @focus="focusedDate = day.date"
                  @blur="focusedDate = null"
                  @mouseenter="hoveredDate = day.date"
                />
              </div>
            </div>

            <!-- Tooltip -->
            <div
              v-if="tooltipDay"
              :id="`activity-day-tooltip-${tooltipDay.date}`"
              role="tooltip"
              class="pointer-events-none absolute z-20 min-w-[172px] rounded-md border border-[var(--color-activity-tooltip-border)] bg-[var(--color-activity-tooltip-surface)] px-3 py-2 text-xs shadow-xl"
              :style="tooltipStyle"
            >
              <div class="font-medium text-[var(--color-activity-tooltip-text)]">
                {{ getHeatmapCellTitle(tooltipDay, locale, t) }}
              </div>
              <div class="mt-1 text-[var(--color-activity-tooltip-muted)]">
                {{ getHeatmapCellDetail(tooltipDay, t) }}
              </div>
            </div>
          </div>
        </div>

        <!-- Legend -->
        <div class="mt-3 flex items-center justify-end gap-2 text-xs text-[var(--color-text-tertiary)] xl:mt-4">
          <span>{{ t('settings.activity.less') }}</span>
          <span
            v-for="color in HEAT_COLORS"
            :key="color"
            aria-hidden="true"
            class="rounded-[3px] border border-[var(--color-activity-cell-border)]"
            :style="{ width: heatCellSize, height: heatCellSize, backgroundColor: color }"
          />
          <span>{{ t('settings.activity.more') }}</span>
        </div>
      </template>
    </div>

    <!-- ─── Insights & Plugins ─────────────────────────────────────── -->
    <div
      v-if="!isLoading && !error && hasUsage"
      class="mt-12 grid gap-10"
      :class="topPluginItems.length > 0 ? 'lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1fr)]' : 'lg:max-w-[520px]'"
    >
      <section class="min-w-0">
        <h2 class="text-lg font-semibold text-[var(--color-text-primary)]">
          {{ t('settings.activity.activityInsights') }}
        </h2>
        <dl class="mt-5 grid gap-3">
          <div
            v-for="metric in insightMetrics"
            :key="metric.label"
            class="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-5"
          >
            <dt class="min-w-0 truncate text-sm font-medium text-[var(--color-text-tertiary)]">
              {{ metric.label }}
            </dt>
            <dd class="min-w-0 text-right text-sm font-semibold text-[var(--color-text-primary)]">
              <span class="tabular-nums">{{ metric.value }}</span>
              <span
                v-if="metric.detail"
                class="ml-2 text-xs font-medium text-[var(--color-text-tertiary)]"
              >
                {{ metric.detail }}
              </span>
            </dd>
          </div>
        </dl>
      </section>

      <section v-if="topPluginItems.length > 0" class="min-w-0">
        <h2 class="text-lg font-semibold text-[var(--color-text-primary)]">
          {{ t('settings.activity.mostUsedPluginsAndSkills') }}
        </h2>
        <div class="mt-5 grid gap-3">
          <div
            v-for="item in topPluginItems"
            :key="item.id"
            class="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3"
          >
            <span class="flex h-7 w-7 items-center justify-center rounded-md border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] text-[var(--color-text-tertiary)]">
              <span class="material-symbols-outlined text-[16px]" aria-hidden="true">
                {{ item.kind === 'skill' ? 'extension' : 'hub' }}
              </span>
            </span>
            <span class="min-w-0 truncate text-sm font-medium text-[var(--color-text-primary)]">
              {{ item.label }}
            </span>
            <span class="text-sm text-[var(--color-text-tertiary)] tabular-nums">
              {{ formatRunCount(item.count, t) }}
            </span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>