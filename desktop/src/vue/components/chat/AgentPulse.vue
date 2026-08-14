<script setup lang="ts">
/**
 * AgentPulse — live phase indicator that visualizes the agent loop.
 *
 * Shows what the agent is doing RIGHT NOW, with an animated pulse:
 * - "思考中..." when reasoning events arrive
 * - "调用 write_file..." when a tool is executing
 * - "输出中..." when answer text is streaming
 * - Hidden when idle
 *
 * This is the Codex/Claude Code pattern: between text outputs, you see
 * a pulsing indicator that shows the agent is working (not frozen).
 */
import { computed } from 'vue'
import { useLiveState } from '../../composables/useLiveState'

const live = useLiveState()

const phase = computed<{ label: string; icon: string } | null>(() => {
  if (!live.isStreaming) return null

  // Check what's happening right now based on live state
  const runningTool = live.tools.find(t => !t.done)
  if (runningTool) {
    return { label: `调用 ${runningTool.name}...`, icon: 'tool' }
  }

  const thinking = live.thoughts.some(t => !t.done)
  if (thinking) {
    return { label: '思考中...', icon: 'think' }
  }

  if (live.answerLength > 0) {
    return { label: '输出中...', icon: 'write' }
  }

  // Streaming but nothing arrived yet
  return { label: '处理中...', icon: 'wait' }
})
</script>

<template>
  <div v-if="phase" class="agent-pulse">
    <span class="agent-pulse__dot" :class="`agent-pulse__dot--${phase.icon}`"></span>
    <span class="agent-pulse__label">{{ phase.label }}</span>
  </div>
</template>

<style scoped>
.agent-pulse {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  color: var(--color-text-tertiary, #888);
  background: rgba(128, 128, 128, 0.06);
  margin: 4px 0;
  animation: pulse-fade 2s ease-in-out infinite;
}
.agent-pulse__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.agent-pulse__dot--think {
  background: #6b8afd;
  animation: pulse-dot 1.2s ease-in-out infinite;
}
.agent-pulse__dot--tool {
  background: #e8a838;
  animation: pulse-dot 1.2s ease-in-out infinite 0.2s;
}
.agent-pulse__dot--write {
  background: #3ecf8e;
  animation: pulse-dot 1.2s ease-in-out infinite 0.4s;
}
.agent-pulse__dot--wait {
  background: #aaa;
  animation: pulse-dot 1.5s ease-in-out infinite;
}
.agent-pulse__label {
  font-variant-numeric: tabular-nums;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 0.3; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}
@keyframes pulse-fade {
  0%, 100% { opacity: 0.7; }
  50% { opacity: 1; }
}
</style>
