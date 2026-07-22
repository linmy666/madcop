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

        <!-- Phase B: reasoning — eyes closed.
             v3.8.2 — removed the 3 animated thinking-bubble circles.
             They pulsed at 1.5s while the text dots pulse at 1.2s,
             creating a visually jarring mismatch. The mascot stays
             static now; the 'thinking' motion is carried solely by
             the .thinking-dots at the end of the reasoning text. -->
        <g v-else-if="currentPhase === 'reasoning'">
          <!-- closed eyes: gentle arcs -->
          <path d="M 22 34 Q 26 31, 30 34" />
          <path d="M 34 34 Q 38 31, 42 34" />
          <!-- static small thinking bubble (no animation) -->
          <circle cx="56" cy="18" r="1.5" fill="currentColor" stroke="none" opacity="0.5" />
          <circle cx="60" cy="10" r="2.2" fill="currentColor" stroke="none" opacity="0.5" />
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
        <span class="text-[12px] font-semibold text-[var(--color-text-primary)]">
          {{ statusLabel }}
        </span>
        <span class="text-[10px] text-[var(--color-text-tertiary)] tabular-nums ml-auto">
          {{ elapsedText }}
        </span>
      </div>
      <div class="text-[11px] text-[var(--color-text-secondary)] mt-0.5 italic font-hand">
        {{ statusHint }}
      </div>

      <!-- Live reasoning chain — v3.8.1 no frame, no background.
           Plain inline text that flows like the rest of the chat.
           A pulsing dot at the end signals 'still thinking'.
           Collapsible via the small toggle above. -->
      <div v-if="reasoningContent && reasoningContent.trim()" class="mt-1.5">
        <button
          type="button"
          class="text-[10px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] underline-offset-2 hover:underline"
          @click="showReasoning = !showReasoning"
        >
          {{ showReasoning ? '收起思考过程' : '查看思考过程' }}
        </button>
        <div v-if="showReasoning" class="zcode-stream-in mt-1 text-[12px] leading-[1.7] text-[var(--color-text-secondary)]">
          <span class="whitespace-pre-wrap break-words">{{ reasoningContent.trim() }}</span><span class="thinking-dots" aria-hidden="true"><i></i><i></i><i></i></span>
        </div>
      </div>

      <!-- v3.8.1 — removed the static progress bar. It didn't convey
           real progress and broke the 'flowing' feel. The pulsing
           dots above now carry the 'working' signal. -->
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

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

/* v3.8.1 — pulsing dots at the end of streaming reasoning.
 * Three dots that pulse in sequence, signaling 'still thinking'.
 * Defined here (scoped) with unhashed @keyframes name won't work,
 * so we use a vendor-prefixed name that Vue won't rewrite. */
.thinking-dots {
  display: inline-flex;
  align-items: baseline;
  gap: 2px;
  margin-left: 4px;
  vertical-align: baseline;
}
.thinking-dots i {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--color-text-secondary, #555);
  opacity: 0.3;
  animation: thinking-dot-pulse 1.2s ease-in-out infinite;
}
.thinking-dots i:nth-child(2) { animation-delay: 0.15s; }
.thinking-dots i:nth-child(3) { animation-delay: 0.30s; }

/* Note: Vue scoped rewriter hashes @keyframes names. We work around
 * this by NOT using scoped for this keyframe — define it in the
 * global stylesheet instead. The class .thinking-dots stays scoped
 * (it's just element styling), only the animation name is global. */
</style>

<!-- Global keyframe (not scoped) so Vue doesn't hash the name -->
<style>
@keyframes thinking-dot-pulse {
  0%, 100% { opacity: 0.25; transform: translateY(0); }
  50%      { opacity: 0.9;  transform: translateY(-1px); }
}
@media (prefers-reduced-motion: reduce) {
  .thinking-dots i { animation: none; opacity: 0.5; }
}
</style>