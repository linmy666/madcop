<script setup lang="ts">
/**
 * LocalSlashCommandPanel — Vue 3 SFC full translation of
 * components/chat/LocalSlashCommandPanel.tsx (1118 lines)
 *
 * Shows panels for /mcp, /skills, /help, /status, /cost, /context
 */

import {
  ref,
  computed,
  watch,
  onMounted,
  defineComponent,
  h,
  type PropType,
  type VNode,
} from 'vue'

// ─── API ──────────────────────────────────────────────────────
import { skillsApi } from '../../../api/skills'
import { mcpApi } from                    '../../../api/mcp'
import {
  sessionsApi,
  type SessionContextSnapshot,
  type SessionInspectionResponse,
  type SessionUsageSnapshot,
} from                    '../../../api/sessions'

// ─── i18n ─────────────────────────────────────────────────────
import { useTranslation, type TranslationKey } from '../../../i18n'

// ─── Stores ───────────────────────────────────────────────────
import { useUIStore } from                    '../../../stores/uiStore'
import { SETTINGS_TAB_ID, useTabStore } from  '../../../stores/tabStore'
import { useMcpStore } from                   '../../../stores/mcpStore'
import { useSkillStore } from                 '../../../stores/skillStore'

// ─── Types ────────────────────────────────────────────────────
import type { McpServerRecord } from  '../../../types/mcp'
import type { SkillMeta } from        '../../../types/skill'
import type { SlashCommandOption } from '../../../types/slash'

// ─── Prop Types ───────────────────────────────────────────────
export type LocalSlashCommandName = 'mcp' | 'skills' | 'help' | 'status' | 'cost' | 'context'

const props = defineProps({
  command: { type: String as PropType<LocalSlashCommandName>, required: true },
  sessionId: { type: String as PropType<string | undefined>, default: undefined },
  cwd: { type: String as PropType<string | undefined>, default: undefined },
  commands: { type: Array as PropType<SlashCommandOption[] | undefined>, default: undefined },
  onClose: { type: Function as PropType<() => void>, required: true },
})

const t = useTranslation()
const setPendingSettingsTab = useUIStore((s) => s.setPendingSettingsTab)
const selectServer = useMcpStore((s) => s.selectServer)
const fetchSkillDetail = useSkillStore((s) => s.fetchSkillDetail)

// ══════════════════════════════════════════════════════════════
// Helper functions
// ══════════════════════════════════════════════════════════════

type SessionInspectorTab = 'status' | 'usage' | 'context'

function toneForStatus(status: McpServerRecord['status']): string {
  switch (status) {
    case 'connected':
      return 'bg-[var(--color-inspector-success-bg)] text-[var(--color-inspector-success)] border-[var(--color-inspector-border)]'
    case 'needs-auth':
      return 'bg-[var(--color-surface-container-low)] text-[var(--color-warning)] border-[var(--color-border)]'
    case 'failed':
      return 'bg-[var(--color-inspector-danger-bg)] text-[var(--color-inspector-danger)] border-[var(--color-inspector-border)]'
    case 'disabled':
      return 'bg-[var(--color-surface-hover)] text-[var(--color-text-secondary)] border-[var(--color-border)]'
    default:
      return ''
  }
}

function scopeLabel(scope: string): string {
  switch (scope) {
    case 'user':
      return t('settings.mcp.scope.user')
    case 'local':
      return t('settings.mcp.scope.local')
    case 'project':
      return t('settings.mcp.scope.project')
    default:
      return scope
  }
}

function projectBadge(path?: string): string | null {
  if (!path) return null
  const label = path.replace(/\/$/, '').split('/').pop() || path
  return t('slash.mcp.projectBadge', { name: label })
}

function formatNumber(value: number | undefined): string {
  return new Intl.NumberFormat().format(value ?? 0)
}

function formatDuration(seconds: number | undefined): string {
  const total = Math.max(0, Math.round(seconds ?? 0))
  if (total < 60) return `${total}s`
  const minutes = Math.floor(total / 60)
  const remaining = total % 60
  return remaining ? `${minutes}m ${remaining}s` : `${minutes}m`
}

function formatPercent(value: number | undefined): string {
  const percent = Math.max(0, Math.min(100, value ?? 0))
  return `${percent.toFixed(percent >= 10 || Number.isInteger(percent) ? 0 : 1)}%`
}

function sessionInspectorInitialTab(command: LocalSlashCommandName): SessionInspectorTab {
  if (command === 'cost') return 'usage'
  if (command === 'context') return 'context'
  return 'status'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object')
}

function isSessionInspectionResponse(value: unknown): value is SessionInspectionResponse {
  if (!isRecord(value)) return false
  if (typeof value.active !== 'boolean') return false
  if (!isRecord(value.status)) return false
  return (
    typeof (value.status as any).sessionId === 'string' &&
    typeof (value.status as any).workDir === 'string' &&
    typeof (value.status as any).permissionMode === 'string'
  )
}

function assertSessionInspectionResponse(value: unknown): SessionInspectionResponse {
  if (isSessionInspectionResponse(value)) return value
  throw new Error(t('slash.inspector.error.unavailable'))
}

function isCapacityCategory(category: ContextCategory): boolean {
  const name = category.name.toLowerCase()
  return category.isDeferred || name.includes('free') || name.includes('autocompact')
}

function memoryContextFileLabel(path: string): string {
  const normalized = path.replace(/\\/g, '/')
  return normalized.split('/').pop() || normalized
}

function statusDisplayLabel(status: string): string {
  const normalized = status.toLowerCase()
  if (normalized === 'connected') return t('slash.inspector.status.connected')
  if (normalized === 'failed') return t('slash.inspector.status.failed')
  return status
}

// COMMAND_GROUPS
const COMMAND_GROUPS = [
  {
    titleKey: 'slash.help.group.context' as TranslationKey,
    names: ['clear', 'compact', 'context', 'cost'],
  },
  {
    titleKey: 'slash.help.group.project' as TranslationKey,
    names: ['init', 'review', 'commit', 'pr'],
  },
  {
    titleKey: 'slash.help.group.desktop' as TranslationKey,
    names: ['mcp', 'skills', 'plugin', 'help'],
  },
] as const

// ══════════════════════════════════════════════════════════════
// Utility type: render children from VNode[] | VNode | string
// ══════════════════════════════════════════════════════════════

type RenderResult = VNode | VNode[] | string | null | undefined

function renderSlot(children: RenderResult): RenderResult[] {
  if (children == null) return []
  if (Array.isArray(children)) return children as VNode[]
  return [children as VNode | string]
}

// ══════════════════════════════════════════════════════════════
// Sub-components (render functions — no template)
// ══════════════════════════════════════════════════════════════

