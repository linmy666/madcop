<script setup lang="ts">
/**
 * RunItemCard — one tool-call rendered as a "RunItem" block
 * (OpenAI Agents SDK style).
 *
 * States:
 *   - pending: spinner + target, default expanded (user wants to
 *     see what's running, not the result)
 *   - done:    ✓ + tool · target · duration · optional result preview
 *              (collapsed by default; click to expand)
 *   - failed:  ✗ + tool · target + error snippet
 */
import { computed, ref } from 'vue'
import { useTranslation } from '../../i18n'

interface Props {
  toolName: string
  input?: unknown
  isPending?: boolean
  result?: { content: unknown; isError?: boolean } | null
  durationMs?: number
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  isPending: false,
  result: null,
  durationMs: undefined,
  error: undefined,
})

const t = useTranslation()

const expanded = ref(false)

interface ToolMeta { verb: string; icon: string; labelKey?: string }
const TOOL_META: Record<string, ToolMeta> = {
  read_file:         { verb: '读取文件', labelKey: 'runItem.verb.readFile', icon: 'description' },
  write_file:        { verb: '写入文件', labelKey: 'runItem.verb.writeFile', icon: 'edit_note' },
  write_xlsx:        { verb: '生成表格', labelKey: 'runItem.verb.writeXlsx', icon: 'table_chart' },
  edit_file:         { verb: '编辑文件', labelKey: 'runItem.verb.editFile', icon: 'edit' },
  web_search:        { verb: '搜索网络', labelKey: 'runItem.verb.webSearch', icon: 'search' },
  web_fetch:         { verb: '抓取页面', labelKey: 'runItem.verb.webFetch', icon: 'download' },
  bash:              { verb: '执行命令', labelKey: 'runItem.verb.bash', icon: 'terminal' },
  get_current_time:  { verb: '获取时间', labelKey: 'runItem.verb.getCurrentTime', icon: 'schedule' },
  get_weather:       { verb: '查询天气', labelKey: 'runItem.verb.getWeather', icon: 'cloud' },
  query_rag:         { verb: '查询记忆', labelKey: 'runItem.verb.queryRag', icon: 'memory' },
  recall_memory:     { verb: '回忆记忆', labelKey: 'runItem.verb.recallMemory', icon: 'history' },
  remember:          { verb: '记住', labelKey: 'runItem.verb.remember',     icon: 'bookmark' },
  route:             { verb: '路由', labelKey: 'runItem.verb.route',     icon: 'alt_route' },
  ask_user:          { verb: '提问', labelKey: 'runItem.verb.askUser',     icon: 'help_outline' },
  echo:              { verb: '输出', labelKey: 'runItem.verb.echo',     icon: 'format_quote' },
}
const meta = computed<ToolMeta>(() => {
  const m = TOOL_META[(props.toolName || '').toLowerCase()]
    || { verb: props.toolName, icon: 'settings' }
  if (m.labelKey) m.verb = t(m.labelKey as any, m.verb)
  return m
})

const target = computed(() => {
  const input = props.input
  if (!input) return ''
  if (typeof input === 'string') {
    try { return extractFromObj(JSON.parse(input)) } catch { return input.slice(0, 80) }
  }
  if (typeof input === 'object' && input !== null) return extractFromObj(input as Record<string, unknown>)
  return ''
})

function extractFromObj(obj: Record<string, unknown>): string {
  for (const key of ['path', 'file_path', 'filePath', 'target_path', 'file']) {
    const v = obj[key]
    if (typeof v === 'string' && v) return shortenPath(v)
  }
  for (const key of ['query', 'q', 'search', 'question', 'prompt', 'fact']) {
    const v = obj[key]
    if (typeof v === 'string' && v) return v.slice(0, 80)
  }
  for (const key of ['command', 'cmd']) {
    const v = obj[key]
    if (typeof v === 'string' && v) return v.slice(0, 80)
  }
  return ''
}

function shortenPath(p: string): string {
  const parts = p.split('/')
  if (parts.length <= 2) return p
  return '…/' + parts.slice(-2).join('/')
}

const isFailed = computed(() => {
  if (props.error) return true
  if (props.result?.isError) return true
  if (!props.result) return false
  const content = typeof props.result.content === 'string'
    ? props.result.content : JSON.stringify(props.result.content || '')
  return content.includes('"error"') || content.startsWith('Error') || content.includes('failed')
})

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
  try {
    const parsed = JSON.parse(text)
    if (parsed && typeof parsed === 'object') {
      const bytes = parsed.bytes ?? parsed.size
      if (typeof bytes === 'number') return formatBytes(bytes)
      if (Array.isArray(parsed.results)) return `${parsed.results.length} 条结果`
      if (Array.isArray(parsed)) return `${parsed.length} 条结果`
    } else if (Array.isArray(parsed)) {
      return `${parsed.length} 条结果`
    }
  } catch { /* not JSON */ }
  return ''
})

