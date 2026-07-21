<template>
  <div class="thinking-indicator flex items-center gap-3 py-2.5">
    <!-- Hand-drawn MadCop mascot — simple black line art, pose per phase -->
    <div class="thinking-mascot" :class="`thinking-mascot--${currentPhase}`">
      <svg
        viewBox="0 0 64 64"
        width="48"
        height="48"
        fill="none"
        stroke="currentColor"
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="1.8"
        class="mascot-svg"
      >
        <!-- Body: waterdrop shape -->
        <path
          d="M 32 10
             C 18 16, 14 32, 14 42
             C 14 52, 22 58, 32 58
             C 42 58, 50 52, 50 42
             C 50 32, 46 16, 32 10 Z"
        />

        <!-- Phase A: analyzing — pupils move around -->
        <g v-if="currentPhase === 'analyzing'">
          <circle cx="26" cy="34" r="2" fill="currentColor" stroke="none">
            <animate attributeName="cx" values="24;28;24" dur="1.2s" repeatCount="indefinite" />
          </circle>
          <circle cx="38" cy="34" r="2" fill="currentColor" stroke="none">
            <animate attributeName="cx" values="40;36;40" dur="1.2s" repeatCount="indefinite" />
          </circle>
          <!-- neutral mouth -->
          <line x1="28" y1="44" x2="36" y2="44" />
        </g>

        <!-- Phase B: reasoning — eyes closed, thinking bubble -->
        <g v-else-if="currentPhase === 'reasoning'">
          <!-- closed eyes: gentle arcs -->
          <path d="M 22 34 Q 26 31, 30 34" />
          <path d="M 34 34 Q 38 31, 42 34" />
          <!-- small thinking bubble dots -->
          <circle cx="54" cy="22" r="1.2" fill="currentColor" stroke="none">
            <animate attributeName="opacity" values="0.3;1;0.3" dur="1.5s" repeatCount="indefinite" />
          </circle>
          <circle cx="58" cy="16" r="1.8" fill="currentColor" stroke="none">
            <animate attributeName="opacity" values="0.3;1;0.3" dur="1.5s" begin="0.3s" repeatCount="indefinite" />
          </circle>
          <circle cx="60" cy="8" r="2.4" fill="currentColor" stroke="none">
            <animate attributeName="opacity" values="0.3;1;0.3" dur="1.5s" begin="0.6s" repeatCount="indefinite" />
          </circle>
        </g>

        <!-- Phase C: generating — eyes bright, writing -->
        <g v-else>
          <!-- wide open eyes -->
          <circle cx="26" cy="34" r="3.5" fill="none" />
          <circle cx="38" cy="34" r="3.5" fill="none" />
          <circle cx="26" cy="34" r="1.5" fill="currentColor" stroke="none" />
          <circle cx="38" cy="34" r="1.5" fill="currentColor" stroke="none" />
          <!-- excited smile -->
          <path d="M 28 44 Q 32 48, 36 44" />
          <!-- small pencil mark next to body -->
          <g class="pencil">
            <line x1="54" y1="44" x2="60" y2="50" />
            <line x1="60" y1="50" x2="62" y2="52" />
          </g>
        </g>
      </svg>
    </div>

    <!-- Phase label + hand-written hint + progress bar (all black) -->
    <div class="flex-1 min-w-0 pt-0.5">
      <div class="flex items-baseline gap-2">
        <!-- v3.7.3 — opencode/codex-style shimmer sweep on the status
             label. Cosine 'spotlight' travels across the text every
             2s; characters near the spotlight brighten + bold.
             Fades to a static label under prefers-reduced-motion. -->
        <ThinkingDots
          variant="shimmer"
          :label="statusLabel"
          color="var(--color-text-primary)"
          class="thinking-shimmer"
        />
        <span class="text-[10px] text-[var(--color-text-tertiary)] tabular-nums ml-auto">
          {{ elapsedText }}
        </span>
      </div>
      <div class="text-[11px] text-[var(--color-text-secondary)] mt-0.5 italic font-hand">
        {{ statusHint }}
      </div>

      <!-- Live reasoning chain (model's real thinking).
           v3.7.5 — defaults to EXPANDED while the agent is working
           so the user sees the streaming narrative form live
           (opencode/ZCode parity). Adds a blinking caret at the
           end while new tokens are arriving, and a subtle fade-in
           on newly appended text. Auto-collapses when the turn
           finishes (parent hides the whole indicator on idle). -->
      <div v-if="reasoningContent && reasoningContent.trim()" class="mt-1.5">
        <button
          type="button"
          class="td-toggle"
          @click="showReasoning = !showReasoning"
        >
          <span class="td-toggle__icon">{{ showReasoning ? '▾' : '▸' }}</span>
          <span>{{ showReasoning ? '收起思考过程' : '查看思考过程' }}</span>
        </button>
        <div v-if="showReasoning" class="td-stream-wrap">
          <pre
            class="td-stream"
          ><span class="td-stream__text">{{ reasoningContent.trim() }}</span><span class="td-stream__caret" aria-hidden="true">▍</span></pre>
        </div>
      </div>

      <div class="relative mt-1.5 h-[2px] overflow-hidden rounded-full bg-[var(--color-border)]/40">
        <div
          class="h-full rounded-full transition-all duration-700 ease-out bg-[var(--color-text-primary)]"
          :style="{ width: progressPercent + '%' }"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import ThinkingDots from './ThinkingDots.vue'

const props = defineProps<{
  reasoningContent?: string | null
  hasText?: boolean
  activeToolName?: string | null
  /** Current plan step context: { label, tool, index, total, status } */
  planStep?: {
    label: string
    tool: string | null
    index: number
    total: number
    status: string
  } | null
}>()

// v3.7.5 — default to EXPANDED so the user sees streaming thinking
// without needing to click. The parent hides the whole indicator
// when the turn finishes, so we don't need to auto-collapse.
const showReasoning = ref(true)

const elapsedMs = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  timer = setInterval(() => {
    elapsedMs.value += 100
  }, 100)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

// A tool call is the most concrete "what's happening" signal.
const isToolPhase = computed(() => Boolean(props.activeToolName))
// Plan steps being generated/executed.
const isPlanPhase = computed(() => Boolean(props.planStep))

const currentPhase = computed<'analyzing' | 'reasoning' | 'generating'>(() => {
  if (isToolPhase.value) return 'generating'
  if (isPlanPhase.value) return 'reasoning'
  const t = elapsedMs.value
  if (t < 2500) return 'analyzing'
  if (t < 5500) return 'reasoning'
  return 'generating'
})

// Real, data-driven status line instead of fake rotating hints.
const statusLabel = computed(() => {
  if (isToolPhase.value) return `正在调用工具 · ${props.activeToolName}`
  if (isPlanPhase.value) {
    return `正在规划 · 第 ${props.planStep!.index}/${props.planStep!.total} 步`
  }
  return phaseLabel.value
})

const statusHint = computed(() => {
  if (isToolPhase.value) return `执行 ${props.activeToolName} 工具，请稍候…`
  if (isPlanPhase.value) {
    const step = props.planStep!
    const toolNote = step.tool ? `（工具：${step.tool}）` : ''
    return `${step.label}${toolNote}`
  }
  return phaseHint.value
})

const phaseLabel = computed(() => {
  switch (currentPhase.value) {
    case 'analyzing': return '正在分析'
    case 'reasoning': return '正在推理'
    case 'generating': return '正在生成'
  }
})

const hintIndex = ref(0)
const hints = {
  analyzing: [
    '翻看笔记，整理上下文…',
    '在问题里找关键信号…',
    '拆解需求，列要点…',
  ],
  reasoning: [
    '在脑子里过一遍逻辑…',
    '比对可能的路径…',
    '从几个角度推演…',
  ],
  generating: [
    '把想法写成字…',
    '斟酌措辞…',
    '组织最终答案…',
  ],
}
const phaseHint = computed(() => hints[currentPhase.value][hintIndex.value])

// Progress: plan step completion, else a gentle decorative pulse.
const progressPercent = computed(() => {
  if (isPlanPhase.value && props.planStep) {
    return Math.round((props.planStep.index / props.planStep.total) * 100)
  }
  const t = elapsedMs.value
  if (t < 2500) return (t / 2500) * 100
  if (t < 5500) return ((t - 2500) / 3000) * 100
  const phaseT = (t - 5500) / 1000
  return 80 + Math.sin(phaseT * 0.5) * 7.5
})

const elapsedText = computed(() => {
  const secs = elapsedMs.value / 1000
  if (secs < 60) return `${secs.toFixed(1)}s`
  return `${Math.floor(secs / 60)}m ${(secs % 60).toFixed(0)}s`
})
</script>

<style scoped>
.thinking-mascot {
  position: relative;
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--color-text-primary, #1f2937);
}

.mascot-svg {
  display: block;
}

/* Body sway per phase — gentle, hand-drawn feel */
.thinking-mascot--analyzing .mascot-svg {
  animation: sway-analyzing 2.4s ease-in-out infinite;
  transform-origin: center;
}
.thinking-mascot--reasoning .mascot-svg {
  animation: sway-reasoning 1.8s ease-in-out infinite;
  transform-origin: center bottom;
}
.thinking-mascot--generating .mascot-svg {
  animation: sway-generating 1.4s ease-in-out infinite;
  transform-origin: center top;
}

@keyframes sway-analyzing {
  0%, 100% { transform: rotate(-2.5deg); }
  50%      { transform: rotate(2.5deg); }
}
@keyframes sway-reasoning {
  0%, 100% { transform: translateY(0) rotate(0deg); }
  50%      { transform: translateY(-1px) rotate(-1deg); }
}
@keyframes sway-generating {
  0%, 100% { transform: translateY(0); }
  50%      { transform: translateY(1.5px); }
}

.font-hand {
  font-family: var(--font-body);
  font-style: italic;
  letter-spacing: 0.2px;
}

/* v3.7.5 — streaming reasoning display.
 * Borrowed from opencode (markdown streaming cursor) and codex
 * (caret blink on live text). The caret ▍ is appended after the
 * accumulated text and blinks at 1s; the wrapper has a subtle
 * background tint so the user can tell it's 'live' content. */
.td-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: var(--color-text-tertiary);
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  transition: color 120ms, background 120ms;
}
.td-toggle:hover {
  color: var(--color-text-secondary);
  background: var(--color-surface-hover, rgba(0,0,0,0.04));
}
.td-toggle__icon {
  font-size: 9px;
  width: 8px;
  display: inline-block;
}
.td-stream-wrap {
  margin-top: 4px;
  position: relative;
}
.td-stream {
  margin: 0;
  max-height: 240px;
  overflow-y: auto;
  word-break: break-word;
  border-radius: 8px;
  background: color-mix(in srgb, var(--color-brand, #7c3aed) 6%, var(--color-surface, #fff));
  border: 1px solid color-mix(in srgb, var(--color-brand, #7c3aed) 18%, var(--color-border, #e5e5e7));
  padding: 8px 12px;
  font-size: 12px;
  line-height: 1.65;
  color: var(--color-text-secondary, #555);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre-wrap;
}
.td-stream__caret {
  display: inline-block;
  width: 6px;
  margin-left: 1px;
  color: var(--color-brand, #7c3aed);
  font-weight: 700;
  animation: td-caret-blink 1s steps(2, start) infinite;
}
@keyframes td-caret-blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .td-stream__caret { animation: none; opacity: 0.6; }
}
</style>