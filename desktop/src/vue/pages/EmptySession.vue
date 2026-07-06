<script setup lang="ts">
/**
 * EmptySession — Vue 3 port of pages/EmptySession.tsx (839 lines)
 *
 * Full translation: composer with slash commands, @ file search, attachments,
 * permission mode, model selector, repository launch controls, drag-and-drop.
 *
 * Conversion rules applied:
 *   className → class
 *   useState → ref()
 *   useEffect → onMounted / watch
 *   useCallback → () => { ... }
 *   useMemo → computed()
 *   lucide-react icons → <span class="material-symbols-outlined">
 *   createPortal → <teleport to="body">
 *   Tailwind classes and --color-* variables kept VERBATIM.
 */

import {
  ref,
  onMounted,
  onUnmounted,
  computed,
  nextTick,
  watch,
} from 'vue'

/* ────────────────────────────────────────────────────────────────────
   Imports (APIs, stores, hooks, components)
   ──────────────────────────────────────────────────────────────────── */
import { ApiError } from '../api/client'
import { agentsApi } from '../api/agents'
import { skillsApi } from '../api/skills'
import { useTranslation } from '../i18n'
import { useSessionStore } from '../stores/sessionStore'
import { useChatStore } from '../stores/chatStore'
import { usePluginStore } from '../stores/pluginStore'
import { useSessionRuntimeStore, DRAFT_RUNTIME_SELECTION_KEY } from '../stores/sessionRuntimeStore'
import { useSettingsStore } from '../stores/settingsStore'
import { useUIStore } from '../stores/uiStore'
import { SETTINGS_TAB_ID, useTabStore } from '../stores/tabStore'
import RepositoryLaunchControls from '../components/shared/RepositoryLaunchControls.vue'
import PermissionModeSelector from '../components/controls/PermissionModeSelector.vue'
import ModelSelector from '../components/controls/ModelSelector.vue'
import AttachmentGallery from '../components/chat/AttachmentGallery.vue'
import ComposerDropOverlay from '../components/chat/ComposerDropOverlay.vue'
import ContextUsageIndicator from '../components/chat/ContextUsageIndicator.vue'
import FileSearchMenu from '../components/chat/FileSearchMenu.vue'
import LocalSlashCommandPanel from '../components/chat/LocalSlashCommandPanel.vue'
import { useMobileViewport } from '../hooks/useMobileViewport'
import { isDesktopRuntime } from '../lib/desktopRuntime'
import MadCopLoader from '../components/common/MadCopLoader.vue'
import {
  filesToComposerAttachments,
  selectNativeFileAttachments,
  type ComposerAttachment,
} from '../lib/composerAttachments'
import { useComposerFileDrop } from '../components/chat/useComposerFileDrop'
import { shouldSubmitOnEnter } from '../components/chat/sendShortcut'
import {
  appendAgentSlashCommands,
  buildAgentSlashCommands,
  getLocalizedFallbackCommands,
  filterSlashCommands,
  findSlashToken,
  insertSlashTrigger,
  mergeSlashCommands,
  replaceSlashCommand,
  resolveSlashUiAction,
} from '../components/chat/composerUtils'
import type { AttachmentRef } from '../types/chat'
import type { PermissionMode } from '../types/settings'
import type { SlashCommandOption } from '../components/chat/composerUtils'

type Attachment = ComposerAttachment

/* ────────────────────────────────────────────────────────────────────
   Translation helper
   ──────────────────────────────────────────────────────────────────── */
const t = useTranslation()

/* ────────────────────────────────────────────────────────────────────
   React helper functions (ported as plain functions)
   ──────────────────────────────────────────────────────────────────── */
function getApiErrorCode(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null
  const body = (error as ApiError).body
  if (!body || typeof body !== 'object' || !('error' in body)) return null
  return typeof (body as { error?: unknown }).error === 'string'
    ? ((body as { error: string }).error as string)
    : null
}

