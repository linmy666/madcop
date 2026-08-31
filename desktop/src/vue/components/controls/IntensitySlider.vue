<script setup lang="ts">
import { useTranslation } from '../../i18n'
const t = useTranslation()
/**
 * IntensitySlider — 思考深度选择器.
 *
 * One continuous 31-notch slider that selects the model × reasoning-effort
 * combination in a single gesture. The track is split proportionally
 * across every (model × effort) combo of the active provider; the current
 * position maps back to modelId + effortLevel in the session runtime
 * store. Six named stages give the knob a sense of escalation:
 *
 *   极速 (00) · 快速 (06) · 标准 (12) · 深入 (18) · 深度 (24) · 极致 (30)
 *
 * The plain ModelSelector stays next to it for users who want the flat
 * list — this control is the fast path, not a replacement.
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSessionRuntimeStore } from '../../stores/sessionRuntimeStore'
import { useSettingsStore } from '../../stores/settingsStore'

const props = defineProps<{
  selectionKey: string
  selectedModel?: string
  compact?: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:selectedModel': [model: string]
}>()

const runtimeStore = useSessionRuntimeStore()
const settingsStore = useSettingsStore()

const NOTCHES = 30 // track spans 0..30

const STAGES = [
  { label: '极速', hint: '直出答案，最快响应' },
  { label: '快速', hint: '少量思考，低延迟' },
  { label: '标准', hint: '日常工作档' },
  { label: '深入', hint: '复杂问题，多步推理' },
  { label: '深度', hint: '长链路推理，充分验证' },
  { label: '极致', hint: '全力推理，不计耗时' },
] as const

const EFFORTS = [
  { value: 'auto', label: '自动' },
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
  { value: 'max', label: '极高' },
] as const

// ── Combo space: active provider's models × efforts ──────────────────
const providerModels = computed<string[]>(() => {
  const active = settingsStore.activeProviderName
  const list = (settingsStore.availableModels || []).filter(
    (m: any) => !active || m.providerId === active,
  )
  const names = list.map((m: any) => m.name).filter(Boolean)
  if (names.length) return names
  // Provider model list not loaded yet — fall back to the current pick
  // (or a single placeholder) so the slider still spans the effort axis
  // from 实习生, instead of collapsing to the rightmost notch.
  // Placeholder carries an impossible id (leading space) so it can
  // never be sent to the LLM as a model name ('unknown model 当前模型').
  return [props.selectedModel || ' __placeholder__']
})

interface Combo { model: string; effort: string; effortLabel: string }

const combos = computed<Combo[]>(() =>
  providerModels.value.flatMap((model) =>
    EFFORTS.map((e) => ({ model, effort: e.value, effortLabel: e.label })),
  ),
)

const currentEffort = computed(
  () => runtimeStore.selections[props.selectionKey]?.effortLevel ?? 'auto',
)

// Index of the active combo; -1 when the current model isn't in the
// provider list (keep effort axis, snap model to the nearest valid one).
const currentIndex = computed(() => {
  const list = combos.value
  const eff = currentEffort.value
  const exact = list.findIndex((c) => c.model === props.selectedModel && c.effort === eff)
  if (exact !== -1) return exact
  const byEffort = list.findIndex((c) => c.effort === eff)
  if (byEffort !== -1) return byEffort
  return 0
})

// position (0..30) ↔ combo index, proportional like the six-stage table:
// with 6 combos the boundaries land exactly on 00/06/12/18/24/30.
function posForIndex(i: number, total: number): number {
  if (total <= 1) return 30
  return Math.round((i / (total - 1)) * NOTCHES)
}
function indexForPos(p: number, total: number): number {
  if (total <= 1) return 0
  return Math.min(total - 1, Math.max(0, Math.round((p / NOTCHES) * (total - 1))))
}

const position = computed(() =>
  posForIndex(currentIndex.value, combos.value.length),
)

const stage = computed(() => {
  const s = Math.round(position.value / (NOTCHES / (STAGES.length - 1)))
  const _s = STAGES[Math.min(STAGES.length - 1, Math.max(0, s))]
  return _stageT(_s)
})

const activeCombo = computed(() =>
  combos.value[currentIndex.value] ?? { model: props.selectedModel || '—', effort: currentEffort.value, effortLabel: '自动' },
)

// ── Commit ────────────────────────────────────────────────────────────
function commitPosition(p: number) {
  const idx = indexForPos(p, combos.value.length)
  const combo = combos.value[idx]
  if (!combo) return
  const isPlaceholder = combo.model.startsWith(' ')
  const cur = runtimeStore.selections[props.selectionKey]
  runtimeStore.setSelection(props.selectionKey, {
    providerId: cur?.providerId ?? settingsStore.activeProviderName ?? 'official',
    // Placeholder combo: adjust effort only — never write the fake
    // id into modelId or emit it upward.
    modelId: isPlaceholder ? (cur?.modelId ?? '') : combo.model,
    effortLevel: combo.effort,
    agentMode: cur?.agentMode,
    workDir: cur?.workDir ?? null,
  })
  if (!isPlaceholder && combo.model !== props.selectedModel) {
    emit('update:selectedModel', combo.model)
  }
}

// ── Popover + drag interaction ───────────────────────────────────────
const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)
const trackRef = ref<HTMLElement | null>(null)
const dragPos = ref<number | null>(null) // live notch while dragging

const displayPos = computed(() => dragPos.value ?? position.value)
const displayStage = computed(() => {
  const s = Math.round(displayPos.value / (NOTCHES / (STAGES.length - 1)))
  const _s = STAGES[Math.min(STAGES.length - 1, Math.max(0, s))]
  return _stageT(_s)
})

function toggle() {
  if (!props.disabled) open.value = !open.value
}

function notchFromEvent(e: PointerEvent): number | null {
  const el = trackRef.value
  if (!el) return null
  const rect = el.getBoundingClientRect()
  const ratio = (e.clientX - rect.left) / rect.width
  return Math.min(NOTCHES, Math.max(0, Math.round(ratio * NOTCHES)))
}

let dragging = false

function onTrackPointerDown(e: PointerEvent) {
  if (props.disabled) return
  dragging = true
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  const n = notchFromEvent(e)
  if (n !== null) dragPos.value = n
}

function onTrackPointerMove(e: PointerEvent) {
  if (!dragging || props.disabled) return
  const n = notchFromEvent(e)
  if (n !== null) dragPos.value = n
}

function onTrackPointerUp() {
  if (!dragging) return
  dragging = false
  if (dragPos.value !== null) commitPosition(dragPos.value)
  dragPos.value = null
}

function jumpToStage(stageIdx: number) {
  if (props.disabled) return
  commitPosition(stageIdx * (NOTCHES / (STAGES.length - 1)))
}

function onKeydown(e: KeyboardEvent) {
  if (props.disabled || !open.value) return
  const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
  if (step) {
    e.preventDefault()
    commitPosition(Math.min(NOTCHES, Math.max(0, displayPos.value + step)))
  } else if (e.key === 'Home') {
    e.preventDefault()
    commitPosition(0)
  } else if (e.key === 'End') {
    e.preventDefault()
    commitPosition(NOTCHES)
  }
}

function onClickOutside(e: MouseEvent) {
  if (open.value && rootRef.value && !rootRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

onMounted(() => {
  document.addEventListener('mousedown', onClickOutside)
  document.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  document.removeEventListener('mousedown', onClickOutside)
  document.removeEventListener('keydown', onKeydown)
})

// Thin-tick marks: every notch gets a tick; stage-boundary notches
// (multiples of 30/5) are emphasized.
const stageNotchStep = NOTCHES / (STAGES.length - 1)
function isStageNotch(n: number): boolean {
  return n % stageNotchStep === 0
}
</script>

<template>
  <div ref="rootRef" class="relative">
    <!-- Trigger -->
    <button
      @click.stop="toggle"
      :disabled="disabled"
      :aria-label="t('intensity.title', '思考深度') + '：' + stage.label"
      :title="`${stage.label} · ${activeCombo.effortLabel}推理`"
      class="intensity-slider__trigger"
      :class="{ 'intensity-slider__trigger--compact': compact }"
      data-testid="intensity-slider-trigger"
    >
      <svg width="12" height="12" viewBox="0 0 16 16" fill="none" class="intensity-slider__icon">
        <path d="M2.5 12.5v-2M6 12.5v-4.5M9.5 12.5v-7M13 12.5v-9.5"
          stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
      </svg>
      <span v-if="!compact" class="intensity-slider__label">
        {{ stage.label }}
      </span>
      <svg width="10" height="10" viewBox="0 0 12 12" fill="none" class="opacity-40">
        <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.5"
          stroke-linecap="round" />
      </svg>
    </button>

    <!-- Popover -->
    <Transition name="mode-drop">
      <div
        v-if="open"
        class="intensity-slider__popover"
        data-testid="intensity-slider-popover"
      >
        <!-- Header: stage + hint -->
        <div class="intensity-slider__head">
          <div class="intensity-slider__stage-row">
            <span class="intensity-slider__stage-name">{{ displayStage.label }}</span>
            <span class="intensity-slider__combo">
              {{ activeCombo.model }} · {{ activeCombo.effortLabel }}推理
            </span>
          </div>
          <span class="intensity-slider__hint">{{ displayStage.hint }}</span>
        </div>

        <!-- Signal meter: pure SVG, fills with the stage -->
        <div class="intensity-slider__meter" aria-hidden="true">
          <svg width="150" height="20" viewBox="0 0 150 20" fill="none">
            <path
              v-for="i in 6" :key="i"
              :d="`M${(i - 1) * 25 + 12} ${20 - (i * 2.6)}v${i * 2.6}`"
              stroke="currentColor"
              :stroke-width="2.5"
              stroke-linecap="round"
              :class="i - 1 <= Math.round(displayPos / stageNotchStep) ? 'intensity-slider__bar--on' : 'intensity-slider__bar'"
            />
          </svg>
        </div>

        <!-- The 31-notch track -->
        <div
          ref="trackRef"
          class="intensity-slider__track"
          :class="{ 'intensity-slider__track--disabled': disabled }"
          data-testid="intensity-slider-track"
          @pointerdown="onTrackPointerDown"
          @pointermove="onTrackPointerMove"
          @pointerup="onTrackPointerUp"
          @pointercancel="onTrackPointerUp"
        >
          <div class="intensity-slider__rail" />
          <span
            v-for="n in NOTCHES + 1" :key="n"
            class="intensity-slider__tick"
            :class="{
              'intensity-slider__tick--stage': isStageNotch(n - 1),
              'intensity-slider__tick--passed': n - 1 <= displayPos,
            }"
            :style="{ left: ((n - 1) / NOTCHES) * 100 + '%' }"
          />
          <div
            class="intensity-slider__thumb"
            :style="{ left: (displayPos / NOTCHES) * 100 + '%' }"
            data-testid="intensity-slider-thumb"
          />
        </div>

        <!-- Stage ruler -->
        <div class="intensity-slider__ruler">
          <button
            v-for="(s, i) in STAGES" :key="s.label"
            class="intensity-slider__ruler-label"
            :class="{ 'intensity-slider__ruler-label--active': i === Math.round(displayPos / stageNotchStep) }"
            @click="jumpToStage(i)"
          >
            {{ s.label }}
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.intensity-slider__trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 120ms;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
}

.intensity-slider__trigger:hover {
  background: var(--color-surface-hover);
}

.intensity-slider__trigger:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.intensity-slider__trigger--compact {
  padding: 6px 8px;
  gap: 4px;
}

.intensity-slider__icon {
  flex-shrink: 0;
}

.intensity-slider__label {
  white-space: nowrap;
}

.intensity-slider__popover {
  position: absolute;
  bottom: 100%;
  left: 0;
  margin-bottom: 8px;
  z-index: 50;
  width: 300px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  box-shadow: var(--shadow-dropdown);
  padding: 14px 14px 10px;
  user-select: none;
}

.intensity-slider__head {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 10px;
}

.intensity-slider__stage-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.intensity-slider__stage-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.intensity-slider__combo {
  font-size: 11px;
  color: var(--color-text-tertiary);
  font-family: var(--font-mono, ui-monospace, monospace);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.intensity-slider__hint {
  font-size: 11px;
  color: var(--color-text-tertiary);
}

.intensity-slider__meter {
  color: var(--color-text-tertiary);
  margin-bottom: 2px;
}

.intensity-slider__bar,
.intensity-slider__bar--on {
  transition: color 150ms;
}

.intensity-slider__bar--on {
  color: var(--color-primary);
}

.intensity-slider__track {
  position: relative;
  height: 26px;
  cursor: pointer;
  touch-action: none;
}

.intensity-slider__track--disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.intensity-slider__rail {
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  height: 2px;
  transform: translateY(-50%);
  background: var(--color-border);
  border-radius: 1px;
}

.intensity-slider__tick {
  position: absolute;
  top: 50%;
  width: 1px;
  height: 5px;
  transform: translate(-50%, -50%);
  background: var(--color-border);
  pointer-events: none;
}

.intensity-slider__tick--stage {
  height: 11px;
  width: 1.5px;
}

.intensity-slider__tick--passed {
  background: var(--color-primary);
}

.intensity-slider__thumb {
  position: absolute;
  top: 50%;
  width: 14px;
  height: 14px;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: var(--color-surface);
  border: 2px solid var(--color-primary);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
  pointer-events: none;
  transition: left 80ms ease-out;
}

.intensity-slider__track:active .intensity-slider__thumb {
  transform: translate(-50%, -50%) scale(1.15);
  transition: transform 100ms;
}

.intensity-slider__ruler {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
}

.intensity-slider__ruler-label {
  background: none;
  border: none;
  padding: 2px 0;
  font-size: 10px;
  color: var(--color-text-tertiary);
  cursor: pointer;
  transition: color 100ms;
}

.intensity-slider__ruler-label:hover {
  color: var(--color-text-secondary);
}

.intensity-slider__ruler-label--active {
  color: var(--color-primary);
  font-weight: 600;
}

.mode-drop-enter-active,
.mode-drop-leave-active {
  transition: all 120ms;
}

.mode-drop-enter-from,
.mode-drop-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
</style>
