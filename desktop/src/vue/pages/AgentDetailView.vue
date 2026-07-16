<script setup lang="ts">
// v3.0 — AgentDetailView (Vue 3 SFC translation from React Settings.tsx lines 3943-4090)
// Agent detail page with header, description, detail stats, tools, and system prompt.

import { computed, ref, onMounted, watch } from 'vue'
import { useTranslation } from '../i18n'
import { getApiUrl } from '../../api/client'

// ─── Props ───────────────────────────────────────────────────
interface Props {
  agent: {
    agentType: string
    description?: string
    model?: string
    modelDisplay?: string
    tools?: string[]
    systemPrompt?: string
    color?: string
    source: string
    baseDir?: string
    overriddenBy?: string
    isActive: boolean
  }
}

const props = defineProps<Props>()

interface Emits {
  (e: 'back'): void
}
const emit = defineEmits<Emits>()

const t = useTranslation()

// ─── Per-agent model routing ─────────────────────────────────
// Each agent can override its model in deep mode. The override is stored
// in settings.agent_routing { agentId: { model } } and read by build_engine.
const editableModel = ref(props.agent.model || '')
const modelSaved = ref(false)
const modelSaving = ref(false)

async function loadRouting() {
  try {
    const res = await fetch(getApiUrl('/api/settings/agent-routing'))
    if (res.ok) {
      const data = await res.json()
      const route = (data.agent_routing || {})[props.agent.agentType]
      if (route?.model) editableModel.value = route.model
    }
  } catch {}
}
onMounted(loadRouting)
watch(() => props.agent.agentType, loadRouting)

async function saveModel() {
  modelSaving.value = true
  try {
    // Read current routing, update this agent, PUT back.
    const getRes = await fetch(getApiUrl('/api/settings/agent-routing'))
    const routing = getRes.ok ? (await getRes.json()).agent_routing || {} : {}
    routing[props.agent.agentType] = { ...(routing[props.agent.agentType] || {}), model: editableModel.value }
    await fetch(getApiUrl('/api/settings/agent-routing'), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(routing),
    })
    modelSaved.value = true
    setTimeout(() => { modelSaved.value = false }, 2000)
  } catch {} finally {
    modelSaving.value = false
  }
}

// ─── Constants (from React lines 3705-3714) ─────────────────
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

// ─── Helpers (from React lines 4092-4113) ────────────────────
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

// ─── Computed ───────────────────────────────────────────────
const sourceLabel = computed(() => t(`settings.agents.source.${props.agent.source}`))

</script>

