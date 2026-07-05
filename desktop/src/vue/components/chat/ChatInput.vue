<script setup lang="ts">
/**
 * ChatInput — Vue 3 port of components/chat/ChatInput.tsx (1369 lines)
 * 
 * The main composer: textarea + attachments + mode selector + slash commands
 * + file search + permission selector + send/stop button.
 * 
 * Uses Pinia stores for state management. The component is self-contained
 * for the input UI but calls store methods for actual actions.
 */

import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useChatStore } from '../../stores/chatStore'
import { useTabStore } from '../../stores/tabs'
import { useSessionStore } from '../../stores/sessionStore'
import { useSettingsStore } from '../../stores/settingsStore'
import { useSessionRuntimeStore } from '../../stores/sessionRuntimeStore'
import { useWorkspaceChatContextStore } from '../../stores/workspaceChatContextStore'
import AttachmentGallery from './AttachmentGallery.vue'
import ModeSelector from './ModeSelector.vue'
import PermissionModeSelector from '../controls/PermissionModeSelector.vue'
import RepositoryLaunchControls from '../shared/RepositoryLaunchControls.vue'
import FileSearchMenu from './FileSearchMenu.vue'
import ContextUsageIndicator from './ContextUsageIndicator.vue'
import LocalSlashCommandPanel from './LocalSlashCommandPanel.vue'
import ComposerDropOverlay from './ComposerDropOverlay.vue'
import ProjectContextChip from '../shared/ProjectContextChip.vue'

export type ComposerAttachment = {
  id: string
  name: string
  type: 'file' | 'image' | 'text'
  path?: string
  isDirectory?: boolean
  lineStart?: number
  lineEnd?: number
  note?: string
  quote?: string
}

interface Props {
  variant?: 'default' | 'hero'
  compact?: boolean
  /** Override active sessionId (from parent like ChatPage) */
  sessionId?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  compact: false,
})

const chatStore = useChatStore()
const tabStore = useTabStore()
const sessionStore = useSessionStore()
const settingsStore = useSettingsStore()
const runtimeStore = useSessionRuntimeStore()
const workspaceStore = useWorkspaceChatContextStore()

// ─── Local state ───────────────────────────────────────────────

const input = ref('')
const attachments = ref<ComposerAttachment[]>([])
const plusMenuOpen = ref(false)
const slashMenuOpen = ref(false)
const fileSearchOpen = ref(false)
const slashFilter = ref('')
const fileSearchRef = ref<any>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const composerRef = ref<HTMLDivElement | null>(null)

const selectedMode = ref('react')
const plusMenuPosition = ref<'top' | 'bottom'>('bottom')
const slashMenuPosition = ref<'top' | 'bottom'>('bottom')
const slashCommandFilter = ref('')

// ─── Computed state from stores ────────────────────────────────

const activeTabId = computed(() => {
  return props.sessionId || tabStore.activeTabId
})

const sessionState = computed(() => {
  if (!activeTabId.value) return undefined
  return chatStore.sessions[activeTabId.value]
})

const chatState = computed(() => sessionState.value?.chatState ?? 'idle')
const slashCommands = computed(() => sessionState.value?.slashCommands ?? [])
const composerPrefill = computed(() => sessionState.value?.composerPrefill ?? null)
const queuedUserMessages = computed(() => sessionState.value?.queuedUserMessages ?? [])

const activeSession = computed(() => {
  if (!activeTabId.value) return null
  return sessionStore.sessions.find(s => s.id === activeTabId.value) || null
})

const runtimeSelection = computed(() => {
  if (!activeTabId.value) return undefined
  return runtimeStore.selections[activeTabId.value]
})

const currentModel = computed(() => settingsStore.currentModel)
const chatSendBehavior = computed(() => settingsStore.chatSendBehavior)

const isStreaming = computed(() => chatState.value === 'busy')
const messageCount = computed(() => {
  const loaded = sessionState.value?.messages?.length ?? 0
  const total = activeSession.value?.messageCount ?? 0
  return Math.max(loaded, total)
})

