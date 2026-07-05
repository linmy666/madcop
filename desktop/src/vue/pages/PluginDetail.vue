<script setup lang="ts">
// v3.0 — PluginDetail (Vue 3)
// Full translation of PluginDetail.tsx (755 lines) → Vue SFC
// Rules: className → class, useState → ref(), useMemo → computed(),
// lucide-react → material-symbols-outlined, Tailwind + --color-* verbatim.

import { ref, computed } from 'vue'
import { usePluginStore } from '../stores/pluginStore'
import { useSessionStore } from '../stores/sessionStore'
import { useUIStore } from '../stores/uiStore'
import { useSkillStore } from '../stores/skillStore'
import { useAgentStore } from '../stores/agentStore'
import { useMcpStore } from '../stores/mcpStore'
import { useTranslation } from '../i18n'
import { SETTINGS_TAB_ID, useTabStore } from '../stores/tabs'
import Button from '../components/shared/Button.vue'
import ConfirmDialog from '../components/shared/ConfirmDialog.vue'
import type { PluginCapabilityKey } from '../types/plugin'

// Child component imports
import StatusPill from '../components/plugins/StatusPill.vue'
import MetaPill from '../components/plugins/MetaPill.vue'
import DetailStat from '../components/plugins/DetailStat.vue'
import CapabilityPreviewSection from '../components/plugins/CapabilityPreviewSection.vue'
import SkillPreviewCard from '../components/plugins/SkillPreviewCard.vue'
import McpPreviewCard from '../components/plugins/McpPreviewCard.vue'
import CommandPreviewCard from '../components/plugins/CommandPreviewCard.vue'
import AgentPreviewCard from '../components/plugins/AgentPreviewCard.vue'
import HookPreviewCard from '../components/plugins/HookPreviewCard.vue'

// ─── Constants ────────────────────────────────────────────────────

const CAPABILITY_ORDER: PluginCapabilityKey[] = ['lspServers']

// ─── Stores ───────────────────────────────────────────────────────

const pluginStore = usePluginStore()
const sessionStore = useSessionStore()
const uiStore = useUIStore()
const skillStore = useSkillStore()
const agentStore = useAgentStore()
const mcpStore = useMcpStore()
const t = useTranslation()

// ─── Local reactive state ─────────────────────────────────────────

const actionKey = ref<string | null>(null)
const showUninstallDialog = ref(false)

// ─── Computed (useMemo replacements) ──────────────────────────────

const selectedPlugin = computed(() => pluginStore.selectedPlugin)
const isDetailLoading = computed(() => pluginStore.isDetailLoading)
const isApplying = computed(() => pluginStore.isApplying)

const sessions = computed(() => sessionStore.sessions)
const activeSessionId = computed(() => sessionStore.activeSessionId)

const activeSession = computed(() =>
  sessions.value.find((session) => session.id === activeSessionId.value)
)
const currentWorkDir = computed(() => activeSession.value?.workDir ?? undefined)

const otherCapabilityItems = computed(() =>
  CAPABILITY_ORDER.map((key) => ({
    key,
    items: selectedPlugin.value?.capabilities[key] ?? [],
  }))
)

const canMutate = computed(() => {
  const p = selectedPlugin.value
  if (!p) return false
  return p.scope !== 'managed' && p.scope !== 'builtin'
})

const canNavigateSharedCapabilities = computed(() => {
  return selectedPlugin.value?.enabled ?? false
})

// ─── Helpers ──────────────────────────────────────────────────────

const addToast = (type: 'success' | 'error' | 'warning', message: string) => {
  uiStore.showToast(message, type)
}

const runAction = async (key: string, fn: () => Promise<string>) => {
  actionKey.value = key
  try {
    const message = await fn()
    addToast('success', message)
  } catch (err) {
    addToast('error', err instanceof Error ? err.message : String(err))
  } finally {
    actionKey.value = null
  }
}

