<script setup lang="ts">
// CodeViewer — syntax-highlighted code block with header + copy + collapse.
//
// Highlighting uses shiki's single-file codeToHtml (ships its own grammar
// bundle). Token colors bind to the app's --color-code-* CSS variables so a
// highlighted block follows the active theme. Plain-text / unknown langs
// fall back to a monospace <pre> with no tokenizing.
import { ref, computed, watch, h, defineComponent } from 'vue'
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

/** ── Shiki single-file highlighter ──────────────────────────────────────
 *  Lazy-load codeToHtml once; reuse across all CodeViewer instances. */
let codeToHtmlPromise: Promise<typeof import('shiki')['codeToHtml']> | null = null
function loadCodeToHtml() {
  codeToHtmlPromise ??= import('shiki').then((m) => m.codeToHtml)
  return codeToHtmlPromise
}

// A shiki theme whose colors ARE the var() strings — shiki emits them
// verbatim as inline styles, and the browser resolves the CSS variable, so
// highlighting tracks --color-code-* across light/white/dark automatically.
const SHIKI_THEME = {
  name: 'madcop-code',
  type: 'dark' as const,
  fg: 'var(--color-code-fg)',
  bg: 'transparent',
  tokenColors: [
    { scope: ['comment', 'punctuation.definition.comment'], settings: { foreground: 'var(--color-code-comment)', fontStyle: 'italic' } },
    { scope: ['string', 'string.quoted', 'string.template', 'string.regexp'], settings: { foreground: 'var(--color-code-string)' } },
    { scope: ['keyword', 'keyword.control', 'storage', 'storage.type', 'storage.modifier', 'keyword.operator', 'entity.name.tag', 'punctuation.definition.tag'], settings: { foreground: 'var(--color-code-keyword)' } },
    { scope: ['entity.name.function', 'support.function'], settings: { foreground: 'var(--color-code-function)' } },
    { scope: ['entity.name.type', 'support.type', 'support.class', 'entity.name.class', 'entity.other.inherited-class', 'variable.other.constant'], settings: { foreground: 'var(--color-code-type)' } },
    { scope: ['constant.numeric', 'constant.language', 'entity.name.type.parameter'], settings: { foreground: 'var(--color-code-number)' } },
    { scope: ['variable', 'variable.other', 'variable.other.readwrite'], settings: { foreground: 'var(--color-code-fg)' } },
    { scope: ['variable.parameter'], settings: { foreground: 'var(--color-code-parameter)' } },
    { scope: ['variable.other.property', 'support.type.property-name', 'meta.object-literal.key', 'entity.other.attribute-name'], settings: { foreground: 'var(--color-code-property)' } },
    { scope: ['punctuation', 'meta.brace', 'meta.bracket'], settings: { foreground: 'var(--color-code-punctuation)' } },
    { scope: ['markup.inserted', 'punctuation.definition.inserted'], settings: { foreground: 'var(--color-code-inserted)' } },
    { scope: ['markup.deleted', 'punctuation.definition.deleted'], settings: { foreground: 'var(--color-code-deleted)' } },
  ],
}

/** ── CodeArea ───────────────────────────────────────────────────────────── */
const CodeArea = defineComponent({
  props: {
    code: { type: String, required: true },
    language: { type: String, required: false },
    showLineNumbers: { type: Boolean, default: false },
    wrapLongLines: { type: Boolean, default: false },
  },
  setup(props) {
    const highlighted = ref<string>('')        // shiki HTML; '' = loading/failed/plain
    const effectiveLang = computed(() => {
      const l = (props.language || 'text').toLowerCase()
      // shiki has no standalone 'sh'/'shell' grammar; bash covers it.
      if (l === 'sh' || l === 'shell') return 'bash'
      return l
    })

    async function render() {
      const lang = effectiveLang.value
      if (!lang || lang === 'text' || lang === 'plaintext') {
        highlighted.value = ''
        return
      }
      try {
        const codeToHtml = await loadCodeToHtml()
        highlighted.value = codeToHtml(props.code, {
          lang,
          theme: SHIKI_THEME as any,
          defaultColor: false,                  // don't wrap in a .shiki color div
        })
      } catch {
        highlighted.value = ''                  // unknown lang / load fail → plain
      }
    }

    watch([() => props.code, () => props.language], render, { immediate: true })

    return () => {
      const baseStyle: Record<string, string> = {
        margin: '0',
        padding: CODE_AREA_PADDING,
        fontFamily: 'var(--font-mono)',
        fontSize: '12px',
        lineHeight: String(CODE_LINE_HEIGHT),
        whiteSpace: props.wrapLongLines ? 'pre-wrap' : 'pre',
        wordBreak: props.wrapLongLines ? 'break-word' : 'normal',
        color: 'var(--color-code-fg)',
        background: 'transparent',
      }

      // Shiki path: inject its HTML (a <pre class="shiki"><code>…</code></pre>).
      if (highlighted.value) {
        return h('div', {
          class: 'code-viewer-shiki',
          'data-highlight-engine': 'shiki',
          style: baseStyle,
          innerHTML: highlighted.value,
        })
      }

      // Plain-text fallback: consistent typography + optional line numbers.
      return h(
        'pre',
        {
          'data-code-viewer-content': '',
          'data-highlight-engine': 'plain',
          style: baseStyle,
        },
        props.code.split('\n').map((line, index) =>
          h('span', { key: index }, [
            props.showLineNumbers
              ? h('span', {
                  class: 'mr-3 inline-block min-w-[2.5ch] select-none text-right text-[var(--color-text-tertiary)]',
                }, String(index + 1))
              : null,
            h('span', { key: 't' + index }, line),
            '\n',
          ]),
        ),
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

<style scoped>
/* shiki emits <pre class="shiki"><code>...; neutralize its defaults so our
   container/padding/win govern and the code fills the block. */
.code-viewer-shiki :deep(.shiki) {
  margin: 0;
  padding: 0;
  background: transparent !important;
}
.code-viewer-shiki :deep(code) {
  display: block;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
}
</style>