// PanelShell
function renderPanelShell(
  title: string,
  subtitle: string,
  onClose: () => void,
  body: RenderResult
): VNode {
  return h(
    'div',
    {
      class:
        'absolute bottom-full left-0 right-0 z-50 mb-3 overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] shadow-[var(--shadow-dropdown)]',
    },
    [
      h(
        'div',
        { class: 'flex items-start justify-between gap-4 border-b border-[var(--color-border)] px-5 py-4' },
        [
          h('div', undefined, [
            h('h3', { class: 'text-lg font-semibold text-[var(--color-text-primary)]' }, title),
            h('p', { class: 'mt-1 text-sm text-[var(--color-text-tertiary)]' }, subtitle),
          ]),
          h(
            'button',
            {
              type: 'button',
              onClick: onClose,
              class:
                'flex h-9 w-9 items-center justify-center rounded-full text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]',
            },
            h('span', { class: 'material-symbols-outlined text-[18px]' }, 'close')
          ),
        ]
      ),
      h('div', { class: 'max-h-[min(620px,72vh)] overflow-y-auto px-5 py-4' }, renderSlot(body)),
    ]
  )
}

function renderLoadingState(label: string): VNode {
  return h(
    'div',
    { class: 'flex items-center justify-center py-12 text-sm text-[var(--color-text-tertiary)]' },
    [
      h('div', { class: 'mr-3 h-5 w-5 animate-spin rounded-full border-2 border-[var(--color-brand)] border-t-transparent' }),
      label,
    ]
  )
}

function renderEmptyState(title: string, body: string): VNode {
  return h(
    'div',
    { class: 'rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-10 text-center' },
    [
      h('div', { class: 'text-sm font-semibold text-[var(--color-text-primary)]' }, title),
      h('div', { class: 'mt-2 text-xs leading-6 text-[var(--color-text-tertiary)]' }, body),
    ]
  )
}

function renderErrorState(message: string): VNode {
  return h(
    'div',
    { class: 'rounded-2xl border border-[var(--color-inspector-border)] bg-[var(--color-inspector-panel)] px-5 py-4 text-sm text-[var(--color-inspector-danger)]' },
    message
  )
}

function renderInspectorSectionTitle(
  title: string | VNode | VNode[],
  action?: VNode | null
): VNode {
  return h(
    'div',
    { class: 'mb-3 flex items-center justify-between gap-4' },
    [
      h('div', { class: 'font-mono text-[12px] font-semibold uppercase tracking-[0.24em] text-[var(--color-inspector-heading)]' }, renderSlot(title)),
      action ?? null,
    ]
  )
}

function renderMetricCard(label: string, value: RenderResult, detail?: RenderResult): VNode {
  return h(
    'div',
    { class: 'min-h-[82px] rounded-md border border-[var(--color-inspector-border)] bg-[var(--color-inspector-panel)] px-4 py-4 font-mono' },
    [
      h('div', { class: 'text-[12px] uppercase tracking-[0.2em] text-[var(--color-inspector-heading)]' }, label),
      h('div', { class: 'mt-3 whitespace-pre-line text-[15px] leading-6 text-[var(--color-inspector-text)]' }, renderSlot(value)),
      detail ? h('div', { class: 'mt-1 text-[13px] leading-5 text-[var(--color-inspector-muted)]' }, renderSlot(detail)) : null,
    ]
  )
}

function renderInspectorNotice(content: RenderResult): VNode {
  return h(
    'div',
    { class: 'flex items-center gap-3 rounded-md border border-[var(--color-inspector-border)] bg-[var(--color-inspector-surface)] px-4 py-3 text-[14px] text-[var(--color-inspector-heading)]' },
    [
      h('span', { class: 'material-symbols-outlined text-[18px] text-[var(--color-inspector-muted)]' }, 'info'),
      h('span', undefined, renderSlot(content)),
    ]
  )
}

function renderKeyValueRows(rows: Array<[string, RenderResult]>): VNode {
  return h(
    'div',
    { class: 'overflow-hidden rounded-md border border-[var(--color-inspector-border)] bg-[var(--color-inspector-surface)] font-mono' },
    rows.map(([label, value], idx) =>
      h('div', {
        key: label,
        class: idx === 0
          ? 'grid grid-cols-[220px_minmax(0,1fr)]'
          : 'grid grid-cols-[220px_minmax(0,1fr)] border-t border-[var(--color-inspector-border)]',
      }, [
        h('div', { class: 'border-r border-[var(--color-inspector-border)] bg-[var(--color-inspector-panel)] px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.24em] text-[var(--color-inspector-heading)]' }, label),
        h('div', { class: 'min-w-0 break-words px-4 py-3 text-[14px] text-[var(--color-inspector-text)]' }, renderSlot(value)),
      ])
    )
  )
}

// McpServerIcon
function renderMcpServerIcon(status: string): VNode {
  const isFailed = status === 'failed'
  return h(
    'span',
    {
      class: `material-symbols-outlined text-[20px] ${isFailed ? 'text-[var(--color-inspector-danger)]' : 'text-[var(--color-inspector-success)]'}`,
    },
    isFailed ? 'power_off' : 'dns'
  )
}

// InspectorStatusBadge
function renderInspectorStatusBadge(status: string): VNode {
  const normalized = status.toLowerCase()
  const isConnected = normalized === 'connected'
  const isFailed = normalized === 'failed'
  const badgeClass = isConnected
    ? 'bg-[var(--color-inspector-success-bg)] text-[var(--color-inspector-success)]'
    : isFailed
      ? 'bg-[var(--color-inspector-danger-bg)] text-[var(--color-inspector-danger)]'
      : 'bg-[var(--color-inspector-chip)] text-[var(--color-inspector-muted-strong)]'
  const dotClass = isConnected
    ? 'bg-[var(--color-inspector-success)]'
    : isFailed ? 'bg-[var(--color-inspector-danger)]' : 'bg-[var(--color-inspector-muted)]'
  return h(
    'span',
    { class: `inline-flex items-center gap-1.5 rounded-sm px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] ${badgeClass}` },
    [
      h('span', { class: `h-1.5 w-1.5 rounded-full ${dotClass}` }),
      statusDisplayLabel(status),
    ]
  )
}

// ══════════════════════════════════════════════════════════════
// StatusTab build function
// ══════════════════════════════════════════════════════════════

