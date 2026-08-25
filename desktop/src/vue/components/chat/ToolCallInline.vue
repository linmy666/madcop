<script setup lang="ts">
/**
 * ToolCallInline — lightweight one-line tool-call indicator.
 *
 * Renders as a single dim gray line: icon + verb + target.
 * No color, no frame, no cartoon. Reads as 'process metadata'
 * rather than 'content'. Designed to flow inline with the
 * streaming narrative: think → explore file → think → answer.
 */
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  toolName: string
  input?: unknown
  isPending?: boolean
  result?: { content: unknown; isError?: boolean } | null
  /** v4 tool_end metadata.elapsed_ms — SDK-standard tool-row duration. */
  durationMs?: number
}>(), {
  isPending: false,
  result: null,
  durationMs: undefined,
})

interface ToolMeta { verb: string; icon: string }

const TOOL_META: Record<string, ToolMeta> = {
  read_file:         { verb: '探索',   icon: 'search' },
  write_file:        { verb: '编辑',   icon: 'edit' },
  write_xlsx:        { verb: '生成',   icon: 'grid_on' },
  edit_file:         { verb: '修改',   icon: 'edit' },
  web_search:        { verb: '搜索',   icon: 'search' },
  web_fetch:         { verb: '抓取',   icon: 'download' },
  bash:              { verb: '执行',   icon: 'terminal' },
  get_current_time:  { verb: '获取时间', icon: 'schedule' },
  get_weather:       { verb: '查询天气', icon: 'cloud' },
  query_rag:         { verb: '查询记忆', icon: 'memory' },
  recall_memory:     { verb: '回忆',   icon: 'memory' },
  remember:          { verb: '记忆',   icon: 'bookmark_border' },
  route:             { verb: '路由',   icon: 'alt_route' },
  ask_user:          { verb: '提问',   icon: 'help_outline' },
  echo:              { verb: '输出',   icon: 'format_quote' },
}

const meta = computed<ToolMeta>(() =>
  TOOL_META[(props.toolName || '').toLowerCase()] || { verb: '调用', icon: 'settings' }
)

const target = computed(() => {
  const input = props.input
  if (!input) return ''
  if (typeof input === 'string') {
    try { return extractFromObj(JSON.parse(input)) } catch { return input.slice(0, 60) }
  }
  if (typeof input === 'object' && input !== null) return extractFromObj(input as Record<string, unknown>)
  return ''
})

function extractFromObj(obj: Record<string, unknown>): string {
  for (const key of ['path', 'file_path', 'filePath', 'target_path']) {
    const v = obj[key]
    if (typeof v === 'string' && v) return shortenPath(v)
  }
  for (const key of ['query', 'q', 'search']) {
    const v = obj[key]
    if (typeof v === 'string' && v) return v.slice(0, 50)
  }
  for (const key of ['command', 'cmd']) {
    const v = obj[key]
    if (typeof v === 'string' && v) return v.slice(0, 50)
  }
  for (const key of ['question', 'prompt', 'fact']) {
    const v = obj[key]
    if (typeof v === 'string' && v) return v.slice(0, 50)
  }
  return ''
}

function shortenPath(p: string): string {
  const parts = p.split('/')
  if (parts.length <= 2) return p
  return '…/' + parts.slice(-2).join('/')
}

const isFailed = computed(() => {
  if (props.result?.isError) return true
  if (!props.result) return false
  const content = typeof props.result.content === 'string'
    ? props.result.content
    : JSON.stringify(props.result.content || '')
  return content.includes('"error"') || content.startsWith('Error') || content.includes('failed')
})

const statusIcon = computed(() => {
  if (isFailed.value) return 'close'
  if (props.result) return 'check'
  return ''
})

// SDK-standard tool-row suffix (Claude Code style): duration + result
// size/hit-count, e.g. "编辑 …/index.html · 23.9KB · 1.2s".
const durationLabel = computed(() => {
  if (props.isPending || props.durationMs == null) return ''
  const ms = props.durationMs
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.max(1, Math.round(ms))}ms`
})

const resultSummary = computed(() => {
  if (props.isPending || !props.result) return ''
  const c = props.result.content
  const text = typeof c === 'string' ? c : ''
  if (!text) return ''
  // write_file/edit_file: tool_result JSON carries byte length
  try {
    const parsed = JSON.parse(text)
    if (parsed && typeof parsed === 'object') {
      const bytes = parsed.bytes ?? parsed.size ?? (typeof parsed.content === 'string' ? parsed.content.length : undefined)
      if (typeof bytes === 'number') return formatBytes(bytes)
      if (Array.isArray(parsed.results)) return `${parsed.results.length} 条结果`
      if (Array.isArray(parsed)) return `${parsed.length} 条结果`
    } else if (Array.isArray(parsed)) {
      return `${parsed.length} 条结果`
    }
  } catch { /* not JSON */ }
  if (text.startsWith('[')) return ''
  return ''
})

function formatBytes(n: number): string {
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)}MB`
  if (n >= 1024) return `${(n / 1024).toFixed(1)}KB`
  return `${n}B`
}
</script>

<template>
  <div class="tool-inline" data-testid="tool-inline">
    <span v-if="isPending" class="tool-inline__spinner" aria-hidden="true"></span>
    <svg v-else-if="isFailed" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" class="tool-inline__status--failed" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
    <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="tool-inline__status--ok" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>
    <span class="tool-inline__verb">{{ meta.verb }}</span>
    <span v-if="target" class="tool-inline__target">{{ target }}</span>
    <span v-if="resultSummary" class="tool-inline__meta">{{ resultSummary }}</span>
    <span v-if="durationLabel" class="tool-inline__meta">· {{ durationLabel }}</span>
  </div>
</template>

<style scoped>
.tool-inline {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 2px 0;
  margin: 1px 0;
  font-size: 12px;
  line-height: 1.5;
  /* v3.8.3 — uniform dim gray, no color accents */
  color: var(--color-text-tertiary, #999);
}

.tool-inline__spinner {
  width: 10px;
  height: 10px;
  border-width: 1.5px;
  color: var(--color-text-tertiary, #999);
  flex-shrink: 0;
}

.tool-inline__meta {
  font-size: 11px;
  color: var(--color-text-tertiary, #aaa);
  opacity: 0.85;
}

.tool-inline__status--ok {
  color: inherit;
  opacity: 0.5;
}
.tool-inline__status--failed {
  color: inherit;
  opacity: 0.7;
}
.tool-inline__legacy-status {
  font-size: 13px;
  flex-shrink: 0;
  /* Same gray as the rest — no green/red */
  color: inherit;
  opacity: 0.6;
}
/* v3.10.1 — failed tool calls show a red ✗ */
.tool-inline__status--failed {
  color: #e03131;
  opacity: 0.8;
}

.tool-inline__icon {
  font-size: 13px;
  flex-shrink: 0;
  opacity: 0.5;
}

.tool-inline__verb {
  font-weight: 400;
}

.tool-inline__target {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px;
  opacity: 0.7;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
}
</style>