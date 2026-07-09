<script setup lang="ts">
// v5.0 — ToolCallGroup (full Vue 3 SFC translation from React components/chat/ToolCallGroup.tsx, 1088 lines)
// - useState → ref() ; useEffect → watch ; useMemo → computed
// - lucide-react icons → <span class="material-symbols-outlined">icon_name</span>
// - createPortal → <teleport to="body">
// - keep ALL Tailwind classes and --color-* CSS variables VERBATIM
// - ALL sub-components rendered inline as template sections with their own ref() state
// - Per-instance state (AgentCallCard expanded/previewOpen) tracked via Record<string, boolean> maps

import {
  ref,
  watch,
  computed,
  type Ref,
} from 'vue'
import { useTranslation } from '../../i18n'
import type { TranslationKey } from '../../i18n'
import { SETTINGS_TAB_ID, useTabStore } from '../../stores/tabStore'
import { useUIStore } from '../../stores/uiStore'
import type { UIMessage, AgentTaskNotification } from '../../types/chat'
import { AGENT_LIFECYCLE_TYPES } from '../../../types/team.ts'
import ToolCallBlock from './ToolCallBlock.vue'
import MarkdownRenderer from '../shared/MarkdownRenderer.vue'
import Modal from '../shared/Modal.vue'

// ─── Types ───────────────────────────────────────────────────────

type ToolCall = Extract<UIMessage, { type: 'tool_use' }>
type ToolResult = Extract<UIMessage, { type: 'tool_result' }>
type MemoryToolAction = 'saved' | 'referenced'

type MemoryToolFile = {
  path: string
  label: string
  action: MemoryToolAction
  lineHint?: string
  preview?: string
}

type MemoryToolActivity = {
  action: MemoryToolAction
  files: MemoryToolFile[]
}

type AgentStatus = 'starting' | 'running' | 'done' | 'failed' | 'stopped'

export interface ToolCallGroupProps {
  toolCalls: ToolCall[]
  resultMap: Map<string, ToolResult>
  childToolCallsByParent: Map<string, ToolCall[]>
  agentTaskNotifications: Record<string, AgentTaskNotification>
  isStreaming?: boolean
}

const props = withDefaults(defineProps<ToolCallGroupProps>(), {
  isStreaming: false,
  resultMap: () => new Map(),  // fallback empty map if undefined
  childToolCallsByParent: () => new Map(),
  agentTaskNotifications: () => ({}),
})

const t = useTranslation()

// ─── Pure helpers (single source of truth) ──────────────────────

const TOOL_VERBS: Record<
  string,
  (count: number, tFn: (key: TranslationKey, params?: Record<string, string | number>) => string) => string
> = {
  Read: (n, tFn) => (n === 1 ? tFn('toolGroup.readOne') : tFn('toolGroup.readMany', { count: n })),
  Write: (n, tFn) => (n === 1 ? tFn('toolGroup.createdOne') : tFn('toolGroup.createdMany', { count: n })),
  Edit: (n, tFn) => (n === 1 ? tFn('toolGroup.editedOne') : tFn('toolGroup.editedMany', { count: n })),
  Bash: (n, tFn) => (n === 1 ? tFn('toolGroup.ranOne') : tFn('toolGroup.ranMany', { count: n })),
  Glob: (_n, tFn) => tFn('toolGroup.foundFiles'),
  Grep: (n, tFn) => (n === 1 ? tFn('toolGroup.searchedOne') : tFn('toolGroup.searchedMany', { count: n })),
  Agent: (n, tFn) => (n === 1 ? tFn('toolGroup.agentOne') : tFn('toolGroup.agentMany', { count: n })),
  WebSearch: (_n, tFn) => tFn('toolGroup.searchedWeb'),
  WebFetch: (n, tFn) => (n === 1 ? tFn('toolGroup.fetchedOne') : tFn('toolGroup.fetchedMany', { count: n })),
}

function generateSummary(
  toolCalls: ToolCall[],
  tFn: (key: TranslationKey, params?: Record<string, string | number>) => string,
): string {
  const counts = new Map<string, number>()
  for (const tc of toolCalls) {
    counts.set(tc.toolName, (counts.get(tc.toolName) ?? 0) + 1)
  }
  const parts: string[] = []
  for (const [name, count] of counts) {
    const verbFn = TOOL_VERBS[name]
    parts.push(verbFn ? verbFn(count, tFn) : `${name} (${count})`)
  }
  return parts.join(', ')
}

function toolCallHasError(
  toolCall: ToolCall,
  resultMap: Map<string, ToolResult>,
  childToolCallsByParent: Map<string, ToolCall[]>,
): boolean {
  const result = resultMap.get(toolCall.toolUseId)
  if (result?.isError) return true
  return (childToolCallsByParent.get(toolCall.toolUseId) ?? []).some((childToolCall) =>
    toolCallHasError(childToolCall, resultMap, childToolCallsByParent),
  )
}

function groupHasErrors(
  toolCalls: ToolCall[],
  resultMap: Map<string, ToolResult>,
  childToolCallsByParent: Map<string, ToolCall[]>,
): boolean {
  return toolCalls.some((tc) => {
    return toolCallHasError(tc, resultMap, childToolCallsByParent)
  })
}

function isToolCallResolved(
  toolCall: ToolCall,
  resultMap: Map<string, ToolResult>,
  childToolCallsByParent: Map<string, ToolCall[]>,
): boolean {
  if (toolCall.status === 'stopped') return true
  if (!resultMap.has(toolCall.toolUseId)) return false

  return (childToolCallsByParent.get(toolCall.toolUseId) ?? []).every((childToolCall) =>
    isToolCallResolved(childToolCall, resultMap, childToolCallsByParent),
  )
}

function hasUnresolvedToolCalls(
  toolCalls: ToolCall[],
  resultMap: Map<string, ToolResult>,
  childToolCallsByParent: Map<string, ToolCall[]>,
): boolean {
  return toolCalls.some((toolCall) =>
    !isToolCallResolved(toolCall, resultMap, childToolCallsByParent),
  )
}

// ─── Agent status helpers ───────────────────────────────────────

function getAgentStatus({
  hasResult,
  isError,
  isLaunchResult,
  isStreaming,
  childCount,
  taskStatus,
}: {
  hasResult: boolean
  isError: boolean
  isLaunchResult: boolean
  isStreaming: boolean
  childCount: number
  taskStatus?: AgentTaskNotification['status']
}): AgentStatus {
  if (taskStatus === 'failed') return 'failed'
  if (taskStatus === 'stopped') return 'stopped'
  if (taskStatus === 'completed') return 'done'
  if (hasResult && isError && !isLaunchResult) return 'failed'
  if (hasResult && !isLaunchResult) return 'done'
  if (isStreaming || childCount > 0 || isLaunchResult) return 'running'
  return 'starting'
}

function getAgentStatusLabel(
  status: AgentStatus,
  tFn: (key: TranslationKey, params?: Record<string, string | number>) => string,
): string {
  switch (status) {
    case 'failed':
      return tFn('agentStatus.failed')
    case 'stopped':
      return tFn('agentStatus.stopped')
    case 'done':
      return tFn('agentStatus.done')
    case 'running':
      return tFn('agentStatus.running')
    case 'starting':
    default:
      return tFn('agentStatus.starting')
  }
}

function getAgentStatusClassName(status: AgentStatus): string {
  switch (status) {
    case 'failed':
      return 'bg-[var(--color-error)]/10 text-[var(--color-error)]'
    case 'stopped':
      return 'bg-[var(--color-surface-container-high)] text-[var(--color-text-secondary)]'
    case 'done':
      return 'bg-[var(--color-success)]/10 text-[var(--color-success)]'
    case 'running':
      return 'bg-[var(--color-warning)]/10 text-[var(--color-warning)]'
    case 'starting':
    default:
      return 'bg-[var(--color-surface-container-high)] text-[var(--color-text-secondary)]'
  }
}

// ─── Text extraction ────────────────────────────────────────────

function extractTextContent(content: unknown): string {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    return content
      .map((chunk) => {
        if (typeof chunk === 'string') return chunk
        if (chunk && typeof chunk === 'object' && 'text' in chunk) {
          return typeof chunk.text === 'string' ? chunk.text : ''
        }
        return ''
      })
      .filter(Boolean)
      .join('\n')
  }
  if (content && typeof content === 'object') {
    const rec = content as Record<string, unknown>
    if (
      'status' in rec &&
      rec.status === 'completed' &&
      Array.isArray(rec.content)
    ) {
      return extractTextContent(rec.content)
    }
    return JSON.stringify(content)
  }
  return ''
}

