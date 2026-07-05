<script setup lang="ts">
import { ref, computed, h, type VNode } from 'vue'
import { useTranslation } from '../../i18n'
import type { TranslationKey } from '../../i18n'
import CodeViewer from './CodeViewer.vue'
import DiffViewer from './DiffViewer.vue'
import TerminalChrome from './TerminalChrome.vue'
import CopyButton from '../shared/CopyButton.vue'
import InlineImageGallery from './InlineImageGallery.vue'
import type { AgentTaskNotification } from '../../types/chat'
import PlanPreviewCard from './PlanModePreview.vue'
import { extractPlanPreview, isExitPlanModeTool } from './planModePreviewHelpers'
import PlanToolCallBlock from './PlanToolCallBlock.vue'

// ─── Props ────────────────────────────────────────────────────

export interface ToolCallBlockProps {
  toolName: string
  input: unknown
  result?: { content: unknown; isError: boolean } | null
  compact?: boolean
  isPending?: boolean
  status?: 'stopped'
  agentTaskNotification?: AgentTaskNotification
  partialInput?: string
}

const props = withDefaults(defineProps<ToolCallBlockProps>(), {
  compact: false,
  isPending: false,
  partialInput: undefined,
})

// ─── Constants ────────────────────────────────────────────────

const TOOL_ICONS: Record<string, string> = {
  Bash: 'terminal',
  Read: 'description',
  Write: 'edit_document',
  Edit: 'edit_note',
  Glob: 'search',
  Grep: 'find_in_page',
  Agent: 'smart_toy',
  WebSearch: 'travel_explore',
  WebFetch: 'cloud_download',
  NotebookEdit: 'note',
  Skill: 'auto_awesome',
}

const WRITER_PREVIEW_MAX_LINES = 120
const WRITER_PREVIEW_MAX_CHARS = 30000

interface ContentStats {
  lines: number
  chars: number
  visibleLines?: number
  windowed?: boolean
}

// ─── Pure helper functions ────────────────────────────────────

function extractTextContent(content: unknown): string | null {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    return content
      .map((chunk: any) => (typeof chunk === 'string' ? chunk : chunk?.text || ''))
      .filter(Boolean)
      .join('\n')
  }
  if (content && typeof content === 'object') {
    return JSON.stringify(content, null, 2)
  }
  return null
}

function getToolSummary(
  toolName: string,
  obj: Record<string, unknown>,
  t?: (key: TranslationKey, params?: Record<string, string | number>) => string,
): string {
  switch (toolName) {
    case 'Bash':
      return typeof obj.command === 'string' ? obj.command : ''
    case 'Read':
      return t?.('tool.readFileContents') ?? 'Read file contents'
    case 'Write':
      return typeof obj.content === 'string'
        ? (t?.('tool.linesCreated', { count: obj.content.split('\n').length }) ?? `${obj.content.split('\n').length} lines created`)
        : (t?.('tool.createFile') ?? 'Create file')
    case 'Edit':
      return typeof obj.old_string === 'string' && typeof obj.new_string === 'string'
        ? changedLineSummary(obj.old_string, obj.new_string, t)
        : (t?.('tool.updateFileContents') ?? 'Update file contents')
    case 'Glob':
      return typeof obj.pattern === 'string' ? obj.pattern : ''
    case 'Grep':
      return typeof obj.pattern === 'string' ? obj.pattern : ''
    case 'Agent':
      return typeof obj.description === 'string' ? obj.description : ''
    default:
      return ''
  }
}

function changedLineSummary(
  oldString: string,
  newString: string,
  t?: (key: TranslationKey, params?: Record<string, string | number>) => string,
): string {
  const oldLines = oldString.split('\n')
  const newLines = newString.split('\n')
  let changed = 0
  const max = Math.max(oldLines.length, newLines.length)
  for (let index = 0; index < max; index += 1) {
    if ((oldLines[index] ?? '') !== (newLines[index] ?? '')) {
      changed += 1
    }
  }
  return t?.('tool.linesChanged', { count: changed }) ?? `${changed} lines changed`
}

