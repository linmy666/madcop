<script setup lang="ts">
// v3.0 — Settings (Vue 3 SFC translation from React Settings.tsx)
// Phase 1: Main orchestrator + ProviderSettings + SortableProviderCard
// Helper functions (ProviderFormModal, confirm dialogs, JSON helpers, etc.) → Phase 2

import { ref, onMounted, watch, computed, type Ref } from 'vue'
import { useSettingsStore } from '../stores/settingsStore'
import { useProviderStore } from '../stores/providerStore'
import { useTranslation } from '../../i18n'
import { useUIStore } from '../stores/uiStore'
import AdapterSettings from './AdapterSettings.vue'
import ComputerUseSettings from './ComputerUseSettings.vue'
import McpSettings from './McpSettings.vue'
import TerminalSettings from './TerminalSettings.vue'
import DiagnosticsSettings from './DiagnosticsSettings.vue'
import TraceList from './TraceList.vue'
import ActivitySettings from './ActivitySettings.vue'
import MemorySettings from './MemorySettings.vue'

// ─── Constants ───────────────────────────────────────────────
const MADCOP_BUILT_IN_PROVIDER_A = 'provider-0'
const MADCOP_BUILT_IN_PROVIDER_B = 'provider-1'
const BUILT_IN_PROVIDER_IDS = [MADCOP_BUILT_IN_PROVIDER_A, MADCOP_BUILT_IN_PROVIDER_B] as const

// ─── Helper type & pure functions (from React lines 260-326) ─
type ProviderListItem =
  | { id: typeof MADCOP_BUILT_IN_PROVIDER_A; kind: 'provider-0' }
  | { id: typeof MADCOP_BUILT_IN_PROVIDER_B; kind: 'provider-1' }
  | { id: string; kind: 'saved'; provider: { id: string; name: string; baseUrl: string; models: { main: string }; presetId: string; apiFormat?: string } }

function defaultProviderOrder(providers: ProviderListItem[] extends { id: string; kind: string }[] ? never : never): string[] {
  // Note: providers parameter type is simplified for Vue; see buildProviderListItems below
  return []
}

// Re-implemented for Vue type safety
function defaultProviderOrderImpl(providerIds: string[]): string[] {
  return [...providerIds, ...BUILT_IN_PROVIDER_IDS]
}

function normalizeProviderOrder(providerOrder: string[] | undefined, providers: string[]): string[] {
  const knownIds = new Set<string>(defaultProviderOrderImpl(providers))
  const seen = new Set<string>()
  const order: string[] = []

  const source = providerOrder && providerOrder.length > 0
    ? providerOrder
    : defaultProviderOrderImpl(providers)

  for (const id of source) {
    if (!knownIds.has(id) || seen.has(id)) continue
    seen.add(id)
    order.push(id)
  }

  for (const id of defaultProviderOrderImpl(providers)) {
    if (seen.has(id)) continue
    seen.add(id)
    order.push(id)
  }

  return order
}

function buildProviderListItems(
  providers: Array<{ id: string; name: string; baseUrl: string; models: { main: string }; presetId: string; apiFormat?: string }>,
  providerOrder: string[] | undefined,
): ProviderListItem[] {
  const savedItems = new Map(
    providers.map((p) => [
      p.id,
      { id: p.id, kind: 'saved' as const, provider: p },
    ]),
  )
  const items = new Map<string, ProviderListItem>(savedItems)

  return normalizeProviderOrder(providerOrder, providers.map((p) => p.id))
    .map((id) => items.get(id))
    .filter((item): item is ProviderListItem => item !== undefined)
}

function providerItemTestId(item: ProviderListItem): string {
  switch (item.kind) {
    case 'provider-0': return 'provider-0-card'
    case 'provider-1': return 'provider-1-card'
    case 'saved': return `provider-${item.provider.id}`
  }
}

// ─── Reactive state ──────────────────────────────────────────
const activeTab = ref('providers')
const t = useTranslation()

// Subscribe to pendingSettingsTab from UI store
const uiStore = useUIStore()
watch(
  () => uiStore.pendingSettingsTab,
  (newTab) => {
    if (!newTab) return
    activeTab.value = newTab as any
    uiStore.setPendingSettingsTab(null)
  },
)

// ─── ProviderSettings reactive state ─────────────────────────
const providerStore = useProviderStore()
const settingsStore = useSettingsStore()
const fetchSettings = () => { /* settingsStore.fetchAll() — stub for Phase 2 */ }

