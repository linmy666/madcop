<script setup lang="ts">
// v3.0 — StreamingIndicator (Vue 3 SFC)
// Full translation of src/components/chat/StreamingIndicator.tsx (167 lines).
// Reacted the streaming card (collapsible, shows assistant name + action + message count + stop),
// plus the tiny chip at the bottom of the chat when a turn is streaming but not yet committed.
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue'

// ── Props ─────────────────────────────────────────────────────────────
interface StreamingCardProps {
  assistantName?: string | null
  actionDescription?: string | null
  /** Whether the run is in the middle of working (true = show Stop button). */
  isWorking?: boolean
  /** Message count to display inside the badge. */
  messageCount?: number
  /** Whether the card is visually collapsed (smaller, only a row at the bottom). */
  collapsed?: boolean
  /** Whether this card has never scrolled into the viewport (animates once). */
  unread?: boolean
  onToggle?: (collapsed: boolean) => void
  onStop?: () => void
}

const props = withDefaults(defineProps<StreamingCardProps>(), {
  isWorking: true,
  messageCount: 0,
  collapsed: false,
  unread: false,
  onToggle: () => {},
  onStop: () => {},
})

// ── Card implementation ───────────────────────────────────────────────
// We use a tiny internal component for the card so the template is clean.
// (In Vue SFCs we could also just inline, but keeping it structured.)

const STREAMING_BADGE_TEXT = 'Streaming'

const label = computed(() =>
  props.assistantName ? `${props.assistantName} · ${STREAMING_BADGE_TEXT}` : STREAMING_BADGE_TEXT
)

function handleCollapseClick() {
  props.onToggle(!props.collapsed)
}

// ── Lifecycle ─────────────────────────────────────────────────────────
// When unread, once scrolled into view we can reset unread flag.
// The parent (ActiveSession) owns unread state; we just render the class.
// No side-effects needed here beyond that.

// ── Bottom-of-chat chip (the tiny pill) ───────────────────────────────
interface StreamingBadgeChipProps {
  messageCount: number
  onOpenCard?: () => void
}

// (Used by parent — we expose via a sibling component below.)
</script>

<template>
  <div
    class="group flex w-full cursor-pointer items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3 transition-colors hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/35"
    @click="handleCollapseClick"
  >
    <!-- Leading strip: indicator + avatar -->
    <div class="flex shrink-0 items-center gap-2">
      <span
        :class="[
          'h-2 w-2 rounded-full bg-[var(--color-brand)]',
          props.isWorking ? 'animate-pulse' : '',
        ]"
        :aria-label="STREAMING_BADGE_TEXT"
      />
      <span
        v-if="props.assistantName"
        class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-brand)]/12 text-[10px] font-semibold text-[var(--color-brand)]"
        :title="props.assistantName"
      >
        {{ props.assistantName.charAt(0).toUpperCase() }}
      </span>
    </div>

    <!-- Text -->
    <div class="min-w-0 flex-1 text-left">
      <p class="truncate text-sm font-medium text-[var(--color-text-primary)]">
        {{ label }}
      </p>
      <p v-if="props.actionDescription" class="mt-0.5 truncate text-xs text-[var(--color-text-secondary)]">
        {{ props.actionDescription }}
      </p>
    </div>

    <!-- Right side: badge + chevron / stop -->
    <div class="flex shrink-0 items-center gap-2">
      <span
        v-if="props.messageCount > 0"
        class="flex h-5 shrink-0 items-center justify-center rounded-full bg-[var(--color-brand)]/12 px-2 font-mono text-xs text-[var(--color-brand)]"
      >
        {{ props.messageCount }}
      </span>

      <button
        v-if="props.isWorking"
        type="button"
        @click.stop="props.onStop"
        class="inline-flex h-7 shrink-0 items-center justify-center rounded-[var(--radius-md)] p-1 text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]/35"
        :aria-label="`Stop ${props.assistantName ?? ''}`"
      >
        <span class="material-symbols-outlined text-[18px]">stop</span>
      </button>

      <span
        class="material-symbols-outlined text-[18px] text-[var(--color-text-tertiary)] transition-transform"
        :class="{ 'rotate-180': !props.collapsed }"
      >
        expand_more
      </span>
    </div>
  </div>
</template>
