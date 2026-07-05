<script setup lang="ts">
/**
 * WorkspaceCodeSurface — Vue 3 full port of components/workspace/WorkspaceCodeSurface.tsx (192 lines)
 * Displays file code diffs with line numbers, +/- highlighting, hunk headers.
 * Prop-driven.
 *
 * Translation rules:
 *   - className → class
 *   - useState → ref()
 *   - useEffect → onMounted / watch
 *   - prism-react-renderer → inline CSS var rendering (no React tokenization)
 *   - ALL Tailwind classes and --color-* variables kept VERBATIM
 */
import { ref, computed, watch, h, defineComponent } from 'vue'

/** ── Constants ─────────────────────────────────────────────────────────── */
export const WORKSPACE_PREVIEW_LINE_LIMIT = 2000
export const WORKSPACE_PLAIN_TEXT_LINE_THRESHOLD = 5000

/**
 * Workspace Prism theme driven by CSS custom properties.
 * (Token-level colors can't be applied without prismjs;
 *  the plain foreground color is applied as a base.)
 */
export const workspacePrismTheme = {
  plain: {
    color: 'var(--color-code-fg)',
    backgroundColor: 'transparent',
  },
  styles: [
    { types: ['comment', 'prolog', 'doctype', 'cdata'], style: { color: 'var(--color-code-comment)', fontStyle: 'italic' } },
    { types: ['string', 'attr-value', 'template-string'], style: { color: 'var(--color-code-string)' } },
    { types: ['keyword', 'selector', 'important', 'atrule'], style: { color: 'var(--color-code-keyword)' } },
    { types: ['function'], style: { color: 'var(--color-code-function)' } },
    { types: ['tag'], style: { color: 'var(--color-code-keyword)' } },
    { types: ['number', 'boolean'], style: { color: 'var(--color-code-number)' } },
    { types: ['operator'], style: { color: 'var(--color-code-fg)' } },
    { types: ['punctuation'], style: { color: 'var(--color-code-punctuation)' } },
    { types: ['variable', 'parameter'], style: { color: 'var(--color-code-fg)' } },
    { types: ['property', 'attr-name'], style: { color: 'var(--color-code-property)' } },
    { types: ['builtin', 'class-name', 'constant', 'symbol'], style: { color: 'var(--color-code-type)' } },
    { types: ['inserted'], style: { color: 'var(--color-code-inserted)' } },
    { types: ['deleted'], style: { color: 'var(--color-code-deleted)' } },
  ],
}

/** ── Exported utility functions (also used by React consumers) ─────────── */
export function getFileExtension(name: string): string {
  const cleanName = name.split('/').pop() ?? name
  const lastDot = cleanName.lastIndexOf('.')
  if (lastDot <= 0 || lastDot === cleanName.length - 1) return ''
  return cleanName.slice(lastDot + 1).toLowerCase()
}

export function normalizePrismLanguage(language: string): string {
  const lower = language.toLowerCase()
  const map: Record<string, string> = {
    text: 'text',
    typescript: 'typescript',
    ts: 'typescript',
    tsx: 'tsx',
    javascript: 'javascript',
    js: 'javascript',
    jsx: 'jsx',
    markdown: 'markdown',
    md: 'markdown',
    html: 'markup',
    xml: 'markup',
    shell: 'bash',
    sh: 'bash',
    zsh: 'bash',
    diff: 'diff',
  }
  return map[lower] ?? lower
}

export function getLanguageFromPath(path: string): string {
  return normalizePrismLanguage(getFileExtension(path) || 'text')
}

/** ── InlineHighlightedCode ─────────────────────────────────────────────── */
/**
 * Vue port of the React InlineHighlightedCode component.
 * Since prism-react-renderer is React-only and prismjs is not in deps,
 * this renders the code inline with the Prism theme's plain color via CSS vars.
 * Token-level highlighting requires adding prismjs as a dependency.
 */
const InlineHighlightedCode = defineComponent({
  props: {
    value: { type: String, required: true },
    language: { type: String, required: true },
  },
  setup(props) {
    return () => {
      // Render plain code; base color comes from --color-code-fg CSS var.
      return h(
        'span',
        {
          class: 'inline-block',
          style: { color: workspacePrismTheme.plain.color },
        },
        props.value,
      )
    }
  },
})

/** ── WorkspaceDiffSurface ──────────────────────────────────────────────── */
export interface WorkspaceDiffSurfaceProps {
  value: string
  path: string
  className?: string
  lineLimit?: number
  t?: (key: string, params?: Record<string, string | number>) => string
}

