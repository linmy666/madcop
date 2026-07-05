<script setup lang="ts">
/**
 * NewTaskModal — Vue 3 port of components/tasks/NewTaskModal.tsx
 * Modal dialog for creating/editing a scheduled task.
 * Prop-driven: open/onClose from parent.
 */

interface NewTaskModalProps {
  open: boolean
  editTask?: {
    id: string
    name: string
    prompt: string
    schedule?: string
  }
}

interface NewTaskModalEmit {
  (e: 'close'): void
  (e: 'save', task: { name: string; prompt: string; schedule?: string }): void
}

const props = defineProps<NewTaskModalProps>()
const emit = defineEmits<NewTaskModalEmit>()

const name = ref('')
const prompt = ref('')
const schedule = ref('')
const step = ref<'basic' | 'schedule' | 'confirm'>('basic')

function open() {
  name.value = props.editTask?.name || ''
  prompt.value = props.editTask?.prompt || ''
  schedule.value = props.editTask?.schedule || ''
  step.value = props.editTask ? 'confirm' : 'basic'
}

function proceed() {
  if (name.value.trim() && prompt.value.trim()) {
    step.value = 'schedule'
  }
}

function finish() {
  emit('save', { name: name.value, prompt: prompt.value, schedule: schedule.value })
  emit('close')
}

function cancel() {
  emit('close')
}

// Watch for open state changes
watch(() => props.open, (v) => {
  if (v) open()
}, { immediate: true })
</script>

<template>
  <Teleport to="body">
    <transition name="fade">
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center">
        <!-- Backdrop -->
        <div class="fixed inset-0 bg-black/50" @click="cancel" />
        <!-- Modal -->
        <div class="relative z-10 w-full max-w-lg mx-4 bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] shadow-2xl overflow-hidden">
          <!-- Header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
            <div class="flex items-center gap-2">
              <span class="material-symbols-outlined text-[var(--color-brand)] text-lg">{{ props.editTask ? 'edit_note' : 'add_task' }}</span>
              <h2 class="text-base font-bold text-[var(--color-text-primary)]">{{ props.editTask ? 'Edit Task' : 'New Task' }}</h2>
            </div>
            <button @click="cancel" class="p-1 hover:bg-[var(--color-surface-hover)] rounded text-[var(--color-text-tertiary)]">
              <span class="material-symbols-outlined text-sm">close</span>
            </button>
          </div>

          <!-- Body -->
          <div class="p-6 space-y-4">
            <!-- Step indicator -->
            <div v-if="!props.editTask" class="flex items-center gap-2">
              <span :class="['w-2 h-2 rounded-full', step === 'basic' ? 'bg-[var(--color-brand)]' : 'bg-[var(--color-border)]']" />
              <span class="text-xs text-[var(--color-text-tertiary)]">Basic</span>
              <span class="material-symbols-outlined text-[10px] text-[var(--color-text-tertiary)]">chevron_right</span>
              <span :class="['w-2 h-2 rounded-full', step === 'schedule' ? 'bg-[var(--color-brand)]' : 'bg-[var(--color-border)]']" />
              <span class="text-xs text-[var(--color-text-tertiary)]">Schedule</span>
            </div>

            <!-- Name -->
            <div>
              <label class="text-xs font-semibold text-[var(--color-text-tertiary)] mb-1 block">Task Name</label>
              <input v-model="name" type="text"
                :class="['w-full px-3 py-2 rounded-lg border text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]/30',
                  name.trim() ? 'border-[var(--color-border)]' : 'border-[var(--color-error)]/50']"
                placeholder="e.g. Daily standup notes" />
            </div>

            <!-- Prompt -->
            <div>
              <label class="text-xs font-semibold text-[var(--color-text-tertiary)] mb-1 block">Prompt</label>
              <textarea v-model="prompt" rows="3"
                :class="['w-full px-3 py-2 rounded-lg border text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]/30',
                  prompt.trim() ? 'border-[var(--color-border)]' : 'border-[var(--color-error)]/50']"
                placeholder="What should the agent do?" />
            </div>

            <!-- Schedule (step 2) -->
            <div v-if="step === 'schedule'" class="space-y-3">
              <label class="text-xs font-semibold text-[var(--color-text-tertiary)] mb-1 block">Schedule (optional)</label>
              <div class="grid grid-cols-3 gap-2">
                <button v-for="s in ['Daily', 'Weekly', 'Monthly']" :key="s"
                  @click="schedule = s"
                  :class="['px-3 py-2 rounded-lg border text-xs font-medium transition-colors',
                    schedule === s ? 'border-[var(--color-brand)] bg-[var(--color-primary-container)] text-[var(--color-brand)]' : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-brand)]/50']">
                  {{ s }}
                </button>
              </div>
              <input v-model="schedule" type="text" placeholder="Or enter a cron expression..."
                class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]/30" />
            </div>
          </div>

          <!-- Footer -->
          <div class="flex justify-end gap-2 px-6 py-4 border-t border-[var(--color-border)]">
            <button @click="cancel" class="px-4 py-2 text-xs text-[var(--color-text-secondary)] hover:underline">Cancel</button>
            <button v-if="step === 'basic'" @click="proceed" :disabled="!name.trim() || !prompt.trim()"
              class="px-4 py-2 bg-[var(--color-brand)] text-[var(--color-on-brand)] rounded text-xs font-semibold disabled:opacity-50">
              Next
            </button>
            <button v-else @click="finish"
              class="px-4 py-2 bg-[image:var(--gradient-btn-primary)] text-[var(--color-btn-primary-fg)] rounded text-xs font-semibold shadow-sm">
              {{ props.editTask ? 'Save Changes' : 'Create Task' }}
            </button>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
