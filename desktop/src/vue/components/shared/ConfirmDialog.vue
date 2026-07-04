<script setup lang="ts">
// v3.0 — Confirm dialog (Vue 3)
// Wraps Modal with a confirm/cancel pair. Used for destructive actions.
import { Modal } from './Modal.vue'
import { Button } from './Button.vue'

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
    <div class="madcop-confirm__body"><slot /></div>
    <template #footer>
      <Button variant="secondary" @click="emit('close')">{{ cancelLabel }}</Button>
      <Button :variant="confirmVariant" :loading="loading" @click="emit('confirm')">
        {{ confirmLabel }}
      </Button>
    </template>
  </Modal>
</template>

<style scoped>
.madcop-confirm__body { font-size: 13px; color: var(--madcop-ink-body); line-height: 1.6; }
</style>
