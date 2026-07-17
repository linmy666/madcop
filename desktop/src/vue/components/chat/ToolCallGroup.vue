<script setup lang="ts">
// v5.0 — ToolCallGroup (full Vue 3 SFC translation from React components/chat/ToolCallGroup.tsx, 1088 lines)
// - useState → ref() ; useEffect → watch ; useMemo → computed
// - lucide-react icons → <span class="material-symbols-outlined">icon_name</span>
// - createPortal → <teleport to="body">
// - keep ALL Tailwind classes and --color-* CSS variables VERBATIM
// - ALL sub-components rendered inline as template sections with their own ref() state
// - Per-instance state (AgentCallCard expanded/previewOpen) tracked via Record<string, boolean> maps

import {
  ref,
  watch,
  computed,
  type Ref,
} from 'vue'
import { useTranslation } from '../../i18n'
import { SETTINGS_TAB_ID, useTabStore } from '../../stores/tabStore'
import { useUIStore } from '../../stores/uiStore'
import type { AgentTaskNotification } from '../../types/chat'
import ToolCallBlock from './ToolCallBlock.vue'
import MarkdownRenderer from '../shared/MarkdownRenderer.vue'
import Modal from '../shared/Modal.vue'

import {
  type ToolCall,
  type ToolResult,
  type MemoryToolActivity,
  type AgentStatus,
  generateSummary,
  toolCallHasError,
  groupHasErrors,
  isToolCallResolved,
  hasUnresolvedToolCalls,
  getAgentStatus,
  getAgentStatusLabel,
  getAgentStatusClassName,
  extractTextContent,
  formatRecentToolUseSummary,
  getAgentErrorSummary,
  getAgentOutputSummary,
  isAgentLaunchResult,
  isAgentLifecycleResult,
  extractAgentDisplayText,
  formatAgentStructuredResult,
  isMemoryToolCall,
  getMemoryToolActivity,
  memoryFileLabel,
} from './toolCallGroupUtils'

export interface ToolCallGroupProps {
  toolCalls: ToolCall[]
  resultMap: Map<string, ToolResult>
  childToolCallsByParent: Map<string, ToolCall[]>
  agentTaskNotifications: Record<string, AgentTaskNotification>
  isStreaming?: boolean
}

const props = withDefaults(defineProps<ToolCallGroupProps>(), {
  isStreaming: false,
  resultMap: () => new Map(),  // fallback empty map if undefined
  childToolCallsByParent: () => new Map(),
  agentTaskNotifications: () => ({}),
})

const t = useTranslation()


// ─── Open-memory-settings helper ────────────────────────────────
function openMemorySettings(path?: string) {
  const ui = useUIStore()
  if (path) ui.setPendingMemoryPath(path)
  ui.setPendingSettingsTab('memory')
  useTabStore().openTab(SETTINGS_TAB_ID, 'Settings', 'settings')
}

// ─── Top-level computed ────────────────────────────────────────

const memoryActivity = computed(() =>
  getMemoryToolActivity(props.toolCalls, props.resultMap),
)

const memoryToolCalls = computed(() => props.toolCalls.filter(isMemoryToolCall))
const regularToolCalls = computed(() => props.toolCalls.filter((tc) => !isMemoryToolCall(tc)))
const allAgents = computed(() => props.toolCalls.every((tc) => tc.toolName === 'Agent'))
const allRegularAgents = computed(() => regularToolCalls.value.every((tc) => tc.toolName === 'Agent'))

// ─── Sub-component state (refs — top-level to avoid conditional hook calls) ─

// MemoryToolActivityGroup state
const memExpanded = ref(true)
const memDetailsExpanded = ref(false)

watch(
  () => props.isStreaming,
  (is) => {
    if (is) memExpanded.value = true
  },
)

// ToolCallGroupMulti state
const multiExpanded = ref(false)

// AgentToolGroup state
const agentExpanded = ref(true)

watch(
  () => props.isStreaming,
  (is) => {
    if (is) agentExpanded.value = true
  },
)

// AgentCallCard per-instance state (keyed by toolUseId)
const agentCardExpandedMap = ref<Record<string, boolean>>({})
const previewOpenMap = ref<string | null>(null)

function toggleAgentCardExpanded(id: string): void {
  agentCardExpandedMap.value = {
    ...agentCardExpandedMap.value,
    [id]: !agentCardExpandedMap.value[id],
  }
}

function openPreview(id: string): void {
  previewOpenMap.value = id
}

function closePreviewModal(): void {
  previewOpenMap.value = null
}

// ─── AgentToolGroup derived state (for allAgents + regularAgents) ──────────────────────

function computeAgentGroupDerived(
  agentToolCalls: ToolCall[],
  agentNotifications: Record<string, AgentTaskNotification>,
  resultMap: Map<string, ToolResult>,
  childToolCallsByParent: Map<string, ToolCall[]>,
  isStreaming: boolean,
): {
  statuses: Array<{ tc: ToolCall; status: AgentStatus; statusLabel: string; statusClassName: string }>
  isAnyRunning: boolean
  errorPresent: boolean
  allComplete: boolean
  anyStopped: boolean
} {
  const statuses = agentToolCalls.map((tc) => {
    const status = getAgentStatus({
      hasResult: resultMap.has(tc.toolUseId),
      isError: !!resultMap.get(tc.toolUseId)?.isError,
      isLaunchResult: isAgentLaunchResult(resultMap.get(tc.toolUseId)?.content),
      isStreaming: isStreaming && !resultMap.has(tc.toolUseId),
      childCount: (childToolCallsByParent.get(tc.toolUseId) ?? []).length,
      taskStatus: agentNotifications[tc.toolUseId]?.status,
    })
    return {
      tc,
      status,
      statusLabel: getAgentStatusLabel(status, t),
      statusClassName: getAgentStatusClassName(status),
    }
  })

  return {
    statuses,
    isAnyRunning: statuses.some((s) => s.status === 'running' || s.status === 'starting'),
    errorPresent: statuses.some((s) => s.status === 'failed'),
    allComplete: statuses.every((s) => s.status === 'done'),
    anyStopped: statuses.some((s) => s.status === 'stopped'),
  }
}

function getAgentGroupDerivedFor(tcs: ToolCall[]): ReturnType<typeof computeAgentGroupDerived> {
  return computeAgentGroupDerived(
    tcs,
    props.agentTaskNotifications,
    props.resultMap,
    props.childToolCallsByParent,
    !!props.isStreaming,
  )
}

// For the all-agents case (top-level)
const allAgentDerived = computed(() => getAgentGroupDerivedFor(props.toolCalls))

