<script setup lang="ts">
/**
 * TraceBadges — Vue 3 port of components/trace/TraceBadges.tsx
 * TypeIcon, StatusGlyph, StatusPill, MetaChip, LiveBadge components for trace UI.
 * Pure component library, no store imports.
 * Exports: iconForSpan(), statusGlyphIcon(), pillStyle(), pillLabel(),
 *          spanDisplayTitle(), turnDisplayTitle(), traceEventPhaseLabel()
 *          + Vue components TypeIcon, StatusGlyph, StatusPill, MetaChip, LiveBadge
 */
import { useTranslation } from '../../i18n'
import type { TraceSpan, TraceSpanStatus } from '../../lib/traceViewModel'

// ─── Lucide icon mapping → material-symbols-outlined names ──────────
// Sparkles=auto_awesome, Wrench=build, GitBranch=call_split, RadioTower=radio,
// AlertTriangle=warning, CircleDot=radio_button_unchecked, Bot=smart_toy,
// FileJson2=description, MessageSquareText=chat_bubble

// ─── iconForSpan() — used by TypeIcon Vue component ─────────────────
export function iconForSpan(span: TraceSpan): { icon: string; color: string } {
  const tertiary = 'var(--color-text-tertiary)'
  switch (span.kind) {
    case 'llm':
      return { icon: 'auto_awesome', color: 'var(--color-brand)' }
    case 'tool':
      return { icon: 'build', color: 'var(--color-warning)' }
    case 'tool_result':
      return { icon: 'build', color: tertiary }
    case 'turn':
      return { icon: 'call_split', color: tertiary }
    case 'session':
      return { icon: 'radio', color: tertiary }
    case 'event':
      return span.status === 'error'
        ? { icon: 'warning', color: 'var(--color-error)' }
        : { icon: 'radio_button_unchecked', color: tertiary }
    case 'message': {
      if (span.message?.type === 'assistant') {
        return { icon: 'smart_toy', color: tertiary }
      }
      if (span.message?.type === 'system') {
        return { icon: 'description', color: tertiary }
      }
      return { icon: 'chat_bubble', color: tertiary }
    }
    default:
      return { icon: 'description', color: tertiary }
  }
}

// ─── statusGlyphIcon() — used by StatusGlyph Vue component ──────────
export function statusGlyphIcon(status: TraceSpanStatus): { icon: string; color: string; animate?: boolean } | null {
  if (status === 'error') {
    return { icon: 'warning', color: 'var(--color-error)' }
  }
  if (status === 'pending') {
    return { icon: 'schedule', color: 'var(--color-warning)', animate: true }
  }
  return null
}

// ─── pillStyle() + pillLabel() — used by StatusPill Vue component ───
export function pillStyle(status: TraceSpanStatus): string {
  if (status === 'error') return 'bg-[var(--color-error)]/10 text-[var(--color-error)]'
  if (status === 'pending') return 'bg-[var(--color-warning)]/10 text-[var(--color-warning)]'
  return 'bg-[var(--color-success)]/10 text-[var(--color-success)]'
}

export function pillLabel(status: TraceSpanStatus, t: ReturnType<typeof useTranslation>): string {
  if (status === 'error') return t('trace.status.error')
  if (status === 'pending') return t('trace.status.pending')
  return t('trace.status.ok')
}

// ─── spanDisplayTitle() — pure helper, used by TraceDetail ──────────
export function spanDisplayTitle(span: TraceSpan, t: ReturnType<typeof useTranslation>): string {
  if (span.kind === 'message' && span.message) {
    switch (span.message.type) {
      case 'user': return t('trace.message.user')
      case 'assistant': return t('trace.message.assistant')
      case 'system': return t('trace.message.system')
      case 'tool_use': return t('trace.message.toolRequest')
      case 'tool_result': return t('trace.message.toolResult')
      default: return span.message.type
    }
  }
  if (span.kind === 'llm') {
    return span.call?.model ?? span.call?.provider?.name ?? t('trace.modelCall')
  }
  if (span.kind === 'tool') {
    return span.toolName ?? span.title
  }
  if (span.kind === 'tool_result') {
    return span.status === 'error' ? t('trace.toolError') : t('trace.toolResult')
  }
  if (span.kind === 'event' && span.event) {
    return traceEventPhaseLabel(span.event.phase, t)
  }
  if (span.kind === 'turn') {
    return turnDisplayTitle(span.title, (span.turnIndex ?? 0) + 1, t)
  }
  return span.title
}

