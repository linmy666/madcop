<script setup lang="ts">
import { ref, computed } from 'vue'

/**
 * PermissionDialog — Vue 3 port of components/chat/PermissionDialog.tsx
 * Tool permission dialog. Prop-driven: parent passes callbacks.
 */

const TOOL_META: Record<string, { icon: string; label: string; color: string }> = {
  Bash: { icon: 'terminal', label: 'Bash', color: 'var(--color-warning)' },
  Edit: { icon: 'edit_note', label: 'Edit File', color: 'var(--color-brand)' },
  Write: { icon: 'edit_document', label: 'Write File', color: 'var(--color-success)' },
  Read: { icon: 'description', label: 'Read File', color: 'var(--color-secondary)' },
  Glob: { icon: 'search', label: 'Glob Search', color: 'var(--color-secondary)' },
  Grep: { icon: 'find_in_page', label: 'Grep Search', color: 'var(--color-secondary)' },
  Agent: { icon: 'smart_toy', label: 'Agent', color: 'var(--color-tertiary)' },
  WebSearch: { icon: 'travel_explore', label: 'Web Search', color: 'var(--color-secondary)' },
  WebFetch: { icon: 'cloud_download', label: 'Web Fetch', color: 'var(--color-secondary)' },
  NotebookEdit: { icon: 'note', label: 'Notebook Edit', color: 'var(--color-brand)' },
  Skill: { icon: 'auto_awesome', label: 'Skill', color: 'var(--color-tertiary)' },
}

export interface PermissionDialogProps {
  toolName: string
  input: unknown
  description?: string
  isPending?: boolean
  t?: (key: string, params?: Record<string, string | number>) => string
}

const props = withDefaults(defineProps<PermissionDialogProps>(), {
  isPending: true,
  t: () => '',
})

const showRaw = ref(false)
const meta = computed(() => TOOL_META[props.toolName] || { icon: 'shield', label: props.toolName, color: 'var(--color-text-tertiary)' })

function getPermissionTitle(): string {
  const obj = (props.input && typeof props.input === 'object') ? props.input as Record<string, unknown> : {}
  const filePath = typeof obj.file_path === 'string' ? obj.file_path : ''
  const fileName = filePath ? filePath.split('/').pop() || filePath : ''
  switch (props.toolName) {
    case 'Edit': case 'Write':
      return fileName ? props.t('permission.allowEditFile', { toolName: props.toolName, fileName }) : props.t('permission.allowEditFileGeneric', { toolName: props.toolName.toLowerCase() })
    case 'Bash': return props.t('permission.allowBash')
    default: return props.t('permission.allowTool', { toolName: props.toolName })
  }
}

function extractToolDetails(): { primary: string; secondary?: string } {
  const obj = (props.input && typeof props.input === 'object') ? props.input as Record<string, unknown> : {}
  switch (props.toolName) {
    case 'Bash': return { primary: typeof obj.command === 'string' ? obj.command : '', secondary: typeof obj.description === 'string' ? obj.description : undefined }
    case 'Edit': return { primary: typeof obj.file_path === 'string' ? obj.file_path : '', secondary: obj.old_string ? props.t('permission.replacingContent') : undefined }
    case 'Write': case 'Read': return { primary: typeof obj.file_path === 'string' ? obj.file_path : '' }
    case 'Glob': case 'Grep': return { primary: typeof obj.pattern === 'string' ? obj.pattern : '' }
    case 'Agent': return { primary: typeof obj.description === 'string' ? obj.description : '' }
    case 'WebSearch': return { primary: typeof obj.query === 'string' ? obj.query : '' }
    case 'WebFetch': return { primary: typeof obj.url === 'string' ? obj.url : '' }
    default: return { primary: typeof props.input === 'string' ? props.input : JSON.stringify(props.input, null, 2) }
  }
}
</script>

