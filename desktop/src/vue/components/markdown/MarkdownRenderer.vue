<!--
  v3.0 — MarkdownRenderer (Vue 3 SFC)
  Full translation of src/components/markdown/MarkdownRenderer.tsx (566 lines).
  Renders markdown content with code highlighting, tables, task lists,
  KaTeX math, and Mermaid diagrams.
-->
<script setup lang="ts">
import { computed, h, defineComponent, ref, watch, onBeforeUnmount } from 'vue'
import DOMPurify from 'dompurify'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { marked, type Tokens } from 'marked'
import CodeViewer from '../chat/CodeViewer.vue'
import MermaidRenderer from '../chat/MermaidRenderer.vue'

// ── Props ─────────────────────────────────────────────────────────────────────
export interface MarkdownRendererProps {
  content: string
  variant?: 'default' | 'document' | 'compact'
  class?: string
  cache?: boolean
  streaming?: boolean
  onLinkClick?: (href: string, event: MouseEvent) => boolean | void
}

const props = withDefaults(defineProps<MarkdownRendererProps>(), {
  variant: 'default',
  class: undefined,
  cache: true,
  streaming: false,
  onLinkClick: undefined,
})

// ── Types ─────────────────────────────────────────────────────────────────────
interface CodeBlock {
  id: string
  code: string
  language: string | undefined
}

interface MathBlock {
  id: string
  tex: string
  displayMode: boolean
}

type HtmlPart = { type: 'html'; content: string }
type CodePart = { type: 'code'; block: CodeBlock }
type MarkdownPart = HtmlPart | CodePart

// ── Constants ─────────────────────────────────────────────────────────────────
const MERMAID_LANGUAGE = 'mermaid'
const PLAINTEXT_LANGUAGES = new Set(['', 'text', 'plaintext', 'plain'])
const MERMAID_DIAGRAM_START = /^(graph|flowchart|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|journey|gantt|pie|gitGraph|mindmap|timeline|requirementDiagram|quadrantChart|xychart-beta|sankey-beta|block-beta|packet-beta|architecture|kanban)\b/i
const CODE_FENCE_START = /^ {0,3}(`{3,}|~{3,})/
const MATH_RENDER_CACHE_LIMIT = 200
const mathRenderCache = new Map<string, string>()

const FINALIZED_CACHE_MAX_ENTRIES = 200
const FINALIZED_CACHE_MAX_CHARS = 8_000_000
const STREAMING_CACHE_MAX_ENTRIES = 4

// ── Helper functions (verbatim from React, no logic change) ───────────────────
function normalizeCodeLanguage(language: string | undefined): string | undefined {
  const normalized = language?.trim().split(/\s+/)[0]?.toLowerCase()
  return normalized || undefined
}

function looksLikeMermaid(code: string): boolean {
  const firstMeaningfulLine = code
    .split('\n')
    .map((line) => line.trim())
    .find(Boolean)
  return firstMeaningfulLine ? MERMAID_DIAGRAM_START.test(firstMeaningfulLine) : false
}

function shouldRenderAsMermaid(block: CodeBlock): boolean {
  const normalizedLanguage = normalizeCodeLanguage(block.language)
  if (normalizedLanguage === MERMAID_LANGUAGE) {
    return true
  }
  if (!PLAINTEXT_LANGUAGES.has(normalizedLanguage ?? '')) {
    return false
  }
  return looksLikeMermaid(block.code)
}

function findUnescapedDelimiter(text: string, delimiter: string, fromIndex: number): number {
  let index = text.indexOf(delimiter, fromIndex)
  while (index !== -1) {
    let backslashCount = 0
    for (let i = index - 1; i >= 0 && text[i] === '\\'; i--) {
      backslashCount += 1
    }
    if (backslashCount % 2 === 0) return index
    index = text.indexOf(delimiter, index + delimiter.length)
  }
  return -1
}

function consumeMath(
  content: string,
  mathBlocks: MathBlock[],
  start: number,
  open: string,
  close: string,
  displayMode: boolean,
): { replacement: string; end: number } | null {
  const contentStart = start + open.length
  const end = findUnescapedDelimiter(content, close, contentStart)
  if (end === -1) return null

  const tex = content.slice(contentStart, end)
  if (!tex.trim()) return null
  if (!displayMode && /[\n\r]/.test(tex)) return null
  if (open === '$' && (/\s/.test(content[contentStart] ?? '') || /\s/.test(content[end - 1] ?? ''))) {
    return null
  }

  const id = `math-${mathBlocks.length}`
  mathBlocks.push({ id, tex, displayMode })
  const tag = displayMode ? 'div' : 'span'
  const spacing = displayMode ? '\n\n' : ''
  return {
    replacement: `${spacing}<${tag} data-math-id="${id}"></${tag}>${spacing}`,
    end: end + close.length,
  }
}

function extractMathFromSegment(segment: string, mathBlocks: MathBlock[]): string {
  let output = ''
  let index = 0

  while (index < segment.length) {
    if (segment[index] === '`') {
      const match = /^`+/.exec(segment.slice(index))
      const ticks = match?.[0] ?? '`'
      const end = segment.indexOf(ticks, index + ticks.length)
      if (end !== -1) {
        output += segment.slice(index, end + ticks.length)
        index = end + ticks.length
        continue
      }
    }

    const displayDollar = segment.startsWith('$$', index)
      ? consumeMath(segment, mathBlocks, index, '$$', '$$', true)
      : null
    if (displayDollar) {
      output += displayDollar.replacement
      index = displayDollar.end
      continue
    }

    const displayBracket = segment.startsWith('\\[', index)
      ? consumeMath(segment, mathBlocks, index, '\\[', '\\]', true)
      : null
    if (displayBracket) {
      output += displayBracket.replacement
      index = displayBracket.end
      continue
    }

    const inlineParen = segment.startsWith('\\(', index)
      ? consumeMath(segment, mathBlocks, index, '\\(', '\\)', false)
      : null
    if (inlineParen) {
      output += inlineParen.replacement
      index = inlineParen.end
      continue
    }

    const inlineDollar = segment[index] === '$' && segment[index + 1] !== '$'
      ? consumeMath(segment, mathBlocks, index, '$', '$', false)
      : null
    if (inlineDollar) {
      output += inlineDollar.replacement
      index = inlineDollar.end
      continue
    }

    output += segment[index]
    index += 1
  }

  return output
}

