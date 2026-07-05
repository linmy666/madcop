<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

/**
 * ThinkingAnimation — Vue 3 port of components/chat/ThinkingAnimation.tsx
 * Hand-drawn stick-figure step animation. Pure SVG/CSS.
 */

export type Stage = 'reading' | 'thinking' | 'searching' | 'ready'

export interface ThinkingAnimationProps {
  active?: boolean
  stage?: string | null
}

const props = withDefaults(defineProps<ThinkingAnimationProps>(), {
  active: true,
  stage: null,
})

const STAGES: Stage[] = ['reading', 'thinking', 'searching', 'ready']
const STAGE_LABELS: Record<Stage, string> = {
  reading: '正在读问题', thinking: '正在拆解思路', searching: '正在查记忆 / 工具', ready: '正在写答案',
}

const stage = ref<Stage>('reading')
const tick = ref(0)
let intervalId: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  if (props.stage && STAGES.includes(props.stage as Stage)) stage.value = props.stage as Stage
  if (!props.active) return
  let i = 0
  intervalId = setInterval(() => { i = (i + 1) % STAGES.length; stage.value = STAGES[i]; tick.value++ }, 2200)
})

onUnmounted(() => { if (intervalId) clearInterval(intervalId) })
</script>

<template>
  <div role="status" aria-live="polite" :data-thinking-stage="stage" :data-thinking-tick="tick"
    class="flex items-center gap-2 rounded-lg border border-[var(--color-brand)]/20 bg-[var(--color-brand)]/5 px-3 py-2">
    <div class="relative h-9 w-9 shrink-0">
      <svg viewBox="0 0 40 40" width="36" height="36" fill="none" stroke="currentColor"
        stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
        class="thinking-figure" :data-stage="stage">
        <circle cx="20" cy="11" r="4.2" class="thinking-head" />
        <line x1="20" y1="15" x2="20" y2="26" />
        <template v-if="stage === 'reading'">
          <line x1="20" y1="19" x2="14" y2="24" /><line x1="20" y1="19" x2="26" y2="24" />
        </template>
        <template v-if="stage === 'thinking'">
          <line x1="20" y1="19" x2="13" y2="24" /><line x1="20" y1="19" x2="27" y2="14" />
        </template>
        <template v-if="stage === 'searching'">
          <line x1="20" y1="19" x2="13" y2="24" /><line x1="20" y1="19" x2="29" y2="19" />
        </template>
        <template v-if="stage === 'ready'">
          <line x1="20" y1="19" x2="13" y2="24" /><line x1="20" y1="19" x2="27" y2="11" />
        </template>
        <line x1="20" y1="26" x2="15" y2="34" /><line x1="20" y1="26" x2="25" y2="34" />
        <g v-if="stage === 'reading'" class="thinking-prop-reading">
          <rect x="11" y="22" width="9" height="6" rx="0.6" />
          <line x1="13" y1="25" x2="18" y2="25" /><line x1="13" y1="27" x2="18" y2="27" />
        </g>
        <g v-if="stage === 'thinking'" class="thinking-prop-thinking">
          <path d="M 27 9 q 1.2 -1 2 0 q 1.2 -1 2 0" />
          <circle cx="32" cy="6" r="0.8" fill="currentColor" />
          <line x1="27" y1="14" x2="30" y2="11" />
          <line x1="30" y1="11" x2="31.4" y2="9.6" stroke-width="0.7" />
        </g>
        <g v-if="stage === 'searching'" class="thinking-prop-searching">
          <circle cx="29" cy="19" r="2.4" />
          <line x1="30.7" y1="20.7" x2="32.6" y2="22.6" stroke-width="1.1" />
          <line x1="28" y1="19" x2="30" y2="19" stroke-width="0.6" />
        </g>
        <g v-if="stage === 'ready'" class="thinking-prop-ready">
          <circle cx="28" cy="9" r="1.4" fill="currentColor" stroke="none" />
          <line x1="25" y1="6" x2="26" y2="7" stroke-width="0.9" />
          <line x1="31" y1="7" x2="30" y2="6" stroke-width="0.9" />
          <line x1="32" y1="11" x2="33" y2="10" stroke-width="0.9" />
          <line x1="25" y1="11" x2="24" y2="10" stroke-width="0.9" />
        </g>
      </svg>
    </div>
    <div class="flex flex-col leading-tight">
      <span class="text-[12px] font-medium text-[var(--color-brand)]">MadCop 正在思考</span>
      <span :key="stage" class="text-[11px] text-[var(--color-text-secondary)] thinking-stage-text">
        {{ STAGE_LABELS[stage] }}<span class="thinking-dots" />
      </span>
    </div>
    <style scoped>
@keyframes thinking-stage-text-fade { 0% { opacity: 0; transform: translateY(2px); } 20%, 100% { opacity: 1; transform: translateY(0); } }
.thinking-stage-text { display: inline-block; animation: thinking-stage-text-fade 350ms ease-out; }
@keyframes thinking-wobble { 0%, 100% { transform: translate(0,0) rotate(0deg); } 25% { transform: translate(-0.2px,0.1px) rotate(-0.5deg); } 50% { transform: translate(0.2px,-0.1px) rotate(0.4deg); } 75% { transform: translate(-0.1px,0.2px) rotate(-0.3deg); } }
.thinking-figure { animation: thinking-wobble 1.6s ease-in-out infinite; transform-origin: 20px 30px; }
@keyframes thinking-head-bob { 0%, 100% { transform: translate(0,0) rotate(0deg); } 40% { transform: translate(0.4px,-0.3px) rotate(2deg); } 60% { transform: translate(-0.3px,0.2px) rotate(-1.5deg); } }
.thinking-figure[data-stage="thinking"] .thinking-head { animation: thinking-head-bob 1.4s ease-in-out infinite; transform-origin: 20px 11px; }
@keyframes thinking-wave { 0%, 100% { transform: rotate(0deg); } 20% { transform: rotate(-12deg); } 60% { transform: rotate(10deg); } }
.thinking-figure[data-stage="ready"] .thinking-prop-ready { transform-origin: 27px 9px; animation: thinking-wave 1.2s ease-in-out infinite; }
@keyframes searching-drift { 0%, 100% { transform: translate(0,0); } 50% { transform: translate(1px,-1px); } }
.thinking-figure[data-stage="searching"] .thinking-prop-searching { animation: searching-drift 1.2s ease-in-out infinite; }
@keyframes reading-shake { 0%, 100% { transform: translate(0,0); } 50% { transform: translate(0.3px,0); } }
.thinking-figure[data-stage="reading"] .thinking-prop-reading { animation: reading-shake 0.6s ease-in-out infinite; }
@keyframes thinking-dots-cycle { 0%, 20% { content: ''; } 40% { content: '·'; } 60% { content: '··'; } 80%, 100% { content: '···'; } }
.thinking-dots::after { content: ''; display: inline-block; width: 1.5em; text-align: left; animation: thinking-dots-cycle 1.4s steps(1, end) infinite; }
    </style>
  </div>
</template>
