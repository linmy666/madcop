<script setup lang="ts">
// v3.0 — ConfirmPopover (Vue 3)
// Direct translation — same Tailwind classes.
import Button from './Button.vue'

withDefaults(defineProps<{
  message: string
  confirmLabel: string
  cancelLabel: string
  confirmVariant?: 'primary' | 'danger'
}>(), {
  confirmVariant: 'primary',
})

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()
</script>

<template>
  <div class="absolute right-0 top-full mt-1.5 z-50 w-52 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] shadow-lg p-3">
    <p class="mb-2.5 text-xs text-[var(--color-text-secondary)]">{{ message }}</p>
    <div class="flex justify-end gap-1.5">
      <Button type="button" variant="ghost" size="sm" @click="emit('cancel')">{{ cancelLabel }}</Button>
      <Button type="button" :variant="confirmVariant" size="sm" @click="emit('confirm')">{{ confirmLabel }}</Button>
    </div>
  </div>
</template>