const editingProvider = ref<any>(null)
const showCreateModal = ref(false)
const pendingDeleteProvider = ref<any>(null)
const isDeletingProvider = ref(false)
const testResults = ref<Record<string, { loading: boolean; result?: any }>>({})
// Presets map
const presetMap = computed(() => {
  const presets = (providerStore as any).presets || []
  return new Map(presets.map((p: any) => [p.id, p]))
})

const providerItems = computed(() => {
  const providers = (providerStore as any).providers || []
  const providerOrder = (providerStore as any).providerOrder
  return buildProviderListItems(providers, providerOrder)
})

const isClaudeOfficialActive = computed(() => {
  return (providerStore as any).hasLoadedProviders && (providerStore as any).activeId === null
})
const isBuiltinProviderActive = computed(() => {
  return (providerStore as any).hasLoadedProviders && (providerStore as any).activeId === MADCOP_BUILT_IN_PROVIDER_B
})

// ─── ProviderSettings actions ────────────────────────────────
async function handleDelete(provider: any) {
  if ((providerStore as any).activeId === provider.id) return
  pendingDeleteProvider.value = provider
}

async function confirmDelete() {
  if (!pendingDeleteProvider.value) return
  isDeletingProvider.value = true
  try {
    await (providerStore as any).deleteProvider(pendingDeleteProvider.value.id)
    pendingDeleteProvider.value = null
  } catch (error) {
    console.error(error)
  } finally {
    isDeletingProvider.value = false
  }
}

async function handleTest(provider: any) {
  testResults.value = { ...testResults.value, [provider.id]: { loading: true } }
  try {
    const result = await (providerStore as any).testProvider(provider.id)
    testResults.value = { ...testResults.value, [provider.id]: { loading: false, result } }
  } catch {
    testResults.value = {
      ...testResults.value,
      [provider.id]: { loading: false, result: { connectivity: { success: false, latencyMs: 0, error: t('settings.providers.requestFailed') } } },
    }
  }
}

async function handleActivate(id: string) {
  await (providerStore as any).activateProvider(id)
  await fetchSettings()
}

async function handleActivateOfficial() {
  await (providerStore as any).activateOfficial()
  await fetchSettings()
}

// Fetch providers on mount
onMounted(async () => {
  await (providerStore as any).fetchProviders()
  await (providerStore as any).fetchPresets()
})

// ─── Placeholder props for sub-components ────────────────────
// TODO: Phase 2 — implement SkillList, SkillDetail, PluginList,
// PluginDetail, MarkdownRenderer, ClaudeOfficialLogin, ChatGPTOfficialLogin
// as proper Vue components.
</script>

<script lang="ts">
/**
 * Phase 2 placeholder: helper components from React lines 696-4661
 * (ProviderFormModal, ConfirmDialog, ClaudeOfficialLogin, ChatGPTOfficialLogin,
 *  SkillList, SkillDetail, PluginList, PluginDetail, GeneralSettings,
 *  H5AccessSettings, AgentsSettings, SkillSettings, PluginSettings, AboutSettings)
 * are deferred to Phase 2. Below are minimal inline stubs.
 */
import { defineComponent, h } from 'vue'

// ─── TabButton ───────────────────────────────────────────────
export const TabButton = defineComponent({
  props: {
    icon: { type: String, required: true },
    label: { type: String, required: true },
    active: { type: Boolean, default: false },
  },
  emits: ['click'],
  setup(props, { emit }) {
    return () =>
      h(
        'button',
        {
          onClick: () => emit('click'),
          class: [
            'w-full flex items-center gap-2.5 px-4 py-2.5 text-sm text-left transition-colors',
            props.active
              ? 'bg-[var(--color-surface-selected)] text-[var(--color-text-primary)] font-medium'
              : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]',
          ],
        },
        [
          h('span', { class: 'material-symbols-outlined text-[18px]' }, props.icon),
          props.label,
        ],
      )
  },
})

