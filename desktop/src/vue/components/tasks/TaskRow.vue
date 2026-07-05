<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

/**
 * TaskRow — Vue 3 port of components/tasks/TaskRow.tsx
 * Row for a scheduled cron task with run/edit/delete actions.
 * Prop-driven: parent passes task, showLogs, onToggleLogs.
 * No React store imports — uses emits for actions.
 */

export interface CronTask {
  id: string
  name: string
  description?: string
  cron: string
  enabled: boolean
  createdAt: string
  lastFiredAt?: string
}

export interface TaskRowProps {
  task: CronTask
  showLogs: boolean
}

const props = defineProps<TaskRowProps>()
const emit = defineEmits<{
  toggleLogs: []
  run: [taskId: string]
  toggle: [taskId: string]
  delete: [taskId: string]
  edit: [task: CronTask]
}>()

const isRunning = ref(false)
const confirmAction = ref<'run' | 'toggle' | 'delete' | null>(null)
const showMenu = ref(false)
const menuRef = ref<HTMLDivElement | null>(null)

const iconBtn = 'p-1.5 rounded-[var(--radius-sm)] transition-colors'
const menuItem = 'flex items-center gap-2.5 w-full px-3 py-2 text-xs text-left rounded-[var(--radius-sm)] transition-colors'

function handleRun() {
  confirmAction.value = null
  isRunning.value = true
  emit('run', props.task.id)
  setTimeout(() => isRunning.value = false, 1000)
}

function handleToggle() {
  confirmAction.value = null
  showMenu.value = false
  emit('toggle', props.task.id)
}

function handleDelete() {
  confirmAction.value = null
  showMenu.value = false
  emit('delete', props.task.id)
}

function handleOutsideClick(e: MouseEvent) {
  if (showMenu.value && menuRef.value && !menuRef.value.contains(e.target as Node)) {
    showMenu.value = false
  }
  if (confirmAction.value && e.target) {
    confirmAction.value = null
  }
}

onMounted(() => document.addEventListener('mousedown', handleOutsideClick))
onUnmounted(() => document.removeEventListener('mousedown', handleOutsideClick))
</script>

<template>
  <div class="border-b border-[var(--color-border-separator)]">
    <div class="flex items-center justify-between px-4 py-3 hover:bg-[var(--color-surface-hover)] transition-colors group">
      <div class="flex items-center gap-3 min-w-0 flex-1">
        <span :class="['w-2 h-2 rounded-full flex-shrink-0', props.task.enabled ? 'bg-[var(--color-success)]' : 'bg-[var(--color-text-tertiary)]']" />
        <div class="min-w-0">
          <div class="text-sm font-medium text-[var(--color-text-primary)] truncate">{{ props.task.name }}</div>
          <div v-if="props.task.description" class="text-xs text-[var(--color-text-secondary)] truncate">{{ props.task.description }}</div>
          <div class="flex items-center gap-3 text-[11px] text-[var(--color-text-tertiary)] mt-0.5">
            <span>Created {{ new Date(props.task.createdAt).toLocaleDateString() }}</span>
          </div>
        </div>
      </div>
      <div class="flex items-center gap-3 flex-shrink-0">
        <span class="text-xs text-[var(--color-text-tertiary)]" :title="props.task.cron">{{ props.task.cron }}</span>
        <div class="flex items-center gap-0.5">
          <!-- Run Now -->
          <div class="relative">
            <button @click="isRunning || !props.task.enabled ? undefined : (confirmAction = confirmAction === 'run' ? null : 'run')"
              :disabled="isRunning || !props.task.enabled"
              :class="[iconBtn, props.task.enabled ? 'text-[var(--color-brand)] hover:bg-[var(--color-surface-selected)]' : 'text-[var(--color-text-tertiary)] cursor-not-allowed']">
              <span :class="['material-symbols-outlined text-[18px]', isRunning ? 'animate-spin' : '']">
                {{ isRunning ? 'sync' : 'play_arrow' }}
              </span>
            </button>
            <ConfirmPopover v-if="confirmAction === 'run'" message="Run this task now?" confirmLabel="Run"
              @confirm="handleRun" @cancel="confirmAction = null" />
          </div>
          <!-- View Logs -->
          <button @click="emit('toggleLogs')"
            :class="[iconBtn, showLogs ? 'text-[var(--color-brand)] bg-[var(--color-surface-selected)]' : 'text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-selected)]']">
            <span class="material-symbols-outlined text-[18px]">receipt_long</span>
          </button>
          <!-- More menu -->
          <div class="relative" ref="menuRef">
            <button @click="showMenu = !showMenu; confirmAction = null"
              :class="[iconBtn, 'text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-selected)]']">
              <span class="material-symbols-outlined text-[18px]">more_vert</span>
            </button>
            <div v-if="showMenu && !confirmAction" class="absolute right-0 top-full mt-1 z-50 w-44 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] shadow-lg py-1">
              <button @click="showMenu = false; emit('edit', props.task)" :class="[menuItem, 'text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)]']">
                <span class="material-symbols-outlined text-[16px] text-[var(--color-text-secondary)]">edit</span>Edit
              </button>
              <button @click="confirmAction = 'toggle'" :class="[menuItem, 'text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)]']">
                <span class="material-symbols-outlined text-[16px] text-[var(--color-text-secondary)]">{{ props.task.enabled ? 'pause_circle' : 'play_circle' }}</span>
                {{ props.task.enabled ? 'Disable' : 'Enable' }}
              </button>
              <div class="my-1 h-px bg-[var(--color-border-separator)]" />
              <button @click="confirmAction = 'delete'" :class="[menuItem, 'text-[var(--color-error)] hover:bg-[var(--color-error-container)]/18']">
                <span class="material-symbols-outlined text-[16px]">delete</span>Delete
              </button>
            </div>
            <ConfirmPopover v-if="confirmAction === 'toggle'"
              :message="props.task.enabled ? 'Disable this task?' : 'Enable this task?'"
              :confirmLabel="props.task.enabled ? 'Disable' : 'Enable'"
              @confirm="handleToggle" @cancel="confirmAction = null; showMenu = false" />
            <ConfirmPopover v-if="confirmAction === 'delete'" message="Delete this task?" confirmLabel="Delete"
              confirmVariant="danger" @confirm="handleDelete" @cancel="confirmAction = null; showMenu = false" />
          </div>
        </div>
      </div>
    </div>
    <Teleport v-if="showLogs" to="body">
      <div class="absolute left-4 right-4 bottom-0">
        <slot name="logs" :task-id="props.task.id" />
      </div>
    </Teleport>
  </div>
</template>