function buildStatusTab(data: SessionInspectionResponse, commands?: SlashCommandOption[]): VNode {
  const mcpServers = Array.isArray(data.status.mcpServers) ? data.status.mcpServers : []
  const tools = Array.isArray(data.status.tools) ? data.status.tools : []
  const context = (data.context ?? (data as any).contextEstimate) as SessionContextSnapshot | undefined
  const usageModels = data.usage?.models ?? []
  const model =
    data.status.model ??
    context?.model ??
    usageModels[0]?.displayName ??
    usageModels[0]?.model ??
    t('slash.inspector.status.unknown')
  const contextWindow =
    context?.rawMaxTokens ??
    usageModels.find((entry: any) => entry.contextWindow > 0)?.contextWindow
  const slashCommandCount =
    (data.status.slashCommandCount ?? 0) > 0 ? data.status.slashCommandCount : (commands?.length ?? 0)
  const connectedMcp = mcpServers.filter((s) => s.status === 'connected').length
  const failedMcp = mcpServers.filter((s) => s.status === 'failed').length

  const children: VNode[] = []

  // Metric cards row
  children.push(
    h('div', { class: 'grid grid-cols-2 gap-4 lg:grid-cols-4' }, [
      renderMetricCard(
        t('slash.inspector.status.cliStatus'),
        h('span', { class: 'inline-flex items-center gap-2' }, [
          h('span', { class: `h-2 w-2 rounded-full ${data.active ? 'bg-[var(--color-inspector-success)]' : 'bg-[var(--color-inspector-danger)]'}` }),
          data.active ? t('slash.inspector.status.running') : t('slash.inspector.status.notRunning'),
        ])
      ),
      renderMetricCard(
        t('slash.inspector.status.activeModel'),
        model,
        contextWindow ? `${t('slash.inspector.status.contextWindow')}: ${formatNumber(contextWindow)}` : undefined
      ),
      renderMetricCard(
        t('slash.inspector.status.mcpConnections'),
        h('span', undefined, [
          h('span', { class: 'text-[var(--color-inspector-success)]' }, formatNumber(connectedMcp)),
          h('span', { class: 'mx-5 text-[var(--color-inspector-text)]' }, '/'),
          h('span', { class: 'text-[var(--color-inspector-danger)]' }, formatNumber(failedMcp)),
        ]),
        h('span', undefined, [
          h('span', { class: 'text-[var(--color-inspector-success)]' }, t('slash.inspector.status.connected')),
          h('span', { class: 'mx-5 text-[var(--color-inspector-text)]' }),
          h('span', { class: 'text-[var(--color-inspector-danger)]' }, t('slash.inspector.status.failed')),
        ])
      ),
      renderMetricCard(
        t('slash.inspector.status.registeredTools'),
        `${formatNumber(tools.length)} / ${formatNumber(slashCommandCount)} ${t('slash.inspector.status.commands')}`
      ),
    ])
  )

  // Session metadata
  children.push(
    h('section', undefined, [
      renderInspectorSectionTitle(t('slash.inspector.status.sessionMetadata')),
      renderKeyValueRows([
        [t('slash.inspector.status.version'), data.status.version ?? t('slash.inspector.status.unknown')],
        [t('slash.inspector.status.sessionId'), h('span', { class: 'font-mono text-[13px]' }, data.status.sessionId)],
        [t('slash.inspector.status.workingDirectory'), h('span', { class: 'font-mono text-[13px]' }, data.status.cwd ?? data.status.workDir)],
        [t('slash.inspector.status.permissionMode'), h('span', { class: 'rounded-sm bg-[var(--color-inspector-chip)] px-1.5 py-1' }, data.status.permissionMode)],
        [t('slash.inspector.status.authToken'), data.status.apiKeySource ?? t('slash.inspector.status.unknown')],
        [t('slash.inspector.status.outputStyle'), data.status.outputStyle ?? t('slash.inspector.status.default')],
      ]),
    ])
  )

  // MCP servers
  if (mcpServers.length > 0) {
    children.push(
      h('section', undefined, [
        renderInspectorSectionTitle(
          t('slash.inspector.status.mcpServers'),
          h('button', {
            type: 'button',
            class: 'font-mono text-[12px] tracking-[0.18em] text-[var(--color-inspector-accent)] hover:text-[var(--color-inspector-accent-hover)]',
          }, `↻ ${t('slash.inspector.status.refresh')}`)
        ),
        h('div', { class: 'grid gap-3 lg:grid-cols-2' },
          mcpServers.map((server) =>
            h(
              'div',
              {
                key: `${server.name}:${server.status}`,
                class: 'flex min-h-[48px] items-center justify-between gap-4 rounded-md border border-[var(--color-inspector-border)] bg-[var(--color-inspector-panel)] px-4 py-3 font-mono',
              },
              [
                h('div', { class: 'flex min-w-0 items-center gap-3' }, [
                  renderMcpServerIcon(server.status),
                  h('span', { class: 'min-w-0 truncate text-[14px] text-[var(--color-inspector-text)]' }, server.name),
                ]),
                renderInspectorStatusBadge(server.status),
              ]
            )
          )
        ),
      ])
    )
  }

  return h('div', { class: 'space-y-8' }, children)
}

// ══════════════════════════════════════════════════════════════
// UsageTab build function
// ══════════════════════════════════════════════════════════════

