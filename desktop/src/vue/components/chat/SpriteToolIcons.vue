<script setup lang="ts">
/**
 * SpriteToolIcons — hand-drawn-style SVG icons for tool calls.
 *
 * Designed to match MadCop's existing hand-drawn mascot aesthetic
 * (ThinkingIndicator used a similar line-art style before the
 * ZCode rewrite). Each icon is a 16×16 line drawing with a
 * slightly wobbly stroke (stroke-linecap round + small
 * path imperfections) so it feels 'drawn' rather than 'generated'.
 *
 * The icon also pulses while the tool is in progress — a subtle
 * opacity wave that reads as 'working' without being distracting.
 *
 * Usage:
 *   <SpriteToolIcon name="write" :spinning="true" />
 */
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  /** Tool kind. Falls back to 'generic' for unknown tools. */
  name?: string
  /** Whether the tool is currently executing (shows pulse). */
  spinning?: boolean
  /** Override stroke color; defaults to currentColor. */
  color?: string
  /** Size in pixels. */
  size?: number
}>(), {
  name: 'generic',
  spinning: false,
  size: 16,
})

// Map common tool names to a canonical kind. The matching is
// lenient — we'd rather show a related icon than the generic one.
const KIND_MAP: Record<string, string> = {
  // file ops
  read: 'read', read_file: 'read',
  write: 'write', write_file: 'write', write_xlsx: 'write',
  edit: 'edit', edit_file: 'edit', multiedit: 'edit',
  // search
  glob: 'search', grep: 'search', search: 'search',
  web_search: 'websearch', websearch: 'websearch',
  web_fetch: 'webfetch', webfetch: 'webfetch',
  // shell / exec
  bash: 'bash', shell: 'bash', terminal: 'bash', sandbox: 'bash',
  // agent / memory
  agent: 'agent', task: 'agent', spawn_subagent: 'agent',
  query_rag: 'memory', recall_memory: 'memory', remember: 'memory',
  route: 'route',
  // misc
  get_current_time: 'time', get_time: 'time',
  get_weather: 'weather', weather: 'weather',
  echo: 'generic',
  clarify: 'ask', ask_user: 'ask',
}

const kind = computed(() => {
  const k = KIND_MAP[(props.name || '').toLowerCase()]
  return k || 'generic'
})

const strokeWidth = 2.0
</script>