function formatBytes(n: number): string {
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)}MB`
  if (n >= 1024) return `${(n / 1024).toFixed(1)}KB`
  return `${n}B`
}

const resultText = computed(() => {
  if (props.isPending || !props.result) return ''
  const c = props.result.content
  if (typeof c === 'string') return c
  try { return JSON.stringify(c, null, 2) } catch { return String(c) }
})

const errorText = computed(() => {
  if (props.error) return props.error
  if (!isFailed.value || !props.result) return ''
  const c = props.result.content
  if (typeof c === 'string') return c
  try { return JSON.stringify(c) } catch { return String(c) }
})
</script>

<template>
  <div
    class="run-item"
    :class="{
      'run-item--pending': isPending,
      'run-item--done': !isPending && !isFailed,
      'run-item--failed': !isPending && isFailed,
      'run-item--expanded': expanded,
    }"
    data-testid="run-item"
    :data-tool="toolName"
    :data-state="isPending ? 'pending' : (isFailed ? 'failed' : 'done')"
  >
    <button
      type="button"
      class="run-item__head"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <span class="run-item__icon" aria-hidden="true">
        <svg v-if="isPending" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <path d="M21 12a9 9 0 1 1-6.219-8.56" />
        </svg>
        <svg v-else-if="isFailed" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
          <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
        </svg>
        <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </span>
      <span class="run-item__verb">{{ meta.verb }}</span>
      <code v-if="target" class="run-item__target">{{ target }}</code>
      <span v-if="resultSummary" class="run-item__meta">{{ resultSummary }}</span>
      <span v-if="durationLabel" class="run-item__meta">· {{ durationLabel }}</span>
      <svg class="run-item__chev" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
        <polyline v-if="!expanded" points="6 9 12 15 18 9" />
        <polyline v-else points="6 15 12 9 18 15" />
      </svg>
    </button>
    <div v-if="expanded" class="run-item__body" :class="{ 'run-item__body--error': isFailed }">
      <div v-if="isPending" class="run-item__pending-row">
        <div class="run-item__bar"><div class="run-item__bar-fill"></div></div>
        <span class="run-item__pending-text">{{ t('runItem.running', '运行中…') }}</span>
      </div>
      <div v-else-if="isFailed" class="run-item__error-pre">
        <pre>{{ errorText || '执行失败' }}</pre>
      </div>
      <pre v-else-if="resultText" class="run-item__result-pre">{{ resultText }}</pre>
    </div>
  </div>
</template>

<style scoped>
.run-item {
  display: block;
  margin: 4px 0;
  border: 1px solid var(--color-border, rgba(128,128,128,0.18));
  border-radius: 8px;
  background: var(--color-surface-container-low, rgba(128,128,128,0.04));
  overflow: hidden;
  transition: border-color 120ms, background 120ms;
}
.run-item--pending {
  border-color: var(--color-primary, #7c5cff);
  background: color-mix(in srgb, var(--color-primary, #7c5cff) 8%, transparent);
}
.run-item--failed {
  border-color: var(--color-error, #d44a4a);
  background: color-mix(in srgb, var(--color-error, #d44a4a) 6%, transparent);
}
.run-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 10px;
  background: transparent;
  border: 0;
  cursor: pointer;
  text-align: left;
  color: inherit;
  font-family: inherit;
  font-size: 12px;
}
.run-item__head:hover {
  background: var(--color-surface-hover, rgba(128,128,128,0.06));
}
.run-item__icon {
  display: inline-flex;
  width: 18px;
  height: 18px;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--color-text-tertiary, #888);
}
.run-item--pending .run-item__icon {
  color: var(--color-primary, #7c5cff);
  animation: run-item-spin 0.9s linear infinite;
}
.run-item--done .run-item__icon {
  color: var(--color-success, #1f9d55);
}
.run-item--failed .run-item__icon {
  color: var(--color-error, #d44a4a);
}
@keyframes run-item-spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
.run-item__verb {
  font-weight: 600;
  color: var(--color-text-primary, #111);
}
.run-item__target {
  font-family: var(--font-mono, ui-monospace, monospace);
  color: var(--color-text-secondary, #555);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 50%;
}
.run-item__meta {
  margin-left: auto;
  color: var(--color-text-tertiary, #888);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.run-item__chev {
  color: var(--color-text-tertiary, #888);
  flex-shrink: 0;
}
.run-item__body {
  border-top: 1px solid var(--color-border, rgba(128,128,128,0.12));
  padding: 8px 10px;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px;
  max-height: 320px;
  overflow: auto;
}
.run-item__body--error {
  color: var(--color-error, #d44a4a);
}
.run-item__result-pre,
.run-item__error-pre pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--color-text-secondary, #555);
}
.run-item__pending-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-sans, system-ui, sans-serif);
  color: var(--color-primary, #7c5cff);
}
.run-item__bar {
  flex: 1;
  height: 4px;
  background: var(--color-border, rgba(128,128,128,0.18));
  border-radius: 2px;
  overflow: hidden;
}
.run-item__bar-fill {
  height: 100%;
  width: 40%;
  background: currentColor;
  border-radius: 2px;
  animation: run-item-progress 1.4s ease-in-out infinite;
}
@keyframes run-item-progress {
  0%   { transform: translateX(-100%); }
  50%  { transform: translateX(60%); }
  100% { transform: translateX(180%); }
}
.run-item__pending-text {
  font-size: 11px;
}
</style>
