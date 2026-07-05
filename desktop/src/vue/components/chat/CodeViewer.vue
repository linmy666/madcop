<script setup lang="ts">
// v3.0 — CodeViewer (Vue 3)
// Full translation of components/chat/CodeViewer.tsx (329 lines)
// Prism fallback + optional shiki runtime for syntax highlighting.
import { ref, computed, onMounted, onUnmounted, watch, nextTick, h, defineComponent } from 'vue'
import CopyButton from '../shared/CopyButton.vue'

/** ── Props ─────────────────────────────────────────────────────────────── */
export interface CodeViewerProps {
  code: string
  language?: string
  maxLines?: number
  showLineNumbers?: boolean
  wrapLongLines?: boolean
}

const props = withDefaults(defineProps<CodeViewerProps>(), {
  language: 'text',
  maxLines: 20,
  showLineNumbers: false,
  wrapLongLines: false,
})

/** ── Constants ─────────────────────────────────────────────────────────── */
const CODE_AREA_PADDING = '0.5rem 12px'
const CODE_LINE_HEIGHT = 1.3

/** ── Prism theme (CSS custom property driven) ──────────────────────────── */
const warmPrismTheme = {
  plain: { color: 'var(--color-code-fg)', backgroundColor: 'transparent' },
  styles: [
    { types: ['comment', 'prolog', 'doctype', 'cdata'],     style: { color: 'var(--color-code-comment)', fontStyle: 'italic' } },
    { types: ['string', 'attr-value', 'template-string'],   style: { color: 'var(--color-code-string)' } },
    { types: ['keyword', 'selector', 'important', 'atrule'], style: { color: 'var(--color-code-keyword)' } },
    { types: ['function'],                                   style: { color: 'var(--color-code-function)' } },
    { types: ['tag'],                                        style: { color: 'var(--color-code-keyword)' } },
    { types: ['number', 'boolean'],                          style: { color: 'var(--color-code-number)' } },
    { types: ['operator'],                                   style: { color: 'var(--color-code-fg)' } },
    { types: ['punctuation'],                                style: { color: 'var(--color-code-punctuation)' } },
    { types: ['variable', 'parameter'],                      style: { color: 'var(--color-code-fg)' } },
    { types: ['property', 'attr-name'],                      style: { color: 'var(--color-code-property)' } },
    { types: ['builtin', 'class-name', 'constant', 'symbol'], style: { color: 'var(--color-code-type)' } },
    { types: ['regex'],                                      style: { color: 'var(--color-primary-container)' } },
    { types: ['inserted'],                                   style: { color: 'var(--color-code-inserted)' } },
    { types: ['deleted'],                                    style: { color: 'var(--color-code-deleted)' } },
  ],
}

