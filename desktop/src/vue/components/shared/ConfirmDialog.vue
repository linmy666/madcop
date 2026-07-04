<script setup lang="ts">
// v3.0 — ConfirmDialog (Vue 3)
// Direct translation of ConfirmDialog.tsx — wraps Modal + Button.
import Modal from './Modal.vue'
import Button from './Button.vue'

withDefaults(defineProps<{
  open: boolean
  title: string
  confirmLabel?: string
  cancelLabel?: string
  confirmVariant?: 'primary' | 'danger'
  loading?: boolean
}>(), {
  confirmLabel: '确定',
  cancelLabel: '取消',
  confirmVariant: 'danger',
  loading: false,
})

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'confirm'): void | Promise<void>
}>()
</script>

<template>
  <Modal :open="open" :title="title" :footer="true" @close="emit('close')">
    <div class="text-sm text-[var(--color-text-secondary)] leading-relaxed">
      <slot />
    </div>
    <template #footer>
      <Button variant="secondary" @click="emit('close')">{{ cancelLabel }}</Button>
      <Button :variant="confirmVariant" :loading="loading" @click="emit('confirm')">
        {{ confirmLabel }}
      </Button>
    </template>
  </Modal>
</template>