<template>
  <div class="flex h-full min-h-0 flex-col gap-4 min-w-0">
    <!-- Back button -->
    <div>
      <button
        @click="emit('back')"
        class="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]"
      >
        <span class="material-symbols-outlined text-[16px]" style="fontVariationSettings: 'FILL' 1">arrow_back</span>
        {{ t('settings.agents.backToList') }}
      </button>
    </div>

    <!-- Header section -->
    <section class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] overflow-hidden">
      <div class="grid gap-4 px-5 py-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.9fr)] lg:items-start">
        <div class="min-w-0">
          <div class="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--color-text-tertiary)] mb-2">
            {{ t('settings.agents.entryEyebrow') }}
          </div>
          <div class="flex flex-wrap items-center gap-2 mb-2">
            <!-- Color dot -->
            <span
              class="h-3 w-3 rounded-full flex-shrink-0"
              :style="{ backgroundColor: getAgentDotColor(props.agent.color) }"
            />
            <!-- Agent name -->
            <h3 class="text-[22px] font-semibold leading-tight text-[var(--color-text-primary)] break-all">
              {{ props.agent.agentType }}
            </h3>
            <!-- Source pill -->
            <span class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]">
              {{ sourceLabel }}
            </span>
            <!-- Model pill -->
            <span
              v-if="props.agent.modelDisplay"
              class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]"
            >
              {{ props.agent.modelDisplay }}
            </span>
            <!-- Status pill -->
            <span class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]">
              {{ props.agent.isActive ? t('settings.agents.status.active') : t('settings.agents.status.available') }}
            </span>
            <!-- OverriddenBy pill -->
            <span
              v-if="props.agent.overriddenBy"
              class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]"
            >
              {{ t('settings.agents.overriddenByShort', {
                source: t(`settings.agents.source.${props.agent.overriddenBy}`),
              }) }}
            </span>
          </div>
          <!-- Description -->
          <div class="max-w-4xl text-sm leading-6 text-[var(--color-text-secondary)]">
            <div class="prose text-sm leading-6 text-[var(--color-text-secondary)] [&_p]:m-0 [&_p:not(:first-child)]:mt-2 [&_code]:bg-[var(--color-surface-container-low)] [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-xs [&_pre]:bg-[var(--color-surface-container-lowest)] [&_pre]:rounded-lg [&_pre]:p-3 [&_pre]:text-xs [&_pre]:overflow-x-auto [&_a]:text-[var(--color-brand)] [&_a]:underline">
              {{ props.agent.description || t('settings.agents.noDescription') }}
            </div>
          </div>
          <!-- Meta info -->
          <div class="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-[var(--color-text-tertiary)]">
            <span>
              {{ props.agent.tools && props.agent.tools.length > 0 ? t('settings.agents.toolCount', { count: String(props.agent.tools.length) }) : t('settings.agents.noTools') }}
            </span>
            <span v-if="props.agent.baseDir" class="break-all">{{ props.agent.baseDir }}</span>
          </div>
        </div>

        <!-- Detail stats -->
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-2">
          <!-- Source -->
          <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3">
            <div class="flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-[var(--color-text-tertiary)]">
              <span class="material-symbols-outlined text-[14px]" style="fontVariationSettings: 'FILL' 1">layers</span>
              <span>{{ t('settings.agents.summary.source') }}</span>
            </div>
            <div class="mt-2 text-base font-semibold text-[var(--color-text-primary)] break-all">{{ sourceLabel }}</div>
          </div>
          <!-- Model — editable so the user can route this agent to a
               different model in deep mode (e.g. planner→strong model,
               researcher→cheap model). Saved to agent_routing. -->
          <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3">
            <div class="flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-[var(--color-text-tertiary)]">
              <span class="material-symbols-outlined text-[14px]" style="fontVariationSettings: 'FILL' 1">psychology</span>
              <span>{{ t('settings.agents.summary.model') }}</span>
            </div>
            <input
              v-model="editableModel"
              type="text"
              class="mt-2 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] px-2.5 py-1.5 text-sm text-[var(--color-text-primary)] focus:border-[var(--color-brand)] focus:outline-none"
              :placeholder="props.agent.modelDisplay || '模型名'"
            />
            <div class="mt-1.5 flex items-center justify-between">
              <span class="text-[11px] text-[var(--color-text-tertiary)]">默认: {{ props.agent.modelDisplay || '—' }}</span>
              <button
                type="button"
                @click="saveModel"
                :disabled="modelSaving"
                class="rounded-md bg-[var(--color-brand)] px-2.5 py-1 text-[11px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              >{{ modelSaved ? '✓ 已保存' : modelSaving ? '保存中…' : '保存路由' }}</button>
            </div>
          </div>
          <!-- Tools -->
          <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3">
            <div class="flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-[var(--color-text-tertiary)]">
              <span class="material-symbols-outlined text-[14px]" style="fontVariationSettings: 'FILL' 1">build</span>
              <span>{{ t('settings.agents.summary.tools') }}</span>
            </div>
            <div class="mt-2 text-base font-semibold text-[var(--color-text-primary)] break-all">{{ String(props.agent.tools?.length ?? 0) }}</div>
          </div>
          <!-- Status -->
          <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3">
            <div class="flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-[var(--color-text-tertiary)]">
              <span class="material-symbols-outlined text-[14px]" style="fontVariationSettings: 'FILL' 1">bolt</span>
              <span>{{ t('settings.agents.summary.status') }}</span>
            </div>
            <div class="mt-2 text-base font-semibold text-[var(--color-text-primary)] break-all">{{ props.agent.isActive ? t('settings.agents.status.active') : t('settings.agents.status.available') }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- Tools section -->
    <section
      v-if="props.agent.tools && props.agent.tools.length > 0"
      class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-4"
    >
      <div class="flex items-center gap-2 mb-3">
        <span class="material-symbols-outlined text-[18px] text-[var(--color-text-tertiary)]" style="fontVariationSettings: 'FILL' 1">build</span>
        <h4 class="text-sm font-semibold text-[var(--color-text-primary)]">
          {{ t('settings.agents.tools') }}
        </h4>
      </div>
      <div class="flex flex-wrap gap-2">
        <span
          v-for="tool in props.agent.tools"
          :key="tool"
          class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]"
        >
          {{ tool }}
        </span>
      </div>
    </section>

    <!-- System prompt section -->
    <section class="flex flex-1 min-h-0 min-w-0 overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)]">
      <div class="flex min-w-0 flex-1 flex-col overflow-hidden">
        <!-- Header -->
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-4 py-3">
          <div class="min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="text-xs font-mono text-[var(--color-text-secondary)] break-all">
                {{ props.agent.baseDir || sourceLabel }}
              </span>
            </div>
            <div class="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
              {{ t('settings.agents.promptHint') }}
            </div>
          </div>
          <div class="flex items-center gap-2">
            <span class="rounded-full bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)] border border-[var(--color-border)]">
              {{ t('settings.agents.systemPrompt') }}
            </span>
          </div>
        </div>

        <!-- Content -->
        <div class="min-h-0 flex-1 overflow-y-auto bg-[var(--color-surface-container-lowest)]">
          <div v-if="props.agent.systemPrompt" class="px-6 py-5 lg:px-8">
            <div class="mx-auto max-w-[72ch] prose prose-sm text-[var(--color-text-secondary)] [&_p]:m-0 [&_p:not(:first-child)]:mt-2 [&_code]:bg-[var(--color-surface-container-low)] [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-xs [&_pre]:bg-[var(--color-surface-container-lowest)] [&_pre]:rounded-lg [&_pre]:p-3 [&_pre]:text-xs [&_pre]:overflow-x-auto [&_a]:text-[var(--color-brand)] [&_a]:underline">
              {{ props.agent.systemPrompt }}
            </div>
          </div>
          <div v-else class="px-6 py-10 text-center">
            <span class="material-symbols-outlined text-[32px] text-[var(--color-text-tertiary)] mb-2 block" style="fontVariationSettings: 'FILL' 1">article</span>
            <p class="text-sm text-[var(--color-text-tertiary)]">
              {{ t('settings.agents.noSystemPrompt') }}
            </p>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
