<script setup lang="ts">
// v3.0 — AgentDetailView (Vue 3 SFC translation from React Settings.tsx lines 3943-4090)
// Agent detail page with header, description, detail stats, tools, and system prompt.

import { computed, ref, onMounted, watch } from 'vue'
import { useTranslation } from '../i18n'
import { getApiUrl } from '../api/client'

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
const editableModel = ref(props.agent.model || '')
const modelSaved = ref(false)
const modelSaving = ref(false)
const promptCopied = ref(false)

async function loadRouting() {
  try {
    const res = await fetch(getApiUrl('/api/settings/agent-routing'))
    if (res.ok) {
      const data = await res.json()
      const route = (data.agent_routing || {})[props.agent.agentType]
      if (route?.model) editableModel.value = route.model
      else editableModel.value = props.agent.model || ''
    }
  } catch { /* ignore */ }
}
onMounted(loadRouting)
watch(() => props.agent.agentType, loadRouting)

async function saveModel() {
  modelSaving.value = true
  try {
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
  } catch { /* ignore */ } finally {
    modelSaving.value = false
  }
}

async function copyPrompt() {
  if (!props.agent.systemPrompt) return
  try {
    await navigator.clipboard.writeText(props.agent.systemPrompt)
    promptCopied.value = true
    setTimeout(() => { promptCopied.value = false }, 1800)
  } catch { /* ignore */ }
}

// ─── Constants ───────────────────────────────────────────────
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

function getAgentDotColor(color?: string): string {
  return color && AGENT_COLORS[color] ? AGENT_COLORS[color] : 'var(--color-text-tertiary)'
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
      return 'bg-[var(--color-surface-container-high)] text-[var(--color-text-tertiary)]'
  }
}

const sourceLabel = computed(() => t(`settings.agents.source.${props.agent.source}`))
const toolCount = computed(() => props.agent.tools?.length ?? 0)
const defaultModelLabel = computed(() => props.agent.modelDisplay || props.agent.model || '—')

</script>

