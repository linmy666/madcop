<script setup lang="ts">
import { computed } from 'vue'

/**
 * CurrentTurnChangeCard — Vue 3 port of components/chat/CurrentTurnChangeCard.tsx
 * Turn changed notification banner. Prop-driven.
 */

export interface CurrentTurnChangeCardProps {
  oldTitle?: string
  newTitle: string
  reason?: string
}

const props = defineProps<CurrentTurnChangeCardProps>()
const emit = defineEmits<{ close: [] }>()

const displayReason = computed(() => {
  if (!props.reason) return ''
  if (props.reason === 'user_edited') return 'You edited a previous message'
  if (props.reason === 'agent_revised') return 'MadCop revised its answer'
  if (props.reason === 'compact') return 'Context was compacted'
  return props.reason
})
</script>

<template>
  <div class="mx-auto max-w-[860px] animate-fade-in">
    <div class="flex items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-brand)]/30 bg-[var(--color-brand)]/5 px-4 py-2.5 transition-all hover:bg-[var(--color-brand)]/10">
      <div class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--color-brand)]/15">
        <span class="material-symbols-outlined text-[14px] text-[var(--color-brand)]">swap_horiz</span>
      </div>
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2">
          <span v-if="oldTitle" class="text-[11px] font-medium text-[var(--color-text-tertiary)] line-through">{{ oldTitle }}</span>
          <span v-if="oldTitle" class="material-symbols-outlined text-[14px] text-[var(--color-brand)]">arrow_forward</span>
          <span class="text-[12px] font-semibold text-[var(--color-text-primary)]">{{ newTitle }}</span>
        </div>
        <p v-if="displayReason" class="mt-0.5 text-[11px] text-[var(--color-text-secondary)]">{{ displayReason }}</p>
      </div>
      <button type="button" @click="emit('close')"
        class="shrink-0 rounded-full p-1 text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-container)] hover:text-[var(--color-text-primary)]" aria-label="Dismiss">
        <span class="material-symbols-outlined text-[14px]">close</span>
      </button>
    </div>
  </div>
</template>