const handleReload = async () => {
  actionKey.value = 'reload'
  try {
    const summary = await pluginStore.reloadPlugins(
      currentWorkDir.value,
      activeSessionId.value ?? undefined
    )
    addToast(
      summary.errors > 0 ? 'warning' : 'success',
      t('settings.plugins.reloadToast', {
        enabled: String(summary.enabled),
        skills: String(summary.skills),
        errors: String(summary.errors),
      })
    )
  } catch (err) {
    addToast('error', err instanceof Error ? err.message : String(err))
  } finally {
    actionKey.value = null
  }
}

const openSettingsTab = (tab: 'skills' | 'agents' | 'mcp') => {
  uiStore.setPendingSettingsTab(tab)
  useTabStore().openTab(SETTINGS_TAB_ID, 'Settings', 'settings')
}

const handleOpenSkill = async (skillName: string) => {
  if (!canNavigateSharedCapabilities.value) {
    addToast('warning', t('settings.plugins.sharedNavigationDisabled'))
    return
  }
  openSettingsTab('skills')
  await skillStore.fetchSkillDetail(
    'plugin',
    skillName,
    currentWorkDir.value,
    'plugins'
  )
  const { selectedSkill: s, error } = skillStore.getState()
  if (!s && error) {
    addToast('error', error)
  }
}

const handleOpenAgent = async (agentType: string) => {
  if (!canNavigateSharedCapabilities.value) {
    addToast('warning', t('settings.plugins.sharedNavigationDisabled'))
    return
  }
  openSettingsTab('agents')
  await agentStore.fetchAgents(currentWorkDir.value)
  const { allAgents } = agentStore.getState()
  const agent = allAgents.find((entry) => entry.agentType === agentType)
  if (!agent) {
    addToast('error', `Unable to locate agent: ${agentType}`)
    return
  }
  agentStore.selectAgent(agent, 'plugins')
}

const handleOpenMcpServer = async (serverName: string) => {
  if (!canNavigateSharedCapabilities.value) {
    addToast('warning', t('settings.plugins.sharedNavigationDisabled'))
    return
  }
  openSettingsTab('mcp')
  await mcpStore.fetchServers(undefined, currentWorkDir.value)
  const { servers } = mcpStore.getState()
  const server = servers.find((entry) => entry.name === serverName)
  if (!server) {
    addToast('error', `Unable to locate MCP server: ${serverName}`)
    return
  }
  mcpStore.selectServer(server)
}
</script>