// ─── SortableProviderCard (non-dnd version) ──────────────────
// TODO: @dnd-kit drag-and-drop will be replaced with Vue native drag events in Phase 2
export const SortableProviderCard = defineComponent({
  props: {
    item: { type: Object, required: true },
    isActive: { type: Boolean, default: false },
    dragLabel: { type: String, required: true },
    title: { type: String, required: true },
    subtitle: { type: String, required: true },
    badges: { type: String, default: '' },
    result: { type: String, default: '' },
    actions: { type: String, default: '' },
    details: { type: String, default: '' },
    onActivate: { type: Function, default: null },
  },
  emits: [],
  setup(props) {
    return () => {
      const itemTestId = (() => {
        if (props.item.kind === 'provider-0') return 'provider-0-card'
        if (props.item.kind === 'provider-1') return 'provider-1-card'
        return `provider-${props.item.provider?.id || props.item.id}`
      })()

      return h(
        'div',
        {
          'data-testid': itemTestId,
          class: [
            'group relative flex flex-col rounded-[8px] border transition-colors',
            props.isActive
              ? 'border-[var(--color-border-focus)] bg-[var(--color-surface-container-low)]'
              : 'border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] hover:border-[var(--color-border-focus)] hover:bg-[var(--color-surface-hover)]',
          ],
        },
        [
          h(
            'div',
            { class: 'flex items-center gap-2 px-3 py-3' },
            [
              // Drag handle (non-functional without dnd-kit)
              h(
                'button',
                {
                  type: 'button',
                  'aria-label': props.dragLabel,
                  title: props.dragLabel,
                  class:
                    'flex h-8 w-8 shrink-0 cursor-grab items-center justify-center rounded-[6px] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-container-high)] hover:text-[var(--color-text-secondary)] focus:outline-none',
                  style: { touchAction: 'none' },
                },
                [h('span', { class: 'material-symbols-outlined text-[18px]' }, 'drag_indicator')],
              ),
              // Provider info button
              h(
                'button',
                {
                  type: 'button',
                  onClick: props.onActivate,
                  'aria-disabled': !props.onActivate,
                  class: [
                    'flex min-w-0 flex-1 items-center gap-3 rounded-[6px] text-left focus:outline-none',
                    props.onActivate ? 'cursor-pointer' : 'cursor-default',
                  ],
                },
                [
                  h('span', {
                    class: `h-2.5 w-2.5 shrink-0 rounded-full ${props.isActive ? 'bg-[var(--color-success)]' : 'bg-[var(--color-text-tertiary)]'}`,
                  }),
                  h(
                    'span',
                    { class: 'min-w-0 flex-1' },
                    [
                      h(
                        'span',
                        { class: 'flex min-w-0 items-center gap-2' },
                        [
                          h('span', { class: 'truncate text-sm font-semibold text-[var(--color-text-primary)]' }, props.title),
                          props.badges ? h('span', { class: 'text-xs' }, props.badges) : null,
                        ],
                      ),
                      h('span', { class: 'mt-0.5 block truncate text-xs text-[var(--color-text-tertiary)]' }, props.subtitle),
                      props.result ? h('div', { class: 'text-xs' }, props.result) : null,
                    ],
                  ),
                ],
              ),
              // Actions (hidden on mobile, shown on hover)
              props.actions
                ? h(
                    'div',
                    { class: 'flex shrink-0 items-center gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100' },
                    [h('span', { class: 'text-xs' }, props.actions)],
                  )
                : null,
            ],
          ),
          // Details (expanded content for active provider)
          props.details ? h('div', { class: 'border-t border-[var(--color-border-separator)] px-4 pb-4 pt-3' }, props.details) : null,
        ],
      )
    }
  },
})

// ─── Placeholder sub-components (Phase 2) ────────────────────
export const Placeholder = defineComponent({
  props: { label: { type: String, default: 'TODO: Phase 2' } },
  setup(props) {
    return () =>
      h('div', { class: 'p-6 text-center text-sm text-[var(--color-text-tertiary)]' }, [
        '<!-- TODO --> ',
        props.label,
      ])
  },
})
</script>