<template>
  <span
    class="sprite-icon"
    :class="{ 'sprite-icon--spin': spinning }"
    :style="{
      width: `${size + (spinning ? 4 : 0)}px`,
      height: `${size + (spinning ? 4 : 0)}px`,
      color: color || 'currentColor',
    }"
    role="img"
    :aria-label="kind"
  >
    <!-- READ — an open book / document -->
    <svg v-if="kind === 'read'" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round">
      <path d="M4 5 C 4 4, 5 3.5, 6 3.5 L 11 3.5 L 12 5 L 12 20 L 6 20 C 5 20, 4 19.5, 4 18.5 Z" />
      <path d="M20 5 C 20 4, 19 3.5, 18 3.5 L 13 3.5 L 12 5 L 12 20 L 18 20 C 19 20, 20 19.5, 20 18.5 Z" />
      <path d="M7 8 L 10 8 M7 11 L 10 11" opacity="0.6" />
      <path d="M14 8 L 17 8 M14 11 L 17 11" opacity="0.6" />
    </svg>

    <!-- WRITE — a pencil over paper -->
    <svg v-else-if="kind === 'write'" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round">
      <path d="M5 19 L 5 16 L 16 5 L 19 8 L 8 19 Z" />
      <path d="M14 7 L 17 10" />
      <path d="M5 19 L 5 21 L 7 21" opacity="0.7" />
      <path d="M3 21 L 10 21" opacity="0.5" />
    </svg>

    <!-- EDIT — a pencil with a small spark (modification) -->
    <svg v-else-if="kind === 'edit'" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round">
      <path d="M5 19 L 5 16 L 14 7 L 17 10 L 8 19 Z" />
      <path d="M12 9 L 15 12" />
      <path d="M18 5 L 18 8 M16.5 6.5 L 19.5 6.5" opacity="0.7" />
    </svg>

    <!-- SEARCH — magnifying glass -->
    <svg v-else-if="kind === 'search'" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="10" cy="10" r="6" />
      <path d="M14.5 14.5 L 20 20" />
      <path d="M7 10 L 13 10 M10 7 L 10 13" opacity="0.5" />
    </svg>

    <!-- WEB SEARCH — globe with arrow -->
    <svg v-else-if="kind === 'websearch'" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="11" cy="11" r="7" />
      <path d="M4 11 L 18 11 M11 4 C 8 7, 8 15, 11 18 M11 4 C 14 7, 14 15, 11 18" opacity="0.6" />
      <path d="M18 18 L 21 21" />
    </svg>

    <!-- WEB FETCH — cloud download -->
    <svg v-else-if="kind === 'webfetch'" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round">
      <path d="M7 16 C 4 16, 3 14, 3 12 C 3 10, 5 8, 7 8 C 7 5, 10 4, 12 5 C 14 4, 17 5, 17 8 C 20 8, 21 10, 21 12" />
      <path d="M12 11 L 12 20 M9 17 L 12 20 L 15 17" />
    </svg>

    <!-- BASH / TERMINAL — a terminal window with cursor -->
    <svg v-else-if="kind === 'bash'" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round">
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M7 10 L 10 12 L 7 14" />
      <path d="M12 14 L 16 14" />
    </svg>

    <!-- AGENT / TASK — a robot head -->
    <svg v-else-if="kind === 'agent'" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round">
      <rect x="5" y="8" width="14" height="11" rx="2" />
      <path d="M12 4 L 12 8 M9 4 L 15 4" />
      <circle cx="9" cy="13" r="1" fill="currentColor" />
      <circle cx="15" cy="13" r="1" fill="currentColor" />
      <path d="M9 16 L 15 16" opacity="0.6" />
    </svg>

    <!-- MEMORY / RAG — a brain in a stack -->
    <svg v-else-if="kind === 'memory'" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 5 C 9 5, 7 7, 7 10 C 7 12, 8 13, 9 13 C 9 16, 11 18, 12 18 C 13 18, 15 16, 15 13 C 16 13, 17 12, 17 10 C 17 7, 15 5, 12 5 Z" />
      <path d="M12 5 L 12 18" opacity="0.4" />
      <path d="M5 20 L 19 20" opacity="0.5" />
    </svg>

    <!-- ROUTE — a fork in the road -->
    <svg v-else-if="kind === 'route'" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="6" cy="6" r="2" />
      <circle cx="18" cy="6" r="2" />
      <circle cx="12" cy="18" r="2" />
      <path d="M6 8 L 6 12 C 6 14, 11 15, 12 16 M18 8 L 18 12 C 18 14, 13 15, 12 16" />
    </svg>

    <!-- TIME — a clock -->
    <svg v-else-if="kind === 'time'" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8 L 12 12 L 15 14" />
    </svg>

    <!-- WEATHER — sun behind cloud -->
    <svg v-else-if="kind === 'weather'" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="8" cy="8" r="3" />
      <path d="M8 2 L 8 4 M2 8 L 4 8 M12 8 L 14 8 M8 12 L 8 14 M3.5 3.5 L 5 5 M11 3.5 L 12.5 5" opacity="0.6" />
      <path d="M8 16 C 6 16, 5 17, 5 18.5 C 5 20, 6 21, 8 21 L 17 21 C 19 21, 20 20, 20 18.5 C 20 17, 19 16, 17 16 C 17 14, 15 13, 13 14" />
    </svg>

    <!-- ASK / CLARIFY — a question mark in a speech bubble -->
    <svg v-else-if="kind === 'ask'" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round">
      <path d="M4 5 C 4 4, 5 3, 6 3 L 18 3 C 19 3, 20 4, 20 5 L 20 14 C 20 15, 19 16, 18 16 L 10 16 L 6 20 L 6 16 C 5 16, 4 15, 4 14 Z" />
      <path d="M10 8 C 10 6, 12 6, 12 8 C 12 9, 11 9.5, 11 10.5" opacity="0.8" />
      <circle cx="11.5" cy="13" r="0.6" fill="currentColor" />
    </svg>

    <!-- GENERIC — three dots -->
    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="6" cy="12" r="1.2" fill="currentColor" />
      <circle cx="12" cy="12" r="1.2" fill="currentColor" />
      <circle cx="18" cy="12" r="1.2" fill="currentColor" />
    </svg>
  </span>
</template>

<style scoped>
.sprite-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  /* v3.7.10 — use text-secondary (darker) instead of outline so the
   * hand-drawn line art is actually visible. The previous outline
   * tint was too light to read on a white background. */
  color: var(--color-text-secondary, #555);
}
.sprite-icon svg {
  width: 100%;
  height: 100%;
}

/* v3.7.9 — pulse + wobble animations are defined in globals.css
 * as .madcop-sprite-pulse / .madcop-sprite-wobble so they aren't
 * hashed by Vue's <style scoped> rewriter (which renames
 * @keyframes and breaks the animation reference). */
.sprite-icon--spin {
  animation: madcop-sprite-pulse 1.6s ease-in-out infinite;
}
.sprite-icon--spin svg {
  animation: madcop-sprite-wobble 2.4s ease-in-out infinite;
  transform-origin: 50% 50%;
}

@media (prefers-reduced-motion: reduce) {
  .sprite-icon--spin,
  .sprite-icon--spin svg { animation: none; opacity: 1; }
}
</style>