<template>
  <div class="flex flex-col gap-4 min-w-0">
    <!-- Back button -->
    <div>
      <button
        @click="pluginStore.clearSelection"
        class="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]"
      >
        <span class="material-symbols-outlined text-[16px]">arrow_back</span>
        {{ t('settings.plugins.back') }}
      </button>
    </div>

    <!-- Plugin header -->
    <section
      v-if="!isDetailLoading"
      class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] overflow-hidden"
    >
      <div class="grid gap-4 px-5 py-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.9fr)] lg:items-start">
        <!-- Left: name, status, meta -->
        <div class="min-w-0">
          <div class="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--color-text-tertiary)] mb-2">
            {{ t('settings.plugins.entryEyebrow') }}
          </div>
          <div class="flex flex-wrap items-center gap-2 mb-2">
            <h3 class="text-[22px] font-semibold leading-tight text-[var(--color-text-primary)] break-all">
              {{ selectedPlugin?.name }}
            </h3>
            <StatusPill
              v-if="selectedPlugin"
              :enabled="selectedPlugin.enabled"
              :has-errors="selectedPlugin.hasErrors"
            />
            <MetaPill v-if="selectedPlugin">
              {{ t(`settings.plugins.scope.${selectedPlugin.scope}`) }}
            </MetaPill>
            <MetaPill v-if="selectedPlugin">
              {{ selectedPlugin.marketplace }}
            </MetaPill>
            <MetaPill v-if="selectedPlugin?.version">
              v{{ selectedPlugin.version }}
            </MetaPill>
          </div>
          <p class="max-w-4xl text-sm leading-6 text-[var(--color-text-secondary)]">
            {{ selectedPlugin?.description || t('settings.plugins.noDescription') }}
          </p>
          <div class="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-[var(--color-text-tertiary)]">
            <span v-if="selectedPlugin?.authorName">
              {{ t('settings.plugins.author', { value: selectedPlugin.authorName }) }}
            </span>
            <span v-if="selectedPlugin?.projectPath">
              {{ t('settings.plugins.projectPath', { value: selectedPlugin.projectPath }) }}
            </span>
            <span v-if="selectedPlugin?.installPath">
              {{ t('settings.plugins.installPath', { value: selectedPlugin.installPath }) }}
            </span>
          </div>
        </div>

        <!-- Right: stats -->
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-2">
          <DetailStat
            v-if="selectedPlugin"
            :label="t('settings.plugins.summary.skills')"
            :value="String(selectedPlugin.componentCounts?.skills ?? 0)"
            icon="auto_awesome"
          />
          <DetailStat
            v-if="selectedPlugin"
            :label="t('settings.plugins.summary.agents')"
            :value="String(selectedPlugin.componentCounts?.agents ?? 0)"
            icon="smart_toy"
          />
          <DetailStat
            v-if="selectedPlugin"
            :label="t('settings.plugins.summary.mcp')"
            :value="String(selectedPlugin.componentCounts?.mcpServers ?? 0)"
            icon="hub"
          />
          <DetailStat
            v-if="selectedPlugin"
            :label="t('settings.plugins.summary.hooks')"
            :value="String(selectedPlugin.componentCounts?.hooks ?? 0)"
            icon="bolt"
          />
        </div>
      </div>
    </section>

    <!-- Action buttons -->
    <section
      v-if="selectedPlugin"
      class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-4"
    >
      <div class="flex flex-wrap gap-2">
        <!-- Enable / Disable toggle -->
        <Button
          v-if="canMutate"
          :variant="selectedPlugin.enabled ? 'secondary' : undefined"
          size="sm"
          :loading="isApplying && actionKey === (selectedPlugin.enabled ? 'disable' : 'enable')"
          @click="
            runAction(
              selectedPlugin.enabled ? 'disable' : 'enable',
              () =>
                selectedPlugin.enabled
                  ? pluginStore.disablePlugin(
                      selectedPlugin.id,
                      selectedPlugin.scope,
                      currentWorkDir,
                      activeSessionId ?? undefined
                    )
                  : pluginStore.enablePlugin(
                      selectedPlugin.id,
                      selectedPlugin.scope,
                      currentWorkDir,
                      activeSessionId ?? undefined
                    )
            )
          "
        >
          {{ selectedPlugin.enabled ? t('settings.plugins.disable') : t('settings.plugins.enable') }}
        </Button>

        <!-- Update -->
        <Button
          v-if="canMutate"
          variant="secondary"
          size="sm"
          :loading="isApplying && actionKey === 'update'"
          @click="
            runAction('update', () =>
              pluginStore.updatePlugin(
                selectedPlugin.id,
                selectedPlugin.scope,
                currentWorkDir,
                activeSessionId ?? undefined
              )
            )
          "
        >
          {{ t('settings.plugins.update') }}
        </Button>

        <!-- Apply / Reload -->
        <Button
          variant="secondary"
          size="sm"
          :loading="isApplying && actionKey === 'reload'"
          @click="handleReload"
        >
          {{ t('settings.plugins.apply') }}
        </Button>

        <!-- Uninstall -->
        <Button
          v-if="canMutate"
          variant="danger"
          size="sm"
          :loading="isApplying && actionKey === 'uninstall'"
          @click="showUninstallDialog = true"
        >
          {{ t('settings.plugins.uninstall') }}
        </Button>
      </div>

      <p v-if="!canMutate" class="mt-3 text-xs text-[var(--color-text-tertiary)]">
        {{
          selectedPlugin.scope === 'managed'
            ? t('settings.plugins.managedHint')
            : t('settings.plugins.builtinHint')
        }}
      </p>
      <p class="mt-3 text-xs text-[var(--color-text-tertiary)]">
        {{ t('settings.plugins.applyHint') }}
      </p>
    </section>

    <!-- Errors section -->
    <section
      v-if="selectedPlugin && selectedPlugin.errors.length > 0"
      class="rounded-2xl border border-[var(--color-error)]/20 bg-[var(--color-error)]/6 px-5 py-4"
    >
      <div class="flex items-center gap-2 mb-3">
        <span class="material-symbols-outlined text-[18px] text-[var(--color-error)]">
          error
        </span>
        <h4 class="text-sm font-semibold text-[var(--color-text-primary)]">
          {{ t('settings.plugins.errorsTitle') }}
        </h4>
      </div>
      <div class="flex flex-col gap-2">
        <div
          v-for="error in selectedPlugin.errors"
          :key="error"
          class="rounded-xl border border-[var(--color-error)]/15 bg-[var(--color-surface)] px-3 py-3 text-sm text-[var(--color-text-secondary)]"
        >
          {{ error }}
        </div>
      </div>
    </section>

    <!-- Capabilities section -->
    <section
      v-if="selectedPlugin"
      class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden"
    >
      <div class="px-5 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface-container-low)]">
        <h4 class="text-sm font-semibold text-[var(--color-text-primary)]">
          {{ t('settings.plugins.capabilitiesTitle') }}
        </h4>
        <p class="text-xs text-[var(--color-text-tertiary)] mt-1">
          {{ t('settings.plugins.capabilitiesHint') }}
        </p>
      </div>

      <div class="flex flex-col gap-4 p-4">
        <!-- Skills -->
        <CapabilityPreviewSection
          :title="t('settings.plugins.capabilityLabel.skills')"
          :count="selectedPlugin.skillEntries.length"
          :empty-label="t('settings.plugins.capabilityEmpty')"
          :hint="
            !canNavigateSharedCapabilities
              ? t('settings.plugins.sharedNavigationDisabled')
              : undefined
          "
        >
          <div
            v-if="selectedPlugin.skillEntries.length > 0"
            class="grid gap-3 xl:grid-cols-2"
          >
            <SkillPreviewCard
              v-for="skill in selectedPlugin.skillEntries"
              :key="skill.name"
              :name="skill.displayName || skill.name"
              :raw-name="skill.displayName ? skill.name : undefined"
              :description="skill.description"
              :version="skill.version"
              :disabled="!canNavigateSharedCapabilities"
              @click="handleOpenSkill(skill.name)"
            />
          </div>
        </CapabilityPreviewSection>

        <!-- MCP Servers -->
        <CapabilityPreviewSection
          :title="t('settings.plugins.capabilityLabel.mcpServers')"
          :count="selectedPlugin.mcpServerEntries.length"
          :empty-label="t('settings.plugins.capabilityEmpty')"
          :hint="
            !canNavigateSharedCapabilities
              ? t('settings.plugins.sharedNavigationDisabled')
              : undefined
          "
        >
          <div
            v-if="selectedPlugin.mcpServerEntries.length > 0"
            class="grid gap-3 xl:grid-cols-2"
          >
            <McpPreviewCard
              v-for="server in selectedPlugin.mcpServerEntries"
              :key="server.name"
              :name="server.displayName || server.name"
              :transport="server.transport"
              :summary="server.summary"
              :disabled="!canNavigateSharedCapabilities"
              @click="handleOpenMcpServer(server.name)"
            />
          </div>
        </CapabilityPreviewSection>

        <!-- Commands -->
        <CapabilityPreviewSection
          :title="t('settings.plugins.capabilityLabel.commands')"
          :count="selectedPlugin.commandEntries.length"
          :empty-label="t('settings.plugins.capabilityEmpty')"
        >
          <div
            v-if="selectedPlugin.commandEntries.length > 0"
            class="grid gap-3 xl:grid-cols-2"
          >
            <CommandPreviewCard
              v-for="command in selectedPlugin.commandEntries"
              :key="command.name"
              :name="command.name"
              :description="command.description"
            />
          </div>
        </CapabilityPreviewSection>

        <!-- Agents -->
        <CapabilityPreviewSection
          :title="t('settings.plugins.capabilityLabel.agents')"
          :count="selectedPlugin.agentEntries.length"
          :empty-label="t('settings.plugins.capabilityEmpty')"
          :hint="
            !canNavigateSharedCapabilities
              ? t('settings.plugins.sharedNavigationDisabled')
              : undefined
          "
        >
          <div
            v-if="selectedPlugin.agentEntries.length > 0"
            class="grid gap-3 xl:grid-cols-2"
          >
            <AgentPreviewCard
              v-for="agent in selectedPlugin.agentEntries"
              :key="agent.name"
              :name="agent.displayName || agent.name"
              :description="agent.description"
              :disabled="!canNavigateSharedCapabilities"
              @click="handleOpenAgent(agent.name)"
            />
          </div>
        </CapabilityPreviewSection>

        <!-- Hooks -->
        <CapabilityPreviewSection
          :title="t('settings.plugins.capabilityLabel.hooks')"
          :count="selectedPlugin.hookEntries.length"
          :empty-label="t('settings.plugins.capabilityEmpty')"
        >
          <div
            v-if="selectedPlugin.hookEntries.length > 0"
            class="grid gap-3 xl:grid-cols-2"
          >
            <HookPreviewCard
              v-for="(hook, index) in selectedPlugin.hookEntries"
              :key="`${hook.event}:${hook.matcher || 'all'}:${index}`"
              :event="hook.event"
              :matcher="hook.matcher"
              :actions="hook.actions"
            />
          </div>
        </CapabilityPreviewSection>

        <!-- Other capabilities (lspServers, etc.) -->
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div
            v-for="{ key, items } in otherCapabilityItems"
            :key="key"
            class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-4 py-3"
          >
            <div class="flex items-center justify-between gap-2 mb-2">
              <div class="text-sm font-semibold text-[var(--color-text-primary)]">
                {{ t(`settings.plugins.capabilityLabel.${key}`) }}
              </div>
              <span class="text-[11px] text-[var(--color-text-tertiary)]">
                {{ items.length }}
              </span>
            </div>
            <div v-if="items.length > 0" class="flex flex-wrap gap-2">
              <span
                v-for="item in items"
                :key="item"
                class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[11px] text-[var(--color-text-secondary)] break-all"
              >
                {{ item }}
              </span>
            </div>
            <div v-else class="text-xs text-[var(--color-text-tertiary)]">
              {{ t('settings.plugins.capabilityEmpty') }}
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Loading state -->
    <div v-if="isDetailLoading" class="flex justify-center py-12">
      <div
        class="animate-spin w-5 h-5 border-2 border-[var(--color-brand)] border-t-transparent rounded-full"
      />
    </div>

    <!-- Uninstall ConfirmDialog -->
    <ConfirmDialog
      :open="showUninstallDialog"
      :title="selectedPlugin ? t('settings.plugins.uninstall') : ''"
      :confirm-label="t('settings.plugins.uninstall')"
      :cancel-label="t('common.cancel')"
      confirm-variant="danger"
      :loading="isApplying && actionKey === 'uninstall'"
      @close="showUninstallDialog = false"
      @confirm="
        runAction(
          'uninstall',
          () =>
            pluginStore.uninstallPlugin(
              selectedPlugin!.id,
              selectedPlugin!.scope,
              false,
              currentWorkDir,
              activeSessionId ?? undefined
            )
        )
      "
    >
      {{
        selectedPlugin
          ? t('settings.plugins.confirmUninstall', { name: selectedPlugin.name })
          : ''
      }}
    </ConfirmDialog>
  </div>
</template>