// ─── turnDisplayTitle() ─────────────────────────────────────────────
export function turnDisplayTitle(title: string, oneBasedIndex: number, t: ReturnType<typeof useTranslation>): string {
  if (title === 'Session activity') return t('trace.sessionActivity')
  const match = title.match(/^Turn (\d+)$/)
  if (match) return t('trace.turnLabel', { index: match[1]! })
  if (!title.trim()) return t('trace.turnLabel', { index: oneBasedIndex })
  return title
}

// ─── traceEventPhaseLabel() ─────────────────────────────────────────
export function traceEventPhaseLabel(phase: string, t: ReturnType<typeof useTranslation>): string {
  switch (phase) {
    case 'api_call_started': return t('trace.event.apiCallStarted')
    case 'api_call_completed': return t('trace.event.apiCallCompleted')
    case 'api_call_failed': return t('trace.event.apiCallFailed')
    case 'api_call_aborted': return t('trace.event.apiCallAborted')
    case 'response_capture_failed': return t('trace.event.responseCaptureFailed')
    case 'upstream_fetch_started': return t('trace.event.upstreamFetchStarted')
    case 'upstream_fetch_completed': return t('trace.event.upstreamFetchCompleted')
    case 'upstream_fetch_failed': return t('trace.event.upstreamFetchFailed')
    default:
      return phase
        .split(/[_\s-]+/)
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ')
  }
}
</script>

<template>
  <!-- Placeholder — helper functions used via script import; components defined below -->
</template>

<script lang="ts">
// ── Vue components (defined in non-setup script for import/export) ───
import type { Component } from 'vue'
import { useTranslation } from '../../i18n'
import type { TraceSpan, TraceSpanStatus } from '../../lib/traceViewModel'

// TypeIcon — renders a span icon with color
export const TypeIcon: Component = {
  name: 'TypeIcon',
  props: {
    span: Object as () => TraceSpan,
    size: { type: Number, default: 14 },
  },
  setup(props) {
    const { icon, color } = iconForSpan(props.span)
    return { icon, color, size: props.size }
  },
  template: `
    <span class="inline-flex shrink-0 items-center justify-center" aria-hidden="true">
      <span class="material-symbols-outlined" :style="{ fontSize: size + 'px', lineHeight: size + 'px', color }">
        {{ icon }}
      </span>
    </span>
  `,
}

// StatusGlyph — renders an error/pending icon
export const StatusGlyph: Component = {
  name: 'StatusGlyph',
  props: {
    status: String as () => TraceSpanStatus,
  },
  setup(props) {
    const glyph = statusGlyphIcon(props.status)
    return { glyph }
  },
  template: `
    <span v-if="glyph" aria-hidden="true" class="inline-flex shrink-0 items-center justify-center">
      <span
        class="material-symbols-outlined"
        :class="glyph.animate ? 'animate-pulse-dot' : ''"
        :style="{ fontSize: '13px', lineHeight: '13px', color: glyph.color }"
      >
        {{ glyph.icon }}
      </span>
    </span>
  `,
}

// StatusPill — renders a status pill
export const StatusPill: Component = {
  name: 'StatusPill',
  props: {
    status: String as () => TraceSpanStatus,
  },
  setup() {
    const t = useTranslation()
    return { t }
  },
  template: `
    <span :class="['inline-flex shrink-0 items-center rounded-[var(--radius-sm)] px-1.5 py-0.5 text-[10px] font-semibold', pillStyle(props.status)]">
      {{ pillLabel(props.status, t) }}
    </span>
  `,
}

// MetaChip — renders a label: value chip
export const MetaChip: Component = {
  name: 'MetaChip',
  props: {
    label: String,
    value: String,
    tone: { type: String, default: 'default' }, // 'default' | 'danger'
    title: String,
  },
  template: `
    <span
      class="inline-flex min-w-0 items-center gap-1 text-[10px]"
      :title="title || undefined"
    >
      <span class="shrink-0 text-[var(--color-text-tertiary)]">{{ label }}</span>
      <span :class="[
        'truncate font-mono',
        tone === 'danger' ? 'text-[var(--color-error)]' : 'text-[var(--color-text-secondary)]'
      ]">{{ value }}</span>
    </span>
  `,
}

// LiveBadge — renders a live indicator
export const LiveBadge: Component = {
  name: 'LiveBadge',
  setup() {
    const t = useTranslation()
    return { t }
  },
  template: `
    <span class="inline-flex shrink-0 items-center gap-1 rounded-[var(--radius-sm)] border border-[var(--color-success)]/25 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--color-success)]">
      <span class="h-1.5 w-1.5 rounded-full bg-[var(--color-success)] animate-pulse-dot" />
      {{ t('trace.live') }}
    </span>
  `,
}
</script>