function resolveCreateSessionErrorMessage(
  error: unknown,
  tFn: ReturnType<typeof useTranslation>,
): string {
  const code = getApiErrorCode(error)
  switch (code) {
    case 'WORKDIR_MISSING':
    case 'WORKDIR_NOT_DIRECTORY':
      return tFn('empty.createError.workdirMissing')
    case 'REPOSITORY_NOT_GIT':
      return tFn('empty.createError.notGit')
    case 'REPOSITORY_BRANCH_NOT_FOUND':
      return tFn('empty.createError.branchNotFound')
    case 'REPOSITORY_DIRTY_WORKTREE':
      return tFn('empty.createError.dirtyWorktree')
    case 'REPOSITORY_BRANCH_CHECKED_OUT':
      return tFn('empty.createError.branchCheckedOut')
    case 'REPOSITORY_WORKTREE_CREATE_FAILED':
      return tFn('empty.createError.worktreeCreateFailed', {
        detail: error instanceof Error ? error.message : tFn('empty.failedToCreate'),
      })
    case 'REPOSITORY_SWITCH_FAILED':
      return tFn('empty.createError.switchFailed', {
        detail: error instanceof Error ? error.message : tFn('empty.failedToCreate'),
      })
    case 'REPOSITORY_CONTEXT_ERROR':
      return tFn('empty.createError.contextFailed')
    default:
      return error instanceof Error ? error.message : tFn('empty.failedToCreate')
  }
}

/* ────────────────────────────────────────────────────────────────────
   Reactive state (useState → ref)
   ──────────────────────────────────────────────────────────────────── */
const input = ref('')
const isSubmitting = ref(false)
const workDir = ref('')
const selectedBranch = ref<string | null>(null)
const useWorktree = ref(false)
const repositoryLaunchReady = ref(true)
const attachments = ref<Attachment[]>([])
const plusMenuOpen = ref(false)
const slashMenuOpen = ref(false)
const fileSearchOpen = ref(false)
const localSlashPanel = ref<LocalSlashCommandName | null>(null)
const atFilter = ref('')
const atCursorPos = ref(-1)
const slashFilter = ref('')
const slashSelectedIndex = ref(0)
const slashCommands = ref<SlashCommandOption[]>([])
const agentSlashCommands = ref<SlashCommandOption[]>([])
const draftPermissionMode = ref<PermissionMode>('ask')

/* ────────────────────────────────────────────────────────────────────
   Refs for DOM elements (useRef → ref<HTMLElement | null>(null))
   ──────────────────────────────────────────────────────────────────── */
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const panelRef = ref<HTMLDivElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const plusMenuRef = ref<HTMLDivElement | null>(null)
const slashMenuRef = ref<HTMLDivElement | null>(null)
const fileSearchRef = ref<InstanceType<typeof FileSearchMenu> | null>(null)
const slashItemRefs = ref<(HTMLButtonElement | null)[]>([])

/* ────────────────────────────────────────────────────────────────────
   Store bindings (zustand selectors → direct calls in onMounted)
   ──────────────────────────────────────────────────────────────────── */
const createSession = useSessionStore().createSession
const sendMessage = useChatStore().sendMessage
const connectToSession = useChatStore().connectToSession
const setActiveView = useUIStore().setActiveView
const addToast = useUIStore().addToast
const currentModel = useSettingsStore().currentModel
const chatSendBehavior = useSettingsStore().chatSendBehavior
const defaultPermissionMode = useSettingsStore().permissionMode
draftPermissionMode.value = defaultPermissionMode
const lastPluginReloadSummary = usePluginStore().lastReloadSummary

/* ────────────────────────────────────────────────────────────────────
   Computed values (useMemo / derived state)
   ──────────────────────────────────────────────────────────────────── */
const draftRuntimeSelection = computed(() => {
  return useSessionRuntimeStore().selections[DRAFT_RUNTIME_SELECTION_KEY]
})

const draftRuntimeSelectionKey = computed(() => {
  const sel = draftRuntimeSelection.value
  if (!sel) return undefined
  return `${sel.providerId ?? 'official'}:${sel.modelId}:${sel.effortLevel ?? 'auto'}`
})

const draftModelLabel = computed(() => {
  return draftRuntimeSelection.value?.modelId ?? currentModel?.name ?? currentModel?.id
})

const isMobileComposer = computed(() => useMobileViewport() && !isDesktopRuntime())

const allSlashCommands = computed(() => {
  return appendAgentSlashCommands(
    mergeSlashCommands(slashCommands.value ?? [], getLocalizedFallbackCommands(t)),
    agentSlashCommands.value ?? [],
  ) ?? []
})

const filteredCommands = computed(() => {
  return filterSlashCommands(allSlashCommands.value ?? [], slashFilter.value) ?? []
})

const exactSlashCommand = computed(() => {
  const normalized = slashFilter.value.trim().toLowerCase()
  if (!normalized) return null
  return (
    filteredCommands.value.find(
      (c) => c.name.toLowerCase() === normalized,
    ) ?? null
  )
})

