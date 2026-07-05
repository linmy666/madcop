<!-- v3.0 — PluginList (Vue 3 SFC)
     Full translation of React PluginList.tsx (580 lines) → Vue 3 Composition API SFC.

     Rules applied:
     - className → class (all Tailwind classes kept VERBATIM)
     - All --color-* CSS variables kept VERBATIM
     - useState → ref() ; useEffect → onMounted/watch ; useMemo → computed
     - lucide-react icons → <span class="material-symbols-outlined">icon_name</span>
     - createPortal → <teleport to="body"> (not used; ConfirmDialog handles it)
     - Self-contained leaf: uses usePluginStore(), useSessionStore(), useUIStore(), useTranslation()
       (matches parent Settings.vue render pattern: <PluginList /> no props)
     - i18n key format: settings.plugins.*
     - Sub-components (SummaryCard, StatusPill, ScopePill) rendered inline via template helpers
       and <template> v-for patterns, matching DiagnosticsSettings.vue approach
     - Pure helpers (canMutatePlugin, formatPluginNames) kept as standalone functions
-->

<script setup lang="ts">
// ─── Imports ────────────────────────────────────────────────────────────────

import {
  ref,
  computed,
  onMounted,
  watch,
} from 'vue'
import type { PluginSummary } from '../../types/plugin'
import { useTranslation } from '../i18n'
import { usePluginStore } from '../stores/pluginStore'
import { useSessionStore } from '../stores/sessionStore'
import { useUIStore } from '../stores/uiStore'
import Button from '../components/shared/Button.vue'
import ConfirmDialog from '../components/shared/ConfirmDialog.vue'
import SummaryCard from '../components/shared/SummaryCard.vue'

// ─── Types ──────────────────────────────────────────────────────────────────

type PluginBucket = 'attention' | 'enabled' | 'disabled'
type BatchAction = 'enable' | 'disable'

// ─── Pure helpers ───────────────────────────────────────────────────────────

function canMutatePlugin(plugin: PluginSummary): boolean {
  return plugin.scope !== 'managed' && plugin.scope !== 'builtin'
}

function formatPluginNames(plugins: PluginSummary[]): string {
  return plugins.map((plugin) => plugin.name).join(', ')
}

// ─── Reactive state ─────────────────────────────────────────────────────────

const t = useTranslation()
const pluginStore = usePluginStore()
const sessionStore = useSessionStore()
const addToast = useUIStore((s) => s.addToast)

// Local state (mirrors React useState)
const selectedPluginIds = ref<Set<string>>(new Set())
const confirmBatchAction = ref<BatchAction | null>(null)

// ─── Computed (mirrors React useMemo) ───────────────────────────────────────

const plugins = computed(() => pluginStore.plugins)
const marketplaces = computed(() => pluginStore.marketplaces)
const summary = computed(() => pluginStore.summary)
const lastReloadSummary = computed(() => pluginStore.lastReloadSummary)
const isLoading = computed(() => pluginStore.isLoading)
const isApplying = computed(() => pluginStore.isApplying)
const error = computed(() => pluginStore.error)

const sessions = computed(() => sessionStore.sessions)
const activeSessionId = computed(() => sessionStore.activeSessionId)
const activeSession = computed(() => sessions.value.find((session) => session.id === activeSessionId.value))
const currentWorkDir = computed(() => activeSession.value?.workDir ?? undefined)

// Grouped plugins: attention / enabled / disabled
const grouped = computed(() => {
  const buckets: Record<PluginBucket, PluginSummary[]> = {
    attention: [],
    enabled: [],
    disabled: [],
  }
  for (const plugin of plugins.value) {
    if (plugin.hasErrors) {
      buckets.attention.push(plugin)
    } else if (plugin.enabled) {
      buckets.enabled.push(plugin)
    } else {
      buckets.disabled.push(plugin)
    }
  }
  return buckets
})

// Selected plugins (only mutable ones)
const selectedPlugins = computed(() =>
  plugins.value.filter((plugin) => selectedPluginIds.value.has(plugin.id) && canMutatePlugin(plugin)),
)

const enableCandidates = computed(() => selectedPlugins.value.filter((plugin) => !plugin.enabled))
const disableCandidates = computed(() => selectedPlugins.value.filter((plugin) => plugin.enabled))

