<script setup lang="ts">
/**
 * ConfirmDialog — modal confirmation dialog with loading state.
 * Used for turn change / rewind confirmation.
 */

const props = defineProps<{
  open: boolean
  title: string
  body: string
  confirmLabel: string
  cancelLabel: string
  loading?: boolean
  confirmVariant?: 'danger' | 'primary'
}>()

const emit = defineEmits<{
  close: []
  confirm: []
}>()
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex items-center justify-center p-4"
    >
      <!-- Backdrop -->
      <div
        class="absolute inset-0 bg-black/40 backdrop-blur-sm"
        @click="emit('close')"
      />
      <!-- Dialog -->
      <div
        class="relative w-full max-w-md rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container)] p-5 shadow-xl"
        role="dialog"
        aria-modal="true"
      >
        <h2 class="mb-2 text-base font-semibold text-[var(--color-text-primary)]">{{ title }}</h2>
        <p class="mb-5 text-sm text-[var(--color-text-secondary)]">{{ body }}</p>
        <div class="flex justify-end gap-2">
          <button
            type="button"
            @click="emit('close')"
            :disabled="loading"
            class="rounded-md px-3 py-1.5 text-sm font-medium text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)]"
          >
            {{ cancelLabel }}
          </button>
          <button
            type="button"
            @click="emit('confirm')"
            :disabled="loading"
            :class="[
              'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-white transition-colors',
              confirmVariant === 'danger'
                ? 'bg-[var(--color-error)] hover:bg-[var(--color-error)]/90'
                : 'bg-[var(--color-brand)] hover:bg-[var(--color-brand)]/90',
              loading && 'opacity-60 cursor-wait',
            ]"
          >
            <span v-if="loading" class="material-symbols-outlined text-[16px] animate-spin">
              progress_activity
            </span>
            {{ confirmLabel }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>