function extractMath(content: string): { markdown: string; mathBlocks: MathBlock[] } {
  const mathBlocks: MathBlock[] = []
  const lines = content.match(/[^\n]*\n|[^\n]+/g) ?? ['']
  let output = ''
  let pendingMarkdown = ''
  let inFence: string | null = null

  const flushPendingMarkdown = () => {
    if (!pendingMarkdown) return
    output += extractMathFromSegment(pendingMarkdown, mathBlocks)
    pendingMarkdown = ''
  }

  for (const line of lines) {
    const fenceMatch = CODE_FENCE_START.exec(line)
    if (fenceMatch) {
      const marker = fenceMatch[1]!.charAt(0)
      if (!inFence) {
        flushPendingMarkdown()
        inFence = marker
      } else if (inFence === marker) {
        inFence = null
      }
      output += line
      continue
    }

    if (inFence) {
      output += line
    } else {
      pendingMarkdown += line
    }
  }

  flushPendingMarkdown()

  return { markdown: output, mathBlocks }
}

function renderMath(block: MathBlock): string {
  const cacheKey = `${block.displayMode ? 'block' : 'inline'}\0${block.tex}`
  const cached = mathRenderCache.get(cacheKey)
  if (cached) return cached

  try {
    const rendered = katex.renderToString(block.tex, {
      displayMode: block.displayMode,
      output: 'html',
      throwOnError: false,
      strict: false,
      trust: false,
    })
    mathRenderCache.set(cacheKey, rendered)
    if (mathRenderCache.size > MATH_RENDER_CACHE_LIMIT) {
      const firstKey = mathRenderCache.keys().next().value
      if (firstKey) mathRenderCache.delete(firstKey)
    }
    return rendered
  } catch {
    return DOMPurify.sanitize(block.tex)
  }
}

