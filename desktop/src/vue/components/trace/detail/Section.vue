<script setup lang="ts">
// v3.0 — Section (trace detail, Vue 3)
// Collapsible section with chevron, badge, and actions slot.
import { ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  sectionKey: string
  title: string
  badge?: string | number
  defaultOpen?: boolean
}>(), {
  defaultOpen: false,
})

const open = ref(props.defaultOpen)

watch(() => [props.sectionKey, props.defaultOpen], () => {
  open.value = props.defaultOpen
})
</script>

<template>
  <div class="border-b border-[var(--color-border)] last:border-b-0">
    <button
      type="button"
      @click="open = !open"
      class="flex w-full items-center gap-2 px-4 py-3 text-left transition-colors hover:bg-[var(--color-surface-hover)]"
    >
      <span
        class="material-symbols-outlined text-[16px] text-[var(--color-text-tertiary)] transition-transform duration-200"
        :style="{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }"
      >chevron_right</span>
      <span class="flex-1 min-w-0 text-sm font-semibold text-[var(--color-text-primary)]">{{ title }}</span>
      <span v-if="badge !== undefined" class="inline-flex items-center justify-center rounded-full bg-[var(--color-surface-container-high)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-text-tertiary)]">{{ badge }}</span>
      <slot name="actions" />
    </button>
    <Transition name="section-collapse">
      <div v-if="open" class="px-4 pb-3"><slot /></div>
    </Transition>
  </div>
</template>

<style>
.section-collapse-enter-active, .section-collapse-leave-active { transition: all 200ms; overflow: hidden; }
.section-collapse-enter-from, .section-collapse-leave-to { opacity: 0; max-height: 0; }
</style>
