<script setup lang="ts">
// v3.0 — MessageActionBar (Vue 3)
// Direct translation of MessageActionBar.tsx — same Tailwind classes.
import { ref, computed } from 'vue'
import CopyButton from '../shared/CopyButton.vue'

const props = withDefaults(defineProps<{
  copyText?: string
  copyLabel?: string
  align?: 'start' | 'end'
  timestamp?: number
  branchLabel?: string
  branchLoading?: boolean
}>(), {
  copyLabel: 'Copy',
  align: 'start',
  branchLabel: '',
  branchLoading: false,
})

const emit = defineEmits<{ (e: 'branch'): void }>()

const hasCopy = computed(() => Boolean(props.copyText?.trim()))
const hasBranch = computed(() => Boolean(props.branchLabel))

const ts = computed(() => {
  if (typeof props.timestamp !== 'number') return ''
  return new Date(props.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
})
const tsFull = computed(() => {
  if (typeof props.timestamp !== 'number') return ''
  return new Date(props.timestamp).toLocaleString('zh-CN')
})
</script>

<template>
  <div
    v-if="hasCopy || hasBranch"
    data-message-actions
    :data-align="align"
    :class="[
      'pointer-events-none mt-2 flex h-7 w-full opacity-0 transition-opacity duration-150 group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100',
      align === 'end' ? 'justify-end' : 'justify-start',
    ]"
  >
    <div class="flex min-h-7 items-center gap-1.5">
      <CopyButton
        v-if="hasCopy"
        :text="copyText!"
        :label="copyLabel"
        class="inline-flex h-7 w-7 items-center justify-center rounded-full border border-transparent bg-transparent text-[var(--color-text-tertiary)] transition-colors hover:border-[var(--color-brand)]/30 hover:bg-[var(--color-surface-container-low)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/35"
      >
        <template #default="{ copied }">
          <span v-if="copied" class="material-symbols-outlined text-[13px]">check</span>
          <span v-else class="material-symbols-outlined text-[13px]">content_copy</span>
        </template>
      </CopyButton>
      <button
        v-if="hasBranch"
        type="button"
        :disabled="branchLoading"
        :aria-label="branchLabel"
        :title="branchLabel"
        class="inline-flex h-7 w-7 items-center justify-center rounded-full border border-transparent bg-transparent text-[var(--color-text-tertiary)] transition-colors hover:border-[var(--color-brand)]/30 hover:bg-[var(--color-surface-container-low)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/35 disabled:cursor-wait disabled:opacity-60"
        @click="emit('branch')"
      >
        <span class="material-symbols-outlined text-[13px]">git_fork</span>
      </button>
      <span
        v-if="ts"
        class="ml-1 inline-flex items-center text-[11px] font-medium tabular-nums text-[var(--color-text-tertiary)]"
        :title="tsFull"
      >{{ ts }}</span>
    </div>
  </div>
</template>