function enhanceMarkdownHtml(html: string, mathBlocks: MathBlock[]): string {
  const cleanHtml = DOMPurify.sanitize(html, {
    ADD_TAGS: ['use'],
    ADD_ATTR: ['xlink:href'],
  })

  const needsDomEnhancement = mathBlocks.length > 0 || /<(a|table)\b/i.test(cleanHtml)
  if (!needsDomEnhancement) {
    return cleanHtml
  }

  if (typeof document === 'undefined') {
    return cleanHtml
  }

  const container = document.createElement('div')
  container.innerHTML = cleanHtml
  const mathById = new Map(mathBlocks.map((block) => [block.id, block]))

  container.querySelectorAll<HTMLElement>('[data-math-id]').forEach((placeholder) => {
    const block = mathById.get(placeholder.dataset.mathId ?? '')
    if (!block) return

    const rendered = document.createElement(block.displayMode ? 'div' : 'span')
    rendered.className = block.displayMode ? 'md-math-display' : 'md-math-inline'
    rendered.innerHTML = renderMath(block)
    placeholder.replaceWith(rendered)
  })

  container.querySelectorAll('table').forEach((table) => {
    if (table.parentElement?.classList.contains('md-table-wrap')) return
    const wrapper = document.createElement('div')
    wrapper.className = 'md-table-wrap'
    table.parentNode?.insertBefore(wrapper, table)
    wrapper.appendChild(table)
  })

  container.querySelectorAll('a[href]').forEach((link) => {
    link.setAttribute('target', '_blank')
    link.setAttribute('rel', 'noreferrer noopener')
  })

  return container.innerHTML
}

// ── marked renderer + code block extraction ───────────────────────────────────
const renderer = new marked.Renderer()

let pendingCodeBlocks: CodeBlock[] = []

renderer.code = function ({ text, lang }: Tokens.Code) {
  const id = `cb-${pendingCodeBlocks.length}`
  pendingCodeBlocks.push({
    id,
    code: text,
    language: normalizeCodeLanguage(lang || undefined),
  })
  return `<div data-codeblock-id="${id}"></div>`
}

marked.setOptions({
  breaks: true,
  gfm: true,
})
marked.use({ renderer })

// ── Parse ─────────────────────────────────────────────────────────────────────
function parseMarkdown(content: string): { html: string; codeBlocks: CodeBlock[]; mathBlocks: MathBlock[] } {
  pendingCodeBlocks = []
  const { markdown, mathBlocks } = extractMath(content)
  const html = marked.parse(markdown) as string
  const codeBlocks = [...pendingCodeBlocks]
  pendingCodeBlocks = []
  return { html, codeBlocks, mathBlocks }
}

type MarkdownParseResult = ReturnType<typeof parseMarkdown>

// ── Cache ─────────────────────────────────────────────────────────────────────
interface CacheEntry {
  parsed: MarkdownParseResult
  chars: number
}

const finalizedMarkdownCache = new Map<string, CacheEntry>()
const streamingMarkdownCache = new Map<string, CacheEntry>()
let finalizedMarkdownCacheChars = 0