const canSubmit = computed(() => {
  return (
    (input.value.trim().length > 0 ||
      attachments.value.length > 0 ||
      !!workDir.value) &&
    !isSubmitting.value &&
    repositoryLaunchReady.value
  )
})

/* ────────────────────────────────────────────────────────────────────
   Loaders
   ──────────────────────────────────────────────────────────────────── */
const loadSlashCommands = async () => {
  const cwd = workDir.value || undefined
  try {
    const { skills } = await skillsApi.list(cwd)
    slashCommands.value = skills
      .filter((skill) => skill.userInvocable)
      .map((skill) => ({
        name: skill.name,
        description: skill.description,
      }))
  } catch {
    slashCommands.value = []
  }
}

const loadAgentSlashCommands = async () => {
  const cwd = workDir.value || undefined
  try {
    const { activeAgents } = await agentsApi.list(cwd)
    agentSlashCommands.value = buildAgentSlashCommands(activeAgents)
  } catch {
    agentSlashCommands.value = []
  }
}

/* ────────────────────────────────────────────────────────────────────
   Lifecycle (useEffect → onMounted / watch)
   ──────────────────────────────────────────────────────────────────── */
onMounted(() => {
  // Focus textarea on mount (useEffect with [])
  nextTick(() => {
    textareaRef.value?.focus()
  })

  // Initial slash command loads
  loadSlashCommands()
  loadAgentSlashCommands()
})

// Reload slash commands when workDir or plugin reload summary changes
watch(
  () => [workDir.value, lastPluginReloadSummary],
  () => {
    loadSlashCommands()
    loadAgentSlashCommands()
  },
)

// Reset slashSelectedIndex when slashFilter changes (useEffect with [slashFilter])
watch(slashFilter, () => {
  slashSelectedIndex.value = 0
})

// Scroll active slash menu item into view (useEffect with [slashMenuOpen, slashSelectedIndex])
watch([slashMenuOpen, slashSelectedIndex], () => {
  if (!slashMenuOpen.value) return
  const activeItem = slashItemRefs.value[slashSelectedIndex.value]
  if (activeItem && typeof activeItem.scrollIntoView === 'function') {
    activeItem.scrollIntoView({ block: 'nearest' })
  }
})

// Click-outside listeners (useEffect → watch on menu-open state)
watch(plusMenuOpen, () => registerClickOutside('plus'))
watch(slashMenuOpen, () => registerClickOutside('slash'))
watch(localSlashPanel, () => registerClickOutside('localPanel'))
watch(fileSearchOpen, () => registerClickOutside('fileSearch'))

/* ────────────────────────────────────────────────────────────────────
   Click-outside handlers (useEffect with mousedown listener)
   ──────────────────────────────────────────────────────────────────── */
let plusClickListener: ((e: MouseEvent) => void) | null = null
let slashClickListener: ((e: MouseEvent) => void) | null = null
let localPanelClickListener: ((e: MouseEvent) => void) | null = null
let fileSearchClickListener: ((e: MouseEvent) => void) | null = null

const registerClickOutside = (type: 'plus' | 'slash' | 'localPanel' | 'fileSearch') => {
  const removeExisting = () => {
    document.removeEventListener('mousedown', plusClickListener!)
    document.removeEventListener('mousedown', slashClickListener!)
    document.removeEventListener('mousedown', localPanelClickListener!)
    document.removeEventListener('mousedown', fileSearchClickListener!)
    plusClickListener = null
    slashClickListener = null
    localPanelClickListener = null
    fileSearchClickListener = null
  }

  removeExisting()

  if (type === 'plus' && plusMenuOpen.value) {
    plusClickListener = (event: MouseEvent) => {
      if (plusMenuRef.value && !plusMenuRef.value.contains(event.target as Node)) {
        plusMenuOpen.value = false
      }
    }
    document.addEventListener('mousedown', plusClickListener)
  } else if (type === 'slash' && slashMenuOpen.value) {
    slashClickListener = (event: MouseEvent) => {
      if (
        slashMenuRef.value &&
        !slashMenuRef.value.contains(event.target as Node) &&
        textareaRef.value &&
        !textareaRef.value.contains(event.target as Node)
      ) {
        slashMenuOpen.value = false
      }
    }
    document.addEventListener('mousedown', slashClickListener)
  } else if (type === 'localPanel' && localSlashPanel.value) {
    localPanelClickListener = (event: MouseEvent) => {
      if (
        slashMenuRef.value &&
        !slashMenuRef.value.contains(event.target as Node) &&
        textareaRef.value &&
        !textareaRef.value.contains(event.target as Node)
      ) {
        localSlashPanel.value = null
      }
    }
    document.addEventListener('mousedown', localPanelClickListener)
  } else if (type === 'fileSearch' && fileSearchOpen.value) {
    fileSearchClickListener = (event: MouseEvent) => {
      const menu = document.getElementById('file-search-menu')
      if (
        menu &&
        !menu.contains(event.target as Node) &&
        textareaRef.value &&
        !textareaRef.value.contains(event.target as Node)
      ) {
        fileSearchOpen.value = false
      }
    }
    document.addEventListener('mousedown', fileSearchClickListener)
  }
}

