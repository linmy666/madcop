<script setup lang="ts">
// v3.0 — Modal (Vue 3)
// Direct translation of Modal.tsx — same Tailwind classes, Teleport replaces createPortal.
import { onMounted, onUnmounted, watch } from 'vue'

const props = withDefaults(defineProps<{
  open: boolean
  title?: string
  width?: number
  footer?: boolean
}>(), {
  width: 560,
  footer: false,
})

const emit = defineEmits<{ (e: 'close'): void }>()

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) emit('close')
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
watch(() => props.open, (v) => {
  if (typeof document !== 'undefined') document.body.style.overflow = v ? 'hidden' : ''
})
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-[var(--color-overlay-scrim)] transition-opacity duration-200" @click="emit('close')" />
        <div
          class="glass-panel relative rounded-[var(--radius-xl)] max-h-[85vh] flex flex-col"
          :style="{ width: width + 'px', maxWidth: 'calc(100vw - 48px)' }"
          role="dialog"
          aria-modal="true"
          :aria-label="title"
        >
          <div v-if="title" class="flex items-start justify-between gap-4 px-6 pt-6 pb-0">
            <h2 class="text-xl font-bold text-[var(--color-text-primary)]">{{ title }}</h2>
            <button
              type="button"
              class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
              @click="emit('close')"
              aria-label="Close dialog"
            >
              <span class="material-symbols-outlined text-[18px]">close</span>
            </button>
          </div>
          <div class="px-6 py-4 overflow-y-auto flex-1">
            <slot />
          </div>
          <div v-if="footer" class="px-6 pb-6 pt-0 flex justify-end gap-2">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style>
.modal-fade-enter-active, .modal-fade-leave-active { transition: opacity 200ms; }
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }
</style>