function fnv1aHash(value: string): number {
  let hash = 2166136261 >>> 0
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

function buildMarkdownCacheKey(content: string): string {
  return `${content.length}:${fnv1aHash(content).toString(36)}`
}

function evictFinalizedMarkdownEntries(): void {
  while (
    finalizedMarkdownCache.size > FINALIZED_CACHE_MAX_ENTRIES ||
    finalizedMarkdownCacheChars > FINALIZED_CACHE_MAX_CHARS
  ) {
    const oldestKey = finalizedMarkdownCache.keys().next().value
    if (typeof oldestKey !== 'string') break
    const entry = finalizedMarkdownCache.get(oldestKey)
    finalizedMarkdownCache.delete(oldestKey)
    if (entry) finalizedMarkdownCacheChars -= entry.chars
  }
}

function evictStreamingMarkdownEntries(): void {
  while (streamingMarkdownCache.size > STREAMING_CACHE_MAX_ENTRIES) {
    const oldestKey = streamingMarkdownCache.keys().next().value
    if (typeof oldestKey !== 'string') break
    streamingMarkdownCache.delete(oldestKey)
  }
}

function getCachedMarkdownParse(content: string, streaming: boolean): MarkdownParseResult {
  const cache = streaming ? streamingMarkdownCache : finalizedMarkdownCache
  const key = buildMarkdownCacheKey(content)
  const cached = cache.get(key)
  if (cached) {
    cache.delete(key)
    cache.set(key, cached)
    return cached.parsed
  }

  const parsed = parseMarkdown(content)
  const entry: CacheEntry = { parsed, chars: content.length }
  cache.set(key, entry)

  if (streaming) {
    evictStreamingMarkdownEntries()
  } else {
    finalizedMarkdownCacheChars += content.length
    evictFinalizedMarkdownEntries()
  }

  return parsed
}

// Exposed for testing / diagnostics (matches React's `__markdownParseCacheInternals`)
const __markdownParseCacheInternals = {
  finalizedSize: () => finalizedMarkdownCache.size,
  streamingSize: () => streamingMarkdownCache.size,
  finalizedChars: () => finalizedMarkdownCacheChars,
  hasFinalized: (content: string) => finalizedMarkdownCache.has(buildMarkdownCacheKey(content)),
  hasStreaming: (content: string) => streamingMarkdownCache.has(buildMarkdownCacheKey(content)),
  reset: () => {
    finalizedMarkdownCache.clear()
    streamingMarkdownCache.clear()
    finalizedMarkdownCacheChars = 0
  },
}

// ── Prose Tailwind classes ────────────────────────────────────────────────────
const BASE_PROSE_CLASSES = `markdown-prose prose prose-sm min-w-0 max-w-none break-words [overflow-wrap:anywhere] text-[var(--color-text-primary)]
  prose-headings:text-[var(--color-text-primary)] prose-headings:font-semibold
  prose-p:my-2 prose-p:leading-relaxed
  prose-p:break-words prose-p:[overflow-wrap:anywhere]
  prose-code:text-[13px] prose-code:text-[var(--color-code-fg)] prose-code:font-[var(--font-mono)] prose-code:bg-[var(--color-code-bg)] prose-code:border prose-code:border-[var(--color-border)] prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:before:hidden prose-code:after:hidden
  prose-pre:!bg-transparent prose-pre:!p-0 prose-pre:!shadow-none
  prose-a:text-[var(--color-text-accent)] prose-a:no-underline prose-a:[overflow-wrap:anywhere] hover:prose-a:underline
  prose-strong:text-[var(--color-text-primary)]
  prose-ul:my-2 prose-ol:my-2 prose-ul:pl-5 prose-ol:pl-5 prose-ul:list-outside prose-ol:list-outside
  prose-li:my-0.5
  prose-table:my-0 prose-table:w-full prose-table:table-auto prose-table:text-sm
  prose-th:bg-[var(--color-surface-info)] prose-th:px-3 prose-th:py-2 prose-th:text-left prose-th:whitespace-normal prose-th:break-words prose-th:align-top prose-th:border-b prose-th:border-[var(--color-border)]
  prose-td:px-3 prose-td:py-2 prose-td:border-b prose-td:border-[var(--color-border)] prose-td:whitespace-normal prose-td:break-words prose-td:align-top prose-td:bg-[var(--color-surface)]
  [&_.katex]:[white-space:nowrap] [&_.katex]:[overflow-wrap:normal] [&_.katex]:[word-break:normal]
  [&_.md-math-inline]:inline-flex [&_.md-math-inline]:max-w-full [&_.md-math-inline]:overflow-x-auto [&_.md-math-inline]:[vertical-align:-0.08em] [&_.md-math-inline_.katex]:text-[1.02em]
  [&_.md-math-display]:my-5 [&_.md-math-display]:flex [&_.md-math-display]:max-w-full [&_.md-math-display]:justify-center [&_.md-math-display]:overflow-x-auto [&_.md-math-display]:px-1 [&_.md-math-display]:py-2 [&_.md-math-display]:[scrollbar-width:thin]
  [&_.md-math-display_.katex-display]:m-0 [&_.md-math-display_.katex]:text-[1.14em] [&_.md-math-display_.katex-html]:min-w-max
  [&_.md-table-wrap]:my-5 [&_.md-table-wrap]:overflow-x-auto [&_.md-table-wrap]:rounded-xl [&_.md-table-wrap]:border [&_.md-table-wrap]:border-[var(--color-border)] [&_.md-table-wrap]:bg-[var(--color-surface-container-lowest)]`

const DOCUMENT_PROSE_CLASSES = `
  prose-p:text-[15px] prose-p:leading-7
  prose-headings:scroll-mt-6 prose-headings:tracking-[-0.01em]
  prose-h1:mb-4 prose-h1:text-2xl prose-h1:font-semibold prose-h1:leading-tight
  prose-h2:mt-8 prose-h2:mb-3 prose-h2:border-b prose-h2:border-[var(--color-border)] prose-h2:pb-2 prose-h2:text-xl prose-h2:font-semibold
  prose-h3:mt-6 prose-h3:mb-2 prose-h3:text-base prose-h3:font-semibold
  prose-h4:mt-5 prose-h4:mb-2 prose-h4:text-sm prose-h4:font-semibold
  prose-blockquote:my-4 prose-blockquote:rounded-r-lg prose-blockquote:border-l-4 prose-blockquote:border-[var(--color-outline-variant)] prose-blockquote:bg-[var(--color-surface-container-low)] prose-blockquote:px-4 prose-blockquote:py-2 prose-blockquote:italic
  prose-hr:my-6 prose-hr:border-[var(--color-border)]
  prose-img:rounded-lg prose-img:border prose-img:border-[var(--color-border)]
  prose-kbd:rounded prose-kbd:border prose-kbd:border-[var(--color-border)] prose-kbd:bg-[var(--color-surface-container-lowest)] prose-kbd:px-1.5 prose-kbd:py-0.5 prose-kbd:font-[var(--font-mono)] prose-kbd:text-[12px] prose-kbd:font-normal prose-kbd:text-[var(--color-text-secondary)] prose-kbd:shadow-none
  prose-ul:pl-5 prose-ul:[&>li]:marker:text-[var(--color-text-tertiary)]
  prose-ol:pl-5 prose-ol:[&>li]:marker:text-[var(--color-text-tertiary)]
  prose-li:my-1.5
  prose-table:my-0
  [&_.md-math-display]:my-6 [&_.md-math-display_.katex]:text-[1.18em]`

const COMPACT_PROSE_CLASSES = `
  prose-p:my-1 prose-p:text-xs prose-p:leading-5 prose-p:text-[var(--color-text-secondary)]
  prose-headings:mt-2 prose-headings:mb-1 prose-headings:leading-snug
  prose-h1:text-base prose-h2:text-sm prose-h3:text-xs prose-h4:text-xs
  prose-blockquote:my-2 prose-blockquote:border-l-2 prose-blockquote:border-[var(--color-outline-variant)] prose-blockquote:pl-3 prose-blockquote:text-[var(--color-text-secondary)]
  prose-code:text-[12px]
  prose-ul:my-1 prose-ol:my-1 prose-ul:pl-4 prose-ol:pl-4
  prose-li:my-0.5 prose-li:text-xs prose-li:leading-5 prose-li:text-[var(--color-text-secondary)]
  prose-table:text-xs
  [&_.md-math-display]:my-2 [&_.md-math-display]:py-1 [&_.md-math-display_.katex]:text-[1.04em]
  [&_.md-table-wrap]:my-2`

function getProseClasses(variant: 'default' | 'document' | 'compact', cls?: string): string {
  return [
    BASE_PROSE_CLASSES,
    variant === 'document' ? DOCUMENT_PROSE_CLASSES : '',
    variant === 'compact' ? COMPACT_PROSE_CLASSES : '',
    cls ?? '',
  ]
    .filter(Boolean)
    .join(' ')
}

// ── Clipboard helper (verbatim from React clipboard.ts) ───────────────────────
async function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // Fall through to legacy copy path.
  }

  try {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', 'true')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    const copied = document.execCommand('copy')
    document.body.removeChild(textarea)
    return copied
  } catch {
    return false
  }
}

