<script setup lang="ts">
// v3.0 — AgentsSettings (Vue 3 SFC translation from React Settings.tsx lines 3726-3941)
// Main agents list page. Shows summary cards, grouped agent list by source, and navigates to AgentDetailView.

import { ref, onMounted, watch, computed } from 'vue'
import { useAgentStore } from '../stores/agentStore'
import { useSessionStore } from '../stores/sessionStore'
import { useUIStore } from '../stores/uiStore'
import { useTranslation } from '../i18n'
import AgentDetailView from './AgentDetailView.vue'

// ─── Constants (from React lines 3705-3724) ──────────────────
const AGENT_COLORS: Record<string, string> = {
  red: '#ef4444',
  orange: '#f97316',
  yellow: '#eab308',
  green: '#22c55e',
  blue: '#3b82f6',
  purple: '#a855f7',
  pink: '#ec4899',
  cyan: '#06b6d4',
}

const AGENT_SOURCE_ORDER = [
  'userSettings',
  'projectSettings',
  'localSettings',
  'policySettings',
  'plugin',
  'flagSettings',
  'built-in',
] as const

type AgentSource = typeof AGENT_SOURCE_ORDER[number]

// ─── Stores ─────────────────────────────────────────────────
const agentStore = useAgentStore()
const sessionStore = useSessionStore()
const uiStore = useUIStore()
const t = useTranslation()

// ─── Local state ────────────────────────────────────────────
const currentWorkDir = ref<string | undefined>(undefined)

// ─── Computed (from React useMemo/useEffect) ────────────────
const groupedAgents = computed(() => {
  const groups: Partial<Record<AgentSource, typeof agentStore.allAgents[number][]>> = {}
  for (const agent of agentStore.allAgents) {
    const key = agent.source as AgentSource
    ;(groups[key] ??= []).push(agent)
  }
  return groups
})

const sourceCount = computed(() => {
  return AGENT_SOURCE_ORDER.filter((source) => (groupedAgents.value[source] ?? []).length > 0).length
})

const activeSession = computed(() => {
  return sessionStore.sessions.find((s) => s.id === sessionStore.activeSessionId)
})

// ─── Helpers (from React lines 4092-4132) ────────────────────
function getAgentDotColor(color?: string): string {
  return color && AGENT_COLORS[color] ? AGENT_COLORS[color] : 'var(--color-text-tertiary)'
}

function getAgentSourceIcon(source: string): string {
  switch (source) {
    case 'userSettings':
      return 'person'
    case 'projectSettings':
      return 'folder'
    case 'localSettings':
      return 'folder_lock'
    case 'policySettings':
      return 'shield'
    case 'plugin':
      return 'extension'
    case 'flagSettings':
      return 'terminal'
    case 'built-in':
      return 'inventory_2'
    default:
      return 'smart_toy'
  }
}

function getAgentSourceAccentClass(source: string): string {
  switch (source) {
    case 'userSettings':
      return 'bg-[var(--color-primary-fixed)] text-[var(--color-brand)]'
    case 'projectSettings':
      return 'bg-[var(--color-success-container)] text-[var(--color-success)]'
    case 'localSettings':
      return 'bg-[var(--color-info-container)] text-[var(--color-info)]'
    case 'policySettings':
      return 'bg-[var(--color-warning-container)] text-[var(--color-warning)]'
    case 'plugin':
      return 'bg-[var(--color-warning-container)] text-[var(--color-warning)]'
    case 'flagSettings':
      return 'bg-[var(--color-error)]/10 text-[var(--color-error)]'
    case 'built-in':
      return 'bg-[var(--color-surface-container-high)] text-[var(--color-text-tertiary)]'
    default:
      return ''
  }
}

// ─── Lifecycle ──────────────────────────────────────────────
onMounted(() => {
  currentWorkDir.value = activeSession.value?.workDir || undefined
  agentStore.fetchAgents(currentWorkDir.value)
})

// Watch for session changes to re-fetch agents with correct workDir
watch(
  () => activeSession.value?.workDir,
  (newDir) => {
    currentWorkDir.value = newDir || undefined
    agentStore.fetchAgents(currentWorkDir.value)
  }
)

// ─── Actions ────────────────────────────────────────────────
function handleAgentBack() {
  const returnTab = agentStore.selectedAgentReturnTab
  agentStore.selectAgent(null)
  if (returnTab === 'plugins') {
    uiStore.setPendingSettingsTab('plugins')
  }
}

</script>

