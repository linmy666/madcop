<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useSettingsStore } from '../../stores/settingsStore'
import { useChatStore } from '../../stores/chatStore'
import { useSessionStore } from '../../stores/sessionStore'
import { useTabStore } from '../../stores/tabs'

/**
 * PermissionModeSelector — Vue 3 port of controls/PermissionModeSelector.tsx
 * Dropdown selector for agent execution permissions.
 * Prop-driven for controlled mode, store-driven for uncontrolled.
 */

type PermissionMode = 'default' | 'acceptEdits' | 'plan' | 'bypassPermissions' | 'dontAsk'

interface Props {
  workDir?: string
  compact?: boolean
  value?: PermissionMode
  onChange?: (mode: PermissionMode) => void
}

const props = withDefaults(defineProps<Props>(), {
  workDir: '~',
  compact: false,
})

const emit = defineEmits<{
  change: [mode: PermissionMode]
}>()

const open = ref(false)
const confirmDialog = ref(false)
const menuRef = ref<HTMLElement | null>(null)
const rootRef = ref<HTMLElement | null>(null)

const settingsStore = useSettingsStore()
const chatStore = useChatStore()
const sessionStore = useSessionStore()
const tabStore = useTabStore()

const isControlled = computed(() => props.value !== undefined)
const activeSession = computed(() => {
  if (!tabStore.activeTabId) return null
  return sessionStore.sessions.find(s => s.id === tabStore.activeTabId) || null
})
const currentMode = computed((): PermissionMode => {
  if (isControlled.value) return props.value!
  return (activeSession.value?.permissionMode as PermissionMode) || settingsStore.permissionMode
})

const MODE_ICONS: Record<PermissionMode, string> = {
  default: 'verified_user',
  acceptEdits: 'bolt',
  plan: 'architecture',
  bypassPermissions: 'gavel',
  dontAsk: 'gavel',
}

const MODE_LABELS: Record<PermissionMode, string> = {
  default: 'Ask permissions',
  acceptEdits: 'Auto-accept',
  plan: 'Plan mode',
  bypassPermissions: 'Bypass permissions',
  dontAsk: "Don't ask",
}

const PERMISSION_ITEMS: Array<{
  value: PermissionMode
  label: string
  description: string
  icon: string
  color?: string
}> = [
  { value: 'default', label: 'Ask permissions', description: 'Agent asks before every action', icon: 'verified_user' },
  { value: 'acceptEdits', label: 'Auto-accept', description: 'Accept file edits automatically', icon: 'bolt' },
  { value: 'plan', label: 'Plan mode', description: 'Agent only plans, never executes', icon: 'architecture', color: 'text-[var(--color-text-tertiary)]' },
  { value: 'bypassPermissions', label: 'Bypass permissions', description: 'Agent executes without asking', icon: 'gavel', color: 'text-[var(--color-error)]' },
]

function selectMode(mode: PermissionMode) {
  if (mode === 'bypassPermissions') {
    open.value = false
    confirmDialog.value = true
    return
  }
  if (isControlled.value) {
    emit('change', mode)
  } else if (tabStore.activeTabId) {
    chatStore.setSessionPermissionMode(tabStore.activeTabId, mode)
  }
  open.value = false
}

function closeOnClickOutside(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node) &&
      menuRef.value && !menuRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') open.value = false
}

onMounted(() => {
  document.addEventListener('mousedown', closeOnClickOutside)
  document.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  document.removeEventListener('mousedown', closeOnClickOutside)
  document.removeEventListener('keydown', onKeydown)
})

const workDir = computed(() => props.workDir || activeSession.value?.workDir || '~')
const isMobile = ref(false) // Would check useMobileViewport hook
</script>