const confirmBatchPlugins = computed(() =>
  confirmBatchAction.value === 'enable' ? enableCandidates.value : disableCandidates.value,
)
const confirmBatchNames = computed(() => formatPluginNames(confirmBatchPlugins.value))

// ─── Lifecycle (mirrors React useEffect) ────────────────────────────────────

onMounted(() => {
  void pluginStore.fetchPlugins(currentWorkDir.value)
})

// Re-fetch when currentWorkDir changes (watch mirrors useEffect dep)
watch(currentWorkDir, (newDir) => {
  void pluginStore.fetchPlugins(newDir)
})

// Sync selectedPluginIds — remove ids no longer selectable (mirrors useEffect)
watch(plugins, () => {
  const selectableIds = new Set(plugins.value.filter(canMutatePlugin).map((p) => p.id))
  const next = new Set([...selectedPluginIds.value].filter((id) => selectableIds.has(id)))
  if (next.size !== selectedPluginIds.value.size) {
    selectedPluginIds.value = next
  }
})

// ─── Actions ────────────────────────────────────────────────────────────────

const handleReload = async () => {
  try {
    const reloadSummary = await pluginStore.reloadPlugins(currentWorkDir.value, activeSessionId.value || undefined)
    addToast({
      type: reloadSummary.errors > 0 ? 'warning' : 'success',
      message: t('settings.plugins.reloadToast', {
        enabled: String(reloadSummary.enabled),
        skills: String(reloadSummary.skills),
        errors: String(reloadSummary.errors),
      }),
    })
  } catch (err: unknown) {
    addToast({
      type: 'error',
      message: err instanceof Error ? err.message : String(err),
    })
  }
}

const togglePluginSelection = (pluginId: string, selected: boolean) => {
  const next = new Set(selectedPluginIds.value)
  if (selected) {
    next.add(pluginId)
  } else {
    next.delete(pluginId)
  }
  selectedPluginIds.value = next
}

const clearSelection = () => {
  selectedPluginIds.value = new Set()
}

const toActionTargets = (items: PluginSummary[]) =>
  items.map((plugin) => ({ id: plugin.id, scope: plugin.scope }))

const handleBatchConfirm = async () => {
  if (!confirmBatchAction.value) return

  const action = confirmBatchAction.value
  const targets = action === 'enable' ? enableCandidates.value : disableCandidates.value
  if (targets.length === 0) {
    confirmBatchAction.value = null
    return
  }

  try {
    const changed = action === 'enable'
      ? await pluginStore.bulkEnablePlugins(toActionTargets(targets), currentWorkDir.value, activeSessionId.value || undefined)
      : await pluginStore.bulkDisablePlugins(toActionTargets(targets), currentWorkDir.value, activeSessionId.value || undefined)
    // Deselect the changed plugins
    const next = new Set(selectedPluginIds.value)
    for (const plugin of targets) {
      next.delete(plugin.id)
    }
    selectedPluginIds.value = next
    confirmBatchAction.value = null
    addToast({
      type: 'success',
      message: t(action === 'enable' ? 'settings.plugins.bulkEnableToast' : 'settings.plugins.bulkDisableToast', {
        count: String(changed),
      }),
    })
  } catch (err: unknown) {
    confirmBatchAction.value = null
    addToast({
      type: 'error',
      message: err instanceof Error ? err.message : String(err),
    })
  }
}

// ─── StatusPill / ScopePill helpers ─────────────────────────────────────────

const statusPillClasses = (plugin: PluginSummary): string => {
  if (plugin.hasErrors) {
    return 'rounded-full bg-[var(--color-error)]/12 px-2 py-0.5 text-[10px] font-medium text-[var(--color-error)]'
  }
  if (plugin.enabled) {
    return 'rounded-full bg-[var(--color-success-container)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-success)]'
  }
  return 'rounded-full bg-[var(--color-surface-container-high)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-text-tertiary)]'
}

const statusPillText = (plugin: PluginSummary): string => {
  if (plugin.hasErrors) return t('settings.plugins.status.attention')
  return plugin.enabled ? t('settings.plugins.status.enabled') : t('settings.plugins.status.disabled')
}

const scopePillText = (scope: PluginSummary['scope']): string => {
  return t(`settings.plugins.scope.${scope}`)
}

// ─── RenderGroup helpers (used in template) ─────────────────────────────────

function getGroupTitleKey(bucket: PluginBucket): string {
  if (bucket === 'attention') return 'settings.plugins.group.attention'
  if (bucket === 'enabled') return 'settings.plugins.group.enabled'
  return 'settings.plugins.group.disabled'
}
</script>