// ── Streaming placeholder (local renderless component, available in template) ─
const MermaidStreamingPlaceholder = defineComponent({
  name: 'MermaidStreamingPlaceholder',
  setup() {
    return () => h(
      'div',
      {
        'data-testid': 'mermaid-streaming-placeholder',
        class:
          'my-4 flex items-center justify-center rounded-[var(--radius-lg)] border border-[var(--color-border)]/50 bg-[var(--color-surface-container-low)] py-8',
      },
      h(
        'div',
        { class: 'flex items-center gap-2 text-[11px] text-[var(--color-text-tertiary)]' },
        [
          h('span', { class: 'material-symbols-outlined animate-spin text-[16px]' }, 'progress_activity'),
          'Generating diagram...',
        ],
      ),
    )
  },
})

// ── Computed state ────────────────────────────────────────────────────────────
// While streaming, throttle content updates to one re-parse per animation
// frame. Tokens arrive faster than the screen refreshes; without this every
// token triggers a full marked re-parse + re-render, which flickers code
// blocks and tables. The frame-aligned ref coalesces a burst of tokens into
// a single render. When not streaming, render the final content immediately.
//
// For long documents we escalate the throttle and optionally collapse the
// visible slice so a 200KB reply does not re-parse the whole tree every frame.
const LONG_STREAM_CHARS = 24_000
const LONG_COLLAPSE_CHARS = 80_000
const LONG_STREAM_MIN_INTERVAL_MS = 120
const LONG_STREAM_MIN_DELTA = 96