function buildUsageTab(
  usage?: SessionUsageSnapshot | null,
  context?: SessionContextSnapshot | null,
  error?: string
): VNode {
  if (error && !usage) return renderErrorState(error)
  if (!usage) {
    return renderEmptyState(t('slash.inspector.usage.emptyTitle'), t('slash.inspector.usage.emptyBody'))
  }

  const usageHasTokens =
    usage.totalInputTokens +
    usage.totalOutputTokens +
    usage.totalCacheReadInputTokens +
    usage.totalCacheCreationInputTokens > 0

  const apiUsage = context?.apiUsage
  const useContextUsageFallback = !usageHasTokens && !!apiUsage
  const totalInputTokens = useContextUsageFallback ? (apiUsage?.input_tokens ?? 0) : usage.totalInputTokens
  const totalOutputTokens = useContextUsageFallback ? (apiUsage?.output_tokens ?? 0) : usage.totalOutputTokens
  const totalCacheReadInputTokens = useContextUsageFallback ? (apiUsage?.cache_read_input_tokens ?? 0) : usage.totalCacheReadInputTokens
  const totalCacheCreationInputTokens = useContextUsageFallback ? (apiUsage?.cache_creation_input_tokens ?? 0) : usage.totalCacheCreationInputTokens

  const models: any[] = []
  if (Array.isArray(usage.models) && usage.models.length > 0) {
    models.push(...usage.models)
  } else if (useContextUsageFallback) {
    models.push({
      model: context?.model ?? 'current-model',
      displayName: context?.model ?? t('slash.inspector.status.activeModel'),
      inputTokens: totalInputTokens,
      outputTokens: totalOutputTokens,
      cacheReadInputTokens: totalCacheReadInputTokens,
      cacheCreationInputTokens: totalCacheCreationInputTokens,
      webSearchRequests: 0,
      costUSD: 0,
      costDisplay: 'n/a',
      contextWindow: (context as any)?.rawMaxTokens ?? 0,
      maxOutputTokens: 0,
    })
  }

  const sourceLabel = useContextUsageFallback
    ? t('slash.inspector.usage.source.contextSnapshot')
    : usage.source === 'transcript'
      ? t('slash.inspector.usage.source.transcript')
      : t('slash.inspector.usage.source.currentProcess')

  const children: VNode[] = []

  if (useContextUsageFallback) {
    children.push(renderInspectorNotice(t('slash.inspector.usage.contextSnapshotNotice')))
  }
  if (usage.source === 'transcript') {
    children.push(
      h(
        'div',
        { class: 'rounded-md border border-[var(--color-inspector-border)] bg-[var(--color-inspector-surface)] px-4 py-3 text-sm text-[var(--color-inspector-muted-strong)]' },
        t('slash.inspector.usage.transcriptNotice')
      )
    )
  }
  if (usage.hasUnknownModelCost) {
    children.push(
      h(
        'div',
        { class: 'rounded-xl border border-[var(--color-inspector-border)] bg-[var(--color-inspector-panel)] px-4 py-3 text-sm text-[var(--color-warning)]' },
        t('slash.inspector.usage.unknownCost')
      )
    )
  }

  // Metric cards
  children.push(
    h('div', { class: 'grid grid-cols-2 gap-4 lg:grid-cols-4' }, [
      renderMetricCard(t('slash.inspector.usage.totalCost'), useContextUsageFallback ? 'n/a' : (usage.costDisplay ?? 'n/a')),
      renderMetricCard(t('slash.inspector.usage.source'), sourceLabel),
      renderMetricCard(t('slash.inspector.usage.apiDuration'),
        (usage.source === 'transcript' || useContextUsageFallback) ? '0ms' : formatDuration(usage.totalAPIDuration)),
      renderMetricCard(
        usage.source === 'transcript' ? t('slash.inspector.usage.usageSpan') : t('slash.inspector.usage.wallDuration'),
        useContextUsageFallback ? '0ms' : formatDuration(usage.totalDuration)
      ),
      renderMetricCard(t('slash.inspector.usage.codeChanges'),
        `${formatNumber(usage.totalLinesAdded)}/${formatNumber(usage.totalLinesRemoved)}`),
      renderMetricCard(t('slash.inspector.usage.input'), formatNumber(totalInputTokens)),
      renderMetricCard(t('slash.inspector.usage.output'), formatNumber(totalOutputTokens)),
      renderMetricCard(t('slash.inspector.usage.cacheReadWrite'),
        `${formatNumber(totalCacheReadInputTokens)} / ${formatNumber(totalCacheCreationInputTokens)}`),
      renderMetricCard(t('slash.inspector.usage.webSearch'), formatNumber(usage.totalWebSearchRequests)),
    ])
  )

  // By model section
  children.push(
    h('section', undefined, [
      h('div', { class: 'mb-3 text-[22px] font-semibold text-[var(--color-inspector-text)]' }, t('slash.inspector.usage.byModel')),
      models.length === 0
        ? renderEmptyState(t('slash.inspector.usage.noModelTitle'), t('slash.inspector.usage.noModelBody'))
        : h(
            'div',
            { class: 'overflow-hidden rounded-md border border-[var(--color-inspector-border)] bg-[var(--color-inspector-surface)] font-mono' },
            models.map((model: any) =>
              h('div', { key: model.model, class: 'border-t border-[var(--color-inspector-border)] first:border-t-0' }, [
                h(
                  'div',
                  { class: 'grid grid-cols-[minmax(0,1fr)_120px] items-center gap-4 border-b border-[var(--color-inspector-border)] px-4 py-3' },
                  [
                    h('div', { class: 'min-w-0' }, [
                      h('div', { class: 'truncate text-[13px] font-semibold text-[var(--color-inspector-text)]' }, model.displayName || model.model),
                      (model.contextWindow > 0 || (context as any)?.rawMaxTokens)
                        ? h(
                            'div',
                            { class: 'mt-1 truncate text-[11px] text-[var(--color-inspector-muted)]' },
                            `${t('slash.inspector.status.contextWindow')}: ${formatNumber(model.contextWindow || (context as any)?.rawMaxTokens)}`
                          )
                        : null,
                    ]),
                    h('div', { class: 'text-right text-[12px] font-semibold uppercase tracking-[0.18em] text-[var(--color-inspector-heading)]' }, t('slash.inspector.usage.tokens')),
                  ]
                ),
                h(
                  'div',
                  { class: 'grid grid-cols-[160px_minmax(0,1fr)_120px] items-center gap-4 border-b border-[var(--color-inspector-border)] px-4 py-3 last:border-b-0' },
                  [
                    h('div', { class: 'text-[12px] uppercase tracking-[0.18em] text-[var(--color-inspector-heading)]' }, t('slash.inspector.usage.input')),
                    h('div', { class: 'h-1 overflow-hidden rounded-full bg-[var(--color-inspector-chip)]' }, [
                      h('div', { class: 'h-full rounded-full bg-[var(--color-inspector-accent)]', style: { width: '95%' } }),
                    ]),
                    h('div', { class: 'text-right text-[13px] text-[var(--color-inspector-text)]' }, formatNumber(model.inputTokens)),
                  ]
                ),
                h(
                  'div',
                  { class: 'grid grid-cols-[160px_minmax(0,1fr)_120px] items-center gap-4 px-4 py-3' },
                  [
                    h('div', { class: 'text-[12px] uppercase tracking-[0.18em] text-[var(--color-inspector-heading)]' }, t('slash.inspector.usage.output')),
                    h('div', { class: 'h-1 overflow-hidden rounded-full bg-[var(--color-inspector-chip)]' }, [
                      h('div', {
                        class: 'h-full rounded-full bg-[var(--color-inspector-accent-secondary)]',
                        style: { width: `${Math.max(4, Math.min(100, (model.outputTokens / Math.max(1, model.inputTokens)) * 100))}%` },
                      }),
                    ]),
                    h('div', { class: 'text-right text-[13px] text-[var(--color-inspector-text)]' }, formatNumber(model.outputTokens)),
                  ]
                ),
              ])
            )
          ),
    ])
  )

  return h('div', { class: 'space-y-7' }, children)
}

// ══════════════════════════════════════════════════════════════
// ContextTab build function
// ══════════════════════════════════════════════════════════════

type ContextCategory = SessionContextSnapshot['categories'][number]
type ContextMemoryFile = SessionContextSnapshot['memoryFiles'][number]

