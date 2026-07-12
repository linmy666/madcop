<script setup lang="ts">
/**
 * ChatInput — Vue 3 port of components/chat/ChatInput.tsx (1369 lines)
 *
 * The main composer: textarea + attachments + mode selector + slash commands
 * + file search + permission selector + send/stop button + queued messages.
 *
 * Uses Pinia stores for state management. The component is self-contained
 * for the input UI but calls store methods for actual actions.
 *
 * Key differences from React:
 * - useState → ref()
 * - useCallback/useMemo → functions / computed()
 * - useEffect → watch() / onMounted()
 * - useRef → ref()
 * - isDesktopRuntime/useMobileViewport → inline detection
 * - useComposerFileDrop → inline drag handlers
 * - shouldSubmitOnEnter → inline check
 * - useTeamStore/useUIStore → stubbed (not in Vue yet)
 */

import { ref, computed, watch, onMounted, onUnmounted, nextTick, useTemplateRef } from 'vue'
import { useChatStore, type AttachmentRef, type QueuedUserMessage } from '../../stores/chatStore'
import { useTabStore } from '../../stores/tabs'
import { useSessionStore } from '../../stores/sessionStore'
import { useSettingsStore } from '../../stores/settingsStore'
import { useSessionRuntimeStore } from '../../stores/sessionRuntimeStore'
import { useWorkspaceChatContextStore } from '../../stores/workspaceChatContextStore'
import { useTranslation } from '../../i18n'
import { detectAmbiguity } from '../../lib/clarify'
import AttachmentGallery from './AttachmentGallery.vue'
import ModeSelector from './ModeSelector.vue'
import ClarifyHints from './ClarifyHints.vue'
import PermissionModeSelector from '../controls/PermissionModeSelector.vue'
import RepositoryLaunchControls from '../shared/RepositoryLaunchControls.vue'
import Tooltip from '../common/Tooltip.vue'
import FileSearchMenu from './FileSearchMenu.vue'
import ContextUsageIndicator from './ContextUsageIndicator.vue'
import ModelSelector from '../controls/ModelSelector.vue'
import LocalSlashCommandPanel from './LocalSlashCommandPanel.vue'
import ComposerDropOverlay from './ComposerDropOverlay.vue'
import ProjectContextChip from '../shared/ProjectContextChip.vue'
import {
  findSlashTrigger,
  replaceSlashToken,
  filterSlashCommands,
  mergeSlashCommands,
  getLocalizedFallbackCommands,
  appendAgentSlashCommands,
  buildAgentSlashCommands,
  resolveSlashUiAction,
  type SlashCommand,
  type LocalSlashCommandName,
  type SlashUiAction,
} from './composerUtils'

// ─── Inline helpers (no external deps) ───────────────────────────

function isDesktopRuntime(): boolean {
  try {
    return typeof window !== 'undefined' &&
      (navigator.userAgent.includes('Electron') ||
       navigator.userAgent.includes('madcop') ||
       location.protocol === 'file:')
  } catch {
    return false
  }
}

function isMobileViewport(): boolean {
  try {
    return typeof window !== 'undefined' && window.innerWidth < 768
  } catch {
    return false
  }
}

function shouldSubmitOnEnter(event: KeyboardEvent, behavior: string): boolean {
  if (event.key !== 'Enter') return false
  if (event.shiftKey) return false
  if (behavior === 'enter') return true
  if (behavior === 'ctrl-enter' && (event.ctrlKey || event.metaKey)) return true
  return false
}

// ─── Types ───────────────────────────────────────────────────────

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
  mimeType?: string
  previewUrl?: string
  data?: string
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

// ─── Stores ──────────────────────────────────────────────────────

const t = useTranslation()
const chatStore = useChatStore()
const tabStore = useTabStore()
const sessionStore = useSessionStore()
const settingsStore = useSettingsStore()
const runtimeStore = useSessionRuntimeStore()
const workspaceStore = useWorkspaceChatContextStore()

// ─── Local state ───────────────────────────────────────────────

const input = ref('')
const clarifyDismissed = ref(false)  // user clicked × to hide clarification
const clarifications = computed(() => {
  if (clarifyDismissed.value) return []
  // Only show clarifications after the user has typed at least 3 chars
  if (input.value.trim().length < 3) return []
  return detectAmbiguity(input.value)
})

function pickClarification(slot: string, value: string) {
  // Append the clarification to the input in a natural way:
  //  - "今天天气怎么样" + "北京" → "今天天气怎么样（北京）"
  //  - "best restaurant" + "NYC" → "best restaurant in NYC"
  const slotPhrases: Record<string, { prefix?: string; suffix?: string }> = {
    location: { suffix: `（${value}）` },
    time: { suffix: `（${value}）` },
    subject: { suffix: `（${value}）` },
    method: { suffix: `（${value}）` },
  }
  const conf = slotPhrases[slot] || { suffix: `（${value}）` }
  if (conf.suffix) input.value = `${input.value.trim()}${conf.suffix}`
}
const inputRef = ref(input) // React inputRef.sync pattern
const attachments = ref<ComposerAttachment[]>([])
const attachmentsRef = ref(attachments) // sync ref
const slashMenuOpen = ref(false)
const slashFilter = ref('')
const slashSelectedIndex = ref(0)
const slashItemRefs = ref<(HTMLButtonElement | null)[]>([])
const fileSearchOpen = ref(false)
const atFilter = ref('')
const atCursorPos = ref(-1)
const plusMenuOpen = ref(false)
const localSlashPanel = ref<LocalSlashCommandName | null>(null)
const selectedMode = ref('react')
const selectedModel = ref('sensenova-6.7-flash-lite')
const composingRef = ref(false)
const previousActiveTabIdRef = ref<string | null>(null)

// Git info
const gitInfo = ref<{ workDir?: string; branch?: string; repoName?: string; worktree?: { enabled?: boolean; slug?: string; sourceWorkDir?: string; path?: string; plannedPath?: string } } | null>(null)

// Launch controls
const launchWorkDir = ref('')
const launchBranch = ref<string | null>(null)
const launchUseWorktree = ref(false)
const launchReady = ref(true)
const launchTransitioning = ref(false)

// Queued message editing
const editingQueuedMessageId = ref<string | null>(null)
const editingQueuedMessageText = ref('')

// Drag
const isDragActive = ref(false)

