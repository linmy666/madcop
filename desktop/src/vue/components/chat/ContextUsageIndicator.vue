<script setup lang="ts">
import { ref, computed } from 'vue'

/**
 * ContextUsageIndicator — Vue 3 port of components/chat/ContextUsageIndicator.tsx
 * Context usage circular indicator. Prop-driven state.
 */

export interface ContextUsageIndicatorProps {
  chatState: 'idle' | 'running' | 'error' | 'closed'
  usagePercent?: number
  modelLabel?: string
  loading?: boolean
  t?: (key: string) => string
  compact?: boolean
}

const props = withDefaults(defineProps<ContextUsageIndicatorProps>(), {
  loading: false, t: () => '', compact: false,
})

const strokeColor = computed(() => {
  const p = props.usagePercent ?? 0
  return p >= 90 ? 'var(--color-error)' : p >= 75 ? 'var(--color-warning)' : 'var(--color-secondary)'
})

const ringStyle = computed(() => {
  const p = props.usagePercent
  if (p === undefined || p === null) return 'var(--color-surface-container-high)'
  return `conic-gradient(${strokeColor.value} ${Math.max(0, Math.min(100, p)) * 3.6}deg, var(--color-surface-container-high) 0deg)`
})

const displayPercent = computed(() => {
  if (props.usagePercent === undefined || props.usagePercent === null) return '--'
  const p = Math.max(0, Math.min(100, props.usagePercent))
  return `${p.toFixed(p >= 10 ? 0 : 1)}%`
})

function formatNumber(value: number): string { return value.toLocaleString() }
</script>

<template>
  <div class="group/context relative pointer-events-auto">
    <button type="button" :aria-label="loading ? 'Loading context usage' : (usagePercent !== undefined && usagePercent !== null ? `Context usage: ${displayPercent}` : 'Context usage unavailable')"
      :title="t('contextIndicator.title')"
      :class="['flex h-8 shrink-0 items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-container)] text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-border-focus)] hover:bg-[var(--color-surface-container-high)] hover:text-[var(--color-text-primary)]', compact ? 'px-2' : 'px-2.5']">
      <span class="relative grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full">
        <span v-if="loading" class="absolute inset-[2px] rounded-full border-2 border-[var(--color-text-tertiary)] border-t-transparent animate-spin" />
        <span v-else class="relative grid h-[18px] w-[18px] place-items-center rounded-full" :style="ringStyle">
          <span class="absolute inset-[3px] rounded-full bg-[var(--color-surface-container-lowest)]" />
          <span class="relative h-[5px] w-[5px] rounded-full" :style="{ backgroundColor: strokeColor }" />
        </span>
      </span>
      <span class="font-mono text-[11px] font-semibold tabular-nums">{{ displayPercent }}</span>
    </button>

    <div v-if="!compact" class="pointer-events-none absolute bottom-full right-0 z-40 mb-2 w-[320px] max-w-[calc(100vw-2rem)] translate-y-1 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] p-4 text-left opacity-0 shadow-[var(--shadow-dropdown)] transition-all duration-150 group-hover/context:translate-y-0 group-hover/context:opacity-100 group-focus-within/context:translate-y-0 group-focus-within/context:opacity-100">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--color-text-tertiary)]">{{ t('contextIndicator.title') }}</div>
          <div class="mt-1 truncate text-sm font-semibold text-[var(--color-text-primary)]">{{ modelLabel || t('contextIndicator.modelUnknown') }}</div>
        </div>
        <div class="shrink-0 font-mono text-xl font-semibold text-[var(--color-text-primary)]">{{ displayPercent }}</div>
      </div>
      <div v-if="usagePercent !== undefined && usagePercent !== null" class="mt-4 grid grid-cols-2 gap-3 font-mono text-xs">
        <div>
          <div class="text-[var(--color-text-tertiary)]">{{ t('contextIndicator.used') }}</div>
          <div class="mt-1 text-[var(--color-text-primary)]">{{ formatNumber(usagePercent) }}</div>
        </div>
        <div>
          <div class="text-[var(--color-text-tertiary)]">{{ t('contextIndicator.free') }}</div>
          <div class="mt-1 text-[var(--color-text-primary)]">{{ formatNumber(Math.max(0, 100 - usagePercent)) }}</div>
        </div>
      </div>
      <div v-else class="mt-4 text-sm leading-6 text-[var(--color-text-secondary)]">{{ loading ? t('contextIndicator.loading') : t('contextIndicator.unavailableDetail') }}</div>
    </div>
  </div>
</template>