const unregisterClickOutside = () => {
  document.removeEventListener('mousedown', plusClickListener!)
  document.removeEventListener('mousedown', slashClickListener!)
  document.removeEventListener('mousedown', localPanelClickListener!)
  document.removeEventListener('mousedown', fileSearchClickListener!)
  plusClickListener = null
  slashClickListener = null
  localPanelClickListener = null
  fileSearchClickListener = null
}

onUnmounted(() => {
  unregisterClickOutside()
})

/* ────────────────────────────────────────────────────────────────────
   Event handlers
   ──────────────────────────────────────────────────────────────────── */
const handleWorkDirChange = (newWorkDir: string) => {
  workDir.value = newWorkDir
  selectedBranch.value = null
  useWorktree.value = false
  repositoryLaunchReady.value = !newWorkDir
}

const handleSubmit = async () => {
  const text = input.value.trim()
  if (!canSubmit.value) return

  const slashUiAction = text.startsWith('/') ? resolveSlashUiAction(text.slice(1)) : null

  if (slashUiAction?.type === 'panel') {
    localSlashPanel.value = slashUiAction.command as LocalSlashCommandName
    input.value = ''
    slashMenuOpen.value = false
    fileSearchOpen.value = false
    plusMenuOpen.value = false
    return
  }

  if (slashUiAction?.type === 'settings') {
    useUIStore().setPendingSettingsTab(slashUiAction.tab)
    useTabStore().openTab(SETTINGS_TAB_ID, 'Settings', 'settings')
    input.value = ''
    slashMenuOpen.value = false
    fileSearchOpen.value = false
    plusMenuOpen.value = false
    return
  }

  isSubmitting.value = true
  try {
    const explicitDraftSelection =
      useSessionRuntimeStore().selections[DRAFT_RUNTIME_SELECTION_KEY]
    const sessionId = await createSession(workDir.value || undefined, {
      ...(selectedBranch.value
        ? { repository: { branch: selectedBranch.value, worktree: useWorktree.value } }
        : {}),
      permissionMode: draftPermissionMode.value,
    })
    if (explicitDraftSelection) {
      useSessionRuntimeStore().setSelection(sessionId, explicitDraftSelection)
      useSessionRuntimeStore().clearSelection(DRAFT_RUNTIME_SELECTION_KEY)
    }
    setActiveView('code')
    useTabStore().openTab(sessionId, 'New Session')
    connectToSession(sessionId)
    const attachmentPayload: AttachmentRef[] = attachments.value.map((a) => ({
      type: a.type,
      name: a.name,
      path: a.path,
      data: a.data,
      mimeType: a.mimeType,
    }))
    if (text || attachmentPayload.length > 0) {
      sendMessage(sessionId, text, attachmentPayload)
    }
    input.value = ''
    attachments.value = []
  } catch (error) {
    addToast({
      type: 'error',
      message: resolveCreateSessionErrorMessage(error, t),
    })
  } finally {
    isSubmitting.value = false
  }
}

const handleInputChange = (value: string, cursorPos: number) => {
  input.value = value
  const token = findSlashToken(value, cursorPos)
  if (!token) {
    slashMenuOpen.value = false
  } else {
    slashFilter.value = token.filter
    slashMenuOpen.value = true
  }

  // Detect @ trigger for file search
  const textBeforeCursor = value.slice(0, cursorPos)
  let pos = -1
  for (let i = textBeforeCursor.length - 1; i >= 0; i--) {
    const ch = textBeforeCursor[i]!
    if (ch === '@') {
      if (i === 0 || /\s/.test(textBeforeCursor[i - 1]!)) {
        pos = i
        break
      }
      break
    }
    if (/\s/.test(ch)) {
      break
    }
  }
  if (pos < 0) {
    fileSearchOpen.value = false
    atFilter.value = ''
    atCursorPos.value = -1
  } else {
    atFilter.value = textBeforeCursor.slice(pos + 1)
    atCursorPos.value = pos
    slashMenuOpen.value = false
    fileSearchOpen.value = true
  }
}