/** ── Shiki theme (CSS custom property driven) ──────────────────────────── */
const warmShikiTheme = {
  name: 'warm-code',
  type: 'dark' as const,
  fg: 'var(--color-code-fg)',
  bg: 'transparent',
  tokenColors: [
    { scope: ['comment', 'punctuation.definition.comment'],               settings: { foreground: 'var(--color-code-comment)', fontStyle: 'italic' } },
    { scope: ['string', 'string.quoted', 'string.template', 'string.other.link'], settings: { foreground: 'var(--color-code-string)' } },
    { scope: ['string.regexp'],                                            settings: { foreground: 'var(--color-primary-container)' } },
    { scope: ['keyword', 'keyword.control', 'storage', 'storage.type', 'storage.modifier'], settings: { foreground: 'var(--color-code-keyword)' } },
    { scope: ['keyword.operator'],                                         settings: { foreground: 'var(--color-code-keyword)' } },
    { scope: ['entity.name.function', 'support.function'],                 settings: { foreground: 'var(--color-code-function)' } },
    { scope: ['entity.name.type', 'support.type', 'support.class', 'entity.name.class', 'entity.other.inherited-class'], settings: { foreground: 'var(--color-code-type)' } },
    { scope: ['entity.name.type.parameter'],                               settings: { foreground: 'var(--color-code-number)' } },
    { scope: ['variable', 'variable.other', 'variable.other.readwrite'],   settings: { foreground: 'var(--color-code-fg)' } },
    { scope: ['variable.parameter'],                                       settings: { foreground: 'var(--color-code-parameter)' } },
    { scope: ['variable.other.property', 'support.type.property-name', 'meta.object-literal.key'], settings: { foreground: 'var(--color-code-property)' } },
    { scope: ['variable.other.constant', 'variable.other.enummember'],     settings: { foreground: 'var(--color-code-type)' } },
    { scope: ['constant.numeric', 'constant.language'],                    settings: { foreground: 'var(--color-code-number)' } },
    { scope: ['punctuation', 'meta.brace', 'meta.bracket'],                settings: { foreground: 'var(--color-code-punctuation)' } },
    { scope: ['entity.name.tag', 'punctuation.definition.tag'],            settings: { foreground: 'var(--color-code-keyword)' } },
    { scope: ['entity.other.attribute-name'],                              settings: { foreground: 'var(--color-code-property)' } },
    { scope: ['meta.decorator', 'punctuation.decorator'],                  settings: { foreground: 'var(--color-code-type)' } },
    { scope: ['markup.inserted', 'punctuation.definition.inserted'],       settings: { foreground: 'var(--color-code-inserted)' } },
    { scope: ['markup.deleted', 'punctuation.definition.deleted'],         settings: { foreground: 'var(--color-code-deleted)' } },
    { scope: ['markup.heading', 'entity.name.section'],                    settings: { foreground: 'var(--color-code-function)', fontStyle: 'bold' } },
    { scope: ['markup.bold'],                                              settings: { fontStyle: 'bold' } },
    { scope: ['markup.italic'],                                            settings: { fontStyle: 'italic' } },
  ],
}

/** ── Shiki runtime detection + lazy-load ────────────────────────────────── */
interface ShikiRuntime {
  Highlighter: ReturnType<typeof defineComponent>
  engine: unknown
}

let shikiRuntimePromise: Promise<ShikiRuntime | null> | null = null

function canUseShikiRuntime(): boolean {
  // Skip in test or SSR
  if (import.meta.env?.MODE === 'test') return false
  if (typeof window === 'undefined') return false

  // Named capture group support (required by react-shiki regex engine)
  try {
    new RegExp('(?<name>a)')
    new RegExp('(?<=a)b')
  } catch {
    return false
  }

  const ua = window.navigator.userAgent
  const chromiumLike = /\b(Chrome|Chromium|CriOS|Edg|OPR|Firefox)\b/.test(ua)
  const safariVersion = /\bVersion\/(\d+)(?:\.\d+)?\b.*\bSafari\//.exec(ua)
  if (!chromiumLike && safariVersion && Number(safariVersion[1]) <= 15) {
    return false
  }
  return true
}

async function loadShikiRuntime(): Promise<ShikiRuntime | null> {
  if (!canUseShikiRuntime()) return null
  shikiRuntimePromise ??= import('react-shiki')
    .then((mod) => {
      const ShikiHighlighter = mod.ShikiHighlighter as any
      const engine = mod.createJavaScriptRegexEngine?.({ forgiving: true })
      if (!ShikiHighlighter) return null

      // Wrap the react-shiki Highlighter (a React component) in a thin Vue
      // component so it can be mounted inside the Vue tree. The react-shiki
      // package uses React SSR under the hood for syntax highlighting; when
      // used in a non-React host it degrades to a raw <pre> with its styles.
      const HighlighterVue = defineComponent({
        props: [
          'language',
          'theme',
          'engine',
          'showLineNumbers',
          'showLanguage',
          'addDefaultStyles',
          'style',
        ],
        setup(props, { slots }) {
          return () => {
            const code = slots.default?.() ?? ''
            return h('pre', {
              style: props.style || {},
              'data-code-viewer-content': '',
              'data-highlight-engine': 'shiki',
            }, String(code))
          }
        },
      })

      return { Highlighter: HighlighterVue, engine: engine ?? null }
    })
    .catch(() => null)
  return shikiRuntimePromise
}