<template>
  <div class="w-full min-w-0">
    <!-- Agent detail view -->
    <AgentDetailView
      v-if="agentStore.selectedAgent"
      :agent="agentStore.selectedAgent"
      @back="handleAgentBack"
    />

    <!-- Agents list view -->
    <template v-else>
      <!-- Loading state -->
      <div v-if="agentStore.isLoading && agentStore.allAgents.length === 0" class="flex justify-center py-12">
        <div class="animate-spin w-5 h-5 border-2 border-[var(--color-brand)] border-t-transparent rounded-full" />
      </div>

      <!-- Error state -->
      <div v-else-if="agentStore.error" class="text-center py-12 px-4">
        <span class="material-symbols-outlined text-[40px] text-[var(--color-error)] mb-3 block" style="fontVariationSettings: 'FILL' 1">error_outline</span>
        <p class="text-sm text-[var(--color-error)] mb-2">{{ agentStore.error }}</p>
        <button
          @click="agentStore.fetchAgents(currentWorkDir)"
          class="text-xs text-[var(--color-text-accent)] hover:underline"
        >
          {{ t('common.retry') }}
        </button>
      </div>

      <!-- Empty state -->
      <div v-else-if="agentStore.allAgents.length === 0" class="text-center py-12 px-4 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface-container-low)]">
        <span class="material-symbols-outlined text-[40px] text-[var(--color-text-tertiary)] mb-3 block" style="fontVariationSettings: 'FILL' 1">smart_toy</span>
        <p class="text-sm text-[var(--color-text-secondary)] mb-1">{{ t('settings.agents.empty') }}</p>
        <p class="text-xs text-[var(--color-text-tertiary)]">{{ t('settings.agents.emptyHint') }}</p>
      </div>

      <!-- Agents list -->
      <div v-else class="flex flex-col gap-6 min-w-0">
        <!-- Header card -->
        <section class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] overflow-hidden">
          <div class="grid gap-4 px-5 py-5 min-w-0 xl:grid-cols-[minmax(0,1.6fr)_minmax(320px,1fr)] xl:items-end">
            <div class="min-w-0">
              <div class="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--color-text-tertiary)] mb-2">
                {{ t('settings.agents.browserEyebrow') }}
              </div>
              <div class="flex items-center gap-3 mb-2">
                <span class="material-symbols-outlined text-[22px] text-[var(--color-brand)]" style="fontVariationSettings: 'FILL' 1">smart_toy</span>
                <h3 class="text-lg font-semibold text-[var(--color-text-primary)]">
                  {{ t('settings.agents.browserTitle') }}
                </h3>
              </div>
              <p class="text-sm leading-6 text-[var(--color-text-secondary)] max-w-3xl">
                {{ t('settings.agents.description') }}
              </p>
            </div>

            <!-- Summary cards -->
            <div class="grid grid-cols-2 gap-3 min-w-0 sm:grid-cols-3">
              <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3 min-w-0">
                <div class="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-tertiary)] min-w-0">
                  <span class="material-symbols-outlined text-[14px] flex-shrink-0" style="fontVariationSettings: 'FILL' 1">smart_toy</span>
                  <span class="truncate">{{ t('settings.agents.summary.totalAgents') }}</span>
                </div>
                <div class="mt-2 text-lg font-semibold text-[var(--color-text-primary)] truncate">{{ String(agentStore.allAgents.length) }}</div>
              </div>
              <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3 min-w-0">
                <div class="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-tertiary)] min-w-0">
                  <span class="material-symbols-outlined text-[14px] flex-shrink-0" style="fontVariationSettings: 'FILL' 1">bolt</span>
                  <span class="truncate">{{ t('settings.agents.summary.activeAgents') }}</span>
                </div>
                <div class="mt-2 text-lg font-semibold text-[var(--color-text-primary)] truncate">{{ String(agentStore.activeAgents.length) }}</div>
              </div>
              <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3 min-w-0 col-span-2 sm:col-span-1">
                <div class="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-tertiary)] min-w-0">
                  <span class="material-symbols-outlined text-[14px] flex-shrink-0" style="fontVariationSettings: 'FILL' 1">layers</span>
                  <span class="truncate">{{ t('settings.agents.summary.sources') }}</span>
                </div>
                <div class="mt-2 text-lg font-semibold text-[var(--color-text-primary)] truncate">{{ String(sourceCount) }}</div>
              </div>
            </div>
          </div>
        </section>

        <!-- Grouped agent sections -->
        <div :class="['grid gap-4', sourceCount >= 2 ? 'xl:grid-cols-2' : '']">
          <template v-for="source in AGENT_SOURCE_ORDER" :key="source">
            <section
              v-if="(groupedAgents[source] as typeof agentStore.allAgents)?.length"
              class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden min-w-0"
            >
              <!-- Section header -->
              <div class="flex items-start justify-between gap-3 px-5 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface-container-low)]">
                <div class="min-w-0">
                  <div class="flex items-center gap-2 mb-1 flex-wrap">
                    <span :class="['inline-flex h-7 w-7 items-center justify-center rounded-full', getAgentSourceAccentClass(source)]">
                      <span class="material-symbols-outlined text-[16px]" style="fontVariationSettings: 'FILL' 1">
                        {{ getAgentSourceIcon(source) }}
                      </span>
                    </span>
                    <h4 class="text-sm font-semibold text-[var(--color-text-primary)]">
                      {{ t(`settings.agents.source.${source}`) }}
                    </h4>
                    <span class="text-xs text-[var(--color-text-tertiary)]">
                      {{ (groupedAgents[source] as typeof agentStore.allAgents).length }}
                    </span>
                  </div>
                  <p class="text-xs leading-5 text-[var(--color-text-tertiary)]">
                    {{ t('settings.agents.groupHint', {
                      source: t(`settings.agents.source.${source}`),
                      count: String((groupedAgents[source] as typeof agentStore.allAgents).length),
                    }) }}
                  </p>
                </div>
              </div>

              <!-- Agent list -->
              <div class="flex flex-col p-2">
                <template v-for="agent in groupedAgents[source]" :key="`${agent.source}-${agent.agentType}`">
                  <button
                    @click="agentStore.selectAgent(agent, 'agents')"
                    class="group rounded-xl border border-transparent px-3 py-3 text-left transition-all hover:border-[var(--color-border-focus)] hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)]"
                  >
                    <div class="flex items-start gap-3">
                      <!-- Agent icon -->
                      <span
                        class="mt-0.5 flex-shrink-0 inline-flex items-center justify-center"
                        :style="{ color: getAgentDotColor(agent.color) }"
                      >
                        <span class="material-symbols-outlined text-[18px]" style="fontVariationSettings: 'FILL' 1">smart_toy</span>
                      </span>
                      <!-- Agent info -->
                      <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 flex-wrap">
                          <span class="text-sm font-bold text-[var(--color-text-primary)] break-all">
                            {{ agent.agentType }}
                          </span>
                          <!-- Model pill -->
                          <span
                            v-if="agent.modelDisplay"
                            class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]"
                          >
                            {{ agent.modelDisplay }}
                          </span>
                          <!-- Source pill -->
                          <span class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]">
                            {{ t(`settings.agents.source.${source}`) }}
                          </span>
                          <!-- Status pill -->
                          <span class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]">
                            {{ agent.isActive ? t('settings.agents.status.active') : t('settings.agents.status.available') }}
                          </span>
                          <!-- OverriddenBy pill -->
                          <span
                            v-if="agent.overriddenBy"
                            class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]"
                          >
                            {{ t('settings.agents.overriddenBy', {
                              source: t(`settings.agents.source.${agent.overriddenBy}`),
                            }) }}
                          </span>
                        </div>
                        <!-- Description -->
                        <div class="mt-1 text-xs leading-5 text-[var(--color-text-secondary)] break-words prose [&_p]:text-xs [&_p]:leading-5 [&_p]:text-[var(--color-text-secondary)] [&_p]:m-0">
                          {{ agent.description || t('settings.agents.noDescription') }}
                        </div>
                        <!-- Meta info -->
                        <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--color-text-tertiary)]">
                          <span>
                            {{ agent.tools && agent.tools.length > 0 ? t('settings.agents.toolCount', { count: String(agent.tools.length) }) : t('settings.agents.noTools') }}
                          </span>
                          <span v-if="agent.baseDir" class="break-all">{{ agent.baseDir }}</span>
                        </div>
                      </div>
                      <!-- Chevron -->
                      <span class="material-symbols-outlined text-[18px] text-[var(--color-text-tertiary)] opacity-60 transition-transform group-hover:translate-x-0.5 group-hover:opacity-100" style="fontVariationSettings: 'FILL' 1">chevron_right</span>
                    </div>
                  </button>
                </template>
              </div>
            </section>
          </template>
        </div>
      </div>
    </template>
  </div>
</template>