function buildContextOverview(context: SessionContextSnapshot, categories: ContextCategory[]): VNode {
  const usedPercent = Math.min(100, Math.max(0, context.percentage))
  const freeTokens = Math.max(0, context.rawMaxTokens - context.totalTokens)
  const freePercent = context.rawMaxTokens > 0 ? (freeTokens / context.rawMaxTokens) * 100 : 0

  const activeCategories = categories.filter((c) => !isCapacityCategory(c) && c.tokens > 0)

  return h(
    'div',
    { class: 'rounded-md border border-[var(--color-inspector-border)] bg-[var(--color-inspector-panel)] px-5 py-6' },
    [
      h('div', { class: 'mb-8 flex items-start justify-between gap-4' }, [
        renderInspectorSectionTitle(t('slash.inspector.context.windowUsage')),
        h(
          'span',
          { class: 'rounded-sm border border-[var(--color-inspector-border)] bg-[var(--color-inspector-chip)] px-2 py-1 font-mono text-xs text-[var(--color-inspector-muted-strong)]' },
          context.model
        ),
      ]),
      h('div', { class: 'font-mono text-[24px] font-semibold text-[var(--color-inspector-text)]' }, [
        formatNumber(context.totalTokens),
        h('span', { class: 'mx-1.5 text-[var(--color-inspector-text)]' }, '/'),
        h('span', undefined, formatNumber(context.rawMaxTokens)),
        h('span', { class: 'ml-3 align-middle text-sm font-normal text-[var(--color-inspector-accent-secondary)]' },
          `[${formatPercent(usedPercent)} ${t('slash.inspector.context.used')}]`
        ),
      ]),
      h('div', { class: 'mt-7' }, [
        activeCategories.length > 0
          ? h('div', { class: 'overflow-hidden rounded-full bg-[var(--color-inspector-chip)]' }, [
              h('div', { class: 'flex h-2.5 w-full' },
                activeCategories.map((category) =>
                  h('div', {
                    key: category.name,
                    title: `${category.name}: ${formatNumber(category.tokens)} tokens`,
                    style: {
                      width: `${Math.max(0.5, (category.tokens / context.rawMaxTokens) * 100)}%`,
                      backgroundColor: category.color,
                    },
                  })
                )
              )
            ])
          : null,
      ]),
      h('div', { class: 'mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4' }, [
        h(
          'div',
          { class: 'rounded-md border border-[var(--color-inspector-border)] bg-[var(--color-inspector-surface)] px-4 py-3' },
          [buildContextStatPill(t('slash.inspector.context.free'), formatNumber(freeTokens), formatPercent(freePercent))]
        ),
        h(
          'div',
          { class: 'rounded-md border border-[var(--color-inspector-border)] bg-[var(--color-inspector-surface)] px-4 py-3' },
          [buildContextStatPill(
            t('slash.inspector.context.messages'),
            formatNumber((context.messageBreakdown as any)?.assistantMessageTokens ?? 0),
            t('slash.inspector.context.assistant')
          )]
        ),
        h(
          'div',
          { class: 'rounded-md border border-[var(--color-inspector-border)] bg-[var(--color-inspector-surface)] px-4 py-3' },
          [buildContextStatPill(
            t('slash.inspector.context.toolResults'),
            formatNumber((context.messageBreakdown as any)?.toolResultTokens ?? 0)
          )]
        ),
        h(
          'div',
          { class: 'rounded-md border border-[var(--color-inspector-border)] bg-[var(--color-inspector-surface)] px-4 py-3' },
          [buildContextStatPill(t('slash.inspector.context.context'), formatPercent(usedPercent))]
        ),
      ]),
    ]
  )
}

function buildContextStatPill(label: string, value: string, detail?: string): VNode {
  return h('div', { class: 'min-w-0 font-mono' }, [
    h('div', { class: 'truncate text-[12px] font-semibold uppercase tracking-[0.22em] text-[var(--color-inspector-muted)]' }, label),
    h('div', { class: 'mt-2 truncate text-[16px] font-semibold text-[var(--color-inspector-text)]' }, value),
    detail ? h('div', { class: 'mt-1 truncate text-[13px] text-[var(--color-inspector-muted)]' }, detail) : null,
  ])
}

function buildCategoryBreakdown(categories: ContextCategory[], rawMaxTokens: number): VNode {
  const visibleCategories = categories.filter((c) => c.tokens > 0)
  if (visibleCategories.length === 0) {
    return renderEmptyState(t('slash.inspector.context.noCategoriesTitle'), t('slash.inspector.context.noCategoriesBody'))
  }

  return h(
    'div',
    { class: 'rounded-md border border-[var(--color-inspector-border)] bg-[var(--color-inspector-panel)] px-5 py-5 font-mono' },
    [
      renderInspectorSectionTitle(t('slash.inspector.context.categoryTitle')),
      h(
        'div',
        { class: 'grid gap-x-10 gap-y-5 sm:grid-cols-2' },
        visibleCategories.map((category) => {
          const percent = rawMaxTokens > 0 ? (category.tokens / rawMaxTokens) * 100 : 0
          const muted = isCapacityCategory(category)
          return h('div', { key: category.name, class: 'min-w-0' }, [
            h('div', { class: 'grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3' }, [
              h('div', { class: 'flex min-w-0 items-center gap-2' }, [
                h(
                  'span',
                  { class: `min-w-0 truncate text-[14px] font-semibold ${muted ? 'text-[var(--color-inspector-muted-strong)]' : 'text-[var(--color-inspector-text)]'}` },
                  category.name
                ),
              ]),
              h('div', { class: 'shrink-0 text-right leading-tight' }, [
                h('div', { class: 'text-sm text-[var(--color-inspector-text)]' }, formatNumber(category.tokens)),
                h('div', { class: 'mt-0.5 text-[12px] text-[var(--color-inspector-muted)]' }, formatPercent(percent)),
              ]),
            ]),
            h('div', { class: 'mt-2 h-1 overflow-hidden rounded-full bg-[var(--color-inspector-chip)]' }, [
              h('div', {
                class: muted ? 'h-full rounded-full opacity-65' : 'h-full rounded_full',
                style: {
                  width: `${Math.min(100, Math.max(0.5, percent))}%`,
                  backgroundColor: muted ? 'var(--color-inspector-capacity)' : 'var(--color-inspector-accent)',
                },
              }),
            ]),
          ])
        })
      ),
    ]
  )
}