const frameContent = ref(props.content)
const longDocExpanded = ref(false)
let rafId: number | null = null
let throttleTimer: ReturnType<typeof setTimeout> | null = null
let lastFlushAt = 0
let lastFlushedLen = props.content.length

function flushFrameContent() {
  frameContent.value = props.content
  lastFlushAt = Date.now()
  lastFlushedLen = props.content.length
}

function clearSchedule() {
  if (rafId !== null) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
  if (throttleTimer !== null) {
    clearTimeout(throttleTimer)
    throttleTimer = null
  }
}

function scheduleFrame() {
  if (!props.streaming) return
  const len = props.content.length
  const isLong = len >= LONG_STREAM_CHARS
  if (isLong) {
    // Skip tiny token-by-token flushes on large docs.
    const delta = len - lastFlushedLen
    const elapsed = Date.now() - lastFlushAt
    if (delta < LONG_STREAM_MIN_DELTA && elapsed < LONG_STREAM_MIN_INTERVAL_MS) {
      if (throttleTimer === null) {
        throttleTimer = setTimeout(() => {
          throttleTimer = null
          flushFrameContent()
        }, LONG_STREAM_MIN_INTERVAL_MS - elapsed)
      }
      return
    }
    if (throttleTimer === null && elapsed < LONG_STREAM_MIN_INTERVAL_MS) {
      throttleTimer = setTimeout(() => {
        throttleTimer = null
        flushFrameContent()
      }, LONG_STREAM_MIN_INTERVAL_MS - elapsed)
      return
    }
    flushFrameContent()
    return
  }
  if (rafId !== null) return
  rafId = requestAnimationFrame(() => {
    rafId = null
    flushFrameContent()
  })
}
watch(() => props.content, () => {
  if (props.streaming) {
    scheduleFrame()
  } else {
    // Non-streaming (final): update immediately so the finished render is exact.
    clearSchedule()
    flushFrameContent()
    // Reset collapse when content is replaced with a new short message.
    if (props.content.length < LONG_COLLAPSE_CHARS) longDocExpanded.value = false
  }
})
watch(() => props.streaming, (s) => {
  if (!s) {
    clearSchedule()
    flushFrameContent()
  }
})
onBeforeUnmount(() => { clearSchedule() })

const rawParseTarget = computed(() => props.streaming ? frameContent.value : props.content)

/** Collapsed slice for huge finalized messages (user can expand). */
const isLongCollapsed = computed(
  () =>
    !props.streaming
    && !longDocExpanded.value
    && rawParseTarget.value.length > LONG_COLLAPSE_CHARS,
)