const props = withDefaults(defineProps<WorkspaceDiffSurfaceProps>(), {
  className: 'min-h-0 flex-1 overflow-auto bg-[var(--color-code-bg)]',
  lineLimit: WORKSPACE_PREVIEW_LINE_LIMIT,
  t: () => '',
})

const showAllLines = ref(false)
const lines = computed(() => props.value.split('\n'))
const visibleLines = computed(() => (showAllLines.value ? lines.value : lines.value.slice(0, props.lineLimit)))
const language = computed(() => getLanguageFromPath(props.path))
const usePlainLargePreview = computed(() => showAllLines.value && lines.value.length > WORKSPACE_PLAIN_TEXT_LINE_THRESHOLD)

/** Reset showAllLines when path or value changes (useEffect) */
watch([() => props.path, () => props.value], () => {
  showAllLines.value = false
})
</script>

<template>
  <div :class="className">
    <div class="relative min-w-max py-2">
      <pre
        data-workspace-code=""
        data-testid="workspace-code"
        class="m-0 font-[var(--font-mono)] text-[12px] leading-[1.55] text-[var(--color-code-fg)]"
      >
        <div
          v-for="(line, index) in visibleLines"
          :key="index"
          :class="['grid min-w-full w-max grid-cols-[48px_18px_max-content] gap-2 px-3',
            line.startsWith('+') && !line.startsWith('+++')
              ? 'bg-[var(--color-diff-added-bg)]'
              : line.startsWith('-') && !line.startsWith('---')
                ? 'bg-[var(--color-diff-removed-bg)]'
                : line.startsWith('@@')
                  ? 'bg-[var(--color-diff-highlight-bg)]'
                  : 'hover:bg-[var(--color-surface-hover)]'
          ]"
        >
          <!-- Line number -->
          <span class="select-none text-right text-[11px] text-[var(--color-text-tertiary)]">
            {{ index + 1 }}
          </span>
          <!-- Prefix (+, -, space) -->
          <span
            :class="['select-none text-center',
              line.startsWith('+') && !line.startsWith('+++')
                ? 'text-[var(--color-diff-added-text)]'
                : line.startsWith('-') && !line.startsWith('---')
                  ? 'text-[var(--color-diff-removed-text)]'
                  : 'text-[var(--color-text-tertiary)]'
            ]"
          >
            {{
              line.length > 0
                ? (line.startsWith('+') && !line.startsWith('+++') ? '+' : (line.startsWith('-') && !line.startsWith('---') ? '-' : ' '))
                : ' '
            }}
          </span>
          <!-- Code content -->
          <span
            :class="['whitespace-pre pr-6',
              (line.startsWith('diff --') || line.startsWith('--- ') || line.startsWith('+++ '))
                ? 'font-semibold text-[var(--color-text-secondary)]'
                : line.startsWith('@@')
                  ? 'font-semibold text-[var(--color-warning)]'
                  : ''
            ]"
          >
            <template v-if="(line.startsWith('+') && !line.startsWith('+++')) || (line.startsWith('-') && !line.startsWith('---')) || line.startsWith(' ')">
              <template v-if="!usePlainLargePreview">
                <InlineHighlightedCode
                  v-if="line.length > 1"
                  :value="line.slice(1)"
                  :language="language"
                />
                <span v-else> </span>
              </template>
              <template v-else>
                {{ line.length > 1 ? line.slice(1) : ' ' }}
              </template>
            </template>
            <template v-else>
              {{ line || ' ' }}
            </template>
          </span>
        </div>
      </pre>

      <!-- Bottom bar: line limit indicator + show/collapse toggle -->
      <div
        v-if="lines.length > lineLimit"
        class="sticky bottom-0 flex items-center gap-3 border-t border-[var(--color-border)] bg-[var(--color-surface-glass)] px-3 py-2 text-xs text-[var(--color-text-tertiary)] backdrop-blur"
      >
        <span>
          {{ showAllLines ? t('workspace.previewAllLines', { total: lines.length }) : t('workspace.previewLineLimit', { count: visibleLines.length, total: lines.length }) }}
        </span>
        <button
          type="button"
          @click="showAllLines = !showAllLines"
          class="ml-auto rounded-[6px] px-2 py-1 text-[12px] font-medium text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
        >
          {{ showAllLines ? t('workspace.collapsePreview') : t('workspace.showAllLoadedLines') }}
        </button>
      </div>
    </div>
  </div>
</template>
