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
        <span class="text-[12px] font-semibold text-[var(--color-text-primary)]">
          {{ phaseLabel }}
        </span>
        <span class="text-[10px] text-[var(--color-text-tertiary)] tabular-nums ml-auto">
          {{ elapsedText }}
        </span>
      </div>
      <div class="text-[11px] text-[var(--color-text-secondary)] mt-0.5 italic font-hand">
        {{ phaseHint }}
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

const props = defineProps<{
  reasoningContent?: string | null
  hasText?: boolean
}>()

const elapsedMs = ref(0)
let timer: ReturnType<typeof setInterval> | null = null
let phaseHintTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  timer = setInterval(() => {
    elapsedMs.value += 100
  }, 100)
  phaseHintTimer = setInterval(() => {
    hintIndex.value = (hintIndex.value + 1) % 3
  }, 2500)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (phaseHintTimer) clearInterval(phaseHintTimer)
})

const currentPhase = computed(() => {
  const t = elapsedMs.value
  if (t < 2500) return 'analyzing'
  if (t < 5500) return 'reasoning'
  return 'generating'
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

const progressPercent = computed(() => {
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
  font-family: 'Bradley Hand', 'Comic Sans MS', 'Marker Felt', cursive;
  font-style: italic;
  letter-spacing: 0.2px;
}
</style>