function buildMemoryFilesBreakdown(files: ContextMemoryFile[]): VNode {
  if (files.length === 0) {
    return h(
      'div',
      { class: 'rounded-md border border-[var(--color-inspector-border)] bg-[var(--color-inspector-panel)] px-5 py-5' },
      [
        h('div', { class: 'flex items-center justify-between gap-3' }, [
          renderInspectorSectionTitle(t('slash.inspector.context.memoryFiles')),
          h(
            'button',
            {
              type: 'button',
              onClick: () => {
                setPendingSettingsTab('memory')
                useTabStore.getState().openTab(SETTINGS_TAB_ID, 'Settings', 'settings')
              },
              class: 'rounded-sm border border-[var(--color-inspector-border)] bg-[var(--color-inspector-chip)] px-2.5 py-1 text-xs font-semibold text-[var(--color-inspector-muted-strong)] hover:text-[var(--color-inspector-text)]',
            },
            t('slash.inspector.context.openMemory')
          ),
        ]),
        h('div', { class: 'mt-4 text-sm text-[var(--color-inspector-muted)]' }, t('slash.inspector.context.noMemoryFiles')),
      ]
    )
  }

  return h(
    'div',
    { class: 'rounded-md border border-[var(--color-inspector-border)] bg-[var(--color-inspector-panel)] px-5 py-5' },
    [
      h('div', { class: 'flex items-center justify-between gap-3' }, [
        renderInspectorSectionTitle(t('slash.inspector.context.memoryFiles')),
        h(
          'button',
          {
            type: 'button',
            onClick: () => {
              setPendingSettingsTab('memory')
              useTabStore.getState().openTab(SETTINGS_TAB_ID, 'Settings', 'settings')
            },
            class: 'rounded-sm border border-[var(--color-inspector-border)] bg-[var(--color-inspector-chip)] px-2.5 py-1 text-xs font-semibold text-[var(--color-inspector-muted-strong)] hover:text-[var(--color-inspector-text)]',
          },
          t('slash.inspector.context.openMemory')
        ),
      ]),
      h('div', { class: 'mt-4 grid gap-2' },
        files.map((file) =>
          h(
            'div',
            {
              key: `${file.type}:${file.path}`,
              class: 'grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-md border border-[var(--color-inspector-border)] bg-[var(--color-inspector-surface)] px-3 py-2',
            },
            [
              h('div', { class: 'min-w-0' }, [
                h(
                  'div',
                  { class: 'truncate font-mono text-sm font-semibold text-[var(--color-inspector-text)]', title: file.path },
                  memoryContextFileLabel(file.path)
                ),
                h(
                  'div',
                  { class: 'mt-0.5 truncate font-mono text-[11px] text-[var(--color-inspector-muted)]', title: file.path },
                  file.path
                ),
              ]),
              h('div', { class: 'shrink-0 text-right font-mono' }, [
                h('div', { class: 'text-xs font全面建设社会主义现代化 uppercase tracking-[0.12em] text-[var(--color-inspector-muted-strong)]' }, file.type),
                h('div', { class: 'mt-0.5 text-[11px] text-[var(--color-inspector-muted)]' }, `${formatNumber(file.tokens)} tokens`),
              ]),
            ]
          )
        )
      ),
    ]
  )
}

function buildContextTab(
  context?: SessionContextSnapshot | null,
  error?: string,
  loading?: boolean
): VNode {
  if (error && !context) return renderErrorState(error)
  if (loading && !context) return renderLoadingState(t('slash.inspector.context.loading'))
  if (!context) {
    return renderEmptyState(t('slash.inspector.context.emptyTitle'), t('slash.inspector.context.emptyBody'))
  }

  const categories = Array.isArray(context.categories) ? context.categories : []
  const files = Array.isArray(context.memoryFiles) ? context.memoryFiles : []

  return h('div', { class: 'space-y-6' }, [
    buildContextOverview(context, categories),
    buildMemoryFilesBreakdown(files),
    buildCategoryBreakdown(categories, context.rawMaxTokens),
  ])
}

// ══════════════════════════════════════════════════════════════
// SessionInspectorShell
// ══════════════════════════════════════════════════════════════

function renderSessionInspectorShell(
  selectedTab: SessionInspectorTab,
  tabs: Array<{ id: SessionInspectorTab; label: string }>,
  onSelectTab: (tab: SessionInspectorTab) => void,
  onClose: () => void,
  body: VNode
): VNode {
  return h(
    'div',
    {
      class:
        'absolute bottom-full left-0 right-0 z-50 mb-4 overflow-hidden rounded-[10px] border border-[var(--color-inspector-border)] bg-[var(--color-inspector-surface)] text-[var(--color-inspector-text)] shadow-[var(--shadow-inspector)]',
    },
    [
      h(
        'div',
        { class: 'grid min-h>[64px] grid-cols-[1fr_auto_1fr] items-center border-b border-[var(--color-inspector-border)] bg-[var(--color-inspector-surface)] px-6' },
        [
          h('div', { class: 'font-mono text-[16px] font-semibold uppercase text-[var(--color-inspector-accent)]' }, t('slash.inspector.title')),
          h('div', { class: 'flex items-center gap-8' },
            tabs.map((tab) =>
              h(
                'button',
                {
                  key: tab.id,
                  type: 'button',
                  onClick: () => onSelectTab(tab.id),
                  class: `relative h-10 px-0 font-sans text-sm transition-colors ${
                    selectedTab === tab.id
                      ? 'text-[var(--color-inspector-accent)]'
                      : 'text-[var(--color-inspector-muted-strong)] hover:text-[var(--color-inspector-accent)]'
                  }`,
                },
                [
                  tab.label,
                  selectedTab === tab.id
                    ? h('span', { class: 'absolute bottom-1 left-0 right-0 h-[2px] bg-[var(--color-inspector-accent)]' })
                    : null,
                ]
              )
            )
          ),
          h('div', { class: 'flex justify-end' }, [
            h(
              'button',
              {
                type: 'button',
                onClick: onClose,
                'aria-label': t('slash.inspector.close'),
                class: 'flex h-10 w-10 items-center justify-center text-[var(--color-inspector-accent)] transition-colors hover:text-[var(--color-inspector-accent-hover)]',
              },
              h('span', { class: 'material-symbols-outlined text-[24px]' }, 'close')
            ),
          ]),
        ]
      ),
      h('div', { class: 'max-h>[min(540px,58vh)] overflow-y-auto bg-[var(--color-inspector-surface)] px-6 py-6' }, body),
    ]
  )
}

// ══════════════════════════════════════════════════════════════
// Reactive state for SessionInspectorPanel
// ══════════════════════════════════════════════════════════════

const inspectorSelectedTab = ref<SessionInspectorTab>(sessionInspectorInitialTab(props.command))
const inspectorData = ref<SessionInspectionResponse | null>(null)
const inspectorError = ref<string | null>(null)
const inspectorContextLoading = ref(false)
const inspectorContextError = ref<string | null>(null)
const inspectorRequestSessionRef = ref<string | null>(null)

// Watch command changes
watch(
  () => props.command,
  (newCommand) => {
    if (newCommand !== 'status' && newCommand !== 'cost' && newCommand !== 'context') return
    inspectorSelectedTab.value = sessionInspectorInitialTab(newCommand)
  }
)

// Fetch inspection on sessionId change
watch(
  () => props.sessionId,
  async (newSessionId) => {
    if (!newSessionId) {
      inspectorError.value = t('slash.inspector.error.noActiveSession')
      return
    }
    let cancelled = false
    inspectorData.value = null
    inspectorError.value = null
    inspectorContextLoading.value = false
    inspectorContextError.value = null
    inspectorRequestSessionRef.value = null

    try {
      const response = await sessionsApi.getInspection(newSessionId, { includeContext: false })
      if (!cancelled) inspectorData.value = assertSessionInspectionResponse(response)
    } catch (err) {
      if (!cancelled) inspectorError.value = err instanceof Error ? err.message : String(err)
    }

    return () => { cancelled = true }
  }
)