<template>
  <div :class="['mb-4 overflow-hidden rounded-[var(--radius-lg)] border',
    isPending ? 'border-[var(--color-warning)] bg-[var(--color-surface-container-lowest)]' : 'border-[var(--color-outline-variant)]/40 bg-[var(--color-surface-container-low)] opacity-70']">
    <div :class="['flex items-center gap-3 px-4 py-3', isPending ? 'bg-[var(--color-surface-container)]' : 'bg-[var(--color-surface-container-low)]']">
      <div class="flex items-center justify-center w-8 h-8 rounded-[var(--radius-md)]" :style="{ backgroundColor: `${meta.color}18` }">
        <span class="material-symbols-outlined text-[18px]" :style="{ color: meta.color }">{{ meta.icon }}</span>
      </div>
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2">
          <span class="text-sm font-semibold text-[var(--color-text-primary)]">{{ getPermissionTitle() }}</span>
          <span v-if="isPending" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-[var(--color-warning)]/15 text-[var(--color-warning)]">
            <span class="w-1.5 h-1.5 rounded-full bg-[var(--color-warning)] animate-pulse" />
            {{ t('permission.awaitingApproval') }}
          </span>
          <span v-else class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-[var(--color-surface-container-high)] text-[var(--color-text-tertiary)]">
            {{ t('permission.responded') }}
          </span>
        </div>
        <p v-if="description" class="mt-0.5 text-xs text-[var(--color-text-secondary)] truncate">{{ description }}</p>
      </div>
    </div>

    <div class="border-t border-[var(--color-outline-variant)]/20 px-4 py-3">
      <div class="mb-2">
        <div class="flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-surface-container)] px-3 py-2 text-xs font-[var(--font-mono)] text-[var(--color-text-secondary)]">
          <span class="material-symbols-outlined text-[14px] text-[var(--color-outline)] flex-shrink-0">{{ toolName === 'Glob' || toolName === 'Grep' ? 'search' : 'folder_open' }}</span>
          <span class="truncate">{{ extractToolDetails().primary }}</span>
        </div>
      </div>

      <button @click="showRaw = !showRaw" class="mt-2 flex cursor-pointer items-center gap-1 text-[11px] text-[var(--color-text-accent)] hover:underline">
        <span class="material-symbols-outlined text-[14px]">{{ showRaw ? 'expand_less' : 'expand_more' }}</span>
        {{ showRaw ? t('permission.hideDetails') : t('permission.showFullInput') }}
      </button>
      <pre v-if="showRaw" class="mt-2 max-h-[220px] overflow-y auto overflow-x-auto rounded-[var(--radius-md)] bg-[var(--color-terminal-bg)] px-3 py-2.5 font-[var(--font-mono)] text-[11px] leading-[1.3] text-[var(--color-terminal-fg)] whitespace-pre-wrap break-words">
{{ typeof input === 'string' ? input : JSON.stringify(input, null, 2) }}
      </pre>
    </div>

    <div v-if="isPending" class="flex items-center gap-2 border-t border-[var(--color-outline-variant)]/20 bg-[var(--color-surface-container-low)] px-4 py-3">
      <button @click="$emit('allow', '')" class="inline-flex items-center gap-1 rounded-[var(--radius-md)] bg-[var(--color-brand)] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand)]/85">
        <span class="material-symbols-outlined text-[14px]">check</span> {{ t('permission.allow') }}
      </button>
      <button @click="$emit('allowForSession', '')" class="inline-flex items-center gap-1 rounded-[var(--radius-md)] border border-[var(--color-border)] px-3 py-1.5 text-[12px] font-medium text-[var(--color-text-primary)] hover:bg-[var(--color-surface-container)]">
        <span class="material-symbols-outlined text-[14px]">verified</span> {{ t('permission.allowForSession') }}
      </button>
      <div class="flex-1" />
      <button @click="$emit('deny', '')" class="inline-flex items-center gap-1 rounded-[var(--radius-md)] border border-[var(--color-error)]/30 px-3 py-1.5 text-[12px] font-medium text-[var(--color-error)] hover:bg-[var(--color-error)]/10">
        <span class="material-symbols-outlined text-[14px]">close</span> {{ t('permission.deny') }}
      </button>
    </div>
  </div>
</template>
