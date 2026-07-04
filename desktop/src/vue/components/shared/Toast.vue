<script setup lang="ts">
// v3.0 — Toast (Vue 3)
// Direct translation of Toast.tsx — same typeStyles, same animations.
defineProps<{
  toasts: Array<{
    id: string
    type: 'success' | 'error' | 'warning' | 'info'
    message: string
  }>
}>()

const emit = defineEmits<{ (e: 'remove', id: string): void }>()

const typeClasses: Record<string, string> = {
  success: 'border-l-4 border-l-[var(--color-success)]',
  error: 'border-l-4 border-l-[var(--color-error)]',
  warning: 'border-l-4 border-l-[var(--color-warning)]',
  info: 'border-l-4 border-l-[var(--color-text-accent)]',
}
</script>

<template>
  <div v-if="toasts.length > 0" class="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-sm">
    <div
      v-for="toast in toasts" :key="toast.id"
      :class="[
        'bg-[var(--color-surface)] rounded-[var(--radius-md)] shadow-[var(--shadow-dropdown)] px-4 py-3 text-sm text-[var(--color-text-primary)]',
        typeClasses[toast.type],
      ]"
    >
      <div class="flex items-center justify-between gap-2">
        <span>{{ toast.message }}</span>
        <button
          class="text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] text-lg leading-none"
          @click="emit('remove', toast.id)"
        >×</button>
      </div>
    </div>
  </div>
</template>
