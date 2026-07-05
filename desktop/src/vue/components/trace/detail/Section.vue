<script setup lang="ts">
// Section — Vue 3 port of components/trace/detail/Section.tsx
// Collapsible section with chevron, badge, actions slot.
// Tracks open state globally via Map keyed by scopeId:sectionKey, just like React's sectionOpenState.
import { ref, watch, computed } from 'vue'

// Global module-level state — mirrors React's sectionOpenState
const sectionOpenState = new Map<string, boolean>()

export function resetTraceSectionState(): void {
  sectionOpenState.clear()
}

const props = withDefaults(defineProps<{
  sectionKey: string
  title: string
  badge?: string | number
  actions?: string // slot name indicator (kept for API compat, unused in template)
  defaultOpen?: boolean
  scopeId?: string
}>(), {
  defaultOpen: false,
  scopeId: 'default',
})

// State key uses scopeId + sectionKey — same pattern as React's `stateKey = resolvedScopeId:sectionKey`
const stateKey = computed(() => `${props.scopeId}:${props.sectionKey}`)
const open = ref(sectionOpenState.get(stateKey.value) ?? props.defaultOpen)

// Watch for key changes (e.g. when scopeId or sectionKey changes)
watch(() => [stateKey.value, props.defaultOpen], () => {
  open.value = sectionOpenState.get(stateKey.value) ?? props.defaultOpen
})

function toggle(): void {
  open.value = !open.value
  sectionOpenState.set(stateKey.value, open.value)
}

// Chevron rotation: 90deg when open (chevron_right rotated = chevron_down visual)
const chevronTransform = computed(() => (open.value ? 'rotate(90deg)' : 'rotate(0deg)'))
</script>

<template>
  <section class="border-t border-[var(--color-border)] first:border-t-0">
    <div class="flex items-center gap-2 px-4 py-2">
      <button
        type="button"
        @click="toggle"
        :aria-expanded="open"
        class="flex min-w-0 flex-1 items-center gap-1.5 text-left transition-colors"
      >
        <span
          class="material-symbols-outlined shrink-0 text-[var(--color-text-tertiary)] transition-transform"
          :style="{ fontSize: '13px', lineHeight: '13px', transform: chevronTransform }"
        >chevron_right</span>
        <span class="truncate text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]">
          {{ title }}
        </span>
        <span
          v-if="badge !== undefined"
          class="shrink-0 rounded-[var(--radius-sm)] bg-[var(--color-surface-container)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-text-tertiary)]"
        >
          {{ badge }}
        </span>
      </button>
      <slot name="actions" />
    </div>
    <div v-if="open" class="px-4 pb-4">
      <slot />
    </div>
  </section>
</template>