<template>
  <div ref="rootRef" class="relative">
    <button
      @click="open = !open"
      :class="[
        'flex items-center bg-[var(--color-surface-container-low)] font-medium text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)]',
        compact ? (isMobile ? 'h-11 w-11 justify-center rounded-xl p-0' : 'h-8 w-8 justify-center rounded-full p-0')
          : 'gap-1.5 rounded-full px-2.5 py-1.5 text-xs'
      ]"
      :title="compact ? MODE_LABELS[currentMode] : undefined"
    >
      <span class="material-symbols-outlined text-[14px]">{{ MODE_ICONS[currentMode] }}</span>
      <span v-if="!compact">{{ MODE_LABELS[currentMode] }}</span>
      <span v-if="!compact" class="material-symbols-outlined text-[12px]">expand_more</span>
    </button>

    <div v-if="open && !isMobile"
         ref="menuRef"
         class="absolute left-0 bottom-full mb-2 w-[320px] rounded-xl bg-[var(--color-surface-container-lowest)] border border-[var(--color-border)] shadow-[var(--shadow-dropdown)] z-50 py-2">
      <div class="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--color-outline)]">
        Execution Permissions
      </div>
      <div role="menu">
        <button v-for="item in PERMISSION_ITEMS" :key="item.value"
                @click="selectMode(item.value)"
                role="menuitem"
                :class="[
                  'flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg>[var(--color-surface-hover)]',
                  item.value === currentMode ? 'bg>[var(--color-surface-selected)]' : ''
                ]">
          <span :class="['material-symbols-outlined mt-0.5 text-[20px]', item.color || 'text>[var(--color-text-secondary)]']">{{ item.icon }}</span>
          <div class="min-w-0 flex-1">
            <div class="text-sm font-semibold text>[var(--color-text-primary)]">{{ item.label }}</div>
            <div class="mt-0.5 text-xs text>[var(--color-text-tertiary)]">{{ item.description }}</div>
          </div>
          <span v-if="item.value === currentMode" class="material-symbols-outlined mt-0.5 text-[16px] text>[var(--color-brand)]" style="fontVariationSettings: 'FILL' 1">check_circle</span>
        </button>
      </div>
    </div>

    <!-- Bypass confirmation dialog -->
    <Teleport to="body">
      <div v-if="confirmDialog" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="fixed inset-0 bg-black/50" @click="confirmDialog = false" />
        <div class="relative z-10 bg>[var(--color-surface)] rounded-xl border border>[var(--color-border)] p-5 max-w-sm mx-4 shadow-xl">
          <p class="text-sm font-semibold text>[var(--color-error)] mb-3">Enable Bypass Permissions?</p>
          <p class="text-xs text>[var(--color-text-secondary)] mb-3">This will allow the agent to execute actions without asking for permission.</p>
          <div class="flex items-center gap-2 rounded-lg border border>[var(--color-border)] bg>[var(--color-surface-container)] px-3 py-2 mb-3" :title="workDir">
            <span class="material-symbols-outlined shrink-0 text-[16px] text>[var(--color-text-tertiary)]">folder</span>
            <code class="truncate text-xs font-mono text>[var(--color-text-primary)]">{{ workDir }}</code>
          </div>
          <ul class="space-y-1.5 text-xs text>[var(--color-text-secondary)] mb-4">
            <li class="flex items-start gap-2">
              <span class="material-symbols-outlined mt-0.5 text-[14px] text>[var(--color-error)]">check</span>
              Read and write files
            </li>
            <li class="flex items-start gap-2">
              <span class="material-symbols-outlined mt-0.5 text-[14px] text>[var(--color-error)]">check</span>
              Execute shell commands
            </li>
            <li class="flex items-start gap-2">
              <span class="material-symbols-outlined mt-0.5 text-[14px] text>[var(--color-error)]">check</span>
              Install packages
            </li>
          </ul>
          <div class="flex justify-end gap-2">
            <button @click="confirmDialog = false" class="px-3 py-1.5 text-xs text>[var(--color-text-secondary)] hover:underline">Cancel</button>
            <button @click="selectMode('bypassPermissions')" class="px-3 py-1.5 bg>[var(--color-error)] text>[var(--color-on-error)] rounded text-xs font-semibold">Enable Bypass</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
