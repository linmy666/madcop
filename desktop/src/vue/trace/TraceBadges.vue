<script setup lang="ts">
/**
 * TraceBadges — Vue 3 port of components/trace/TraceBadges.tsx
 * TypeIcon, StatusGlyph, StatusPill, MetaChip, LiveBadge helpers for trace UI.
 * Pure component library, no store imports.
 */

export function iconForSpanKind(kind: string, status: string): { icon: string; color: string } {
  if (kind === 'llm') return { icon: 'sparkle', color: 'var(--color-brand)' }
  if (kind === 'tool') return { icon: 'build', color: 'var(--color-warning)' }
  if (kind === 'tool_result') return { icon: 'build', color: 'var(--color-text-tertiary)' }
  if (kind === 'turn') return { icon: 'call_split', color: 'var(--color-text-tertiary)' }
  if (kind === 'session') return { icon: 'radio', color: 'var(--color-text-tertiary)' }
  if (kind === 'event') return status === 'error' ? { icon: 'warning', color: 'var(--color-error)' } : { icon: 'radio_button_unchecked', color: 'var(--color-text-tertiary)' }
  if (kind === 'message') return { icon: 'chat_bubble', color: 'var(--color-text-tertiary)' }
  return { icon: 'description', color: 'var(--color-text-tertiary)' }
}

export function statusBadge(status: string): { icon: string; color: string } | null {
  if (status === 'error') return { icon: 'error', color: 'var(--color-error)' }
  if (status === 'pending') return { icon: 'schedule', color: 'var(--color-warning)' }
  return null
}

export function pillStyle(status: string): string {
  if (status === 'error') return 'bg-[var(--color-error)]/10 text-[var(--color-error)]'
  if (status === 'pending') return 'bg-[var(--color-warning)]/10 text-[var(--color-warning)]'
  return 'bg-[var(--color-success)]/10 text-[var(--color-success)]'
}

export function pillLabel(status: string): string {
  if (status === 'error') return 'Error'
  if (status === 'pending') return 'Pending'
  return 'OK'
}
</script>

<template>
  <!-- Placeholder — helpers are used via :is or imported -->
</template>
