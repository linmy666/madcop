<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  reasoningContent?: string | null
  hasText?: boolean
  activeToolName?: string | null
  /** v3.10 — Grok-Build-style independent thought blocks. */
  thoughtBlocks?: { id: string; text: string; done: boolean }[] | null
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

// UED-FIX: event-driven phase, not elapsed-time-based. The old
// 2.5s/3s/∞ timer guesses made the mascot animate 'generating' during
// a 10s tool call and 'reasoning' during pure waiting. Phases now map
// 1:1 to real SSE signals:
//   reasoning  ← unfinished thought block
//   generating ← a tool is executing OR plan steps running
//   analyzing  ← busy with neither (pre-first-token wait)
const currentPhase = computed<'analyzing' | 'reasoning' | 'generating'>(() => {
  if (isToolPhase.value || isPlanPhase.value) return 'generating'
  const blocks = props.thoughtBlocks || []
  if (blocks.some((b: any) => !b.done)) return 'reasoning'
  if ((props.reasoningContent || '').trim()) return 'reasoning'
  return 'analyzing'
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
<template>
  <div v-if="isStreaming" class="thinking-hint" data-testid="thinking-hint">
    <span class="thinking-hint__spinner" aria-hidden="true"></span>
    <span class="thinking-hint__text">{{ statusLabel }}</span>
    <span v-if="elapsedText" class="thinking-hint__elapsed">{{ elapsedText }}</span>
  </div>
</template>

<style scoped>
.thinking-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0 2px;
  font-size: 11px;
  color: var(--color-text-tertiary, #999);
  /* Deliberately minimal: the interleaved tool-line timeline is the
     primary streaming experience. This hint just confirms "still working"
     between tool calls / during long reasoning gaps. */
}
.thinking-hint__spinner {
  width: 10px;
  height: 10px;
  border: 1.5px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: thinking-hint-spin 0.9s linear infinite;
  flex-shrink: 0;
}
.thinking-hint__text {
  font-weight: 400;
}
.thinking-hint__elapsed {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
  opacity: 0.6;
}
@keyframes thinking-hint-spin {
  to { transform: rotate(360deg); }
}
@media (prefers-reduced-motion: reduce) {
  .thinking-hint__spinner { animation: none; border-top-color: currentColor; }
}
</style>
