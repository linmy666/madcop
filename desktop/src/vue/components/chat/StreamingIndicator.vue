<script setup lang="ts">
import { computed } from 'vue'

/**
 * StreamingIndicator — Vue 3 port of components/chat/StreamingIndicator.tsx
 * Shows animated dots while assistant is streaming tokens.
 * Prop-driven — no store imports.
 */

export interface StreamingIndicatorProps {
  streaming: boolean
  tokens?: number
  verb?: string
}

const props = withDefaults(defineProps<StreamingIndicatorProps>(), {
  tokens: 0,
  verb: 'thinking',
})

const dotCount = computed(() => {
  if (!props.streaming || props.tokens === 0) return 3
  return Math.min(4, Math.floor((props.tokens % 24) / 6) + 1)
})

const verbText = computed(() => props.verb)
</script>

<template>
  <div
    v-if="props.streaming"
    class="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-3 py-1.5 text-xs text-[var(--color-text-secondary)]"
  >
    <div class="flex items-center gap-0.5">
      <span
        v-for="i in dotCount"
        :key="i"
        class="h-1.5 w-1.5 rounded-full bg-[var(--color-brand)] animate-bounce"
        :style="{ animationDelay: `${(i - 1) * 100}ms` }"
      />
    </div>
    <span class="font-medium">{{ verbText }}</span>
    <span v-if="props.tokens > 0" class="tabular-nums text-[var(--color-text-tertiary)]">
      {{ props.tokens }} tokens
    </span>
  </div>
</template>