// Fetch context when switching to context tab
watch(
  [() => inspectorSelectedTab.value, () => inspectorData.value, () => props.sessionId],
  async ([selectedTab, data, sessionId]) => {
    if (!sessionId || selectedTab !== 'context' || data === null) return
    if ((data as any).context) return
    if (inspectorRequestSessionRef.value === sessionId) return

    inspectorRequestSessionRef.value = sessionId
    let cancelled = false
    inspectorContextLoading.value = true
    inspectorContextError.value = null

    try {
      const response = await sessionsApi.getInspection(sessionId, { includeContext: true, contextOnly: true, timeout: 45_000 })
      if (cancelled) return
      const inspected = assertSessionInspectionResponse(response)
      const prev = inspectorData.value
      inspectorData.value = prev
        ? ({
            ...prev,
            context: inspected.context,
            errors: {
              ...(prev.errors ?? {}),
              ...(inspected.errors ?? {}),
            },
          } as SessionInspectionResponse)
        : inspected
      inspectorContextError.value = (inspected.errors as any)?.context ?? null
    } catch (err) {
      if (!cancelled) inspectorContextError.value = err instanceof Error ? err.message : String(err)
    } finally {
      if (!cancelled) inspectorContextLoading.value = false
    }

    return () => { cancelled = true }
  }
)

const inspectorTabs = [
  { id: 'status' as SessionInspectorTab, label: t('slash.inspector.tab.status') },
  { id: 'usage' as SessionInspectorTab, label: t('slash.inspector.tab.usage') },
  { id: 'context' as SessionInspectorTab, label: t('slash.inspector.tab.context') },
]

function buildInspectorContent(): VNode {
  if (inspectorError.value) {
    return renderErrorState(inspectorError.value)
  }
  if (inspectorData.value === null) {
    return renderLoadingState(t('slash.inspector.loading'))
  }
  const data = inspectorData.value
  if (inspectorSelectedTab.value === 'usage') {
    return buildUsageTab(data.usage, data.context ?? (data as any).contextEstimate, (data.errors as any)?.usage)
  }
  if (inspectorSelectedTab.value === 'context') {
    return buildContextTab(
      data.context ?? (data as any).contextEstimate,
      inspectorContextError.value ?? (data.errors as any)?.context,
      inspectorContextLoading.value && !(data as any).contextEstimate
    )
  }
  return buildStatusTab(data, props.commands)
}

// ══════════════════════════════════════════════════════════════
// McpPanel
// ══════════════════════════════════════════════════════════════

const mcpServers = ref<McpServerRecord[] | null>(null)
const mcpError = ref<string | null>(null)

onMounted(() => {
  let cancelled = false
  if (props.command !== 'mcp') return

  mcpApi.list(props.cwd)
    .then(async (response) => {
      if (cancelled) return
      const visibleServers = response.servers.filter(
        (server) => server.scope === 'user' || server.scope === 'local' || server.scope === 'project'
      )
      mcpServers.value = visibleServers

      const statusResults = await Promise.allSettled(
        visibleServers.map((server) => mcpApi.status(server.name, props.cwd))
      )
      if (cancelled) return

      const liveServers = new Map<string, McpServerRecord>()
      for (const result of statusResults) {
        if (result.status === 'fulfilled') {
          liveServers.set((result.value as any).server.name, (result.value as any).server)
        }
      }
      if (liveServers.size > 0) {
        mcpServers.value = mcpServers.value?.map((server) => liveServers.get(server.name) ?? server) ?? mcpServers.value
      }
    })
    .catch((err) => {
      if (cancelled) return
      mcpError.value = err instanceof Error ? err.message : String(err)
    })

  return () => { cancelled = true }
})

const mcpGrouped = computed(() => {
  const groups = new Map<string, McpServerRecord[]>()
  for (const server of mcpServers.value ?? []) {
    const key = server.scope
    const existing = groups.get(key) ?? []
    existing.push(server)
    groups.set(key, existing)
  }
  return groups
})

function buildMcpPanel(): VNode {
  const onClose = props.onClose
  const title = t('slash.mcp.title')
  const subtitle = props.cwd ? t('slash.mcp.subtitleWithProject', { path: props.cwd }) : t('slash.mcp.subtitle')

  if (mcpError.value) {
    return renderPanelShell(title, subtitle, onClose, renderErrorState(mcpError.value))
  }
  if (mcpServers.value === null) {
    return renderPanelShell(title, subtitle, onClose, renderLoadingState(t('common.loading')))
  }
  if (mcpServers.value.length === 0) {
    return renderPanelShell(title, subtitle, onClose, renderEmptyState(t('slash.mcp.emptyTitle'), t('slash.mcp.emptyBody')))
  }

  const scopeList = ['user', 'local', 'project'].filter((scope) => mcpGrouped.value.has(scope))

  return renderPanelShell(title, subtitle, onClose,
    h('div', { class: 'space-y-5' },
      scopeList.map((scope) =>
        h('section', { key: scope }, [
          h('div', { class: 'mb-2 flex items-center justify-between' }, [
            h('div', { class: 'text-sm font-semibold text-[var(--color-text-primary)]' }, scopeLabel(scope)),
            h('div', { class: 'text-xs text-[var(--color-text-tertiary)]' }, mcpGrouped.value.get(scope)?.length ?? 0),
          ]),
          h('div', { class: 'overflow-hidden rounded-2xl border border>[var(--color-border)] bg-[var(--color-surface)]' },
            mcpGrouped.value.get(scope)?.map((server) =>
              h(
                'button',
                {
                  type: 'button',
                  key: `${server.scope}:${server.projectPath ?? 'global'}:${server.name}`,
                  onClick: () => {
                    selectServer(server)
                    setPendingSettingsTab('mcp')
                    useTabStore.getState().openTab(SETTINGS_TAB_ID, 'Settings', 'settings')
                    onClose()
                  },
                  class: 'block w-full border-t border>[var(--color-border)] px-4 py-4 text-left first:border-t-0 hover:bg-[var(--color-surface-hover)]',
                },
                [
                  h('div', { class: 'flex items-center gap-3' }, [
                    h('div', { class: 'text-sm font-semibold text-[var(--color-text-primary)]' }, server.name),
                    h(
                      'span',
                      { class: `inline-flex items-center rounded-full border px-2 py-1 text-[11px] font-semibold ${toneForStatus(server.status)}` },
                      server.statusLabel
                    ),
                  ]),
                  h('div', { class: 'mt-2 flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-tertiary)]' }, [
                    h('span', { class: 'rounded-full bg-[var(--color-surface-hover)] px-2 py-1' }, server.transport),
                    server.projectPath
                      ? h(
                          'span',
                          { class: 'rounded-full bg-[var(--color-surface-hover)] px-2 py-1', title: server.projectPath },
                          projectBadge(server.projectPath)
                        )
                      : null,
                    h('span', { class: 'truncate' }, server.summary),
                  ]),
                ]
              )
            ) ?? []
          ),
        ])
      )
    )
  )
}

