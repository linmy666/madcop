<script setup lang="ts">
/**
 * ThinkingDots — opencode/codex-inspired thinking indicator.
 *
 * Three animation primitives borrowed from research:
 *
 *  1. Pulsing dot grid (opencode session-ui): a 5×5 grid of dots
 *     that light up in a diagonal wave, with the center dot as a
 *     steady 'heartbeat'. Gives an organic, breathing feel that's
 *     less mechanical than a spinner.
 *
 *  2. Braille spinner (industry standard, both opencode + codex):
 *     ⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏ cycling at 80ms. Compact, fits inline.
 *
 *  3. Shimmer text (codex): a cosine 'spotlight' sweeps across the
 *     label text every 2s, characters near the spotlight brighten
 *     to white + bold, others stay dim. Feels 'AI is thinking'.
 *
 * All three respect prefers-reduced-motion: animations stop, only
 * the static center dot + dimmed label remain (codex's MotionMode
 * pattern, opencode's animations_enabled KV).
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

const props = withDefaults(defineProps<{
  /** Inline label after the dots (e.g. "Thinking", "智能体思考中"). */
  label?: string
  /** Which visual to lead with. */
  variant?: 'dots' | 'spinner' | 'shimmer'
  /** Override theme color (CSS color string). Defaults to brand. */
  color?: string
  size?: number
}>(), {
  label: 'Thinking',
  variant: 'dots',
  size: 14,
})

// --- Braille spinner (80ms cadence, opencode default) ---
const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
const spinnerIdx = ref(0)
let spinTimer: number | null = null

// --- Shimmer position (2s cosine sweep, codex default) ---
const shimmerPos = ref(0)
let shimmerRaf: number | null = null
const shimmerStart = ref(0)

const reducedMotion = ref(false)

function detectReducedMotion() {
  reducedMotion.value = typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

onMounted(() => {
  detectReducedMotion()
  if (reducedMotion.value) return

  if (props.variant === 'spinner') {
    spinTimer = window.setInterval(() => {
      spinnerIdx.value = (spinnerIdx.value + 1) % SPINNER_FRAMES.length
    }, 80)
  }
  if (props.variant === 'shimmer') {
    shimmerStart.value = performance.now()
    const tick = (now: number) => {
      const elapsed = now - shimmerStart.value
      // 2s period, position 0..1
      shimmerPos.value = (elapsed % 2000) / 2000
      shimmerRaf = requestAnimationFrame(tick)
    }
    shimmerRaf = requestAnimationFrame(tick)
  }
})

onBeforeUnmount(() => {
  if (spinTimer) clearInterval(spinTimer)
  if (shimmerRaf) cancelAnimationFrame(shimmerRaf)
})

// Shimmer: compute per-char brightness
const shimmerChars = computed(() => {
  const text = props.label || ''
  if (props.variant !== 'shimmer' || reducedMotion.value) {
    return text.split('').map(c => ({ c, t: 0 }))
  }
  const period = text.length + 20 // 10-char padding each side
  const pos = shimmerPos.value * period
  return text.split('').map((c, i) => {
    const dist = Math.abs(i + 10 - pos)
    const t = dist <= 5 ? 0.5 * (1 + Math.cos(Math.PI * dist / 5)) : 0
    return { c, t }
  })
})

// Pulsing dot grid: 5×5 = 25 dots, each with its own delay
// forming a diagonal wave (opencode session-ui pattern).
const dotDelays = computed(() => {
  const out: number[] = []
  for (let r = 0; r < 5; r++) {
    for (let c = 0; c < 5; c++) {
      // Diagonal wave: dots along the same r+c animate together
      out.push((r + c) * 0.12)
    }
  }
  return out
})
</script>

<template>
  <span class="thinking-dots" :style="{ '--td-color': color || 'var(--color-brand, #7c3aed)' }">
    <!-- Variant 1: 5×5 pulsing dot grid -->
    <span v-if="variant === 'dots'" class="td-grid" :style="{ width: `${size * 2.5}px`, height: `${size * 2.5}px` }">
      <template v-if="reducedMotion">
        <!-- Static center dot only -->
        <span class="td-dot td-dot--center-static" :style="{ width: `${size / 5}px`, height: `${size / 5}px` }" />
      </template>
      <template v-else>
        <span
          v-for="(delay, i) in dotDelays"
          :key="i"
          class="td-dot"
          :class="{ 'td-dot--center': i === 12 }"
          :style="{
            animationDelay: `${delay}s`,
            width: `${size / 5}px`,
            height: `${size / 5}px`,
          }"
        />
      </template>
    </span>

    <!-- Variant 2: Braille spinner -->
    <span v-else-if="variant === 'spinner'" class="td-spinner">
      <template v-if="reducedMotion">⋯</template>
      <template v-else>{{ SPINNER_FRAMES[spinnerIdx] }}</template>
    </span>

    <!-- Variant 3: Shimmer text -->
    <span v-else class="td-shimmer-label">
      <template v-if="reducedMotion || variant !== 'shimmer'">{{ label }}</template>
      <template v-else>
        <span
          v-for="(p, i) in shimmerChars"
          :key="i"
          class="td-shimmer-char"
          :style="{ opacity: 0.3 + p.t * 0.7, fontWeight: p.t > 0.5 ? 700 : 400 }"
        >{{ p.c }}</span>
      </template>
    </span>

    <!-- Optional label next to dots/spinner -->
    <span v-if="label && variant !== 'shimmer'" class="td-label">{{ label }}</span>
  </span>
</template>

<style scoped>
.thinking-dots {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--td-color);
  font-size: 12px;
  line-height: 1;
  vertical-align: middle;
}

/* --- Dot grid --- */
.td-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  grid-template-rows: repeat(5, 1fr);
  gap: 1px;
  align-items: center;
  justify-items: center;
}
.td-dot {
  background: var(--td-color);
  border-radius: 50%;
  opacity: 0.2;
  animation: td-pulse 1.2s ease-in-out infinite;
}
.td-dot--center {
  opacity: 1;  /* heartbeat: always on */
  animation: none;
}
.td-dot--center-static {
  opacity: 1;
  background: var(--td-color);
  border-radius: 50%;
}
@keyframes td-pulse {
  0%, 100% { opacity: 0.2; transform: scale(0.8); }
  50%      { opacity: 1;   transform: scale(1.1); }
}

/* --- Spinner --- */
.td-spinner {
  font-family: ui-monospace, monospace;
  font-size: 14px;
  line-height: 1;
}

/* --- Shimmer --- */
.td-shimmer-label {
  display: inline-flex;
  letter-spacing: 0.02em;
}
.td-shimmer-char {
  color: var(--td-color);
  transition: none;
}

/* --- Side label --- */
.td-label {
  color: var(--color-text-secondary, #666);
  font-weight: 500;
}

@media (prefers-reduced-motion: reduce) {
  .td-dot { animation: none !important; opacity: 0.2; }
  .td-dot--center { opacity: 1; }
}
</style>