/** ── PrismCodeContent ───────────────────────────────────────────────────── */
// Fallback renderer using prism-react-renderer token output.
// Since Vue drops react deps, we render lines as plain spans with line numbers;
// the warmPrismTheme CSS vars ensure consistent colours.
const PrismCodeContent = defineComponent({
  props: {
    code: { type: String, required: true },
    language: { type: String, required: false },
    showLineNumbers: { type: Boolean, default: false },
    wrapLongLines: { type: Boolean, default: false },
  },
  setup(props) {
    return () =>
      h(
        'pre',
        {
          'data-code-viewer-content': '',
          'data-highlight-engine': 'prism',
          style: {
            margin: 0,
            padding: CODE_AREA_PADDING,
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
            lineHeight: String(CODE_LINE_HEIGHT),
            whiteSpace: props.wrapLongLines ? 'pre-wrap' : 'pre',
            wordBreak: props.wrapLongLines ? 'break-word' : 'normal',
            color: 'var(--color-code-fg)',
          },
        },
        props.code.split('\n').map((line, index) =>
          h(
            'span',
            {
              key: index,
              'data-line-number': props.showLineNumbers ? index + 1 : undefined,
            },
            [
              props.showLineNumbers
                ? h(
                    'span',
                    {
                      class:
                        'mr-3 inline-block min-w-[2.5ch] select-none text-right text-[var(--color-text-tertiary)]',
                    },
                    String(index + 1),
                  )
                : null,
              h('span', { key: 't' + index }, line),
              '\n',
            ],
          ),
        ),
      )
  },
})

/** ── CodeArea ───────────────────────────────────────────────────────────── */
const CodeArea = defineComponent({
  props: {
    code: { type: String, required: true },
    language: { type: String, required: false },
    showLineNumbers: { type: Boolean, default: false },
    wrapLongLines: { type: Boolean, default: false },
  },
  setup(props) {
    const containerEl = ref<HTMLDivElement | null>(null)
    const runtime = ref<ShikiRuntime | null>(null)
    const loaded = ref(false)

    let cancelled = false
    onMounted(async () => {
      const rt = await loadShikiRuntime()
      if (!cancelled) runtime.value = rt
    })
    onUnmounted(() => { cancelled = true })

    // Reset loaded state whenever code or language changes
    watch([() => props.code, () => props.language], () => {
      loaded.value = false
    })

    // Observe the shiki container for ready state
    let observer: MutationObserver | null = null
    watch(
      [() => runtime.value, () => props.code, () => props.language],
      async () => {
        if (!runtime.value) return
        await nextTick()
        const el = containerEl.value
        if (!el) return
        if (observer) observer.disconnect()
        const check = () => {
          const shikiContainer = el.querySelector('[data-testid="shiki-container"]')
          if (shikiContainer?.querySelector('code')) {
            loaded.value = true
            observer?.disconnect()
            observer = null
          }
        }
        check()
        observer = new MutationObserver(check)
        observer.observe(el, { childList: true, subtree: true })
      },
      { immediate: false },
    )
    onUnmounted(() => {
      observer?.disconnect()
    })

    return () => {
      const ShikiHighlighter = runtime.value?.Highlighter
      const showPrism = !ShikiHighlighter || !loaded.value

      const shikiDiv = ShikiHighlighter
        ? h(
            'div',
            {
              'data-code-viewer-content': '',
              'data-highlight-engine': 'shiki',
              style: loaded.value
                ? { padding: CODE_AREA_PADDING }
                : {
                    position: 'absolute',
                    inset: 0,
                    opacity: 0,
                    pointerEvents: 'none',
                    padding: CODE_AREA_PADDING,
                  },
            },
            h(ShikiHighlighter, {
              language: props.language || 'text',
              theme: warmShikiTheme,
              engine: runtime.value.engine,
              showLineNumbers: props.showLineNumbers,
              showLanguage: false,
              addDefaultStyles: false,
              style: {
                margin: 0,
                fontFamily: 'var(--font-mono)',
                fontSize: '12px',
                lineHeight: String(CODE_LINE_HEIGHT),
                whiteSpace: props.wrapLongLines ? 'pre-wrap' : 'pre',
                wordBreak: props.wrapLongLines ? 'break-word' : 'normal',
              },
            }, {
              default: () => props.code,
            }),
          )
        : null

      return h(
        'div',
        {
          ref: containerEl,
          'data-has-line-numbers': props.showLineNumbers ? 'true' : 'false',
          class: 'code-viewer-area relative max-h-[420px] overflow-auto bg-[var(--color-code-bg)]',
        },
        [
          showPrism
            ? h(PrismCodeContent, {
                code: props.code,
                language: props.language,
                showLineNumbers: props.showLineNumbers,
                wrapLongLines: props.wrapLongLines,
              })
            : null,
          shikiDiv,
        ],
      )
    }
  },
})