// Refs
const textareaRef = useTemplateRef<HTMLTextAreaElement>('textareaRef')
const panelRef = useTemplateRef<HTMLDivElement>('panelRef')
const plusMenuRef = useTemplateRef<HTMLDivElement>('plusMenuRef')
const slashMenuRef = useTemplateRef<HTMLDivElement>('slashMenuRef')
const fileSearchRef = useTemplateRef<any>('fileSearchRef')
const fileInputRef = useTemplateRef<HTMLInputElement>('fileInputRef')

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
const composerInsertion = computed(() => sessionState.value?.composerInsertion ?? null)
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

const runtimeSelectionKey = computed(() =>
  runtimeSelection.value
    ? `${runtimeSelection.value.providerId ?? 'official'}:${runtimeSelection.value.modelId}:${runtimeSelection.value.effortLevel ?? 'auto'}`
    : undefined,
)
const runtimeModelLabel = computed(() =>
  runtimeSelection.value?.modelId ?? currentModel.value?.name ?? currentModel.value?.id,
)

const isStreaming = computed(() => chatState.value === 'busy')
const isActive = computed(() => false) // Always let handleSubmit run

const messageCount = computed(() => {
  const loaded = sessionState.value?.messages?.length ?? 0
  const total = activeSession.value?.messageCount ?? 0
  return Math.max(loaded, total)
})

const totalContent = computed(() => {
  const msgs = sessionState.value?.messages ?? []
  return msgs.map((m: any) => m.content || '').join('\n')
})

const workspaceReferences = computed(() => {
  if (!activeTabId.value) return []
  return workspaceStore.referencesBySession[activeTabId.value] || []
})

// Stub for member session (useTeamStore not in Vue yet)
const memberInfo = computed(() => null)
const isMemberSession = computed(() => !!memberInfo.value)
const isWorkspaceMissing = computed(() => activeSession.value?.workDirExists === false)
const hasWorkspaceReferences = computed(() => !isMemberSession.value && workspaceReferences.value.length > 0)
const isHeroComposer = computed(() => props.variant === 'hero' && !isMemberSession.value && !props.compact)
const resolvedWorkDir = computed(() => activeSession.value?.workDir || gitInfo.value?.workDir || undefined)
const showLaunchControls = computed(() => !isMemberSession.value && messageCount.value === 0)
const useCompactControls = computed(() => props.compact || isMobileViewport())
const iconOnlyAction = computed(() => props.compact || isMobileViewport())
const activeLaunchWorkDir = computed(() =>
  showLaunchControls.value ? (launchWorkDir.value || resolvedWorkDir.value || '') : (resolvedWorkDir.value || ''),
)
const embedLaunchControlsInHero = computed(() => false) // v3.0: always show in composer area, never embedded in hero
const pendingSlashUiAction = computed((): SlashUiAction => {
  if (isMemberSession.value || !input.value.trim().startsWith('/')) return null
  return resolveSlashUiAction(input.value.trim().slice(1))
})
const canSubmit = computed(() => {
  // Simplified: just need text or attachments
  return input.value.trim().length > 0 || attachments.value.length > 0
})

function workspaceReferenceToAttachment(reference: { id: string; name: string; kind?: string; path?: string; isDirectory?: boolean; lineStart?: number; lineEnd?: number; note?: string; quote?: string }): ComposerAttachment {
  return {
    id: reference.id,
    name: reference.name,
    type: 'file',
    path: reference.kind === 'chat-selection' ? undefined : reference.path,
    isDirectory: reference.isDirectory,
    lineStart: reference.lineStart,
    lineEnd: reference.lineEnd,
    note: reference.note,
    quote: reference.quote,
  }
}

const composerAttachments = computed<ComposerAttachment[]>(() => [
  ...attachments.value,
  ...workspaceReferences.value.map(workspaceReferenceToAttachment),
])

// ─── Slash commands ────────────────────────────────────────────

const allSlashCommands = computed<SlashCommand[]>(() =>
  appendAgentSlashCommands(
    mergeSlashCommands(slashCommands.value, getLocalizedFallbackCommands(t)),
    agentSlashCommands.value,
  ),
)

const agentSlashCommands = ref<ReturnType<typeof buildAgentSlashCommands>>([])

const filteredCommands = computed<SlashCommand[]>(() =>
  filterSlashCommands(allSlashCommands.value, slashFilter.value),
)

const exactSlashCommand = computed<SlashCommand | null>(() => {
  const normalized = slashFilter.value.trim().toLowerCase()
  if (!normalized) return null
  return filteredCommands.value.find((c) => c.name.toLowerCase() === normalized) ?? null
})

// ─── Helpers ───────────────────────────────────────────────────

const setComposerInput = (value: string) => {
  inputRef.value = value
  input.value = value
}

const setComposerAttachments = (value: ComposerAttachment[] | ((prev: ComposerAttachment[]) => ComposerAttachment[])) => {
  attachments.value = typeof value === 'function' ? value(attachments.value) : value
  attachmentsRef.value = attachments.value
}

function insertComposerTokenAtRange(value: string, start: number, end: number, token: string) {
  const boundedStart = Math.max(0, Math.min(start, value.length))
  const boundedEnd = Math.max(boundedStart, Math.min(end, value.length))
  const before = value.slice(0, boundedStart)
  const after = value.slice(boundedEnd)
  const leadingSpace = before.length > 0 && !/\s$/.test(before) ? ' ' : ''
  const trailingSpace = after.length > 0 && !/^\s/.test(after) ? ' ' : ''
  const insertion = `${leadingSpace}${token}${trailingSpace}`
  return {
    value: `${before}${insertion}${after}`,
    cursorPos: before.length + insertion.length,
  }
}

const saveComposerDraft = (sessionId: string) => {
  const draft = {
    input: inputRef.value,
    attachments: attachmentsRef.value,
  }
  if (draft.input.length === 0 && draft.attachments.length === 0) {
    chatStore.clearComposerDraft(sessionId)
    return
  }
  chatStore.setComposerDraft(sessionId, draft)
}

// ─── Detect @ trigger (file search) ────────────────────────────