<template>
  <!-- Loading -->
  <div v-if="isLoading" class="flex justify-center py-12">
    <div class="animate-spin w-5 h-5 border-2 border-[var(--color-brand)] border-t-transparent rounded-full" />
  </div>

  <!-- Error -->
  <div v-else-if="error" class="text-sm text-[var(--color-error)] py-4">
    {{ error }}
  </div>

  <!-- Empty state -->
  <div
    v-else-if="plugins.length === 0"
    class="text-center py-12 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-6"
  >
    <span class="material-symbols-outlined text-[40px] text-[var(--color-text-tertiary)] mb-2 block">
      extension
    </span>
    <p class="text-sm text-[var(--color-text-tertiary)]">
      {{ t('settings.plugins.empty') }}
    </p>
    <p class="text-xs text-[var(--color-text-tertiary)] mt-1">
      {{ t('settings.plugins.emptyHint') }}
    </p>
  </div>

  <!-- Main content -->
  <div v-else class="flex flex-col gap-6 min-w-0">
    <!-- Header section -->
    <section class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] overflow-hidden">
      <div class="flex flex-col gap-4 px-5 py-5 min-w-0">
        <div class="flex flex-col gap-4 min-w-0 xl:flex-row xl:items-start xl:justify-between">
          <div class="min-w-0 max-w-4xl">
            <div class="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--color-text-tertiary)] mb-2">
              {{ t('settings.plugins.browserEyebrow') }}
            </div>
            <div class="flex items-center gap-3 mb-2">
              <span class="material-symbols-outlined text-[22px] text-[var(--color-brand)]">
                extension
              </span>
              <h3 class="text-lg font-semibold text-[var(--color-text-primary)]">
                {{ t('settings.plugins.browserTitle') }}
              </h3>
            </div>
            <p class="text-sm leading-6 text-[var(--color-text-secondary)]">
              {{ t('settings.plugins.browserDescription') }}
            </p>
          </div>

          <div class="flex flex-wrap gap-2 xl:justify-end">
            <Button
              variant="secondary"
              size="sm"
              class="min-h-9 flex-1 sm:flex-none"
              @click="pluginStore.fetchPlugins(currentWorkDir)"
            >
              <span class="material-symbols-outlined text-[16px]">refresh</span>
              {{ t('settings.plugins.refresh') }}
            </Button>
            <Button
              size="sm"
              class="min-h-9 flex-1 sm:flex-none"
              @click="handleReload"
              :loading="isApplying"
            >
              <span class="material-symbols-outlined text-[16px]">sync</span>
              {{ t('settings.plugins.apply') }}
            </Button>
          </div>
        </div>

        <div class="grid min-w-0 grid-cols-2 gap-2 md:grid-cols-4">
          <SummaryCard
            :label="t('settings.plugins.summary.total')"
            :value="String(summary?.total ?? plugins.length)"
            icon="extension"
          />
          <SummaryCard
            :label="t('settings.plugins.summary.enabled')"
            :value="String(summary?.enabled ?? plugins.filter(p => p.enabled).length)"
            icon="check_circle"
          />
          <SummaryCard
            :label="t('settings.plugins.summary.attention')"
            :value="String(grouped.attention.length)"
            icon="warning"
          />
          <SummaryCard
            :label="t('settings.plugins.summary.marketplaces')"
            :value="String(summary?.marketplaceCount ?? marketplaces.length)"
            icon="storefront"
          />
        </div>

        <p v-if="lastReloadSummary" class="text-xs text-[var(--color-text-tertiary)]">
          {{ t('settings.plugins.lastReload', {
            enabled: String(lastReloadSummary.enabled),
            skills: String(lastReloadSummary.skills),
            errors: String(lastReloadSummary.errors),
          }) }}
        </p>
      </div>

      <!-- Selection bar -->
      <div class="flex flex-col gap-3 border-t border-[var(--color-border)] px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div class="flex min-w-0 items-center gap-2 text-xs text-[var(--color-text-secondary)]">
          <span class="material-symbols-outlined text-[16px] text-[var(--color-text-tertiary)]">
            checklist
          </span>
          <span class="font-medium text-[var(--color-text-primary)]">
            {{ t('settings.plugins.selectionCount', { count: String(selectedPlugins.length) }) }}
          </span>
          <button
            v-if="selectedPlugins.length > 0"
            type="button"
            @click="clearSelection"
            class="rounded-md px-2 py-1 text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]"
          >
            {{ t('settings.plugins.clearSelection') }}
          </button>
        </div>
        <div class="flex flex-wrap gap-2 sm:justify-end">
          <Button
            size="sm"
            :disabled="enableCandidates.length === 0 || isApplying"
            @click="confirmBatchAction = 'enable'"
          >
            <span class="material-symbols-outlined text-[16px]" aria-hidden="true">toggle_on</span>
            {{ t('settings.plugins.enableSelected') }}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            :disabled="disableCandidates.length === 0 || isApplying"
            @click="confirmBatchAction = 'disable'"
          >
            <span class="material-symbols-outlined text-[16px]" aria-hidden="true">toggle_off</span>
            {{ t('settings.plugins.disableSelected') }}
          </Button>
        </div>
      </div>
    </section>

    <!-- Marketplaces -->
    <section
      v-if="marketplaces.length > 0"
      class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden"
    >
      <div class="px-5 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface-container-low)]">
        <h4 class="text-sm font-semibold text-[var(--color-text-primary)]">
          {{ t('settings.plugins.marketplacesTitle') }}
        </h4>
        <p class="text-xs text-[var(--color-text-tertiary)] mt-1">
          {{ t('settings.plugins.marketplacesHint') }}
        </p>
      </div>
      <div class="grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="marketplace in marketplaces"
          :key="marketplace.name"
          class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-4 py-3"
        >
          <div class="flex items-center gap-2">
            <span class="text-sm font-semibold text-[var(--color-text-primary)]">
              {{ marketplace.name }}
            </span>
            <span
              :class="[
                'rounded-full px-2 py-0.5 text-[10px] font-medium',
                marketplace.autoUpdate
                  ? 'bg-[var(--color-success-container)] text-[var(--color-success)]'
                  : 'bg-[var(--color-surface-container-high)] text-[var(--color-text-tertiary)]',
              ]"
            >
              {{ marketplace.autoUpdate
                ? t('settings.plugins.marketplaceAutoUpdateOn')
                : t('settings.plugins.marketplaceAutoUpdateOff') }}
            </span>
          </div>
          <div class="mt-2 text-xs leading-5 text-[var(--color-text-secondary)] break-words">
            {{ marketplace.source }}
          </div>
          <div class="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-[var(--color-text-tertiary)]">
            <span>
              {{ t('settings.plugins.marketplaceInstalledCount', { count: String(marketplace.installedCount) }) }}
            </span>
            <span v-if="marketplace.lastUpdated">
              {{ t('settings.plugins.marketplaceUpdatedAt', { value: new Date(marketplace.lastUpdated).toLocaleString() }) }}
            </span>
          </div>
        </div>
      </div>
    </section>

    <!-- Plugin Groups: attention / enabled / disabled -->
    <template
      v-for="({ bucket, items }) in [
        { bucket: 'attention', items: grouped.attention },
        { bucket: 'enabled', items: grouped.enabled },
        { bucket: 'disabled', items: grouped.disabled },
      ]"
      :key="bucket"
    >
      <section
        v-if="items.length > 0"
        class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden"
      >
        <div class="flex items-start justify-between gap-3 px-5 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface-container-low)]">
          <div class="min-w-0">
            <h4 class="text-sm font-semibold text-[var(--color-text-primary)]">
              {{ t(getGroupTitleKey(bucket)) }}
            </h4>
            <p class="text-xs leading-5 text-[var(--color-text-tertiary)] mt-1">
              {{ t('settings.plugins.groupHint', { count: String(items.length) }) }}
            </p>
          </div>
          <span class="text-xs text-[var(--color-text-tertiary)]">{{ items.length }}</span>
        </div>

        <div class="flex flex-col p-2">
          <div
            v-for="plugin in items"
            :key="plugin.id"
            :class="[
              'group rounded-xl border px-3 py-3 transition-all hover:border-[var(--color-border-focus)] hover:bg-[var(--color-surface-hover)]',
              selectedPluginIds.has(plugin.id)
                ? 'border-[var(--color-brand)]/45 bg-[var(--color-surface-selected)]'
                : 'border-transparent',
            ]"
          >
            <div class="flex items-start gap-3">
              <!-- Checkbox or placeholder -->
              <label
                v-if="canMutatePlugin(plugin)"
                class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-container-high)]"
              >
                <input
                  type="checkbox"
                  :aria-label="t('settings.plugins.selectPlugin', { name: plugin.name })"
                  :checked="selectedPluginIds.has(plugin.id)"
                  @change="togglePluginSelection(plugin.id, ($event.target as HTMLInputElement).checked)"
                  class="h-4 w-4 rounded border-[var(--color-border)] accent-[var(--color-brand)]"
                />
              </label>
              <span v-else class="mt-0.5 h-6 w-6 shrink-0" aria-hidden="true" />

              <!-- Plugin row button -->
              <button
                type="button"
                @click="pluginStore.fetchPluginDetail(plugin.id, currentWorkDir)"
                class="flex min-w-0 flex-1 items-start gap-3 rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)]"
              >
                <span class="mt-0.5 material-symbols-outlined text-[18px] text-[var(--color-text-tertiary)]">
                  {{ plugin.hasErrors ? 'warning' : plugin.enabled ? 'extension' : 'extension_off' }}
                </span>
                <div class="flex-1 min-w-0">
                  <!-- Name + pills row -->
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-sm font-semibold text-[var(--color-text-primary)] break-all">
                      {{ plugin.name }}
                    </span>
                    <span :class="statusPillClasses(plugin)">
                      {{ statusPillText(plugin) }}
                    </span>
                    <span class="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-text-tertiary)]">
                      {{ scopePillText(plugin.scope) }}
                    </span>
                    <span
                      v-if="plugin.version"
                      class="rounded-full bg-[var(--color-surface-container-high)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-text-tertiary)]"
                    >
                      v{{ plugin.version }}
                    </span>
                  </div>

                  <!-- Description -->
                  <p class="mt-1 text-xs leading-5 text-[var(--color-text-secondary)] break-words">
                    {{ plugin.description || t('settings.plugins.noDescription') }}
                  </p>

                  <!-- Meta row -->
                  <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--color-text-tertiary)]">
                    <span>{{ plugin.marketplace }}</span>
                    <span v-if="plugin.componentCounts.skills > 0">
                      {{ t('settings.plugins.capability.skills', { count: String(plugin.componentCounts.skills) }) }}
                    </span>
                    <span v-if="plugin.componentCounts.agents > 0">
                      {{ t('settings.plugins.capability.agents', { count: String(plugin.componentCounts.agents) }) }}
                    </span>
                    <span v-if="plugin.componentCounts.mcpServers > 0">
                      {{ t('settings.plugins.capability.mcpServers', { count: String(plugin.componentCounts.mcpServers) }) }}
                    </span>
                    <span
                      v-if="plugin.errors.length > 0"
                      class="text-[var(--color-error)]"
                    >
                      {{ t('settings.plugins.errorCount', { count: String(plugin.errors.length) }) }}
                    </span>
                  </div>
                </div>

                <!-- Chevron -->
                <span class="material-symbols-outlined text-[18px] text-[var(--color-text-tertiary)] opacity-60 transition-transform group-hover:translate-x-0.5 group-hover:opacity-100">
                  chevron_right
                </span>
              </button>
            </div>
          </div>
        </div>
      </section>
    </template>

    <!-- ConfirmDialog (batch action) -->
    <ConfirmDialog
      :open="confirmBatchAction !== null"
      :title="confirmBatchAction === 'enable'
        ? t('settings.plugins.bulkEnableTitle', { count: String(confirmBatchPlugins.length) })
        : t('settings.plugins.bulkDisableTitle', { count: String(confirmBatchPlugins.length) })"
      :confirm-label="confirmBatchAction === 'enable'
        ? t('settings.plugins.enable')
        : t('settings.plugins.disable')"
      :cancel-label="t('common.cancel')"
      :confirm-variant="confirmBatchAction === 'disable' ? 'danger' : 'primary'"
      :loading="isApplying"
      @close="confirmBatchAction = null"
      @confirm="handleBatchConfirm"
    >
      <div class="text-sm text-[var(--color-text-secondary)] leading-relaxed">
        {{ confirmBatchAction === 'enable'
          ? t('settings.plugins.bulkEnableBody', { names: confirmBatchNames })
          : t('settings.plugins.bulkDisableBody', { names: confirmBatchNames }) }}
      </div>
    </ConfirmDialog>
  </div>
</template>