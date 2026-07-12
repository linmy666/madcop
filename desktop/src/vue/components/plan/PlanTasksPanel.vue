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
  <aside class="tasks-panel">
    <header class="tp__head">
      <div class="tp__head-top">
        <h3 class="tp__title">任务监控</h3>
        <span v-if="plan" class="tp__count" :key="completedCount">{{ completedCount }}<span class="tp__count-slash">/</span>{{ totalSteps }}</span>
        <span v-else class="tp__count tp__count--loading">
          <span class="tp__dot-pulse"></span>
        </span>
      </div>
      <div v-if="plan" class="tp__progress">
        <div
          class="tp__progress-fill"
          :style="{ width: (totalSteps ? (completedCount / totalSteps) * 100 : 0) + '%' }"
        ></div>
      </div>
    </header>

    <!-- Waiting for plan from new message -->
    <div v-if="!plan" class="tp__body tp__body--loading">
      <div class="tp__loading-row">
        <div class="tp__check tp__check--active"><div class="tp__spinner"></div></div>
        <div class="tp__action">正在分析任务，生成执行计划…</div>
      </div>
    </div>

    <div v-else class="tp__body">
      <!-- 进行中 -->
      <Transition name="tp-fade">
        <section v-if="activeStep" class="tp__section" key="active">
          <div class="tp__label">进行中</div>
          <div class="tp__row tp__row--active">
            <div class="tp__check tp__check--active">
              <div class="tp__spinner"></div>
            </div>
            <div class="tp__action">{{ truncate(activeStep.action, 32) }}</div>
          </div>
        </section>
      </Transition>

      <!-- 待办 -->
      <Transition name="tp-fade">
        <section v-if="queuedSteps.length > 0" class="tp__section" key="pending">
          <div class="tp__label">待办</div>
          <div
            v-for="step in queuedSteps"
            :key="'p'+step.step"
            class="tp__row tp__row-enter"
          >
            <div class="tp__check tp__check--empty"></div>
            <div class="tp__action">{{ truncate(step.action, 32) }}</div>
          </div>
        </section>
      </Transition>

      <!-- 已完成 -->
      <Transition name="tp-fade">
        <section v-if="completedSteps.length > 0" class="tp__section" key="done">
          <div class="tp__label">已完成</div>
          <div
            v-for="step in completedSteps"
            :key="'c'+step.step"
            class="tp__row tp__row--done tp__row-enter"
          >
            <div class="tp__check tp__check--done tp__check-pop">
              <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
            </div>
            <div class="tp__action">{{ truncate(step.action, 32) }}</div>
          </div>
        </section>
      </Transition>

      <!-- 失败 -->
      <Transition name="tp-fade">
        <section v-if="failedSteps.length > 0" class="tp__section tp__section--failed" key="fail">
          <div class="tp__label">失败</div>
          <div
            v-for="step in failedSteps"
            :key="'f'+step.step"
            class="tp__row tp__row-enter"
          >
            <div class="tp__check tp__check--fail tp__check-pop">
              <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </div>
            <div class="tp__action">{{ truncate(step.action, 32) }}</div>
          </div>
        </section>
      </Transition>

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

/* ── Header ── */
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
  transition: opacity 0.15s;
}
.tp__count-slash {
  color: var(--color-border, #d0d0d0);
  margin: 0 1px;
}

/* ── Progress bar ── */
.tp__progress {
  height: 3px;
  background: var(--color-border, #e8e8ec);
  border-radius: 999px;
  overflow: hidden;
}
.tp__progress-fill {
  height: 100%;
  background: linear-gradient(90deg, rgb(99, 91, 255), rgb(139, 134, 255));
  border-radius: 999px;
  transition: width 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
  position: relative;
}
/* Progress shimmer */
.tp__progress-fill::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent 30%, rgba(255,255,255,0.3) 50%, transparent 70%);
  animation: tp-shimmer 2s ease-in-out infinite;
}
@keyframes tp-shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(200%); }
}

/* ── Body ── */
.tp__body {
  max-height: 280px;
  overflow-y: auto;
  padding: 4px 0 12px 0;
}

/* ── Section ── */
.tp__section {
  padding: 8px 0;
}
.tp__section--failed {
  background: rgba(220, 38, 38, 0.02);
}

/* ── Label ── */
.tp__label {
  padding: 4px 16px 4px 16px;
  font-size: 10px;
  font-weight: 600;
  color: var(--color-text-tertiary, #888);
  text-transform: uppercase;
  letter-spacing: 0.8px;
}

/* ── Row ── */
.tp__row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 16px;
  font-size: 13px;
}

/* Row entrance: slide down + fade */
.tp__row-enter {
  animation: tp-row-in 0.25s ease-out both;
}
@keyframes tp-row-in {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.tp__row--active {
  background: rgba(99, 91, 255, 0.04);
}
.tp__row--done .tp__action {
  color: var(--color-text-tertiary, #888);
}

/* ── Active row pulse ── */
.tp__row--active {
  animation: tp-active-pulse 2s ease-in-out infinite;
}
@keyframes tp-active-pulse {
  0%, 100% { background: rgba(99, 91, 255, 0.04); }
  50% { background: rgba(99, 91, 255, 0.08); }
}

/* ── Check icons ── */
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

/* Check pop animation */
.tp__check-pop {
  animation: tp-check-pop 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
@keyframes tp-check-pop {
  0% {
    transform: scale(0);
    opacity: 0;
  }
  60% {
    transform: scale(1.15);
  }
  100% {
    transform: scale(1);
    opacity: 1;
  }
}

/* ── Action text ── */
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

/* ── Active spinner ── */
.tp__spinner {
  width: 10px;
  height: 10px;
  border: 2px solid rgba(99, 91, 255, 0.25);
  border-top-color: rgb(99, 91, 255);
  border-radius: 50%;
  animation: tp-spin 0.5s cubic-bezier(0.4, 0.0, 0.6, 1) infinite;
}
@keyframes tp-spin {
  to { transform: rotate(360deg); }
}

/* ── Goal ── */
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

/* ── Section fade transitions ── */
.tp-fade-enter-active {
  animation: tp-section-in 0.25s ease-out;
}
.tp-fade-leave-active {
  animation: tp-section-out 0.15s ease-in;
}
@keyframes tp-section-in {
  from { opacity: 0; max-height: 0; }
  to { opacity: 1; max-height: 200px; }
}
@keyframes tp-section-out {
  from { opacity: 1; max-height: 200px; }
  to { opacity: 0; max-height: 0; padding: 0; }
}

/* ── Loading / null-plan state ── */
.tp__body--loading {
  display: flex;
  align-items: center;
  padding: 20px 0;
}
.tp__loading-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 16px;
  font-size: 13px;
  width: 100%;
}
.tp__loading-row .tp__action {
  color: var(--color-text-secondary, #555);
}
.tp__count--loading {
  display: flex;
  align-items: center;
  justify-content: center;
}
.tp__dot-pulse {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgb(99, 91, 255);
  animation: tp-dot-bounce 1.2s ease-in-out infinite;
}
@keyframes tp-dot-bounce {
  0%, 80%, 100% { transform: scale(0.5); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}
</style>