// ══════════════════════════════════════════════════════════════
// SkillsPanel
// ══════════════════════════════════════════════════════════════

const skillsList = ref<SkillMeta[] | null>(null)
const skillsError = ref<string | null>(null)

onMounted(() => {
  let cancelled = false
  if (props.command !== 'skills') return

  skillsApi.list(props.cwd)
    .then((response) => {
      if (cancelled) return
      skillsList.value = response.skills.filter((skill) => skill.userInvocable)
    })
    .catch((err) => {
      if (cancelled) return
      skillsError.value = err instanceof Error ? err.message : String(err)
    })

  return () => { cancelled = true }
})

function buildSkillsPanel(): VNode {
  const onClose = props.onClose
  const title = t('slash.skills.title')
  const subtitle = props.cwd ? t('slash.skills.subtitleWithProject', { path: props.cwd }) : t('slash.skills.subtitle')

  if (skillsError.value) {
    return renderPanelShell(title, subtitle, onClose, renderErrorState(skillsError.value))
  }
  if (skillsList.value === null) {
    return renderPanelShell(title, subtitle, onClose, renderLoadingState(t('common.loading')))
  }
  if (skillsList.value.length === 0) {
    return renderPanelShell(title, subtitle, onClose, renderEmptyState(t('slash.skills.emptyTitle'), t('slash.skills.emptyBody')))
  }

  return renderPanelShell(title, subtitle, onClose,
    h(
      'div',
      { class: 'overflow-hidden rounded-2xl border border>[var(--color-border)] bg-[var(--color-surface)]' },
      skillsList.value!.map((skill) =>
        h(
          'button',
          {
            type: 'button',
            key: `${skill.source}:${skill.name}`,
            onClick: async () => {
              await fetchSkillDetail(skill.source, skill.name, props.cwd, 'skills')
              setPendingSettingsTab('skills')
              useTabStore.getState().openTab(SETTINGS_TAB_ID, 'Settings', 'settings')
              onClose()
            },
            class: 'block w-full border-t border>[var(--color-border)] px-4 py-4 text-left first:border-t-0 hover:bg-[var(--color-surface-hover)]',
          },
          [
            h('div', { class: 'flex items-center gap-3' }, [
              h('div', { class: 'text-sm font-semibold text-[var(--color-text-primary)]' }, `/${skill.name}`),
              h('span', { class: 'rounded-full bg-[var(--color-surface-hover)] px-2 py-1 text-[11px] text-[var(--color-text-secondary)]' }, skill.source),
            ]),
            h('div', { class: 'mt-2 text-xs leading-6 text-[var(--color-text-tertiary)]' }, skill.description),
          ]
        )
      )
    )
  )
}

// ══════════════════════════════════════════════════════════════
// HelpPanel
// ══════════════════════════════════════════════════════════════

function buildHelpPanel(): VNode {
  const commandMap = new Map<string, SlashCommandOption>()
  for (const command of props.commands ?? []) {
    commandMap.set(command.name, command)
  }

  const groupedNames = new Set(COMMAND_GROUPS.flatMap((group) => group.names))
  const otherCommands = (props.commands ?? [])
    .filter((command) => !groupedNames.has(command.name))
    .slice(0, 12)
  const hiddenOtherCommandCount = Math.max(
    0,
    (props.commands ?? []).filter((command) => !groupedNames.has(command.name)).length - otherCommands.length
  )

  const renderCommand = (command: SlashCommandOption) =>
    h('div', { key: command.name, class: 'flex min-w-0 items-start gap-3 border-t border>[var(--color-border)] px-4 py-3 first:border-t-0' }, [
      h('div', { class: 'flex min-w-[120px] max-w-[45%] shrink-0 flex-wrap items-baseline gap-x-1.5 font-mono' }, [
        h('span', { class: 'text-sm font-semibold text-[var(--color-text-primary)]' }, `/${command.name}`),
        command.argumentHint
          ? h('span', { class: 'text-[11px] leading-5 text-[var(--color-text-tertiary)]' }, command.argumentHint)
          : null,
      ]),
      h('div', { class: 'min-w-0 flex-1 text-xs leading-5 text-[var(--color-text-tertiary)]' }, command.description),
    ])

  const sections: VNode[] = []
  for (const group of COMMAND_GROUPS) {
    const entries = group.names
      .map((name) => commandMap.get(name))
      .filter((command): command is SlashCommandOption => Boolean(command))
    if (entries.length === 0) continue
    sections.push(
      h('section', { key: group.titleKey }, [
        h('div', { class: 'mb-2 text-sm font-semibold text-[var(--color-text-primary)]' }, t(group.titleKey)),
        h('div', { class: 'overflow-hidden rounded-2xl border border>[var(--color-border)] bg-[var(--color-surface)]' }, entries.map(renderCommand)),
      ])
    )
  }

  if (otherCommands.length > 0) {
    sections.push(
      h('section', { key: 'other' }, [
        h('div', { class: 'mb-2 text-sm font-semibold text-[var(--color-text-primary)]' }, t('slash.help.group.more')),
        h('div', { class: 'overflow-hidden rounded-2xl border border>[var(--color-border)] bg-[var(--color-surface)]' }, otherCommands.map(renderCommand)),
        hiddenOtherCommandCount > 0
          ? h('p', { class: 'mt-2 text-xs leading-5 text-[var(--color-text-tertiary)]' }, t('slash.help.moreAvailable', { count: hiddenOtherCommandCount }))
          : null,
      ])
    )
  }

  return renderPanelShell(
    t('slash.help.title'),
    t('slash.help.subtitle'),
    props.onClose,
    h('div', { class: 'space-y-4' }, sections)
  )
}

// ══════════════════════════════════════════════════════════════
// Main computed — determines which panel to render
// ══════════════════════════════════════════════════════════════

const currentPanel = computed(() => {
  if (props.command === 'mcp') return buildMcpPanel()
  if (props.command === 'skills') return buildSkillsPanel()
  if (props.command === 'status' || props.command === 'cost' || props.command === 'context') {
    return renderSessionInspectorShell(
      inspectorSelectedTab.value,
      inspectorTabs,
      (tab) => { inspectorSelectedTab.value = tab },
      props.onClose,
      buildInspectorContent()
    )
  }
  return buildHelpPanel()
})
</script>

<template>
  <div>
    <component :is="currentPanel" />
  </div>
</template>