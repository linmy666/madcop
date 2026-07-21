<script setup lang="ts">
/**
 * ThinkingIndicator — ZCode-style streaming reasoning panel.
 *
 * v3.7.6 — completely rewritten to match ZCode's visual language:
 *   - Collapsible row with a gradient-flow "Thinking..." label
 *     while tokens are arriving; flips to a static dim "Thought · Ns"
 *     when done.
 *   - Reasoning body is plain inline black text on the page
 *     background — NO frame, NO colored box. Reads as part of the
 *     chat narrative.
 *   - The live streaming is indicated only by the gradient label
 *     and a 3-dot pulse at the end of the body.
 *
 * Props:
 *   reasoningContent — the accumulated text (already filtered for
 *     ReAct protocol markers upstream in chatStore).
 *   activeToolName   — optional, shows a "using <tool>" suffix on
 *     the label.
 *   planStep         — optional, unused but kept for backward compat.
 */
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps<{
  reasoningContent?: string | null
  activeToolName?: string | null
  planStep?: { label: string; tool: string | null; index: number; total: number; status: string } | null
  /** When false, the parent tells us the turn finished — we flip
   *  from "Thinking..." to "Thought · Ns". */
  isStreaming?: boolean
}>()

// Default expanded so streaming narrative is visible immediately.
const showReasoning = ref(true)

// Elapsed timer for the "Thought · Ns" label after completion.
const elapsedMs = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  timer = setInterval(() => { elapsedMs.value += 100 }, 100)
})
onUnmounted(() => { if (timer) clearInterval(timer) })

const elapsedSeconds = computed(() => Math.max(1, Math.round(elapsedMs.value / 1000)))

// Whether the model is still emitting reasoning. If the parent
// doesn't tell us (isStreaming undefined), infer from content
// growth — but the parent should pass it explicitly.
const streaming = computed(() => props.isStreaming !== false)

const labelText = computed(() =>
  streaming.value ? '正在思考' : `已思考 · ${elapsedSeconds.value}s`
)

const hasContent = computed(() => !!(props.reasoningContent || '').trim())
const trimmedContent = computed(() => (props.reasoningContent || '').trim())

// Tool suffix on the label ("正在思考 · write_file")
const toolSuffix = computed(() => {
  const t = (props.activeToolName || '').trim()
  if (!t) return ''
  return ` · ${t}`
})
</script>

<template>
  <div class="zreasoning" role="region" aria-label="AI 思考过程">
    <!-- Trigger row: icon + gradient label + chevron -->
    <button
      type="button"
      class="zreasoning__trigger"
      :aria-expanded="showReasoning"
      @click="showReasoning = !showReasoning"
    >
      <!-- Brain icon (inline SVG so no extra dep) -->
      <svg class="zreasoning__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z" />
        <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z" />
      </svg>

      <!-- Gradient-flow label while streaming; dim static when done -->
      <span v-if="streaming" class="zcode-gradient-text zreasoning__label">{{ labelText }}{{ toolSuffix }}</span>
      <span v-else class="zreasoning__label zreasoning__label--done">{{ labelText }}</span>

      <!-- Chevron (only visible on hover, ZCode pattern) -->
      <svg
        class="zreasoning__chevron"
        :class="{ 'zreasoning__chevron--open': showReasoning }"
        viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
      >
        <path d="m9 18 6-6-6-6" />
      </svg>
    </button>

    <!-- Body: plain inline black text, no frame, no background -->
    <div v-if="showReasoning && hasContent" class="zreasoning__body zcode-stream-in">
      <span class="zreasoning__text">{{ trimmedContent }}</span>
      <!-- 3-dot pulse while streaming; hidden when done -->
      <span v-if="streaming" class="zreasoning__dots" aria-hidden="true">
        <i></i><i></i><i></i>
      </span>
    </div>
  </div>
</template>

<style scoped>
.zreasoning {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 4px 0;
  /* No background, no border — blends into the chat surface. */
}

.zreasoning__trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 2px 0;
  font-size: 14px;
  line-height: 20px;
  align-self: flex-start;
  border-radius: 6px;
  transition: opacity 120ms;
}
.zreasoning__trigger:hover {
  opacity: 0.75;
}

.zreasoning__icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: var(--zcode-fg-subtlest, rgba(38, 38, 38, 0.40));
}

.zreasoning__label {
  font-size: 14px;
  font-weight: 500;
}
.zreasoning__label--done {
  color: var(--zcode-fg-subtlest, rgba(38, 38, 38, 0.40));
}

.zreasoning__chevron {
  width: 14px;
  height: 14px;
  color: var(--zcode-fg-subtlest, rgba(38, 38, 38, 0.40));
  opacity: 0;
  transform: rotate(0deg);
  transition: opacity 120ms, transform 120ms;
}
.zreasoning__trigger:hover .zreasoning__chevron {
  opacity: 1;
}
.zreasoning__chevron--open {
  transform: rotate(90deg);
}

.zreasoning__body {
  /* Inline narrative text, not a code block. */
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text-primary, #0d0d0d);
  font-family: var(--font-sans, ui-sans-serif, system-ui, sans-serif);
  white-space: pre-wrap;
  word-break: break-word;
  /* Indent slightly so it reads as 'under' the trigger. */
  padding-left: 24px;
  max-width: 100%;
}

.zreasoning__text {
  /* No special styling — inherits body color. */
}

/* 3-dot pulse at the end of streaming reasoning. Discreet. */
.zreasoning__dots {
  display: inline-flex;
  align-items: flex-end;
  gap: 3px;
  margin-left: 4px;
  vertical-align: baseline;
}
.zreasoning__dots i {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--color-text-primary, #0d0d0d);
  opacity: 0.4;
  animation: zreasoning-dot 1.2s ease-in-out infinite;
}
.zreasoning__dots i:nth-child(2) { animation-delay: 0.15s; }
.zreasoning__dots i:nth-child(3) { animation-delay: 0.30s; }
@keyframes zreasoning-dot {
  0%, 100% { opacity: 0.25; transform: translateY(0); }
  50%      { opacity: 0.9; transform: translateY(-1px); }
}

@media (prefers-reduced-motion: reduce) {
  .zreasoning__dots i { animation: none; opacity: 0.6; }
}
</style>