// For the regular-tool-calls case (when regular calls are all agents)
const regularAgentDerived = computed(() => getAgentGroupDerivedFor(regularToolCalls.value))

// ─── ToolCallGroupMulti derived state ──────────────────────────

const multiSummary = computed(() => generateSummary(props.toolCalls, t))
const multiErrorPresent = computed(() =>
  groupHasErrors(props.toolCalls, props.resultMap, props.childToolCallsByParent),
)
const multiHasUnresolved = computed(() =>
  hasUnresolvedToolCalls(props.toolCalls, props.resultMap, props.childToolCallsByParent),
)
const multiIsRunning = computed(() => !!props.isStreaming || multiHasUnresolved.value)
const multiHasNested = computed(() =>
  props.toolCalls.some((tc) => (props.childToolCallsByParent.get(tc.toolUseId)?.length ?? 0) > 0),
)

watch(
  () => [multiHasNested.value, multiIsRunning.value],
  ([hasNested, isRunning]) => {
    if (isRunning || hasNested) multiExpanded.value = true
  },
)

// ─── AgentCallCard per-call derived state ──────────────────────

function agentCardDerived(tc: ToolCall) {
  const result = props.resultMap.get(tc.toolUseId)
  const childToolCalls = props.childToolCallsByParent.get(tc.toolUseId) ?? []
  const isLaunchResult = isAgentLaunchResult(result?.content)
  const recentToolCalls = childToolCalls.slice(-2)
  const status = getAgentStatus({
    hasResult: !!result,
    isError: !!result?.isError,
    isLaunchResult,
    isStreaming: !!props.isStreaming && !props.resultMap.has(tc.toolUseId),
    childCount: childToolCalls.length,
    taskStatus: props.agentTaskNotifications[tc.toolUseId]?.status,
  })
  const statusClassName = getAgentStatusClassName(status)
  const statusLabel = getAgentStatusLabel(status, t)
  const taskSummary = props.agentTaskNotifications[tc.toolUseId]?.summary?.trim() || ''
  const taskResult = props.agentTaskNotifications[tc.toolUseId]?.result?.trim() || ''
  const errorText =
    status === 'failed'
      ? taskSummary || (result?.isError ? getAgentErrorSummary(result.content) : '')
      : result?.isError
      ? getAgentErrorSummary(result.content)
      : ''
  const fullOutputText =
    result &&
    !result.isError &&
    !isLaunchResult &&
    !isAgentLifecycleResult(result.content)
      ? extractAgentDisplayText(result.content).trim()
      : ''
  const terminalTaskReport = (status === 'done' || status === 'stopped') ? taskResult : ''
  const terminalTaskSummary = (status === 'done' || status === 'stopped') ? taskSummary : ''
  const previewText = terminalTaskReport || fullOutputText || terminalTaskSummary
  const outputSummary = previewText ? getAgentOutputSummary(previewText) : ''
  const input =
    tc.input && typeof tc.input === 'object'
      ? (tc.input as Record<string, unknown>)
      : {}
  const description = typeof input.description === 'string' ? input.description : ''

  return {
    result,
    childToolCalls,
    isLaunchResult,
    recentToolCalls,
    status,
    statusClassName,
    statusLabel,
    taskSummary,
    taskResult,
    errorText,
    fullOutputText,
    terminalTaskReport,
    terminalTaskSummary,
    previewText,
    outputSummary,
    description,
  }
}

// ─── ToolCallTree (recursive) ───────────────────────────────────
// Rendered inline in the template using v-for + ToolCallBlock + self-referencing template block

</script>

