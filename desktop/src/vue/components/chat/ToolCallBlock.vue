<script setup lang="ts">
import { ref, computed } from 'vue'

/**
 * ToolCallBlock — Vue 3 port of components/chat/ToolCallBlock.tsx
 * Renders tool call blocks with name, icon, input preview, and result.
 * Prop-driven: no React stores, no lucide-react.
 * Depends on CodeViewer, DiffViewer, InlineImageGallery (Vue versions available).
 */

export interface ToolCallBlockProps {
  toolName: string
  input: unknown
  result?: { content: unknown; isError: boolean } | null
  compact?: boolean
  isPending?: boolean
  status?: 'stopped'
  t?: (key: string) => string
}

const props = withDefaults(defineProps<ToolCallBlockProps>(), {
  compact: false,
  isPending: false,
  t: () => '',
})

const TOOL_ICONS: Record<string, string> = {
  Bash: 'terminal', Read: 'description', Write: 'edit_document', Edit: 'edit_note',
  Glob: 'search', Grep: 'find_in_page', Agent: 'smart_toy', WebSearch: 'travel_explore',
  WebFetch: 'cloud_download', NotebookEdit: 'note', Skill: 'auto_awesome',
}

const expanded = ref(false)
const obj = computed(() => {
  if (!props.input || typeof props.input !== 'object') return {}
  return props.input as Record<string, unknown>
})

const icon = computed(() => TOOL_ICONS[props.toolName] || 'build')
const filePath = computed(() => (typeof obj.value.file_path === 'string' ? obj.value.file_path : ''))

function getResultContent(): string {
  if (!props.result?.content) return ''
  if (typeof props.result.content === 'string') return props.result.content
  if (typeof props.result.content === 'object') return JSON.stringify(props.result.content, null, 2)
  return String(props.result.content)
}

const resultContent = computed(getResultContent)
const resultIsError = computed(() => props.result?.isError ?? false)

function getSummary(): string {
  const t = props.t
  switch (props.toolName) {
    case 'Bash': {
      const cmd = typeof obj.value.command === 'string' ? obj.value.command : ''
      return cmd.length > 80 ? cmd.slice(0, 80) + '...' : cmd || t('tool.callRunning')
    }
    case 'Edit':
    case 'Write':
    case 'Read': {
      const fp = filePath.value
      return fp ? fp.split('/').pop() || fp : (props.toolName.toLowerCase() + ' file')
    }
    case 'Glob':
    case 'Grep':
      return typeof obj.value.pattern === 'string' ? obj.value.pattern : t('tool.searching')
    case 'WebSearch':
      return typeof obj.value.query === 'string' ? obj.value.query : t('tool.searching')
    case 'WebFetch':
      return typeof obj.value.url === 'string' ? obj.value.url : t('tool.fetching')
    default:
      return props.toolName
  }
}

const summary = computed(getSummary)
const isPlanTool = computed(() => props.toolName === 'ExitPlanMode')

function showTerminal() {
  if (props.toolName !== 'Bash') return false
  return !!(obj.value.command && typeof obj.value.command === 'string')
}

function getBashCommand(): string {
  return typeof obj.value.command === 'string' ? obj.value.command : ''
}

function getEditDiff(): { filePath: string; old: string; newStr: string } | null {
  if (props.toolName !== 'Edit') return null
  const fp = filePath.value || 'file'
  const oldStr = typeof obj.value.old_string === 'string' ? obj.value.old_string : ''
  const newStr = typeof obj.value.new_string === 'string' ? obj.value.new_string : ''
  if (!oldStr && !newStr) return null
  return { filePath: fp, old: oldStr, newStr: newStr }
}

function getWriteDiff(): { filePath: string; old: string; newStr: string } | null {
  if (props.toolName !== 'Write') return null
  const fp = filePath.value || 'file'
  const content = typeof obj.value.content === 'string' ? obj.value.content : ''
  if (!content) return null
  return { filePath: fp, old: '', newStr: content }
}