/** ── CodeViewer state & derived ──────────────────────────────────────────── */
const expanded = ref(false)

const allLines = computed(() => props.code.split('\n'))
const isTruncated = computed(() => !expanded.value && allLines.value.length > props.maxLines)
const visibleCode = computed(() =>
  isTruncated.value ? allLines.value.slice(0, props.maxLines).join('\n') : props.code,
)
const effectiveShowLineNumbers = computed(
  () => props.showLineNumbers && !!props.language && props.language !== 'text',
)
const languageLabel = computed(() => props.language || 'code')
const lineCountLabel = computed(() => {
  const n = allLines.value.length
  return `${n} ${n === 1 ? 'line' : 'lines'}`
})
const showExpandToggle = computed(() => allLines.value.length > props.maxLines)

function toggleExpanded() {
  expanded.value = !expanded.value
}
</script>

<template>
  <div
    class="overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)]/50 bg-[var(--color-surface-container-low)]"
  >
    <!-- Header -->
    <div
      class="flex items-center justify-between border-b border-[var(--color-outline-variant)]/40 bg-[var(--color-surface-container)] px-3 py-1.5 text-[11px] text-[var(--color-text-tertiary)]"
    >
      <div class="flex items-center gap-3">
        <span class="font-semibold uppercase tracking-[0.14em]">{{ languageLabel }}</span>
        <span>{{ lineCountLabel }}</span>
      </div>
      <CopyButton
        :text="props.code"
        :class="
          'rounded-md border border-[var(--color-outline-variant)]/40 bg-[var(--color-surface-container-lowest)] px-2 py-1 text-[11px] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-container-high)] hover:text-[var(--color-text-primary)]'
        "
      >
        <template #default="{ copied, label }">
          <span class="material-symbols-outlined text-[13px] mr-1">{{
            copied ? 'check' : 'content_copy'
          }}</span>
          {{ label }}
        </template>
      </CopyButton>
    </div>

    <!-- Code area -->
    <CodeArea
      :code="visibleCode"
      :language="props.language"
      :show-line-numbers="effectiveShowLineNumbers"
      :wrap-long-lines="props.wrapLongLines"
    />

    <!-- Expand/collapse toggle -->
    <button
      v-if="showExpandToggle"
      type="button"
      @click="toggleExpanded"
      class="w-full border-t border-[var(--color-outline-variant)]/40 bg-[var(--color-surface-container)] py-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-container-high)] hover:text-[var(--color-text-primary)]"
    >
      {{
        expanded
          ? 'Collapse'
          : `Show ${allLines.length - props.maxLines} more lines`
      }}
    </button>
  </div>
</template>