function formatRecentToolUseSummary(
  toolCall: ToolCall,
  resultMap: Map<string, ToolResult>,
): string {
  const input =
    toolCall.input && typeof toolCall.input === 'object'
      ? (toolCall.input as Record<string, unknown>)
      : {}
  const result = resultMap.get(toolCall.toolUseId)
  const suffix = result?.isError ? ' • failed' : result ? ' • done' : ' • running'

  switch (toolCall.toolName) {
    case 'Bash':
      return `Bash · ${typeof input.command === 'string' ? input.command : ''}${suffix}`
    case 'Read':
      return `Read · ${typeof input.file_path === 'string' ? input.file_path.split('/').pop() : 'file'}${suffix}`
    case 'Glob':
      return `Glob · ${typeof input.pattern === 'string' ? input.pattern : ''}${suffix}`
    case 'Grep':
      return `Grep · ${typeof input.pattern === 'string' ? input.pattern : ''}${suffix}`
    case 'Agent':
      return `Agent · ${typeof input.description === 'string' ? input.description : ''}${suffix}`
    default:
      return `${toolCall.toolName}${suffix}`
  }
}

function getAgentErrorSummary(content: unknown): string {
  const text = extractTextContent(content).replace(/\s+/g, ' ').trim()
  if (!text) return ''
  if (text.includes(`Agent type 'Explore' not found`)) {
    return 'Explore agent unavailable in this session'
  }
  return text.length > 120 ? `${text.slice(0, 120)}...` : text
}

function getAgentOutputSummary(content: string): string {
  const text = content.replace(/\s+\n/g, '\n').trim()
  if (!text) return ''
  return text.length > 220 ? `${text.slice(0, 220)}...` : text
}

function isAgentLaunchResult(content: unknown): boolean {
  const text = extractTextContent(content).trim()
  if (!text) return false

  return (
    text.startsWith('Async agent launched successfully.') ||
    text.startsWith('Remote agent launched in CCR.') ||
    (text.startsWith('Spawned successfully.') &&
      text.includes('The agent is now running and will receive instructions via mailbox.')) ||
    text.includes('The agent is working in the background. You will be notified automatically when it completes.') ||
    text.includes('The agent is running remotely. You will be notified automatically when it completes.')
  )
}

function isAgentLifecycleResult(content: unknown): boolean {
  const text = extractTextContent(content).trim()
  if (!text) return false
  if (text.startsWith('{') && text.endsWith('}')) {
    try {
      const parsed = JSON.parse(text) as Record<string, unknown>
      if (typeof parsed.type === 'string' && AGENT_LIFECYCLE_TYPES.has(parsed.type)) {
        return true
      }
    } catch {
      // Not valid JSON, not a lifecycle message
    }
  }
  return false
}

function extractAgentDisplayText(content: unknown): string {
  return stripAgentResultMetadata(
    formatAgentStructuredResult(content) || extractTextContent(content),
  )
}

function formatAgentStructuredResult(content: unknown): string {
  const structured = parseStructuredAgentContent(content)
  if (!structured || Array.isArray(structured)) return ''

  const results = (structured as Record<string, unknown>).results
  if (!Array.isArray(results) || results.length === 0) return ''

  const items = results
    .map((result, index) => formatAgentStructuredResultItem(result, index))
    .filter(Boolean)

  return items.join('\n')
}

function parseStructuredAgentContent(
  content: unknown,
): Record<string, unknown> | unknown[] | null {
  if (typeof content === 'string') {
    return parseStructuredAgentText(content)
  }

  if (Array.isArray(content)) {
    return parseStructuredAgentText(extractTextContent(content))
  }

  if (content && typeof content === 'object') {
    if ('results' in content) return content as Record<string, unknown>

    const extracted = extractTextContent(content)
    return extracted ? parseStructuredAgentText(extracted) : null
  }

  return null
}

function parseStructuredAgentText(
  text: string,
): Record<string, unknown> | unknown[] | null {
  const trimmed = text.trim()
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return null
  try {
    const parsed = JSON.parse(trimmed) as unknown
    return typeof parsed === 'object' && parsed !== null
      ? (parsed as Record<string, unknown> | unknown[])
      : null
  } catch {
    return null
  }
}

function formatAgentStructuredResultItem(result: unknown, index: number): string {
  if (!result || typeof result !== 'object' || Array.isArray(result)) {
    const text = extractTextContent(result).trim()
    return text ? `${index + 1}. ${text}` : ''
  }

  const record = result as Record<string, unknown>
  const location = formatAgentResultLocation(record)
  const context = getStringField(record, 'context')
  const snippet = getStringField(record, 'snippet')
  const message =
    getStringField(record, 'message') ||
   getStringField(record, 'text') ||
    getStringField(record, 'summary')
  const nestedItems = Array.isArray(record.items) ? record.items : []

  if (nestedItems.length > 0) {
    const label =
      getStringField(record, 'risk') ||
      getStringField(record, 'title') ||
      message ||
      'Grouped results'
    const lines = [
      `${index + 1}. ${formatAgentGroupLabel(label)}`,
    ]
    if (context) lines.push(`   - ${context}`)
    if (snippet) lines.push(`   - ${snippet}`)

    nestedItems
      .map(formatAgentStructuredNestedItem)
      .filter(Boolean)
      .forEach((item) => {
        lines.push(
          item
            .split('\n')
            .map((line, lineIndex) =>
              `${lineIndex === 0 ? '   - ' : '     '}${line}`,
            )
            .join('\n'),
        )
      })

    return lines.join('\n')
  }

  const lines = [
    `${index + 1}. ${location ? formatInlineCode(location) : 'Result'}`,
  ]

  if (message) lines.push(`   - ${message}`)
  if (context) lines.push(`   - ${context}`)
  if (snippet) lines.push(`   - ${snippet}`)

  return lines.join('\n')
}

function formatAgentStructuredNestedItem(item: unknown): string {
  if (!item || typeof item !== 'object' || Array.isArray(item)) {
    return extractTextContent(item).trim()
  }

  const record = item as Record<string, unknown>
  const location = formatAgentResultLocation(record)
  const context = getStringField(record, 'context')
  const snippet = getStringField(record, 'snippet')
  const message =
    getStringField(record, 'message') ||
    getStringField(record, 'text') ||
    getStringField(record, 'summary')
  const headingParts = [location ? formatInlineCode(location) : '', message].filter(Boolean)
  const lines = [headingParts.join(' - ') || 'Result']

  if (context) lines.push(context)
  if (snippet) lines.push(snippet)

  return lines.join('\n')
}

function formatAgentGroupLabel(label: string): string {
  const normalized = label.trim()
  if (!normalized) return 'Grouped results'
  return `${normalized.charAt(0).toUpperCase()}${normalized.slice(1)}`
}

function formatAgentResultLocation(record: Record<string, unknown>): string {
  const file = getStringField(record, 'file')
  if (!file) return ''
  const line = typeof record.line === 'number' ? record.line : null
  return line !== null ? `${file}:${line}` : file
}

function getStringField(record: Record<string, unknown>, key: string): string {
  const value = record[key]
  return typeof value === 'string' ? value.trim() : ''
}

function formatInlineCode(value: string): string {
  return `\`${value.replace(/`/g, '\\`')}\``
}