function getToolResultSummary(
  toolName: string,
  content: unknown,
  isError: boolean,
  t?: (key: TranslationKey, params?: Record<string, string | number>) => string,
): string {
  const text = extractTextContent(content)
  if (!text) return ''
  if (isError) {
    const firstLine = text
      .split('\n')
      .map((line) => stripAnsi(line).replace(/\s+/g, ' ').trim())
      .find(Boolean)
    if (!firstLine) return t?.('tool.error') ?? 'Error'
    return firstLine.length <= 72 ? firstLine : `${firstLine.slice(0, 72)}…`
  }
  if (toolName === 'Bash') return ''
  const lineCount = text.split('\n').length
  if (lineCount > 1) {
    return t?.('tool.linesOutput', { count: lineCount }) ?? `${lineCount} lines output`
  }
  const compact = text.replace(/\s+/g, ' ').trim()
  if (!compact) return ''
  if (compact.length <= 36) return compact
  return `${compact.slice(0, 36)}…`
}

function stripAnsi(value: string): string {
  return value.replace(/\x1B\[[0-9;]*m/g, '')
}

function getPendingSummary(
  toolName: string,
  t?: (key: TranslationKey, params?: Record<string, string | number>) => string,
): string {
  if (toolName === 'Write') return t?.('tool.generatingContent') ?? 'Generating content'
  if (toolName === 'Edit' || toolName === 'MultiEdit') return t?.('tool.preparingEdit') ?? 'Preparing edit'
  return t?.('tool.preparingTool') ?? 'Preparing tool'
}

function getVisibleResultText(
  toolName: string,
  result?: { content: unknown; isError: boolean } | null,
): string | null {
  if (!result) return null
  const text = extractTextContent(result.content)
  if (!text) return null
  if (result.isError) return text
  if (toolName === 'Bash' || toolName === 'Read' || toolName === 'Edit' || toolName === 'Write') return null
  return text
}

function getToolContentStats(
  toolName: string,
  obj: Record<string, unknown>,
  partialInput?: string,
): ContentStats | null {
  const content = getToolContentForStats(toolName, obj, partialInput)
  return content === null ? null : countContentStats(content)
}

function getToolContentForStats(
  toolName: string,
  obj: Record<string, unknown>,
  partialInput?: string,
): string | null {
  if (toolName === 'Write') {
    if (typeof obj.content === 'string') return obj.content
    return partialInput ? extractPartialJsonStringField(partialInput, 'content') : null
  }
  if (toolName === 'Edit') {
    if (typeof obj.new_string === 'string') return obj.new_string
    return partialInput ? extractPartialJsonStringField(partialInput, 'new_string') : null
  }
  if (toolName === 'MultiEdit' && Array.isArray(obj.edits)) {
    const replacements = obj.edits
      .map((edit) =>
        edit && typeof edit === 'object' && typeof (edit as Record<string, unknown>).new_string === 'string'
          ? (edit as Record<string, string>).new_string
          : ''
      )
      .filter(Boolean)
    return replacements.length > 0 ? replacements.join('\n') : null
  }
  return null
}

function countContentStats(content: string): ContentStats {
  return {
    lines: content.length === 0 ? 0 : content.split('\n').length,
    chars: content.length,
  }
}

function formatContentStats(
  stats: ContentStats,
  t?: (key: TranslationKey, params?: Record<string, string | number>) => string,
): string {
  const chars = formatCharCount(stats.chars, t)
  if (stats.windowed && typeof stats.visibleLines === 'number' && stats.visibleLines < stats.lines) {
    return t?.('tool.contentStatsLatest', {
      visible: formatCount(stats.visibleLines),
      total: formatCount(stats.lines),
      chars,
    }) ?? `Latest ${formatCount(stats.visibleLines)} / ${formatCount(stats.lines)} lines · ${chars}`
  }
  return t?.('tool.contentStats', {
    lines: formatLineCount(stats.lines, t),
    chars,
  }) ?? `${formatLineCount(stats.lines, t)} · ${chars}`
}

function formatLineCount(
  count: number,
  t?: (key: TranslationKey, params?: Record<string, string | number>) => string,
): string {
  return count === 1
    ? (t?.('tool.lineCountSingular', { count: formatCount(count) }) ?? `${formatCount(count)} line`)
    : (t?.('tool.lineCountPlural', { count: formatCount(count) }) ?? `${formatCount(count)} lines`)
}

function formatCharCount(
  count: number,
  t?: (key: TranslationKey, params?: Record<string, string | number>) => string,
): string {
  return count === 1
    ? (t?.('tool.charCountSingular', { count: formatCount(count) }) ?? `${formatCount(count)} char`)
    : (t?.('tool.charCountPlural', { count: formatCount(count) }) ?? `${formatCount(count)} chars`)
}

function formatCount(count: number): string {
  return new Intl.NumberFormat().format(count)
}

function extractPartialJsonStringField(source: string, field: string): string | null {
  const key = `"${field}"`
  const keyIndex = source.indexOf(key)
  if (keyIndex < 0) return null
  const colonIndex = source.indexOf(':', keyIndex + key.length)
  if (colonIndex < 0) return null

  let index = colonIndex + 1
  while (index < source.length && /\s/.test(source[index] ?? '')) index += 1
  if (source[index] !== '"') return null
  index += 1

  let value = ''
  while (index < source.length) {
    const char = source[index]
    if (char === '"') return value
    if (char !== '\\') {
      value += char
      index += 1
      continue
    }
    const escaped = source[index + 1]
    if (escaped === undefined) break
    switch (escaped) {
      case 'n': value += '\n'; index += 2; break
      case 'r': value += '\r'; index += 2; break
      case 't': value += '\t'; index += 2; break
      case 'b': value += '\b'; index += 2; break
      case 'f': value += '\f'; index += 2; break
      case '"':
      case '\\':
      case '/':
        value += escaped; index += 2; break
      case 'u': {
        const hex = source.slice(index + 2, index + 6)
        if (/^[0-9a-fA-F]{4}$/.test(hex)) {
          value += String.fromCharCode(Number.parseInt(hex, 16))
          index += 6
        } else {
          index = source.length
        }
        break
      }
      default:
        value += escaped; index += 2; break
    }
  }
  return value
}

function formatPartialJsonInput(source: string): string {
  const trimmed = source.trim()
  if (!trimmed) return source
  try {
    return JSON.stringify(JSON.parse(trimmed), null, 2)
  } catch {
    return formatJsonLikeInput(trimmed)
  }
}

function formatJsonLikeInput(source: string): string {
  let output = ''
  let indent = 0
  let inString = false
  let escaping = false
  let skipWhitespace = false

  const newline = () => {
    output = output.trimEnd()
    output += `\n${'  '.repeat(indent)}`
    skipWhitespace = true
  }

  for (const char of source) {
    if (inString) {
      output += char
      if (escaping) escaping = false
      else if (char === '\\') escaping = true
      else if (char === '"') inString = false
      continue
    }
    if (skipWhitespace && /\s/.test(char)) { skipWhitespace = false; continue }
    skipWhitespace = false
    if (char === '"') { inString = true; output += char; continue }
    if (char === '{' || char === '[') { output += char; indent += 1; newline(); continue }
    if (char === '}' || char === ']') {
      indent = Math.max(0, indent - 1)
      if (!output.endsWith('\n')) newline()
      output += char
      continue
    }
    if (char === ',') { output += char; newline(); continue }
    if (char === ':') { output += ': '; skipWhitespace = true; continue }
    output += char
  }
  return output.trimEnd()
}

// ─── Component setup (render function) ────────────────────────

const t = useTranslation()

const isPlanTool = computed(() => isExitPlanModeTool(props.toolName))
const expanded = ref(isPlanTool.value)

const obj = computed<Record<string, unknown>>(() =>
  props.input && typeof props.input === 'object'
    ? (props.input as Record<string, unknown>)
    : {}
)

const icon = computed(() => TOOL_ICONS[props.toolName] || 'build')
const filePath = computed(() =>
  typeof obj.value.file_path === 'string' ? obj.value.file_path : ''
)
const summary = computed(() => getToolSummary(props.toolName, obj.value, t))
const outputSummary = computed(() =>
  getToolResultSummary(props.toolName, props.result?.content, props.result?.isError ?? false, t)
)
const pendingSummary = computed(() =>
  props.isPending && !props.result ? getPendingSummary(props.toolName, t) : ''
)
const stoppedSummary = computed(() =>
  props.status === 'stopped' && !props.result ? t('tool.stopped') : ''
)
const liveStats = computed<ContentStats | null>(() =>
  getToolContentStats(props.toolName, obj.value, props.isPending ? props.partialInput : undefined)
)
const liveStatsSummary = computed(() =>
  liveStats.value ? formatContentStats(liveStats.value, t) : ''
)
const hasResultDetails = computed(() =>
  Boolean(props.result && extractTextContent(props.result.content))
)
const hasEditPreview = computed(() =>
  props.toolName === 'Edit' &&
  typeof obj.value.old_string === 'string' &&
  typeof obj.value.new_string === 'string'
)
const hasWritePreview = computed(() =>
  props.toolName === 'Write' && typeof obj.value.content === 'string'
)
const expandable = computed(() =>
  hasEditPreview.value || hasWritePreview.value || hasResultDetails.value ||
  Boolean(props.isPending && props.partialInput)
)

// Compute plan tool preview
const planPreview = computed(() => {
  if (!isPlanTool.value) return null
  return extractPlanPreview(props.input, props.result?.content)
})

// ─── JSX render helpers ───────────────────────────────────────

function renderStatusIndicators(): VNode[] | null {
  const nodes: VNode[] = []

  if (pendingSummary.value) {
    nodes.push(h('span', {
      class: 'inline-flex min-w-0 max-w-[58%] shrink-0 items-center gap-1 text-[10px] text-[var(--color-outline)]',
      title: liveStatsSummary.value ? `${pendingSummary.value} · ${liveStatsSummary.value}` : pendingSummary.value,
    }, [
      h('span', { class: 'material-symbols-outlined', style: { fontSize: '12px' } }, 'auto_awesome'),
      h('span', { class: 'truncate' }, pendingSummary.value),
      liveStatsSummary.value ? h('span', { class: 'shrink-0 text-[var(--color-text-tertiary)]' }, '·') : null,
      liveStatsSummary.value ? h('span', {
        class: 'shrink-0 font-[var(--font-mono)] tabular-nums text-[var(--color-text-tertiary)]',
      }, liveStatsSummary.value) : null,
    ]))
  } else if (stoppedSummary.value) {
    nodes.push(h('span', {
      class: 'inline-flex shrink-0 items-center gap-1 text-[10px] text-[var(--color-outline)]',
    }, [
      h('span', { class: 'material-symbols-outlined', style: { fontSize: '12px' } }, 'stop_circle'),
      stoppedSummary.value,
    ]))
  } else if (props.result && outputSummary.value) {
    nodes.push(h('span', {
      class: ['shrink-0 text-[10px]', props.result.isError ? 'text-[var(--color-error)]' : 'text-[var(--color-outline)]'],
    }, outputSummary.value))
  } else if (liveStatsSummary.value) {
    nodes.push(h('span', {
      class: 'shrink-0 font-[var(--font-mono)] text-[10px] tabular-nums text-[var(--color-outline)]',
    }, liveStatsSummary.value))
  }

  if (props.result?.isError) {
    nodes.push(h('span', {
      class: 'material-symbols-outlined shrink-0 text-[14px] text-[var(--color-error)]',
    }, 'error'))
  }

  if (expandable.value) {
    nodes.push(h('span', {
      class: 'material-symbols-outlined text-[14px] text-[var(--color-outline)]',
    }, expanded.value ? 'expand_less' : 'expand_more'))
  }

  return nodes.length > 0 ? nodes : null
}

function renderResultOutput(result: { content: unknown; isError: boolean }, text: string): VNode {
  return h('div', {}, [
    h(InlineImageGallery, { text }),
    h('div', {
      class: [
        'overflow-hidden rounded-lg border',
        result.isError
          ? 'border-[var(--color-error)]/20 bg-[var(--color-error-container)]/60'
          : 'border-[var(--color-border)] bg-[var(--color-surface)]'
      ],
    }, [
      h('div', {
        class: 'flex items-center justify-between border-b border-[var(--color-border)]/60 px-3 py-2 text-[10px] uppercase tracking-[0.18em] text-[var(--color-outline)]',
      }, [
        h('span', {}, result.isError ? (t('tool.errorOutput') ?? 'Error Output') : (t('tool.toolOutput') ?? 'Tool Output')),
        h(CopyButton, {
          text,
          class: 'rounded-md border border-[var(--color-border)] px-2 py-1 text-[10px] normal-case tracking-normal text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text-primary)]',
        }),
      ]),
      result.isError
        ? h('pre', {
            class: 'max-h-[420px] overflow-auto whitespace-pre-wrap break-words bg-[var(--color-code-bg)] px-3 py-2 font-[var(--font-mono)] text-[12px] leading-[1.45] text-[var(--color-error)]',
          }, text)
        : h(CodeViewer, { code: text, language: 'plaintext', maxLines: 18 }),
    ]),
  ])
}

function renderPreviewContent(): VNode | null {
  const text = getVisibleResultText(props.toolName, props.result)
  const resultOutput = props.result && text ? renderResultOutput(props.result, text) : null

  if (hasEditPreview.value) {
    return h('div', {}, [
      h(DiffViewer, {
        filePath: filePath.value || 'file',
        oldString: obj.value.old_string as string,
        newString: obj.value.new_string as string,
      }),
      resultOutput,
    ])
  }

  if (hasWritePreview.value) {
    return h('div', {}, [
      h(DiffViewer, {
        filePath: filePath.value || 'file',
        oldString: '',
        newString: obj.value.content as string,
      }),
      resultOutput,
    ])
  }

  if (props.toolName === 'Bash' && typeof obj.value.command === 'string') {
    return h('div', {}, [
      h(TerminalChrome, {
        title: typeof obj.value.description === 'string' ? obj.value.description : filePath.value,
      }, () => h('div', {
        class: 'px-3 py-2.5 font-[var(--font-mono)] text-[11px] leading-[1.3] text-[var(--color-terminal-fg)]',
      }, [
        h('span', { class: 'text-[var(--color-terminal-accent)]' }, '$ '),
        obj.value.command as string,
      ])),
      resultOutput,
    ])
  }

  if (props.toolName === 'Read') {
    return resultOutput || null
  }

  return resultOutput
}

function renderDetailsContent(): VNode | null {
  const partialInput = props.isPending ? props.partialInput : undefined

  if (partialInput) {
    if (props.toolName === 'Write') {
      const writerContent = extractPartialJsonStringField(partialInput, 'content')
      if (writerContent !== null) {
        return renderWriterPreview(writerContent)
      }
    }
    return renderPartialInput(partialInput)
  }

  if (props.toolName === 'Edit' || props.toolName === 'Write') return null

  const text = JSON.stringify(obj.value, null, 2)
  return h('div', {
    class: 'overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]',
  }, [
    h('div', {
      class: 'flex items-center justify-between border-b border-[var(--color-border)] px-3 py-2 text-[10px] uppercase tracking-[0.18em] text-[var(--color-outline)]',
    }, [
      h('span', {}, t('tool.toolInput') ?? 'Tool Input'),
      h(CopyButton, {
        text,
        class: 'rounded-md border border-[var(--color-border)] px-2 py-1 text-[10px] normal-case tracking-normal text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text-primary)]',
      }),
    ]),
    h(CodeViewer, { code: text, language: 'json', maxLines: 18 }),
  ])
}

function renderWriterPreview(content: string): VNode {
  const contentStats = countContentStats(content)
  const lines = content.length === 0 ? [] : content.split('\n')
  const totalLines = contentStats.lines
  const visibleLines = lines.length > WRITER_preview_MAX_LINES
    ? lines.slice(-WRITER_preview_MAX_LINES)
    : lines
  let visibleContent = visibleLines.join('\n')
  const charTruncated = visibleContent.length > WRITER_preview_MAX_CHARS
  if (charTruncated) {
    visibleContent = visibleContent.slice(-WRITER_preview_MAX_CHARS)
  }
  const lineWindowed = totalLines > visibleLines.length
  const isWindowed = lineWindowed || charTruncated
  const visibleLineCount = visibleContent.length === 0 ? 0 : visibleContent.split('\n').length
  const statsSummary = formatContentStats({
    lines: totalLines,
    chars: contentStats.chars,
    visibleLines: visibleLineCount,
    windowed: isWindowed,
  }, t)

  return h('div', {
    class: 'overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]',
  }, [
    h('div', {
      class: 'flex items-center justify-between border-b border-[var(--color-border)] px-3 py-2 text-[10px] uppercase tracking-[0.18em] text-[var(--color-outline)]',
    }, [
      h('span', {}, t('tool.writerPreview') ?? 'Writer'),
      h('span', { class: 'font-[var(--font-mono)] normal-case tracking-normal tabular-nums' }, statsSummary),
    ]),
    h('pre', {
      class: 'max-h-[420px] overflow-auto whitespace-pre-wrap break-words bg-[var(--color-code-bg)] px-3 py-2 font-[var(--font-mono)] text-[12px] leading-[1.45] text-[var(--color-code-fg)]',
    }, visibleContent),
  ])
}

function renderPartialInput(partialInput: string): VNode {
  const formattedInput = formatPartialJsonInput(partialInput)
  return h('div', {
    class: 'overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]',
  }, [
    h('div', {
      class: 'border-b border-[var(--color-border)] px-3 py-2 text-[10px] uppercase tracking-[0.18em] text-[var(--color-outline)]',
    }, t('tool.partialInput') ?? 'Partial input'),
    h(CodeViewer, { code: formattedInput, language: 'json', maxLines: 8, wrapLongLines: true }),
  ])
}


// ─── Main render ──────────────────────────────────────────────

// ─── Computed values for template ──────────────────────────────

const planTitle = computed(() => {
  if (!isPlanTool.value) return ''
  return props.result?.isError
    ? t('permission.planRejected')
    : props.result
      ? t('permission.planApproved')
      : t('permission.planReadyTitle')
})

const hasRawResult = computed(() => {
  if (!isPlanTool.value) return false
  return Boolean(props.result && extractTextContent(props.result.content))
})

const statusNodes = computed(() => renderStatusIndicators() || [])

const previewContent = computed(() => renderPreviewContent())

const resultOutputVNode = computed(() => {
  if (!isPlanTool.value) return null
  if (!props.result?.isError || !hasRawResult.value) return null
  const text = extractTextContent(props.result.content) ?? ''
  return renderResultOutput(props.result, text)
})

const filePathLabel = computed(() => {
  if (!filePath.value) return ''
  const parts = filePath.value.split('/')
  return parts[parts.length - 1] || filePath.value
})

function toggleExpanded() {
  if (expandable.value) {
    expanded.value = !expanded.value
  }
}
</script>

<template>
  <!-- ─── Plan tool case ────────────────────────────────────── -->
  <div
    v-if="isPlanTool"
    :class="[
      'overflow-hidden rounded-lg border border-[var(--color-brand)]/35 bg-[var(--color-surface-container-lowest)]',
      compact ? 'mb-0' : 'mb-2'
    ]"
  >
    <button
      type="button"
      class="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-[var(--color-surface-hover)]/50"
      @click="expanded = !expanded"
    >
      <span class="material-symbols-outlined text-[14px] text-[var(--color-brand)]">architecture</span>
      <span class="min-w-0 flex-1 truncate text-[12px] font-semibold text-[var(--color-text-primary)]">{{ planTitle }}</span>
      <span
        v-if="planPreview?.filePath"
        class="hidden max-w-[40%] truncate font-[var(--font-mono)] text-[11px] text-[var(--color-text-tertiary)] sm:inline"
      >{{ planPreview?.filePath }}</span>
      <span
        v-if="isPending"
        class="inline-flex shrink-0 items-center gap-1 text-[10px] text-[var(--color-outline)]"
      >
        <span class="material-symbols-outlined" style="font-size: 12px;">auto_awesome</span>
        {{ t('tool.preparingTool') }}
      </span>
      <span
        class="material-symbols-outlined text-[14px] text-[var(--color-outline)]"
      >{{ expanded ? 'expand_less' : 'expand_more' }}</span>
    </button>
    <div
      v-if="expanded"
      class="space-y-2.5 border-t border-[var(--color-border)]/60 px-3 py-3"
    >
      <PlanPreviewCard
        :title="t('permission.planPreviewTitle')"
        :plan="planPreview?.plan"
        :file-path="planPreview?.filePath"
        :allowed-prompts="planPreview?.allowedPrompts"
        :requested-permissions-title="t('permission.planRequestedPermissions')"
        :empty-label="t('permission.planEmpty')"
      />
      <component v-if="resultOutputVNode" :is="resultOutputVNode" />
    </div>
  </div>

  <!-- ─── Main tool call block ──────────────────────────────── -->
  <div
    v-else
    :class="[
      'overflow-hidden rounded-lg border border-[var(--color-border)]/50 bg-[var(--color-surface-container-lowest)]',
      compact ? 'mb-0' : 'mb-2'
    ]"
  >
    <button
      type="button"
      class="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-[var(--color-surface-hover)]/50"
      @click="toggleExpanded"
    >
      <span class="material-symbols-outlined text-[14px] text-[var(--color-outline)]">{{ icon }}</span>
      <span class="text-[11px] font-semibold text-[var(--color-text-secondary)]">{{ toolName }}</span>
      <span
        v-if="filePathLabel"
        class="min-w-0 flex-1 truncate font-[var(--font-mono)] text-[11px] text-[var(--color-text-tertiary)]"
      >{{ filePathLabel }}</span>
      <span
        v-else-if="summary"
        class="min-w-0 flex-1 truncate font-[var(--font-mono)] text-[11px] text-[var(--color-text-tertiary)]"
      >{{ summary }}</span>
      <span v-else class="flex-1"></span>
      <!-- status nodes (pending, stopped, output summary, error icon) -->
      <template v-if="statusNodes.length">
        <component v-for="(node, idx) in statusNodes" :key="idx" :is="node" />
      </template>
    </button>
    <!-- expanded content -->
    <div
      v-if="expanded && expandable"
      class="border-t border-[var(--color-border)]/60 px-3 py-3"
    >
      <component v-if="previewContent" :is="previewContent" />
    </div>
  </div>
</template>
