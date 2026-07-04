<script setup lang="ts">
// v3.0 — Modal (Vue 3)
// Vue's <Teleport> replaces React's createPortal. We render into
// document.body to escape any parent overflow / z-index trap.
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
  if (v) document.body.style.overflow = 'hidden'
  else document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <Transition name="madcop-modal">
      <div v-if="open" class="madcop-modal">
        <div class="madcop-modal__backdrop" @click="emit('close')" />
        <div
          class="madcop-modal__panel"
          :style="{ width: width + 'px', maxWidth: 'calc(100vw - 48px)' }"
          role="dialog"
          aria-modal="true"
          :aria-label="title"
        >
          <div v-if="title" class="madcop-modal__head">
            <h2 class="madcop-modal__title">{{ title }}</h2>
            <button type="button" class="madcop-modal__close" @click="emit('close')" aria-label="Close">
              <span style="font-size: 16px; line-height: 1;">×</span>
            </button>
          </div>
          <div class="madcop-modal__body"><slot /></div>
          <div v-if="footer" class="madcop-modal__foot"><slot name="footer" /></div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.madcop-modal {
  position: fixed; inset: 0; z-index: 50;
  display: flex; align-items: center; justify-content: center;
}
.madcop-modal__backdrop {
  position: absolute; inset: 0;
  background: rgba(15, 23, 42, 0.48);
}
.madcop-modal__panel {
  position: relative;
  max-height: 85vh;
  display: flex; flex-direction: column;
  background: var(--madcop-panel-raised);
  border: 1.5px solid var(--madcop-line);
  border-radius: 8px;
  box-shadow: 0 16px 48px rgba(15, 23, 42, 0.18);
  overflow: hidden;
}
.madcop-modal__head {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
  padding: 20px 24px 0;
}
.madcop-modal__title {
  font-size: 20px; font-weight: 700; color: var(--madcop-ink);
  margin: 0; letter-spacing: -0.01em;
}
.madcop-modal__close {
  flex-shrink: 0; width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  background: transparent; border: none; cursor: pointer;
  color: var(--madcop-ink-muted); border-radius: 50%;
  font-size: 16px;
}
.madcop-modal__close:hover { background: var(--madcop-panel-sunken); color: var(--madcop-ink); }
.madcop-modal__body { padding: 16px 24px; overflow-y: auto; flex: 1; }
.madcop-modal__foot {
  padding: 0 24px 20px; display: flex; justify-content: flex-end; gap: 8px;
}
.madcop-modal-enter-active, .madcop-modal-leave-active { transition: opacity 200ms; }
.madcop-modal-enter-from, .madcop-modal-leave-to { opacity: 0; }
</style>