<template>
  <!--
    ════════════════════════════════════════════════════════════════
    TOP-LEVEL: memory activity routing
    ════════════════════════════════════════════════════════════════
  -->

  <!-- ─── Memory + regular tool calls present ─────────────────── -->
  <div v-if="memoryActivity && regularToolCalls.length > 0" class="mb-2 space-y-2">
    <!-- ── MemoryToolActivityGroup ── -->
    <div class="mb-2">
      <div
        data-testid="memory-tool-activity-card"
        class="overflow-hidden rounded-lg border border-[var(--color-memory-border)] bg-[var(--color-memory-surface)]"
      >
        <button
          type="button"
          @click="memExpanded = !memExpanded"
          class="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-[var(--color-surface-hover)]/50"
        >
          <span
            class="material-symbols-outlined text-[15px] shrink-0 text-[var(--color-text-tertiary)]"
            aria-hidden="true"
          >{{ memExpanded ? 'expand_more' : 'chevron_right' }}</span>
          <span
            class="material-symbols-outlined text-[15px] shrink-0 text-[var(--color-memory-accent)]"
            aria-hidden="true"
          >bookmarks</span>
          <span
            class="min-w-0 flex-1 truncate text-[13px] font-medium text-[var(--color-text-primary)]"
          >
            {{ t(memoryActivity.action === 'saved' ? 'chat.memorySavedFromToolsTitle' : 'chat.memoryReferencedTitle', { count: memoryActivity.files.length }) }}
          </span>
          <span
            v-if="isStreaming"
            class="h-1.5 w-1.5 rounded-full bg-[var(--color-memory-accent)] animate-pulse-dot"
          />
        </button>

        <div v-if="memExpanded" class="border-t border-[var(--color-border)]/55 px-3 py-2.5">
          <div class="space-y-1.5">
            <button
              v-for="file in memoryActivity.files.slice(0, 4)"
              :key="file.path"
              type="button"
              :title="file.path"
              @click="openMemorySettings(file.path)"
              class="group flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-[var(--color-surface-hover)] focus:outline-none focus-visible:shadow-[var(--shadow-focus-ring)]"
            >
              <span
                class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-sm border border-[var(--color-memory-border)] bg-[var(--color-memory-icon-bg)] text-[var(--color-text-tertiary)] group-hover:text-[var(--color-memory-accent)]"
              >
                <span class="material-symbols-outlined text-[12px]" aria-hidden="true">settings</span>
              </span>
              <span class="min-w-0 flex-1">
                <span class="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span class="truncate text-[13px] font-medium text-[var(--color-text-primary)]">
                    {{ file.label }}
                  </span>
                  <span
                    v-if="file.lineHint"
                    class="shrink-0 text-[12px] text-[var(--color-text-tertiary)]"
                  >{{ file.lineHint }}</span>
                </span>
                <span
                  v-if="file.preview"
                  class="mt-0.5 line-clamp-2 text-[12px] leading-5 text-[var(--color-text-secondary)]"
                >{{ file.preview }}</span>
              </span>
            </button>

            <div
              v-if="memoryActivity.files.length > 4"
              class="px-2 py-1 text-[12px] text-[var(--color-text-tertiary)]"
            >
              {{ t('chat.memoryMoreFiles', { count: memoryActivity.files.length - 4 }) }}
            </div>
          </div>

          <button
            type="button"
            @click="memDetailsExpanded = !memDetailsExpanded"
            class="mt-2 inline-flex h-7 items-center gap-1.5 rounded-md border border-[var(--color-border)] px-2 text-[11px] font-medium text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
          >
            <span class="material-symbols-outlined text-[13px]">
              {{ memDetailsExpanded ? 'expand_more' : 'chevron_right' }}
            </span>
            {{ t('chat.memoryTechnicalDetails') }}
          </button>

          <div v-if="memDetailsExpanded" class="mt-2 space-y-1">
            <template
              v-for="tc in memoryToolCalls"
              :key="tc.id"
            >
              <div class="space-y-1">
                <ToolCallBlock
                  :tool-name="tc.toolName"
                  :input="tc.input"
                  :result="resultMap.get(tc.toolUseId) ? { content: resultMap.get(tc.toolUseId)!.content, isError: resultMap.get(tc.toolUseId)!.isError } : null"
                  compact
                  :is-pending="tc.isPending"
                  :status="tc.status"
                  :partial-input="tc.partialInput"
                />
                <div
                  v-if="(childToolCallsByParent.get(tc.toolUseId) ?? []).length > 0"
                  class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                >
                  <div class="space-y-1">
                    <template
                      v-for="childToolCall in childToolCallsByParent.get(tc.toolUseId) ?? []"
                      :key="childToolCall.id"
                    >
                      <div class="space-y-1">
                        <ToolCallBlock
                          :tool-name="childToolCall.toolName"
                          :input="childToolCall.input"
                          :result="resultMap.get(childToolCall.toolUseId) ? { content: resultMap.get(childToolCall.toolUseId)!.content, isError: resultMap.get(childToolCall.toolUseId)!.isError } : null"
                          compact
                          :is-pending="childToolCall.isPending"
                          :status="childToolCall.status"
                          :partial-input="childToolCall.partialInput"
                        />
                        <!-- Nested child recursion (2 levels) -->
                        <div
                          v-if="(childToolCallsByParent.get(childToolCall.toolUseId) ?? []).length > 0"
                          class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                        >
                          <div class="space-y-1">
                            <template
                              v-for="grandchild in childToolCallsByParent.get(childToolCall.toolUseId) ?? []"
                              :key="grandchild.id"
                            >
                              <div class="space-y-1">
                                <ToolCallBlock
                                  :tool-name="grandchild.toolName"
                                  :input="grandchild.input"
                                  :result="resultMap.get(grandchild.toolUseId) ? { content: resultMap.get(grandchild.toolUseId)!.content, isError: resultMap.get(grandchild.toolUseId)!.isError } : null"
                                  compact
                                  :is-pending="grandchild.isPending"
                                  :status="grandchild.status"
                                  :partial-input="grandchild.partialInput"
                                />
                              </div>
                            </template>
                          </div>
                        </div>
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Regular tool calls content ── -->
    <!-- AgentToolGroup (when all regular calls are Agent) -->
    <div v-if="allRegularAgents && regularToolCalls.length > 0" class="mb-2">
      <button
        type="button"
        @click="agentExpanded = !agentExpanded"
        class="flex w-full items-center gap-2 rounded-lg border border-[var(--color-border)]/40 bg-[var(--color-surface-container-low)] px-3 py-1.5 text-left transition-colors hover:bg-[var(--color-surface-container-high)]"
      >
        <span class="material-symbols-outlined text-[14px] text-[var(--color-outline)]">
          {{ agentExpanded ? 'expand_less' : 'expand_more' }}
        </span>
        <span class="flex-1 truncate text-[12px] text-[var(--color-text-secondary)]">
          {{ regularToolCalls.length === 1 ? t('toolGroup.agentOne') : t('toolGroup.agentMany', { count: regularToolCalls.length }) }}
        </span>
        <span
          v-if="regularAgentDerived.isAnyRunning"
          class="rounded-full bg-[var(--color-warning)]/12 px-2 py-0.5 text-[10px] font-semibold text-[var(--color-warning)]"
        >
          {{ t('agentStatus.running') }}
        </span>
        <span
          v-else-if="regularAgentDerived.errorPresent"
          class="material-symbols-outlined text-[14px] text-[var(--color-error)]"
        >error</span>
        <span
          v-else-if="regularAgentDerived.allComplete"
          class="material-symbols-outlined text-[14px] text-[var(--color-success)]"
        >check_circle</span>
        <span
          v-else-if="!regularAgentDerived.anyStopped"
          class="material-symbols-outlined text-[14px] text-[var(--color-outline)]"
        >pending</span>
        <span
          v-else
          class="material-symbols-outlined text-[14px] text-[var(--color-outline)]"
        >stop_circle</span>
      </button>

      <div v-if="agentExpanded" class="relative mt-3 pl-5">
        <div class="absolute bottom-6 left-[11px] top-4 w-px rounded full bg-[var(--color-border)]/45" />
        <div class="space-y-2">
          <div v-for="tc in regularToolCalls" :key="tc.id" class="relative pl-7">
            <div class="absolute left-0 top-1/2 -translate-y-1/2">
              <div class="absolute left-[11px] top-1/2 h-px w-4 -translate-y-1/2 bg-[var(--color-border)]/45" />
              <div class="absolute left-[8px] top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full border border-[var(--color-border)]/65 bg-[var(--color-surface-container-lowest)] shadow-[0_0_0_2px_var(--color-surface)]" />
            </div>
            <!-- ── AgentCallCard ── -->
            <div
              class="overflow-hidden rounded-lg border border-[var(--color-border)]/50 bg-[var(--color-surface-container-lowest)]"
            >
              <div
                class="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--color-surface-hover)]/50"
              >
                <span
                  class="material-symbols-outlined text-[18px] text-[var(--color-outline)]"
                >smart_toy</span>
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <span
                      class="text-[13px] font-semibold text-[var(--color-text-primary)]"
                    >Agent</span>
                    <span
                      v-if="agentCardDerived(tc).description"
                      class="truncate text-[12px] text-[var(--color-text-secondary)]"
                    >{{ agentCardDerived(tc).description }}</span>
                  </div>
                  <!-- Collapsed summary: outputSummary -->
                  <div
                    v-if="!agentCardExpandedMap[tc.toolUseId] && agentCardDerived(tc).outputSummary"
                    class="mt-1 line-clamp-2 text-[11px] text-[var(--color-text-tertiary)]"
                  >{{ agentCardDerived(tc).outputSummary }}</div>
                  <!-- Collapsed summary: recentToolCalls -->
                  <div
                    v-else-if="!agentCardExpandedMap[tc.toolUseId] && !agentCardDerived(tc).outputSummary && agentCardDerived(tc).recentToolCalls.length > 0"
                    class="mt-1 space-y-1"
                  >
                    <div
                      v-for="recentToolCall in agentCardDerived(tc).recentToolCalls"
                      :key="recentToolCall.id"
                      class="truncate text-[11px] text-[var(--color-text-tertiary)]"
                    >{{ formatRecentToolUseSummary(recentToolCall, resultMap) }}</div>
                  </div>
                  <!-- Collapsed summary: errorText -->
                  <div
                    v-else-if="!agentCardExpandedMap[tc.toolUseId] && !agentCardDerived(tc).outputSummary && !agentCardDerived(tc).recentToolCalls.length && agentCardDerived(tc).errorText"
                    class="mt-1 truncate text-[11px] text-[var(--color-error)]"
                  >{{ agentCardDerived(tc).errorText }}</div>
                </div>
                <!-- View Result button -->
                <button
                  v-if="agentCardDerived(tc).outputSummary"
                  type="button"
                  @click="(event: Event) => { event.stopPropagation(); openPreview(tc.toolUseId) }"
                  class="shrink-0 rounded-md border border-[var(--color-border)] px-2.5 py-1 text-[11px] font-medium text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
                >
                  {{ t('agentStatus.viewResult') }}
                </button>
                <!-- Status badge -->
                <span
                  :class="'rounded-full px-2 py-0.5 text-[10px] font-semibold ' + agentCardDerived(tc).statusClassName"
                >{{ agentCardDerived(tc).statusLabel }}</span>
                <!-- Expand/collapse button -->
                <button
                  type="button"
                  @click="toggleAgentCardExpanded(tc.toolUseId)"
                  class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[var(--color-outline)] transition-colors hover:bg-[var(--color-surface-hover)]"
                  :aria-label="agentCardExpandedMap[tc.toolUseId] ? 'Collapse agent' : 'Expand agent'"
                >
                  <span class="material-symbols-outlined text-[16px]">
                    {{ agentCardExpandedMap[tc.toolUseId] ? 'expand_less' : 'expand_more' }}
                  </span>
                </button>
              </div>

              <!-- Expanded body -->
              <div v-if="agentCardExpandedMap[tc.toolUseId]" class="border-t border-[var(--color-border)]/60 px-3 py-3">
                <!-- Error text -->
                <div
                  v-if="agentCardDerived(tc).errorText"
                  class="mb-3 rounded-lg border border-[var(--color-error)]/20 bg-[var(--color-error-container)]/60 px-3 py-2 text-[11px] text-[var(--color-error)]"
                >{{ agentCardDerived(tc).errorText }}</div>
                <!-- Child tool calls -->
                <div v-if="agentCardDerived(tc).childToolCalls.length > 0" class="space-y-1">
                  <template
                    v-for="childToolCall in agentCardDerived(tc).childToolCalls"
                    :key="childToolCall.id"
                  >
                    <div class="space-y-1">
                      <ToolCallBlock
                        :tool-name="childToolCall.toolName"
                        :input="childToolCall.input"
                        :result="resultMap.get(childToolCall.toolUseId) ? { content: resultMap.get(childToolCall.toolUseId)!.content, isError: resultMap.get(childToolCall.toolUseId)!.isError } : null"
                        compact
                        :is-pending="childToolCall.isPending"
                        :status="childToolCall.status"
                        :partial-input="childToolCall.partialInput"
                      />
                      <!-- Nested children (2 levels) -->
                      <div
                        v-if="(childToolCallsByParent.get(childToolCall.toolUseId) ?? []).length > 0"
                        class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                      >
                        <div class="space-y-1">
                          <template
                            v-for="grandchild in childToolCallsByParent.get(childToolCall.toolUseId) ?? []"
                            :key="grandchild.id"
                          >
                            <div class="space-y-1">
                              <ToolCallBlock
                                :tool-name="grandchild.toolName"
                                :input="grandchild.input"
                                :result="resultMap.get(grandchild.toolUseId) ? { content: resultMap.get(grandchild.toolUseId)!.content, isError: resultMap.get(grandchild.toolUseId)!.isError } : null"
                                compact
                                :is-pending="grandchild.isPending"
                                :status="grandchild.status"
                                :partial-input="grandchild.partialInput"
                              />
                            </div>
                          </template>
                        </div>
                      </div>
                    </div>
                  </template>
                </div>
                <!-- No activity -->
                <div
                  v-else-if="agentCardDerived(tc).outputSummary"
                  class="text-[11px] text-[var(--color-text-tertiary)]"
                >{{ t('agentStatus.noActivity') }}</div>
                <div
                  v-else
                  class="text-[11px] text-[var(--color-text-tertiary)]"
                >{{ agentCardDerived(tc).status === 'starting' ? t('agentStatus.starting') : t('agentStatus.noActivity') }}</div>
              </div>
            </div>
            <!-- ── End AgentCallCard ── -->
          </div>
        </div>
      </div>
    </div>

    <!-- Single non-agent regular call -->
    <template v-else-if="regularToolCalls.length === 1">
      <div class="space-y-1">
        <ToolCallBlock
          :tool-name="regularToolCalls[0].toolName"
          :input="regularToolCalls[0].input"
          :result="resultMap.get(regularToolCalls[0].toolUseId) ? { content: resultMap.get(regularToolCalls[0].toolUseId)!.content, isError: resultMap.get(regularToolCalls[0].toolUseId)!.isError } : null"
          :is-pending="regularToolCalls[0].isPending"
          :status="regularToolCalls[0].status"
          :partial-input="regularToolCalls[0].partialInput"
        />
        <div
          v-if="(childToolCallsByParent.get(regularToolCalls[0].toolUseId) ?? []).length > 0"
          class="mb-2 ml-16 border-l border-[var(--color-border)]/60 pl-3"
        >
          <div class="space-y-1">
            <template
              v-for="childToolCall in childToolCallsByParent.get(regularToolCalls[0].toolUseId) ?? []"
              :key="childToolCall.id"
            >
              <div class="space-y-1">
                <ToolCallBlock
                  :tool-name="childToolCall.toolName"
                  :input="childToolCall.input"
                  :result="resultMap.get(childToolCall.toolUseId) ? { content: resultMap.get(childToolCall.toolUseId)!.content, isError: resultMap.get(childToolCall.toolUseId)!.isError } : null"
                  compact
                  :is-pending="childToolCall.isPending"
                  :status="childToolCall.status"
                  :partial-input="childToolCall.partialInput"
                />
                <!-- Nested children (2 levels) -->
                <div
                  v-if="(childToolCallsByParent.get(childToolCall.toolUseId) ?? []).length > 0"
                  class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                >
                  <div class="space-y-1">
                    <template
                      v-for="grandchild in childToolCallsByParent.get(childToolCall.toolUseId) ?? []"
                      :key="grandchild.id"
                    >
                      <div class="space-y-1">
                        <ToolCallBlock
                          :tool-name="grandchild.toolName"
                          :input="grandchild.input"
                          :result="resultMap.get(grandchild.toolUseId) ? { content: resultMap.get(grandchild.toolUseId)!.content, isError: resultMap.get(grandchild.toolUseId)!.isError } : null"
                          compact
                          :is-pending="grandchild.isPending"
                          :status="grandchild.status"
                          :partial-input="grandchild.partialInput"
                        />
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </template>

    <!-- Multiple non-agent regular calls (ToolCallGroupMulti) -->
    <div v-else-if="regularToolCalls.length > 1" class="mb-2">
      <button
        type="button"
        @click="multiExpanded = !multiExpanded"
        class="flex w-full items-center gap-2 rounded-lg border border-[var(--color-border)]/40 bg-[var(--color-surface-container-low)] px-3 py-1.5 text-left transition-colors hover:bg-[var(--color-surface-container-high)]"
      >
        <span class="material-symbols-outlined text-[14px] text-[var(--color-outline)]">
          {{ multiExpanded ? 'expand_less' : 'expand_more' }}
        </span>
        <span class="flex-1 truncate text-[12px] text-[var(--color-text-secondary)]">
          {{ generateSummary(regularToolCalls, t) }}
        </span>
        <span
          v-if="!multiIsRunning && !multiErrorPresent"
          class="material-symbols-outlined text-[14px] text-[var(--color-success)]"
        >check_circle</span>
        <span
          v-else-if="!multiIsRunning && multiErrorPresent"
          class="material-symbols-outlined text-[14px] text-[var(--color-error)]"
        >error</span>
        <span
          v-else-if="multiIsRunning"
          class="h-1.5 w-1.5 rounded-full bg-[var(--color-brand)] animate-pulse-dot"
        />
      </button>

      <div v-if="multiExpanded" class="mt-1.5 space-y-1">
        <template
          v-for="tc in regularToolCalls"
          :key="tc.id"
        >
          <div class="space-y-1">
            <ToolCallBlock
              :tool-name="tc.toolName"
              :input="tc.input"
              :result="resultMap.get(tc.toolUseId) ? { content: resultMap.get(tc.toolUseId)!.content, isError: resultMap.get(tc.toolUseId)!.isError } : null"
              compact
              :is-pending="tc.isPending"
              :status="tc.status"
              :partial-input="tc.partialInput"
            />
            <div
              v-if="(childToolCallsByParent.get(tc.toolUseId) ?? []).length > 0"
              class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
            >
              <div class="space-y-1">
                <template
                  v-for="childToolCall in childToolCallsByParent.get(tc.toolUseId) ?? []"
                  :key="childToolCall.id"
                >
                  <div class="space-y-1">
                    <ToolCallBlock
                      :tool-name="childToolCall.toolName"
                      :input="childToolCall.input"
                      :result="resultMap.get(childToolCall.toolUseId) ? { content: resultMap.get(childToolCall.toolUseId)!.content, isError: resultMap.get(childToolCall.toolUseId)!.isError } : null"
                      compact
                      :is-pending="childToolCall.isPending"
                      :status="childToolCall.status"
                      :partial-input="childToolCall.partialInput"
                    />
                    <!-- Nested children (2 levels) -->
                    <div
                      v-if="(childToolCallsByParent.get(childToolCall.toolUseId) ?? []).length > 0"
                      class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                    >
                      <div class="space-y-1">
                        <template
                          v-for="grandchild in childToolCallsByParent.get(childToolCall.toolUseId) ?? []"
                          :key="grandchild.id"
                        >
                          <div class="space-y-1">
                            <ToolCallBlock
                              :tool-name="grandchild.toolName"
                              :input="grandchild.input"
                              :result="resultMap.get(grandchild.toolUseId) ? { content: resultMap.get(grandchild.toolUseId)!.content, isError: resultMap.get(grandchild.toolUseId)!.isError } : null"
                              compact
                              :is-pending="grandchild.isPending"
                              :status="grandchild.status"
                              :partial-input="grandchild.partialInput"
                            />
                          </div>
                        </template>
                      </div>
                    </div>
                  </div>
                </template>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>

  <!-- ─── Memory only (no regular tool calls) ─────────────────── -->
  <div v-else-if="memoryActivity && regularToolCalls.length === 0" class="mb-2">
    <div
      data-testid="memory-tool-activity-card"
      class="overflow-hidden rounded-lg border border-[var(--color-memory-border)] bg-[var(--color-memory-surface)]"
    >
      <button
        type="button"
        @click="memExpanded = !memExpanded"
        class="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-[var(--color-surface-hover)]/50"
      >
        <span
          class="material-symbols-outlined text-[15px] shrink-0 text-[var(--color-text-tertiary)]"
          aria-hidden="true"
        >{{ memExpanded ? 'expand_more' : 'chevron_right' }}</span>
        <span
          class="material-symbols-outlined text-[15px] shrink-0 text-[var(--color-memory-accent)]"
          aria-hidden="true"
        >bookmarks</span>
        <span
          class="min-w-0 flex-1 truncate text-[13px] font-medium text-[var(--color-text-primary)]"
        >
          {{ t(memoryActivity.action === 'saved' ? 'chat.memorySavedFromToolsTitle' : 'chat.memoryReferencedTitle', { count: memoryActivity.files.length }) }}
        </span>
        <span
          v-if="isStreaming"
          class="h-1.5 w-1.5 rounded-full bg-[var(--color-memory-accent)] animate-pulse-dot"
        />
      </button>

      <div v-if="memExpanded" class="border-t border-[var(--color-border)]/55 px-3 py-2.5">
        <div class="space-y-1.5">
          <button
            v-for="file in memoryActivity.files.slice(0, 4)"
            :key="file.path"
            type="button"
            :title="file.path"
            @click="openMemorySettings(file.path)"
            class="group flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-[var(--color-surface-hover)] focus:outline-none focus-visible:shadow-[var(--shadow-focus-ring)]"
          >
            <span
              class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-sm border border-[var(--color-memory-border)] bg-[var(--color-memory-icon-bg)] text-[var(--color-text-tertiary)] group-hover:text-[var(--color-memory-accent)]"
            >
              <span class="material-symbols-outlined text-[12px]" aria-hidden="true">settings</span>
            </span>
            <span class="min-w-0 flex-1">
              <span class="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span class="truncate text-[13px] font-medium text-[var(--color-text-primary)]">
                  {{ file.label }}
                </span>
                <span
                  v-if="file.lineHint"
                  class="shrink-0 text-[12px] text-[var(--color-text-tertiary)]"
                >{{ file.lineHint }}</span>
              </span>
              <span
                v-if="file.preview"
                class="mt-0.5 line-clamp-2 text-[12px] leading-5 text-[var(--color-text-secondary)]"
              >{{ file.preview }}</span>
            </span>
          </button>

          <div
            v-if="memoryActivity.files.length > 4"
            class="px-2 py-1 text-[12px] text-[var(--color-text-tertiary)]"
          >
            {{ t('chat.memoryMoreFiles', { count: memoryActivity.files.length - 4 }) }}
          </div>
        </div>

        <button
          type="button"
          @click="memDetailsExpanded = !memDetailsExpanded"
          class="mt-2 inline-flex h-7 items-center gap-1.5 rounded-md border border-[var(--color-border)] px-2 text-[11px] font-medium text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
        >
          <span class="material-symbols-outlined text-[13px]">
            {{ memDetailsExpanded ? 'expand_more' : 'chevron_right' }}
          </span>
          {{ t('chat.memoryTechnicalDetails') }}
        </button>

        <div v-if="memDetailsExpanded" class="mt-2 space-y-1">
          <template
            v-for="tc in memoryToolCalls"
            :key="tc.id"
          >
            <div class="space-y-1">
              <ToolCallBlock
                :tool-name="tc.toolName"
                :input="tc.input"
                :result="resultMap.get(tc.toolUseId) ? { content: resultMap.get(tc.toolUseId)!.content, isError: resultMap.get(tc.toolUseId)!.isError } : null"
                compact
                :is-pending="tc.isPending"
                :status="tc.status"
                :partial-input="tc.partialInput"
              />
              <div
                v-if="(childToolCallsByParent.get(tc.toolUseId) ?? []).length > 0"
                class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
              >
                <div class="space-y-1">
                  <template
                    v-for="childToolCall in childToolCallsByParent.get(tc.toolUseId) ?? []"
                    :key="childToolCall.id"
                  >
                    <div class="space-y-1">
                      <ToolCallBlock
                        :tool-name="childToolCall.toolName"
                        :input="childToolCall.input"
                        :result="resultMap.get(childToolCall.toolUseId) ? { content: resultMap.get(childToolCall.toolUseId)!.content, isError: resultMap.get(childToolCall.toolUseId)!.isError } : null"
                        compact
                        :is-pending="childToolCall.isPending"
                        :status="childToolCall.status"
                        :partial-input="childToolCall.partialInput"
                      />
                      <div
                        v-if="(childToolCallsByParent.get(childToolCall.toolUseId) ?? []).length > 0"
                        class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                      >
                        <div class="space-y-1">
                          <template
                            v-for="grandchild in childToolCallsByParent.get(childToolCall.toolUseId) ?? []"
                            :key="grandchild.id"
                          >
                            <div class="space-y-1">
                              <ToolCallBlock
                                :tool-name="grandchild.toolName"
                                :input="grandchild.input"
                                :result="resultMap.get(grandchild.toolUseId) ? { content: resultMap.get(grandchild.toolUseId)!.content, isError: resultMap.get(grandchild.toolUseId)!.isError } : null"
                                compact
                                :is-pending="grandchild.isPending"
                                :status="grandchild.status"
                                :partial-input="grandchild.partialInput"
                              />
                            </div>
                          </template>
                        </div>
                      </div>
                    </div>
                  </template>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>

  <!-- ─── No memory activity — render directly ─────────────────── -->
  <template v-else>
    <!-- AgentToolGroup (all agents at top level) -->
    <div v-if="allAgents" class="mb-2">
      <button
        type="button"
        @click="agentExpanded = !agentExpanded"
        class="flex w-full items-center gap-2 rounded-lg border border-[var(--color-border)]/40 bg-[var(--color-surface-container-low)] px-3 py-1.5 text-left transition-colors hover:bg-[var(--color-surface-container-high)]"
      >
        <span class="material-symbols-outlined text-[14px] text-[var(--color-outline)]">
          {{ agentExpanded ? 'expand_less' : 'expand_more' }}
        </span>
        <span class="flex-1 truncate text-[12px] text-[var(--color-text-secondary)]">
          {{ toolCalls.length === 1 ? t('toolGroup.agentOne') : t('toolGroup.agentMany', { count: toolCalls.length }) }}
        </span>
        <span
          v-if="allAgentDerived.isAnyRunning"
          class="rounded-full bg-[var(--color-warning)]/12 px-2 py-0.5 text-[10px] font-semibold text-[var(--color-warning)]"
        >
          {{ t('agentStatus.running') }}
        </span>
        <span
          v-else-if="allAgentDerived.errorPresent"
          class="material-symbols-outlined text-[14px] text-[var(--color-error)]"
        >error</span>
        <span
          v-else-if="allAgentDerived.allComplete"
          class="material-symbols-outlined text-[14px] text-[var(--color-success)]"
        >check_circle</span>
        <span
          v-else-if="!allAgentDerived.anyStopped"
          class="material-symbols-outlined text-[14px] text-[var(--color-outline)]"
        >pending</span>
        <span
          v-else
          class="material-symbols-outlined text-[14px] text-[var(--color-outline)]"
        >stop_circle</span>
      </button>

      <div v-if="agentExpanded" class="relative mt-3 pl-5">
        <div class="absolute bottom-6 left-[11px] top-4 w-px rounded-full bg-[var(--color-border)]/45" />
        <div class="space-y-2">
          <div v-for="tc in toolCalls" :key="tc.id" class="relative pl-7">
            <div class="absolute left-0 top-1/2 -translate-y-1/2">
              <div class="absolute left-[11px] top-1/2 h-px w-4 -translate-y-1/2 bg-[var(--color-border)]/45" />
              <div class="absolute left-[8px] top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full border border-[var(--color-border)]/65 bg-[var(--color-surface-container-lowest)] shadow-[0_0_0_2px_var(--color-surface)]" />
            </div>
            <!-- ── AgentCallCard ── -->
            <div
              class="overflow-hidden rounded-lg border border-[var(--color-border)]/50 bg-[var(--color-surface-container-lowest)]"
            >
              <div
                class="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--color-surface-hover)]/50"
              >
                <span
                  class="material-symbols-outlined text-[18px] text-[var(--color-outline)]"
                >smart_toy</span>
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <span
                      class="text-[13px] font-semibold text-[var(--color-text-primary)]"
                    >Agent</span>
                    <span
                      v-if="agentCardDerived(tc).description"
                      class="truncate text-[12px] text-[var(--color-text-secondary)]"
                    >{{ agentCardDerived(tc).description }}</span>
                  </div>
                  <!-- Collapsed: outputSummary -->
                  <div
                    v-if="!agentCardExpandedMap[tc.toolUseId] && agentCardDerived(tc).outputSummary"
                    class="mt-1 line-clamp-2 text-[11px] text-[var(--color-text-tertiary)]"
                  >{{ agentCardDerived(tc).outputSummary }}</div>
                  <!-- Collapsed: recentToolCalls -->
                  <div
                    v-else-if="!agentCardExpandedMap[tc.toolUseId] && !agentCardDerived(tc).outputSummary && agentCardDerived(tc).recentToolCalls.length > 0"
                    class="mt-1 space-y-1"
                  >
                    <div
                      v-for="recentToolCall in agentCardDerived(tc).recentToolCalls"
                      :key="recentToolCall.id"
                      class="truncate text-[11px] text-[var(--color-text-tertiary)]"
                    >{{ formatRecentToolUseSummary(recentToolCall, resultMap) }}</div>
                  </div>
                  <!-- Collapsed: errorText -->
                  <div
                    v-else-if="!agentCardExpandedMap[tc.toolUseId] && !agentCardDerived(tc).outputSummary && !agentCardDerived(tc).recentToolCalls.length && agentCardDerived(tc).errorText"
                    class="mt-1 truncate text-[11px] text-[var(--color-error)]"
                  >{{ agentCardDerived(tc).errorText }}</div>
                </div>
                <!-- View Result button -->
                <button
                  v-if="agentCardDerived(tc).outputSummary"
                  type="button"
                  @click="(event: Event) => { event.stopPropagation(); openPreview(tc.toolUseId) }"
                  class="shrink-0 rounded-md border border-[var(--color-border)] px-2.5 py-1 text-[11px] font-medium text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
                >
                  {{ t('agentStatus.viewResult') }}
                </button>
                <!-- Status badge -->
                <span
                  :class="'rounded-full px-2 py-0.5 text-[10px] font-semibold ' + agentCardDerived(tc).statusClassName"
                >{{ agentCardDerived(tc).statusLabel }}</span>
                <!-- Expand/collapse button -->
                <button
                  type="button"
                  @click="toggleAgentCardExpanded(tc.toolUseId)"
                  class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[var(--color-outline)] transition-colors hover:bg-[var(--color-surface-hover)]"
                  :aria-label="agentCardExpandedMap[tc.toolUseId] ? 'Collapse agent' : 'Expand agent'"
                >
                  <span class="material-symbols-outlined text-[16px]">
                    {{ agentCardExpandedMap[tc.toolUseId] ? 'expand_less' : 'expand_more' }}
                  </span>
                </button>
              </div>

              <!-- Expanded body -->
              <div v-if="agentCardExpandedMap[tc.toolUseId]" class="border-t border-[var(--color-border)]/60 px-3 py-3">
                <div
                  v-if="agentCardDerived(tc).errorText"
                  class="mb-3 rounded-lg border border-[var(--color-error)]/20 bg-[var(--color-error-container)]/60 px-3 py-2 text-[11px] text-[var(--color-error)]"
                >{{ agentCardDerived(tc).errorText }}</div>
                <div v-if="agentCardDerived(tc).childToolCalls.length > 0" class="space-y-1">
                  <template
                    v-for="childToolCall in agentCardDerived(tc).childToolCalls"
                    :key="childToolCall.id"
                  >
                    <div class="space-y-1">
                      <ToolCallBlock
                        :tool-name="childToolCall.toolName"
                        :input="childToolCall.input"
                        :result="resultMap.get(childToolCall.toolUseId) ? { content: resultMap.get(childToolCall.toolUseId)!.content, isError: resultMap.get(childToolCall.toolUseId)!.isError } : null"
                        compact
                        :is-pending="childToolCall.isPending"
                        :status="childToolCall.status"
                        :partial-input="childToolCall.partialInput"
                      />
                      <div
                        v-if="(childToolCallsByParent.get(childToolCall.toolUseId) ?? []).length > 0"
                        class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                      >
                        <div class="space-y-1">
                          <template
                            v-for="grandchild in childToolCallsByParent.get(childToolCall.toolUseId) ?? []"
                            :key="grandchild.id"
                          >
                            <div class="space-y-1">
                              <ToolCallBlock
                                :tool-name="grandchild.toolName"
                                :input="grandchild.input"
                                :result="resultMap.get(grandchild.toolUseId) ? { content: resultMap.get(grandchild.toolUseId)!.content, isError: resultMap.get(grandchild.toolUseId)!.isError } : null"
                                compact
                                :is-pending="grandchild.isPending"
                                :status="grandchild.status"
                                :partial-input="grandchild.partialInput"
                              />
                            </div>
                          </template>
                        </div>
                      </div>
                    </div>
                  </template>
                </div>
                <div
                  v-else-if="agentCardDerived(tc).outputSummary"
                  class="text-[11px] text-[var(--color-text-tertiary)]"
                >{{ t('agentStatus.noActivity') }}</div>
                <div
                  v-else
                  class="text-[11px] text-[var(--color-text-tertiary)]"
                >{{ agentCardDerived(tc).status === 'starting' ? t('agentStatus.starting') : t('agentStatus.noActivity') }}</div>
              </div>
            </div>
            <!-- ── End AgentCallCard ── -->
          </div>
        </div>
      </div>
    </div>

    <!-- Single non-agent tool call -->
    <template v-else-if="toolCalls.length === 1">
      <div class="space-y-1">
        <ToolCallBlock
          :tool-name="toolCalls[0].toolName"
          :input="toolCalls[0].input"
          :result="resultMap.get(toolCalls[0].toolUseId) ? { content: resultMap.get(toolCalls[0].toolUseId)!.content, isError: resultMap.get(toolCalls[0].toolUseId)!.isError } : null"
          :is-pending="toolCalls[0].isPending"
          :status="toolCalls[0].status"
          :partial-input="toolCalls[0].partialInput"
        />
        <div
          v-if="(childToolCallsByParent.get(toolCalls[0].toolUseId) ?? []).length > 0"
          class="mb-2 ml-16 border-l border-[var(--color-border)]/60 pl-3"
        >
          <div class="space-y-1">
            <template
              v-for="childToolCall in childToolCallsByParent.get(toolCalls[0].toolUseId) ?? []"
              :key="childToolCall.id"
            >
              <div class="space-y-1">
                <ToolCallBlock
                  :tool-name="childToolCall.toolName"
                  :input="childToolCall.input"
                  :result="resultMap.get(childToolCall.toolUseId) ? { content: resultMap.get(childToolCall.toolUseId)!.content, isError: resultMap.get(childToolCall.toolUseId)!.isError } : null"
                  compact
                  :is-pending="childToolCall.isPending"
                  :status="childToolCall.status"
                  :partial-input="childToolCall.partialInput"
                />
                <div
                  v-if="(childToolCallsByParent.get(childToolCall.toolUseId) ?? []).length > 0"
                  class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                >
                  <div class="space-y-1">
                    <template
                      v-for="grandchild in childToolCallsByParent.get(childToolCall.toolUseId) ?? []"
                      :key="grandchild.id"
                    >
                      <div class="space-y-1">
                        <ToolCallBlock
                          :tool-name="grandchild.toolName"
                          :input="grandchild.input"
                          :result="resultMap.get(grandchild.toolUseId) ? { content: resultMap.get(grandchild.toolUseId)!.content, isError: resultMap.get(grandchild.toolUseId)!.isError } : null"
                          compact
                          :is-pending="grandchild.isPending"
                          :status="grandchild.status"
                          :partial-input="grandchild.partialInput"
                        />
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </template>

    <!-- Multiple non-agent tool calls (ToolCallGroupMulti) -->
    <div v-else class="mb-2">
      <button
        type="button"
        @click="multiExpanded = !multiExpanded"
        class="flex w-full items-center gap-2 rounded-lg border border-[var(--color-border)]/40 bg-[var(--color-surface-container-low)] px-3 py-1.5 text-left transition-colors hover:bg-[var(--color-surface-container-high)]"
      >
        <span class="material-symbols-outlined text-[14px] text-[var(--color-outline)]">
          {{ multiExpanded ? 'expand_less' : 'expand_more' }}
        </span>
        <span class="flex-1 truncate text-[12px] text-[var(--color-text-secondary)]">
          {{ multiSummary }}
        </span>
        <span
          v-if="!multiIsRunning && !multiErrorPresent"
          class="material-symbols-outlined text-[14px] text-[var(--color-success)]"
        >check_circle</span>
        <span
          v-else-if="!multiIsRunning && multiErrorPresent"
          class="material-symbols-outlined text-[14px] text-[var(--color-error)]"
        >error</span>
        <span
          v-else-if="multiIsRunning"
          class="h-1.5 w-1.5 rounded-full bg-[var(--color-brand)] animate-pulse-dot"
        />
      </button>

      <div v-if="multiExpanded" class="mt-1.5 space-y-1">
        <template
          v-for="tc in toolCalls"
          :key="tc.id"
        >
          <div class="space-y-1">
            <ToolCallBlock
              :tool-name="tc.toolName"
              :input="tc.input"
              :result="resultMap.get(tc.toolUseId) ? { content: resultMap.get(tc.toolUseId)!.content, isError: resultMap.get(tc.toolUseId)!.isError } : null"
              compact
              :is-pending="tc.isPending"
              :status="tc.status"
              :partial-input="tc.partialInput"
            />
            <div
              v-if="(childToolCallsByParent.get(tc.toolUseId) ?? []).length > 0"
              class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
            >
              <div class="space-y-1">
                <template
                  v-for="childToolCall in childToolCallsByParent.get(tc.toolUseId) ?? []"
                  :key="childToolCall.id"
                >
                  <div class="space-y-1">
                    <ToolCallBlock
                      :tool-name="childToolCall.toolName"
                      :input="childToolCall.input"
                      :result="resultMap.get(childToolCall.toolUseId) ? { content: resultMap.get(childToolCall.toolUseId)!.content, isError: resultMap.get(childToolCall.toolUseId)!.isError } : null"
                      compact
                      :is-pender="childToolCall.isPending"
                      :status="childToolCall.status"
                      :partial-input="childToolCall.partialInput"
                    />
                    <div
                      v-if="(childToolCallsByParent.get(childToolCall.toolUseId) ?? []).length > 0"
                      class="ml-4 border-l border-[var(--color-border)]/60 pl-3"
                    >
                      <div class="space-y-1">
                        <template
                          v-for="grandchild in childToolCallsByParent.get(childToolCall.toolUseId) ?? []"
                          :key="grandchild.id"
                        >
                          <div class="space-y-1">
                            <ToolCallBlock
                              :tool-name="grandchild.toolName"
                              :input="grandchild.input"
                              :result="resultMap.get(grandchild.toolUseId) ? { content: resultMap.get(grandchild.toolUseId)!.content, isError: resultMap.get(grandchild.toolUseId)!.isError } : null"
                              compact
                              :is-pending="grandchild.isPending"
                              :status="grandchild.status"
                              :partial-input="grandchild.partialInput"
                            />
                          </div>
                        </template>
                      </div>
                    </div>
                  </div>
                </template>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </template>

  <!-- ─── Preview Modal (shared across all AgentCallCards) ─── -->
  <teleport to="body">
    <Modal
      v-if="previewOpenMap"
      :open="!!previewOpenMap"
      :on-close="closePreviewModal"
      :title="(agentCardDerived(toolCalls.find(tc => tc.toolUseId === previewOpenMap)!).description || t('agentStatus.resultTitle'))"
      :width="900"
    >
      <div class="max-h-[70vh] overflow-y-auto">
        <MarkdownRenderer
          :content="(agentCardDerived(toolCalls.find(tc => tc.toolUseId === previewOpenMap)!).previewText || agentCardDerived(toolCalls.find(tc => tc.toolUseId === previewOpenMap)!).errorText)"
        />
      </div>
    </Modal>
  </teleport>
</template>