const parseTarget = computed(() => {
  const full = rawParseTarget.value
  if (!isLongCollapsed.value) return full
  // Cut at a line boundary near the limit so we don't mid-fence a code block.
  const slice = full.slice(0, LONG_COLLAPSE_CHARS)
  const lastNl = slice.lastIndexOf('\n')
  return lastNl > LONG_COLLAPSE_CHARS * 0.6 ? slice.slice(0, lastNl) : slice
})

const parsed = computed(() =>
  props.cache ? getCachedMarkdownParse(parseTarget.value, props.streaming) : parseMarkdown(parseTarget.value),
)

function expandLongDoc() {
  longDocExpanded.value = true
}

const proseClasses = computed(() => getProseClasses(props.variant, props.class))

const parts = computed<MarkdownPart[]>(() => {
  const { html, codeBlocks, mathBlocks } = parsed.value
  if (codeBlocks.length === 0) {
    return [{ type: 'html' as const, content: enhanceMarkdownHtml(html, mathBlocks) }]
  }

  const result: MarkdownPart[] = []
  let remaining = html

  for (const block of codeBlocks) {
    const marker = `<div data-codeblock-id="${block.id}"></div>`
    const idx = remaining.indexOf(marker)
    if (idx === -1) continue

    const before = remaining.slice(0, idx)
    if (before) {
      result.push({ type: 'html', content: enhanceMarkdownHtml(before, mathBlocks) })
    }
    result.push({ type: 'code', block })
    remaining = remaining.slice(idx + marker.length)
  }

  if (remaining) {
    result.push({ type: 'html', content: enhanceMarkdownHtml(remaining, mathBlocks) })
  }

  return result
})

// ── Click handler (copy-code button + link-click callback) ────────────────────
function handleClick(event: MouseEvent): void {
  const target = event.target as HTMLElement | null
  const button = target?.closest<HTMLButtonElement>('[data-copy-code]')
  if (!button) {
    const link = target?.closest<HTMLAnchorElement>('a[href]')
    if (!link || !props.onLinkClick) return

    const href = link.getAttribute('href') ?? ''
    const handled = props.onLinkClick(href, event)
    if (handled) {
      event.preventDefault()
      event.stopPropagation()
    }
    return
  }

  const text = button.getAttribute('data-copy-code')
  if (!text) return

  ;(async () => {
    const copied = await copyTextToClipboard(text)
    if (!copied) return
    const original = button.textContent
    button.textContent = 'Copied'
    setTimeout(() => {
      button.textContent = original
    }, 1500)
  })()
}
</script>

<template>
  <div class="md-root">
    <div
      v-if="parts.length === 1 && parts[0].type === 'html'"
      :class="proseClasses"
      v-html="parts[0].content"
      @click="handleClick"
    />
    <div
      v-else
      :class="proseClasses"
      @click="handleClick"
    >
      <template v-for="(part, i) in parts" :key="i">
        <div
          v-if="part.type === 'html'"
          v-html="part.content"
        />
        <MermaidStreamingPlaceholder
          v-else-if="shouldRenderAsMermaid(part.block) && props.streaming"
        />
        <MermaidRenderer
          v-else-if="shouldRenderAsMermaid(part.block)"
          :code="part.block.code"
        />
        <div v-else class="my-4">
          <!-- v3.7.7 — collapse code aggressively by default (5 lines
               + ellipsis + expand button). Showing the full code up
               front makes programming-task replies feel walls-of-text;
               the user can click to expand when they care. -->
          <CodeViewer :code="part.block.code" :language="part.block.language" :max-lines="5" />
        </div>
      </template>
    </div>
    <button
      v-if="isLongCollapsed"
      type="button"
      class="md-expand-long"
      @click="expandLongDoc"
    >
      Show full message ({{ Math.round(rawParseTarget.length / 1000) }}k chars)
    </button>
  </div>
</template>

<style scoped>
.md-expand-long {
  margin-top: 0.75rem;
  display: inline-flex;
  align-items: center;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: var(--color-surface-container-low);
  padding: 0.4rem 0.75rem;
  font-size: 12px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}
.md-expand-long:hover {
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
}
</style>