const workspaceReferences = computed(() => {
  if (!activeTabId.value) return []
  return workspaceStore.referencesBySession[activeTabId.value] || []
})

// ─── Slash command detection ───────────────────────────────────

const slashAtCursor = computed(() => {
  const pos = inputRef.value?.selectionStart ?? 0
  const text = input.value
  const before = text.slice(0, pos)
  // Find the last "/" in the text before cursor
  const match = before.match(/\/(\S*)$/)
  if (match) {
    return { filter: match[1], full: match[0] }
  }
  return null
})

watch(slashAtCursor, (val) => {
  if (val) {
    slashMenuOpen.value = true
    slashFilter.value = val.filter
  } else {
    slashMenuOpen.value = false
  }
})

// ─── Auto-resize textarea ──────────────────────────────────────

function autoResize() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

watch(input, () => nextTick(autoResize))
onMounted(() => nextTick(autoResize))

// ─── Composer prefill handling ─────────────────────────────────

watch(composerPrefill, (prefill) => {
  if (!prefill) return
  if (prefill.mode === 'replace') {
    input.value = prefill.text
  } else {
    input.value = (input.value + ' ' + prefill.text).trim()
  }
  // Apply attachments from prefill
  if (prefill.attachments && prefill.attachments.length > 0) {
    prefill.attachments.forEach(att => {
      const exists = attachments.value.find(a => a.id === att.id)
      if (!exists) {
        attachments.value.push({
          id: att.id,
          name: att.name,
          type: att.type as 'file' | 'image' | 'text',
          path: att.path,
        })
      }
    })
  }
  // Clear prefill after applying
  if (activeTabId.value) {
    chatStore.clearComposerPrefill(activeTabId.value)
  }
  nextTick(() => {
    inputRef.value?.focus()
  })
}, { immediate: true })

// ─── Keyboard handling ─────────────────────────────────────────

function handleKeydown(e: KeyboardEvent) {
  // Slash menu navigation
  if (slashMenuOpen.value) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      return
    }
    if (e.key === 'Escape') {
      slashMenuOpen.value = false
      return
    }
  }

  // Submit on Enter (depending on settings)
  if (e.key === 'Enter' && !e.shiftKey && chatSendBehavior.value === 'enter') {
    if (slashMenuOpen.value) return // Let slash panel handle Enter
    e.preventDefault()
    handleSend()
    return
  }

  // Ctrl/Cmd + Enter to submit regardless of setting
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault()
    handleSend()
  }
}

// ─── Send message ──────────────────────────────────────────────

function handleSend() {
  const text = input.value.trim()
  if (!text && attachments.value.length === 0) return
  if (!activeTabId.value) return

  chatStore.sendMessage(
    activeTabId.value,
    text,
    attachments.value.map(a => ({
      id: a.id,
      name: a.name,
      path: a.path,
      type: a.type,
    })),
  )

  // Clear input
  input.value = ''
  attachments.value = []
  nextTick(autoResize)
  slashMenuOpen.value = false
}

// ─── Stop generation ───────────────────────────────────────────

function handleStop() {
  if (activeTabId.value) {
    chatStore.stopGeneration(activeTabId.value)
  }
}

// ─── Slash command selection ───────────────────────────────────

function handleSlashSelect(command: string, _args?: string) {
  slashMenuOpen.value = false
  const pos = inputRef.value?.selectionStart ?? input.value.length
  const before = input.value.slice(0, pos)
  const after = input.value.slice(pos)
  
  // Remove the current slash token
  const cleaned = before.replace(/\/\S*$/, '')
  
  // Insert the command
  const leadingSpace = cleaned.length > 0 && !/\s$/.test(cleaned) ? ' ' : ''
  input.value = cleaned + leadingSpace + command + after
  nextTick(() => {
    inputRef.value?.focus()
  })
}

// ─── File search ───────────────────────────────────────────────

function handleFileSearchSelect(path: string, name: string) {
  // Add as attachment
  attachments.value.push({
    id: `file-${Date.now()}`,
    name,
    type: 'file',
    path,
  })
  fileSearchOpen.value = false
}