const handleKeyDown = (event: KeyboardEvent) => {
  // Ignore key events during IME composition
  if ((event as any).nativeEvent?.isComposing) return

  // Route file search navigation keys
  if (fileSearchOpen.value) {
    const key = event.key
    if (key === 'ArrowDown' || key === 'ArrowUp' || key === 'Enter' || key === 'Tab' || key === 'Escape') {
      event.preventDefault()
      if (key === 'Escape') {
        fileSearchOpen.value = false
        atFilter.value = ''
        atCursorPos.value = -1
        return
      }
      fileSearchRef.value?.handleKeyDown?.(event)
      return
    }
    return
  }

  if (slashMenuOpen.value && filteredCommands.value.length > 0) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      slashSelectedIndex.value = (slashSelectedIndex.value + 1) % filteredCommands.value.length
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      slashSelectedIndex.value =
        (slashSelectedIndex.value - 1 + filteredCommands.value.length) %
        filteredCommands.value.length
      return
    }
    if (event.key === 'Enter' || event.key === 'Tab') {
      const selected = filteredCommands.value[slashSelectedIndex.value]
      if (
        event.key === 'Enter' &&
        exactSlashCommand.value &&
        selected?.name.toLowerCase() === exactSlashCommand.value.name.toLowerCase() &&
        slashFilter.value.trim().toLowerCase() === exactSlashCommand.value.name.toLowerCase() &&
        shouldSubmitOnEnter(event, chatSendBehavior)
      ) {
        event.preventDefault()
        void handleSubmit()
        return
      }
      event.preventDefault()
      if (selected) selectSlashCommand(selected.name)
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      slashMenuOpen.value = false
      return
    }
  }

  if (shouldSubmitOnEnter(event, chatSendBehavior)) {
    event.preventDefault()
    handleSubmit()
  }
}

const handlePaste = (event: ClipboardEvent) => {
  const items = event.clipboardData?.items
  if (!items) return

  let hasImage = false
  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (!item || !item.type.startsWith('image/')) continue

    hasImage = true
    event.preventDefault()
    const file = item.getAsFile()
    if (!file) continue
    const id = `att-${Date.now()}-${Math.random().toString(36).slice(2)}`
    const reader = new FileReader()
    reader.onload = () => {
      attachments.value = [
        ...attachments.value,
        {
          id,
          name: `pasted-image-${Date.now()}.png`,
          type: 'image',
          mimeType: file.type || undefined,
          previewUrl: reader.result as string,
          data: reader.result as string,
        },
      ]
    }
    reader.readAsDataURL(file)
  }
}

const appendFiles = async (files: FileList | File[]) => {
  try {
    const nextAttachments = await filesToComposerAttachments(files)
    if (nextAttachments.length === 0) return
    attachments.value = [...attachments.value, ...nextAttachments]
  } catch (error) {
    console.warn('[attachments] Failed to read selected files', error)
  }
}

const appendAttachments = (nextAttachments: Attachment[]) => {
  if (nextAttachments.length === 0) return
  attachments.value = [...attachments.value, ...nextAttachments]
}

const { isDragActive, dragHandlers } = useComposerFileDrop({
  panelRef,
  onAttachments: appendAttachments,
  onError: (error) => {
    console.warn('[attachments] Failed to read dropped files', error)
  },
})

const openAttachmentPicker = () => {
  plusMenuOpen.value = false
  if (!isDesktopRuntime()) {
    fileInputRef.value?.click()
    return
  }

  selectNativeFileAttachments()
    .then((nativeAttachments) => {
      if (nativeAttachments && nativeAttachments.length > 0) {
        attachments.value = [...attachments.value, ...nativeAttachments]
        return
      }
      fileInputRef.value?.click()
    })
    .catch(() => {
      fileInputRef.value?.click()
    })
}

const handleFileSelect = (event: Event) => {
  const files = (event.target as HTMLInputElement).files
  if (!files) return
  appendFiles(files)
  ;(event.target as HTMLInputElement).value = ''
}

const removeAttachment = (id: string) => {
  attachments.value = attachments.value.filter((a) => a.id !== id)
}

const selectSlashCommand = (command: string) => {
  const el = textareaRef.value
  if (!el) return
  const cursorPos = el.selectionStart ?? input.value.length
  const replacement = replaceSlashCommand(input.value, cursorPos, command)
  if (!replacement) return
  input.value = replacement.value
  slashMenuOpen.value = false
  requestAnimationFrame(() => {
    el.focus()
    el.setSelectionRange(replacement.cursorPos, replacement.cursorPos)
  })
}