function stripAgentResultMetadata(text: string): string {
  return text
    .replace(/^\s*agentId:.*(?:\r?\n)?/gm, '')
    .replace(/<usage>[\s\S]*?<\/usage>/g, '')
    .replace(/^\s*(?:total_tokens|tool_uses|duration_ms):\s*\d+\s*$/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

// ─── Memory tool helpers ────────────────────────────────────────

function isMemoryWriteTool(toolName: string): boolean {
  return toolName === 'Write' || toolName === 'Edit' || toolName === 'MultiEdit'
}

function getToolFilePath(input: unknown): string | null {
  if (!input || typeof input !== 'object') return null
  const record = input as Record<string, unknown>
  const filePath = record.file_path ?? record.path
  return typeof filePath === 'string' ? filePath : null
}

function isMemoryMarkdownPath(path: string): boolean {
  const normalized = path.replace(/\\/g, '/')
  return normalized.endsWith('.md') && normalized.includes('/memory/')
}

function memoryFileLabel(path: string): string {
  const normalized = path.replace(/\\/g, '/')
  return normalized.split('/').pop() || normalized
}

function extractLineHint(text: string): string | undefined {
  const match = text.match(/(\d+)\s+lines?\b/i) ?? text.match(/(\d+)\s+行/)
  return match?.[1] ? `${match[1]} lines` : undefined
}

function extractMemoryPreview(content: unknown): { text?: string; lineHint?: string } {
  const raw = extractTextContent(content)
  if (!raw) return {}
  const lineHint = extractLineHint(raw)
  const lines = raw
    .replace(/<system-reminder>[\s\S]*?<\/system-reminder>/g, '')
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*\d+\s*/, '').trim())
    .filter(Boolean)

  let inFrontmatter = false
  for (const line of lines) {
    if (line === '---') {
      inFrontmatter = !inFrontmatter
      continue
    }
    if (inFrontmatter) continue
    const normalized = line.replace(/^#+\s*/, '').replace(/^[-*]\s*/, '').trim()
    if (!normalized || normalized === '---') continue
    if (/^(file|lines?|total)\b/i.test(normalized)) continue
    return {
      text: normalized.length > 140 ? `${normalized.slice(0, 140)}...` : normalized,
      lineHint,
    }
  }
  return { lineHint }
}

function isMemoryToolCall(toolCall: ToolCall): boolean {
  if (toolCall.isPending) return false
  const path = getToolFilePath(toolCall.input)
  if (!path || !isMemoryMarkdownPath(path)) return false
  return toolCall.toolName === 'Read' || isMemoryWriteTool(toolCall.toolName)
}

function getMemoryToolActivity(
  toolCalls: ToolCall[],
  resultMap: Map<string, ToolResult>,
): MemoryToolActivity | null {
  const filesByPath = new Map<string, MemoryToolFile>()
  let sawSave = false

  for (const toolCall of toolCalls) {
    if (toolCall.isPending) continue
    const path = getToolFilePath(toolCall.input)
    if (!path || !isMemoryMarkdownPath(path)) continue

    const isSave = isMemoryWriteTool(toolCall.toolName)
    const isReference = toolCall.toolName === 'Read'
    if (!isSave && !isReference) continue
    sawSave ||= isSave

    const result = resultMap.get(toolCall.toolUseId)
    const preview = extractMemoryPreview(result?.content)
    const current = filesByPath.get(path)
    filesByPath.set(path, {
      path,
      label: memoryFileLabel(path),
      action: isSave ? 'saved' : (current?.action ?? 'referenced'),
      lineHint: preview.lineHint || current?.lineHint,
      preview: preview.text || current?.preview,
    })
  }

  if (filesByPath.size === 0) return null
  return {
    action: sawSave ? 'saved' : 'referenced',
    files: [...filesByPath.values()],
  }
}

// ─── Open-memory-settings helper ────────────────────────────────
function openMemorySettings(path?: string) {
  const ui = useUIStore()
  if (path) ui.setPendingMemoryPath(path)
  ui.setPendingSettingsTab('memory')
  useTabStore().openTab(SETTINGS_TAB_ID, 'Settings', 'settings')
}

// ─── Top-level computed ────────────────────────────────────────

const memoryActivity = computed(() =>
  getMemoryToolActivity(props.toolCalls, props.resultMap),
)

const memoryToolCalls = computed(() => props.toolCalls.filter(isMemoryToolCall))
const regularToolCalls = computed(() => props.toolCalls.filter((tc) => !isMemoryToolCall(tc)))
const allAgents = computed(() => props.toolCalls.every((tc) => tc.toolName === 'Agent'))
const allRegularAgents = computed(() => regularToolCalls.value.every((tc) => tc.toolName === 'Agent'))

// ─── Sub-component state (refs — top-level to avoid conditional hook calls) ─

// MemoryToolActivityGroup state
const memExpanded = ref(true)
const memDetailsExpanded = ref(false)

watch(
  () => props.isStreaming,
  (is) => {
    if (is) memExpanded.value = true
  },
)

// ToolCallGroupMulti state
const multiExpanded = ref(false)

// AgentToolGroup state
const agentExpanded = ref(true)

watch(
  () => props.isStreaming,
  (is) => {
    if (is) agentExpanded.value = true
  },
)

// AgentCallCard per-instance state (keyed by toolUseId)
const agentCardExpandedMap = ref<Record<string, boolean>>({})
const previewOpenMap = ref<string | null>(null)

function toggleAgentCardExpanded(id: string): void {
  agentCardExpandedMap.value = {
    ...agentCardExpandedMap.value,
    [id]: !agentCardExpandedMap.value[id],
  }
}

function openPreview(id: string): void {
  previewOpenMap.value = id
}

function closePreviewModal(): void {
  previewOpenMap.value = null
}

// ─── AgentToolGroup derived state (for allAgents + regularAgents) ──────────────────────

function computeAgentGroupDerived(
  agentToolCalls: ToolCall[],
  agentNotifications: Record<string, AgentTaskNotification>,
  resultMap: Map<string, ToolResult>,
  childToolCallsByParent: Map<string, ToolCall[]>,
  isStreaming: boolean,
): {
  statuses: Array<{ tc: ToolCall; status: AgentStatus; statusLabel: string; statusClassName: string }>
  isAnyRunning: boolean
  errorPresent: boolean
  allComplete: boolean
  anyStopped: boolean
} {
  const statuses = agentToolCalls.map((tc) => {
    const status = getAgentStatus({
      hasResult: resultMap.has(tc.toolUseId),
      isError: !!resultMap.get(tc.toolUseId)?.isError,
      isLaunchResult: isAgentLaunchResult(resultMap.get(tc.toolUseId)?.content),
      isStreaming: isStreaming && !resultMap.has(tc.toolUseId),
      childCount: (childToolCallsByParent.get(tc.toolUseId) ?? []).length,
      taskStatus: agentNotifications[tc.toolUseId]?.status,
    })
    return {
      tc,
      status,
      statusLabel: getAgentStatusLabel(status, t),
      statusClassName: getAgentStatusClassName(status),
    }
  })

  return {
    statuses,
    isAnyRunning: statuses.some((s) => s.status === 'running' || s.status === 'starting'),
    errorPresent: statuses.some((s) => s.status === 'failed'),
    allComplete: statuses.every((s) => s.status === 'done'),
    anyStopped: statuses.some((s) => s.status === 'stopped'),
  }
}

function getAgentGroupDerivedFor(tcs: ToolCall[]): ReturnType<typeof computeAgentGroupDerived> {
  return computeAgentGroupDerived(
    tcs,
    props.agentTaskNotifications,
    props.resultMap,
    props.childToolCallsByParent,
    !!props.isStreaming,
  )
}

// For the all-agents case (top-level)
const allAgentDerived = computed(() => getAgentGroupDerivedFor(props.toolCalls))

// For the regular-tool-calls case (when regular calls are all agents)
const regularAgentDerived = computed(() => getAgentGroupDerivedFor(regularToolCalls.value))

// ─── ToolCallGroupMulti derived state ──────────────────────────

const multiSummary = computed(() => generateSummary(props.toolCalls, t))
const multiErrorPresent = computed(() =>
  groupHasErrors(props.toolCalls, props.resultMap, props.childToolCallsByParent),
)
const multiHasUnresolved = computed(() =>
  hasUnresolvedToolCalls(props.toolCalls, props.resultMap, props.childToolCallsByParent),
)
const multiIsRunning = computed(() => !!props.isStreaming || multiHasUnresolved.value)
const multiHasNested = computed(() =>
  props.toolCalls.some((tc) => (props.childToolCallsByParent.get(tc.toolUseId)?.length ?? 0) > 0),
)

watch(
  () => [multiHasNested.value, multiIsRunning.value],
  ([hasNested, isRunning]) => {
    if (isRunning || hasNested) multiExpanded.value = true
  },
)

// ─── AgentCallCard per-call derived state ──────────────────────

function agentCardDerived(tc: ToolCall) {
  const result = props.resultMap.get(tc.toolUseId)
  const childToolCalls = props.childToolCallsByParent.get(tc.toolUseId) ?? []
  const isLaunchResult = isAgentLaunchResult(result?.content)
  const recentToolCalls = childToolCalls.slice(-2)
  const status = getAgentStatus({
    hasResult: !!result,
    isError: !!result?.isError,
    isLaunchResult,
    isStreaming: !!props.isStreaming && !props.resultMap.has(tc.toolUseId),
    childCount: childToolCalls.length,
    taskStatus: props.agentTaskNotifications[tc.toolUseId]?.status,
  })
  const statusClassName = getAgentStatusClassName(status)
  const statusLabel = getAgentStatusLabel(status, t)
  const taskSummary = props.agentTaskNotifications[tc.toolUseId]?.summary?.trim() || ''
  const taskResult = props.agentTaskNotifications[tc.toolUseId]?.result?.trim() || ''
  const errorText =
    status === 'failed'
      ? taskSummary || (result?.isError ? getAgentErrorSummary(result.content) : '')
      : result?.isError
      ? getAgentErrorSummary(result.content)
      : ''
  const fullOutputText =
    result &&
    !result.isError &&
    !isLaunchResult &&
    !isAgentLifecycleResult(result.content)
      ? extractAgentDisplayText(result.content).trim()
      : ''
  const terminalTaskReport = (status === 'done' || status === 'stopped') ? taskResult : ''
  const terminalTaskSummary = (status === 'done' || status === 'stopped') ? taskSummary : ''
  const previewText = terminalTaskReport || fullOutputText || terminalTaskSummary
  const outputSummary = previewText ? getAgentOutputSummary(previewText) : ''
  const input =
    tc.input && typeof tc.input === 'object'
      ? (tc.input as Record<string, unknown>)
      : {}
  const description = typeof input.description === 'string' ? input.description : ''

  return {
    result,
    childToolCalls,
    isLaunchResult,
    recentToolCalls,
    status,
    statusClassName,
    statusLabel,
    taskSummary,
    taskResult,
    errorText,
    fullOutputText,
    terminalTaskReport,
    terminalTaskSummary,
    previewText,
    outputSummary,
    description,
  }
}

// ─── ToolCallTree (recursive) ───────────────────────────────────
// Rendered inline in the template using v-for + ToolCallBlock + self-referencing template block

</script>

<template>
  <!--
    ════════════════════════════════════════════════════════════════
    TOP-LEVEL: memory activity routing
    ════════════════════════════════════════════════════════════════
  -->

  <!-- ─── Memory + regular tool calls present ─────────────────── -->
  <div v-if="memoryActivity && regularToolCalls.length > 0" class="mb-2 space-y-2">
    <!-- ── MemoryToolActivityGroup ── -->
    <div class="mb-2">
      <div
        data-testid="memory-tool-activity-card"
        class="overflow-hidden rounded-lg border border-[var(--color-memory-border)] bg-[var(--color-memory-surface)]"
      >
        <button
          type="button"
          @click="memExpanded = !memExpanded"
          class="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-[var(--color-surface-hover)]/50"
        >
          <span
            class="material-symbols-outlined text-[15px] shrink-0 text-[var(--color-text-tertiary)]"
            aria-hidden="true"
          >{{ memExpanded ? 'expand_more' : 'chevron_right' }}</span>
          <span
            class="material-symbols-outlined text-[15px] shrink-0 text-[var(--color-memory-accent)]"
            aria-hidden="true"
          >bookmarks</span>
          <span
            class="min-w-0 flex-1 truncate text-[13px] font-medium text-[var(--color-text-primary)]"
          >
            {{ t(memoryActivity.action === 'saved' ? 'chat.memorySavedFromToolsTitle' : 'chat.memoryReferencedTitle', { count: memoryActivity.files.length }) }}
          </span>
          <span
            v-if="isStreaming"
            class="h-1.5 w-1.5 rounded-full bg-[var(--color-memory-accent)] animate-pulse-dot"
          />
        </button>

        <div v-if="memExpanded" class="border-t border-[var(--color-border)]/55 px-3 py-2.5">
          <div class="space-y-1.5">
            <button
              v-for="file in memoryActivity.files.slice(0, 4)"
              :key="file.path"
              type="button"
              :title="file.path"
              @click="openMemorySettings(file.path)"
              class="group flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-[var(--color-surface-hover)] focus:outline-none focus-visible:shadow-[var(--shadow-focus-ring)]"
            >
              <span
                class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-sm border border-[var(--color-memory-border)] bg-[var(--color-memory-icon-bg)] text-[var(--color-text-tertiary)] group-hover:text-[var(--color-memory-accent)]"
              >
                <span class="material-symbols-outlined text-[12px]" aria-hidden="true">settings</span>
              </span>
              <span class="min-w-0 flex-1">
                <span class="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span class="truncate text-[13px] font-medium text-[var(--color-text-primary)]">
                    {{ file.label }}
                  </span>
                  <span
                    v-if="file.lineHint"
                    class="shrink-0 text-[12px] text-[var(--color-text-tertiary)]"
                  >{{ file.lineHint }}</span>
                </span>
                <span
                  v-if="file.preview"
                  class="mt-0.5 line-clamp-2 text-[12px] leading-5 text-[var(--color-text-secondary)]"
                >{{ file.preview }}</span>
              </span>
            </button>

            <div
              v-if="memoryActivity.files.length > 4"
              class="px-2 py-1 text-[12px] text-[var(--color-text-tertiary)]"
            >
              {{ t('chat.memoryMoreFiles', { count: memoryActivity.files.length - 4 }) }}
            </div>
          </div>

          <button
            type="button"
            @click="memDetailsExpanded = !memDetailsExpanded"
            class="mt-2 inline-flex h-7 items-center gap-1.5 rounded-md border border-[var(--color-border)] px-2 text-[11px] font-medium text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
          >
            <span class="material-symbols-outlined text-[13px]">
              {{ memDetailsExpanded ? 'expand_more' : 'chevron_right' }}
            </span>
            {{ t('chat.memoryTechnicalDetails') }}
          </button>

          <div v-if="memDetailsExpanded" class="mt-2 space-y-1">
            <template
              v-for="tc in memoryToolCalls"
              :key="tc.id"
            >
              <div class="space-y-1">
                <ToolCallBlock
                  :tool-name="tc.toolName"
                  :input="tc.input"
                  :result="resultMap.get(tc.toolUseId) ? { content: resultMap.get(tc.toolUseId)!.content, isError: resultMap.get(tc.toolUseId)!.isError } : null"
                  compact
                  :is-pending="tc.isPending"
                  :status="tc.status"
                  :partial-input="tc.partialInput"
                />
                <div
                  v-if="(childToolCallsByParent.get(tc.toolUseId) ?? []).length > 0"
                  class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                >
                  <div class="space-y-1">
                    <template
                      v-for="childToolCall in childToolCallsByParent.get(tc.toolUseId) ?? []"
                      :key="childToolCall.id"
                    >
                      <div class="space-y-1">
                        <ToolCallBlock
                          :tool-name="childToolCall.toolName"
                          :input="childToolCall.input"
                          :result="resultMap.get(childToolCall.toolUseId) ? { content: resultMap.get(childToolCall.toolUseId)!.content, isError: resultMap.get(childToolCall.toolUseId)!.isError } : null"
                          compact
                          :is-pending="childToolCall.isPending"
                          :status="childToolCall.status"
                          :partial-input="childToolCall.partialInput"
                        />
                        <!-- Nested child recursion (2 levels) -->
                        <div
                          v-if="(childToolCallsByParent.get(childToolCall.toolUseId) ?? []).length > 0"
                          class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                        >
                          <div class="space-y-1">
                            <template
                              v-for="grandchild in childToolCallsByParent.get(childToolCall.toolUseId) ?? []"
                              :key="grandchild.id"
                            >
                              <div class="space-y-1">
                                <ToolCallBlock
                                  :tool-name="grandchild.toolName"
                                  :input="grandchild.input"
                                  :result="resultMap.get(grandchild.toolUseId) ? { content: resultMap.get(grandchild.toolUseId)!.content, isError: resultMap.get(grandchild.toolUseId)!.isError } : null"
                                  compact
                                  :is-pending="grandchild.isPending"
                                  :status="grandchild.status"
                                  :partial-input="grandchild.partialInput"
                                />
                              </div>
                            </template>
                          </div>
                        </div>
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Regular tool calls content ── -->
    <!-- AgentToolGroup (when all regular calls are Agent) -->
    <div v-if="allRegularAgents && regularToolCalls.length > 0" class="mb-2">
      <button
        type="button"
        @click="agentExpanded = !agentExpanded"
        class="flex w-full items-center gap-2 rounded-lg border border-[var(--color-border)]/40 bg-[var(--color-surface-container-low)] px-3 py-1.5 text-left transition-colors hover:bg-[var(--color-surface-container-high)]"
      >
        <span class="material-symbols-outlined text-[14px] text-[var(--color-outline)]">
          {{ agentExpanded ? 'expand_less' : 'expand_more' }}
        </span>
        <span class="flex-1 truncate text-[12px] text-[var(--color-text-secondary)]">
          {{ regularToolCalls.length === 1 ? t('toolGroup.agentOne') : t('toolGroup.agentMany', { count: regularToolCalls.length }) }}
        </span>
        <span
          v-if="regularAgentDerived.isAnyRunning"
          class="rounded-full bg-[var(--color-warning)]/12 px-2 py-0.5 text-[10px] font-semibold text-[var(--color-warning)]"
        >
          {{ t('agentStatus.running') }}
        </span>
        <span
          v-else-if="regularAgentDerived.errorPresent"
          class="material-symbols-outlined text-[14px] text-[var(--color-error)]"
        >error</span>
        <span
          v-else-if="regularAgentDerived.allComplete"
          class="material-symbols-outlined text-[14px] text-[var(--color-success)]"
        >check_circle</span>
        <span
          v-else-if="!regularAgentDerived.anyStopped"
          class="material-symbols-outlined text-[14px] text-[var(--color-outline)]"
        >pending</span>
        <span
          v-else
          class="material-symbols-outlined text-[14px] text-[var(--color-outline)]"
        >stop_circle</span>
      </button>

      <div v-if="agentExpanded" class="relative mt-3 pl-5">
        <div class="absolute bottom-6 left-[11px] top-4 w-px rounded full bg-[var(--color-border)]/45" />
        <div class="space-y-2">
          <div v-for="tc in regularToolCalls" :key="tc.id" class="relative pl-7">
            <div class="absolute left-0 top-1/2 -translate-y-1/2">
              <div class="absolute left-[11px] top-1/2 h-px w-4 -translate-y-1/2 bg-[var(--color-border)]/45" />
              <div class="absolute left-[8px] top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full border border-[var(--color-border)]/65 bg-[var(--color-surface-container-lowest)] shadow-[0_0_0_2px_var(--color-surface)]" />
            </div>
            <!-- ── AgentCallCard ── -->
            <div
              class="overflow-hidden rounded-lg border border-[var(--color-border)]/50 bg-[var(--color-surface-container-lowest)]"
            >
              <div
                class="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--color-surface-hover)]/50"
              >
                <span
                  class="material-symbols-outlined text-[18px] text-[var(--color-outline)]"
                >smart_toy</span>
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <span
                      class="text-[13px] font-semibold text-[var(--color-text-primary)]"
                    >Agent</span>
                    <span
                      v-if="agentCardDerived(tc).description"
                      class="truncate text-[12px] text-[var(--color-text-secondary)]"
                    >{{ agentCardDerived(tc).description }}</span>
                  </div>
                  <!-- Collapsed summary: outputSummary -->
                  <div
                    v-if="!agentCardExpandedMap[tc.toolUseId] && agentCardDerived(tc).outputSummary"
                    class="mt-1 line-clamp-2 text-[11px] text-[var(--color-text-tertiary)]"
                  >{{ agentCardDerived(tc).outputSummary }}</div>
                  <!-- Collapsed summary: recentToolCalls -->
                  <div
                    v-else-if="!agentCardExpandedMap[tc.toolUseId] && !agentCardDerived(tc).outputSummary && agentCardDerived(tc).recentToolCalls.length > 0"
                    class="mt-1 space-y-1"
                  >
                    <div
                      v-for="recentToolCall in agentCardDerived(tc).recentToolCalls"
                      :key="recentToolCall.id"
                      class="truncate text-[11px] text-[var(--color-text-tertiary)]"
                    >{{ formatRecentToolUseSummary(recentToolCall, resultMap) }}</div>
                  </div>
                  <!-- Collapsed summary: errorText -->
                  <div
                    v-else-if="!agentCardExpandedMap[tc.toolUseId] && !agentCardDerived(tc).outputSummary && !agentCardDerived(tc).recentToolCalls.length && agentCardDerived(tc).errorText"
                    class="mt-1 truncate text-[11px] text-[var(--color-error)]"
                  >{{ agentCardDerived(tc).errorText }}</div>
                </div>
                <!-- View Result button -->
                <button
                  v-if="agentCardDerived(tc).outputSummary"
                  type="button"
                  @click="(event: Event) => { event.stopPropagation(); openPreview(tc.toolUseId) }"
                  class="shrink-0 rounded-md border border-[var(--color-border)] px-2.5 py-1 text-[11px] font-medium text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
                >
                  {{ t('agentStatus.viewResult') }}
                </button>
                <!-- Status badge -->
                <span
                  :class="'rounded-full px-2 py-0.5 text-[10px] font-semibold ' + agentCardDerived(tc).statusClassName"
                >{{ agentCardDerived(tc).statusLabel }}</span>
                <!-- Expand/collapse button -->
                <button
                  type="button"
                  @click="toggleAgentCardExpanded(tc.toolUseId)"
                  class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[var(--color-outline)] transition-colors hover:bg-[var(--color-surface-hover)]"
                  :aria-label="agentCardExpandedMap[tc.toolUseId] ? 'Collapse agent' : 'Expand agent'"
                >
                  <span class="material-symbols-outlined text-[16px]">
                    {{ agentCardExpandedMap[tc.toolUseId] ? 'expand_less' : 'expand_more' }}
                  </span>
                </button>
              </div>

              <!-- Expanded body -->
              <div v-if="agentCardExpandedMap[tc.toolUseId]" class="border-t border-[var(--color-border)]/60 px-3 py-3">
                <!-- Error text -->
                <div
                  v-if="agentCardDerived(tc).errorText"
                  class="mb-3 rounded-lg border border-[var(--color-error)]/20 bg-[var(--color-error-container)]/60 px-3 py-2 text-[11px] text-[var(--color-error)]"
                >{{ agentCardDerived(tc).errorText }}</div>
                <!-- Child tool calls -->
                <div v-if="agentCardDerived(tc).childToolCalls.length > 0" class="space-y-1">
                  <template
                    v-for="childToolCall in agentCardDerived(tc).childToolCalls"
                    :key="childToolCall.id"
                  >
                    <div class="space-y-1">
                      <ToolCallBlock
                        :tool-name="childToolCall.toolName"
                        :input="childToolCall.input"
                        :result="resultMap.get(childToolCall.toolUseId) ? { content: resultMap.get(childToolCall.toolUseId)!.content, isError: resultMap.get(childToolCall.toolUseId)!.isError } : null"
                        compact
                        :is-pending="childToolCall.isPending"
                        :status="childToolCall.status"
                        :partial-input="childToolCall.partialInput"
                      />
                      <!-- Nested children (2 levels) -->
                      <div
                        v-if="(childToolCallsByParent.get(childToolCall.toolUseId) ?? []).length > 0"
                        class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                      >
                        <div class="space-y-1">
                          <template
                            v-for="grandchild in childToolCallsByParent.get(childToolCall.toolUseId) ?? []"
                            :key="grandchild.id"
                          >
                            <div class="space-y-1">
                              <ToolCallBlock
                                :tool-name="grandchild.toolName"
                                :input="grandchild.input"
                                :result="resultMap.get(grandchild.toolUseId) ? { content: resultMap.get(grandchild.toolUseId)!.content, isError: resultMap.get(grandchild.toolUseId)!.isError } : null"
                                compact
                                :is-pending="grandchild.isPending"
                                :status="grandchild.status"
                                :partial-input="grandchild.partialInput"
                              />
                            </div>
                          </template>
                        </div>
                      </div>
                    </div>
                  </template>
                </div>
                <!-- No activity -->
                <div
                  v-else-if="agentCardDerived(tc).outputSummary"
                  class="text-[11px] text-[var(--color-text-tertiary)]"
                >{{ t('agentStatus.noActivity') }}</div>
                <div
                  v-else
                  class="text-[11px] text-[var(--color-text-tertiary)]"
                >{{ agentCardDerived(tc).status === 'starting' ? t('agentStatus.starting') : t('agentStatus.noActivity') }}</div>
              </div>
            </div>
            <!-- ── End AgentCallCard ── -->
          </div>
        </div>
      </div>
    </div>

    <!-- Single non-agent regular call -->
    <template v-else-if="regularToolCalls.length === 1">
      <div class="space-y-1">
        <ToolCallBlock
          :tool-name="regularToolCalls[0].toolName"
          :input="regularToolCalls[0].input"
          :result="resultMap.get(regularToolCalls[0].toolUseId) ? { content: resultMap.get(regularToolCalls[0].toolUseId)!.content, isError: resultMap.get(regularToolCalls[0].toolUseId)!.isError } : null"
          :is-pending="regularToolCalls[0].isPending"
          :status="regularToolCalls[0].status"
          :partial-input="regularToolCalls[0].partialInput"
        />
        <div
          v-if="(childToolCallsByParent.get(regularToolCalls[0].toolUseId) ?? []).length > 0"
          class="mb-2 ml-16 border-l border-[var(--color-border)]/60 pl-3"
        >
          <div class="space-y-1">
            <template
              v-for="childToolCall in childToolCallsByParent.get(regularToolCalls[0].toolUseId) ?? []"
              :key="childToolCall.id"
            >
              <div class="space-y-1">
                <ToolCallBlock
                  :tool-name="childToolCall.toolName"
                  :input="childToolCall.input"
                  :result="resultMap.get(childToolCall.toolUseId) ? { content: resultMap.get(childToolCall.toolUseId)!.content, isError: resultMap.get(childToolCall.toolUseId)!.isError } : null"
                  compact
                  :is-pending="childToolCall.isPending"
                  :status="childToolCall.status"
                  :partial-input="childToolCall.partialInput"
                />
                <!-- Nested children (2 levels) -->
                <div
                  v-if="(childToolCallsByParent.get(childToolCall.toolUseId) ?? []).length > 0"
                  class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                >
                  <div class="space-y-1">
                    <template
                      v-for="grandchild in childToolCallsByParent.get(childToolCall.toolUseId) ?? []"
                      :key="grandchild.id"
                    >
                      <div class="space-y-1">
                        <ToolCallBlock
                          :tool-name="grandchild.toolName"
                          :input="grandchild.input"
                          :result="resultMap.get(grandchild.toolUseId) ? { content: resultMap.get(grandchild.toolUseId)!.content, isError: resultMap.get(grandchild.toolUseId)!.isError } : null"
                          compact
                          :is-pending="grandchild.isPending"
                          :status="grandchild.status"
                          :partial-input="grandchild.partialInput"
                        />
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </template>

    <!-- Multiple non-agent regular calls (ToolCallGroupMulti) -->
    <div v-else-if="regularToolCalls.length > 1" class="mb-2">
      <button
        type="button"
        @click="multiExpanded = !multiExpanded"
        class="flex w-full items-center gap-2 rounded-lg border border-[var(--color-border)]/40 bg-[var(--color-surface-container-low)] px-3 py-1.5 text-left transition-colors hover:bg-[var(--color-surface-container-high)]"
      >
        <span class="material-symbols-outlined text-[14px] text-[var(--color-outline)]">
          {{ multiExpanded ? 'expand_less' : 'expand_more' }}
        </span>
        <span class="flex-1 truncate text-[12px] text-[var(--color-text-secondary)]">
          {{ generateSummary(regularToolCalls, t) }}
        </span>
        <span
          v-if="!multiIsRunning && !multiErrorPresent"
          class="material-symbols-outlined text-[14px] text-[var(--color-success)]"
        >check_circle</span>
        <span
          v-else-if="!multiIsRunning && multiErrorPresent"
          class="material-symbols-outlined text-[14px] text-[var(--color-error)]"
        >error</span>
        <span
          v-else-if="multiIsRunning"
          class="h-1.5 w-1.5 rounded-full bg-[var(--color-brand)] animate-pulse-dot"
        />
      </button>

      <div v-if="multiExpanded" class="mt-1.5 space-y-1">
        <template
          v-for="tc in regularToolCalls"
          :key="tc.id"
        >
          <div class="space-y-1">
            <ToolCallBlock
              :tool-name="tc.toolName"
              :input="tc.input"
              :result="resultMap.get(tc.toolUseId) ? { content: resultMap.get(tc.toolUseId)!.content, isError: resultMap.get(tc.toolUseId)!.isError } : null"
              compact
              :is-pending="tc.isPending"
              :status="tc.status"
              :partial-input="tc.partialInput"
            />
            <div
              v-if="(childToolCallsByParent.get(tc.toolUseId) ?? []).length > 0"
              class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
            >
              <div class="space-y-1">
                <template
                  v-for="childToolCall in childToolCallsByParent.get(tc.toolUseId) ?? []"
                  :key="childToolCall.id"
                >
                  <div class="space-y-1">
                    <ToolCallBlock
                      :tool-name="childToolCall.toolName"
                      :input="childToolCall.input"
                      :result="resultMap.get(childToolCall.toolUseId) ? { content: resultMap.get(childToolCall.toolUseId)!.content, isError: resultMap.get(childToolCall.toolUseId)!.isError } : null"
                      compact
                      :is-pending="childToolCall.isPending"
                      :status="childToolCall.status"
                      :partial-input="childToolCall.partialInput"
                    />
                    <!-- Nested children (2 levels) -->
                    <div
                      v-if="(childToolCallsByParent.get(childToolCall.toolUseId) ?? []).length > 0"
                      class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                    >
                      <div class="space-y-1">
                        <template
                          v-for="grandchild in childToolCallsByParent.get(childToolCall.toolUseId) ?? []"
                          :key="grandchild.id"
                        >
                          <div class="space-y-1">
                            <ToolCallBlock
                              :tool-name="grandchild.toolName"
                              :input="grandchild.input"
                              :result="resultMap.get(grandchild.toolUseId) ? { content: resultMap.get(grandchild.toolUseId)!.content, isError: resultMap.get(grandchild.toolUseId)!.isError } : null"
                              compact
                              :is-pending="grandchild.isPending"
                              :status="grandchild.status"
                              :partial-input="grandchild.partialInput"
                            />
                          </div>
                        </template>
                      </div>
                    </div>
                  </div>
                </template>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>

  <!-- ─── Memory only (no regular tool calls) ─────────────────── -->
  <div v-else-if="memoryActivity && regularToolCalls.length === 0" class="mb-2">
    <div
      data-testid="memory-tool-activity-card"
      class="overflow-hidden rounded-lg border border-[var(--color-memory-border)] bg-[var(--color-memory-surface)]"
    >
      <button
        type="button"
        @click="memExpanded = !memExpanded"
        class="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-[var(--color-surface-hover)]/50"
      >
        <span
          class="material-symbols-outlined text-[15px] shrink-0 text-[var(--color-text-tertiary)]"
          aria-hidden="true"
        >{{ memExpanded ? 'expand_more' : 'chevron_right' }}</span>
        <span
          class="material-symbols-outlined text-[15px] shrink-0 text-[var(--color-memory-accent)]"
          aria-hidden="true"
        >bookmarks</span>
        <span
          class="min-w-0 flex-1 truncate text-[13px] font-medium text-[var(--color-text-primary)]"
        >
          {{ t(memoryActivity.action === 'saved' ? 'chat.memorySavedFromToolsTitle' : 'chat.memoryReferencedTitle', { count: memoryActivity.files.length }) }}
        </span>
        <span
          v-if="isStreaming"
          class="h-1.5 w-1.5 rounded-full bg-[var(--color-memory-accent)] animate-pulse-dot"
        />
      </button>

      <div v-if="memExpanded" class="border-t border-[var(--color-border)]/55 px-3 py-2.5">
        <div class="space-y-1.5">
          <button
            v-for="file in memoryActivity.files.slice(0, 4)"
            :key="file.path"
            type="button"
            :title="file.path"
            @click="openMemorySettings(file.path)"
            class="group flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-[var(--color-surface-hover)] focus:outline-none focus-visible:shadow-[var(--shadow-focus-ring)]"
          >
            <span
              class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-sm border border-[var(--color-memory-border)] bg-[var(--color-memory-icon-bg)] text-[var(--color-text-tertiary)] group-hover:text-[var(--color-memory-accent)]"
            >
              <span class="material-symbols-outlined text-[12px]" aria-hidden="true">settings</span>
            </span>
            <span class="min-w-0 flex-1">
              <span class="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span class="truncate text-[13px] font-medium text-[var(--color-text-primary)]">
                  {{ file.label }}
                </span>
                <span
                  v-if="file.lineHint"
                  class="shrink-0 text-[12px] text-[var(--color-text-tertiary)]"
                >{{ file.lineHint }}</span>
              </span>
              <span
                v-if="file.preview"
                class="mt-0.5 line-clamp-2 text-[12px] leading-5 text-[var(--color-text-secondary)]"
              >{{ file.preview }}</span>
            </span>
          </button>

          <div
            v-if="memoryActivity.files.length > 4"
            class="px-2 py-1 text-[12px] text-[var(--color-text-tertiary)]"
          >
            {{ t('chat.memoryMoreFiles', { count: memoryActivity.files.length - 4 }) }}
          </div>
        </div>

        <button
          type="button"
          @click="memDetailsExpanded = !memDetailsExpanded"
          class="mt-2 inline-flex h-7 items-center gap-1.5 rounded-md border border-[var(--color-border)] px-2 text-[11px] font-medium text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
        >
          <span class="material-symbols-outlined text-[13px]">
            {{ memDetailsExpanded ? 'expand_more' : 'chevron_right' }}
          </span>
          {{ t('chat.memoryTechnicalDetails') }}
        </button>

        <div v-if="memDetailsExpanded" class="mt-2 space-y-1">
          <template
            v-for="tc in memoryToolCalls"
            :key="tc.id"
          >
            <div class="space-y-1">
              <ToolCallBlock
                :tool-name="tc.toolName"
                :input="tc.input"
                :result="resultMap.get(tc.toolUseId) ? { content: resultMap.get(tc.toolUseId)!.content, isError: resultMap.get(tc.toolUseId)!.isError } : null"
                compact
                :is-pending="tc.isPending"
                :status="tc.status"
                :partial-input="tc.partialInput"
              />
              <div
                v-if="(childToolCallsByParent.get(tc.toolUseId) ?? []).length > 0"
                class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
              >
                <div class="space-y-1">
                  <template
                    v-for="childToolCall in childToolCallsByParent.get(tc.toolUseId) ?? []"
                    :key="childToolCall.id"
                  >
                    <div class="space-y-1">
                      <ToolCallBlock
                        :tool-name="childToolCall.toolName"
                        :input="childToolCall.input"
                        :result="resultMap.get(childToolCall.toolUseId) ? { content: resultMap.get(childToolCall.toolUseId)!.content, isError: resultMap.get(childToolCall.toolUseId)!.isError } : null"
                        compact
                        :is-pending="childToolCall.isPending"
                        :status="childToolCall.status"
                        :partial-input="childToolCall.partialInput"
                      />
                      <div
                        v-if="(childToolCallsByParent.get(childToolCall.toolUseId) ?? []).length > 0"
                        class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                      >
                        <div class="space-y-1">
                          <template
                            v-for="grandchild in childToolCallsByParent.get(childToolCall.toolUseId) ?? []"
                            :key="grandchild.id"
                          >
                            <div class="space-y-1">
                              <ToolCallBlock
                                :tool-name="grandchild.toolName"
                                :input="grandchild.input"
                                :result="resultMap.get(grandchild.toolUseId) ? { content: resultMap.get(grandchild.toolUseId)!.content, isError: resultMap.get(grandchild.toolUseId)!.isError } : null"
                                compact
                                :is-pending="grandchild.isPending"
                                :status="grandchild.status"
                                :partial-input="grandchild.partialInput"
                              />
                            </div>
                          </template>
                        </div>
                      </div>
                    </div>
                  </template>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>

  <!-- ─── No memory activity — render directly ─────────────────── -->
  <template v-else>
    <!-- AgentToolGroup (all agents at top level) -->
    <div v-if="allAgents" class="mb-2">
      <button
        type="button"
        @click="agentExpanded = !agentExpanded"
        class="flex w-full items-center gap-2 rounded-lg border border-[var(--color-border)]/40 bg-[var(--color-surface-container-low)] px-3 py-1.5 text-left transition-colors hover:bg-[var(--color-surface-container-high)]"
      >
        <span class="material-symbols-outlined text-[14px] text-[var(--color-outline)]">
          {{ agentExpanded ? 'expand_less' : 'expand_more' }}
        </span>
        <span class="flex-1 truncate text-[12px] text-[var(--color-text-secondary)]">
          {{ toolCalls.length === 1 ? t('toolGroup.agentOne') : t('toolGroup.agentMany', { count: toolCalls.length }) }}
        </span>
        <span
          v-if="allAgentDerived.isAnyRunning"
          class="rounded-full bg-[var(--color-warning)]/12 px-2 py-0.5 text-[10px] font-semibold text-[var(--color-warning)]"
        >
          {{ t('agentStatus.running') }}
        </span>
        <span
          v-else-if="allAgentDerived.errorPresent"
          class="material-symbols-outlined text-[14px] text-[var(--color-error)]"
        >error</span>
        <span
          v-else-if="allAgentDerived.allComplete"
          class="material-symbols-outlined text-[14px] text-[var(--color-success)]"
        >check_circle</span>
        <span
          v-else-if="!allAgentDerived.anyStopped"
          class="material-symbols-outlined text-[14px] text-[var(--color-outline)]"
        >pending</span>
        <span
          v-else
          class="material-symbols-outlined text-[14px] text-[var(--color-outline)]"
        >stop_circle</span>
      </button>

      <div v-if="agentExpanded" class="relative mt-3 pl-5">
        <div class="absolute bottom-6 left-[11px] top-4 w-px rounded-full bg-[var(--color-border)]/45" />
        <div class="space-y-2">
          <div v-for="tc in toolCalls" :key="tc.id" class="relative pl-7">
            <div class="absolute left-0 top-1/2 -translate-y-1/2">
              <div class="absolute left-[11px] top-1/2 h-px w-4 -translate-y-1/2 bg-[var(--color-border)]/45" />
              <div class="absolute left-[8px] top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full border border-[var(--color-border)]/65 bg-[var(--color-surface-container-lowest)] shadow-[0_0_0_2px_var(--color-surface)]" />
            </div>
            <!-- ── AgentCallCard ── -->
            <div
              class="overflow-hidden rounded-lg border border-[var(--color-border)]/50 bg-[var(--color-surface-container-lowest)]"
            >
              <div
                class="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--color-surface-hover)]/50"
              >
                <span
                  class="material-symbols-outlined text-[18px] text-[var(--color-outline)]"
                >smart_toy</span>
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <span
                      class="text-[13px] font-semibold text-[var(--color-text-primary)]"
                    >Agent</span>
                    <span
                      v-if="agentCardDerived(tc).description"
                      class="truncate text-[12px] text-[var(--color-text-secondary)]"
                    >{{ agentCardDerived(tc).description }}</span>
                  </div>
                  <!-- Collapsed: outputSummary -->
                  <div
                    v-if="!agentCardExpandedMap[tc.toolUseId] && agentCardDerived(tc).outputSummary"
                    class="mt-1 line-clamp-2 text-[11px] text-[var(--color-text-tertiary)]"
                  >{{ agentCardDerived(tc).outputSummary }}</div>
                  <!-- Collapsed: recentToolCalls -->
                  <div
                    v-else-if="!agentCardExpandedMap[tc.toolUseId] && !agentCardDerived(tc).outputSummary && agentCardDerived(tc).recentToolCalls.length > 0"
                    class="mt-1 space-y-1"
                  >
                    <div
                      v-for="recentToolCall in agentCardDerived(tc).recentToolCalls"
                      :key="recentToolCall.id"
                      class="truncate text-[11px] text-[var(--color-text-tertiary)]"
                    >{{ formatRecentToolUseSummary(recentToolCall, resultMap) }}</div>
                  </div>
                  <!-- Collapsed: errorText -->
                  <div
                    v-else-if="!agentCardExpandedMap[tc.toolUseId] && !agentCardDerived(tc).outputSummary && !agentCardDerived(tc).recentToolCalls.length && agentCardDerived(tc).errorText"
                    class="mt-1 truncate text-[11px] text-[var(--color-error)]"
                  >{{ agentCardDerived(tc).errorText }}</div>
                </div>
                <!-- View Result button -->
                <button
                  v-if="agentCardDerived(tc).outputSummary"
                  type="button"
                  @click="(event: Event) => { event.stopPropagation(); openPreview(tc.toolUseId) }"
                  class="shrink-0 rounded-md border border-[var(--color-border)] px-2.5 py-1 text-[11px] font-medium text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
                >
                  {{ t('agentStatus.viewResult') }}
                </button>
                <!-- Status badge -->
                <span
                  :class="'rounded-full px-2 py-0.5 text-[10px] font-semibold ' + agentCardDerived(tc).statusClassName"
                >{{ agentCardDerived(tc).statusLabel }}</span>
                <!-- Expand/collapse button -->
                <button
                  type="button"
                  @click="toggleAgentCardExpanded(tc.toolUseId)"
                  class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[var(--color-outline)] transition-colors hover:bg-[var(--color-surface-hover)]"
                  :aria-label="agentCardExpandedMap[tc.toolUseId] ? 'Collapse agent' : 'Expand agent'"
                >
                  <span class="material-symbols-outlined text-[16px]">
                    {{ agentCardExpandedMap[tc.toolUseId] ? 'expand_less' : 'expand_more' }}
                  </span>
                </button>
              </div>

              <!-- Expanded body -->
              <div v-if="agentCardExpandedMap[tc.toolUseId]" class="border-t border-[var(--color-border)]/60 px-3 py-3">
                <div
                  v-if="agentCardDerived(tc).errorText"
                  class="mb-3 rounded-lg border border-[var(--color-error)]/20 bg-[var(--color-error-container)]/60 px-3 py-2 text-[11px] text-[var(--color-error)]"
                >{{ agentCardDerived(tc).errorText }}</div>
                <div v-if="agentCardDerived(tc).childToolCalls.length > 0" class="space-y-1">
                  <template
                    v-for="childToolCall in agentCardDerived(tc).childToolCalls"
                    :key="childToolCall.id"
                  >
                    <div class="space-y-1">
                      <ToolCallBlock
                        :tool-name="childToolCall.toolName"
                        :input="childToolCall.input"
                        :result="resultMap.get(childToolCall.toolUseId) ? { content: resultMap.get(childToolCall.toolUseId)!.content, isError: resultMap.get(childToolCall.toolUseId)!.isError } : null"
                        compact
                        :is-pending="childToolCall.isPending"
                        :status="childToolCall.status"
                        :partial-input="childToolCall.partialInput"
                      />
                      <div
                        v-if="(childToolCallsByParent.get(childToolCall.toolUseId) ?? []).length > 0"
                        class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                      >
                        <div class="space-y-1">
                          <template
                            v-for="grandchild in childToolCallsByParent.get(childToolCall.toolUseId) ?? []"
                            :key="grandchild.id"
                          >
                            <div class="space-y-1">
                              <ToolCallBlock
                                :tool-name="grandchild.toolName"
                                :input="grandchild.input"
                                :result="resultMap.get(grandchild.toolUseId) ? { content: resultMap.get(grandchild.toolUseId)!.content, isError: resultMap.get(grandchild.toolUseId)!.isError } : null"
                                compact
                                :is-pending="grandchild.isPending"
                                :status="grandchild.status"
                                :partial-input="grandchild.partialInput"
                              />
                            </div>
                          </template>
                        </div>
                      </div>
                    </div>
                  </template>
                </div>
                <div
                  v-else-if="agentCardDerived(tc).outputSummary"
                  class="text-[11px] text-[var(--color-text-tertiary)]"
                >{{ t('agentStatus.noActivity') }}</div>
                <div
                  v-else
                  class="text-[11px] text-[var(--color-text-tertiary)]"
                >{{ agentCardDerived(tc).status === 'starting' ? t('agentStatus.starting') : t('agentStatus.noActivity') }}</div>
              </div>
            </div>
            <!-- ── End AgentCallCard ── -->
          </div>
        </div>
      </div>
    </div>

    <!-- Single non-agent tool call -->
    <template v-else-if="toolCalls.length === 1">
      <div class="space-y-1">
        <ToolCallBlock
          :tool-name="toolCalls[0].toolName"
          :input="toolCalls[0].input"
          :result="resultMap.get(toolCalls[0].toolUseId) ? { content: resultMap.get(toolCalls[0].toolUseId)!.content, isError: resultMap.get(toolCalls[0].toolUseId)!.isError } : null"
          :is-pending="toolCalls[0].isPending"
          :status="toolCalls[0].status"
          :partial-input="toolCalls[0].partialInput"
        />
        <div
          v-if="(childToolCallsByParent.get(toolCalls[0].toolUseId) ?? []).length > 0"
          class="mb-2 ml-16 border-l border-[var(--color-border)]/60 pl-3"
        >
          <div class="space-y-1">
            <template
              v-for="childToolCall in childToolCallsByParent.get(toolCalls[0].toolUseId) ?? []"
              :key="childToolCall.id"
            >
              <div class="space-y-1">
                <ToolCallBlock
                  :tool-name="childToolCall.toolName"
                  :input="childToolCall.input"
                  :result="resultMap.get(childToolCall.toolUseId) ? { content: resultMap.get(childToolCall.toolUseId)!.content, isError: resultMap.get(childToolCall.toolUseId)!.isError } : null"
                  compact
                  :is-pending="childToolCall.isPending"
                  :status="childToolCall.status"
                  :partial-input="childToolCall.partialInput"
                />
                <div
                  v-if="(childToolCallsByParent.get(childToolCall.toolUseId) ?? []).length > 0"
                  class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                >
                  <div class="space-y-1">
                    <template
                      v-for="grandchild in childToolCallsByParent.get(childToolCall.toolUseId) ?? []"
                      :key="grandchild.id"
                    >
                      <div class="space-y-1">
                        <ToolCallBlock
                          :tool-name="grandchild.toolName"
                          :input="grandchild.input"
                          :result="resultMap.get(grandchild.toolUseId) ? { content: resultMap.get(grandchild.toolUseId)!.content, isError: resultMap.get(grandchild.toolUseId)!.isError } : null"
                          compact
                          :is-pending="grandchild.isPending"
                          :status="grandchild.status"
                          :partial-input="grandchild.partialInput"
                        />
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </template>

    <!-- Multiple non-agent tool calls (ToolCallGroupMulti) -->
    <div v-else class="mb-2">
      <button
        type="button"
        @click="multiExpanded = !multiExpanded"
        class="flex w-full items-center gap-2 rounded-lg border border-[var(--color-border)]/40 bg-[var(--color-surface-container-low)] px-3 py-1.5 text-left transition-colors hover:bg-[var(--color-surface-container-high)]"
      >
        <span class="material-symbols-outlined text-[14px] text-[var(--color-outline)]">
          {{ multiExpanded ? 'expand_less' : 'expand_more' }}
        </span>
        <span class="flex-1 truncate text-[12px] text-[var(--color-text-secondary)]">
          {{ multiSummary }}
        </span>
        <span
          v-if="!multiIsRunning && !multiErrorPresent"
          class="material-symbols-outlined text-[14px] text-[var(--color-success)]"
        >check_circle</span>
        <span
          v-else-if="!multiIsRunning && multiErrorPresent"
          class="material-symbols-outlined text-[14px] text-[var(--color-error)]"
        >error</span>
        <span
          v-else-if="multiIsRunning"
          class="h-1.5 w-1.5 rounded-full bg-[var(--color-brand)] animate-pulse-dot"
        />
      </button>

      <div v-if="multiExpanded" class="mt-1.5 space-y-1">
        <template
          v-for="tc in toolCalls"
          :key="tc.id"
        >
          <div class="space-y-1">
            <ToolCallBlock
              :tool-name="tc.toolName"
              :input="tc.input"
              :result="resultMap.get(tc.toolUseId) ? { content: resultMap.get(tc.toolUseId)!.content, isError: resultMap.get(tc.toolUseId)!.isError } : null"
              compact
              :is-pending="tc.isPending"
              :status="tc.status"
              :partial-input="tc.partialInput"
            />
            <div
              v-if="(childToolCallsByParent.get(tc.toolUseId) ?? []).length > 0"
              class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
            >
              <div class="space-y-1">
                <template
                  v-for="childToolCall in childToolCallsByParent.get(tc.toolUseId) ?? []"
                  :key="childToolCall.id"
                >
                  <div class="space-y-1">
                    <ToolCallBlock
                      :tool-name="childToolCall.toolName"
                      :input="childToolCall.input"
                      :result="resultMap.get(childToolCall.toolUseId) ? { content: resultMap.get(childToolCall.toolUseId)!.content, isError: resultMap.get(childToolCall.toolUseId)!.isError } : null"
                      compact
                      :is-pender="childToolCall.isPending"
                      :status="childToolCall.status"
                      :partial-input="childToolCall.partialInput"
                    />
                    <div
                      v-if="(childToolCallsByParent.get(childToolCall.toolUseId) ?? []).length > 0"
                      class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                    >
                      <div class="space-y-1">
                        <template
                          v-for="grandchild in childToolCallsByParent.get(childToolCall.toolUseId) ?? []"
                          :key="grandchild.id"
                        >
                          <div class="space-y-1">
                            <ToolCallBlock
                              :tool-name="grandchild.toolName"
                              :input="grandchild.input"
                              :result="resultMap.get(grandchild.toolUseId) ? { content: resultMap.get(grandchild.toolUseId)!.content, isError: resultMap.get(grandchild.toolUseId)!.isError } : null"
                              compact
                              :is-pending="grandchild.isPending"
                              :status="grandchild.status"
                              :partial-input="grandchild.partialInput"
                            />
                          </div>
                        </template>
                      </div>
                    </div>
                  </div>
                </template>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </template>

  <!-- ─── Preview Modal (shared across all AgentCallCards) ─── -->
  <teleport to="body">
    <Modal
      v-if="previewOpenMap"
      :open="!!previewOpenMap"
      :on-close="closePreviewModal"
      :title="(agentCardDerived(toolCalls.find(tc => tc.toolUseId === previewOpenMap)!).description || t('agentStatus.resultTitle'))"
      :width="900"
    >
      <div class="max-h-[70vh] overflow-y-auto">
        <MarkdownRenderer
          :content="(agentCardDerived(toolCalls.find(tc => tc.toolUseId === previewOpenMap)!).previewText || agentCardDerived(toolCalls.find(tc => tc.toolUseId === previewOpenMap)!).errorText)"
        />
      </div>
    </Modal>
  </teleport>
</template>