<template>
  <!-- ─── Settings Page ────────────────────────────────────── -->
  <div class="flex-1 flex flex-col overflow-hidden bg-[var(--color-surface)]">
    <div class="flex-1 flex overflow-hidden">
      <!-- Tab navigation -->
      <div class="w-[180px] border-r border-[var(--color-border)] py-3 flex-shrink-0 flex flex-col">
        <div class="flex-1">
          <TabButton icon="dns" :label="t('settings.tab.providers')" :active="activeTab === 'providers'" @click="activeTab = 'providers'" />
          <TabButton icon="tune" :label="t('settings.tab.general')" :active="activeTab === 'general'" @click="activeTab = 'general'" />
          <TabButton icon="qr_code_2" :label="t('settings.tab.h5Access')" :active="activeTab === 'h5Access'" @click="activeTab = 'h5Access'" />
          <TabButton icon="chat" :label="t('settings.tab.adapters')" :active="activeTab === 'adapters'" @click="activeTab = 'adapters'" />
          <TabButton icon="terminal" :label="t('settings.tab.terminal')" :active="activeTab === 'terminal'" @click="activeTab = 'terminal'" />
          <TabButton icon="dns" :label="t('settings.tab.mcp')" :active="activeTab === 'mcp'" @click="activeTab = 'mcp'" />
          <TabButton icon="smart_toy" :label="t('settings.tab.agents')" :active="activeTab === 'agents'" @click="activeTab = 'agents'" />
          <TabButton icon="auto_awesome" :label="t('settings.tab.skills')" :active="activeTab === 'skills'" @click="activeTab = 'skills'" />
          <TabButton icon="history_edu" :label="t('settings.tab.memory')" :active="activeTab === 'memory'" @click="activeTab = 'memory'" />
          <TabButton icon="extension" :label="t('settings.tab.plugins')" :active="activeTab === 'plugins'" @click="activeTab = 'plugins'" />
          <TabButton icon="mouse" :label="t('settings.tab.computerUse')" :active="activeTab === 'computerUse'" @click="activeTab = 'computerUse'" />
          <TabButton icon="monitoring" :label="t('settings.tab.activity')" :active="activeTab === 'activity'" @click="activeTab = 'activity'" />
          <TabButton icon="account_tree" :label="t('settings.tab.trace')" :active="activeTab === 'trace'" @click="activeTab = 'trace'" />
          <TabButton icon="monitor_heart" :label="t('settings.tab.diagnostics')" :active="activeTab === 'diagnostics'" @click="activeTab = 'diagnostics'" />
        </div>
        <div class="border-t border-[var(--color-border)]/40 pt-1">
          <TabButton icon="info" :label="t('settings.tab.about')" :active="activeTab === 'about'" @click="activeTab = 'about'" />
        </div>
      </div>

      <!-- Tab content; trace embeds a full-bleed page that manages its own scroll -->
      <div :class="activeTab === 'trace' ? 'flex-1 flex min-h-0 flex-col overflow-hidden' : 'flex-1 overflow-y-auto px-8 py-6'">
        <!-- Providers -->
        <template v-if="activeTab === 'providers'">
          <div class="max-w-2xl">
            <div class="flex items-center justify-between mb-4">
              <div>
                <h2 class="text-base font-semibold text-[var(--color-text-primary)]">{{ t('settings.providers.title') }}</h2>
                <p class="text-sm text-[var(--color-text-tertiary)] mt-0.5">{{ t('settings.providers.description') }}</p>
              </div>
              <button
                class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-[var(--color-border)] bg-[var(--color-surface-container)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] transition-colors"
                @click="showCreateModal = true"
                :disabled="false"
              >
                <span class="material-symbols-outlined text-[16px]">add</span>
                {{ t('settings.providers.addProvider') }}
              </button>
            </div>

            <!--
              TODO: @dnd-kit drag-and-drop (DndContext + SortableContext + useSortable)
              will be replaced with Vue native drag events in Phase 2.
              For now, providers are rendered as a static list.
            -->
            <div class="flex flex-col gap-2">
              <template v-for="item in providerItems" :key="item.id">
                <!-- Provider-0 (Claude official) -->
                <SortableProviderCard
                  v-if="item.kind === 'provider-0'"
                  :item="item"
                  :is-active="isClaudeOfficialActive"
                  :drag-label="t('settings.providers.dragToReorder')"
                  :title="t('settings.providers.officialName')"
                  :subtitle="t('settings.providers.officialDesc')"
                  :badges="isClaudeOfficialActive ? t('settings.providers.default') : ''"
                  :actions="''"
                />
                <!-- Provider-1 (OpenAI official) -->
                <SortableProviderCard
                  v-else-if="item.kind === 'provider-1'"
                  :item="item"
                  :is-active="isBuiltinProviderActive"
                  :drag-label="t('settings.providers.dragToReorder')"
                  :title="t('settings.providers.openaiOfficialName')"
                  :subtitle="t('settings.providers.openaiOfficialDesc')"
                  :badges="isBuiltinProviderActive ? t('settings.providers.default') : ''"
                  :actions="''"
                />
                <!-- Saved provider -->
                <SortableProviderCard
                  v-else
                  :item="item"
                  :is-active="providerStore.activeId === item.provider.id"
                  :drag-label="t('settings.providers.dragToReorder')"
                  :title="item.provider.name"
                  :subtitle="item.provider.baseUrl + ' · ' + item.provider.models.main"
                  :badges="`
                    ${presetMap.get(item.provider.presetId)?.name || ''}
                    ${item.provider.apiFormat && item.provider.apiFormat !== 'anthropic'
                      ? (item.provider.apiFormat === 'openai_chat' ? 'OpenAI Chat' : 'OpenAI Responses')
                      : ''}
                    ${providerStore.activeId === item.provider.id ? t('settings.providers.default') : ''}
                  `".trim()}
                  :result=""
                  :actions=""
                />
              </template>
            </div>

            <!-- Loading state -->
            <div v-if="providerStore.isLoading && providerItems.length === 0" class="flex justify-center py-8">
              <div class="h-12 w-12 rounded-full border-2 border-[var(--color-brand)] border-t-transparent animate-spin"></div>
            </div>

            <!-- Create Modal placeholder -->
            <!-- TODO: Phase 2 — ProviderFormModal with create/edit forms -->
            <div v-if="showCreateModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
              <div class="rounded-lg bg-[var(--color-surface)] p-6 w-full max-w-lg">
                <h3 class="text-base font-semibold mb-4">{{ t('settings.providers.addProvider') }}</h3>
                <p class="text-sm text-[var(--color-text-tertiary)] mb-4">TODO: Phase 2 — ProviderFormModal create form</p>
                <button
                  class="px-3 py-1.5 text-xs rounded border border-[var(--color-border)]"
                  @click="showCreateModal = false"
                >Close</button>
              </div>
            </div>

            <!-- Edit Modal placeholder -->
            <div v-if="editingProvider" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
              <div class="rounded-lg bg-[var(--color-surface)] p-6 w-full max-w-lg">
                <h3 class="text-base font-semibold mb-4">Edit {{ editingProvider.name }}</h3>
                <p class="text-sm text-[var(--color-text-tertiary)] mb-4">TODO: Phase 2 — ProviderFormModal edit form</p>
                <button
                  class="px-3 py-1.5 text-xs rounded border border-[var(--color-border)]"
                  @click="editingProvider = null"
                >Close</button>
              </div>
            </div>

            <!-- Confirm Delete Dialog -->
            <div
              v-if="pendingDeleteProvider"
              class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
            >
              <div class="rounded-lg bg-[var(--color-surface)] p-6 w-full max-w-sm">
                <h3 class="text-base font-semibold mb-2">{{ t('common.delete') }}</h3>
                <p class="text-sm text-[var(--color-text-tertiary)] mb-4">
                  {{ t('settings.providers.confirmDelete', { name: pendingDeleteProvider.name }) }}
                </p>
                <div class="flex justify-end gap-2">
                  <button
                    class="px-3 py-1.5 text-xs rounded border border-[var(--color-border)]"
                    :disabled="isDeletingProvider"
                    @click="pendingDeleteProvider = null"
                  >{{ t('common.cancel') }}</button>
                  <button
                    class="px-3 py-1.5 text-xs rounded bg-[var(--color-error)] text-white"
                    :disabled="isDeletingProvider"
                    @click="confirmDelete"
                  >{{ isDeletingProvider ? '...' : t('common.delete') }}</button>
                </div>
              </div>
            </div>
          </div>
        </template>

        <!-- Activity -->
        <ActivitySettings v-if="activeTab === 'activity'" />

        <!-- General — TODO: Phase 2 -->
        <Placeholder v-if="activeTab === 'general'" label="TODO: Phase 2 — GeneralSettings (theme, language, shortcuts, output style)" />

        <!-- H5Access — TODO: Phase 2 -->
        <Placeholder v-if="activeTab === 'h5Access'" label="TODO: Phase 2 — H5AccessSettings (QR, LAN access, public URL)" />

        <!-- Adapters -->
        <AdapterSettings v-if="activeTab === 'adapters'" />

        <!-- Terminal -->
        <TerminalSettings v-if="activeTab === 'terminal'" :show-preferences="true" />

        <!-- MCP -->
        <McpSettings v-if="activeTab === 'mcp'" />

        <!-- Agents — TODO: Phase 2 -->
        <Placeholder v-if="activeTab === 'agents'" label="TODO: Phase 2 — AgentsSettings (agent definitions, MCP agents)" />

        <!-- Skills — TODO: Phase 2 -->
        <Placeholder v-if="activeTab === 'skills'" label="TODO: Phase 2 — SkillSettings (SkillList + SkillDetail)" />

        <!-- Memory -->
        <MemorySettings v-if="activeTab === 'memory'" />

        <!-- Plugins — TODO: Phase 2 -->
        <Placeholder v-if="activeTab === 'plugins'" label="TODO: Phase 2 — PluginSettings (PluginList + PluginDetail)" />

        <!-- ComputerUse -->
        <ComputerUseSettings v-if="activeTab === 'computerUse'" />

        <!-- Trace -->
        <TraceList v-if="activeTab === 'trace'" />

        <!-- Diagnostics -->
        <DiagnosticsSettings v-if="activeTab === 'diagnostics'" />

        <!-- About — TODO: Phase 2 -->
        <Placeholder v-if="activeTab === 'about'" label="TODO: Phase 2 — AboutSettings (version, build info, stats, update)" />
      </div>
    </div>
  </div>
</template>