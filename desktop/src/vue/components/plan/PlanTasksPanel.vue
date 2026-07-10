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

const queuedSteps = computed(() =>
  props.plan?.steps.filter((s) => s.status === 'pending') || []
)
const activeStep = computed(() =>
  props.plan?.steps.find((s) => s.status === 'in_progress') || null
)
const completedSteps = computed(() =>
  props.plan?.steps.filter((s) => s.status === 'completed') || []
)
const failedSteps = computed(() =>
  props.plan?.steps.filter((s) => s.status === 'failed') || []
)

function truncate(s: string | null, max = 36): string {
  if (!s) return ''
  return s.length > max ? s.slice(0, max) + '…' : s
}
</script>

<template>
  <aside class="plan-tasks-panel">
    <!-- Header -->
    <header class="ptp__head">
      <h3 class="ptp__title">任务监控</h3>
    </header>

    <!-- Sections -->
    <div v-if="plan" class="ptp__body">
      <!-- 进行中 -->
      <section v-if="activeStep" class="ptp__section ptp__section--active">
        <div class="ptp__label">进行中</div>
        <div class="ptp__row ptp__row--active">
          <div class="ptp__check">
            <div class="ptp__spinner"></div>
          </div>
          <div class="ptp__action">{{ truncate(activeStep.action, 30) }}</div>
        </div>
      </section>

      <!-- 待办 -->
      <section v-if="queuedSteps.length > 0" class="ptp__section">
        <div class="ptp__label">待办</div>
        <div
          v-for="step in queuedSteps"
          :key="step.step"
          class="ptp__row ptp__row--queued"
        >
          <div class="ptp__check ptp__check--empty"></div>
          <div class="ptp__action">{{ truncate(step.action, 30) }}</div>
        </div>
      </section>

      <!-- 已完成 -->
      <section v-if="completedSteps.length > 0" class="ptp__section">
        <div class="ptp__label">已完成</div>
        <div
          v-for="step in completedSteps"
          :key="step.step"
          class="ptp__row ptp__row--done"
        >
          <div class="ptp__check">✓</div>
          <div class="ptp__action">{{ truncate(step.action, 30) }}</div>
        </div>
      </section>

      <!-- 失败 -->
      <section v-if="failedSteps.length > 0" class="ptp__section ptp__section--failed">
        <div class="ptp__label">失败</div>
        <div
          v-for="step in failedSteps"
          :key="step.step"
          class="ptp__row ptp__row--fail"
        >
          <div class="ptp__check ptp__check--fail">✗</div>
          <div class="ptp__action">{{ truncate(step.action, 30) }}</div>
        </div>
      </section>

      <!-- Goal summary -->
      <section class="ptp__goal-summary">
        <div class="ptp__goal-label">目标</div>
        <div class="ptp__goal-text">{{ truncate(plan.goal, 60) }}</div>
      </section>
    </div>
  </aside>
</template>

<style scoped>
.plan-tasks-panel {
  width: 100%;
  height: 100%;
  background: var(--color-surface, #fff);
  border-left: 1px solid var(--color-border, #e5e5e5);
  display: flex;
  flex-direction: column;
  font-size: 13px;
  color: var(--color-text-primary, #222);
}

.ptp__head {
  padding: 14px 18px;
  border-bottom: 1px solid var(--color-border, #e5e5e5);
}
.ptp__title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  letter-spacing: 0.2px;
  color: var(--color-text-primary, #222);
}

.ptp__body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0 16px 0;
}

.ptp__section {
  padding: 8px 0;
}
.ptp__section--active {
  background: rgba(37, 99, 235, 0.03);
  border-radius: 0;
}
.ptp__section--failed {
  background: rgba(220, 38, 38, 0.03);
}

.ptp__label {
  padding: 6px 18px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-tertiary, #999);
  text-transform: uppercase;
  letter-spacing: 0.6px;
}

.ptp__row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 18px;
  font-size: 13px;
}

.ptp__check {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #16a34a;
  color: #fff;
  font-size: 9px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.ptp__check--empty {
  background: transparent;
  border: 1.5px solid #d4d4d8;
}
.ptp__check--fail {
  background: #dc2626;
}

.ptp__row--active .ptp__action {
  color: var(--color-text-primary, #222);
  font-weight: 500;
}
.ptp__row--queued .ptp__action {
  color: var(--color-text-tertiary, #999);
}
.ptp__row--done .ptp__action {
  color: var(--color-text-secondary, #555);
}
.ptp__row--fail .ptp__action {
  color: #dc2626;
}

.ptp__action {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ptp__spinner {
  width: 10px;
  height: 10px;
  border: 2px solid var(--color-border, #e5e5e5);
  border-top-color: #2563eb;
  border-radius: 50%;
  animation: ptp-spin 0.6s linear infinite;
}
@keyframes ptp-spin {
  to { transform: rotate(360deg); }
}

.ptp__goal-summary {
  margin-top: 8px;
  padding: 12px 18px;
  border-top: 1px solid var(--color-border, #e5e5e5);
}
.ptp__goal-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-tertiary, #999);
  text-transform: uppercase;
  letter-spacing: 0.6px;
  margin-bottom: 4px;
}
.ptp__goal-text {
  font-size: 12px;
  color: var(--color-text-secondary, #555);
  line-height: 1.4;
}
</style>