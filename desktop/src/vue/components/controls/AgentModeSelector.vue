<script setup lang="ts">
import { useTranslation } from '../../i18n'
const t = useTranslation()
/**
 * AgentModeSelector — unified execution-mode picker.
 *
 * Replaces the old EffortSelector + fake "R Act 推理" button.
 * Modes that control BOTH the workflow AND reasoning effort:
 *
 *   快速 (quick)    — direct LLM call, effort=low
 *   标准 (standard) — ReAct loop, effort=medium  (DEFAULT)
 *   深度 (deep)     — multi-agent (plan→code→review), effort=high
 *   创作 (create)   — source-first long-form: search→fetch→outline→write
 *
 * Also supports "auto" — lets the backend task router decide.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSessionRuntimeStore } from '../../stores/sessionRuntimeStore'

const props = defineProps<{
  selectionKey: string
  compact?: boolean
  disabled?: boolean
}>()

const runtimeStore = useSessionRuntimeStore()

// ── Mode definitions ──────────────────────────────────────────────────

interface ModeOption {
  value: string
  label: string
  shortLabel: string
  desc: string
  icon: string
  workflow: string
  effort: string
}

const MODES_RAW: ModeOption[] = [
  {
    value: 'chat',
    label: '对话',
    shortLabel: '对话',
    desc: '智能问答，自动判断是否需要搜索/工具',
    icon: 'chat_bubble',
    workflow: 'chat',
    effort: 'auto',
  },
  {
    value: 'task',
    label: '任务',
    shortLabel: '任务',
    desc: '实验性：MEA循环(Manager→Executor→Auditor)，适合长程任务，速度较慢',
    icon: 'assignment',
    workflow: 'mea_loop',
    effort: 'high',
  },
  {
    value: 'create',
    label: '创作',
    shortLabel: '创作',
    desc: '联网检索 → 抓取 → 大纲 → 带引用正文',
    icon: 'edit_note',
    workflow: 'create',
    effort: 'high',
  },
]

// ── Current selection ─────────────────────────────────────────────────

const current = computed<string>(() => {
  return runtimeStore.selections[props.selectionKey]?.agentMode ?? 'chat'
})

const currentMode = computed(() => {
  const m = MODES_RAW.find(m => m.value === current.value) ?? MODES_RAW[2]
  return { ...m, label: t('agentMode.' + m.value + '.label', m.label), shortLabel: t('agentMode.' + m.value + '.shortLabel', m.shortLabel || m.label), desc: t('agentMode.' + m.value + '.desc', m.desc) }
})

// ── Dropdown state ────────────────────────────────────────────────────

const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)

function toggle() {
  if (!props.disabled) open.value = !open.value
}

function select(mode: ModeOption) {
  if (props.disabled) return
  const cur = runtimeStore.selections[props.selectionKey]
  runtimeStore.setSelection(props.selectionKey, {
    providerId: cur?.providerId ?? 'official',
    modelId: cur?.modelId ?? '',
    effortLevel: mode.effort,
    agentMode: mode.value,
    workDir: cur?.workDir ?? null,
  })
  open.value = false
}

function onClickOutside(e: MouseEvent) {
  if (open.value && rootRef.value && !rootRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('mousedown', onClickOutside))
onUnmounted(() => document.removeEventListener('mousedown', onClickOutside))
</script>

<template>
  <div ref="rootRef" class="relative">
    <!-- Trigger button -->
    <button
      @click.stop="toggle"
      :disabled="disabled"
      :aria-label="t('agentMode.aria', 'mode') + ': ' + currentMode.label"
      class="agent-mode-selector__trigger"
      :class="{
        'agent-mode-selector__trigger--compact': compact,
        'agent-mode-selector__trigger--deep': current === 'deep',
        'agent-mode-selector__trigger--create': current === 'create',
      }"
    >
      <span class="material-symbols-outlined agent-mode-selector__icon">
        {{ currentMode.icon }}
      </span>
      <span v-if="!compact" class="agent-mode-selector__label">
        {{ currentMode.label }}
      </span>
      <svg width="10" height="10" viewBox="0 0 12 12" fill="none" class="opacity-40">
        <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.5"
          stroke-linecap="round" />
      </svg>
    </button>

    <!-- Dropdown -->
    <Transition name="mode-drop">
      <div
        v-if="open"
        class="agent-mode-selector__dropdown"
        :class="{ 'agent-mode-selector__dropdown--compact': compact }"
      >
        <button
          v-for="mode in MODES"
          :key="mode.value"
          @click.stop="select(mode)"
          class="agent-mode-selector__option"
          :class="{ 'agent-mode-selector__option--active': mode.value === current }"
        >
          <span class="material-symbols-outlined agent-mode-selector__option-icon">
            {{ mode.icon }}
          </span>
          <div class="agent-mode-selector__option-text">
            <span class="agent-mode-selector__option-label">{{ mode.label }}</span>
            <span class="agent-mode-selector__option-desc">{{ mode.desc }}</span>
          </div>
          <span
            v-if="mode.value === current"
            class="material-symbols-outlined agent-mode-selector__check"
          >
            check
          </span>
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.agent-mode-selector__trigger {
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

.agent-mode-selector__trigger:hover {
  background: var(--color-surface-hover);
}

.agent-mode-selector__trigger:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.agent-mode-selector__trigger--compact {
  padding: 6px 8px;
  gap: 4px;
}

.agent-mode-selector__trigger--deep {
  background: var(--color-tertiary-container);
  color: var(--color-on-tertiary-container);
  border-color: var(--color-tertiary);
}

.agent-mode-selector__trigger--create {
  background: var(--color-primary-container);
  color: var(--color-on-primary-container);
  border-color: var(--color-primary);
}

.agent-mode-selector__icon {
  font-size: 14px;
}

.agent-mode-selector__label {
  white-space: nowrap;
}

.agent-mode-selector__dropdown {
  position: absolute;
  bottom: 100%;
  left: 0;
  margin-bottom: 8px;
  z-index: 50;
  min-width: 280px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  box-shadow: var(--shadow-dropdown);
  padding: 4px;
}

.agent-mode-selector__dropdown--compact {
  min-width: 240px;
}

.agent-mode-selector__option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  text-align: left;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 100ms;
  background: transparent;
  border: none;
}

.agent-mode-selector__option:hover {
  background: var(--color-surface-hover);
}

.agent-mode-selector__option--active {
  background: var(--color-primary-container);
}

.agent-mode-selector__option--active:hover {
  background: var(--color-primary-container);
  filter: brightness(0.97);
}

.agent-mode-selector__option-icon {
  font-size: 18px;
  margin-top: 1px;
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.agent-mode-selector__option--active .agent-mode-selector__option-icon {
  color: var(--color-primary);
}

.agent-mode-selector__option-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.agent-mode-selector__option-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.agent-mode-selector__option-desc {
  font-size: 11px;
  color: var(--color-text-tertiary);
  line-height: 1.4;
}

.agent-mode-selector__check {
  font-size: 16px;
  color: var(--color-primary);
  flex-shrink: 0;
  margin-top: 1px;
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
