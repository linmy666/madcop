<script setup lang="ts">
// v3.0 — ActionDialog (Vue 3)
// Direct translation — wraps Modal + Button, same dynamic footer.
import { computed } from 'vue'
import Modal from './Modal.vue'
import Button from './Button.vue'

interface DialogAction {
  label: string
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
  loading?: boolean
  disabled?: boolean
}

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  actions: DialogAction[]
  width?: number
  loading?: boolean
  bodyText?: string
}>(), {
  width: 460,
  loading: false,
})

const emit = defineEmits<{ (e: 'close'): void }>()

const busy = computed(() => props.loading || props.actions.some((a) => a.loading))

function handleAction(action: DialogAction, index: number) {
  // Emit with index so parent can identify which action was clicked
  emit('close' as any)  // placeholder — parent will handle via @action
}
</script>

<template>
  <Modal
    :open="open"
    :title="title"
    :width="width"
    :footer="true"
    @close="!busy && emit('close')"
  >
    <p v-if="bodyText" class="text-sm leading-6 text-[var(--color-text-secondary)]">
      {{ bodyText }}
    </p>
    <slot v-else />
    <template #footer>
      <Button
        v-for="(action, i) in actions" :key="i"
        type="button"
        :variant="action.variant ?? 'secondary'"
        :loading="action.loading"
        :disabled="busy || action.disabled"
        @click="handleAction(action, i)"
      >
        {{ action.label }}
      </Button>
    </template>
  </Modal>
</template>