// ─── Workspace reference ───────────────────────────────────────

function addWorkspaceReference(kind: string, path: string, name: string) {
  if (!activeTabId.value) return
  workspaceStore.addReference(activeTabId.value, {
    kind,
    path,
    name,
  })
}

// ─── Plus menu ─────────────────────────────────────────────────

const plusMenuItems = [
  { id: 'file', label: 'Upload file', icon: 'upload_file' },
  { id: 'image', label: 'Upload image', icon: 'image' },
  { id: 'folder', label: 'Select folder', icon: 'folder' },
  { id: 'workspace', label: 'Workspace reference', icon: 'workspace' },
]

function handlePlusMenuItem(id: string) {
  plusMenuOpen.value = false
  if (id === 'workspace') {
    // Would open workspace selector
  } else if (id === 'file' || id === 'image' || id === 'folder') {
    // Would open file picker
  }
}

// ─── Attachment management ─────────────────────────────────────

function removeAttachment(id: string) {
  attachments.value = attachments.value.filter(a => a.id !== id)
}

function addAttachment(file: File) {
  const id = `att-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const type = file.type.startsWith('image/') ? 'image' : 'file'
  attachments.value.push({
    id,
    name: file.name,
    type,
  })
}

// ─── Composer draft persistence ────────────────────────────────

let draftSaveTimer: ReturnType<typeof setTimeout> | null = null
function saveDraft() {
  if (!activeTabId.value) return
  clearTimeout(draftSaveTimer!)
  draftSaveTimer = setTimeout(() => {
    chatStore.setComposerDraft(activeTabId.value!, {
      input: input.value,
      attachments: attachments.value,
    })
  }, 500)
}

watch(input, saveDraft)
watch(attachments, saveDraft, { deep: true })

// ─── Lifecycle ─────────────────────────────────────────────────

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
  nextTick(() => inputRef.value?.focus())
})
onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div
    ref="composerRef"
    :class="[
      'relative w-full max-w-3xl mx-auto',
      variant === 'hero' ? 'p-8' : 'p-4',
    ]"
  >
    <!-- Context usage indicator (above composer) -->
    <ContextUsageIndicator
      v-if="messageCount > 50"
      :message-count="messageCount"
      :session-id="activeTabId"
    />

    <!-- Workspace references -->
    <div v-if="workspaceReferences.length > 0" class="flex flex-wrap gap-1.5 mb-2">
      <span v-for="ref in workspaceReferences" :key="ref.id"
        class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg>[var(--color-secondary-container)] text>[var(--color-secondary)] text-[10px] font-medium">
        <span class="material-symbols-outlined text-[12px]">description</span>
        {{ ref.name }}
        <button @click.stop="workspaceStore.removeReference(activeTabId!, ref.id)"
                class="ml-0.5 hover:opacity-70"
                :class="['material-symbols-outlined text>[12px]']">close</button>
      </span>
    </div>

    <!-- Attachment gallery -->
    <AttachmentGallery
      v-if="attachments.length > 0"
      :attachments="attachments"
      @remove="removeAttachment"
    />

    <!-- Composer input -->
    <div
      :class="[
        'relative rounded-xl border border-[var(--color-border)] bg>[var(--color-surface-container)] p-2 transition-all',
        isStreaming ? 'border>[var(--color-warning)]/30' : '',
        'focus-within:border>[var(--color-brand)] focus-within:ring-2 focus-within:ring>[var(--color-brand)]/20',
      ]"
    >
      <!-- Top toolbar -->
      <div class="flex items-center gap-1 px-1 pb-1">
        <ModeSelector
          v-model="selectedMode"
          :compact="compact"
        />
        <PermissionModeSelector
          :compact="compact"
          :work-dir="activeSession?.workDir"
        />
        <RepositoryLaunchControls
          v-if="activeSession?.workDir"
          :work-dir="activeSession.workDir"
          :branch="null"
          :use-worktree="false"
          @work-dir-change="() => {}"
          @branch-change="() => {}"
          @use-worktree-change="() => {}"
        />
        <div class="flex-1" />
        <!-- Slash command panel -->
        <LocalSlashCommandPanel
          v-if="slashMenuOpen"
          :filter="slashFilter"
          :current-command="slashAtCursor?.filter"
          @select="handleSlashSelect"
          @dismiss="slashMenuOpen = false"
        />
      </div>

      <!-- Input area -->
      <div class="relative">
        <textarea
          ref="inputRef"
          v-model="input"
          rows="1"
          :class="[
            'w-full bg-transparent border-none focus:outline-none text-sm text>[var(--color-text-primary)] py-2 px-1 resize-none',
            isStreaming ? 'placeholder>[var(--color-warning)]' : 'placeholder>[var(--color-text-tertiary)]',
          ]"
          :placeholder="isStreaming ? 'Agent is thinking...' : 'Type a message or / for commands...'"
          @focus="() => {}"
        />
      </div>

      <!-- Bottom toolbar -->
      <div class="flex items-center gap-1 px-1 pt-1">
        <!-- Plus menu -->
        <div class="relative">
          <button
            @click="plusMenuOpen = !plusMenuOpen"
            :class="[
              'p-2 rounded-lg transition-colors',
              plusMenuOpen ? 'bg>[var(--color-primary-container)] text>[var(--color-brand)]' : 'text>[var(--color-text-tertiary)] hover:text>[var(--color-brand)] hover:bg>[var(--color-surface-hover)]',
            ]"
          >
            <span class="material-symbols-outlined">
              {{ plusMenuOpen ? 'close' : 'add' }}
            </span>
          </button>

          <!-- Plus menu dropdown -->
          <div v-if="plusMenuOpen"
               class="absolute left-0 bottom-full mb-2 w-[200px] rounded-xl bg>[var(--color-surface-container-lowest)] border border>[var(--color-border)] shadow-[var(--shadow-dropdown)] z-50 py-1">
            <button v-for="item in plusMenuItems" :key="item.id"
                    @click="handlePlusMenuItem(item.id)"
                    class="flex w-full items-center gap-2 px-3 py-2 text-xs text>[var(--color-text-primary)] hover:bg>[var(--color-surface-hover)] transition-colors">
              <span class="material-symbols-outlined text-[16px] text>[var(--color-text-secondary)]">{{ item.icon }}</span>
              {{ item.label }}
            </button>
          </div>
        </div>

        <!-- File search -->
        <button
          @click="fileSearchOpen = !fileSearchOpen"
          class="p-2 rounded-lg text>[var(--color-text-tertiary)] hover:text>[var(--color-brand)] hover:bg>[var(--color-surface-hover)] transition-colors"
          title="Search files"
        >
          <span class="material-symbols-outlined">search</span>
        </button>

        <FileSearchMenu
          v-if="fileSearchOpen"
          @select="handleFileSearchSelect"
          @dismiss="fileSearchOpen = false"
        />

        <!-- Context chip -->
        <ProjectContextChip
          v-if="activeSession?.projectPath"
          :project-path="activeSession.projectPath"
        />

        <div class="flex-1" />

        <!-- Send / Stop button -->
        <button
          v-if="isStreaming"
          @click="handleStop"
          class="p-2 rounded-lg bg>[var(--color-error)] text>[var(--color-on-error)] hover:opacity-90 transition-all"
        >
          <span class="material-symbols-outlined" style="fontVariationSettings: 'FILL' 1"">stop</span>
        </button>
        <button
          v-else
          @click="handleSend"
          :disabled="!input.trim() && attachments.length === 0"
          :class="[
            'p-2 rounded-lg transition-all',
            input.trim() || attachments.length > 0
              ? 'bg>[image:var(--gradient-btn-primary)] text>[var(--color-btn-primary-fg)] shadow-sm'
              : 'bg>[var(--color-surface-container-high)] text>[var(--color-text-tertiary)]',
          ]"
        >
          <span class="material-symbols-outlined" style="fontVariationSettings: 'FILL' 1"">send</span>
        </button>
      </div>
    </div>

    <!-- Drag overlay -->
    <ComposerDropOverlay />
  </div>
</template>
