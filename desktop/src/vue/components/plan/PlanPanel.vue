<script setup lang="ts">
import { computed } from 'vue'

export interface PlanStepData {
  step: number
  action: string
  tool: string | null
  input_hint: string
  expected_result: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'skipped'
  result: string | null
  error: string | null
  retry_count: number
}

export interface PlanData {
  goal: string
  steps: PlanStepData[]
  current_step: number
  total_steps: number
  completed_steps: number
  failed_steps: number
  status: string
}

const props = defineProps<{
  plan: PlanData | null
}>()

const progressPct = computed(() => {
  if (!props.plan || props.plan.total_steps === 0) return 0
  return Math.round((props.plan.completed_steps / props.plan.total_steps) * 100)
})

const statusLabel = computed(() => {
  if (!props.plan) return ''
  switch (props.plan.status) {
    case 'pending': return '等待执行'
    case 'running': return `执行中 (${props.plan.completed_steps}/${props.plan.total_steps})`
    case 'completed': return '全部完成 ✓'
    case 'failed': return `失败 (${props.plan.failed_steps} 步出错)`
    default: return props.plan.status
  }
})

function statusIcon(status: string): string {
  switch (status) {
    case 'completed': return '✓'
    case 'failed': return '✗'
    case 'in_progress': return '◉'
    case 'pending': return '○'
    case 'skipped': return '—'
    default: return '○'
  }
}

function statusClass(status: string): string {
  switch (status) {
    case 'completed': return 'step--ok'
    case 'failed': return 'step--fail'
    case 'in_progress': return 'step--active'
    default: return 'step--idle'
  }
}

function toolBadge(tool: string | null): string {
  if (!tool) return '推理'
  const labels: Record<string, string> = {
    web_search: '搜索', web_fetch: '抓取',
    read_file: '读文件', write_file: '写文件', edit_file: '改文件',
    computer_use: '电脑', clarify: '询问', weather: '天气',
  }
  return labels[tool] || tool
}
</script>

<template>
  <div v-if="plan" class="plan-panel">
    <!-- Header -->
    <div class="plan-header">
      <div class="plan-goal">{{ plan.goal }}</div>
      <div class="plan-progress">
        <div class="plan-progress-bar">
          <div class="plan-progress-fill" :style="{ width: progressPct + '%' }"></div>
        </div>
        <span class="plan-status-label">{{ statusLabel }}</span>
      </div>
    </div>

    <!-- Steps -->
    <div class="plan-steps">
      <div
        v-for="step in plan.steps"
        :key="step.step"
        :class="['plan-step', statusClass(step.status)]"
      >
        <div class="plan-step__icon">{{ statusIcon(step.status) }}</div>
        <div class="plan-step__body">
          <div class="plan-step__action">
            <span class="plan-step__num">#{{ step.step }}</span>
            {{ step.action }}
            <span :class="['tool-badge', step.tool ? 'tool-badge--has-tool' : '']">
              {{ toolBadge(step.tool) }}
            </span>
          </div>
          <div v-if="step.input_hint" class="plan-step__hint">{{ step.input_hint }}</div>
          <div v-if="step.result && step.status === 'completed'" class="plan-step__result">
            {{ step.result.slice(0, 200) }}<span v-if="step.result.length > 200">…</span>
          </div>
          <div v-if="step.error" class="plan-step__error">✗ {{ step.error }}</div>
        </div>
        <div v-if="step.status === 'in_progress'" class="plan-step__spinner">
          <div class="spinner-dot"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plan-panel {
  font-size: 13px;
  line-height: 1.5;
  color: var(--color-text-primary, #222);
}

/* ── Header ── */
.plan-header {
  margin-bottom: 16px;
}
.plan-goal {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--color-text-primary, #222);
}
.plan-progress {
  display: flex;
  align-items: center;
  gap: 10px;
}
.plan-progress-bar {
  flex: 1;
  height: 4px;
  background: var(--color-border, #e5e5e5);
  border-radius: 2px;
  overflow: hidden;
}
.plan-progress-fill {
  height: 100%;
  background: var(--color-brand, #333);
  border-radius: 2px;
  transition: width 0.3s ease;
}
.plan-status-label {
  font-size: 11px;
  color: var(--color-text-tertiary, #999);
  white-space: nowrap;
  font-family: var(--font-mono);
}

/* ── Steps ── */
.plan-steps {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.plan-step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid var(--color-border, #eee);
  transition: background 0.15s, border-color 0.15s;
}
.plan-step--idle {
  background: var(--color-surface, #fafafa);
  border-color: var(--color-border, #eee);
  opacity: 0.6;
}
.plan-step--active {
  background: var(--color-surface-container, #f0f0f0);
  border-color: var(--color-brand, #333);
}
.plan-step--ok {
  background: var(--color-surface, #fafafa);
  border-color: var(--color-border, #eee);
}
.plan-step--fail {
  background: rgba(220, 38, 38, 0.04);
  border-color: rgba(220, 38, 38, 0.3);
}

.plan-step__icon {
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
  border-radius: 50%;
  margin-top: 1px;
}
.plan-step--idle .plan-step__icon { color: var(--color-text-tertiary, #999); }
.plan-step--active .plan-step__icon { color: var(--color-brand); }
.plan-step--ok .plan-step__icon { color: var(--color-success); background: color-mix(in srgb, var(--color-success) 8%, transparent); }
.plan-step--fail .plan-step__icon { color: var(--color-error); }

.plan-step__body {
  flex: 1;
  min-width: 0;
}
.plan-step__action {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 2px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.plan-step__num {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-text-tertiary, #999);
}

.tool-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--color-surface-container, #eee);
  color: var(--color-text-tertiary, #888);
  font-family: var(--font-mono);
}
.tool-badge--has-tool {
  background: color-mix(in srgb, var(--color-info) 8%, transparent);
  color: var(--color-info);
}

.plan-step__hint,
.plan-step__result {
  font-size: 12px;
  color: var(--color-text-tertiary, #888);
  margin-top: 2px;
}
.plan-step__result {
  color: var(--color-text-secondary, #555);
}
.plan-step__error {
  font-size: 12px;
  color: var(--color-error);
  margin-top: 2px;
}

.plan-step__spinner {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  padding: 0 4px;
}
.spinner-dot {
  width: 10px;
  height: 10px;
  border: 1.5px solid var(--color-border, #ddd);
  border-top-color: var(--color-brand, #333);
  border-radius: 50%;
  animation: plan-spin 0.6s linear infinite;
}
@keyframes plan-spin {
  to { transform: rotate(360deg); }
}
</style>