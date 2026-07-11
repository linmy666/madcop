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
  [...(props.plan?.steps || [])]
    .reverse()
    .filter((s) => s.status === 'completed')
)
const failedSteps = computed(() =>
  [...(props.plan?.steps || [])]
    .reverse()
    .filter((s) => s.status === 'failed')
)

const totalSteps = computed(() => props.plan?.total_steps || 0)
const completedCount = computed(() => props.plan?.completed_steps || 0)

function truncate(s: string | null, max = 36): string {
  if (!s) return ''
  return s.length > max ? s.slice(0, max) + '…' : s
}
</script>

<template>
  <aside class="tasks-panel" v-if="plan">
    <!-- Header -->
    <header class="tp__head">
      <div class="tp__head-top">
        <h3 class="tp__title">任务监控</h3>
        <span class="tp__count">{{ completedCount }}/{{ totalSteps }}</span>
      </div>
      <!-- Progress -->
      <div class="tp__progress">
        <div
          class="tp__progress-fill"
          :style="{ width: (totalSteps ? (completedCount / totalSteps) * 100 : 0) + '%' }"
        ></div>
      </div>
    </header>

    <div class="tp__body">
      <!-- 进行中 -->
      <section v-if="activeStep" class="tp__section">
        <div class="tp__label">进行中</div>
        <div class="tp__row tp__row--active">
          <div class="tp__check tp__check--active">
            <div class="tp__spinner"></div>
          </div>
          <div class="tp__action">{{ truncate(activeStep.action, 32) }}</div>
        </div>
      </section>

      <!-- 待办 -->
      <section v-if="queuedSteps.length > 0" class="tp__section">
        <div class="tp__label">待办</div>
        <div
          v-for="step in queuedSteps"
          :key="step.step"
          class="tp__row"
        >
          <div class="tp__check tp__check--empty"></div>
          <div class="tp__action">{{ truncate(step.action, 32) }}</div>
        </div>
      </section>

      <!-- 已完成 -->
      <section v-if="completedSteps.length > 0" class="tp__section">
        <div class="tp__label">已完成</div>
        <div
          v-for="step in completedSteps"
          :key="step.step"
          class="tp__row tp__row--done"
        >
          <div class="tp__check tp__check--done">
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </div>
          <div class="tp__action">{{ truncate(step.action, 32) }}</div>
        </div>
      </section>

      <!-- 失败 -->
      <section v-if="failedSteps.length > 0" class="tp__section tp__section--failed">
        <div class="tp__label">失败</div>
        <div
          v-for="step in failedSteps"
          :key="step.step"
          class="tp__row"
        >
          <div class="tp__check tp__check--fail">
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </div>
          <div class="tp__action">{{ truncate(step.action, 32) }}</div>
        </div>
      </section>

      <!-- Goal summary -->
      <section v-if="plan.goal" class="tp__goal-summary">
        <div class="tp__label">目标</div>
        <div class="tp__goal-text">{{ truncate(plan.goal, 100) }}</div>
      </section>
    </div>
  </aside>
</template>

<style scoped>
.tasks-panel {
  width: 100%;
  background: var(--color-surface, #fcfcfd);
  border-bottom: 1px solid var(--color-border, #e8e8ec);
  font-size: 13px;
  color: var(--color-text-primary, #1a1a1f);
  -webkit-font-smoothing: antialiased;
}

.tp__head {
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border, #e8e8ec);
}
.tp__head-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.tp__title {
  font-size: 13px;
  font-weight: 600;
  margin: 0;
  letter-spacing: 0;
  color: var(--color-text-primary, #1a1a1f);
}
.tp__count {
  font-size: 10px;
  color: var(--color-text-tertiary, #888);
  font-family: ui-monospace, 'SF Mono', monospace;
}

.tp__progress {
  height: 3px;
  background: var(--color-border, #e8e8ec);
  border-radius: 999px;
  overflow: hidden;
}
.tp__progress-fill {
  height: 100%;
  background: rgb(99, 91, 255);
  border-radius: 999px;
  transition: width 0.3s ease;
}

.tp__body {
  max-height: 280px;
  overflow-y: auto;
  padding: 4px 0 12px 0;
}

.tp__section {
  padding: 8px 0;
}

.tp__section--failed {
  background: rgba(220, 38, 38, 0.02);
}

.tp__label {
  padding: 4px 16px 4px 16px;
  font-size: 10px;
  font-weight: 600;
  color: var(--color-text-tertiary, #888);
  text-transform: uppercase;
  letter-spacing: 0.8px;
}

.tp__row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 16px;
  font-size: 13px;
}

.tp__row--active {
  background: rgba(99, 91, 255, 0.04);
}

.tp__row--done .tp__action {
  color: var(--color-text-tertiary, #888);
}

.tp__check {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.tp__check--done {
  background: rgb(34, 197, 94);
  color: #fff;
}
.tp__check--fail {
  background: rgb(220, 38, 38);
  color: #fff;
}
.tp__check--active {
  background: rgba(99, 91, 255, 0.12);
}
.tp__check--empty {
  background: transparent;
  border: 1.5px solid #d4d4d8;
}

.tp__action {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--color-text-primary, #1a1a1f);
}

.tp__row--active .tp__action {
  color: rgb(99, 91, 255);
  font-weight: 500;
}

.tp__spinner {
  width: 10px;
  height: 10px;
  border: 2px solid rgba(99, 91, 255, 0.3);
  border-top-color: rgb(99, 91, 255);
  border-radius: 50%;
  animation: tp-spin 0.6s linear infinite;
}
@keyframes tp-spin {
  to { transform: rotate(360deg); }
}

.tp__goal-summary {
  border-top: 1px solid var(--color-border, #e8e8ec);
  margin-top: 4px;
  padding: 10px 0 4px 0;
}
.tp__goal-text {
  padding: 0 16px;
  font-size: 12px;
  color: var(--color-text-secondary, #555);
  line-height: 1.5;
}
</style>