const insertSlashCommand = () => {
  const el = textareaRef.value
  const cursorPos = el?.selectionStart ?? input.value.length
  const replacement = insertSlashTrigger(input.value, cursorPos)
  input.value = replacement.value
  plusMenuOpen.value = false
  slashFilter.value = ''
  slashMenuOpen.value = true
  requestAnimationFrame(() => {
    textareaRef.value?.focus()
    textareaRef.value?.setSelectionRange(replacement.cursorPos, replacement.cursorPos)
  })
}
</script>

<template>
  <div class="relative flex flex-1 flex-col overflow-hidden bg-[var(--color-surface)]">
    <!-- ═══════════════════════════════════════════════════════════════
         Centered intro (MadCopLoader + title + subtitle)
         ═══════════════════════════════════════════════════════════════ -->
    <div
      class="flex flex-1 flex-col items-center justify-center"
      :class="isMobileComposer ? 'px-6 pb-[230px] pt-10' : 'p-8 pb-32'"
    >
      <div
        class="flex flex-col items-center text-center"
        :class="isMobileComposer ? 'max-w-[300px]' : 'max-w-md'"
      >
        <MadCopLoader
          :state="isSubmitting ? 'working' : 'ready'"
          :size="isMobileComposer ? 128 : 200"
          :class="isMobileComposer ? 'mb-4' : 'mb-6'"
        />
        <h1
          class="mb-2 font-extrabold tracking-tight text-[var(--color-text-primary)]"
          :class="isMobileComposer ? 'text-2xl' : 'text-3xl'"
          :style="{ fontFamily: 'var(--font-headline)' }"
        >
          {{ t('empty.title') }}
        </h1>
        <p
          class="mx-auto text-[var(--color-text-secondary)]"
          :class="isMobileComposer ? 'max-w-[280px] text-sm leading-6' : 'max-w-xs'"
          :style="{ fontFamily: 'var(--font-body)' }"
        >
          {{ t('empty.subtitle') }}
        </p>
      </div>
    </div>

    <!-- ═══════════════════════════════════════════════════════════════
         Composer (fixed at bottom)
         ═══════════════════════════════════════════════════════════════ -->
    <div
      data-testid="empty-session-composer-shell"
      class="absolute left-0 right-0 z-30 flex justify-center"
      :class="
        isMobileComposer
          ? 'bottom-0 px-3 pb-[calc(env(safe-area-inset-bottom)+10px)]'
          : 'bottom-4 px-8'
      "
    >
      <div class="flex w-full flex-col" :class="isMobileComposer ? 'max-w-none' : 'max-w-3xl'">
        <div
          ref="panelRef"
          v-bind="dragHandlers"
          data-testid="empty-session-composer-panel"
          class="glass-panel relative flex flex-col gap-3 overflow-visible"
          :class="[
            isMobileComposer ? 'rounded-2xl p-3 shadow-[0_-12px_36px_rgba(54,35,28,0.12)]' : 'rounded-xl p-0',
            { 'composer-drop-target-active': isDragActive },
          ]"
        >
          <!-- Drop overlay (teleport-style, but inline since it's relative) -->
          <ComposerDropOverlay
            v-if="isDragActive"
            test-id="empty-session-drop-overlay"
            :title="t('chat.dropFilesTitle')"
            :description="t('chat.dropFilesHint')"
          />

          <div :class="isMobileComposer ? 'contents' : 'flex flex-col gap-3 p-4'">
            <!-- ═══ File Search Menu (v-show for visibility toggle) ═══ -->
            <FileSearchMenu
              v-if="fileSearchOpen"
              ref="fileSearchRef"
              :cwd="workDir || ''"
              :filter="atFilter"
              @navigate="(relativePath: string) => {
                if (atCursorPos < 0) return
                const replacement = '@' + relativePath
                const tokenEnd = atCursorPos + 1 + atFilter.length
                const newValue =
                  input.slice(0, atCursorPos) + replacement + input.slice(tokenEnd)
                const newCursorPos = atCursorPos + replacement.length
                input = newValue
                atFilter = relativePath
                nextTick(() => {
                  textareaRef?.focus()
                  textareaRef?.setSelectionRange(newCursorPos, newCursorPos)
                })
              }"
              @select="(path: string, name: string) => {
                if (atCursorPos >= 0) {
                  const attachmentName = name.split('/').filter(Boolean).pop() || name
                  const tokenEnd = atCursorPos + 1 + atFilter.length
                  const beforeToken = input.slice(0, atCursorPos)
                  const afterToken = beforeToken
                    ? input.slice(tokenEnd).replace(/^\s+/, '')
                    : input.slice(tokenEnd)
                  const spacer =
                    beforeToken &&
                    afterToken &&
                    !/\s$/.test(beforeToken) &&
                    !/^\s/.test(afterToken)
                      ? ' '
                      : ''
                  const newValue = beforeToken + spacer + afterToken
                  const newCursorPos = atCursorPos + spacer.length
                  attachments = [
                    ...attachments,
                    {
                      id: `att-${Date.now()}-${Math.random().toString(36).slice(2)}`,
                      name: attachmentName,
                      type: 'file',
                      path,
                    },
                  ]
                  input = newValue
                  fileSearchOpen = false
                  atFilter = ''
                  atCursorPos = -1
                  nextTick(() => {
                    textareaRef?.focus()
                    textareaRef?.setSelectionRange(newCursorPos, newCursorPos)
                  })
                }
              }"
            />

            <!-- ═══ Local Slash Command Panel ═══ -->
            <div v-if="localSlashPanel" ref="slashMenuRef">
              <LocalSlashCommandPanel
                :command="localSlashPanel"
                :cwd="workDir || undefined"
                :commands="allSlashCommands"
                @close="localSlashPanel = null"
              />
            </div>

            <!-- ═══ Slash Command Dropdown Menu ═══ -->
            <div
              v-if="slashMenuOpen && filteredCommands.length > 0"
              ref="slashMenuRef"
              class="absolute bottom-full left-0 right-0 z-50 mb-2 overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] shadow-[var(--shadow-dropdown)]"
            >
              <div class="max-h-[260px] overflow-y-auto py-1">
                <button
                  v-for="(command, index) in filteredCommands"
                  :key="command.name"
                  @click="selectSlashCommand(command.name)"
                  @mouseenter="slashSelectedIndex = index"
                  class="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors"
                  :class="
                    index === slashSelectedIndex
                      ? 'bg-[var(--color-surface-hover)]'
                      : 'hover:bg-[var(--color-surface-hover)]'
                  "
                  :ref="(el: any) => { slashItemRefs[index] = el }"
                >
                  <span class="flex min-w-0 max-w-[52%] shrink-0 items-baseline gap-1.5">
                    <span
                      class="shrink-0 text-sm font-semibold text-[var(--color-text-primary)]"
                    >
                      /{{ command.name }}
                    </span>
                    <span
                      v-if="command.argumentHint"
                      class="min-w-0 truncate font-mono text-[11px] text-[var(--color-text-tertiary)]"
                    >
                      {{ command.argumentHint }}
                    </span>
                  </span>
                  <span
                    class="min-w-0 flex-1 truncate text-xs text-[var(--color-text-tertiary)]"
                  >
                    {{ command.description }}
                  </span>
                </button>
              </div>
            </div>

            <!-- ═══ Attachment Gallery ═══ -->
            <AttachmentGallery
              v-if="attachments.length > 0"
              :attachments="attachments"
              variant="composer"
              @remove="removeAttachment"
            />

            <!-- ═══ Textarea ═══ -->
            <div class="flex items-start gap-3">
              <textarea
                ref="textareaRef"
                :value="input"
                @input="(e: any) =>
                  handleInputChange(e.target.value, e.target.selectionStart ?? e.target.value.length)"
                @keydown="handleKeyDown"
                @paste="handlePaste"
                class="flex-1 resize-none border-none bg-transparent leading-relaxed text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-tertiary)]"
                :class="
                  isMobileComposer
                    ? 'max-h-[132px] min-h-[72px] py-1.5 text-base'
                    : 'py-2'
                "
                :style="{ fontFamily: 'var(--font-body)' }"
                :placeholder="t('empty.placeholder')"
                rows="2"
              />
            </div>

            <!-- ═══ Bottom bar: tools + permission + model + submit ═══ -->
            <div
              class="border-t border-[var(--color-border-separator)] pt-3"
              :class="
                isMobileComposer
                  ? 'flex flex-wrap items-center gap-2'
                  : 'flex items-center justify-between'
              "
            >
              <!-- Left: tools -->
              <div class="flex shrink-0 items-center gap-2">
                <div ref="plusMenuRef" class="relative">
                  <button
                    @click="plusMenuOpen = !plusMenuOpen"
                    aria-label="Open composer tools"
                    class="text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)]"
                    :class="
                      isMobileComposer
                        ? 'inline-flex h-11 w-11 items-center justify-center rounded-xl'
                        : 'rounded-lg p-1.5'
                    "
                  >
                    <span class="material-symbols-outlined text-[18px]">add</span>
                  </button>

                  <!-- Plus dropdown -->
                  <div
                    v-if="plusMenuOpen"
                    class="absolute bottom-full left-0 mb-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] py-1 shadow-[var(--shadow-dropdown)]"
                    :class="
                      isMobileComposer
                        ? 'w-[min(240px,calc(100vw-32px))]'
                        : 'w-[240px]'
                    "
                  >
                    <button
                      @click="openAttachmentPicker"
                      class="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-surface-hover)]"
                    >
                      <span
                        class="material-symbols-outlined text-[18px] text-[var(--color-text-secondary)]"
                      >
                        attach_file
                      </span>
                      {{ t('empty.addFiles') }}
                    </button>
                    <button
                      @click="insertSlashCommand"
                      class="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-surface-hover)]"
                    >
                      <span
                        class="w-5 text-center text-[18px] font-bold text-[var(--color-text-secondary)]"
                      >
                        /
                      </span>
                      {{ t('empty.slashCommands') }}
                    </button>
                  </div>
                </div>

                <PermissionModeSelector
                  :work-dir="workDir"
                  :compact="isMobileComposer"
                  :value="draftPermissionMode"
                  @change="draftPermissionMode = $event"
                />
              </div>

              <!-- Right: context indicator + model + submit -->
              <div
                class="flex items-center gap-3"
                :class="
                  isMobileComposer
                    ? 'flex min-w-0 flex-1 items-center justify-end gap-2'
                    : ''
                "
              >
                <ContextUsageIndicator
                  chat-state="idle"
                  :message-count="0"
                  :runtime-selection-key="draftRuntimeSelectionKey"
                  :fallback-model-label="draftModelLabel"
                  draft
                  :compact="isMobileComposer"
                />
                <ModelSelector
                  :runtime-key="DRAFT_RUNTIME_SELECTION_KEY"
                  :disabled="isSubmitting"
                  :compact="isMobileComposer"
                />
                <button
                  @click="handleSubmit"
                  :disabled="!canSubmit"
                  :aria-label="t('common.run')"
                  :title="isMobileComposer ? t('common.run') : undefined"
                  class="flex shrink-0 items-center justify-center gap-1 rounded-lg bg-[image:var(--gradient-btn-primary)] text-xs font-semibold text-[var(--color-btn-primary-fg)] shadow-[var(--shadow-button-primary)] transition-all hover:brightness-105 disabled:opacity-30"
                  :class="
                    isMobileComposer
                      ? 'h-11 w-11 rounded-xl px-0 py-0'
                      : 'w-[112px] px-3 py-1.5'
                  "
                >
                  <span v-if="!isMobileComposer">{{ t('common.run') }}</span>
                  <span class="material-symbols-outlined text-[14px]">arrow_forward</span>
                </button>
              </div>
            </div>
          </div>

          <!-- ═══ Repository Launch Controls (desktop: inside panel) ═══ -->
          <RepositoryLaunchControls
            v-if="!isMobileComposer"
            :work-dir="workDir"
            @work-dir-change="handleWorkDirChange"
            :branch="selectedBranch"
            @branch-change="selectedBranch = $event"
            :use-worktree="useWorktree"
            @use-worktree-change="useWorktree = $event"
            @launch-ready-change="repositoryLaunchReady = $event"
            :disabled="isSubmitting"
            placement="composer"
          />
        </div>

        <!-- ═══ Repository Launch Controls (mobile: below panel) ═══ -->
        <RepositoryLaunchControls
          v-if="isMobileComposer"
          :work-dir="workDir"
          @work-dir-change="handleWorkDirChange"
          :branch="selectedBranch"
          @branch-change="selectedBranch = $event"
          :use-worktree="useWorktree"
          @use-worktree-change="useWorktree = $event"
          @launch-ready-change="repositoryLaunchReady = $event"
          :disabled="isSubmitting"
        />
      </div>
    </div>

    <!-- Hidden file input -->
    <input
      ref="fileInputRef"
      type="file"
      multiple
      class="hidden"
      @change="handleFileSelect"
    />
  </div>
</template>

<style scoped>
/* No additional scoped styles — all styling is Tailwind + CSS vars,
   kept verbatim from the React source. */
</style>