function getCodePreview(): { code: string; language: string } | null {
  if (props.toolName === 'NotebookEdit' && typeof obj.value.language === 'string' && typeof obj.value.code === 'string') {
    return { code: obj.value.code, language: obj.value.language }
  }
  return null
}
</script>

<template>
  <div
    :class="['mb-3 overflow-hidden rounded-[var(--radius-md)] border',
      isPending && status !== 'stopped'
        ? 'border-[var(--color-brand)]/30 bg-[var(--color-surface-container-lowest)]'
        : 'border-[var(--color-border)] bg-[var(--color-surface-container-low)]']"
  >
    <!-- Header -->
    <button
      type="button"
      @click="expanded = !expanded"
      class="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-[var(--color-surface-container)]"
      :aria-expanded="expanded"
    >
      <span class="material-symbols-outlined text-[16px] text-[var(--color-text-tertiary)]">{{ icon }}</span>
      <span class="font-[var(--font-mono)] text-[11px] font-semibold text-[var(--color-text-primary)]">{{ toolName }}</span>

      <!-- Status indicator -->
      <span v-if="isPending && status !== 'stopped'" class="material-symbols-outlined text-[14px] text-[var(--color-warning)] animate-spin">pending</span>
      <span v-else-if="status === 'stopped'" class="material-symbols-outlined text-[14px] text-[var(--color-error)]">stop</span>
      <span v-else-if="result?.content" class="material-symbols-outlined text-[14px]" :class="resultIsError ? 'text-[var(--color-error)]' : 'text-[var(--color-success)]'">
        {{ resultIsError ? 'error' : 'check_circle' }}
      </span>

      <span class="min-w-0 flex-1 truncate text-[11px] text-[var(--color-text-secondary)]">{{ summary }}</span>

      <span class="material-symbols-outlined text-[14px] text-[var(--color-text-tertiary)] transition-transform" :class="{ 'rotate-180': expanded }">expand_less</span>
    </button>

    <!-- Body -->
    <div v-if="expanded" class="border-t border-[var(--color-border)]/40">
      <!-- Bash command -->
      <div v-if="showTerminal()" class="overflow-x-auto rounded-b-[var(--radius-md)] bg-[var(--color-terminal-bg)] px-3 py-2.5">
        <pre class="font-[var(--font-mono)] text-[11px] leading-[1.3] text-[var(--color-terminal-fg)] whitespace-pre-wrap break-words">
<span class="text-[var(--color-terminal-accent)] select-none">$ </span>{{ getBashCommand() }}
        </pre>
      </div>

      <!-- Edit/Write diff -->
      <div v-if="getEditDiff()">
        <slot :name="'diff-edit'" :file-path="getEditDiff()!.filePath" :old="getEditDiff()!.old" :new="getEditDiff()!.newStr"></slot>
      </div>
      <div v-else-if="getWriteDiff()">
        <slot :name="'diff-write'" :file-path="getWriteDiff()!.filePath" :old="getWriteDiff()!.old" :new="getWriteDiff()!.newStr"></slot>
      </div>

      <!-- Notebook code -->
      <div v-if="getCodePreview()">
        <slot :name="'code'" :code="getCodePreview()!.code" :language="getCodePreview()!.language"></slot>
      </div>

      <!-- Inline images from result -->
      <slot :name="'images'" :text="resultContent"></slot>

      <!-- Result output -->
      <div v-if="resultContent" class="max-h-[300px] overflow-auto rounded-b-[var(--radius-md)] bg-[var(--color-terminal-bg)] px-3 py-2.5">
        <pre :class="['font-[var(--font-mono)] text-[11px] leading-[1.3] whitespace-pre-wrap break-words', resultIsError ? 'text-[var(--color-error)]' : 'text-[var(--color-terminal-fg)]']">{{ resultContent }}</pre>
      </div>

      <!-- Pending indicator -->
      <div v-if="isPending && !result" class="flex items-center gap-2 px-3 py-2.5 text-xs text-[var(--color-text-tertiary)]">
        <span class="material-symbols-outlined text-[14px] animate-spin">pending</span>
        {{ t('tool.callRunning') }}
      </div>
    </div>
  </div>
</template>