<template>
  <div class="flex h-full min-h-0 flex-col gap-5 min-w-0">
    <!-- Back -->
    <div>
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]"
        @click="emit('back')"
      >
        <span class="material-symbols-outlined text-[16px]" style="fontVariationSettings: 'FILL' 1">arrow_back</span>
        {{ t('settings.agents.backToList') }}
      </button>
    </div>

    <!-- Header card -->
    <section class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] overflow-hidden">
      <div class="grid gap-5 px-5 py-5 lg:grid-cols-[minmax(0,1.55fr)_minmax(300px,0.95fr)] lg:items-start">
        <div class="min-w-0">
          <div class="mb-2 text-[11px] font-semibold tracking-wide text-[var(--color-text-tertiary)]">
            {{ t('settings.agents.entryEyebrow') }}
          </div>
          <div class="mb-3 flex flex-wrap items-center gap-2">
            <span
              class="h-3 w-3 shrink-0 rounded-full ring-2 ring-[var(--color-surface)]"
              :style="{ backgroundColor: getAgentDotColor(props.agent.color) }"
            />
            <h3 class="break-all text-[22px] font-semibold leading-tight text-[var(--color-text-primary)]">
              {{ props.agent.agentType }}
            </h3>
            <span
              class="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-semibold"
              :class="getAgentSourceAccentClass(props.agent.source)"
            >
              {{ sourceLabel }}
            </span>
            <span
              v-if="props.agent.modelDisplay"
              class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold text-[var(--color-text-tertiary)]"
            >
              {{ props.agent.modelDisplay }}
            </span>
            <span
              class="rounded-full border px-2.5 py-1 text-[10px] font-semibold"
              :class="props.agent.isActive
                ? 'border-[var(--color-success)]/30 bg-[var(--color-success)]/10 text-[var(--color-success)]'
                : 'border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-tertiary)]'"
            >
              {{ props.agent.isActive ? t('settings.agents.status.active') : t('settings.agents.status.available') }}
            </span>
            <span
              v-if="props.agent.overriddenBy"
              class="rounded-full border border-[var(--color-warning)]/30 bg-[var(--color-warning)]/10 px-2.5 py-1 text-[10px] font-semibold text-[var(--color-warning)]"
            >
              {{ t('settings.agents.overriddenByShort', {
                source: t(`settings.agents.source.${props.agent.overriddenBy}`),
              }) }}
            </span>
          </div>

          <p class="max-w-4xl text-sm leading-6 text-[var(--color-text-secondary)]">
            {{ props.agent.description || t('settings.agents.noDescription') }}
          </p>

          <div class="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-[var(--color-text-tertiary)]">
            <span class="inline-flex items-center gap-1">
              <span class="material-symbols-outlined text-[14px]">build</span>
              {{ toolCount > 0 ? t('settings.agents.toolCount', { count: String(toolCount) }) : t('settings.agents.noTools') }}
            </span>
            <span v-if="props.agent.baseDir" class="inline-flex min-w-0 items-center gap-1 break-all">
              <span class="material-symbols-outlined shrink-0 text-[14px]">folder</span>
              {{ props.agent.baseDir }}
            </span>
          </div>
        </div>

        <!-- Stat grid -->
        <div class="grid grid-cols-2 gap-3">
          <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-3">
            <div class="flex items-center gap-1.5 text-[11px] text-[var(--color-text-tertiary)]">
              <span class="material-symbols-outlined text-[14px]" style="fontVariationSettings: 'FILL' 1">layers</span>
              {{ t('settings.agents.summary.source') }}
            </div>
            <div class="mt-2 truncate text-base font-semibold text-[var(--color-text-primary)]">{{ sourceLabel }}</div>
          </div>
          <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-3">
            <div class="flex items-center gap-1.5 text-[11px] text-[var(--color-text-tertiary)]">
              <span class="material-symbols-outlined text-[14px]" style="fontVariationSettings: 'FILL' 1">build</span>
              {{ t('settings.agents.summary.tools') }}
            </div>
            <div class="mt-2 text-base font-semibold text-[var(--color-text-primary)]">{{ toolCount }}</div>
          </div>
          <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-3">
            <div class="flex items-center gap-1.5 text-[11px] text-[var(--color-text-tertiary)]">
              <span class="material-symbols-outlined text-[14px]" style="fontVariationSettings: 'FILL' 1">bolt</span>
              {{ t('settings.agents.summary.status') }}
            </div>
            <div class="mt-2 text-base font-semibold text-[var(--color-text-primary)]">
              {{ props.agent.isActive ? t('settings.agents.status.active') : t('settings.agents.status.available') }}
            </div>
          </div>
          <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-3">
            <div class="flex items-center gap-1.5 text-[11px] text-[var(--color-text-tertiary)]">
              <span class="material-symbols-outlined text-[14px]" style="fontVariationSettings: 'FILL' 1">psychology</span>
              {{ t('settings.agents.summary.model') }}
            </div>
            <div class="mt-2 truncate text-sm font-semibold text-[var(--color-text-primary)]" :title="defaultModelLabel">
              {{ defaultModelLabel }}
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Model routing card (tertiary option) -->
    <section class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
      <div class="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-5 py-4">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-[18px] text-[var(--color-brand)]" style="fontVariationSettings: 'FILL' 1">route</span>
            <h4 class="text-sm font-semibold text-[var(--color-text-primary)]">{{ t('settings.agents.modelRouting') }}</h4>
          </div>
          <p class="mt-1 max-w-2xl text-xs leading-5 text-[var(--color-text-tertiary)]">
            {{ t('settings.agents.modelRoutingHint') }}
          </p>
        </div>
      </div>
      <div class="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-end">
        <div class="min-w-0 flex-1">
          <label class="mb-1.5 block text-[11px] font-medium text-[var(--color-text-secondary)]">
            {{ t('settings.agents.summary.model') }}
          </label>
          <input
            v-model="editableModel"
            type="text"
            class="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] px-3 py-2.5 text-sm text-[var(--color-text-primary)] outline-none transition-colors placeholder:text-[var(--color-text-tertiary)] focus:border-[var(--color-brand)]"
            :placeholder="t('settings.agents.modelPlaceholder')"
          />
          <p class="mt-1.5 text-[11px] text-[var(--color-text-tertiary)]">
            {{ t('settings.agents.modelDefault', { model: defaultModelLabel }) }}
          </p>
        </div>
        <button
          type="button"
          class="inline-flex h-10 shrink-0 items-center justify-center gap-1.5 rounded-xl bg-[var(--color-brand)] px-4 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          :disabled="modelSaving"
          @click="saveModel"
        >
          <span v-if="modelSaved" class="material-symbols-outlined text-[16px]">check</span>
          <span v-else-if="modelSaving" class="material-symbols-outlined animate-spin text-[16px]">progress_activity</span>
          <span v-else class="material-symbols-outlined text-[16px]">save</span>
          {{ modelSaved ? t('settings.agents.saved') : modelSaving ? t('settings.agents.saving') : t('settings.agents.saveRouting') }}
        </button>
      </div>
    </section>

    <!-- Tools -->
    <section
      v-if="props.agent.tools && props.agent.tools.length > 0"
      class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-4"
    >
      <div class="mb-3 flex items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-[18px] text-[var(--color-text-tertiary)]" style="fontVariationSettings: 'FILL' 1">build</span>
          <h4 class="text-sm font-semibold text-[var(--color-text-primary)]">{{ t('settings.agents.tools') }}</h4>
          <span class="rounded-full bg-[var(--color-surface-container-high)] px-2 py-0.5 text-[11px] tabular-nums text-[var(--color-text-tertiary)]">
            {{ toolCount }}
          </span>
        </div>
      </div>
      <div class="flex flex-wrap gap-2">
        <span
          v-for="tool in props.agent.tools"
          :key="tool"
          class="inline-flex items-center rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-2.5 py-1 font-mono text-[11px] font-medium text-[var(--color-text-secondary)]"
        >
          {{ tool }}
        </span>
      </div>
    </section>

    <!-- System prompt -->
    <section class="flex min-h-[280px] min-w-0 flex-1 overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)]">
      <div class="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-4 py-3">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <span class="material-symbols-outlined text-[16px] text-[var(--color-text-tertiary)]">article</span>
              <span class="text-sm font-semibold text-[var(--color-text-primary)]">{{ t('settings.agents.systemPrompt') }}</span>
            </div>
            <div class="mt-1 truncate text-[11px] text-[var(--color-text-tertiary)]">
              {{ props.agent.baseDir || sourceLabel }} · {{ t('settings.agents.promptHint') }}
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button
              v-if="props.agent.systemPrompt"
              type="button"
              class="inline-flex h-8 items-center gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 text-[11px] font-medium text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)]"
              @click="copyPrompt"
            >
              <span class="material-symbols-outlined text-[14px]">{{ promptCopied ? 'check' : 'content_copy' }}</span>
              {{ promptCopied ? t('settings.agents.copied') : t('settings.agents.copyPrompt') }}
            </button>
          </div>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto bg-[var(--color-surface-container-lowest)]">
          <div v-if="props.agent.systemPrompt" class="px-6 py-5 lg:px-8">
            <pre class="mx-auto max-w-[78ch] whitespace-pre-wrap break-words font-mono text-[12.5px] leading-6 text-[var(--color-text-secondary)]">{{ props.agent.systemPrompt }}</pre>
          </div>
          <div v-else class="px-6 py-12 text-center">
            <span class="material-symbols-outlined mb-2 block text-[36px] text-[var(--color-text-tertiary)]" style="fontVariationSettings: 'FILL' 1">article</span>
            <p class="text-sm text-[var(--color-text-tertiary)]">{{ t('settings.agents.noSystemPrompt') }}</p>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
