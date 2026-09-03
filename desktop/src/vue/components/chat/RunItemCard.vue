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
  /** Bytes streamed so far while the model composes big tool args. */
  streamingChars?: number
  /** Engine step chip, e.g. 3 of 8. */
  step?: number
  maxSteps?: number
  /** Sibling position within a same-step parallel batch. */
  parallelIndex?: number
  parallelCount?: number
  /** Guardian (codex parity): 'allow' = auto-approved by the LLM
   *  reviewer without a HITL card; 'deny' = refused with a reason. */
  guardian?: 'allow' | 'deny' | string
  guardianReason?: string
}

const props = withDefaults(defineProps<Props>(), {
  isPending: false,
  result: null,
  durationMs: undefined,
  error: undefined,
  streamingChars: undefined,
  step: undefined,
  maxSteps: undefined,
  parallelIndex: undefined,
  parallelCount: undefined,
})

const t = useTranslation()

const expanded = ref(false)

// Long-task liveness: a pending card ticks elapsed seconds so the user
// sees time moving during the minutes a big write_file takes to compose.
import { watch, onBeforeUnmount } from 'vue'
const nowTick = ref(Date.now())
let tickTimer: ReturnType<typeof setInterval> | null = null
const startedAt = ref<number | null>(null)
watch(
  () => props.isPending,
  (pending) => {
    if (pending && startedAt.value == null) startedAt.value = Date.now()
    if (pending && !tickTimer) {
      tickTimer = setInterval(() => { nowTick.value = Date.now() }, 1000)
    } else if (!pending && tickTimer) {
      clearInterval(tickTimer)
      tickTimer = null
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => { if (tickTimer) clearInterval(tickTimer) })

const elapsedLabel = computed(() => {
  if (!props.isPending || startedAt.value == null) return ''
  const s = Math.max(0, Math.floor((nowTick.value - startedAt.value) / 1000))
  return s >= 60
    ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
    : `${s}s`
})

const streamingLabel = computed(() => {
  if (props.isPending && props.streamingChars && props.streamingChars > 0) {
    const kb = props.streamingChars / 1024
    return kb >= 1 ? `${kb.toFixed(1)} KB` : `${props.streamingChars} B`
  }
  return ''
})

// Step chip removed by product request: "Step 1/40" leaked the ENGINE's
// step budget into the UI. Users read it as a 40-step plan for a
// one-tool query. The parallel-call sibling suffix (2/3) is kept —
// that part IS real user-visible information.
const stepLabel = computed(() => {
  const par = props.parallelIndex && props.parallelCount && props.parallelCount > 1
    ? ` · ${props.parallelIndex}/${props.parallelCount}` : ''
  return par
})

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
      <span v-if="stepLabel" class="run-item__meta">{{ stepLabel }}</span>
      <span v-if="streamingLabel" class="run-item__meta run-item__meta--live">
        {{ t('runItem.composing', 'composing…') }} {{ streamingLabel }}
      </span>
      <span v-if="resultSummary" class="run-item__meta">{{ resultSummary }}</span>
      <span v-if="durationLabel" class="run-item__meta">· {{ durationLabel }}</span>
      <span
        v-if="guardian"
        :title="guardian === 'allow'
          ? `Guardian 预审通过，自动放行（${guardianReason || '低风险'}）`
          : `Guardian 拒绝：${guardianReason || '高风险命令'}`"
        :class="[
          'run-item__guardian',
          guardian === 'allow' ? 'run-item__guardian--allow' : 'run-item__guardian--deny'
        ]"
      >
        <span class="material-symbols-outlined" style="font-size: 12px; line-height: 1">shield</span>
        {{ guardian === 'allow' ? 'Guardian 放行' : 'Guardian 拒绝' }}
      </span>
      <span v-if="elapsedLabel" class="run-item__meta run-item__elapsed">{{ elapsedLabel }}</span>
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
  margin: 2px 0;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  overflow: hidden;
  transition: border-color 120ms, background 120ms;
  /* Rows fade-slide in as the run progresses — the timeline reads as
     motion, not as blocks popping into existence. */
  animation: run-item-in 180ms ease-out;
}
@keyframes run-item-in {
  from { opacity: 0; transform: translateY(3px); }
  to   { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  .run-item { animation: none; }
}
/* A finished row only gains a surface on hover — at rest it reads as
   part of the narration, not as a box (Codex activity-row language). */
.run-item:not(.run-item--pending):hover {
  border-color: var(--color-border, rgba(128,128,128,0.18));
  background: var(--color-surface-container-low, rgba(128,128,128,0.04));
}
/* Pending goes quieter still — a Codex-style hairline activity row, not
   a card: no border, no fill, muted text. It becomes a real card only
   once it has a result to show. Progress lives in the global capsule. */
.run-item--pending {
  border-color: transparent;
  background: transparent;
}
.run-item--pending .run-item__verb,
.run-item--pending .run-item__meta {
  color: var(--color-text-tertiary, rgba(128,128,128,0.8));
}

.run-item__guardian {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: 6px;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  vertical-align: middle;
}
.run-item__guardian--allow {
  color: var(--color-text-tertiary);
  background: var(--color-surface-container);
}
.run-item__guardian--deny {
  color: var(--color-error);
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
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
  color: var(--color-text-tertiary, #888);
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
.run-item__meta--live {
  color: var(--color-text-secondary, #666);
  font-variant-numeric: tabular-nums;
}
.run-item__elapsed {
  font-variant-numeric: tabular-nums;
  min-width: 34px;
  text-align: right;
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
  color: var(--color-text-tertiary, #888);
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
  background: var(--color-text-tertiary, #999);
  border-radius: 2px;
  animation: run-item-progress 1.4s ease-in-out infinite;
}
@media (prefers-reduced-motion: reduce) {
  .run-item--pending .run-item__icon,
  .run-item__bar-fill { animation: none !important; }
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