const detectAtTrigger = (value: string, cursorPos: number) => {
  const textBeforeCursor = value.slice(0, cursorPos)
  let pos = -1
  for (let i = textBeforeCursor.length - 1; i >= 0; i--) {
    const ch = textBeforeCursor[i]
    if (ch === '@') {
      if (i === 0 || /\s/.test(textBeforeCursor[i - 1] ?? '')) {
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
    return
  }

  const filter = textBeforeCursor.slice(pos + 1)
  atFilter.value = filter
  atCursorPos.value = pos
  slashMenuOpen.value = false
  fileSearchOpen.value = true
}

// ─── Detect slash trigger ──────────────────────────────────────

const detectSlashTrigger = (value: string, cursorPos: number) => {
  const token = findSlashTrigger(value, cursorPos)
  if (!token) {
    slashMenuOpen.value = false
    return
  }
  fileSearchOpen.value = false
  slashFilter.value = token.filter
  slashMenuOpen.value = true
}

// ─── Input change handler ──────────────────────────────────────

function handleInputChange(event: Event) {
  const target = event.target as HTMLTextAreaElement
  const value = target.value
  if (isMemberSession.value) {
    setComposerInput(value)
    return
  }
  const cursorPos = target.selectionStart ?? value.length
  setComposerInput(value)
  detectSlashTrigger(value, cursorPos)
  detectAtTrigger(value, cursorPos)
}

// ─── Auto-resize textarea ──────────────────────────────────────

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 200)}px`
}

watch(input, () => nextTick(autoResize))
onMounted(() => nextTick(autoResize))

// ─── Cursor positioning for slash commands ─────────────────────

const selectSlashCommand = (command: string) => {
  const el = textareaRef.value
  if (!el) return
  const cursorPos = el.selectionStart ?? input.value.length
  const replacement = replaceSlashToken(input.value, cursorPos, command)
  setComposerInput(replacement.value)
  slashMenuOpen.value = false
  nextTick(() => {
    el.focus()
    el.setSelectionRange(replacement.cursorPos, replacement.cursorPos)
  })
}

// ─── Slash command insertion (from plus menu) ──────────────────

const insertSlashCommand = () => {
  if (isMemberSession.value) return
  const el = textareaRef.value
  const cursorPos = el?.selectionStart ?? input.value.length
  const replacement = replaceSlashToken(input.value, cursorPos, '', { trailingSpace: false })
  setComposerInput(replacement.value)
  plusMenuOpen.value = false
  slashFilter.value = ''
  slashMenuOpen.value = true
  nextTick(() => {
    textareaRef.value?.focus()
    textareaRef.value?.setSelectionRange(replacement.cursorPos, replacement.cursorPos)
  })
}

// ─── Paste handler (image paste) ──────────────────────────────

function handlePaste(event: ClipboardEvent) {
  if (isMemberSession.value) return
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
      setComposerAttachments((prev) => [
        ...prev,
        {
          id,
          name: `pasted-image-${Date.now()}.png`,
          type: 'image',
          mimeType: file.type || 'image/png',
          previewUrl: reader.result as string,
          data: reader.result as string,
        },
      ])
    }
    reader.readAsDataURL(file)
  }
}

// ─── Files to attachments ──────────────────────────────────────

function filesToComposerAttachments(files: FileList | File[]): Promise<ComposerAttachment[]> {
  return Promise.all(
    Array.from(files).map((file) => {
      const id = `att-${Date.now()}-${Math.random().toString(36).slice(2)}`
      const type = file.type.startsWith('image/') ? 'image' : 'file'
      if (type === 'image') {
        return new Promise<ComposerAttachment>((resolve) => {
          const reader = new FileReader()
          reader.onload = () => {
            resolve({
              id,
              name: file.name,
              type: 'image',
              mimeType: file.type,
              previewUrl: reader.result as string,
              data: reader.result as string,
            })
          }
          reader.readAsDataURL(file)
        })
      }
      return Promise.resolve({
        id,
        name: file.name,
        type: 'file',
        path: file.name,
      })
    }),
  )
}

// ─── File select handler ───────────────────────────────────────

function handleFileSelect(event: Event) {
  if (isMemberSession.value) return
  const target = event.target as HTMLInputElement
  const files = target.files
  if (!files) return
  appendFiles(files)
  target.value = ''
}

function appendFiles(files: FileList | File[]) {
  filesToComposerAttachments(files)
    .then((nextAttachments) => {
      if (nextAttachments.length === 0) return
      setComposerAttachments((prev) => [...prev, ...nextAttachments])
    })
    .catch((error) => {
      console.warn('[attachments] Failed to read selected files', error)
    })
}

function openAttachmentPicker() {
  plusMenuOpen.value = false
  if (!isDesktopRuntime()) {
    fileInputRef.value?.click()
    return
  }
  // Desktop runtime: would use native file picker via IPC
  // Fallback to native file input
  fileInputRef.value?.click()
}

// ─── Remove attachment ─────────────────────────────────────────

function removeAttachment(id: string) {
  setComposerAttachments((prev) => prev.filter((a) => a.id !== id))
  if (activeTabId.value) workspaceStore.removeReference(activeTabId.value, id)
}

// ─── Queued message editing ────────────────────────────────────

const startEditingQueuedMessage = (messageId: string, content: string) => {
  editingQueuedMessageId.value = messageId
  editingQueuedMessageText.value = content
}

const saveQueuedMessageEdit = () => {
  if (!activeTabId.value || !editingQueuedMessageId.value) return
  const nextContent = editingQueuedMessageText.value.trim()
  if (!nextContent) return
  chatStore.updateQueuedUserMessage(activeTabId.value, editingQueuedMessageId.value, nextContent)
  editingQueuedMessageId.value = null
  editingQueuedMessageText.value = ''
}

const cancelQueuedMessageEdit = () => {
  editingQueuedMessageId.value = null
  editingQueuedMessageText.value = ''
}

// ─── Replace empty session ─────────────────────────────────────

const replaceEmptySession = async (workDir: string, repository?: { branch?: string | null; worktree?: boolean }) => {
  if (!activeTabId.value) return null
  const oldId = activeTabId.value
  // Create new session and replace tab — simplified for Vue
  // TODO: Implement proper session replacement logic
  return oldId // stub
}

// ─── Launch workdir change ─────────────────────────────────────

const handleLaunchWorkDirChange = async (newWorkDir: string) => {
  launchWorkDir.value = newWorkDir
  launchBranch.value = null
  launchUseWorktree.value = false
  launchReady.value = !newWorkDir
  if (!activeTabId.value) return

  launchTransitioning.value = true
  try {
    await replaceEmptySession(newWorkDir)
  } catch {
    // Toast would go here: useUIStore().addToast(...)
  } finally {
    launchTransitioning.value = false
  }
}

// ─── Submit handler ────────────────────────────────────────────

const handleSubmit = async () => {
  const text = input.value.trim()
  if (!text && (!attachments.value.length && !hasWorkspaceReferences.value) || isMemberSession.value) return

  // Slash UI action: panel
  if (pendingSlashUiAction.value?.type === 'panel') {
    localSlashPanel.value = pendingSlashUiAction.value.command as LocalSlashCommandName
    setComposerInput('')
    slashMenuOpen.value = false
    fileSearchOpen.value = false
    plusMenuOpen.value = false
    return
  }

  // Slash UI action: settings tab
  if (pendingSlashUiAction.value?.type === 'settings') {
    // Would open settings: useUIStore().setPendingSettingsTab(...)
    setComposerInput('')
    slashMenuOpen.value = false
    fileSearchOpen.value = false
    plusMenuOpen.value = false
    return
  }

  // Check launch controls
  if (showLaunchControls.value && (!launchReady.value || launchTransitioning.value)) return

  // Workspace reference prompt (stub — returns empty in Vue)
  const workspaceReferencePrompt = !isMemberSession.value
    ? workspaceStore.formatWorkspaceReferencePrompt(workspaceReferences.value)
    : ''

  const contentForModel = [workspaceReferencePrompt, text].filter(Boolean).join('\n\n')

  const uploadAttachmentPayload: AttachmentRef[] = attachments.value.map((a) => ({
    id: a.id,
    name: a.name,
    type: a.type,
    path: a.path,
    previewUrl: (a as any).previewUrl || (a as any).data,
  }))

  const workspaceAttachmentPayload: AttachmentRef[] = workspaceReferences.value
    .filter((r: any) => r.kind !== 'chat-selection')
    .map((r: any) => ({
      id: r.id,
      name: r.name,
      type: 'file',
      path: r.absolutePath ?? r.path,
    }))

  const visibleAttachmentPayload: AttachmentRef[] = [
    ...uploadAttachmentPayload,
    ...workspaceReferences.value.map((r: any) => ({
      id: r.id,
      name: r.name,
      type: 'file',
      path: r.kind === 'chat-selection' ? undefined : r.path,
    })),
  ]

  let targetSessionId = activeTabId.value!
  if (showLaunchControls.value && activeLaunchWorkDir.value && launchBranch.value) {
    const shouldReplaceForRepositoryLaunch =
      launchUseWorktree.value ||
      (gitInfo.value?.branch ? launchBranch.value !== gitInfo.value.branch : true)
    if (shouldReplaceForRepositoryLaunch) {
      launchTransitioning.value = true
      try {
        const newSessionId = await replaceEmptySession(activeLaunchWorkDir.value, {
          branch: launchBranch.value,
          worktree: launchUseWorktree.value,
        })
        if (!newSessionId) return
        targetSessionId = newSessionId
      } catch {
        // Toast would go here
        return
      } finally {
        launchTransitioning.value = false
      }
    }
  }

  const targetChatState = chatStore.sessions[targetSessionId]?.chatState ?? 'idle'
  if (!isMemberSession.value && targetChatState !== 'idle') {
    chatStore.queueUserMessage(targetSessionId, {
      content: contentForModel,
      attachments: [...uploadAttachmentPayload, ...workspaceAttachmentPayload],
      displayContent: text || (workspaceReferences.value.length > 0
        ? t('chat.contextReferencesOnly', { count: workspaceReferences.value.length })
        : ''),
      displayAttachments: visibleAttachmentPayload,
    })
  } else {
    chatStore.sendMessage(
      targetSessionId,
      contentForModel,
      [...uploadAttachmentPayload, ...workspaceAttachmentPayload],
      {
        displayContent: text || (workspaceReferences.value.length > 0
          ? t('chat.contextReferencesOnly', { count: workspaceReferences.value.length })
          : ''),
        displayAttachments: visibleAttachmentPayload,
        model: selectedModel.value,
      },
    )
  }

  // Clear state
  setComposerInput('')
  setComposerAttachments([])
  if (activeTabId.value) chatStore.clearComposerDraft(activeTabId.value)
  if (targetSessionId !== activeTabId.value) chatStore.clearComposerDraft(targetSessionId)
  if (!isMemberSession.value) {
    workspaceStore.clearReferences(activeTabId.value!)
    if (targetSessionId !== activeTabId.value) workspaceStore.clearReferences(targetSessionId)
  }
  plusMenuOpen.value = false
  slashMenuOpen.value = false
  fileSearchOpen.value = false
  localSlashPanel.value = null
}

// ─── Key handler ───────────────────────────────────────────────

function handleKeydown(event: KeyboardEvent) {
  // Ignore during IME composition
  if (composingRef.value || (event as any).nativeEvent?.isComposing || (event as any).keyCode === 229) return

  // File search navigation
  if (fileSearchOpen.value) {
    const key = event.key
    if (['ArrowDown', 'ArrowUp', 'ArrowRight', 'Enter', 'Tab', 'Escape'].includes(key)) {
      event.preventDefault()
      if (key === 'Escape') {
        fileSearchOpen.value = false
        atFilter.value = ''
        atCursorPos.value = -1
        return
      }
      // Let FileSearchMenu handle it via ref
      fileSearchRef.value?.handleKeyDown?.(event)
      return
    }
    return
  }

  // Local slash panel escape
  if (localSlashPanel.value && event.key === 'Escape') {
    event.preventDefault()
    localSlashPanel.value = null
    return
  }

  // Slash menu navigation
  if (slashMenuOpen.value && filteredCommands.value.length > 0) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      slashSelectedIndex.value = (slashSelectedIndex.value + 1) % filteredCommands.value.length
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      slashSelectedIndex.value = (slashSelectedIndex.value - 1 + filteredCommands.value.length) % filteredCommands.value.length
      return
    }
    if (event.key === 'Enter') {
      const selected = filteredCommands.value[slashSelectedIndex.value]
      if (
        exactSlashCommand.value &&
        selected?.name.toLowerCase() === exactSlashCommand.value.name.toLowerCase() &&
        slashFilter.value.trim().toLowerCase() === exactSlashCommand.value.name.toLowerCase() &&
        shouldSubmitOnEnter(event, chatSendBehavior.value)
      ) {
        event.preventDefault()
        handleSubmit()
        return
      }
      event.preventDefault()
      if (selected) selectSlashCommand(selected.name)
      return
    }
    if (event.key === 'Tab') {
      event.preventDefault()
      const selected = filteredCommands.value[slashSelectedIndex.value]
      if (selected) selectSlashCommand(selected.name)
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      slashMenuOpen.value = false
      return
    }
  }

  // Submit on Enter
  if (shouldSubmitOnEnter(event, chatSendBehavior.value)) {
    event.preventDefault()
    handleSubmit()
  }
}

// ─── Composition events ────────────────────────────────────────

function onCompositionStart() { composingRef.value = true }
function onCompositionEnd() { composingRef.value = false }

// ─── Drag and drop ─────────────────────────────────────────────

function onDragEnter() {
  if (isMemberSession.value || isWorkspaceMissing.value) return
  isDragActive.value = true
}
function onDragOver(event: DragEvent) {
  if (isMemberSession.value || isWorkspaceMissing.value) return
  event.preventDefault()
  isDragActive.value = true
}
function onDragLeave() {
  isDragActive.value = false
}
function onDrop(event: DragEvent) {
  event.preventDefault()
  isDragActive.value = false
  if (isMemberSession.value || isWorkspaceMissing.value) return
  const files = event.dataTransfer?.files
  if (!files || files.length === 0) return
  appendFiles(files)
}

// ─── Click outside handlers ────────────────────────────────────

function onClickOutside(event: MouseEvent) {
  // Plus menu
  if (plusMenuOpen.value && plusMenuRef.value && !plusMenuRef.value.contains(event.target as Node)) {
    plusMenuOpen.value = false
  }
  // Slash menu
  if (slashMenuOpen.value && slashMenuRef.value &&
      !slashMenuRef.value.contains(event.target as Node) &&
      textareaRef.value && !textareaRef.value.contains(event.target as Node)) {
    slashMenuOpen.value = false
  }
  // Local slash panel
  if (localSlashPanel.value && slashMenuRef.value &&
      !slashMenuRef.value.contains(event.target as Node) &&
      textareaRef.value && !textareaRef.value.contains(event.target as Node)) {
    localSlashPanel.value = null
  }
  // File search
  if (fileSearchOpen.value) {
    const menu = document.getElementById('file-search-menu')
    if (menu && !menu.contains(event.target as Node) &&
        textareaRef.value && !textareaRef.value.contains(event.target as Node)) {
      fileSearchOpen.value = false
    }
  }
}

// ─── Tab switch handling ───────────────────────────────────────

watch(activeTabId, (newId, oldId) => {
  if (oldId && oldId !== previousActiveTabIdRef.value) {
    saveComposerDraft(oldId)
  }
  if (previousActiveTabIdRef.value === newId) return
  previousActiveTabIdRef.value = newId

  // Load draft for new tab
  if (newId) {
    const draft = chatStore.sessions[newId]?.composerDraft
    setComposerInput(draft?.input ?? '')
    setComposerAttachments(draft?.attachments ?? [])
  } else {
    setComposerInput('')
    setComposerAttachments([])
  }

  // Reset UI state
  plusMenuOpen.value = false
  slashMenuOpen.value = false
  fileSearchOpen.value = false
  localSlashPanel.value = null
  slashFilter.value = ''
  atFilter.value = ''
  atCursorPos.value = -1
  editingQueuedMessageId.value = null
  editingQueuedMessageText.value = ''
})

// ─── Composer prefill handling ─────────────────────────────────

watch(composerPrefill, (prefill) => {
  if (!prefill || !activeTabId.value) return

  const nextAttachments = (prefill.attachments ?? [])
    .filter((a: any) => a.type === 'image' || a.data)
    .map((a: any, index: number) => ({
      id: `composer-prefill-${prefill.nonce}-${index}`,
      name: a.name,
      type: a.type,
      mimeType: a.mimeType,
      previewUrl: a.type === 'image' ? a.data : undefined,
      data: a.data,
    }))

  if (prefill.mode === 'append') {
    setComposerAttachments((prev) => [...prev, ...nextAttachments])
  } else {
    setComposerInput(prefill.text)
    setComposerAttachments(nextAttachments)
  }
  plusMenuOpen.value = false
  slashMenuOpen.value = false
  fileSearchOpen.value = false
  slashFilter.value = ''
  atFilter.value = ''
  atCursorPos.value = -1

  nextTick(() => {
    textareaRef.value?.focus()
    if (prefill.mode !== 'append') {
      const cursor = prefill.text.length
      textareaRef.value?.setSelectionRange(cursor, cursor)
    }
  })

  chatStore.clearComposerPrefill(activeTabId.value, prefill.nonce)
})

// ─── Composer insertion handling ───────────────────────────────

watch(composerInsertion, (insertion) => {
  if (!insertion || !activeTabId.value || isMemberSession.value) return

  const el = textareaRef.value
  const currentInput = inputRef.value
  const start = el?.selectionStart ?? currentInput.length
  const end = el?.selectionEnd ?? start
  const next = insertComposerTokenAtRange(currentInput, start, end, insertion.text)

  if (insertion.reference) {
    workspaceStore.addReference(activeTabId.value, insertion.reference as any)
  }

  setComposerInput(next.value)
  fileSearchOpen.value = false
  slashMenuOpen.value = false
  atFilter.value = ''
  atCursorPos.value = -1
  chatStore.clearComposerInsertion(activeTabId.value, insertion.nonce)

  nextTick(() => {
    textareaRef.value?.focus()
    textareaRef.value?.setSelectionRange(next.cursorPos, next.cursorPos)
  })
})

// ─── Git info refresh (stub) ───────────────────────────────────

function refreshGitInfo() {
  if (!activeTabId.value || isMemberSession.value) {
    gitInfo.value = null
    return
  }
  // Stub: would call sessionsApi.getGitInfo(activeTabId.value)
  // For now, try to infer from workDir
  if (activeSession.value?.workDir) {
    gitInfo.value = {
      workDir: activeSession.value.workDir,
      branch: null,
      repoName: null,
    }
  }
}

watch([() => activeTabId.value, () => isMemberSession.value, () => messageCount.value, () => slashCommands.value.length], () => {
  if (!activeTabId.value || isMemberSession.value || messageCount.value === 0) {
    gitInfo.value = null
    return
  }
  // Debounce: refresh immediately if idle, after 500ms if busy
  const timeout = chatState.value === 'idle' ? 0 : 500
  setTimeout(refreshGitInfo, timeout)
})

// ─── Agent slash commands (stub) ───────────────────────────────

watch([() => isMemberSession.value, () => resolvedWorkDir.value], () => {
  if (isMemberSession.value) {
    agentSlashCommands.value = []
    return
  }
  // Stub: would call agentsApi.list(resolvedWorkDir)
  // For now, no agent commands
  agentSlashCommands.value = []
})

// ─── Launch workdir sync ───────────────────────────────────────

watch([() => activeSession.value?.workDir, () => gitInfo.value?.workDir, showLaunchControls], () => {
  if (!showLaunchControls.value) return
  const nextWorkDir = activeSession.value?.workDir || gitInfo.value?.workDir || ''
  if (launchWorkDir.value !== nextWorkDir) {
    launchWorkDir.value = nextWorkDir
    launchBranch.value = null
    launchUseWorktree.value = false
    launchReady.value = !nextWorkDir
  }
})

// ─── Slash selected index reset ────────────────────────────────

watch(slashFilter, () => {
  slashSelectedIndex.value = 0
})

// ─── Focus on streaming change ─────────────────────────────────

watch(isStreaming, () => {
  nextTick(() => textareaRef.value?.focus())
})

// ─── Scroll active slash item into view ────────────────────────

watch([slashMenuOpen, slashSelectedIndex], () => {
  if (!slashMenuOpen.value) return
  const activeItem = slashItemRefs.value[slashSelectedIndex.value]
  if (activeItem && typeof activeItem.scrollIntoView === 'function') {
    activeItem.scrollIntoView({ block: 'nearest' })
  }
})

// ─── Member session cleanup ────────────────────────────────────

watch([isMemberSession, () => activeTabId.value], () => {
  if (isMemberSession.value) {
    setComposerAttachments([])
    plusMenuOpen.value = false
    slashMenuOpen.value = false
    fileSearchOpen.value = false
  }
})

// ─── Placeholders ──────────────────────────────────────────────

const composerPlaceholder = computed(() => {
  if (isHeroComposer.value) return t('empty.placeholder')
  if (isWorkspaceMissing.value) return t('chat.placeholderMissing')
  if (isMemberSession.value) return t('teams.memberPlaceholder')
  return t('chat.placeholder')
})

const addFilesLabel = computed(() => (isHeroComposer.value ? t('empty.addFiles') : t('chat.addFiles')))
const slashCommandsLabel = computed(() => (isHeroComposer.value ? t('empty.slashCommands') : t('chat.slashCommands')))

// ─── Lifecycle ─────────────────────────────────────────────────

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
  document.addEventListener('mousedown', onClickOutside)
  nextTick(() => textareaRef.value?.focus())
  // Sync refs
  inputRef.value = input.value
  attachmentsRef.value = attachments.value
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('mousedown', onClickOutside)
  // Save draft on unmount
  if (previousActiveTabIdRef.value) {
    saveComposerDraft(previousActiveTabIdRef.value)
  }
})

// Sync refs on input/attachment changes
watch(input, (v) => { inputRef.value = v })
watch(attachments, (v) => { attachmentsRef.value = v }, { deep: true })

// Reset clarifyDismissed when the user clears the input
watch(input, (v) => {
  if (!v.trim()) clarifyDismissed.value = false
})
</script>

<template>
  <div
    data-testid="chat-input-shell"
    class="w-full"
    :class="[
      isHeroComposer
        ? `bg-[var(--color-surface)] ${isMobileViewport() ? 'px-4 pb-4' : 'px-8 pb-6'}`
        : compact
          ? `border-t border-[var(--color-border)]/70 bg-[var(--color-surface)] ${isMobileViewport() ? 'px-3 pb-[calc(env(safe-area-inset-bottom)+10px)] pt-2' : 'px-3 py-3'}`
          : `bg-[var(--color-surface)] ${isMobileViewport() ? 'px-3 pb-[calc(env(safe-area-inset-bottom)+10px)] pt-2' : 'px-4 py-4'}`,
    ]"
  >
    <div
      :class="[
        isHeroComposer
          ? 'mx-auto flex w-full max-w-3xl flex-col'
          : compact
              ? 'mx-auto max-w-full'
              : `${isMobileViewport() ? 'mx-0 max-w-none' : 'mx-auto max-w-[860px]'}`,
      ]"
    >
      <ClarifyHints
        v-if="clarifications.length > 0"
        :clarifications="clarifications"
        @pick="(p) => pickClarification(p.slot, p.value)"
        @dismiss="clarifyDismissed = true"
      />
      <div
        ref="panelRef"
        data-testid="chat-input-panel"
        :class="[
          isHeroComposer
            ? `glass-panel relative flex flex-col gap-3 overflow-visible rounded-xl p-4 shadow-[var(--shadow-composer)] transition-colors ${isDragActive ? 'composer-drop-target-active' : ''}`
            : compact
              ? `glass-panel relative overflow-visible p-3 transition-colors ${isMobileViewport() ? 'rounded-2xl shadow-[0_-12px_36px_rgba(54,35,28,0.12)]' : 'rounded-xl'} ${isDragActive ? 'composer-drop-target-active' : ''}`
              : `glass-panel relative overflow-visible transition-colors ${isMobileViewport() ? 'rounded-2xl p-3 shadow-[0_-12px_36px_rgba(54,35,28,0.12)]' : 'rounded-xl p-4'} ${isDragActive ? 'composer-drop-target-active' : ''}`,
        ]"
        @dragenter="onDragEnter"
        @dragover="onDragOver"
        @dragleave="onDragLeave"
        @drop="onDrop"
      >
        <!-- Drop overlay -->
        <ComposerDropOverlay
          v-if="isDragActive"
          :title="t('chat.dropFilesTitle')"
          :description="t('chat.dropFilesHint')"
          :test-id="'chat-input-drop-overlay'"
        />

        <!-- File search menu -->
        <FileSearchMenu
          v-if="!isMemberSession && fileSearchOpen"
          ref="fileSearchRef"
          :files="[]"
          :placeholder="t('chat.searchFiles')"
        />

        <!-- Local slash panel -->
        <div v-if="!isMemberSession && localSlashPanel" ref="slashMenuRef" class="relative">
          <LocalSlashCommandPanel
            :filter="slashFilter"
            :current-command="localSlashPanel"
            :on-select="() => { localSlashPanel = null }"
            :on-dismiss="() => { localSlashPanel = null }"
          />
        </div>

        <!-- Slash command dropdown -->
        <div
          v-if="!isMemberSession && slashMenuOpen && filteredCommands.length > 0"
          ref="slashMenuRef"
          class="absolute bottom-full left-0 right-0 z-50 mb-2 overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] shadow-[var(--shadow-dropdown)]"
        >
          <div class="max-h-[300px] overflow-y-auto py-1">
            <button
              v-for="(command, index) in filteredCommands"
              :key="command.name"
              :ref="(el: any) => { if (el) slashItemRefs[index] = el as HTMLButtonElement }"
              @click="selectSlashCommand(command.name)"
              @mouseenter="slashSelectedIndex = index"
              :class="[
                'flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors',
                index === slashSelectedIndex
                  ? 'bg-[var(--color-surface-hover)]'
                  : 'hover:bg-[var(--color-surface-hover)]',
              ]"
            >
              <span class="flex min-w-0 max-w-[52%] shrink-0 items-baseline gap-1.5">
                <span class="shrink-0 text-sm font-semibold text-[var(--color-text-primary)]">
                  /{{ command.name }}
                </span>
                <span v-if="command.argumentHint" class="min-w-0 truncate font-mono text-[11px] text-[var(--color-text-tertiary)]">
                  {{ command.argumentHint }}
                </span>
              </span>
              <span class="min-w-0 flex-1 truncate text-xs text-[var(--color-text-tertiary)]">
                {{ command.description }}
              </span>
            </button>
          </div>
          <div v-if="!isMobileViewport()" class="flex items-center gap-1.5 border-t border-[var(--color-border)] px-4 py-2 text-xs text-[var(--color-text-tertiary)]">
            <kbd class="rounded border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-1.5 py-0.5 font-mono text-[10px]">Up/Down</kbd>
            <span>{{ t('chat.navigate') }}</span>
            <kbd class="ml-2 rounded border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-1.5 py-0.5 font-mono text-[10px]">Enter</kbd>
            <span>{{ t('chat.select') }}</span>
            <kbd class="ml-2 rounded border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-1.5 py-0.5 font-mono text-[10px]">Esc</kbd>
            <span>{{ t('chat.dismiss') }}</span>
          </div>
        </div>

        <!-- Queued user messages -->
        <div
          v-if="!isMemberSession && activeTabId && queuedUserMessages.length > 0"
          data-testid="pending-user-message-list"
          :class="[
            'overflow-hidden border-b border-[var(--color-border-separator)]',
            isHeroComposer ? '-mx-4 -mt-4' : useCompactControls ? '-mx-3 -mt-3' : '-mx-4 -mt-4',
          ]"
        >
          <div
            v-for="message in queuedUserMessages"
            :key="message.id"
            data-testid="pending-user-message"
            :class="[
              'flex min-w-0 items-center gap-2 px-3 py-2 text-xs',
              'border-t border-[var(--color-border-separator)] first:border-t-0',
              'bg-[var(--color-surface-container-lowest)]/70 text-[var(--color-text-secondary)]',
            ]"
          >
            <span class="material-symbols-outlined shrink-0 text-[16px] text-[var(--color-text-tertiary)]" aria-hidden="true">
              subdirectory_arrow_right
            </span>
            <!-- Editing mode -->
            <template v-if="editingQueuedMessageId === message.id">
              <input
                :value="editingQueuedMessageText"
                @input="editingQueuedMessageText = ($event.target as HTMLInputElement).value"
                @keydown.enter="saveQueuedMessageEdit"
                @keydown.escape="cancelQueuedMessageEdit"
                :aria-label="t('chat.pendingMessageEditInput')"
                class="min-w-0 flex-1 rounded-[6px] border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-xs text-[var(--color-text-primary)] outline-none focus:border-[var(--color-border-focus)]"
                autofocus
              />
              <button
                type="button"
                @click="saveQueuedMessageEdit"
                :disabled="!editingQueuedMessageText.trim()"
                class="shrink-0 rounded-[6px] px-2 py-1 font-semibold text-[var(--color-brand)] hover:bg-[var(--color-surface-hover)] disabled:opacity-40"
              >
                {{ t('common.save') }}
              </button>
              <button
                type="button"
                @click="cancelQueuedMessageEdit"
                class="shrink-0 rounded-[6px] px-2 py-1 font-medium text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)]"
              >
                {{ t('common.cancel') }}
              </button>
            </template>
            <!-- Display mode -->
            <template v-else>
              <span class="min-w-0 flex-1 truncate font-medium" :title="message.displayContent">
                {{ message.displayContent }}
              </span>
              <button
                type="button"
                @click="chatStore.sendQueuedUserMessage(activeTabId!, message.id)"
                :aria-label="t('chat.pendingMessageGuideNow')"
                :title="t('chat.pendingMessageGuideNow')"
                class="inline-flex h-7 shrink-0 items-center gap-1 rounded-[6px] px-2 font-semibold text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
              >
                <span class="material-symbols-outlined text-[15px]" aria-hidden="true">subdirectory_arrow_right</span>
                <span>{{ t('chat.pendingMessageGuide') }}</span>
              </button>
              <button
                type="button"
                @click="startEditingQueuedMessage(message.id, message.displayContent)"
                :aria-label="t('chat.pendingMessageEdit')"
                :title="t('chat.pendingMessageEdit')"
                class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
              >
                <span class="material-symbols-outlined text-[15px]" aria-hidden="true">edit</span>
              </button>
              <button
                type="button"
                @click="chatStore.removeQueuedUserMessage(activeTabId!, message.id)"
                :aria-label="t('chat.pendingMessageDelete')"
                :title="t('chat.pendingMessageDelete')"
                class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-error)]"
              >
                <span class="material-symbols-outlined text-[15px]" aria-hidden="true">delete</span>
              </button>
            </template>
          </div>
        </div>

        <!-- Attachment gallery -->
        <template v-if="composerAttachments.length > 0">
          <AttachmentGallery
            v-if="isHeroComposer"
            :attachments="composerAttachments"
            :variant="'composer'"
            @remove="removeAttachment"
          />
          <div v-else class="px-3 pt-3">
            <AttachmentGallery
              :attachments="composerAttachments"
              :variant="'composer'"
              @remove="removeAttachment"
            />
          </div>
        </template>

        <!-- Textarea: hero variant -->
        <div v-if="isHeroComposer" class="flex items-start gap-3">
          <textarea
            ref="textareaRef"
            :value="input"
            @input="handleInputChange"
            @keydown="handleKeydown"
            @compositionstart="onCompositionStart"
            @compositionend="onCompositionEnd"
            @paste="handlePaste"
            :placeholder="composerPlaceholder"
            :disabled="isWorkspaceMissing"
            rows="2"
            class="flex-1 resize-none border-none bg-transparent py-2 leading-relaxed text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-tertiary)] disabled:opacity-50"
          />
        </div>

        <!-- Textarea: default variant -->
        <textarea
          v-else
          ref="textareaRef"
          :value="input"
          @input="handleInputChange"
          @keydown="handleKeydown"
          @compositionstart="onCompositionStart"
          @compositionend="onCompositionEnd"
          @paste="handlePaste"
          :placeholder="composerPlaceholder"
          :disabled="isWorkspaceMissing"
          rows="1"
          :class="`w-full resize-none bg-transparent text-sm leading-relaxed text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-tertiary)] disabled:opacity-50 ${
            useCompactControls ? 'py-1.5' : 'py-2'
          }`"
        />

        <!-- Toolbar -->
        <div
          data-testid="chat-input-toolbar"
          :class="[
            isHeroComposer
              ? 'flex items-center justify-between border-t border-[var(--color-border-separator)] pt-3'
              : `mt-2 flex items-center justify-between border-t border-[var(--color-border-separator)] ${
                  useCompactControls ? '-mx-3 -mb-3 gap-2 px-2.5 py-2' : '-mx-4 -mb-4 px-3 py-3'
                }`,
          ]"
        >
          <!-- Left side -->
          <div class="flex min-w-0 items-center gap-2">
            <template v-if="!isMemberSession">
              <!-- Plus menu -->
              <div ref="plusMenuRef" class="relative">
                <button
                  @click="plusMenuOpen = !plusMenuOpen"
                  :aria-label="'Open composer tools'"
                  :class="[
                    'text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)]',
                    isMobileViewport() ? 'inline-flex h-11 w-11 items-center justify-center rounded-xl' : 'rounded-[var(--radius-md)] p-1.5',
                  ]"
                >
                  <span class="material-symbols-outlined text-[18px]">add</span>
                </button>

                <div
                  v-if="plusMenuOpen"
                  :class="[
                    'absolute bottom-full left-0 z-50 mb-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] py-1 shadow-[var(--shadow-dropdown)]',
                    isMobileViewport() ? 'w-[min(240px,calc(100vw-32px))]' : 'w-[240px]',
                  ]"
                >
                  <button
                    @click="openAttachmentPicker"
                    class="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-[var(--color-surface-hover)]"
                  >
                    <span class="material-symbols-outlined text-[18px] text-[var(--color-text-secondary)]">attach_file</span>
                    <span class="text-sm text-[var(--color-text-primary)]">{{ addFilesLabel }}</span>
                  </button>
                  <button
                    @click="insertSlashCommand"
                    class="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-[var(--color-surface-hover)]"
                  >
                    <span class="w-[24px] text-center text-[18px] font-bold text-[var(--color-text-secondary)]">/</span>
                    <span class="text-sm text-[var(--color-text-primary)]">{{ slashCommandsLabel }}</span>
                  </button>
                </div>
              </div>

              <PermissionModeSelector :compact="useCompactControls" />
            </template>
          </div>

          <!-- Right side -->
          <div class="flex min-w-0 items-center gap-2">
            <template v-if="!isMemberSession && activeTabId">
              <ContextUsageIndicator
                :session-id="activeTabId"
                :chat-state="chatState"
                :message-count="messageCount"
                :total-content="totalContent"
                :runtime-selection-key="runtimeSelectionKey"
                :fallback-model-label="runtimeModelLabel"
                :compact="useCompactControls"
                :refresh-nonce="sessionState?.compactCount ?? 0"
                :t="t"
              />

              <ModelSelector
                :compact="useCompactControls"
                :disabled="isSubmitting"
                :selected-model="selectedModel"
                @update:selected-model="(m: string) => { selectedModel = m }"
              />
              <ModeSelector
                :current-mode="selectedMode"
                @mode-change="(m: string) => { selectedMode = m }"
                :compact="useCompactControls"
              />
            </template>

            <!-- Send / Stop button -->
            <Tooltip
              :label="
                !isMemberSession && isActive
                  ? t('chat.stopTitle')
                  : (isMemberSession ? t('common.send') : t('common.run'))
              "
            >
              <button
                :disabled="!isMemberSession && isActive ? false : !canSubmit"
                @click="handleSubmit" 
                :aria-label="(!isMemberSession && isActive) ? t('common.stop') : (isMemberSession ? t('common.send') : t('common.run'))"
                :title="
                  !isMemberSession && isActive
                    ? t('chat.stopTitle')
                    : iconOnlyAction
                      ? (isMemberSession ? t('common.send') : t('common.run'))
                      : undefined
                "
                :class="[
                  'flex shrink-0 items-center justify-center gap-1 rounded-lg text-xs font-semibold transition-all hover:brightness-105 disabled:opacity-30',
                  iconOnlyAction
                    ? `${isMobileViewport() ? 'h-11 w-11 rounded-xl px-0 py-0' : 'h-8 w-8 px-0 py-0'}`
                    : 'w-[112px] px-3 py-1.5',
                  !isMemberSession && isActive
                    ? 'bg-[var(--color-error-container)] text-[var(--color-on-error-container)]'
                    : 'bg-[image:var(--gradient-btn-primary)] text-[var(--color-btn-primary-fg)] shadow-[var(--shadow-button-primary)]',
                ]"
              >
                <span class="material-symbols-outlined text-[14px]">
                  {{ !isMemberSession && isActive ? 'stop' : 'arrow_forward' }}
                </span>
                <span v-if="!iconOnlyAction">
                  {{ !isMemberSession && isActive ? t('common.stop') : (isMemberSession ? t('common.send') : t('common.run')) }}
                </span>
              </button>
            </Tooltip>
          </div>
        </div>

        <!-- Embed launch controls in hero composer -->
        <div v-if="embedLaunchControlsInHero" class="-mx-4 -mb-4 mt-3">
          <RepositoryLaunchControls
            :work-dir="activeLaunchWorkDir"
            :branch="launchBranch"
            :use-worktree="launchUseWorktree"
            @work-dir-change="handleLaunchWorkDirChange"
            @branch-change="(b: string | null) => { launchBranch = b }"
            @use-worktree-change="(e: boolean) => { launchUseWorktree = e }"
            @launch-ready-change="(r: boolean) => { launchReady = r }"
            :disabled="isActive || launchTransitioning"
            :placement="'composer'"
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

      <!-- Project context chip / Launch controls below composer -->
      <div
        v-if="!isMemberSession && !embedLaunchControlsInHero"
        :class="useCompactControls ? 'mt-2 flex min-w-0 px-1' : 'mt-3 px-1'"
      >
        <template v-if="messageCount > 0">
          <ProjectContextChip
            :work-dir="resolvedWorkDir"
            :repo-name="gitInfo?.repoName || null"
            :branch="gitInfo?.branch || null"
            :source-work-dir="gitInfo?.worktree?.sourceWorkDir || null"
            :is-worktree="!!gitInfo?.worktree?.enabled"
            :worktree-slug="gitInfo?.worktree?.slug || null"
            :worktree-path="gitInfo?.worktree?.path || gitInfo?.worktree?.plannedPath || null"
            :compact="useCompactControls"
          />
        </template>
        <template v-else>
          <RepositoryLaunchControls
            :work-dir="activeLaunchWorkDir"
            :branch="launchBranch"
            :use-worktree="launchUseWorktree"
            @work-dir-change="handleLaunchWorkDirChange"
            @branch-change="(b: string | null) => { launchBranch = b }"
            @use-worktree-change="(e: boolean) => { launchUseWorktree = e }"
            @launch-ready-change="(r: boolean) => { launchReady = r }"
            :disabled="isActive || launchTransitioning"
          />
        </template>
      </div>
    </div>
  </div>
</template>
